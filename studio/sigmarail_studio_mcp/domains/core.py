"""SigmaRail core data catalog and query operations."""
from __future__ import annotations

from typing import Any

from sigmarail_spec.data_query import DataQueryV1


def list_datasets() -> dict[str, Any]:
    from sigmarail.query import list_datasets as _list

    return _list()


def describe_dataset(dataset_id: str) -> dict[str, Any]:
    from sigmarail.query import describe_dataset as _describe

    try:
        return _describe(dataset_id)
    except ValueError as exc:
        return {"error": str(exc), "code": "unknown_dataset"}


def query_dataset(query: DataQueryV1) -> dict[str, Any]:
    from sigmarail.query import query_dataset as _query

    return _query(query)
