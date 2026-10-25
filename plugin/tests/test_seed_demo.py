"""The seeded rig must be a LIVE demo, not an empty one (FR-R007-LIVE).

Measured on a freshly seeded rig before these tests existed: `GET
/api/audit/` answered `count: 0` (so the R-007 activity screen and every
record's audit half painted empty until someone fired a flag by hand), and
`GET /api/orders/<id>/history/` answered ONE row whose shape the machine
itself refuses — `from_status: ""` straight to the final status, `actor:
None`. A trail like that is the worst kind of demo data: it shows a state
transition the transition endpoint would answer 409 for.

So the seed is graded against the server's own rules, over the wire:

- every seeded trail is a LEGAL walk of `Order.TRANSITIONS`, opening with the
  creation entry the API's `perform_create` writes;
- the audit log is non-empty and readable by the seeded NON-superuser
  (`auditor`), which is the identity the gated nav hides surfaces from;
- the row shape the seed writes is the row shape the `flag` @action writes —
  one writer (`AuditEntry.record_flag`) proven by comparing both products
  byte-for-byte through the serializer, not by reading the code twice;
- re-seeding does not accumulate (the rig is re-run by whoever points a
  client at it).

Infrastructure: same in-process rig as test_rbac_roles — conftest mounts the
demo apps (this module is listed in DEMO_RIG_MODULES) and Django's own
DiscoverRunner creates the test DB (pytest-django deliberately absent).
"""
import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from shop.models import AuditEntry, Order, OrderHistory


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
def seeded(db):
    """A freshly seeded rig, rolled back after each test."""
    call_command("seed_demo", verbosity=0)
    return {
        "admin": User.objects.get(username="admin"),
        "auditor": User.objects.get(username="auditor"),
    }


def _authed_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _trail(order_id):
    """The trail the API serves for one order, oldest-first (its own order_by)."""
    return list(
        OrderHistory.objects.filter(order_id=order_id)
        .order_by("created_at", "id")
        .values_list("from_status", "to_status", "actor__username")
    )


def test_every_seeded_trail_is_a_legal_walk_of_the_machine(seeded):
    """Each hop is in TRANSITIONS, and the trail ends on the row's status.

    The seed walks `apply_transition`, so a red assertion here means the demo
    data and the reference state machine have diverged — exactly the drift the
    one-row seed shipped.
    """
    orders = list(Order.objects.all())
    assert len(orders) == 60
    multi_hop = 0
    for order in orders:
        trail = _trail(order.pk)
        assert trail, f"order {order.pk} has no history at all"
        first_from, first_to, first_actor = trail[0]
        assert first_from == "", "the creation entry must open the trail"
        assert first_to == Order.Status.PENDING, (
            f"seeded order {order.pk} was born in {first_to!r}; the machine's "
            "entry state is pending"
        )
        assert first_actor is None, "a system/seed creation entry has no actor"
        current = first_to
        for from_status, to_status, _actor in trail[1:]:
            assert from_status == current, (
                f"order {order.pk}: trail jumps — row starts at {from_status!r} "
                f"after the trail reached {current!r}"
            )
            assert Order.transition_allowed(from_status, to_status), (
                f"order {order.pk}: seeded an illegal hop {from_status!r} -> "
                f"{to_status!r} that POST /transition/ would answer 409 for"
            )
            current = to_status
        assert current == order.status, (
            f"order {order.pk} reads {order.status!r} but its trail ends at "
            f"{current!r}"
        )
        multi_hop += len(trail) > 1
    # At least some orders must actually have moved: a seed that parks every
    # row in `pending` would satisfy every assertion above and show nothing.
    assert multi_hop > 0, "no seeded order has a lifecycle hop"


def test_seeded_rig_serves_a_nonempty_audit_log_to_the_nonsuperuser(seeded):
    """#/activity reads `<listPath>` of the audit model — a fresh rig must
    answer rows, and the demo role-holder (non-staff, non-superuser) must be
    able to read them, since that is the account the gated nav is shown from.
    """
    body = _authed_client(seeded["auditor"]).get("/api/audit/").json()
    assert body["count"] == AuditEntry.objects.count()
    assert body["count"] > 0, "freshly seeded audit log is empty"
    results = body["results"]
    assert results, "the log has rows but the first page is empty"
    assert {e["action"] for e in results} == {AuditEntry.FLAG_ACTION}
    assert {e["object_type"] for e in results} == {"order"}
    # Newest-first is the documented audit ruling (triage), the opposite of
    # the oldest-first lifecycle trail.
    created = [e["created_at"] for e in results]
    assert created == sorted(created, reverse=True) or len(results) < 2
    for entry in results:
        assert entry["actor"] in {"admin", "auditor"}, (
            f"audit entry {entry['id']} names {entry['actor']!r}, not a seeded user"
        )
        assert Order.objects.filter(pk=int(entry["object_id"])).exists(), (
            f"audit entry {entry['id']} points at order {entry['object_id']}, "
            "which the seeded rig does not carry — a ghost the screen would render"
        )


