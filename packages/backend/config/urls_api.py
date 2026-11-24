from django.contrib import admin
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from drf_yasg.generators import OpenAPISchemaGenerator
from rest_framework import permissions
from django.conf import settings

from common.graphql.views import DRFAuthenticatedGraphQLView
from apps.sigmarail_bridge.lean_runtime_api import (
    LeanRuntimeMetaView,
    LeanRuntimeSourceFieldsView,
    LeanRuntimeSourcesView,
    LeanRuntimeUniverseRunView,
)

api_info = openapi.Info(title="Documentation", default_version="v1")


class HttpAndHttpsSchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.schemes = ["http", "https"]
        return schema


schema_view = get_schema_view(
    api_info,
    public=True,
    generator_class=HttpAndHttpsSchemaGenerator,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Worker-only compatibility surface used inside the Compose network.
    path("v1/meta", LeanRuntimeMetaView.as_view(), name="lean-runtime-meta"),
    path("v1/schema/sources", LeanRuntimeSourcesView.as_view(), name="lean-runtime-sources"),
    path("v1/schema/sources/<str:source>/fields", LeanRuntimeSourceFieldsView.as_view(), name="lean-runtime-source-fields"),
    path("v1/universe/run", LeanRuntimeUniverseRunView.as_view(), name="lean-runtime-universe-run"),
    # Django Admin - accessible via path for deployments without subdomain support
    path("admin/", admin.site.urls),
    re_path(r"^swagger(?P<format>\.json|\.yaml)$", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    re_path(r"^doc/", schema_view.with_ui("swagger")),
    re_path(r"^redoc/", schema_view.with_ui("redoc")),
    path(
        "api/",
        include(
            [
                path("graphql/", DRFAuthenticatedGraphQLView.as_view(graphiql=settings.DEBUG)),
                path("content/", include("apps.content.urls")),
                path("demo/", include("apps.demo.urls")),
                path("finances/", include("apps.finances.urls")),
                path("sso/", include("apps.sso.urls")),
                path("translations/", include("apps.translations.urls")),
                path("ai-assistant/", include("apps.integrations.ai_assistant.urls")),
                path("", include("apps.users.urls")),
                path("", include("apps.sigmarail_bridge.urls")),
            ]
        ),
    ),
]
