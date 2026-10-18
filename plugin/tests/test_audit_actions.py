"""FR-R003 — custom actions + append-only audit tests.

Covers the reference implementation clients are told to copy
(docs/custom-actions.md, ROADLOG R-003):

- POST /api/orders/<id>/flag/ — record-scope reference action: appends
  exactly one audit entry, changes no order fields, 400+reason guard,
  401/404 shapes,
- POST /api/orders/bulk_flag/ — bulk-scope reference action: one entry
  per order, duplicate ids collapse, unknown ids answer 400+reason,
- GET /api/audit/ — append-only audit endpoint: newest first, paginated,
  object_type/object_id filters,
- POST /api/audit/ — append surface: actor is ALWAYS the authenticated
  request user, never client-supplied,
- append-only enforcement: PUT/PATCH/DELETE answer 405 by construction
  (no update/delete mixins exist),
- the OpenAPI schema exposes the audit endpoint and both action bodies
  (the thin client derives everything from the schema).

Infrastructure note: conftest mounts the demo rig apps in-memory; this
module creates the real test database with Django's own test utilities
(DiscoverRunner) because pytest-django is deliberately NOT a dependency.
Per-test isolation is an outer atomic block rolled back after each test.
"""
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from shop.models import AuditEntry, Category, Customer, Order, Product


# ---------------------------------------------------------------------------
# database plumbing (no pytest-django — Django test utilities, in-process)
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
    """Per-test isolation: everything inside the outer atomic rolls back."""
    with transaction.atomic():
        yield
        transaction.set_rollback(True)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api(db):
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user("ops1", "ops1@example.com", "pw12345")


@pytest.fixture
def auth_api(api, user):
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def order(db):
    cat = Category.objects.create(name=f"cat-{uuid4().hex[:8]}")
    product = Product.objects.create(
        category=cat, name="Thing", price=Decimal("9.99"), stock=5
    )
    customer = Customer.objects.create(name="Cust", email=f"{uuid4().hex[:8]}@example.com")
    return Order.objects.create(customer=customer, product=product)


@pytest.fixture
def second_order(db):
    cat = Category.objects.create(name=f"cat-{uuid4().hex[:8]}")
    product = Product.objects.create(
        category=cat, name="Other Thing", price=Decimal("19.99"), stock=3
    )
    customer = Customer.objects.create(name="Cust 2", email=f"{uuid4().hex[:8]}@example.com")
    return Order.objects.create(customer=customer, product=product)


def flag_url(pk):
    return reverse("order-flag", args=[pk])


def bulk_flag_url():
    return reverse("order-bulk-flag")


def audit_url():
    return reverse("audit-list")


# ---------------------------------------------------------------------------
# record-scope reference action: POST /api/orders/<id>/flag/
# ---------------------------------------------------------------------------

class TestRecordScopeFlag:
    def test_flag_appends_exactly_one_audit_entry(self, auth_api, order, user):
        response = auth_api.post(flag_url(order.pk), {"reason": "suspected fraud"}, format="json")
        assert response.status_code == 201
        body = response.json()
        assert body["action"] == "order.flag"
        assert body["object_type"] == "order"
        assert body["object_id"] == str(order.pk)
        assert body["actor"] == user.username  # derived from the request, never the body
        assert body["summary"] == "Order flagged: suspected fraud"
        assert body["data"] == {"reason": "suspected fraud"}
        assert AuditEntry.objects.count() == 1

    def test_flag_changes_no_order_fields(self, auth_api, order):
        before = (order.status, order.notes, order.total)
        response = auth_api.post(flag_url(order.pk), {"reason": "check"}, format="json")
        assert response.status_code == 201
        order.refresh_from_db()
        assert (order.status, order.notes, order.total) == before  # audit-only action

    def test_flag_missing_reason_is_400_with_reason_shape(self, auth_api, order):
        response = auth_api.post(flag_url(order.pk), {}, format="json")
        assert response.status_code == 400
        assert list(response.json().keys()) == ["reason"]  # R-001 guard shape, one key
        assert AuditEntry.objects.count() == 0

    def test_flag_unknown_order_is_404(self, auth_api):
        response = auth_api.post(flag_url(999999), {"reason": "x"}, format="json")
        assert response.status_code == 404

    def test_flag_unauthenticated_is_401(self, api, order):
        response = api.post(flag_url(order.pk), {"reason": "x"}, format="json")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# bulk-scope reference action: POST /api/orders/bulk_flag/
# ---------------------------------------------------------------------------

