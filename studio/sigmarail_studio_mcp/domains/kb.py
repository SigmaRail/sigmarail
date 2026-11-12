"""kb domain: KB episode read + extraction/submission pipeline (orphaned vera-mcp-kb tools)."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call, try_call


# --- episode read (client) -------------------------------------------------
def get_episode(
    doc_id: str | None = None,
    vault_relative_path: str | None = None,
    include_derivatives_status: bool = True,
) -> dict[str, Any]:
    from vera_query_core.kb_episode import kb_get_episode

    return call(kb_get_episode, doc_id=doc_id, vault_relative_path=vault_relative_path, include_derivatives_status=include_derivatives_status)


def get_episode_asset(doc_id: str, asset: str, include_content: bool = False) -> dict[str, Any]:
    from vera_query_core.kb_episode import kb_get_episode_asset

    return call(kb_get_episode_asset, doc_id=doc_id, asset=asset, include_content=include_content)


def derivatives_status(doc_id: str) -> dict[str, Any]:
    from vera_query_core.kb_episode import kb_derivatives_status

    return call(kb_derivatives_status, doc_id=doc_id)


def list_extraction_pages(doc_id: str) -> dict[str, Any]:
    from vera_query_core.kb_episode import kb_list_extraction_pages

    return call(kb_list_extraction_pages, doc_id=doc_id)


def get_extraction_page(doc_id: str, page_index: int) -> dict[str, Any]:
    from vera_query_core.kb_episode import kb_get_extraction_page

    return call(kb_get_extraction_page, doc_id=doc_id, page_index=page_index)


# --- schemas + submission (no client) --------------------------------------
def extraction_schema() -> dict[str, Any]:
    from vera_query_core.kb_pipeline import get_extraction_schema

    return try_call(get_extraction_schema)


def extraction_page_schema() -> dict[str, Any]:
    from vera_query_core.kb_pipeline import get_extraction_page_schema

    return try_call(get_extraction_page_schema)


def chunk_embed_schema() -> dict[str, Any]:
    from vera_query_core.kb_pipeline import get_chunk_embed_schema

    return try_call(get_chunk_embed_schema)


def submit_extraction_page(doc_id: str, page_index: int, partial_json: dict[str, Any] | str) -> dict[str, Any]:
    from vera_query_core.kb_pipeline import submit_extraction_page

    return try_call(submit_extraction_page, doc_id=doc_id, page_index=page_index, partial_json=partial_json)


def submit_episode_extraction(
    doc_id: str,
    extraction_json: dict[str, Any] | str,
    rewrite_transcript: bool = True,
    write_manual_sidecar: bool = False,
) -> dict[str, Any]:
    from vera_query_core.kb_pipeline import submit_episode_extraction

    return try_call(
        submit_episode_extraction,
        doc_id=doc_id,
        extraction_json=extraction_json,
        rewrite_transcript=rewrite_transcript,
        write_manual_sidecar=write_manual_sidecar,
    )


def submit_episode_extraction_finalize(
    doc_id: str,
    synthesis_json: dict[str, Any] | str | None = None,
    rewrite_transcript: bool = True,
    write_manual_sidecar: bool = False,
) -> dict[str, Any]:
    from vera_query_core.kb_pipeline import submit_episode_extraction_finalize

    return try_call(
        submit_episode_extraction_finalize,
        doc_id=doc_id,
        synthesis_json=synthesis_json,
        rewrite_transcript=rewrite_transcript,
        write_manual_sidecar=write_manual_sidecar,
    )


def submit_episode_chunks(doc_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    from vera_query_core.kb_pipeline import submit_episode_chunks

    return try_call(submit_episode_chunks, doc_id=doc_id, chunks=chunks)
