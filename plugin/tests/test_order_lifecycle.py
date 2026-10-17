"""FR-R001 — order lifecycle state machine + server contract tests.

Covers the reference implementation clients are told to copy
(docs/order-lifecycle.md, ROADLOG R-001):

- the ordered Status enum + the TRANSITIONS matrix (pure, no DB),
- POST /api/orders/<id>/transition/ — happy path, 409+reason guards,
  400 unknown/missing target, 401 unauthenticated, 404,
- GET /api/orders/<id>/history/ — append-only, oldest first, with actor,
- creation entry written on POST /api/orders/,
- the side-effect seam (_apply_side_effects TODO stubs) is actually
  invoked inside the transition and is a no-op by default,
- the OpenAPI schema exposes both endpoints (the thin client derives
  everything from the schema).

Infrastructure note: conftest mounts the demo rig apps in-memory; this
module creates the real test database with Django's own test utilities
(DiscoverRunner) because pytest-django is deliberately NOT a dependency.
Per-test isolation is an outer atomic block rolled back after each test.
"""
import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from django.urls import reverse
from rest_framework.test import APIClient

from shop.models import Category, Customer, IllegalTransition, Order, OrderHistory, Product

LEGAL_MOVES = [
    ("pending", "paid"),
    ("paid", "shipped"),
    ("paid", "refunded"),
    ("shipped", "refunded"),
]


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


def transition_url(pk):
    return reverse("order-transition", args=[pk])


def history_url(pk):
    return reverse("order-history", args=[pk])


# ---------------------------------------------------------------------------
# the machine itself (pure — no DB)
# ---------------------------------------------------------------------------

class TestStateMachine:
    def test_enum_is_declared_in_lifecycle_order(self):
        assert tuple(Order.Status.values) == ("pending", "paid", "shipped", "refunded")

    def test_status_order_pins_the_lifecycle(self):
        assert tuple(Order.STATUS_ORDER) == tuple(Order.Status.values)
        assert Order.STATUS_ORDER[0] == Order.Status.PENDING  # entry state

    @pytest.mark.parametrize(("current", "target"), LEGAL_MOVES)
    def test_legal_moves(self, current, target):
        assert Order.transition_allowed(current, target) is True

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("pending", "shipped"), ("pending", "refunded"),
            ("paid", "pending"), ("shipped", "pending"), ("shipped", "paid"),
            ("refunded", "pending"), ("refunded", "paid"), ("refunded", "shipped"),
        ],
    )
    def test_illegal_moves(self, current, target):
        assert Order.transition_allowed(current, target) is False

    def test_unknown_current_or_target_is_never_allowed(self):
        assert Order.transition_allowed("teleported", "paid") is False
        assert Order.transition_allowed("pending", "teleported") is False

    def test_apply_transition_rejects_unknown_target(self, db, order):
        with pytest.raises(IllegalTransition) as excinfo:
            order.apply_transition("teleported")
        assert "unknown status" in excinfo.value.reason

    def test_apply_transition_rejects_noop(self, db, order):
        with pytest.raises(IllegalTransition) as excinfo:
            order.apply_transition("pending")
        assert "already" in excinfo.value.reason


# ---------------------------------------------------------------------------
# POST /api/orders/<id>/transition/
# ---------------------------------------------------------------------------

class TestTransitionEndpoint:
    def test_happy_path_moves_status_and_writes_history(self, auth_api, order, user):
        resp = auth_api.post(transition_url(order.pk), {"transition": "paid"}, format="json")
        assert resp.status_code == 200
        assert resp.data["status"] == "paid"
        order.refresh_from_db()
        assert order.status == "paid"
        entry = order.history.get()
        assert entry.from_status == "pending"
        assert entry.to_status == "paid"
        assert entry.actor_id == user.pk
        assert entry.created_at is not None

    def test_full_forward_lifecycle(self, auth_api, order):
        for target in ("paid", "shipped", "refunded"):
            resp = auth_api.post(transition_url(order.pk), {"transition": target}, format="json")
            assert resp.status_code == 200, resp.data
        trail = list(OrderHistory.objects.filter(order=order).order_by("created_at", "id"))
        assert [(e.from_status, e.to_status) for e in trail] == [
            ("pending", "paid"), ("paid", "shipped"), ("shipped", "refunded"),
        ]

    def test_paid_to_refunded_is_legal(self, auth_api, order):
        order.apply_transition("paid")
        resp = auth_api.post(transition_url(order.pk), {"transition": "refunded"}, format="json")
        assert resp.status_code == 200
        assert resp.data["status"] == "refunded"

    def test_illegal_transition_is_409_with_reason_and_no_side_effects(
        self, auth_api, order
    ):
        before = OrderHistory.objects.filter(order=order).count()
        resp = auth_api.post(transition_url(order.pk), {"transition": "shipped"}, format="json")
        assert resp.status_code == 409
        assert "pending" in resp.data["reason"] and "shipped" in resp.data["reason"]
        order.refresh_from_db()
        assert order.status == "pending"  # unchanged
        assert OrderHistory.objects.filter(order=order).count() == before  # nothing appended

    def test_terminal_state_rejects_everything(self, auth_api, order):
        order.apply_transition("paid")
        order.apply_transition("shipped")
        order.apply_transition("refunded")
        resp = auth_api.post(transition_url(order.pk), {"transition": "paid"}, format="json")
        assert resp.status_code == 409
        assert "terminal" in resp.data["reason"]

    def test_noop_transition_is_409(self, auth_api, order):
        resp = auth_api.post(transition_url(order.pk), {"transition": "pending"}, format="json")
        assert resp.status_code == 409
        assert "already" in resp.data["reason"]

    def test_unknown_target_is_400_with_reason(self, auth_api, order):
        resp = auth_api.post(transition_url(order.pk), {"transition": "teleported"}, format="json")
        assert resp.status_code == 400
        assert "unknown status 'teleported'" in resp.data["reason"]
        assert "pending, paid, shipped, refunded" in resp.data["reason"]

    def test_missing_transition_field_is_400_with_reason(self, auth_api, order):
        resp = auth_api.post(transition_url(order.pk), {}, format="json")
        assert resp.status_code == 400
        assert "missing required field 'transition'" in resp.data["reason"]

    def test_transition_missing_order_is_404(self, auth_api):
        resp = auth_api.post(transition_url(999999), {"transition": "paid"}, format="json")
        assert resp.status_code == 404

    def test_unauthenticated_transition_is_rejected(self, api, order):
        resp = api.post(transition_url(order.pk), {"transition": "paid"}, format="json")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/orders/<id>/history/
