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

The machine under test is the BYTE-SACRED 11-state COD machine, mirrored
verbatim from the production Freshorama backend (shop/models.py): pending
-> confirmed -> processing -> ready_to_ship -> shipped -> in_transit ->
delivered, with the delivery_failed / returned / on_hold / cancelled
recovery fan-out. Every legal edge is pinned EXPLICITLY below (29 of
them) — deriving them from Order.TRANSITIONS here would make the test
unable to catch a broken table. The cancel law gets its own endpoint
test: cancel is reachable from every state EXCEPT delivered (a completed
sale is not cancelled; its money is refunded on the payment axis).

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

# Declared lifecycle order — the contract. Keep in lockstep with
# Order.Status and the fixture's TransitionEnum (test_schema_drift grades
# the fixture half; this tuple is the hand-written witness).
STATES = (
    "pending", "confirmed", "processing", "ready_to_ship", "shipped",
    "in_transit", "delivered", "delivery_failed", "returned", "on_hold",
    "cancelled",
)

# Every legal edge of the machine, pinned explicitly (29 of them).
LEGAL_MOVES = [
    ("pending", "confirmed"), ("pending", "on_hold"), ("pending", "cancelled"),
    ("confirmed", "processing"), ("confirmed", "ready_to_ship"),
    ("confirmed", "on_hold"), ("confirmed", "cancelled"),
    ("processing", "ready_to_ship"), ("processing", "on_hold"),
    ("processing", "cancelled"),
    ("ready_to_ship", "shipped"), ("ready_to_ship", "on_hold"),
    ("ready_to_ship", "cancelled"),
    ("shipped", "in_transit"), ("shipped", "delivered"),
    ("shipped", "delivery_failed"), ("shipped", "on_hold"),
    ("shipped", "cancelled"),
    ("in_transit", "delivered"), ("in_transit", "delivery_failed"),
    ("in_transit", "on_hold"), ("in_transit", "cancelled"),
    ("delivery_failed", "shipped"), ("delivery_failed", "returned"),
    ("delivery_failed", "cancelled"),
    ("delivered", "returned"),
    ("on_hold", "confirmed"), ("on_hold", "processing"),
    ("on_hold", "cancelled"),
]

# A machine-illegal pair for EVERY state (both terminals included) —
# the guard must refuse cross-jumps, shortcuts, backwards moves and any
# exit from a terminal state. Pinned explicitly, never derived.
ILLEGAL_MOVES = [
    ("pending", "processing"), ("pending", "ready_to_ship"),
    ("pending", "shipped"), ("pending", "delivered"),
    ("pending", "in_transit"), ("pending", "delivery_failed"),
    ("pending", "returned"),
    ("confirmed", "shipped"), ("confirmed", "delivered"),
    ("confirmed", "in_transit"), ("confirmed", "returned"),
    ("processing", "shipped"), ("processing", "delivered"),
    ("processing", "in_transit"),
    ("ready_to_ship", "delivered"), ("ready_to_ship", "in_transit"),
    ("ready_to_ship", "returned"),
    ("shipped", "confirmed"), ("shipped", "processing"),
    ("shipped", "returned"),
    ("in_transit", "shipped"), ("in_transit", "returned"),
    ("delivery_failed", "delivered"), ("delivery_failed", "in_transit"),
    ("delivery_failed", "on_hold"),
    ("delivered", "shipped"), ("delivered", "pending"),
    ("delivered", "cancelled"),
    ("returned", "pending"), ("returned", "shipped"),
    ("returned", "delivered"), ("returned", "on_hold"),
    ("cancelled", "pending"), ("cancelled", "confirmed"),
    ("cancelled", "shipped"), ("cancelled", "on_hold"),
    ("on_hold", "shipped"), ("on_hold", "delivered"),
    ("on_hold", "returned"),
]

# The legal forward walk from the entry state to each lifecycle state,
# used to DRIVE an order to a state in endpoint tests (the legality
# assertions themselves stay explicit in LEGAL_MOVES/ILLEGAL_MOVES).
WALKS = {
    "pending": [],
    "confirmed": ["confirmed"],
    "on_hold": ["on_hold"],
    "processing": ["confirmed", "processing"],
    "ready_to_ship": ["confirmed", "processing", "ready_to_ship"],
    "shipped": ["confirmed", "processing", "ready_to_ship", "shipped"],
    "in_transit": ["confirmed", "processing", "ready_to_ship", "shipped", "in_transit"],
    "delivery_failed": ["confirmed", "processing", "ready_to_ship", "shipped", "delivery_failed"],
    "delivered": ["confirmed", "processing", "ready_to_ship", "shipped", "in_transit", "delivered"],
}

