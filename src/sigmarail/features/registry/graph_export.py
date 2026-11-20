"""Deterministic graph projection from registry + rules manifest + decisions.

Writes ``registry/graph.json`` (git artifact, like ``compiled.json``). A thin
loader pushes the artifact into ClickHouse ``graph_nodes`` / ``graph_edges``.
Gate tools never read these tables — the graph describes, code decides.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sigmarail.features.gate_tools import ENTRY_GATE_RULES_PATH, load_entry_gate_rules

from .compile import load_compiled

GRAPH_ARTIFACT_RELATIVE = "registry/graph.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def graph_artifact_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / GRAPH_ARTIFACT_RELATIVE


def dumps(graph: dict[str, Any]) -> str:
    return json.dumps(graph, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _metric_node_id(metric: str) -> str:
    return f"vera.metric.{metric}"


def _domain_for_kind(kind: str | None) -> str:
    if kind == "adm_entity":
        return "platform"
    if kind == "concept":
        return "tech"
    return "platform"


def _collect_metrics(rule: dict[str, Any]) -> list[str]:
    metrics: list[str] = []
    for cond in rule.get("all") or []:
        if isinstance(cond, dict) and cond.get("metric"):
            metrics.append(str(cond["metric"]))
    aw = rule.get("applies_when")
    if isinstance(aw, dict) and aw.get("metric"):
        metrics.append(str(aw["metric"]))
    elif isinstance(aw, list):
        for cond in aw:
            if isinstance(cond, dict) and cond.get("metric"):
                metrics.append(str(cond["metric"]))
    lb = rule.get("lookback") or {}
    for key in ("any_row", "none_row"):
        for cond in lb.get(key) or []:
            if isinstance(cond, dict) and cond.get("metric"):
                metrics.append(str(cond["metric"]))
    # preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for m in metrics:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def build_graph(
    *,
    compiled: dict[str, Any] | None = None,
    rules_manifest: dict[str, Any] | None = None,
    decisions_index: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Pure projection → {nodes, edges} dicts. Offline, no ClickHouse."""
    root = repo_root or _repo_root()
    compiled = compiled if compiled is not None else (load_compiled(root) or {"entities": {}})
    rules_manifest = rules_manifest if rules_manifest is not None else load_entry_gate_rules()

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(**kwargs: Any) -> None:
        nid = kwargs["node_id"]
        nodes[nid] = kwargs

    def add_edge(**kwargs: Any) -> None:
        edges.append(kwargs)

    # Registry entities
    for eid, ent in sorted((compiled.get("entities") or {}).items()):
        kind = ent.get("kind") or "concept"
        add_node(
            node_id=eid,
            domain=_domain_for_kind(kind),
            node_type="adm_entity" if kind == "adm_entity" else kind,
            label=ent.get("title") or eid,
            source_type="registry",
            source_ref=ent.get("_sidecar") or ent.get("_source") or "",
            payload={
                "computability": ent.get("computability") or "narrative_only",
                "definition": ent.get("definition") or "",
            },
        )
        adm = ent.get("adm") or {}
        for table in adm.get("tables") or []:
            add_edge(
                src_id=eid,
                edge_type="binds_to",
                dst_id=f"vera.table.{table}",
                domain="platform",
                evidence="",
                source_type="registry",
                source_ref=ent.get("_sidecar") or "",
                confidence=1.0,
            )
            add_node(
                node_id=f"vera.table.{table}",
                domain="platform",
                node_type="adm_entity",
                label=str(table),
                source_type="registry",
                source_ref=ent.get("_sidecar") or "",
                payload={},
            )
        for tool in ent.get("tools") or []:
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            tname = str(tool["name"])
            add_node(
                node_id=f"vera.tool.{tname}",
                domain="platform",
                node_type="tool",
                label=tname,
                source_type="registry",
                source_ref=ent.get("_sidecar") or "",
                payload={"role": tool.get("role"), "note": tool.get("note") or ""},
            )
            add_edge(
                src_id=eid,
                edge_type="enforced_by" if tool.get("role") == "gate" else "binds_to",
                dst_id=f"vera.tool.{tname}",
                domain="platform",
                evidence=tool.get("note") or "",
                source_type="registry",
                source_ref=ent.get("_sidecar") or "",
                confidence=1.0,
            )

    # Entry gate rules
    for rule in rules_manifest.get("rules") or []:
        rid = rule["id"]
        add_node(
            node_id=rid,
            domain="platform",
            node_type="rule",
            label=rule.get("summary") or rid,
            source_type="rules_manifest",
            source_ref=str(ENTRY_GATE_RULES_PATH.name),
            payload={
                "order": rule.get("order"),
                "outcome": rule.get("outcome"),
                "terminal": rule.get("terminal"),
                "constraints": rule.get("constraints"),
                "applies_when": rule.get("applies_when"),
                "provenance": rule.get("provenance"),
            },
        )
        add_edge(
            src_id=rid,
            edge_type="enforced_by",
            dst_id="vera.tool.evaluate_entry_gate",
            domain="platform",
            evidence="",
            source_type="rules_manifest",
            source_ref=str(ENTRY_GATE_RULES_PATH.name),
            confidence=1.0,
        )
        add_node(
            node_id="vera.tool.evaluate_entry_gate",
            domain="platform",
            node_type="tool",
            label="evaluate_entry_gate",
            source_type="rules_manifest",
            source_ref=str(ENTRY_GATE_RULES_PATH.name),
            payload={"role": "gate"},
        )
        for metric in _collect_metrics(rule):
            mid = _metric_node_id(metric)
            add_node(
                node_id=mid,
                domain="market",
                node_type="metric",
                label=metric,
                source_type="rules_manifest",
                source_ref=str(ENTRY_GATE_RULES_PATH.name),
                payload={"table": rules_manifest.get("source_table") or "market_regime_signals_daily"},
            )
            add_edge(
                src_id=rid,
                edge_type="evaluates",
                dst_id=mid,
                domain="market",
                evidence="",
                source_type="rules_manifest",
                source_ref=str(ENTRY_GATE_RULES_PATH.name),
                confidence=1.0,
            )

    # Decisions index (best-effort; FinanceProjects monorepo path)
    decisions_path = decisions_index
    if decisions_path is None:
        # VeraBase/ -> FinanceProjects/docs/decisions/index.md
        candidate = root.parent / "docs" / "decisions" / "index.md"
        if candidate.is_file():
            decisions_path = candidate
    if decisions_path and decisions_path.is_file():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("|") or "decision_id" in line.lower() or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if not parts:
                continue
            did = parts[0].strip("` ")
            if not did or did.lower() in {"id", "decision id", "slice"}:
                continue
            # Skip header-ish rows
            if " " in did and not did[0].isdigit() and "202" not in did:
                continue
            nid = f"vera.decision.{did}"
            add_node(
                node_id=nid,
                domain="platform",
                node_type="decision",
                label=did,
                source_type="decisions",
                source_ref=str(decisions_path.as_posix()),
                payload={"row": parts},
            )
            # Contract / slice refs when present in later columns
            for cell in parts[1:]:
                cell = cell.strip("` ")
                if cell.startswith("C-") or cell.startswith("kb-") or cell.startswith("vera-"):
                    dst = f"vera.contract.{cell}" if cell.startswith("C-") else f"vera.slice.{cell}"
                    add_node(
                        node_id=dst,
                        domain="platform",
                        node_type="contract" if cell.startswith("C-") else "decision",
                        label=cell,
                        source_type="decisions",
                        source_ref=str(decisions_path.as_posix()),
                        payload={},
                    )
                    add_edge(
                        src_id=nid,
                        edge_type="decided_in",
                        dst_id=dst,
                        domain="platform",
                        evidence="",
                        source_type="decisions",
                        source_ref=str(decisions_path.as_posix()),
                        confidence=1.0,
                    )

    # Deterministic sort
    node_list = [nodes[k] for k in sorted(nodes)]
    edge_list = sorted(edges, key=lambda e: (e["src_id"], e["edge_type"], e["dst_id"]))
    return {
        "generated": True,
        "generator": "vera-registry-graph-export",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nodes": node_list,
        "edges": edge_list,
    }


