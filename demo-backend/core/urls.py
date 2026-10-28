from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from rest_framework.authtoken.views import obtain_auth_token

from .views import MeView

urlpatterns = [
    # Auth: POST {username, password} -> {"token": "..."} (DRF authtoken)
    path("api/auth/token/", obtain_auth_token),
    # FR-R007 role claims source: GET -> {username, is_staff, is_superuser, roles}
    # (read-only; the client discovers this path in the OpenAPI schema)
    path("api/me/", MeView.as_view(), name="me"),
    # OpenAPI schema served by drf-spectacular (public so the thin client
    # can introspect; protected per-model endpoints sit behind token auth)
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[]), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/", include("shop.urls")),
    # Runtime branding: GET/PUT /admineverywhere/branding/ (+ asset serving) —
    # lets the thin client rebrand itself from inside the app.
    path("admineverywhere/", include("admineverywhere.urls")),
]
