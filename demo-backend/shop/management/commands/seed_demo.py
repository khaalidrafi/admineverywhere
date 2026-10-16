"""Seed demo data: superuser + shop data with 14 days of order history.

Superuser: admin / admin123 (DEV ONLY — obviously never do this in prod).
Historical `created_at` values give ActivityChart something to draw.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import Category, Customer, Order, Product

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
        for i in range(60):
            Order.objects.create(
                customer=random.choice(customers),
                product=random.choice(products),
                status=random.choice(statuses),
                total=Decimal(random.randint(5, 90)) + Decimal("0.50"),
                notes="" if i % 3 else "Leave at front door.",
                created_at=now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23)),
            )

        self.stdout.write(self.style.SUCCESS(
            f"seeded: {len(cats)} categories, {len(products)} products, "
            f"{len(customers)} customers, 60 orders (last 14 days)"
        ))