# Cancel law: reachable from every state EXCEPT delivered (a completed
# sale is not cancelled — its money is refunded on the payment axis).
# returned/cancelled are terminal and have no exits at all.
CANCEL_LEGAL_STATES = (
    "pending", "confirmed", "processing", "ready_to_ship", "shipped",
    "in_transit", "delivery_failed", "on_hold",
)


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


def walk_to(order, state):
    """Drive the order from the entry state to `state` via legal moves."""
    for target in WALKS[state]:
        order.apply_transition(target)
    order.refresh_from_db()
    assert order.status == state


# ---------------------------------------------------------------------------
# the machine itself (pure — no DB)
# ---------------------------------------------------------------------------

class TestStateMachine:
    def test_enum_is_declared_in_lifecycle_order(self):
        assert tuple(Order.Status.values) == STATES

    def test_status_order_pins_the_lifecycle(self):
        assert tuple(Order.STATUS_ORDER) == tuple(Order.Status.values)
        assert Order.STATUS_ORDER[0] == Order.Status.PENDING  # entry state

    def test_both_terminal_states_have_no_exits(self):
        assert Order.TRANSITIONS[Order.Status.RETURNED] == frozenset()
        assert Order.TRANSITIONS[Order.Status.CANCELLED] == frozenset()

    def test_delivered_exits_only_into_returned(self):
        assert Order.TRANSITIONS[Order.Status.DELIVERED] == frozenset(
            {Order.Status.RETURNED}
        )

    @pytest.mark.parametrize(("current", "target"), LEGAL_MOVES)
    def test_legal_moves(self, current, target):
        assert Order.transition_allowed(current, target) is True

    @pytest.mark.parametrize(("current", "target"), ILLEGAL_MOVES)
    def test_illegal_moves(self, current, target):
        assert Order.transition_allowed(current, target) is False

    def test_the_matrix_is_total_over_declared_states(self):
        """Every declared state appears as a key — no orphan state the map
        silently answers `never allowed` for (the frozenset default would
        hide a typo forever)."""
        assert set(Order.TRANSITIONS) == set(Order.Status.values)

    def test_unknown_current_or_target_is_never_allowed(self):
        assert Order.transition_allowed("teleported", "confirmed") is False
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
        resp = auth_api.post(transition_url(order.pk), {"transition": "confirmed"}, format="json")
        assert resp.status_code == 200
        assert resp.data["status"] == "confirmed"
        order.refresh_from_db()
        assert order.status == "confirmed"
        entry = order.history.get()
        assert entry.from_status == "pending"
        assert entry.to_status == "confirmed"
        assert entry.actor_id == user.pk
        assert entry.created_at is not None

    def test_full_forward_lifecycle_to_delivered_then_returned(
        self, auth_api, order
    ):
        walk = WALKS["delivered"] + ["returned"]
        for target in walk:
            resp = auth_api.post(transition_url(order.pk), {"transition": target}, format="json")
            assert resp.status_code == 200, resp.data
        trail = list(OrderHistory.objects.filter(order=order).order_by("created_at", "id"))
        # ORM-created fixture order: no creation entry — that row belongs to
        # the API path and is pinned by TestCreationEntry.
        assert [(e.from_status, e.to_status) for e in trail] == [
            ("pending", "confirmed"),
            ("confirmed", "processing"),
            ("processing", "ready_to_ship"),
            ("ready_to_ship", "shipped"),
            ("shipped", "in_transit"),
            ("in_transit", "delivered"),
            ("delivered", "returned"),
        ]

    def test_the_delivery_failed_recovery_path_is_legal_over_the_wire(
        self, auth_api, order
    ):
        """shipped -> delivery_failed -> shipped (re-ship) must work: the
        guard refuses shortcuts, never recovery."""
        for target in ("confirmed", "processing", "ready_to_ship", "shipped"):
            assert auth_api.post(
                transition_url(order.pk), {"transition": target}, format="json"
            ).status_code == 200
        assert auth_api.post(
            transition_url(order.pk), {"transition": "delivery_failed"}, format="json"
        ).status_code == 200
        resp = auth_api.post(transition_url(order.pk), {"transition": "shipped"}, format="json")
        assert resp.status_code == 200
        assert resp.data["status"] == "shipped"

    def test_delivered_to_returned_is_the_only_delivered_exit(self, auth_api, order):
        walk_to(order, "delivered")
        resp = auth_api.post(transition_url(order.pk), {"transition": "returned"}, format="json")
        assert resp.status_code == 200
        assert resp.data["status"] == "returned"

    @pytest.mark.parametrize("state", CANCEL_LEGAL_STATES)
    def test_cancel_is_reachable_from_every_state_but_delivered(
        self, auth_api, order, state
    ):
        walk_to(order, state)
        resp = auth_api.post(transition_url(order.pk), {"transition": "cancelled"}, format="json")
        assert resp.status_code == 200, (state, resp.data)
        order.refresh_from_db()
        assert order.status == "cancelled"

    def test_cancel_from_delivered_is_409(self, auth_api, order):
        walk_to(order, "delivered")
        resp = auth_api.post(transition_url(order.pk), {"transition": "cancelled"}, format="json")
        assert resp.status_code == 409
        assert "pending" in resp.data["reason"] or "delivered" in resp.data["reason"]

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

    def test_returned_is_terminal(self, auth_api, order):
        walk_to(order, "delivered")
        order.apply_transition("returned")
        resp = auth_api.post(transition_url(order.pk), {"transition": "delivered"}, format="json")
        assert resp.status_code == 409
        assert "terminal" in resp.data["reason"]

    def test_cancelled_is_terminal(self, auth_api, order):
        order.apply_transition("cancelled")
        resp = auth_api.post(transition_url(order.pk), {"transition": "pending"}, format="json")
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
        assert ", ".join(STATES) in resp.data["reason"]

    def test_missing_transition_field_is_400_with_reason(self, auth_api, order):
        resp = auth_api.post(transition_url(order.pk), {}, format="json")
        assert resp.status_code == 400
        assert "missing required field 'transition'" in resp.data["reason"]

    def test_transition_missing_order_is_404(self, auth_api):
        resp = auth_api.post(transition_url(999999), {"transition": "confirmed"}, format="json")
        assert resp.status_code == 404

    def test_unauthenticated_transition_is_rejected(self, api, order):
        resp = api.post(transition_url(order.pk), {"transition": "confirmed"}, format="json")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/orders/<id>/history/
