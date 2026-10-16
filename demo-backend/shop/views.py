"""ModelViewSets with a naive `?search=` filter (icontains on char/text fields).

The thin client's search box sends `?search=` and ALSO filters the current
page client-side, so this is best-effort on any backend. Pagination shape is
DRF's PageNumberPagination: {count, next, previous, results}.
"""
from django.db.models import Q
from rest_framework import viewsets

from .models import Category, Customer, Order, Product
from .serializers import CategorySerializer, CustomerSerializer, OrderSerializer, ProductSerializer


class SearchableModelViewSet(viewsets.ModelViewSet):
    """Generic: filter across `search_fields` with ?search=<term> (icontains)."""

    search_fields: list[str] = []

    def get_queryset(self):
        qs = super().get_queryset()
        term = (self.request.query_params.get("search") or "").strip()
        if term and self.search_fields:
            qobj = None
            for f in self.search_fields:
                cond = Q(**{f"{f}__icontains": term})
                qobj = cond if qobj is None else qobj | cond
            if qobj is not None:
                qs = qs.filter(qobj)
        return qs


class CategoryViewSet(SearchableModelViewSet):
    queryset = Category.objects.order_by("id")
    serializer_class = CategorySerializer
    search_fields = ["name"]


class ProductViewSet(SearchableModelViewSet):
    queryset = Product.objects.select_related("category").order_by("id")
    serializer_class = ProductSerializer
    search_fields = ["name", "description"]


class CustomerViewSet(SearchableModelViewSet):
    queryset = Customer.objects.order_by("id")
    serializer_class = CustomerSerializer
    search_fields = ["name", "email"]


class OrderViewSet(SearchableModelViewSet):
    queryset = Order.objects.select_related("customer", "product").order_by("-id")
    serializer_class = OrderSerializer
    search_fields = ["notes", "status"]
