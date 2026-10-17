from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    # Auth: POST {username, password} -> {"token": "..."} (DRF authtoken)
    path("api/auth/token/", obtain_auth_token),
    # OpenAPI schema served by drf-spectacular (public so the thin client
    # can introspect; protected per-model endpoints sit behind token auth)
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[]), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/", include("shop.urls")),
    # Runtime branding: GET/PUT /admincraft/branding/ (+ asset serving) —
    # lets the thin client rebrand itself from inside the app.
    path("admincraft/", include("admincraft.urls")),
]
