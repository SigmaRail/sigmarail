"""Expose the versioned SigmaRail Spec as focused MCP Resources."""
from __future__ import annotations

from typing import Any


def register_spec_resources(mcp: Any) -> None:
    """Register each packaged Spec document at its stable, versioned URI."""
    from sigmarail_spec import get_document_text, list_documents

    for document in list_documents():
        uri = document["uri"]

        def make_reader(resource_uri: str):
            def read_document() -> str:
                return get_document_text(resource_uri)

            return read_document

        read_document = make_reader(uri)

        read_document.__name__ = "read_spec_" + document["id"].replace(".", "_").replace("-", "_")
        mcp.resource(
            uri,
            name=read_document.__name__,
            title=document["title"],
            description=document["description"],
            mime_type="application/json",
        )(read_document)
