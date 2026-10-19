from rest_framework.routers import DefaultRouter

from .views import (
    AuditEntryViewSet,
    CategoryViewSet,
    CustomerViewSet,
    OrderViewSet,
    ProductViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("customers", CustomerViewSet, basename="customer")
router.register("orders", OrderViewSet, basename="order")
router.register("audit", AuditEntryViewSet, basename="audit")

urlpatterns = router.urls
