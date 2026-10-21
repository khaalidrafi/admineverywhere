"""Seed demo data: demo users + shop data with 14 days of order history.

Superuser: admin / admin123 (DEV ONLY — obviously never do this in prod).
Role-holder: auditor / audit123 — non-superuser, Django Group `auditors`
only, so FR-R007 role gating is demonstrable live, not just in tests.
Historical `created_at` values give ActivityChart something to draw.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import Category, Customer, Order, OrderHistory, Product

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

        now = timezone.now()
        cats = {}
        for i, name in enumerate(CATEGORIES):
            cats[name] = Category.objects.create(name=name, created_at=now - timedelta(days=30 - i))

        products = []
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
        for i in range(60):
            status = random.choice(statuses)
            order = Order.objects.create(
                customer=random.choice(customers),
                product=random.choice(products),
                status=status,
                total=Decimal(random.randint(5, 90)) + Decimal("0.50"),
                weight=weights[i % len(weights)],
                notes="" if i % 3 else "Leave at front door.",
                created_at=now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23)),
            )
            # FR-R001: seeded orders get their creation history entry too
            # (actor=None — system move), so GET /api/orders/<id>/history/
            # never 404s into an empty trail for demo data.
            OrderHistory.objects.create(
                order=order, from_status="", to_status=status, actor=None
            )

        self.stdout.write(self.style.SUCCESS(
            f"seeded: {len(cats)} categories, {len(products)} products, "
            f"{len(customers)} customers, 60 orders (last 14 days)"
        ))
