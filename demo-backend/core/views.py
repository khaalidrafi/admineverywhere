"""Non-model API surface for the demo rig.

FR-R007 phase (a) — the role claims source. The thin client can only
filter its menu/actions if the SERVER says who the caller is: Django
Groups are the role names, emitted sorted so two runs answer the same
document. Clients discover this path in the OpenAPI schema (GET, no
POST) and bind filtering ONLY when it exists — a plain DRF backend
without it simply never gets filtered (same graceful-degradation law
as runtime branding and the schema-gated CSV export).

Deliberately a read-only view: never PATCH/PUT roles from the client.
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import BooleanField, CharField, ListField, Serializer
from rest_framework.views import APIView


class MeResponseSerializer(Serializer):
    username = CharField()
    is_staff = BooleanField()
    is_superuser = BooleanField()
    roles = ListField(child=CharField())


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeResponseSerializer  # documented only; no body to validate

    @extend_schema(
        responses=(MeResponseSerializer,),
        description=(
            "Role claims of the authenticated caller (FR-R007). 'roles' are the "
            "Django Group names, sorted. Read-only: the client filters its menu "
            "and actions from these, the server stays the actual gate."
        ),
    )
    def get(self, request):
        user = request.user
        return Response(
            {
                "username": user.username,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "roles": sorted(user.groups.values_list("name", flat=True)),
            }
        )
