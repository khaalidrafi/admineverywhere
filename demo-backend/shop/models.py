"""Shop models — one field of every type the admin form must render.

Products exercise: char (required), text (optional), decimal, integer,
boolean, date, FK. Orders add: enum (choices), datetime (auto/read-only),
float (FR-R005's witness — see ``weight`` below).

FR-R001 (ROADLOG R-001): Order carries the reference lifecycle state
machine — an ordered Status enum, an explicit transition table, and an
append-only OrderHistory trail. Client projects copy this pattern; see
docs/order-lifecycle.md for the convention and the API contract.

FR-R003 (ROADLOG R-003): AuditEntry is the append-only custom-actions
audit log — one loose-coupled table any model's actions write into;
see docs/custom-actions.md for the convention and the API contract.
"""
from django.conf import settings
from django.db import models, transaction


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(default=None, blank=True, null=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    class Packaging(models.TextChoices):
        """Free enum (no lifecycle machine): the choices themselves exclude the
        empty value; ``blank=True`` below adds the real "not decided" state."""

        BOX = "box", "Box"
        CRATE = "crate", "Crate"
        PALLET = "pallet", "Pallet"

    # FR-R002 §2 case C — the shape a blank=True choices field emits
    # ({oneOf: [PackagingEnum, BlankEnum]}). The thin client must resolve it to
    # a select, not degrade it to free text.
    PACKAGING_CHOICES = [("", "Not decided")] + Packaging.choices

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    launch_date = models.DateField(null=True, blank=True)
    packaging = models.CharField(
        max_length=20,
        choices=PACKAGING_CHOICES,
        blank=True,
        default="",
        help_text="Free enum that allows the empty state (FR-R002 case C).",
    )

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    joined_on = models.DateField(null=True, blank=True)
    is_vip = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class IllegalTransition(Exception):
    """Raised when a lifecycle move is not in Order.TRANSITIONS.

    ``reason`` is a stable, human-readable string — the API surfaces it
    verbatim as the 409 body (see OrderViewSet.transition).
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Order(models.Model):
    class Status(models.TextChoices):
        # The BYTE-SACRED 11-state COD machine, mirrored VERBATIM from the
        # production backend (Freshorama shop/models.py) — same states, same
        # user-facing labels, same edges. Declared in lifecycle order; this IS
        # the ordered states enum. STATUS_ORDER and TRANSITIONS below depend
        # on this order. The money axis (paid/refunded) is a production
        # Payment-row concern and deliberately has NO status here.
        PENDING = "pending", "Waiting for our call"
        CONFIRMED = "confirmed", "Confirmed by phone"
        PROCESSING = "processing", "Being packed"
        READY_TO_SHIP = "ready_to_ship", "Ready to ship"
        SHIPPED = "shipped", "Out for delivery"
        IN_TRANSIT = "in_transit", "In transit"
        DELIVERED = "delivered", "Delivered"
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"
        RETURNED = "returned", "Returned to shop"
        ON_HOLD = "on_hold", "On hold"
        CANCELLED = "cancelled", "Cancelled"

    # The canonical forward order of the lifecycle (index 0 = entry state).
    # `returned` and `cancelled` sit last as the terminal exits, not stages.
    STATUS_ORDER = (
        Status.PENDING, Status.CONFIRMED, Status.PROCESSING, Status.READY_TO_SHIP,
        Status.SHIPPED, Status.IN_TRANSIT, Status.DELIVERED, Status.DELIVERY_FAILED,
        Status.RETURNED, Status.ON_HOLD, Status.CANCELLED,
    )

    # The whole state machine: current -> frozenset of legal targets.
    # Single source of truth for legality — views, serializers and tests
    # must derive from this, never hand-roll their own rules.
    # Laws (production admin-panel spec, mirrored verbatim):
    #   - cancel is reachable from every state EXCEPT delivered (a completed
    #     sale is not cancelled; its money is refunded on the payment axis);
    #   - delivered is terminal except the refund flow: delivered -> returned
    #     (goods come back; production restores stock and refunds Payment rows);
    #   - `returned` and `cancelled` are terminal.
    TRANSITIONS = {
        Status.PENDING: frozenset({Status.CONFIRMED, Status.ON_HOLD, Status.CANCELLED}),
        Status.CONFIRMED: frozenset({Status.PROCESSING, Status.READY_TO_SHIP, Status.ON_HOLD, Status.CANCELLED}),
        Status.PROCESSING: frozenset({Status.READY_TO_SHIP, Status.ON_HOLD, Status.CANCELLED}),
        Status.READY_TO_SHIP: frozenset({Status.SHIPPED, Status.ON_HOLD, Status.CANCELLED}),
        Status.SHIPPED: frozenset({Status.IN_TRANSIT, Status.DELIVERED, Status.DELIVERY_FAILED, Status.ON_HOLD, Status.CANCELLED}),
        Status.IN_TRANSIT: frozenset({Status.DELIVERED, Status.DELIVERY_FAILED, Status.ON_HOLD, Status.CANCELLED}),
        Status.DELIVERY_FAILED: frozenset({Status.SHIPPED, Status.RETURNED, Status.CANCELLED}),
        Status.RETURNED: frozenset(),  # terminal — nothing leaves returned
        Status.DELIVERED: frozenset({Status.RETURNED}),
        Status.ON_HOLD: frozenset({Status.CONFIRMED, Status.PROCESSING, Status.CANCELLED}),
        Status.CANCELLED: frozenset(),  # terminal — nothing leaves cancelled
    }

    # Production stock law (docs/order-lifecycle.md §3), mirrored as constants:
    # stock is a movement log, not a hand-edited counter — confirm = no change;
    # shipped = deduct; delivery_failed / returned / cancelled-after-ship =
    # restore. The reference seam below stays a deliberate no-op (clients
    # implement their own policy against these constants).
    STOCK_DEDUCT_STATUS = (Status.SHIPPED,)
    STOCK_RESTORE_STATUS = (Status.DELIVERY_FAILED, Status.RETURNED, Status.CANCELLED)

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # The rig's only FloatField, and it is here on purpose (FR-R005): a float is
    # the one value type the two CSV layers can disagree about WITHOUT either
    # side looking broken, because JSONRenderer emits it as a JSON NUMBER (a
    # DecimalField emits a STRING), so layer 1 exports String()-ed digits and
    # layer 2 exports whatever Python formatted. Proven over the wire by
    # TestFloatOverTheWire, byte-for-byte against the shared FLOAT_PARITY table.
    weight = models.FloatField(
        null=True,
        blank=True,
        help_text="Shipping weight in kg. Arrives over JSON as a number "
        "(FloatField, not DecimalField) — both CSV layers must render it alike.",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=None, blank=True, null=True)

    def __str__(self):
        return f"Order #{self.pk} ({self.get_status_display()})"

    # ------------------------------------------------------------------
    # FR-R001 lifecycle machine (reference implementation — clients copy
    # this pattern, docs/order-lifecycle.md).
    # ------------------------------------------------------------------
    @classmethod
    def transition_allowed(cls, current: str, target: str) -> bool:
        """True iff ``current -> target`` is a legal lifecycle move."""
        if current not in cls.TRANSITIONS or target not in cls.Status.values:
            return False
        return target in cls.TRANSITIONS[current]

    def apply_transition(self, target_status: str, actor=None):
        """Move the order to ``target_status`` atomically and record history.

        Raises IllegalTransition (with a ``reason`` string) for unknown
        targets, no-op moves and machine-illegal moves. Side effects run
        inside the same transaction via _apply_side_effects; the history
        row is written here, never by callers.
        Returns the created OrderHistory entry.
        """
        current = self.status
        if target_status not in self.Status.values:
            raise IllegalTransition(f"unknown status '{target_status}'")
        if target_status == current:
            raise IllegalTransition(
                f"order is already '{current}'; no-op transitions are rejected"
            )
        if not self.transition_allowed(current, target_status):
            allowed = ", ".join(sorted(self.TRANSITIONS[current])) or "none (terminal)"
            raise IllegalTransition(
                f"illegal transition: '{current}' -> '{target_status}' (allowed from '{current}': {allowed})"
            )
        with transaction.atomic():
            self._apply_side_effects(self, current, target_status)
            self.status = target_status
            self.save(update_fields=["status"])
            return OrderHistory.objects.create(
                order=self,
                from_status=current,
                to_status=target_status,
                actor=actor,
            )

    @staticmethod
    def _apply_side_effects(order, from_status: str, to_status: str) -> None:
        """Side-effect seam — runs inside the transition transaction.

        This reference implementation ships the stubs as deliberate
        no-ops: every client project implements its own stock policy.
        Replace the bodies, keep the seam and the (from, to) signature.
        The production policy these stubs mirror (see the STOCK_* constants
        above): shipped deducts one `sale` movement per item;
        delivery_failed / returned / cancelled restore one `return`
        movement per item, once per order (the movement log makes the
        effect idempotent).
        """
        if to_status in Order.STOCK_DEDUCT_STATUS:
            # TODO(client): deduct stock — one negative sale movement per
            # order item. Implement your own policy.
            pass
        if to_status in Order.STOCK_RESTORE_STATUS:
            # TODO(client): restore stock — undo the deduction made when
            # the order shipped. Implement your own policy.
            pass


class OrderHistory(models.Model):
    """Append-only lifecycle audit trail for an Order (FR-R001).

    One row per transition; the creation entry has from_status="".
    Rows are never edited or deleted by the API. ``actor`` is the user
    that performed the move (null for system/seed moves).
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(
        max_length=20, choices=Order.Status.choices, blank=True, default=""
    )
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_history",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "order history"

    def __str__(self):
        return f"Order #{self.order_id}: {self.from_status or 'created'} -> {self.to_status}"


class AuditEntry(models.Model):
    """Append-only audit log for custom actions (FR-R003 / ROADLOG R-003).

    One row per performed custom action — record scope (one target) or
    bulk scope (one row per target). Rows are created only through the
    audit API or server-side action code; the API surface exposes
    list + create and nothing else, so PUT/PATCH/DELETE answer 405 by
    construction and the log can only grow. ``actor`` is always derived
    from the authenticated request — never client-supplied (null for
    system/seed entries). ``object_type``/``object_id`` name the target
    loosely (no FK) so any model's actions audit into this one table;
    the record sub-view and the R-007 activity-log screen read it back
    through the object_type/object_id filters.

    Ordering ruling (the R-003 "audit ordering" risk, decided here once):
    audit reads NEWEST-first — triage wants the latest event on top.
    Lifecycle history (OrderHistory) stays oldest-first: replay vs triage.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(
        max_length=100, help_text="Slug of the performed action, e.g. 'order.flag'."
    )
    object_type = models.CharField(
        max_length=120,
        help_text="Loose target type, e.g. 'order' — no FK, any model audits here.",
    )
    object_id = models.CharField(
        max_length=64, help_text="Primary key of the target, as a string."
    )
    summary = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable one-liner surfaced in audit screens.",
    )
    data = models.JSONField(
        null=True,
        blank=True,
        help_text="Structured payload (reason, bulk provenance, diff — action-defined).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "audit entries"
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def __str__(self):
        return f"{self.action} on {self.object_type}#{self.object_id}"

    # ONE WRITER for the reference action's row shape. The `flag` / `bulk_flag`
    # @actions and `manage.py seed_demo` both call this, so a seeded trail and a
    # live click cannot drift apart on summary wording or payload keys — the
    # divergence the export twins are guarded against, closed at the write side.
    FLAG_ACTION = "order.flag"

    # FR-R007 phase b — the direct POST /api/audit/ append surface is
    # allowlisted: action slug -> the object_type it may audit. Until this
    # gate any authenticated caller could plant arbitrary history ("invoice.
    # sent" on nonexistent invoice #7) in the triage screen — the
    # forged-content half of the 2026-11-02 security audit finding. The
    # mapping is the extension point: a downstream host adds its own pairs
    # and the serializer validation follows at request time. Server-side
    # writers (record_flag, seed_demo) create rows through the model and are
    # NOT subject to this allowlist — it guards the HTTP append surface only.
    CREATE_ALLOWLIST = {FLAG_ACTION: "order"}

    @classmethod
    def record_flag(cls, order_id, actor=None, reason="", bulk=False, batch=None):
        """Append one ``order.flag`` audit entry and return it.

        ``bulk`` mirrors the bulk-scope action's payload (provenance: the
        batch size), never a separate action slug — one entry per target.
        ``actor`` is whatever the caller derived server-side (the
        authenticated request user for the API, the named demo user for the
        seed); it is never taken from the request body.
        """
        if bulk:
            return cls.objects.create(
                actor=actor,
                action=cls.FLAG_ACTION,
                object_type="order",
                object_id=str(order_id),
                summary=f"Order flagged (bulk): {reason}",
                data={"reason": reason, "bulk": True, "batch": batch},
            )
        return cls.objects.create(
            actor=actor,
            action=cls.FLAG_ACTION,
            object_type="order",
            object_id=str(order_id),
            summary=f"Order flagged: {reason}",
            data={"reason": reason},
        )
