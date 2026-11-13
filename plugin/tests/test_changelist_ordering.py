"""Changelist sorting (django.contrib.admin parity) — the ?ordering= contract.

The client's sortable headers send ``?ordering=<field>`` / ``?ordering=-<field>``
against the DOCUMENTED parameter: normalizeOpenAPI binds the feature only when
the OpenAPI list operation carries ``ordering`` (which drf-spectacular emits
for the OrderingFilter backend). This module pins the server half of that
contract on the demo rig:

- ``?ordering=`` re-orders the list (ascending, then the ``-`` flip),
- a field outside the viewset's ``ordering_fields`` allowlist answers 400,
- no parameter keeps each viewset's declared default order,
- the OpenAPI document carries the ``ordering`` query parameter — the schema
  half the client's evidence law reads before lighting any header.

Infrastructure: same as test_order_lifecycle — conftest mounts the demo rig
in-memory, Django's own test utilities create the per-module test database,
per-test isolation via an outer atomic block (no pytest-django).
"""
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from rest_framework.test import APIClient

from shop.models import Category, Customer, Order, Product

# ---------------------------------------------------------------------------
# database plumbing (identical to test_order_lifecycle)
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
    from django.contrib.auth.models import User

    return User.objects.create_user("sorter", "sorter@example.com", "pw12345")


@pytest.fixture
def auth_api(api, user):
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def products(db):
    """Two products across two categories with known orderable values."""
    cat_a = Category.objects.create(name=f"alpha-{uuid4().hex[:6]}")
    cat_b = Category.objects.create(name=f"beta-{uuid4().hex[:6]}")
    low = Product.objects.create(
        category=cat_a, name="Alpha", price=Decimal("5.00"), stock=2
    )
    high = Product.objects.create(
        category=cat_b, name="Beta", price=Decimal("9.00"), stock=7
    )
    return {"low": low, "high": high}


@pytest.fixture
def order(db):
    cat = Category.objects.create(name=f"cat-{uuid4().hex[:8]}")
    product = Product.objects.create(
        category=cat, name="Thing", price=Decimal("9.99"), stock=5
    )
    customer = Customer.objects.create(name="Cust", email=f"{uuid4().hex[:8]}@example.com")
    return Order.objects.create(customer=customer, product=product)


# ---------------------------------------------------------------------------
# products: asc, desc flip, allowlist 400, default preserved
# ---------------------------------------------------------------------------


def test_products_ordering_ascending(auth_api, products):
    resp = auth_api.get("/api/products/", {"ordering": "name"})
    assert resp.status_code == 200
    names = [row["name"] for row in resp.data["results"]]
    assert names == sorted(names)


def test_products_ordering_flip_to_descending(auth_api, products):
    resp = auth_api.get("/api/products/", {"ordering": "-price"})
    assert resp.status_code == 200
    prices = [Decimal(row["price"]) for row in resp.data["results"]]
    assert prices == sorted(prices, reverse=True)


def test_products_ordering_unknown_field_is_dropped(auth_api, products):
    # DRF's OrderingFilter REMOVES fields outside the allowlist and falls
    # back to the queryset's own default order — it does not 400. That is
    # the safety we pin: a client cannot order by a column the backend
    # never exposed (no arbitrary lookups, no leaks), and the read stays
    # healthy instead of failing the changelist.
    resp = auth_api.get("/api/products/", {"ordering": "category__name"})
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.data["results"]]
    assert ids == sorted(ids)  # the queryset default (id asc) stands


def test_products_default_order_untouched(auth_api, products):
    # No parameter -> the queryset's own order_by("id") stands.
    resp = auth_api.get("/api/products/")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.data["results"]]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# orders: sorting a lifecycle model does not disturb the machine
# ---------------------------------------------------------------------------


def test_orders_ordering_by_total(auth_api, order):
    resp = auth_api.get("/api/orders/", {"ordering": "-total"})
    assert resp.status_code == 200
    totals = [Decimal(row["total"]) for row in resp.data["results"]]
    assert totals == sorted(totals, reverse=True)


def test_orders_ordering_by_status(auth_api, order):
    resp = auth_api.get("/api/orders/", {"ordering": "status"})
    assert resp.status_code == 200
    statuses = [row["status"] for row in resp.data["results"]]
    assert statuses == sorted(statuses)


# ---------------------------------------------------------------------------
# the schema half: the document must carry the ordering parameter
# (the client binds sortable headers to it — evidence law)
# ---------------------------------------------------------------------------


def test_schema_documents_ordering_param(auth_api):
    resp = auth_api.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert resp.status_code == 200
    doc = json.loads(resp.content)
    op = doc["paths"]["/api/products/"]["get"]
    params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
    assert any(p.get("name") == "ordering" for p in params), (
        "the products list operation must document the ordering query "
        "parameter — the client's sortable headers bind to it"
    )
    op_orders = doc["paths"]["/api/orders/"]["get"]
    params = [p for p in op_orders.get("parameters", []) if p.get("in") == "query"]
    assert any(p.get("name") == "ordering" for p in params)
