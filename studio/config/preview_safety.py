"""Scope the private local preview to Alpaca paper trading."""

from __future__ import annotations

import json

from django.http import JsonResponse


class PaperOnlyPreviewMiddleware:
    """Reject live brokerage actions while retaining paper account controls."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info.rstrip("/")
        if request.method in {"POST", "PUT", "PATCH"}:
            body = self._json_body(request)
            if path == "/api/live/accounts" and body.get("environment", "paper") != "paper":
                return JsonResponse(
                    {"detail": "This preview is restricted to brokerage paper accounts."},
                    status=403,
                )
            if path == "/api/live/local-runtime" and body.get("action") == "start-live":
                return JsonResponse(
                    {"detail": "Live deployments are disabled in this preview; use the paper account."},
                    status=403,
                )
        return self.get_response(request)

    @staticmethod
    def _json_body(request) -> dict:
        try:
            value = json.loads(request.body or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}
