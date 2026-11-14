"""SigmaRail-native dataset catalog and bounded core query API."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class CoreDatasetsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from sigmarail.query import list_datasets

        return Response(list_datasets())


class CoreDatasetView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, dataset_id: str) -> Response:
        from sigmarail.query import describe_dataset

        try:
            return Response(describe_dataset(dataset_id))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)


class CoreQueryView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        from sigmarail.query import compile_query, query_dataset
        from sigmarail_spec.data_query import DataQueryV1

        body = request.data if isinstance(request.data, dict) else {}
        try:
            query = DataQueryV1.model_validate(body)
            compile_query(query)
        except (ValidationError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        result = query_dataset(query)
        if "error" in result:
            response_status = (
                status.HTTP_400_BAD_REQUEST
                if result.get("code") == "invalid_query"
                else status.HTTP_502_BAD_GATEWAY
            )
            return Response(result, status=response_status)
        return Response(result)
