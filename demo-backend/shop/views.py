"""ModelViewSets with a naive `?search=` filter (icontains on char/text fields).

The thin client's search box sends `?search=` and ALSO filters the current
page client-side, so this is best-effort on any backend. Pagination shape is
DRF's PageNumberPagination: {count, next, previous, results}.

FR-R001: OrderViewSet adds the lifecycle contract — POST transition
(guard errors are 409 + {reason}), GET history (append-only trail), and
an initial history entry written on create. IllegalTransition from the
model is the only guard error path; never hand-roll state rules here.
"""
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets

from .models import Category, Customer, IllegalTransition, Order, OrderHistory, Product
from .serializers import (
    CategorySerializer,
    CustomerSerializer,
    OrderHistorySerializer,
    OrderSerializer,
    ProductSerializer,
    TransitionRequestSerializer,
)


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

    def perform_create(self, serializer):
        """Write the creation entry into the history trail (from_status="")."""
        order = serializer.save()
        actor = self.request.user if self.request.user.is_authenticated else None
        OrderHistory.objects.create(
            order=order, from_status="", to_status=order.status, actor=actor
        )

    @extend_schema(
        request=TransitionRequestSerializer,
        responses=OrderSerializer,
        description="Move the order through its lifecycle. Body: {transition: <target state>}. "
        "Illegal moves answer 409 with {reason}; unknown targets answer 400 with {reason}.",
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        order = self.get_object()
        target = request.data.get("transition")
        if not target:
            return Response(
                {"reason": "missing required field 'transition' (body: {\"transition\": <target state>})"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if target not in Order.Status.values:
            return Response(
                {"reason": f"unknown status '{target}' (valid: {', '.join(Order.Status.values)})"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order.apply_transition(target, actor=request.user if request.user.is_authenticated else None)
        except IllegalTransition as exc:
            return Response({"reason": exc.reason}, status=status.HTTP_409_CONFLICT)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)

    @extend_schema(
        responses=OrderHistorySerializer(many=True),
        description="Append-only, timestamped lifecycle trail, oldest first. "
        "The creation entry has from_status=\"\"; actor is null for system/seed moves. "
        "Deliberately NOT paginated — clients always get the full trail.",
    )
    # pagination_class=None: the trail must be a plain array both at runtime
    # and in the schema (the default PageNumberPagination would otherwise
    # make drf-spectacular document a paginated wrapper the endpoint
    # never actually emits).
    @action(detail=True, methods=["get"], pagination_class=None)
    def history(self, request, pk=None):
        order = self.get_object()
        entries = order.history.select_related("actor").order_by("created_at", "id")
        return Response(OrderHistorySerializer(entries, many=True).data)