# ---------------------------------------------------------------------------

class TestHistoryEndpoint:
    def test_trail_is_oldest_first_with_actor(self, auth_api, order, user):
        other = User.objects.create_user("ops2", "ops2@example.com", "pw12345")
        order.apply_transition("confirmed", actor=user)
        order.apply_transition("processing", actor=other)
        resp = auth_api.get(history_url(order.pk))
        assert resp.status_code == 200
        trail = resp.data
        assert [(e["from_status"], e["to_status"], e["actor"]) for e in trail] == [
            ("pending", "confirmed", "ops1"),
            ("confirmed", "processing", "ops2"),
        ]
        assert trail[-1]["created_at"]  # timestamped
        assert trail[0]["order"] == order.pk

    def test_model_level_move_without_actor_serializes_null(self, auth_api, order):
        order.apply_transition("confirmed", actor=None)  # system/seed move
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
            {"customer": order.customer_id, "product": order.product_id, "status": "confirmed"},
            format="json",
        )
        assert resp.status_code == 201
        entry = Order.objects.get(pk=resp.data["id"]).history.get()
        assert entry.to_status == "confirmed"


# ---------------------------------------------------------------------------
# side-effect seam (TODO no-ops — clients implement their own)
# ---------------------------------------------------------------------------

class TestSideEffectSeam:
    def test_seam_runs_inside_transition_with_from_to(self, auth_api, order, user):
        calls = []
        with patch.object(Order, "_apply_side_effects", side_effect=lambda *a: calls.append(a)):
            order.apply_transition("confirmed", actor=user)
        assert calls == [(order, "pending", "confirmed")]

    def test_default_stub_is_a_noop(self, db, order):
        stock_before = order.product.stock
        order.apply_transition("confirmed")
        order.refresh_from_db()
        order.product.refresh_from_db()
        assert order.product.stock == stock_before  # untouched by the stub

    def test_seam_failure_rolls_back_the_whole_transition(self, db, order):
        boom = RuntimeError("client stock policy exploded")
        with patch.object(Order, "_apply_side_effects", side_effect=boom):
            with pytest.raises(RuntimeError):
                order.apply_transition("confirmed")
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
        assert enum_component["enum"] == list(STATES)  # ordered enum in contract
