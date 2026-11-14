"""Authored PipelineDocument patch ops (C-SCREEN-PROBE-V1 agent loop)."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class SpecConflictError(ValueError):
    """expected_hash does not match current ir_content_hash."""


def content_hash(spec_json: str) -> str:
    return hashlib.sha256(spec_json.encode("utf-8")).hexdigest()


def _find_stage(pipeline: dict[str, Any], binding_id: str) -> dict[str, Any]:
    bid = (binding_id or "").strip()
    if not bid:
        raise ValueError("binding_id is required")
    for stage in pipeline.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        sid = str(stage.get("id") or "").strip()
        if not sid:
            sid = str(stage.get("name") or "").lower().replace(" ", "_")
        if sid == bid or (bid == "setup_pass" and sid in ("setup_pass", "setup_group")):
            return stage
    raise ValueError(f"unknown binding_id: {bid!r}")


def _walk_conditions(nodes: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if "logic" in node and "conditions" in node:
            out.extend(_walk_conditions(list(node.get("conditions") or [])))
        elif "op" in node:
            out.append(node)
    return out


def _require_rationale(annotation: dict[str, Any] | None) -> dict[str, Any]:
    ann = dict(annotation or {})
    rationale = str(ann.get("rationale") or "").strip()
    if not rationale:
        raise ValueError("each op requires annotation.rationale")
    ann.setdefault("source", "agent")
    ann.setdefault("at", datetime.now(timezone.utc).isoformat())
    ann["rationale"] = rationale
    return ann


def apply_pipeline_ops(
    pipeline: dict[str, Any],
    ops: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply structured ops; return (patched_pipeline, changelog)."""
    doc = copy.deepcopy(pipeline)
    changelog: list[dict[str, Any]] = []
    for i, raw in enumerate(ops or []):
        if not isinstance(raw, dict):
            raise ValueError(f"ops[{i}] must be an object")
        action = str(raw.get("op") or raw.get("action") or "").strip()
        binding_id = str(raw.get("binding_id") or "").strip()
        stage = _find_stage(doc, binding_id)
        filters = list(stage.get("filters") or [])
        if not filters:
            # Ensure a root AND group for leaf conditions.
            filters = [{"logic": "and", "conditions": []}]
            stage["filters"] = filters
        root = filters[0] if isinstance(filters[0], dict) and "conditions" in filters[0] else None
        if root is None:
            root = {"logic": "and", "conditions": filters}
            stage["filters"] = [root]
        conditions = list(root.get("conditions") or [])
        ann = _require_rationale(raw.get("annotation") if isinstance(raw.get("annotation"), dict) else None)

        if action == "add_condition":
            cond = raw.get("condition")
            if not isinstance(cond, dict):
                raise ValueError(f"ops[{i}].condition required for add_condition")
            cond = copy.deepcopy(cond)
            cond["annotation"] = {**ann, "action": "added"}
            if not cond.get("id"):
                cond["id"] = f"f-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{i}"
            conditions.append(cond)
            changelog.append({"op": action, "binding_id": binding_id, "id": cond["id"], "rationale": ann["rationale"]})
        elif action == "replace_condition":
            cid = str(raw.get("condition_id") or "").strip()
            cond = raw.get("condition")
            if not cid or not isinstance(cond, dict):
                raise ValueError(f"ops[{i}] replace_condition needs condition_id + condition")
            found = False
            for j, node in enumerate(conditions):
                if isinstance(node, dict) and str(node.get("id") or "") == cid:
                    new_c = copy.deepcopy(cond)
                    new_c["id"] = cid
                    new_c["annotation"] = {**ann, "action": "modified"}
                    conditions[j] = new_c
                    found = True
                    break
            if not found:
                # Also search nested groups
                leaves = _walk_conditions(conditions)
                match = next((c for c in leaves if str(c.get("id") or "") == cid), None)
                if match is None:
                    raise ValueError(f"condition_id not found: {cid!r}")
                match.clear()
                match.update(copy.deepcopy(cond))
                match["id"] = cid
                match["annotation"] = {**ann, "action": "modified"}
            changelog.append({"op": action, "binding_id": binding_id, "id": cid, "rationale": ann["rationale"]})
        elif action == "remove_condition":
            cid = str(raw.get("condition_id") or "").strip()
            if not cid:
                raise ValueError(f"ops[{i}] remove_condition needs condition_id")
            before = len(conditions)
            conditions = [
                n for n in conditions if not (isinstance(n, dict) and str(n.get("id") or "") == cid)
            ]
            if len(conditions) == before:
                # nested — mark changelog only if found in walk
                leaves = _walk_conditions(list(root.get("conditions") or []))
                if not any(str(c.get("id") or "") == cid for c in leaves):
                    raise ValueError(f"condition_id not found: {cid!r}")
                # shallow remove only for v1 nested: rebuild by filtering walk is complex;
                # require top-level for remove in v1.
                raise ValueError("remove_condition currently supports top-level conditions only")
            changelog.append(
                {
                    "op": action,
                    "binding_id": binding_id,
                    "id": cid,
                    "rationale": ann["rationale"],
                    "action": "removed",
                }
            )
            docs = dict(stage.get("documentation") or {})
            cl = list(docs.get("filter_changelog") or [])
            cl.append(
                {
                    "id": cid,
                    "rationale": ann["rationale"],
                    "at": ann.get("at"),
                    "action": "removed",
                }
            )
            docs["filter_changelog"] = cl[-20:]
            stage["documentation"] = docs
        else:
            raise ValueError(f"unknown op: {action!r} (add_condition|replace_condition|remove_condition)")

        root["conditions"] = conditions
        stage["filters"] = [root]

    return doc, changelog


def compile_and_hash(pipeline: dict[str, Any]) -> tuple[dict[str, Any], str]:
    from sigmarail_spec.strategy import compile_pipeline
    from sigmarail_spec.strategy.pipeline import PipelineDocument

    doc = PipelineDocument.model_validate(pipeline)
    spec = compile_pipeline(doc)
    # Keep previews spec-truthful: materialize the generated Swing ladder and
    # PCM allocation table so the hash/preview match what save will persist
    # (no-op without vera_lab).
    try:
        from screens.pcm_rules import materialize_pcm_rules
        from screens.risk_rules import materialize_swing_risk_rules

        materialize_swing_risk_rules(spec)
        materialize_pcm_rules(spec)
    except Exception:
        pass
    spec_json = json.dumps(spec, separators=(",", ":"), sort_keys=True)
    return spec, content_hash(spec_json)


__all__ = [
    "SpecConflictError",
    "apply_pipeline_ops",
    "compile_and_hash",
    "content_hash",
]
