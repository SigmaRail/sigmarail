"""Authenticated, package-backed universe screen templates."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .views import _workspace_for_request


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    resource = files("apps.sigmarail_bridge").joinpath("data", "screen_templates.json")
    catalog = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise ValueError("invalid packaged screen template catalog")
    templates = catalog.get("templates")
    details = catalog.get("details")
    if not isinstance(templates, list) or not isinstance(details, dict):
        raise ValueError("invalid packaged screen template catalog")

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
    return catalog


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
    except (OSError, ValueError):
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
