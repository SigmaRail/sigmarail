"""Finance KB write path: MCP bridges to KnowledgeBase apply/indexing."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _ensure_knowledgebase_import() -> None:
    """Add monorepo KnowledgeBase/src to sys.path when MCP launcher omits PYTHONPATH."""
    try:
        import knowledgebase  # noqa: F401
        return
    except ImportError:
        pass

    candidates: list[Path] = []
    for key in ("KNOWLEDGEBASE_SRC", "FINANCE_KB_SRC"):
        val = os.environ.get(key, "").strip()
        if val:
            candidates.append(Path(val).expanduser())
    for key in ("FINANCE_PROJECTS_ROOT", "WORKSPACE_ROOT"):
        val = os.environ.get(key, "").strip()
        if val:
            candidates.append(Path(val).expanduser() / "KnowledgeBase" / "src")
    here = Path(__file__).resolve()
    if len(here.parents) >= 4:
        candidates.append(here.parents[3] / "KnowledgeBase" / "src")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen or not candidate.is_dir():
            continue
        seen.add(key)
        sys.path.insert(0, key)
        try:
            import knowledgebase  # noqa: F401
            return
        except ImportError:
            sys.path.remove(key)

    raise ImportError(
        "No module named 'knowledgebase'. Set PYTHONPATH to KnowledgeBase/src "
        "or run SigmaRail MCP via VeraBase/scripts/run_vera_mcp_stdio.sh"
    )


def get_extraction_schema() -> dict[str, Any]:
    """Return versioned JSON Schema for manual episode extraction."""
    _ensure_knowledgebase_import()
    from knowledgebase.indexing.llm_prompts import (
        MANUAL_EXTRACTION_SCHEMA_VERSION,
        manual_extraction_json_schema,
    )

    schema = manual_extraction_json_schema()
    return {
        "version": MANUAL_EXTRACTION_SCHEMA_VERSION,
        "schema": schema,
        "resource_uri": f"canon://kb/extraction-schema/{MANUAL_EXTRACTION_SCHEMA_VERSION}",
    }


def get_extraction_page_schema() -> dict[str, Any]:
    """Return versioned JSON Schema for one MCP extraction page partial."""
    _ensure_knowledgebase_import()
    from knowledgebase.indexing.llm_prompts import (
        MANUAL_EXTRACTION_PAGE_SCHEMA_VERSION,
        manual_extraction_page_json_schema,
    )

    schema = manual_extraction_page_json_schema()
    return {
        "version": MANUAL_EXTRACTION_PAGE_SCHEMA_VERSION,
        "schema": schema,
        "resource_uri": f"canon://kb/extraction-schema/{MANUAL_EXTRACTION_PAGE_SCHEMA_VERSION}",
    }


def get_chunk_embed_schema() -> dict[str, Any]:
    """Return versioned JSON Schema for agent-submitted RAG chunk vectors."""
    _ensure_knowledgebase_import()
    from knowledgebase.indexing.llm_prompts import (
        CHUNK_EMBED_SCHEMA_VERSION,
        DEFAULT_CHUNK_EMBED_DIM,
        DEFAULT_CHUNK_EMBED_MODEL,
        chunk_embed_json_schema,
    )

    schema = chunk_embed_json_schema(embed_dim=DEFAULT_CHUNK_EMBED_DIM)
    return {
        "version": CHUNK_EMBED_SCHEMA_VERSION,
        "schema": schema,
        "embed_dim": DEFAULT_CHUNK_EMBED_DIM,
        "embed_model": DEFAULT_CHUNK_EMBED_MODEL,
        "resource_uri": f"canon://kb/chunk-embed-schema/{CHUNK_EMBED_SCHEMA_VERSION}",
        "agent_guidance": (
            "Embed chunk_text with the session host embedding API, then submit "
            "submit_episode_chunks with embedding[] on each row. SigmaRail MCP does not "
            "call LM Studio or ClickHouse aiEmbed on this path."
        ),
    }


def submit_extraction_page(
    *,
    doc_id: str,
    page_index: int,
    partial_json: dict[str, Any] | str,
) -> dict[str, Any]:
    """Validate and stage one extraction page partial in ClickHouse."""
    _ensure_knowledgebase_import()
    from knowledgebase.indexing.config import FinanceKbConfig
    from knowledgebase.indexing.db import upsert_kb_extraction_partial
    from knowledgebase.pipeline.apply import validate_extraction_page_data

    if isinstance(partial_json, str):
        data = json.loads(partial_json)
    else:
        data = dict(partial_json)
    validate_extraction_page_data(data)
    resolved_id = str(doc_id or data.get("doc_id") or "").strip()
    if not resolved_id:
        raise ValueError("doc_id is required")
    idx = int(page_index)
    if idx < 0:
        raise ValueError("page_index must be >= 0")
    data.setdefault("doc_id", resolved_id)
    data["page_index"] = idx
    data.setdefault("classifier", "llm_episode_v2_manual_page")

    cfg = FinanceKbConfig.from_env()
    from knowledgebase.indexing.db import ch_client

    client = ch_client(cfg)
    rows = client.query(
        """
        SELECT
            (SELECT count() FROM kb_extraction_pages FINAL WHERE doc_id = %(doc_id)s) AS page_count,
            (SELECT count() FROM kb_extraction_partials FINAL WHERE doc_id = %(doc_id)s) AS partial_count
        """,
        parameters={"doc_id": resolved_id},
    )
    page_count = int(rows.result_rows[0][0]) if rows.result_rows else 0
    if page_count <= 0:
        raise ValueError(f"no kb_extraction_pages rows for doc_id={resolved_id!r}")
    if idx >= page_count:
        raise ValueError(f"page_index {idx} out of range (page_count={page_count})")

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    upsert_kb_extraction_partial(cfg, doc_id=resolved_id, page_index=idx, partial_json=payload)

    partial_count = int(
        client.query(
            "SELECT count() FROM kb_extraction_partials FINAL WHERE doc_id = %(doc_id)s",
            parameters={"doc_id": resolved_id},
        ).result_rows[0][0]
    )

    return {
        "status": "staged",
        "doc_id": resolved_id,
        "page_index": idx,
        "pages_done": partial_count,
        "page_count": page_count,
        "ready_to_finalize": partial_count >= page_count,
    }


def submit_episode_extraction_finalize(
    *,
    doc_id: str,
    synthesis_json: dict[str, Any] | str | None = None,
    rewrite_transcript: bool = True,
    write_manual_sidecar: bool = False,
) -> dict[str, Any]:
    """Merge staged page partials (+ optional synthesis) and publish via apply_extraction_payload."""
    _ensure_knowledgebase_import()
    from knowledgebase.indexing.config import FinanceKbConfig
    from knowledgebase.indexing.db import ch_client, delete_kb_extraction_partials_for_doc
    from knowledgebase.indexing.llm_episode import merge_episode_extractions
    from knowledgebase.pipeline.apply import apply_extraction_payload, validate_manual_extraction_data

    resolved_id = str(doc_id or "").strip()
    if not resolved_id:
        raise ValueError("doc_id is required")

    cfg = FinanceKbConfig.from_env()
    client = ch_client(cfg)
    meta = client.query(
        """
        SELECT
            (SELECT count() FROM kb_extraction_pages FINAL WHERE doc_id = %(doc_id)s) AS page_count,
            (SELECT count() FROM kb_extraction_partials FINAL WHERE doc_id = %(doc_id)s) AS partial_count
        """,
        parameters={"doc_id": resolved_id},
    )
    page_count = int(meta.result_rows[0][0]) if meta.result_rows else 0
    partial_count = int(meta.result_rows[0][1]) if meta.result_rows else 0
    if page_count <= 0:
        raise ValueError(f"no kb_extraction_pages rows for doc_id={resolved_id!r}")
    if partial_count < page_count:
        raise ValueError(f"incomplete partials: {partial_count}/{page_count} pages staged")
    rows = client.query(
        """
        SELECT page_index, partial_json
        FROM kb_extraction_partials FINAL
        WHERE doc_id = %(doc_id)s
        ORDER BY page_index
        """,
        parameters={"doc_id": resolved_id},
    )
    partials: list[dict[str, Any]] = []
    for row in rows.result_rows:
        raw = str(row[1] or "")
        if not raw.strip():
            continue
        partials.append(json.loads(raw))

    merged = merge_episode_extractions(partials)
    if synthesis_json is not None:
        if isinstance(synthesis_json, str):
            synth = json.loads(synthesis_json)
        else:
            synth = dict(synthesis_json)
        for key in (
            "executive_summary",
            "market_tone",
            "market_tone_confidence",
            "market_structure",
            "analysis_scope",
            "market_recency",
            "analysis_scope_reason",
            "exclude_from_kb",
        ):
            if key in synth and synth[key] not in (None, ""):
                merged[key] = synth[key]

    merged.setdefault("doc_id", resolved_id)
    merged.setdefault("classifier", "llm_episode_v2_manual")
    if not str(merged.get("executive_summary") or "").strip():
        merged["executive_summary"] = " ".join(
            str(p.get("executive_summary") or "").strip()
            for p in partials
            if str(p.get("executive_summary") or "").strip()
        ) or "Episode extraction (paged merge)."
    if not str(merged.get("market_tone") or "").strip():
        merged["market_tone"] = "mixed"

    validate_manual_extraction_data(merged)
    sidecar = None
    if write_manual_sidecar:
        from knowledgebase.pipeline.apply import resolve_episode_md_path

        md_path = resolve_episode_md_path(doc_id=resolved_id, cfg=cfg)
        stem = md_path.stem if md_path.name != "episode.md" else md_path.parent.name
        sidecar = md_path.parent / f"{stem}.llm_episode_v2.manual.json"

    result = apply_extraction_payload(
        merged,
        doc_id=resolved_id,
        rewrite_transcript=rewrite_transcript,
        write_manual_sidecar=sidecar,
    )
    delete_kb_extraction_partials_for_doc(cfg, doc_id=resolved_id)
    result["status"] = "published"
    result["pages_merged"] = len(partials)
    result["page_count"] = page_count
    result.setdefault("portfolio_snapshots", int(result.get("portfolio_snapshots") or 0))
    return result


def submit_episode_extraction(
    *,
    doc_id: str,
    extraction_json: dict[str, Any] | str,
    rewrite_transcript: bool = True,
    write_manual_sidecar: bool = False,
) -> dict[str, Any]:
    """Validate and publish extraction JSON via ``kb-apply-extraction`` logic."""
    _ensure_knowledgebase_import()
    from knowledgebase.pipeline.apply import apply_extraction_payload, validate_manual_extraction_data

    if isinstance(extraction_json, str):
        data = json.loads(extraction_json)
    else:
        data = dict(extraction_json)
    validate_manual_extraction_data(data)
    resolved_id = str(doc_id or data.get("doc_id") or "").strip()
    if not resolved_id:
        raise ValueError("doc_id is required")
    data.setdefault("doc_id", resolved_id)
    sidecar = None
    if write_manual_sidecar:
        from knowledgebase.indexing.config import FinanceKbConfig
        from knowledgebase.pipeline.apply import resolve_episode_md_path

        cfg = FinanceKbConfig.from_env()
        md_path = resolve_episode_md_path(doc_id=resolved_id, cfg=cfg)
        stem = md_path.stem if md_path.name != "episode.md" else md_path.parent.name
        sidecar = md_path.parent / f"{stem}.llm_episode_v2.manual.json"
    return apply_extraction_payload(
        data,
        doc_id=resolved_id,
        rewrite_transcript=rewrite_transcript,
        write_manual_sidecar=sidecar,
    )


def submit_episode_chunks(
    *,
    doc_id: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Upsert RAG chunks with agent-submitted ``embedding[]`` vectors."""
    _ensure_knowledgebase_import()
    from knowledgebase.indexing.config import FinanceKbConfig
    from knowledgebase.pipeline.chunks import upsert_kb_chunks_for_doc

    resolved_id = str(doc_id or "").strip()
    if not resolved_id:
        raise ValueError("doc_id is required")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("chunks must be a non-empty array")
    cfg = FinanceKbConfig.from_env()
    result = upsert_kb_chunks_for_doc(cfg, doc_id=resolved_id, chunks=chunks)
    result["status"] = "published"
    return result
