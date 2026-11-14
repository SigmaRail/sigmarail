"""LEAN-facing compatibility endpoints implemented by SigmaRail Studio."""

from __future__ import annotations

import hmac
import os
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class _OptionalApiKeyView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @staticmethod
    def _api_key_error(request: Request) -> Response | None:
        expected = os.environ.get("SIGMARAIL_API_KEY", "").strip()
        supplied = request.headers.get("X-API-Key", "")
        if expected and not hmac.compare_digest(supplied, expected):
            return Response({"detail": "invalid or missing API key"}, status=status.HTTP_401_UNAUTHORIZED)
        return None


class LeanMetaView(_OptionalApiKeyView):
    def get(self, request: Request) -> Response:
        error = self._api_key_error(request)
        if error:
            return error
        from sigmarail.universe import metadata

        return Response(metadata())


class LeanSourcesView(_OptionalApiKeyView):
    def get(self, request: Request) -> Response:
        error = self._api_key_error(request)
        if error:
            return error
        from sigmarail.universe import source_list

        return Response(source_list())


class LeanSourceFieldsView(_OptionalApiKeyView):
    def get(self, request: Request, source: str) -> Response:
        error = self._api_key_error(request)
        if error:
            return error
        from sigmarail.universe import source_fields

        try:
            return Response(source_fields(source))
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)


class LeanUniverseRunView(_OptionalApiKeyView):
    def post(self, request: Request) -> Response:
        error = self._api_key_error(request)
        if error:
            return error
        from sigmarail.universe import universe_run

        body = request.data if isinstance(request.data, dict) else {}
        result = universe_run(body)
        if "error" in result:
            response_status = (
                status.HTTP_400_BAD_REQUEST
                if result.get("code") == "invalid_query"
                else status.HTTP_502_BAD_GATEWAY
            )
            return Response(result, status=response_status)
        return Response(result)
