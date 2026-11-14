"""URL configuration for Screening Studio."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from api.views import HealthView
from api.lean_universe import LeanMetaView, LeanSourceFieldsView, LeanSourcesView, LeanUniverseRunView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", HealthView.as_view(), name="health"),
    path("v1/meta", LeanMetaView.as_view(), name="lean-meta"),
    path("v1/schema/sources", LeanSourcesView.as_view(), name="lean-schema-sources"),
    path("v1/schema/sources/<str:source>/fields", LeanSourceFieldsView.as_view(), name="lean-source-fields"),
    path("v1/universe/run", LeanUniverseRunView.as_view(), name="lean-universe-run"),
    path("api/", include("api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
