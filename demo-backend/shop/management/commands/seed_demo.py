"""Seed demo data: demo users + shop data with 14 days of order history.

Superuser: admin / admin123 (DEV ONLY — obviously never do this in prod).
Role-holder: auditor / audit123 — non-superuser, Django Group `auditors`
only, so FR-R007 role gating is demonstrable live, not just in tests.
Historical `created_at` values give ActivityChart something to draw.

The trail and the audit log are seeded through the SAME code paths the API
uses (`Order.apply_transition`, `AuditEntry.record_flag`), so a freshly
seeded rig paints the R-001 history sub-view and the R-007 activity screen
with data the server would itself have written — never a shape the machine
would refuse.
"""
import random
from collections import deque
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import AuditEntry, Category, Customer, Order, OrderHistory, Product

CATEGORIES = ["Fresh Produce", "Bakery", "Dairy", "Beverages", "Pantry"]
PRODUCTS = {
    "Fresh Produce": ["Organic Bananas", "Honey Crisp Apples", "Baby Spinach", "Roma Tomatoes", "Avocados"],
    "Bakery": ["Sourdough Loaf", "Croissants (4pk)", "Bagels (6pk)", "Cinnamon Rolls"],
    "Dairy": ["Whole Milk 1L", "Greek Yogurt 500g", "Aged Cheddar 250g", "Farm Butter 200g"],
    "Beverages": ["Cold Brew Coffee 1L", "Green Tea (20 bags)", "Orange Juice 1L", "Sparkling Water 6pk"],
    "Pantry": ["Basmati Rice 2kg", "Olive Oil 500ml", "Wild Honey 350g", "Pasta Penne 500g", "Sea Salt 1kg"],
}
CUSTOMERS = [
    ("Ayesha Khan", "ayesha@example.com"), ("Bilal Ahmed", "bilal@example.com"),
    ("Fatima Noor", "fatima@example.com"), ("Usman Ali", "usman@example.com"),
    ("Zainab Malik", "zainab@example.com"), ("Omar Farooq", "omar@example.com"),
    ("Hafsa Iqbal", "hafsa@example.com"), ("Yusuf Rahman", "yusuf@example.com"),
    ("Maryam Siddiqui", "maryam@example.com"), ("Ibrahim Hussain", "ibrahim@example.com"),
    ("Khadija Yousuf", "khadija@example.com"), ("Adam Sheikh", "adam@example.com"),
]

# Reasons the seeded flag entries carry — the audit screen's `summary` is
# rendered verbatim, so demo text should read like a real triage note.
FLAG_REASONS = [
    "suspected fraud",
    "address unverified",
    "repeat customer — priority restock",
    "stock count off by two",
    "delivery window missed",
    "manual price review",
]
BULK_REASON = "warehouse hold — weekend recount"


def trail_to(target):
    """Every hop from the machine's entry state to ``target``, in order.

    Derived from ``Order.TRANSITIONS`` by breadth-first walk — the seed never
    hand-rolls its own lifecycle rules (docs/order-lifecycle.md: the table is
    the single source of legality). An unreachable target yields an empty
    trail, so the seed degrades to a creation entry rather than inventing a
    hop the API would answer 409 for.
    """
    start = Order.STATUS_ORDER[0]
    if target == start:
        return []
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        current, hops = queue.popleft()
        for nxt in sorted(Order.TRANSITIONS[current]):
            if nxt in seen:
                continue
            path = hops + [nxt]
            if nxt == target:
                return path
            seen.add(nxt)
            queue.append((nxt, path))
    return []


