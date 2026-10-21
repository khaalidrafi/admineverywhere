"""Runtime branding endpoints.

Mount in the host project::

    urlpatterns = [
        ...
        path("admincraft/", include("admincraft.urls")),
    ]
"""
from django.urls import path

from . import views

app_name = "admincraft"

urlpatterns = [
    path("branding/", views.branding, name="branding"),
    # <path:name>, not <str:name>: every shipped brand.json (app/brands/*)
    # stores "assets/logo.svg" — build_admin flattens it into public/, so the
    # runtime route must address subdirectories too or the served logo URL
    # 404s at the router. The jail in brandstore/views keeps it inside the
    # brand dir; see docs and views.brand_asset.
    path("branding/asset/<path:name>", views.brand_asset, name="brand-asset"),
]
