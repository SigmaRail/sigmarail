"""Authenticated, package-backed universe screen templates."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .views import _workspace_for_request


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    # SigmaRail owns the built-in v1 screener specs. Read that catalog directly
    # instead of depending on a generated JSON bundle that is not shipped with
    # the application image.
    from sigmarail.features.template_catalog import list_templates, summary_row

    templates: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    records = list_templates(kind="screener", include_body=True)
    for record in records:
        spec = record.get("body")
        if (
            not isinstance(spec, dict)
            or spec.get("version") != 1
            or spec.get("from") != "daily_screener"
        ):
            continue
        template_id = record.get("id")
        if not isinstance(template_id, str) or not template_id:
            continue
        templates.append(summary_row(record))
        details[template_id] = {
            "id": template_id,
            "screen_ir": "universe_query_v1",
            "spec": spec,
        }

    # Preserve the established UI ids as aliases for their SigmaRail presets.
    preset_aliases = {
        "minervini_trend_template": ("minervini_tt", "Minervini Trend Template (Standard)"),
        "canslim_template": ("canslim", "CANSLIM Leader Filter"),
    }
    for alias, (target, label) in preset_aliases.items():
        if target not in details:
            continue
        templates.append({"id": alias, "label": label, "status": "active"})
        details[alias] = {**details[target], "id": alias}

    template_ids: set[str] = set()
    for template in templates:
        if not isinstance(template, dict):
            raise ValueError("invalid screen template summary")
        template_id = template.get("id")
        if not isinstance(template_id, str) or not template_id or template_id in template_ids:
            raise ValueError("invalid or duplicate screen template id")
        if not isinstance(template.get("label"), str) or not template["label"]:
            raise ValueError("screen template label is required")
        template_ids.add(template_id)

    if template_ids != set(details):
        raise ValueError("screen template summaries and details do not match")
    for template_id, detail in details.items():
        spec = detail.get("spec") if isinstance(detail, dict) else None
        if (
            not isinstance(detail, dict)
            or detail.get("id") != template_id
            or not isinstance(spec, dict)
            or spec.get("version") != 1
            or spec.get("from") != "daily_screener"
            or not isinstance(spec.get("where"), dict)
        ):
            raise ValueError(f"invalid universe query document for template {template_id!r}")
    return {"schema_version": 1, "templates": templates, "details": details}


def packaged_universe_screens() -> list[dict[str, Any]]:
    """Return built-in templates in the saved-screen shape used by older clients.

    The templates are part of this Django application, so legacy shared-screen
    availability must not determine whether users can browse or load them.
    """
    catalog = _load_catalog()
    summaries = {template["id"]: template for template in catalog["templates"]}
    screens: list[dict[str, Any]] = []
    for template_id, detail in catalog["details"].items():
        summary = summaries[template_id]
        screens.append(
            {
                "id": template_id,
                "name": summary["label"],
                "description": summary.get("description", ""),
                "spec": detail["spec"],
                "screen_ir": detail.get("screen_ir", "universe_query_v1"),
                "is_system": True,
                "is_shared": False,
                "source_template_id": template_id,
                "category": "System",
            }
        )
    return screens


def _catalog_response(request: Request) -> tuple[dict[str, Any] | None, Response | None]:
    _, error = _workspace_for_request(request)
    if error:
        return None, error
    try:
        return _load_catalog(), None
    except (ImportError, OSError, ValueError):
        return None, Response(
            {"detail": "The packaged universe screen catalog is unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class UniverseScreenTemplatesView(APIView):
    """List built-in templates without contacting the legacy API service."""

    def get(self, request: Request) -> Response:
        catalog, error = _catalog_response(request)
        if error:
            return error
        assert catalog is not None
        return Response({"templates": catalog["templates"]})


class UniverseScreenTemplateView(APIView):
    """Return one built-in universe screen document from the packaged catalog."""

    def get(self, request: Request, template_id: str) -> Response:
        catalog, error = _catalog_response(request)
        if error:
            return error
        assert catalog is not None
        detail = catalog["details"].get(template_id)
        if detail is None:
            return Response({"detail": "Universe screen template not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(detail)