class Command(BaseCommand):
    help = "Seed demo shop data (idempotent: wipes and recreates shop rows)"

    def handle(self, *args, **options):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin123")
            self.stdout.write("superuser admin/admin123 created")

        # FR-R007: the role names /api/me/ reports are Django Group names.
        # Seed them (idempotent) and hold them on admin so a fresh rig
        # demonstrates role claims end to end.
        from django.contrib.auth.models import Group

        groups = {}
        for role in ("auditors", "managers"):
            groups[role] = Group.objects.get_or_create(name=role)[0]
            groups[role].user_set.add(User.objects.get(username="admin"))
        admin = User.objects.get(username="admin")

        # A superuser sees EVERY gated surface by design (rbac.ts:
        # isSuperuser -> allow), so a rig holding only `admin` can never
        # demonstrate a hidden nav entry or button. Seed a second caller
        # that holds exactly one role: `auditor` sees the auditors-gated
        # screens and is denied the managers-only ones, live. DEV ONLY.
        auditor, created = User.objects.get_or_create(
            username="auditor", defaults={"email": "auditor@example.com"}
        )
        if created:
            auditor.set_password("audit123")
            auditor.save()
        auditor.groups.set([groups["auditors"]])
        self.stdout.write(
            "demo logins: admin/admin123 (superuser, auditors+managers — sees "
            "everything) · auditor/audit123 (non-superuser, auditors only — "
            "managers-gated surfaces stay hidden)"
        )

        Order.objects.all().delete()
        Product.objects.all().delete()
        Customer.objects.all().delete()
        Category.objects.all().delete()
        # The audit log names its targets loosely (object_type/object_id, no
        # FK), so rows surviving an order wipe would point at ids that no
        # longer exist — ghosts the activity screen would happily render.
        # Re-seeding repoints the trail, same as the order wipe above.
        AuditEntry.objects.all().delete()

        now = timezone.now()
        cats = {}
        for i, name in enumerate(CATEGORIES):
            cats[name] = Category.objects.create(name=name, created_at=now - timedelta(days=30 - i))

        products = []
        packagings = ["box", "crate", "pallet", ""]  # "" = the real blank state (FR-R002 case C)
        for cat, names in PRODUCTS.items():
            for j, p in enumerate(names):
                products.append(Product.objects.create(
                    category=cats[cat],
                    name=p,
                    description=f"{p} — quality checked daily.",
                    price=Decimal(random.randint(2, 25)) + Decimal("0.99"),
                    stock=random.randint(0, 120),
                    is_active=random.random() > 0.15,
                    launch_date=(now - timedelta(days=random.randint(1, 400))).date(),
                    packaging=random.choice(packagings),
                ))
        # ensure deterministic non-random pk ordering isn't relied on anywhere
        products = list(Product.objects.order_by("id"))

        customers = [
            Customer.objects.create(
                name=n, email=e,
                joined_on=(now - timedelta(days=random.randint(1, 900))).date(),
                is_vip=random.random() > 0.7,
            ) for n, e in CUSTOMERS
        ]

        statuses = ["pending", "paid", "shipped", "refunded"]
        # FR-R005: the rig's FloatField is seeded with the values the two export
        # layers used to disagree on — integral floats (Python str() -> "1.0",
        # the browser -> "1"), an exponent switch point ("1e-07" vs "1e-7"), a
        # long-form switch ("1e+17" vs "100000000000000000000"), a negative
        # sub-unit float (the formula-guard trap) and a NULL. So anyone who
        # exports the seeded collection with either button can diff real bytes.
        weights = [2.0, 0.5, 1e-7, 1e17, -0.00042, 100.0, 48.5, None]
        seeded_orders = []
        for i in range(60):
            status = random.choice(statuses)
            order = Order.objects.create(
                customer=random.choice(customers),
                product=random.choice(products),
                status=Order.Status.PENDING,
                total=Decimal(random.randint(5, 90)) + Decimal("0.50"),
                weight=weights[i % len(weights)],
                notes="" if i % 3 else "Leave at front door.",
                created_at=now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23)),
            )
            # FR-R001: every seeded order gets the trail the machine itself
            # would have written — the creation entry (from_status="", the
            # shape perform_create appends) and then each legal hop to the
            # status the row ends on. A hand-written `"" -> "refunded"` row is
            # a move apply_transition() refuses with 409, so the old one-row
            # seed showed a history the API could never have produced.
            # Refunds are performed by `auditor`, the seeded non-superuser, so
            # a live trail names a role-holder as its actor too (FR-R007-LIVE).
            OrderHistory.objects.create(
                order=order, from_status="", to_status=order.status, actor=None
            )
            for target in trail_to(status):
                actor = auditor if target == Order.Status.REFUNDED else admin
                order.apply_transition(target, actor=actor)
            seeded_orders.append(order)

        # FR-R003 / FR-R007: the audit log the activity screen reads. A freshly
        # seeded rig used to answer `count: 0` here, so #/activity and every
        # record's audit half painted empty until someone fired a flag by hand.
        # Same writer as the @action (AuditEntry.record_flag), so the seeded
        # rows are byte-for-byte the shape a live click produces.
        for k, order in enumerate(seeded_orders[: len(FLAG_REASONS)]):
            AuditEntry.record_flag(
                order.pk, actor=admin, reason=FLAG_REASONS[k]
            )
        bulk_ids = [
            order.pk for order in seeded_orders[len(FLAG_REASONS): len(FLAG_REASONS) + 3]
        ]
        for pk in bulk_ids:
            AuditEntry.record_flag(
                pk, actor=auditor, reason=BULK_REASON, bulk=True, batch=len(bulk_ids)
            )

        self.stdout.write(self.style.SUCCESS(
            f"seeded: {len(cats)} categories, {len(products)} products, "
            f"{len(customers)} customers, 60 orders (last 14 days), "
            f"{OrderHistory.objects.count()} history rows, "
            f"{AuditEntry.objects.count()} audit entries"
        ))
