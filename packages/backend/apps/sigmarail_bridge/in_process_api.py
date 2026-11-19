"""Dispatch the existing Studio API views inside the AppTension Django process.

The domain views stay in the repository's top-level ``api`` and ``screens``
packages. This adapter keeps the old wire routes while eliminating the second
HTTP server hop.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from django.http import HttpResponse
from django.test import RequestFactory
from django.urls.resolvers import RegexPattern, URLResolver

logger = logging.getLogger(__name__)


class InProcessDispatchError(RuntimeError):
    """An API route could not be dispatched in-process."""


def _add_compatibility_package_paths() -> None:
    """Expose shared query-contract packages without shadowing AppTension config."""
    for package_root in (Path("/opt/vera-base/src"), Path("/opt/vera-spec/src")):
        if package_root.is_dir() and str(package_root) not in sys.path:
            sys.path.append(str(package_root))


@dataclass
class InProcessResponse:
    """Small response facade for the few catalog paths using the old client API."""

    response: HttpResponse

    @property
    def status_code(self) -> int:
        return self.response.status_code

    @property
    def content(self) -> bytes:
        return self.response.content

    @property
    def headers(self):
        return self.response.headers

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            try:
                phrase = HTTPStatus(self.status_code).phrase
            except ValueError:
                phrase = "HTTP error"
            raise InProcessDispatchError(f"{self.status_code} {phrase}")


def dispatch_api_request(
    method: str,
    path: str,
    *,
    query: str = "",
    content: bytes | None = None,
    user=None,
    session=None,
    headers: dict[str, str] | None = None,
) -> InProcessResponse:
    """Run a root ``api.urls`` view without opening a network connection."""
    route = path.removeprefix("/api/").lstrip("/")
    if not route:
        raise InProcessDispatchError("An API route is required")
    if query:
        route = f"{route}?{query}"

    try:
        _add_compatibility_package_paths()
        resolver = URLResolver(RegexPattern(r"^"), "api.urls")
        match = resolver.resolve(route.split("?", 1)[0])
    except Exception as exc:
        logger.exception("Could not resolve in-process domain API route %s %s", method.upper(), path)
        raise InProcessDispatchError("The requested API route is not registered in AppTension") from exc

    header_values = headers or {}
    request = RequestFactory().generic(
        method.upper(),
        f"/api/{route}",
        data=content,
        content_type=header_values.get("content-type", "application/json"),
        HTTP_ACCEPT=header_values.get("accept", "application/json"),
    )
    if user is not None:
        request.user = user
        # DRF views normally re-run authentication when wrapping an HttpRequest.
        # Carry AppTension's already-authenticated identity into that boundary.
        request._force_auth_user = user
        request._force_auth_token = None
        # This private process-local marker replaces the former signed HTTP hop
        # for domain endpoints that intentionally disable their own auth layer.
        request._app_tension_authenticated_dispatch = True
    if session is not None:
        request.session = session
    for name, value in header_values.items():
        key = "HTTP_" + name.upper().replace("-", "_")
        if name.lower() not in {"content-type", "accept"}:
            setattr(request, key, value)

    try:
        response = match.func(request, *match.args, **match.kwargs)
        if hasattr(response, "render") and not getattr(response, "is_rendered", True):
            response.render()
    except Exception as exc:
        logger.exception("In-process domain API handler failed for %s %s", method.upper(), path)
        raise InProcessDispatchError("The in-process API handler failed") from exc
    return InProcessResponse(response)
