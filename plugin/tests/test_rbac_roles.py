"""FR-R007 phase (a) — the server must EMIT role claims.

Reference contract (docs/rbac.md): a plain authenticated GET on the API
answers with the caller's identity + role names, so the thin client can
filter its menu and actions without ever guessing a permission model:

    GET /api/me/ -> {"username", "is_staff", "is_superuser", "roles": [...]}

- roles are Django Group names of the authenticated user (sorted);
- anonymous callers get 401 — the endpoint is auth'd like the rest;
- the OpenAPI document advertises the path, which is how the client
  discovers it (schema-driven law: paths come from the document, never
  from string concatenation);
- a backend WITHOUT the endpoint keeps working: the client sees no
  claims and applies NO filtering (graceful degradation, branding law).

Infrastructure note: same in-process rig as test_audit_actions —
conftest mounts the demo apps, this module creates the test DB with
Django's own DiscoverRunner (pytest-django deliberately absent).
"""
import json

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


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


def _authed_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def test_anonymous_me_is_401(api):
    r = api.get("/api/me/")
    assert r.status_code == 401, r.content


def test_me_returns_username_and_flags(api):
    user = User.objects.create_user("rolex", password="x")
    r = _authed_client(user).get("/api/me/")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["username"] == "rolex"
    assert body["is_staff"] is False
    assert body["is_superuser"] is False
    assert body["roles"] == []


def test_me_roles_are_group_names_sorted(api):
    user = User.objects.create_user("multi", password="x", is_staff=True)
    user.groups.set([Group.objects.create(name="auditors"), Group.objects.create(name="managers")])
    body = _authed_client(user).get("/api/me/").json()
    assert body["roles"] == ["auditors", "managers"]
    assert body["is_staff"] is True


def test_superuser_reports_superuser(api):
    user = User.objects.create_superuser("root", password="x")
    body = _authed_client(user).get("/api/me/").json()
    assert body["is_superuser"] is True


def test_seed_demo_gives_a_nonsuperuser_single_role_holder(api):
    """The rig must be able to demonstrate the REJECTION path live.

    A superuser sees every gated surface by design, so `admin` alone can
    never show a hidden button: seed_demo also creates `auditor`, a plain
    non-staff/non-superuser user holding exactly one Group. That body is
    what makes rbac.ts's `roleAllows(["managers"], claims) === false`
    clickable in a browser.
    """
    call_command("seed_demo", verbosity=0)
    auditor = User.objects.get(username="auditor")
    assert auditor.is_superuser is False and auditor.is_staff is False
    body = _authed_client(auditor).get("/api/me/").json()
    assert body == {
        "username": "auditor",
        "is_staff": False,
        "is_superuser": False,
        "roles": ["auditors"],
    }
    # the seeded superuser keeps both groups: the acceptance case, live too.
    admin_body = _authed_client(User.objects.get(username="admin")).get("/api/me/").json()
    assert admin_body["is_superuser"] is True
    assert admin_body["roles"] == ["auditors", "managers"]


def test_seed_demo_gives_a_nonsuperuser_managers_holder(api):
    """The rig must demonstrate the ACCEPTANCE path without the superuser bypass.

    Every gated surface in the reference app requires `managers`
    (Modules.svelte, Branding.svelte, actions/bulk_flag.ts), and
    `roleAllows()` short-circuits to allow for a superuser — so with only
    `admin` + `auditor` seeded there is NO login where the gate opens
    because the caller actually holds the role: admin opens everything by
    bypass, auditor sees everything hidden. `manager` is the missing half:
    a plain non-staff/non-superuser holding exactly `managers`.
    """
    call_command("seed_demo", verbosity=0)
    manager = User.objects.get(username="manager")
    assert manager.is_superuser is False and manager.is_staff is False
    body = _authed_client(manager).get("/api/me/").json()
    assert body == {
        "username": "manager",
        "is_staff": False,
        "is_superuser": False,
        "roles": ["managers"],
    }


def test_seed_demo_covers_both_gate_directions_without_a_superuser(api):
    """Population pin: one non-superuser per direction of the gate.

    A rig that silently drops either user goes back to proving one half
    only, and nothing else in the suite can see that (the unit tests build
    their own users). So: exactly one seeded non-superuser whose roles do
    NOT satisfy a `managers` gate, and one whose roles DO — never the
    superuser standing in for the second.
    """
    call_command("seed_demo", verbosity=0)
    plain = list(
        User.objects.filter(is_superuser=False).values_list("username", flat=True)
    )
    assert set(plain) >= {"auditor", "manager"}, plain
    denied = _authed_client(User.objects.get(username="auditor")).get("/api/me/").json()
    allowed = _authed_client(User.objects.get(username="manager")).get("/api/me/").json()
    assert "managers" not in denied["roles"], denied
    assert "managers" in allowed["roles"], allowed
    assert allowed["is_superuser"] is False and denied["is_superuser"] is False


def test_seed_demo_role_assignment_is_idempotent(api):
    """Rerunning the seed must not drift the claims (rigs get re-seeded)."""
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)
    auditor = User.objects.get(username="auditor")
    assert list(auditor.groups.values_list("name", flat=True)) == ["auditors"]
    body = _authed_client(auditor).get("/api/me/").json()
    assert body["roles"] == ["auditors"]
    assert body["is_superuser"] is False
    manager = User.objects.get(username="manager")
    assert list(manager.groups.values_list("name", flat=True)) == ["managers"]


def test_schema_advertises_me_path(tmp_path):
    """The client binds the button from the document — generation must not
    crash on the new view and the path must carry a GET."""
    out = tmp_path / "schema.json"
    call_command("spectacular", "--format", "openapi-json", file=str(out))
    schema = json.loads(out.read_text())
    me = [p for p in schema["paths"] if p.rstrip("/").endswith("/me")]
    assert me, "no /me path in the schema"
    assert "get" in schema["paths"][me[0]]
    assert "post" not in schema["paths"][me[0]]