class TestBulkScopeFlag:
    def test_bulk_flag_appends_one_entry_per_order(self, auth_api, order, second_order, user):
        response = auth_api.post(
            bulk_flag_url(),
            {"ids": [order.pk, second_order.pk], "reason": "batch check"},
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert len(body) == 2  # one audit entry per order
        assert {entry["object_id"] for entry in body} == {str(order.pk), str(second_order.pk)}
        assert all(entry["action"] == "order.flag" for entry in body)
        assert all(entry["actor"] == user.username for entry in body)
        assert all(entry["data"] == {"reason": "batch check", "bulk": True, "batch": 2} for entry in body)

    def test_bulk_flag_collapses_duplicate_ids(self, auth_api, order, second_order):
        response = auth_api.post(
            bulk_flag_url(),
            {"ids": [order.pk, order.pk, second_order.pk], "reason": "dup"},
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert len(body) == 2  # one per DISTINCT order
        assert all(entry["data"]["batch"] == 2 for entry in body)

    def test_bulk_flag_unknown_ids_are_400_with_reason(self, auth_api, order):
        response = auth_api.post(
            bulk_flag_url(),
            {"ids": [order.pk, 999999], "reason": "x"},
            format="json",
        )
        assert response.status_code == 400
        assert "999999" in response.json()["reason"]
        assert AuditEntry.objects.count() == 0

    @pytest.mark.parametrize("payload", [{}, {"reason": "x"}, {"ids": []}])
    def test_bulk_flag_missing_ids_or_reason_is_400(self, auth_api, order, payload):
        response = auth_api.post(bulk_flag_url(), payload, format="json")
        assert response.status_code == 400
        assert list(response.json().keys()) == ["reason"]
        assert AuditEntry.objects.count() == 0

    def test_bulk_flag_non_integer_ids_are_400(self, auth_api, order):
        response = auth_api.post(
            bulk_flag_url(), {"ids": ["abc"], "reason": "x"}, format="json"
        )
        assert response.status_code == 400
        assert "list of order ids" in response.json()["reason"]

    def test_bulk_flag_unauthenticated_is_401(self, api, order):
        response = api.post(
            bulk_flag_url(), {"ids": [order.pk], "reason": "x"}, format="json"
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# the audit endpoint itself: GET/POST /api/audit/
# ---------------------------------------------------------------------------

class TestAuditEndpoint:
    def test_audit_list_is_newest_first(self, auth_api, order):
        auth_api.post(flag_url(order.pk), {"reason": "first"}, format="json")
        auth_api.post(flag_url(order.pk), {"reason": "second"}, format="json")
        response = auth_api.get(audit_url())
        assert response.status_code == 200
        results = response.json()["results"]
        assert results[0]["id"] > results[1]["id"]  # triage order: latest on top
        assert results[0]["data"]["reason"] == "second"

    def test_audit_list_is_paginated(self, auth_api, order):
        for i in range(12):  # PAGE_SIZE is 10 in the demo rig DRF policy
            AuditEntry.objects.create(
                action="order.flag", object_type="order", object_id=str(order.pk)
            )
        response = auth_api.get(audit_url())
        body = response.json()
        assert body["count"] == 12
        assert len(body["results"]) == 10
        assert body["previous"] is None
        assert body["next"] is not None
        page_two = auth_api.get(body["next"]).json()
        assert len(page_two["results"]) == 2
        assert page_two["previous"] is not None

    def test_audit_object_filters_back_the_record_subview(self, auth_api, order, second_order):
        AuditEntry.objects.create(action="order.flag", object_type="order", object_id=str(order.pk))
        AuditEntry.objects.create(action="order.flag", object_type="order", object_id=str(second_order.pk))
        AuditEntry.objects.create(action="invoice.sent", object_type="invoice", object_id=str(order.pk))
        response = auth_api.get(audit_url(), {"object_type": "order", "object_id": str(order.pk)})
        body = response.json()
        assert body["count"] == 1
        assert body["results"][0]["object_id"] == str(order.pk)
        assert body["results"][0]["object_type"] == "order"

    def test_direct_post_actor_is_never_client_supplied(self, auth_api, user):
        response = auth_api.post(
            audit_url(),
            {
                "action": "order.flag",
                "object_type": "order",
                "object_id": "1",
                "actor": "admin",  # hostile payload — must be ignored
                "summary": "spoofed",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["actor"] == user.username  # request user, always

    def test_direct_post_defaults(self, auth_api):
        response = auth_api.post(
            audit_url(),
            {"action": "invoice.sent", "object_type": "invoice", "object_id": "7"},
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["summary"] == ""
        assert body["data"] is None
        assert body["actor"] is None or isinstance(body["actor"], str)

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_audit_list_rejects_mutations_with_405(self, auth_api, method):
        response = getattr(auth_api, method)(audit_url())
        assert response.status_code == 405  # no update/delete mixins exist

    def test_audit_has_no_detail_route_at_all(self):
        # Stronger than 405: with only List+Create mixins the router never
        # generates a detail route, so audit rows have no URL surface to
        # mutate through — append-only is enforced by the router itself.
        entry = AuditEntry.objects.create(
            action="order.flag", object_type="order", object_id="1"
        )
        with pytest.raises(NoReverseMatch):
            reverse("audit-detail", args=[entry.pk])

    def test_audit_unauthenticated_is_401(self, api):
        assert api.get(audit_url()).status_code == 401
        assert (
            api.post(
                audit_url(),
                {"action": "x", "object_type": "y", "object_id": "1"},
                format="json",
            ).status_code
            == 401
        )


# ---------------------------------------------------------------------------
# OpenAPI contract (the thin client derives everything from the schema)
# ---------------------------------------------------------------------------

class TestSchemaContract:
    def test_audit_and_action_endpoints_are_in_the_schema(self, tmp_path):
        out = tmp_path / "schema.json"
        call_command("spectacular", "--format", "openapi-json", file=str(out))
        schema = json.loads(out.read_text())
        paths = schema["paths"]
        assert "post" in paths["/api/orders/{id}/flag/"]
        assert "post" in paths["/api/orders/bulk_flag/"]
        assert "get" in paths["/api/audit/"]
        assert "post" in paths["/api/audit/"]  # the append surface is documented
        flag_body = paths["/api/orders/{id}/flag/"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert "$ref" in flag_body  # FlagRequestSerializer documented
        bulk_body = paths["/api/orders/bulk_flag/"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert "$ref" in bulk_body  # BulkFlagRequestSerializer documented