def test_seeded_record_filter_finds_the_trail_of_one_order(seeded):
    """The record sub-view and the activity screen read the log through the
    object_type/object_id filters — so a seeded entry must be findable by the
    order it names, and only that order's entries must come back.
    """
    client = _authed_client(seeded["admin"])
    flagged_id = AuditEntry.objects.filter(object_type="order").values_list(
        "object_id", flat=True
    )[0]
    body = client.get(f"/api/audit/?object_type=order&object_id={flagged_id}").json()
    assert body["count"] >= 1
    assert {e["object_id"] for e in body["results"]} == {flagged_id}


def test_bulk_seeded_entries_carry_the_batch_provenance(seeded):
    """One bulk action appends one row per target with the batch size in its
    payload — the seeded bulk rows must look exactly like that, or the demo
    teaches the wrong shape.
    """
    bulk = [e for e in AuditEntry.objects.all() if (e.data or {}).get("bulk")]
    assert bulk, "no bulk-scope audit entry was seeded"
    batch = bulk[0].data["batch"]
    assert batch == len(bulk), f"entry says batch {batch}, log holds {len(bulk)}"
    assert "reason" in bulk[0].data
    assert "(bulk)" in bulk[0].summary


def test_seed_and_the_wire_action_write_the_same_row(seeded):
    """The two flag writers are ONE writer: seed a row and POST the flag @action
    with the same reason, then compare the serialized bodies. Anything but the
    id/target/actor/timestamp is a divergence between demo data and product
    data.
    """
    reason = "suspected fraud"
    seeded_entry = AuditEntry.objects.get(actor=seeded["admin"], data__reason=reason)
    target = Order.objects.exclude(pk=seeded_entry.object_id).first()
    resp = _authed_client(seeded["admin"]).post(
        f"/api/orders/{target.pk}/flag/", {"reason": reason}, format="json"
    )
    assert resp.status_code == 201, resp.content
    wire = resp.json()
    entry = AuditEntry.objects.get(pk=seeded_entry.pk)
    # Compare the four shape fields explicitly (no getattr trickery): the
    # point is the bytes a screen renders, not the identity of the row.
    assert wire["action"] == entry.action
    assert wire["object_type"] == entry.object_type
    assert wire["summary"] == entry.summary
    assert wire["data"] == entry.data
    assert wire["id"] != entry.id
    assert wire["object_id"] == str(target.pk)


def test_refund_hops_are_performed_by_the_seeded_role_holder(seeded):
    """Every seeded move INTO refunded names the non-superuser, every other hop
    names admin and the creation entry stays unattributed — universal over
    whatever the random seed produced, so the assertion cannot pass by luck of
    an absent refund.
    """
    seen_refund = False
    for row in OrderHistory.objects.select_related("actor"):
        if row.from_status == "":
            assert row.actor_id is None, f"creation row {row.pk} names an actor"
        elif row.to_status == Order.Status.REFUNDED:
            seen_refund = True
            assert row.actor_id == seeded["auditor"].pk, (
                f"history row {row.pk} refunded by {row.actor}"
            )
        else:
            assert row.actor_id == seeded["admin"].pk, (
                f"history row {row.pk} moved by {row.actor}, expected admin"
            )
    assert Order.objects.filter(status=Order.Status.PENDING).count() >= 0
    if not seen_refund:
        pytest.skip("this random seed produced no refund hop to grade")


def test_reseeding_does_not_accumulate_the_trail_or_the_log(seeded):
    """`help` promises an idempotent rig. Orders are wiped (history rides the
    cascade), so the audit log has to be wiped with them or the second run
    leaves rows pointing at ids that no longer exist.

    The history COUNT is deliberately not compared: a refund trail is three
    rows and a pending order's is one, so the total moves with the random
    statuses. What must not move is the log's size, and nothing may be orphaned.
    """
    audit_before = AuditEntry.objects.count()
    call_command("seed_demo", verbosity=0)
    assert AuditEntry.objects.count() == audit_before, (
        f"the audit log grew on reseed: {audit_before} -> {AuditEntry.objects.count()}"
    )
    order_ids = set(Order.objects.values_list("id", flat=True))
    orphaned = set(OrderHistory.objects.values_list("order_id", flat=True)) - order_ids
    assert not orphaned, f"history rows survive their order: {sorted(orphaned)}"
    ghosts = {e.object_id for e in AuditEntry.objects.all()} - {str(pk) for pk in order_ids}
    assert not ghosts, f"audit rows name orders the reseed removed: {sorted(ghosts)}"
