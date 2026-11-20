"""Finance KB episode read: episode metadata + body from ClickHouse or watch root."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

_ASSET_ALIASES = {
    "episode_md": "episode_md",
    "md": "episode_md",
    "video_mp4": "video_mp4",
    "video": "video_mp4",
    "mp4": "video_mp4",
    "whisper_srt": "whisper_srt",
    "srt": "whisper_srt",
    "captions_srt": "captions_srt",
    "captions": "captions_srt",
    "chart_snapshots": "chart_snapshots",
    "transcript_txt": "transcript_txt",
    "whisper_meta": "whisper_meta",
}
_MAX_INLINE_BYTES = 2_000_000

def _env_file_path() -> Path:
    explicit = (
        os.environ.get("KNOWLEDGEBASE_ENV_FILE", "").strip()
        or os.environ.get("FINANCE_KB_ENV_FILE", "").strip()
    )
    if explicit:
        return Path(explicit).expanduser()
    for name in (".knowledgebase", ".finance-kb"):
        candidate = Path.home() / name / ".env"
        if candidate.is_file():
            return candidate
    return Path.home() / ".knowledgebase" / ".env"


_DOC_COLUMNS = (
    "doc_id",
    "vault_relative_path",
    "channel_slug",
    "video_id",
    "post_id",
    "title",
    "source_url",
    "source_type",
    "onedrive_url",
    "sentiment",
    "summary",
    "publish_date",
    "body_text",
    "classifier",
    "observed_at",
    "thread_root_post_id",
    "in_reply_to_post_id",
)


def _load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _default_kb_watch_root() -> Path:
    for key in ("SIGMARAIL_KB_ROOT", "ONEDRIVE_KB_ROOT"):
        val = os.environ.get(key, "").strip()
        if val:
            return Path(val).expanduser()
    return Path("/Volumes/External/VeraKnowledgeBase/sources")


def list_kb_watch_root_candidates() -> list[Path]:
    """Ordered roots to try for ``kb_get_episode``."""
    _load_dotenv_file(_env_file_path())
    fallback = _default_kb_watch_root()

    ordered: list[Path] = []
    for key in ("KB_WATCH_ROOT", "SIGMARAIL_KB_ROOT", "ONEDRIVE_KB_ROOT"):
        val = os.environ.get(key, "").strip()
        if val:
            ordered.append(Path(val).expanduser())
    ordered.append(fallback)

    seen: set[str] = set()
    out: list[Path] = []
    for path in ordered:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            out.append(path)
    return out or [fallback]


def resolve_kb_watch_root() -> Path:
    roots = list_kb_watch_root_candidates()
    return roots[0]


def _read_body_under_watch_root(watch_root: Path, vault_relative_path: str) -> tuple[str, int]:
    rel = (vault_relative_path or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        raise ValueError("invalid vault_relative_path")
    root = watch_root.resolve()
    path = (root / rel).resolve()
    if root not in path.parents and path != root:
        raise ValueError("vault_relative_path escapes KB watch root")
    if not path.is_file():
        raise FileNotFoundError(f"markdown not found under KB watch root: {rel}")
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, len(text.encode("utf-8"))


def _fetch_document_row(
    client: Any,
    *,
    doc_id: str | None,
    vault_relative_path: str | None,
) -> dict[str, Any] | None:
    cols = ",\n                ".join(_DOC_COLUMNS)
    if doc_id and doc_id.strip():
        rows = client.query(
            f"""
            SELECT
                {cols}
            FROM kb_documents FINAL
            WHERE doc_id = %(doc_id)s
            LIMIT 1
            """,
            parameters={"doc_id": doc_id.strip()},
        )
    elif vault_relative_path and vault_relative_path.strip():
        rel = vault_relative_path.strip().replace("\\", "/")
        rows = client.query(
            f"""
            SELECT
                {cols}
            FROM kb_documents FINAL
            WHERE vault_relative_path = %(rel)s
            LIMIT 1
            """,
            parameters={"rel": rel},
        )
    else:
        raise ValueError("doc_id or vault_relative_path is required")

    if not rows.result_rows:
        return None
    doc = dict(zip(rows.column_names, rows.result_rows[0]))
    # Older schemas without body_text return fewer columns — tolerate gracefully.
    for col in _DOC_COLUMNS:
        doc.setdefault(col, "" if col != "observed_at" else None)
    return doc


def _episode_dir_from_vault_rel(rel: str, watch_root: Path) -> Path | None:
    rel = rel.strip().replace("\\", "/")
    if not rel:
        return None
    md = (watch_root / rel).resolve()
    if md.name == "episode.md":
        return md.parent
    return md.parent


def _load_episode_json(episode_dir: Path) -> dict[str, Any]:
    path = episode_dir / "episode.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _bundle_artifacts(episode_dir: Path, watch_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    manifest = _load_episode_json(episode_dir)
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}

    def _add(kind: str, path: Path) -> None:
        if not path.is_file():
            return
        try:
            rel = path.resolve().relative_to(watch_root.resolve())
            rel_s = str(rel).replace("\\", "/")
        except ValueError:
            rel_s = str(path)
        mime, _ = mimetypes.guess_type(path.name)
        entries.append(
            {
                "kind": kind,
                "relpath": rel_s,
                "path": str(path.resolve()),
                "size_bytes": path.stat().st_size,
                "mime": mime or "application/octet-stream",
            }
        )

    for key, kind in (
        ("episode_md", "episode_md"),
        ("video_mp4", "video_mp4"),
        ("whisper_srt", "whisper_srt"),
        ("captions_srt", "captions_srt"),
        ("whisper_meta", "whisper_meta"),
        ("chart_snapshots", "chart_snapshots"),
        ("transcript_txt", "transcript_txt"),
    ):
        rel = str(artifacts.get(key) or "").strip()
        if rel:
            _add(kind, episode_dir / rel)
        else:
            defaults = {
                "episode_md": "episode.md",
                "video_mp4": "video.mp4",
                "whisper_srt": "whisper.srt",
                "captions_srt": "captions.srt",
                "whisper_meta": "whisper.meta.json",
                "chart_snapshots": "chart_snapshots.json",
                "transcript_txt": "transcript.txt",
            }
            name = defaults.get(kind, "")
            if name:
                _add(kind, episode_dir / name)

    img_dir = episode_dir / "images"
    if img_dir.is_dir():
        for img in sorted(img_dir.iterdir()):
            if img.is_file():
                _add("image", img)
    return entries


def _resolve_watch_root(watch_root: Path | None) -> list[Path]:
    return [watch_root.expanduser()] if watch_root else list_kb_watch_root_candidates()


def list_kb_thread_documents(
    client: Any,
    *,
    thread_root_post_id: str,
    channel_slug: str | None = None,
) -> list[dict[str, Any]]:
    """All ``kb_documents`` rows sharing an X thread root (chronological)."""
    root = str(thread_root_post_id or "").strip()
    if not root:
        raise ValueError("thread_root_post_id is required")
    cols = ",\n                ".join(_DOC_COLUMNS)
    params: dict[str, Any] = {"root": root}
    where = "thread_root_post_id = %(root)s"
    if channel_slug and channel_slug.strip():
        where += " AND channel_slug = %(channel)s"
        params["channel"] = channel_slug.strip()
    rows = client.query(
        f"""
        SELECT
            {cols}
        FROM kb_documents FINAL
        WHERE {where}
        ORDER BY observed_at ASC, post_id ASC
        """,
        parameters=params,
    )
    out: list[dict[str, Any]] = []
    for row in rows.result_rows:
        doc = dict(zip(rows.column_names, row))
        for col in _DOC_COLUMNS:
            doc.setdefault(col, "" if col != "observed_at" else None)
        out.append(doc)
    return out


EXTRACTION_CONTRACT_REF = "canon://kb/extraction-schema/llm_episode_v2_manual_v1"
EXTRACTION_PAGE_CONTRACT_REF = "canon://kb/extraction-schema/llm_episode_v2_manual_page_v1"
CHUNK_EMBED_CONTRACT_REF = "canon://kb/chunk-embed-schema/kb_chunk_embed_v1"


def _extraction_page_counts(client: Any, *, doc_id: str) -> tuple[int, int]:
    rows = client.query(
        """
        SELECT
            (SELECT count() FROM kb_extraction_pages FINAL WHERE doc_id = %(doc_id)s) AS page_count,
            (SELECT count() FROM kb_extraction_partials FINAL WHERE doc_id = %(doc_id)s) AS partial_count
        """,
        parameters={"doc_id": doc_id},
    )
    if not rows.result_rows:
        return 0, 0
    counts = dict(zip(rows.column_names, rows.result_rows[0]))
    return int(counts.get("page_count") or 0), int(counts.get("partial_count") or 0)


def _ocr_text_from_segments_json(raw: str) -> str:
    try:
        segments = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return ""
    if not isinstance(segments, list):
        return ""
    parts: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("ocr_text") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _prior_context_from_transcript(transcript_text: str) -> str:
    lines = [ln.strip() for ln in str(transcript_text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def kb_list_extraction_pages(client: Any, *, doc_id: str) -> dict[str, Any]:
    """Manifest of extraction pages for MCP paging workflow."""
    resolved = str(doc_id or "").strip()
    if not resolved:
        raise ValueError("doc_id is required")
    doc = _fetch_document_row(client, doc_id=resolved, vault_relative_path=None)
    if doc is None:
        return {"error": f"no kb_documents row for {resolved!r}", "code": "not_found"}

    rows = client.query(
        """
        SELECT
            page_index,
            page_kind,
            start_sec,
            end_sec,
            length(transcript_text) AS char_count,
            length(ocr_segments_json) > 2 AS has_ocr,
            anchor_id
        FROM kb_extraction_pages FINAL
        WHERE doc_id = %(doc_id)s
        ORDER BY page_index
        """,
        parameters={"doc_id": resolved},
    )
    pages: list[dict[str, Any]] = []
    for row in rows.result_rows:
        item = dict(zip(rows.column_names, row))
        pages.append(
            {
                "page_index": int(item.get("page_index") or 0),
                "page_kind": str(item.get("page_kind") or "transcript"),
                "start_sec": float(item.get("start_sec") or 0.0),
                "end_sec": float(item.get("end_sec") or 0.0),
                "char_count": int(item.get("char_count") or 0),
                "has_ocr": bool(item.get("has_ocr")),
                "has_untimed_images": str(item.get("page_kind") or "") == "ocr_static",
                "anchor_id": str(item.get("anchor_id") or ""),
            }
        )
    partial_count = _extraction_page_counts(client, doc_id=resolved)[1]
    return {
        "doc_id": resolved,
        "page_count": len(pages),
        "pages_done": partial_count,
        "ready_to_finalize": len(pages) > 0 and partial_count >= len(pages),
        "pages": pages,
    }


def kb_get_extraction_page(
    client: Any,
    *,
    doc_id: str,
    page_index: int,
) -> dict[str, Any]:
    """Full extraction page payload for one MCP analyze/submit cycle."""
    resolved = str(doc_id or "").strip()
    if not resolved:
        raise ValueError("doc_id is required")
    idx = int(page_index)
    if idx < 0:
        raise ValueError("page_index must be >= 0")

    doc = _fetch_document_row(client, doc_id=resolved, vault_relative_path=None)
    if doc is None:
        return {"error": f"no kb_documents row for {resolved!r}", "code": "not_found"}

    page_count, _partial_count = _extraction_page_counts(client, doc_id=resolved)
    if page_count <= 0:
        return {
            "error": f"no kb_extraction_pages rows for {resolved!r}",
            "code": "not_found",
        }
    if idx >= page_count:
        return {
            "error": f"page_index {idx} out of range (page_count={page_count})",
            "code": "invalid_argument",
        }

    rows = client.query(
        """
        SELECT
            page_index,
            page_kind,
            anchor_id,
            start_sec,
            end_sec,
            transcript_text,
            ocr_segments_json,
            table_type_hint
        FROM kb_extraction_pages FINAL
        WHERE doc_id = %(doc_id)s AND page_index = %(page_index)s
        LIMIT 1
        """,
        parameters={"doc_id": resolved, "page_index": idx},
    )
    if not rows.result_rows:
        return {"error": f"page {idx} not found for {resolved!r}", "code": "not_found"}
    page = dict(zip(rows.column_names, rows.result_rows[0]))
    ocr_segments_raw = str(page.get("ocr_segments_json") or "[]")
    try:
        ocr_segments = json.loads(ocr_segments_raw)
    except json.JSONDecodeError:
        ocr_segments = []
    if not isinstance(ocr_segments, list):
        ocr_segments = []

    prior_context = ""
    if idx > 0:
        prev = client.query(
            """
            SELECT transcript_text
            FROM kb_extraction_pages FINAL
            WHERE doc_id = %(doc_id)s AND page_index = %(page_index)s
            LIMIT 1
            """,
            parameters={"doc_id": resolved, "page_index": idx - 1},
        )
        if prev.result_rows:
            prior_context = _prior_context_from_transcript(str(prev.result_rows[0][0] or ""))

    transcript_text = str(page.get("transcript_text") or "")
    return {
        "doc_id": resolved,
        "page_index": idx,
        "page_count": page_count,
        "page_kind": str(page.get("page_kind") or "transcript"),
        "anchor_id": str(page.get("anchor_id") or ""),
        "start_sec": float(page.get("start_sec") or 0.0),
        "end_sec": float(page.get("end_sec") or 0.0),
        "transcript_text": transcript_text,
        "ocr_text": _ocr_text_from_segments_json(ocr_segments_raw),
        "ocr_segments": ocr_segments,
        "untimed_images": ocr_segments if str(page.get("page_kind") or "") == "ocr_static" else [],
        "table_type_hint": str(page.get("table_type_hint") or ""),
        "char_count": len(transcript_text),
        "prior_context": prior_context,
        "extraction_page_contract_ref": EXTRACTION_PAGE_CONTRACT_REF,
    }


def kb_derivatives_status(client: Any, *, doc_id: str) -> dict[str, Any]:
    """Per-doc ClickHouse layer coverage for KB derivatives."""
    resolved = str(doc_id or "").strip()
    if not resolved:
        raise ValueError("doc_id is required")

    doc = _fetch_document_row(client, doc_id=resolved, vault_relative_path=None)
    if doc is None:
        return {"error": f"no kb_documents row for {resolved!r}", "code": "not_found"}

    body_ok = bool(str(doc.get("body_text") or "").strip())
    rows = client.query(
        """
        SELECT
            (SELECT count() FROM kb_mentions WHERE doc_id = %(doc_id)s) AS mention_count,
            (SELECT count() FROM kb_sentiment_items WHERE doc_id = %(doc_id)s) AS sentiment_count,
            (SELECT count() FROM kb_chunks WHERE doc_id = %(doc_id)s) AS chunk_count,
            (
                SELECT count()
                FROM kb_chunks
                WHERE doc_id = %(doc_id)s
                  AND length(embedding) > 0
            ) AS embedded_count,
            (SELECT count() FROM kb_subdocuments WHERE doc_id = %(doc_id)s) AS subdoc_count,
            (SELECT count() FROM kb_extraction_pages FINAL WHERE doc_id = %(doc_id)s) AS page_count,
            (SELECT count() FROM kb_extraction_partials FINAL WHERE doc_id = %(doc_id)s) AS partial_count,
            (
                SELECT count()
                FROM kb_portfolio_snapshots FINAL
                WHERE doc_id = %(doc_id)s
            ) AS portfolio_snapshot_count
        """,
        parameters={"doc_id": resolved},
    )
    counts = dict(zip(rows.column_names, rows.result_rows[0])) if rows.result_rows else {}
    mention_count = int(counts.get("mention_count") or 0)
    sentiment_count = int(counts.get("sentiment_count") or 0)
    chunk_count = int(counts.get("chunk_count") or 0)
    embedded_count = int(counts.get("embedded_count") or 0)
    subdoc_count = int(counts.get("subdoc_count") or 0)
    page_count = int(counts.get("page_count") or 0)
    partial_count = int(counts.get("partial_count") or 0)
    portfolio_snapshot_count = int(counts.get("portfolio_snapshot_count") or 0)

    chunks_fully_embedded = chunk_count > 0 and embedded_count >= chunk_count
    analysis_complete = body_ok and mention_count > 0 and sentiment_count > 0
    pages_ready = page_count > 0 and partial_count >= page_count
    partials_complete = page_count > 0 and partial_count == page_count

    layers: dict[str, Any] = {
        "document": {"ok": body_ok, "has_body_text": body_ok},
        "mentions": {"ok": mention_count > 0, "count": mention_count},
        "sentiment_items": {"ok": sentiment_count > 0, "count": sentiment_count},
        "extraction_pages": {"ok": page_count > 0, "count": page_count},
        "extraction_partials": {
            "ok": partials_complete,
            "count": partial_count,
            "pages_done": partial_count,
            "page_count": page_count,
        },
        "chunks": {
            "ok": chunks_fully_embedded,
            "count": chunk_count,
            "embedded": embedded_count,
            "optional_for_analysis": True,
            "agent_submitted_embeddings": True,
        },
        "portfolio_snapshots": {
            "ok": portfolio_snapshot_count > 0,
            "count": portfolio_snapshot_count,
            "optional_for_analysis": True,
        },
        "subdocuments": {"ok": subdoc_count > 0, "count": subdoc_count},
    }

    if not body_ok:
        recommended_action = "index_document"
        agent_guidance = (
            "Episode body_text is empty in ClickHouse. Index or fetch the source document "
            "before extraction."
        )
    elif page_count > 0 and not analysis_complete and partial_count < page_count:
        recommended_action = "submit_extraction_page"
        agent_guidance = (
            "Extraction pages are cataloged in ClickHouse. Call kb_list_extraction_pages, then "
            "for each page_index: kb_get_extraction_page → analyze → submit_extraction_page. "
            "Use get_extraction_page_schema for the per-page JSON contract. When all pages are "
            "submitted, call submit_episode_extraction_finalize (optional synthesis_json for "
            "executive_summary / market_tone)."
        )
    elif page_count > 0 and not analysis_complete and pages_ready:
        recommended_action = "submit_episode_extraction_finalize"
        agent_guidance = (
            "All extraction page partials are staged. Call submit_episode_extraction_finalize "
            "to merge partials and publish mentions, sentiment, and portfolio_snapshots to ClickHouse."
        )
    elif not analysis_complete:
        recommended_action = "submit_extraction"
        agent_guidance = (
            "Session LLM performs extraction — no LM Studio required. "
            "When kb_extraction_pages exists, prefer kb_list_extraction_pages paging; otherwise "
            "call get_extraction_schema, analyze kb_get_episode, then submit_episode_extraction. "
            "Safe to cite CH ticker marts after analysis_complete becomes true."
        )
    elif not chunks_fully_embedded:
        recommended_action = "submit_episode_chunks"
        agent_guidance = (
            "analysis_complete is true: mentions and sentiment are populated; you may cite "
            "CH-only marts for this episode. submit_episode_chunks is optional RAG hygiene. "
            "Call get_chunk_embed_schema, embed chunk_text with the session host, then submit "
            "embedding[] on each chunk row. SigmaRail MCP validates and upserts only — no server-side embed."
        )
    else:
        recommended_action = "none"
        agent_guidance = "All derivative layers populated, including embedded RAG chunks."

    complete = recommended_action == "none"

    return {
        "doc_id": resolved,
        "complete": complete,
        "analysis_complete": analysis_complete,
        "layers": layers,
        "recommended_action": recommended_action,
        "agent_guidance": agent_guidance,
        "extraction_contract_ref": EXTRACTION_CONTRACT_REF,
        "extraction_page_contract_ref": EXTRACTION_PAGE_CONTRACT_REF,
        "chunk_embed_contract_ref": CHUNK_EMBED_CONTRACT_REF,
    }


def kb_get_episode(
    client: Any,
    *,
    doc_id: str | None = None,
    vault_relative_path: str | None = None,
    watch_root: Path | None = None,
    include_thread: bool = False,
    include_derivatives_status: bool = True,
) -> dict[str, Any]:
    """Return kb_documents metadata plus body (ClickHouse body_text, else markdown file)."""
    doc = _fetch_document_row(
        client, doc_id=doc_id, vault_relative_path=vault_relative_path
    )
    if doc is None:
        key = doc_id or vault_relative_path
        return {"error": f"no kb_documents row for {key!r}", "code": "not_found"}

    resolved_doc_id = str(doc.get("doc_id") or doc_id or "").strip()
    derivatives: dict[str, Any] | None = None
    if include_derivatives_status and resolved_doc_id:
        derivatives = kb_derivatives_status(client, doc_id=resolved_doc_id)

    def _attach_derivatives(payload: dict[str, Any]) -> dict[str, Any]:
        if derivatives is not None:
            payload["derivatives_status"] = derivatives
            payload["extraction_contract_ref"] = EXTRACTION_CONTRACT_REF
        return payload

    rel = str(doc.get("vault_relative_path") or "")
    roots = _resolve_watch_root(watch_root)
    bundle_info: dict[str, Any] = {}
    for root in roots:
        ep_dir = _episode_dir_from_vault_rel(rel, root)
        if ep_dir is not None and ep_dir.is_dir():
            bundle_info = {
                "episode_dir": str(ep_dir),
                "episode_json": str(ep_dir / "episode.json"),
                "artifacts": _bundle_artifacts(ep_dir, root),
            }
            break

    stored = str(doc.get("body_text") or "").strip()
    thread_root = str(doc.get("thread_root_post_id") or doc.get("post_id") or "").strip()
    thread_docs: list[dict[str, Any]] | None = None
    if include_thread and thread_root:
        try:
            thread_docs = list_kb_thread_documents(
                client,
                thread_root_post_id=thread_root,
                channel_slug=str(doc.get("channel_slug") or "") or None,
            )
        except Exception:
            thread_docs = []

    if stored:
        out: dict[str, Any] = {"document": doc, "bundle": bundle_info}
        out["body"] = stored
        out["body_bytes"] = len(stored.encode("utf-8"))
        out["body_source"] = "clickhouse"
        if thread_docs is not None:
            out["thread"] = thread_docs
        return _attach_derivatives(out)

    out: dict[str, Any] = {"document": doc, "bundle": bundle_info}
    last_err: str | None = None
    for root in roots:
        try:
            body, nbytes = _read_body_under_watch_root(root, rel)
            out["body"] = body
            out["body_bytes"] = nbytes
            out["body_source"] = "filesystem"
            if thread_docs is not None:
                out["thread"] = thread_docs
            return _attach_derivatives(out)
        except FileNotFoundError as e:
            last_err = str(e)
        except ValueError as e:
            return {"error": str(e), "code": "invalid_argument", "document": doc}

    out["body"] = None
    out["body_source"] = "missing"
    out["read_error"] = last_err or f"markdown not found: {rel}"
    if thread_docs is not None:
        out["thread"] = thread_docs
    return _attach_derivatives(out)


def kb_get_episode_asset(
    client: Any,
    *,
    doc_id: str,
    asset: str,
    watch_root: Path | None = None,
    include_content: bool = False,
) -> dict[str, Any]:
    """Resolve one bundle artifact by ``doc_id``; optional base64 inline content (size-capped)."""
    doc = _fetch_document_row(client, doc_id=doc_id.strip(), vault_relative_path=None)
    if doc is None:
        return {"error": f"no kb_documents row for {doc_id!r}", "code": "not_found"}

    kind = _ASSET_ALIASES.get((asset or "").strip().lower())
    if not kind:
        return {
            "error": f"unknown asset {asset!r}; use whisper_srt, video_mp4, episode_md, …",
            "code": "invalid_argument",
        }

    rel = str(doc.get("vault_relative_path") or "")
    for root in _resolve_watch_root(watch_root):
        ep_dir = _episode_dir_from_vault_rel(rel, root)
        if ep_dir is None or not ep_dir.is_dir():
            continue
        artifacts = _bundle_artifacts(ep_dir, root)
        matches = [a for a in artifacts if a.get("kind") == kind]
        if not matches and kind == "image":
            matches = [a for a in artifacts if a.get("kind") == "image"]
        if not matches:
            continue
        entry = matches[0]
        out: dict[str, Any] = {"document": doc, "asset": entry}
        if include_content and entry.get("path"):
            path = Path(str(entry["path"]))
            size = int(entry.get("size_bytes") or 0)
            if size <= _MAX_INLINE_BYTES and path.is_file():
                raw = path.read_bytes()
                out["content_base64"] = base64.b64encode(raw).decode("ascii")
                out["content_encoding"] = "base64"
            else:
                out["content_skipped"] = "too_large" if size > _MAX_INLINE_BYTES else "missing"
        return out

    return {"error": f"asset {kind!r} not found for doc_id={doc_id!r}", "code": "not_found"}
