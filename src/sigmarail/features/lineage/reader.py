from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _repo_root() -> Path:
    # .../VeraBase/src/sigmarail.features/lineage/reader.py -> VeraBase/
    return Path(__file__).resolve().parents[3]


def _validate_table(table: str) -> str:
    t = table.strip()
    if not _IDENT.match(t):
        raise ValueError("Invalid table name")
    return t


def load_table_lineage(table: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    tbl = _validate_table(table)
    root = repo_root or _repo_root()
    p = root / "sql/lineage" / f"{tbl}.json"
    if not p.exists():
        raise FileNotFoundError(f"Lineage artifact not found for table {tbl!r}")
    return json.loads(p.read_text(encoding="utf-8"))


def has_table_lineage(table: str, *, repo_root: Path | None = None) -> bool:
    try:
        tbl = _validate_table(table)
    except ValueError:
        return False
    root = repo_root or _repo_root()
    return (root / "sql/lineage" / f"{tbl}.json").exists()


def _enrich_sources_with_links(
    sources: list[dict[str, Any]] | None, *, repo_root: Path | None = None
) -> list[dict[str, Any]]:
    if not sources:
        return []
    out: list[dict[str, Any]] = []
    for s in sources:
        t = str(s.get("table", "") or "")
        c = str(s.get("column", "") or "")
        via = str(s.get("via", "") or "")
        has = has_table_lineage(t, repo_root=repo_root) if t else False
        out.append(
            {
                "table": t,
                "column": c,
                "via": via,
                "has_lineage": has,
                "next_explain": {"table": t, "column": c} if (t and c and has) else None,
            }
        )
    return out


def _registry_enrichment(
    table: str, column: str, *, repo_root: Path | None
) -> dict[str, Any]:
    """Git-pure entity + COMMENT enrichment (no ClickHouse). Never raises."""
    out: dict[str, Any] = {}
    try:
        from sigmarail.features.registry.enrich import column_comment, entity_for_column

        out["comment"] = column_comment(repo_root, table, column)
        out["entity"] = entity_for_column(repo_root, table, column)
    except Exception:  # enrichment must never break explain_column
        out.setdefault("comment", None)
        out.setdefault("entity", None)
    return out


def aggregate_column_caveats(
    table: str,
    column: str,
    *,
    repo_root: Path | None = None,
    max_depth: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Traverse upstream lineage sources and collect all caveats and closest math presentation."""
    visited: set[tuple[str, str]] = set()
    queue: list[tuple[str, str, int]] = [(table, column, 0)]
    collected_caveats: list[dict[str, Any]] = []
    inherited_math: dict[str, Any] | None = None

    while queue:
        tbl, col, depth = queue.pop(0)
        if (tbl, col) in visited or depth > max_depth:
            continue
        visited.add((tbl, col))

        if not has_table_lineage(tbl, repo_root=repo_root):
            continue

        try:
            artifact = load_table_lineage(tbl, repo_root=repo_root)
        except Exception:
            continue

        col_info = artifact.get("columns", {}).get(col)
        if not isinstance(col_info, dict):
            continue

        cur_math = col_info.get("math")
        if cur_math and isinstance(cur_math, dict):
            latex_str = cur_math.get("latex", "")
            # Prioritize formulas that contain operations/windows rather than bare single-token identifiers
            is_rich = any(token in latex_str for token in ("\\frac", "\\text{Rank}", "\\text{SMA}", "\\cdot", "+", "\\begin{cases}", "\\min", "\\max"))
            already_has_rich = inherited_math and any(token in inherited_math.get("latex", "") for token in ("\\frac", "\\text{Rank}", "\\text{SMA}", "\\begin{cases}", "\\min", "\\max"))
            if is_rich and not already_has_rich:
                inherited_math = cur_math
            elif not inherited_math:
                inherited_math = cur_math

        for c in col_info.get("caveats", []):
            collected_caveats.append(dict(c))

        # Enqueue upstream sources
        sources = col_info.get("sources", [])
        if isinstance(sources, list):
            for s in sources:
                if isinstance(s, dict):
                    src_tbl = str(s.get("table", "") or "")
                    src_col = str(s.get("column", "") or "")
                    if src_tbl and src_col and (src_tbl, src_col) not in visited:
                        queue.append((src_tbl, src_col, depth + 1))

        # Also inspect referenced sibling columns in the same table (e.g. rs_rating using blended_pct)
        expr_text = col_info.get("expression", "")
        for sibling_name in artifact.get("columns", {}):
            if sibling_name != col and re.search(rf"\b{re.escape(sibling_name)}\b", expr_text):
                if (tbl, sibling_name) not in visited:
                    queue.append((tbl, sibling_name, depth + 1))

    # Deduplicate and merge caveats
    merged: dict[str, dict[str, Any]] = {}
    for c in collected_caveats:
        code = c.get("code")
        if not code:
            continue
        if code not in merged:
            merged[code] = c
        else:
            if code == "LOOKBACK_MINIMUM":
                prev_bars = merged[code].get("lookback_bars", 0)
                new_bars = c.get("lookback_bars", 0)
                if new_bars > prev_bars:
                    merged[code] = c

    return list(merged.values()), inherited_math


def explain_column(
    table: str,
    column: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    tbl = _validate_table(table)
    col = column.strip()
    if not col:
        raise ValueError("Invalid column name")
    # Lineage is optional: a column may be documented in the registry / DDL
    # even when no lineage artifact exists for its table (L7 catalog, F2/F5).
    # Missing lineage is not an error; found is true when lineage, COMMENT, or
    # entity enrichment is present so agents do not treat documented columns
    # as missing.
    try:
        artifact = load_table_lineage(tbl, repo_root=repo_root)
    except FileNotFoundError:
        artifact = {}
    info = artifact.get("columns", {}).get(col)
    if info and isinstance(info, dict):
        # Enrich sources and step sources with traversal pointers.
        if "sources" in info:
            info["sources"] = _enrich_sources_with_links(info.get("sources"), repo_root=repo_root)
        steps = info.get("steps")
        if isinstance(steps, list):
            for st in steps:
                if isinstance(st, dict) and "sources" in st:
                    st["sources"] = _enrich_sources_with_links(st.get("sources"), repo_root=repo_root)
    enrichment = _registry_enrichment(tbl, col, repo_root=repo_root)
    documented = bool(enrichment.get("comment") or enrichment.get("entity"))

    aggregated_caveats, inherited_math = aggregate_column_caveats(tbl, col, repo_root=repo_root)
    local_caveats = info.get("caveats", []) if isinstance(info, dict) else []
    local_math = info.get("math") if isinstance(info, dict) else None

    # Prefer substantive formula over bare single-token projection
    active_math = local_math
    substantive_tokens = ("\\frac", "\\text{Rank}", "\\text{SMA}", "\\cdot", "+", "-", "/")
    if inherited_math and (not active_math or not any(tok in active_math.get("latex", "") for tok in substantive_tokens)):
        active_math = inherited_math

    result = {
        "table": tbl,
        "column": col,
        "found": info is not None or documented,
        "lineage": info,
        "caveats": aggregated_caveats or local_caveats,
        "math": active_math,
        "transform_path": artifact.get("transform_path", ""),
        "version": artifact.get("version", 0),
    }
    result.update(enrichment)
    return result


def explain_column_graph(
    table: str,
    column: str,
    *,
    max_depth: int = 4,
    max_nodes: int = 50,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Recursively explain a column by traversing lineage sources into a bounded DAG."""
    tbl = _validate_table(table)
    col = column.strip()
    root = {"table": tbl, "column": col}

    if not has_table_lineage(tbl, repo_root=repo_root):
        # Even without lineage JSON, return documented column if present
        direct = explain_column(tbl, col, repo_root=repo_root)
        if direct.get("found"):
            return {
                "root": root,
                "caveats": direct.get("caveats", []),
                "math": direct.get("math"),
                "nodes": [direct],
                "edges": [],
                "truncated": False,
            }
        return {"root": root, "caveats": [], "math": None, "nodes": [], "edges": [], "truncated": False}

    nodes: dict[str, Any] = {}
    edges: list[dict[str, str]] = []
    queue: list[tuple[str, str, int]] = [(tbl, col, 0)]

    def key(t: str, c: str) -> str:
        return f"{t}.{c}"

    def iter_sources(ex: dict[str, Any]) -> list[dict[str, Any]]:
        lin = ex.get("lineage") or {}
        if not isinstance(lin, dict):
            return []
        out: list[dict[str, Any]] = []
        srcs = lin.get("sources")
        if isinstance(srcs, list):
            out.extend([s for s in srcs if isinstance(s, dict)])
        steps = lin.get("steps")
        if isinstance(steps, list):
            for st in steps:
                if isinstance(st, dict):
                    s2 = st.get("sources")
                    if isinstance(s2, list):
                        out.extend([s for s in s2 if isinstance(s, dict)])
        return out

    while queue and len(nodes) < max_nodes:
        t, c, d = queue.pop(0)
        k = key(t, c)
        if k in nodes:
            continue
        ex = explain_column(t, c, repo_root=repo_root)
        nodes[k] = ex
        if d >= max_depth:
            continue
        for s in iter_sources(ex):
            st = str(s.get("table") or "")
            sc = str(s.get("column") or "")
            if not st or not sc:
                continue
            edges.append({"from": k, "to": key(st, sc)})
            if has_table_lineage(st, repo_root=repo_root):
                queue.append((st, sc, d + 1))

    truncated = bool(queue) or (len(nodes) >= max_nodes)
    root_key = key(tbl, col)
    root_node = nodes.get(root_key, {})
    return {
        "root": root,
        "caveats": root_node.get("caveats", []),
        "math": root_node.get("math"),
        "nodes": list(nodes.values()),
        "edges": edges,
        "truncated": truncated,
    }
