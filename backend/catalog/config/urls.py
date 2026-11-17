from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import LivenessView, ReadinessView
from apps.users.views import JWKSView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(".well-known/jwks.json", JWKSView.as_view(), name="jwks"),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.listings.urls")),
    path("api/v1/", include("apps.reviews.urls")),
    path("api/v1/", include("apps.support.urls")),
    path("api/v1/", include("apps.favorites.urls")),
    path("api/schema/catalog/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/catalog/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("healthz", LivenessView.as_view(), name="healthz"),
    path("readyz", ReadinessView.as_view(), name="readyz"),
    # /metrics, scraped by Prometheus inside the Docker network; the gateway refuses it.
    path("", include("django_prometheus.urls")),
]