def write_graph(graph: dict[str, Any], repo_root: Path | None = None) -> Path:
    # Drop volatile timestamp for git stability when content otherwise equal —
    # keep generated_at but sort so --check compares structure.
    out = graph_artifact_path(repo_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Stable: omit generated_at from the committed byte stream comparison by
    # writing a frozen copy without the wall-clock field.
    stable = {k: v for k, v in graph.items() if k != "generated_at"}
    out.write_text(dumps(stable), encoding="utf-8")
    return out


def load_graph_artifact(repo_root: Path | None = None) -> dict[str, Any] | None:
    p = graph_artifact_path(repo_root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_graph_drift(repo_root: Path | None = None) -> list[str]:
    root = repo_root or _repo_root()
    fresh = dumps({k: v for k, v in build_graph(repo_root=root).items() if k != "generated_at"})
    p = graph_artifact_path(root)
    if not p.is_file():
        return [f"missing {p.relative_to(root).as_posix()} (run: vera-registry graph-export)"]
    if p.read_text(encoding="utf-8") != fresh:
        return ["registry/graph.json is stale (run: vera-registry graph-export and commit)"]
    return []


def load_graph_into_clickhouse(client: Any, graph: dict[str, Any] | None = None, *, repo_root: Path | None = None) -> dict[str, int]:
    """Thin CH loader — inserts artifact rows; ReplacingMergeTree absorbs re-exports."""
    g = graph or load_graph_artifact(repo_root) or build_graph(repo_root=repo_root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    node_rows = []
    for n in g.get("nodes") or []:
        node_rows.append(
            [
                n["node_id"],
                n.get("domain") or "platform",
                n.get("node_type") or "concept",
                n.get("label") or "",
                n.get("source_type") or "",
                n.get("source_ref") or "",
                json.dumps(n.get("payload") or {}, sort_keys=True),
                now,
            ]
        )
    edge_rows = []
    for e in g.get("edges") or []:
        edge_rows.append(
            [
                e["src_id"],
                e["edge_type"],
                e["dst_id"],
                e.get("domain") or "platform",
                e.get("evidence") or "",
                e.get("source_type") or "",
                e.get("source_ref") or "",
                "1970-01-01 00:00:00",
                float(e.get("confidence") or 1.0),
                now,
            ]
        )
    if node_rows:
        client.insert(
            "graph_nodes",
            node_rows,
            column_names=[
                "node_id",
                "domain",
                "node_type",
                "label",
                "source_type",
                "source_ref",
                "payload",
                "updated_at",
            ],
        )
    if edge_rows:
        client.insert(
            "graph_edges",
            edge_rows,
            column_names=[
                "src_id",
                "edge_type",
                "dst_id",
                "domain",
                "evidence",
                "source_type",
                "source_ref",
                "observed_at",
                "confidence",
                "updated_at",
            ],
        )
    return {"nodes": len(node_rows), "edges": len(edge_rows)}
