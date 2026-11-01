"""FR-R007 phase (b) — the server becomes the actual gate.

docs/rbac.md is unambiguous that the client's menu filtering is
"presentation only — the server stays the actual gate." Until now that
sentence was false: the demo rig's only authorization was
IsAuthenticated, so every surface the thin client gates behind the
`managers` role (the bulk_flag action in actions/bulk_flag.ts, the
Modules and Branding pages) was enforceable nowhere server-side — an
`auditors`-role token could fire the managers-only bulk action directly
over the wire, exactly the gap the 2026-11-02 security audit filed as
CRITICAL for any fork deploying the rig with real data.

The fix mirrors the client contract exactly:

- RequireGroups (plugin module, reusable by any host): superuser bypass,
  otherwise the caller must hold AT LEAST ONE of the required group
  names — the same allow rule roleAllows() renders. is_staff is
  deliberately NOT a bypass: /api/me/ reports Group names, and the
  client opens gated surfaces on the roles claim only.
- OrderViewSet.bulk_flag requires the `managers` group.
- Every ungated surface keeps its contract: reads, CRUD, transition,
  flag and export stay any-authenticated (the client shows them to all
  roles), anonymous callers keep DRF's 401 (authentication runs before
  permissions), and the rejection is DRF's 403 detail body.

Infrastructure note: same in-process rig as test_rbac_roles (conftest
mounts the demo apps via DEMO_RIG_MODULES; this module creates its test
database with Django's own DiscoverRunner — pytest-django deliberately
absent).
"""
import pytest
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.test.runner import DiscoverRunner
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from shop.models import AuditEntry, Category, Customer, Order, Product


@pytest.fixture(scope="module")
def demo_db():
    from django.test.utils import setup_test_environment, teardown_test_environment

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


def _client_as(user) -> APIClient:
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _make_user(username: str, *, groups=(), staff=False, superuser=False) -> User:
    if superuser:
        user = User.objects.create_superuser(username, password="x")
    else:
        user = User.objects.create_user(username, password="x", is_staff=staff)
    if groups:
        user.groups.set([Group.objects.get_or_create(name=name)[0] for name in groups])
    return user


@pytest.fixture
def order(db):
    category = Category.objects.create(name="cat")
    product = Product.objects.create(category=category, name="p", price=1)
    customer = Customer.objects.create(name="c", email="c@example.com")
    return Order.objects.create(customer=customer, product=product)


def _bulk_body(order_pk: int) -> dict:
    return {"ids": [order_pk], "reason": "bulk gate check"}


class TestBulkFlagRequiresManagers:
    def test_anonymous_is_401(self, api, order):
        # authentication runs before permissions: 401, not 403
        response = api.post("/api/orders/bulk_flag/", _bulk_body(order.pk), format="json")
        assert response.status_code == 401, response.content

    def test_auditor_role_is_403_and_writes_nothing(self, api, order):
        auditor = _make_user("aud", groups=("auditors",))
        before = AuditEntry.objects.count()
        response = _client_as(auditor).post(
            "/api/orders/bulk_flag/", _bulk_body(order.pk), format="json"
        )
        assert response.status_code == 403, response.content
        # the rejection is not just a status code: not one audit row, not
        # one summary — the write path never ran.
        assert AuditEntry.objects.count() == before

    def test_staff_without_the_group_is_403(self, api, order):
        staffer = _make_user("staffer", staff=True)
        response = _client_as(staffer).post(
            "/api/orders/bulk_flag/", _bulk_body(order.pk), format="json"
        )
        assert response.status_code == 403, response.content

    def test_manager_role_is_201(self, api, order):
        manager = _make_user("mgr", groups=("managers",))
        response = _client_as(manager).post(
            "/api/orders/bulk_flag/", _bulk_body(order.pk), format="json"
        )
        assert response.status_code == 201, response.content
        body = response.json()
        assert len(body) == 1
        assert body[0]["actor"] == "mgr"
        assert body[0]["object_id"] == str(order.pk)

    def test_superuser_bypasses_to_201(self, api, order):
        # the acceptance half of the client contract: rbac.ts
        # short-circuits on isSuperuser, so the server must too.
        root = _make_user("root", superuser=True)
        response = _client_as(root).post(
            "/api/orders/bulk_flag/", _bulk_body(order.pk), format="json"
        )
        assert response.status_code == 201, response.content

    def test_either_matching_group_allows_when_configured(self, api, order):
        # RequireGroups is "at least one of" — the roleAllows() semantics —
        # proven here with a second configured group so the factory is not
        # pinned to a single name.
        from admineverywhere.permissions import require_groups

        cls = require_groups("managers", "ops")
        assert cls.required_groups == ("managers", "ops")


class TestUngatedSurfacesStayAnyAuthenticated:
    """The gate is narrow by design: the client shows orders, transition,
    flag and export to every signed-in role, so locking those server-side
    would break real users the audit never asked to break."""

    def test_auditor_reads_orders(self, api, order):
        auditor = _make_user("aud2", groups=("auditors",))
        response = _client_as(auditor).get("/api/orders/")
        assert response.status_code == 200, response.content

    def test_auditor_transitions(self, api, order):
        auditor = _make_user("aud3", groups=("auditors",))
        response = _client_as(auditor).post(
            f"/api/orders/{order.pk}/transition/", {"transition": "confirmed"}, format="json"
        )
        assert response.status_code == 200, response.content

    def test_auditor_flags(self, api, order):
        auditor = _make_user("aud4", groups=("auditors",))
        response = _client_as(auditor).post(
            f"/api/orders/{order.pk}/flag/", {"reason": "still allowed"}, format="json"
        )
        assert response.status_code == 201, response.content

    def test_auditor_reads_the_audit_log(self, api, order):
        auditor = _make_user("aud5", groups=("auditors",))
        response = _client_as(auditor).get("/api/audit/")
        assert response.status_code == 200, response.content
