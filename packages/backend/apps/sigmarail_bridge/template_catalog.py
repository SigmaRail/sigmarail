"""Authenticated endpoints for the installed SigmaRail template catalog."""

from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from sigmarail.features.template_catalog import get_template, list_templates, summary_row

from .views import _workspace_for_request


class CatalogTemplatesView(APIView):
    """List screener and strategy templates from SigmaRail's packaged catalog."""

    def get(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        kind = request.query_params.get("kind") or None
        status_filter = request.query_params.get("status") or None
        if kind not in (None, "screener", "strategy"):
            return Response({"detail": "kind must be screener or strategy"}, status=status.HTTP_400_BAD_REQUEST)
        if status_filter not in (None, "active", "deprecated", "draft"):
            return Response(
                {"detail": "status must be active, deprecated, or draft"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = [summary_row(record) for record in list_templates(kind=kind, status=status_filter)]
        return Response({"templates": rows})


class CatalogTemplateDetailView(APIView):
    """Return one complete screener or strategy template record."""

    def get(self, request: Request, template_id: str) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        try:
            return Response(get_template(template_id))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
