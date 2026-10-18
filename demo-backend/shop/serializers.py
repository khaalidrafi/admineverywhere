from rest_framework import serializers

from .models import AuditEntry, Category, Customer, Order, OrderHistory, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ("created_at",)


class TransitionRequestSerializer(serializers.Serializer):
    """Body for POST /api/orders/<id>/transition/ — the target state.

    Kept as an explicit serializer so the OpenAPI contract documents the
    request body (the thin client derives everything from the schema).
    """

    transition = serializers.ChoiceField(
        choices=Order.Status.choices,
        help_text="Target lifecycle state (must be legal from the current state).",
    )


class FlagRequestSerializer(serializers.Serializer):
    """Body for POST /api/orders/<id>/flag/ (FR-R003 reference action).

    Kept as an explicit serializer so the OpenAPI contract documents the
    request body (the thin client derives everything from the schema).
    """

    reason = serializers.CharField(
        max_length=255,
        help_text="Why the order is flagged; surfaced verbatim in the audit summary.",
    )


class BulkFlagRequestSerializer(FlagRequestSerializer):
    """Body for POST /api/orders/bulk_flag/ — many orders, one reason."""

    ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="Order primary keys to flag (duplicates collapse to one entry each).",
    )


class AuditEntrySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField(
        help_text="Username of the acting user; null for system/seed entries."
    )

    class Meta:
        model = AuditEntry
        fields = ("id", "action", "object_type", "object_id", "actor", "summary", "data", "created_at")
        read_only_fields = ("actor", "created_at")

    def get_actor(self, obj) -> str | None:
        return obj.actor.username if obj.actor_id else None


class OrderHistorySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField(
        help_text="Username of the user that performed the move; null for system/seed moves."
    )

    class Meta:
        model = OrderHistory
        fields = ("id", "order", "from_status", "to_status", "actor", "created_at")

    def get_actor(self, obj) -> str | None:
        return obj.actor.username if obj.actor_id else None
