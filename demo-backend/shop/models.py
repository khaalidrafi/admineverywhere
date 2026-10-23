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
        """A FREE enum — no lifecycle machine, no ordering meaning (R-002 §1:
        one nested Choices class per semantic field, never shared across
        models). The class itself carries no empty value; `blank=True` on the
        field below is what adds the real "not decided" state."""

        BOX = "box", "Box"
        CRATE = "crate", "Crate"
        PALLET = "pallet", "Pallet"

    # FR-R002 §2 case C lives here on purpose: a blank=True choices field is
    # emitted as {oneOf: [PackagingEnum, BlankEnum]}, the schema shape that used
    # to degrade the client's select to free text. The rig ships it so the shape
    # stays pinned in the fixture (docs/independent-enums.md §4).
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
        # Declared in lifecycle order — this IS the ordered states enum.
        # STATUS_ORDER and TRANSITIONS below depend on this order.
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        REFUNDED = "refunded", "Refunded"

    # The canonical forward order of the lifecycle (index 0 = entry state).
    # REFUNDED sits last as the absorbing exit, not a forward stage.
    STATUS_ORDER = (Status.PENDING, Status.PAID, Status.SHIPPED, Status.REFUNDED)

    # The whole state machine: current -> frozenset of legal targets.
    # Single source of truth for legality — views, serializers and tests
    # must derive from this, never hand-roll their own rules.
    TRANSITIONS = {
        Status.PENDING: frozenset({Status.PAID}),
        Status.PAID: frozenset({Status.SHIPPED, Status.REFUNDED}),
        Status.SHIPPED: frozenset({Status.REFUNDED}),
        Status.REFUNDED: frozenset(),  # terminal — nothing leaves refunded
    }

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
        """
        if from_status == Order.Status.PENDING and to_status == Order.Status.PAID:
            # TODO(client): reserve stock — e.g. decrement order.product.stock
            # or bump a reserved counter. Implement your own policy.
            pass
        if to_status == Order.Status.REFUNDED:
            # TODO(client): release stock — undo the reservation made when
            # the order was paid. Implement your own policy.
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
