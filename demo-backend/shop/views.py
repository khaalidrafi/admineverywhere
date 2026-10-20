"""ModelViewSets with a naive `?search=` filter (icontains on char/text fields).

The thin client's search box sends `?search=` and ALSO filters the current
page client-side, so this is best-effort on any backend. Pagination shape is
DRF's PageNumberPagination: {count, next, previous, results}.

FR-R001: OrderViewSet adds the lifecycle contract — POST transition
(guard errors are 409 + {reason}), GET history (append-only trail), and
an initial history entry written on create. IllegalTransition from the
model is the only guard error path; never hand-roll state rules here.

FR-R003: OrderViewSet adds the custom-actions reference — record-scope
flag and bulk-scope bulk_flag, both appending to the audit log — and
AuditEntryViewSet serves the append-only audit endpoint: list + create
only (PUT/PATCH/DELETE 405 by construction), newest first, actor always
derived from the request. See docs/custom-actions.md.

FR-R005: OrderViewSet gains the line-level export reference — GET
/api/orders/export/ streams the WHOLE collection (search honoured,
pagination off) as one row per parent/child pair with the parent ids
repeated, in a stable order. The thin client's own Export button covers
visible columns of the current page client-side; a flattened join is the
part only the server can do. See docs/csv-export.md.
"""
from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin
from rest_framework.renderers import BaseRenderer, BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response

from .models import (
    AuditEntry,
    Category,
    Customer,
    IllegalTransition,
    Order,
    OrderHistory,
    Product,
)
from .csv_export import ORDER_EXPORT_HEADER, csv_text, order_export_rows
from .serializers import (
    AuditEntrySerializer,
    BulkFlagRequestSerializer,
    CategorySerializer,
    CustomerSerializer,
    FlagRequestSerializer,
    OrderHistorySerializer,
    OrderSerializer,
    ProductSerializer,
    TransitionRequestSerializer,
)


def _request_actor(request):
    """The authenticated request user, or None for anonymous callers."""
    return request.user if request.user.is_authenticated else None


class CSVTextRenderer(BaseRenderer):
    """Makes ``Accept: text/csv`` negotiable, which is the whole job.

    DRF performs content negotiation in ``initialize_request()`` — BEFORE the
    view body runs — so an action that answers a plain ``HttpResponse`` still
    406s when no renderer class matches the request header. The thin client asks
    for ``text/csv`` (the shape the OpenAPI document promises), and the shipped
    default pair (JSON + browsable API) does not satisfy it: measured as a hard
    406 against the live rig, while every APIClient test stayed green because
    APIClient sends ``Accept: */*``.

    Nothing is ever rendered through this class — ``render()`` exists to satisfy
    the interface. Keep it next to the JSON/browsable pair rather than replacing
    them: dropping ``BrowsableAPIRenderer`` would 406 a browser address-bar
    download, and dropping ``JSONRenderer`` would break OPTIONS/Meta.
    """

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode(self.charset)
        return b""


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

    # ------------------------------------------------------------------
    # FR-R003 custom actions reference (docs/custom-actions.md): one
    # record-scope and one bulk-scope action, both audit-wired. Guard
    # errors keep the R-001 shape: 400 + {"reason": "..."}.
    # ------------------------------------------------------------------
    @extend_schema(
        request=FlagRequestSerializer,
        responses=AuditEntrySerializer,
        description="Record-scope custom action (FR-R003 reference): flag this order for review. "
        "Changes no order fields; appends one append-only audit entry (actor = requesting user).",
    )
    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        order = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"reason": "missing required field 'reason' (body: {\"reason\": <text>})"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entry = AuditEntry.objects.create(
            actor=_request_actor(request),
            action="order.flag",
            object_type="order",
            object_id=str(order.pk),
            summary=f"Order flagged: {reason}",
            data={"reason": reason},
        )
        return Response(AuditEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=BulkFlagRequestSerializer,
        responses=AuditEntrySerializer(many=True),
        description="Bulk-scope custom action (FR-R003 reference): flag many orders with one reason. "
        "Appends one audit entry per order; unknown ids answer 400 with {reason} listing them. "
        "Duplicate ids collapse to one entry per order.",
    )
    @action(detail=False, methods=["post"])
    def bulk_flag(self, request, pk=None):
        ids = request.data.get("ids")
        reason = (request.data.get("reason") or "").strip()
        if not isinstance(ids, list) or not ids:
            return Response(
                {"reason": "missing or empty required field 'ids' (body: {\"ids\": [<order id>, ...], \"reason\": <text>})"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not reason:
            return Response(
                {"reason": "missing required field 'reason' (body: {\"ids\": [<order id>, ...], \"reason\": <text>})"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            wanted = {int(value) for value in ids}
        except (TypeError, ValueError):
            return Response(
                {"reason": "field 'ids' must be a list of order ids"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        found = Order.objects.filter(pk__in=wanted).order_by("pk")
        missing = sorted(wanted - {order.pk for order in found})
        if missing:
            return Response(
                {"reason": f"unknown order id(s): {', '.join(str(m) for m in missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = [
            AuditEntry.objects.create(
                actor=_request_actor(request),
                action="order.flag",
                object_type="order",
                object_id=str(flagged.pk),
                summary=f"Order flagged (bulk): {reason}",
                data={"reason": reason, "bulk": True, "batch": len(wanted)},
            )
            for flagged in found
        ]
        return Response(AuditEntrySerializer(entries, many=True).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
        description="Line-level CSV export (FR-R005 reference): the WHOLE order collection "
        "in primary-key order, one row per order/history pair with the parent ids repeated. "
        "Honours ?search=, ignores pagination (a page of an export is not an export). "
        "Answers text/csv with an attachment disposition and a UTF-8 BOM.",
    )
    # pagination_class=None for the same reason history is: the default
    # PageNumberPagination would document a paginated wrapper this endpoint
    # never emits — a CSV body has no page shape at all.
    @action(
        detail=False,
        methods=["get"],
        pagination_class=None,
        # text/csv has to be negotiable or the client's own Accept header 406s
        # before this body ever runs (see CSVTextRenderer).
        renderer_classes=[JSONRenderer, BrowsableAPIRenderer, CSVTextRenderer],
    )
    def export(self, request):
        orders = (
            self.get_queryset()
            .select_related("customer", "product")
            .prefetch_related("history__actor")
            .order_by("id")
        )
        rows = [ORDER_EXPORT_HEADER, *order_export_rows(orders)]
        # utf-8-sig: Excel on Windows reads a BOM-less file as the local
        # codepage and mangles every non-ASCII name.
        body = csv_text(rows).encode("utf-8-sig")
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="orders-line.csv"'
        return response


class AuditEntryViewSet(ListModelMixin, CreateModelMixin, viewsets.GenericViewSet):
    """Append-only audit log (FR-R003): GET list + POST append, nothing else.

    No update/delete mixins exist, so PUT/PATCH/DELETE answer 405 by
    construction — the log can only grow. Entries read newest-first
    (triage order — the R-003 ordering ruling; R-001's history replays
    oldest-first). Optional ``?object_type=`` / ``?object_id=`` filters
    back the record sub-view and the R-007 activity-log screen. POST
    never trusts the client with ``actor``: perform_create derives it
    from the authenticated request.
    """

    queryset = AuditEntry.objects.select_related("actor")
    serializer_class = AuditEntrySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        object_type = self.request.query_params.get("object_type")
        object_id = self.request.query_params.get("object_id")
        if object_type:
            qs = qs.filter(object_type=object_type)
        if object_id:
            qs = qs.filter(object_id=object_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(actor=_request_actor(self.request))