# ---------------------------------------------------------------------------

class TestHistoryEndpoint:
    def test_trail_is_oldest_first_with_actor(self, auth_api, order, user):
        other = User.objects.create_user("ops2", "ops2@example.com", "pw12345")
        order.apply_transition("paid", actor=user)
        order.apply_transition("shipped", actor=other)
        resp = auth_api.get(history_url(order.pk))
        assert resp.status_code == 200
        trail = resp.data
        assert [(e["from_status"], e["to_status"], e["actor"]) for e in trail] == [
            ("pending", "paid", "ops1"),
            ("paid", "shipped", "ops2"),
        ]
        assert trail[-1]["created_at"]  # timestamped
        assert trail[0]["order"] == order.pk

    def test_model_level_move_without_actor_serializes_null(self, auth_api, order):
        order.apply_transition("paid", actor=None)  # system/seed move
        resp = auth_api.get(history_url(order.pk))
        assert resp.status_code == 200
        actors = [e["actor"] for e in resp.data]
        assert actors == [None]

    def test_orm_created_order_has_empty_trail(self, auth_api, order):
        resp = auth_api.get(history_url(order.pk))
        assert resp.status_code == 200
        assert resp.data == []

    def test_history_missing_order_is_404(self, auth_api):
        assert auth_api.get(history_url(999999)).status_code == 404


# ---------------------------------------------------------------------------
# creation entry (perform_create)
# ---------------------------------------------------------------------------

class TestCreationEntry:
    def test_api_created_order_gets_initial_history_entry(self, auth_api, order, user):
        payload = {
            "customer": order.customer_id,
            "product": order.product_id,
            "total": "12.34",
        }
        resp = auth_api.post(reverse("order-list"), payload, format="json")
        assert resp.status_code == 201, resp.data
        created = Order.objects.get(pk=resp.data["id"])
        entry = created.history.get()
        assert entry.from_status == ""
        assert entry.to_status == "pending"
        assert entry.actor_id == user.pk

    def test_explicit_status_at_creation_is_recorded(self, auth_api, order):
        resp = auth_api.post(
            reverse("order-list"),
            {"customer": order.customer_id, "product": order.product_id, "status": "paid"},
            format="json",
        )
        assert resp.status_code == 201
        entry = Order.objects.get(pk=resp.data["id"]).history.get()
        assert entry.to_status == "paid"


# ---------------------------------------------------------------------------
# side-effect seam (TODO no-ops — clients implement their own)
# ---------------------------------------------------------------------------

class TestSideEffectSeam:
    def test_seam_runs_inside_transition_with_from_to(self, auth_api, order, user):
        calls = []
        with patch.object(Order, "_apply_side_effects", side_effect=lambda *a: calls.append(a)):
            order.apply_transition("paid", actor=user)
        assert calls == [(order, "pending", "paid")]

    def test_default_stub_is_a_noop(self, db, order):
        stock_before = order.product.stock
        order.apply_transition("paid")
        order.refresh_from_db()
        order.product.refresh_from_db()
        assert order.product.stock == stock_before  # untouched by the stub

    def test_seam_failure_rolls_back_the_whole_transition(self, db, order):
        boom = RuntimeError("client stock policy exploded")
        with patch.object(Order, "_apply_side_effects", side_effect=boom):
            with pytest.raises(RuntimeError):
                order.apply_transition("paid")
        order.refresh_from_db()
        assert order.status == "pending"  # rolled back
        assert order.history.count() == 0  # no history row either


# ---------------------------------------------------------------------------
# OpenAPI contract (the thin client derives everything from the schema)
# ---------------------------------------------------------------------------

class TestSchemaContract:
    def test_lifecycle_endpoints_are_in_the_schema(self, tmp_path):
        out = tmp_path / "schema.json"
        call_command("spectacular", "--format", "openapi-json", file=str(out))
        schema = json.loads(out.read_text())
        paths = schema["paths"]
        trans = paths["/api/orders/{id}/transition/"]
        hist = paths["/api/orders/{id}/history/"]
        assert "post" in trans
        body = trans["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert "$ref" in body  # TransitionRequestSerializer documented
        assert "get" in hist
        hist_ok = hist["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert hist_ok["type"] == "array"  # deliberately NOT paginated
        enum_component = schema["components"]["schemas"]["TransitionEnum"]
        assert enum_component["enum"] == ["pending", "paid", "shipped", "refunded"]  # ordered enum in contract
