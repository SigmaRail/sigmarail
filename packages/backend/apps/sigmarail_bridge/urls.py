from django.urls import path, re_path

from .core_data import (
    AsOfDateRangeView,
    CoreDatasetView,
    CoreDatasetsView,
    CoreQueryView,
    LatestTradingDateView,
    MarketContextView,
    ScreenSparklinesView,
    UniverseCompileSqlView,
    UniversePreviewView,
    UniverseSectorRangeView,
    UniverseSchemaView,
)
from .strategy_catalog import (
    StrategyPipelineCompileView,
    StrategyPipelineDecompileView,
    StrategyPipelineValidateView,
    StrategyPortfolioCompileView,
    StrategyPortfolioDecompileView,
    StrategyFactorsView,
    StrategyPositionFieldsView,
    StrategyPresetView,
    StrategyPresetsView,
)
from .template_catalog import CatalogTemplateDetailView, CatalogTemplatesView
from .screen_templates import UniverseScreenTemplateView, UniverseScreenTemplatesView
from .strategy_framework_templates import (
    WorkspaceStrategyFrameworkTemplateDetailView,
    WorkspaceStrategyFrameworkTemplatesView,
)
from .views import (
    DomainAPIRouteView,
    RuntimeIdentityView,
    WorkspaceSavedScreenDetailView,
    WorkspaceSavedScreensView,
    WorkspaceStrategySpecDetailView,
    WorkspaceStrategySpecsView,
)


urlpatterns = []

urlpatterns.extend(
    [
        path("runtime/identity", RuntimeIdentityView.as_view(), name="runtime-identity"),
        path("data/datasets", CoreDatasetsView.as_view(), name="core-datasets"),
        path("data/datasets/<path:dataset_id>", CoreDatasetView.as_view(), name="core-dataset"),
        path("data/query", CoreQueryView.as_view(), name="core-query"),
        path("screens/latest-trading-date", LatestTradingDateView.as_view(), name="screen-latest-trading-date"),
        path("screens/as-of-range", AsOfDateRangeView.as_view(), name="screen-as-of-range"),
        path("screens/market-context", MarketContextView.as_view(), name="screen-market-context"),
        path("screens/sparklines", ScreenSparklinesView.as_view(), name="screen-sparklines"),
        path("screens/compile-sql", UniverseCompileSqlView.as_view(), name="screen-compile-sql"),
        path("screens/preview-ir", UniversePreviewView.as_view(), name="screen-preview-ir"),
        path("screens/universe-sector-range", UniverseSectorRangeView.as_view(), name="screen-universe-sector-range"),
        path("screens/ir-schema", UniverseSchemaView.as_view(), name="screen-ir-schema"),
        re_path(r"^screens/templates/?$", UniverseScreenTemplatesView.as_view(), name="screen-templates"),
        re_path(
            r"^screens/templates/(?P<template_id>[a-zA-Z0-9_-]+)/?$",
            UniverseScreenTemplateView.as_view(),
            name="screen-template-detail",
        ),
        path("strategy/factors", StrategyFactorsView.as_view(), name="strategy-factors"),
        path("strategy/position-fields", StrategyPositionFieldsView.as_view(), name="strategy-position-fields"),
        path("strategy/presets", StrategyPresetsView.as_view(), name="strategy-presets"),
        path("strategy/presets/<str:preset_id>", StrategyPresetView.as_view(), name="strategy-preset"),
        path("strategy/pipelines/compile", StrategyPipelineCompileView.as_view(), name="strategy-pipeline-compile"),
        path(
            "strategy/pipelines/decompile",
            StrategyPipelineDecompileView.as_view(),
            name="strategy-pipeline-decompile",
        ),
        path("strategy/pipelines/validate", StrategyPipelineValidateView.as_view(), name="strategy-pipeline-validate"),
        path(
            "strategy/pipelines/compile-portfolio",
            StrategyPortfolioCompileView.as_view(),
            name="strategy-portfolio-compile",
        ),
        path(
            "strategy/pipelines/decompile-portfolio",
            StrategyPortfolioDecompileView.as_view(),
            name="strategy-portfolio-decompile",
        ),
        path(
            "backtests/framework-templates",
            WorkspaceStrategyFrameworkTemplatesView.as_view(),
            name="workspace-framework-templates",
        ),
        path(
            "backtests/framework-templates/<str:template_id>",
            WorkspaceStrategyFrameworkTemplateDetailView.as_view(),
            name="workspace-framework-template-detail",
        ),
        re_path(r"^templates/?$", CatalogTemplatesView.as_view(), name="catalog-templates"),
        path("templates/<str:template_id>", CatalogTemplateDetailView.as_view(), name="catalog-template-detail"),
    ]
)

urlpatterns += [
    re_path(r"^screens/saved/?$", WorkspaceSavedScreensView.as_view(), name="workspace-saved-screens"),
    re_path(
        r"^screens/saved/(?P<screen_id>[^/]+)/?$",
        WorkspaceSavedScreenDetailView.as_view(),
        name="workspace-saved-screen-detail",
    ),
    re_path(r"^backtests/specs/?$", WorkspaceStrategySpecsView.as_view(), name="workspace-strategy-specs"),
    re_path(
        r"^backtests/specs/(?P<ir_id>[^/]+)/?$",
        WorkspaceStrategySpecDetailView.as_view(),
        name="workspace-strategy-spec-detail",
    ),
    re_path(
        r"^(?P<studio_path>(?:screens|backtests|strategy|live|execution|settings|templates|data)(?:/.*)?)$",
        DomainAPIRouteView.as_view(),
        name="domain-api-route",
    ),
]
