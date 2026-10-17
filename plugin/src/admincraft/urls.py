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
    path("branding/asset/<str:name>", views.brand_asset, name="brand-asset"),
]
