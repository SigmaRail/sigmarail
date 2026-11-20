"""
Discover Lean ``Algorithm.Framework`` Python class names, slots, and init signatures (AST-only).

Does **not** import ``AlgorithmImports`` or execute Lean. Requires a checkout of the **Lean** repo
(``LEAN_ROOT`` / ``<workspace>/Lean``) on disk. ``sigmarail_lab_wired`` and ``pydantic_validated`` use
``sigmarail_lab`` registries; see :func:`lean_framework_v1_pydantic_type_ids` and
:func:`sigmarail_lab.runtime.lean_framework_interpreter.all_default_wirable_type_ids`.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .lean_framework_parameters import lean_framework_v1_pydantic_type_ids
from ..runtime.lean_framework_interpreter import all_default_wirable_type_ids

_BASE_ID_TO_SLOT: dict[str, str] = {
    "AlphaModel": "Alpha",
    "PortfolioConstructionModel": "PortfolioConstruction",
    "ExecutionModel": "Execution",
    "RiskManagementModel": "RiskManagement",
    "UniverseSelectionModel": "UniverseSelection",
}


@dataclass
class _ScanResult:
    type_id: str
    slot: str
    relpath: str
    description: str
    init_parameters: list[dict[str, Any]]
    json_param_ok: bool
    class_lineno: int
    init_doc: str = ""
    init_lineno: int = 0


def _class_description(node: ast.ClassDef) -> str:
    doc = ast.get_docstring(node)
    if doc:
        return " ".join(doc.strip().split())
    return ""


def _init_info(node: ast.ClassDef) -> tuple[ast.FunctionDef | None, int]:
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return item, item.lineno
    return None, 0


def _id_from_expr(n: ast.expr) -> str | None:
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
        return n.attr
    if isinstance(n, ast.Subscript) and isinstance(n.value, (ast.Name, ast.Attribute)):
        if isinstance(n.value, ast.Name):
            return n.value.id
        return n.value.attr
    return None


def _match_slot(bases: list[ast.expr]) -> str | None:
    for b in bases:
        name = _id_from_expr(b)
        if not name:
            continue
        if name in _BASE_ID_TO_SLOT:
            return _BASE_ID_TO_SLOT[name]
        for base_id, slot in _BASE_ID_TO_SLOT.items():
            if name == base_id or name.endswith(base_id):
                return slot
    return None


def _param_entry(arg: str, dflt: bool, ann: ast.expr | None) -> dict[str, Any]:
    e: dict[str, Any] = {
        "name": arg,
        "has_default": dflt,
    }
    if ann is not None:
        try:
            e["annotation"] = ast.unparse(ann)  # type: ignore[attr-defined]
        except AttributeError:
            e["annotation"] = "?"
    return e


def _init_json_ok(init: ast.FunctionDef | None) -> bool:
    if init is None:
        return True
    a = init.args
    if a.vararg is not None or a.kwarg is not None:
        return False
    return True


def _init_parameters_list(init: ast.FunctionDef | None) -> list[dict[str, Any]]:
    if init is None:
        return []
    a = init.args
    args_n = a.args
    n_defaults = len(a.defaults)
    first = 1 if (args_n and args_n[0].arg in ("self", "cls")) else 0
    pos = args_n[first:]
    n_pos = len(pos)
    params: list[dict[str, Any]] = []
    for i, arg in enumerate(pos):
        has_default = bool(n_defaults) and (i >= (n_pos - n_defaults))
        params.append(_param_entry(arg.arg, has_default, arg.annotation))
    kdefs = a.kw_defaults
    for j, k in enumerate(a.kwonlyargs):
        dflt = bool(j < len(kdefs) and kdefs[j] is not None)
        params.append(_param_entry(k.arg, dflt, k.annotation))
    return params


def _scan_py(path: Path, rel_root: Path) -> list[_ScanResult]:
    out: list[_ScanResult] = []
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return out
    if not re.search(r"^class\s+\w+", src, re.M):
        return out
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return out
    relp = path.relative_to(rel_root).as_posix()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name.startswith("_"):
            continue
        slot = _match_slot(node.bases)
        if not slot:
            continue
        init, init_ln = _init_info(node)
        j_ok = _init_json_ok(init)
        params = _init_parameters_list(init)
        if init and init.name == "__init__":
            idoc = ast.get_docstring(init) or ""
        else:
            idoc = ""
        out.append(
            _ScanResult(
                type_id=node.name,
                slot=slot,
                relpath=relp,
                description=_class_description(node),
                init_parameters=params,
                json_param_ok=j_ok,
                class_lineno=node.lineno,
                init_doc=" ".join(idoc.strip().split()) if idoc else "",
                init_lineno=init_ln,
            )
        )
    return out


def _iter_framework_py_files(lean_root: Path) -> Iterator[Path]:
    subdirs = [
        lean_root / "Algorithm.Framework" / s
        for s in ("Alphas", "Portfolio", "Execution", "Risk", "Selection")
    ] + [lean_root / "Algorithm" / s for s in ("Selection", "Execution", "Risk", "Alphas", "Portfolio")]
    for sub in subdirs:
        if not sub.is_dir():
            continue
        for p in sorted(sub.rglob("*.py")):
            if p.name.startswith("_"):
                continue
            if "__pycache__" in p.parts:
                continue
            yield p


def _resolve_lean_root(lean_root: Path | str | None) -> Path | None:
    if lean_root is not None:
        p = Path(lean_root).expanduser().resolve()
        return p if p.is_dir() and (p / "Algorithm.Framework").is_dir() else None
    e = (os.environ.get("LEAN_ROOT") or "").strip()
    if e:
        p = Path(e).expanduser().resolve()
        if p.is_dir() and (p / "Algorithm.Framework").is_dir():
            return p
    here = Path(__file__).resolve()
    for anc in [here, *list(here.parents)]:
        cand = anc / "Lean"
        if (cand / "Algorithm.Framework").is_dir():
            return cand
    return None


def _vera_screener_extension_entries() -> list[dict[str, Any]]:
    from . import sigmarail_screener_framework_types as t

    def row(type_id: str, slot: str, desc: str) -> dict[str, Any]:
        return {
            "type_id": type_id,
            "slot": slot,
            "source": "vera_screener",
            "relpath": "sigmarail_lab/ir/sigmarail_screener_framework_types.py",
            "description": desc,
            "init_parameters": [],
            "json_param_ok": True,
            "class_doc": desc,
            "class_lineno": 0,
            "init_doc": "",
            "init_lineno": 0,
        }

    rows: list[dict[str, Any]] = [
        (
            t.UNIVERSE_SELECTION,
            "UniverseSelection",
            "Screener-backed universe (Vera/ClickHouse store; see SigmaRailFrameworkStore).",
        ),
        (t.ALPHA, "Alpha", "Screener-backed alpha; parameters forwarded to the Vera plugin model."),
        (
            t.PORTFOLIO_CONSTRUCTION,
            "PortfolioConstruction",
            "Screener-backed portfolio construction; parameters for the Vera plugin.",
        ),
        (t.EXECUTION, "Execution", "Screener-backed execution model; often paired with manual rebalance OHLC injection."),
    ]
    ext: list[dict[str, Any]] = [row(sid, sl, d) for sid, sl, d in rows]
    for legacy, slot, d in [
        (t.LEGACY_UNIVERSE_SCREENER_STORE, "UniverseSelection", "Legacy ScreenerStore* id; prefer VeraScreener*."),
        (t.LEGACY_UNIVERSE_CLICKHOUSE, "UniverseSelection", "Legacy ClickHouse* id; prefer VeraScreener*."),
        (t.LEGACY_ALPHA_SCREENER_STORE, "Alpha", "Legacy ScreenerStore* id."),
        (t.LEGACY_ALPHA_CLICKHOUSE, "Alpha", "Legacy ClickHouse* id."),
        (t.LEGACY_PORTFOLIO_SCREENER_STORE, "PortfolioConstruction", "Legacy ScreenerStore* id."),
        (t.LEGACY_PORTFOLIO_CLICKHOUSE, "PortfolioConstruction", "Legacy ClickHouse* id."),
        (t.LEGACY_EXECUTION_SCREENER_STORE, "Execution", "Legacy ScreenerStore* id."),
        (t.LEGACY_EXECUTION_CLICKHOUSE, "Execution", "Legacy ClickHouse* id."),
    ]:
        r = row(legacy, slot, d)
        ext.append(r)
    return ext


def discover_lean_framework_types(
    *,
    lean_root: Path | str | None = None,
    slot: str | None = None,
    include_unwired: bool = True,
    include_vera_screener_ids: bool = True,
) -> dict[str, Any]:
    """
    Return JSON-serializable dict of Lean framework class types + Vera extension type ids.

    * ``pydantic_validated``: in :func:`lean_framework_v1_pydantic_type_ids`
    * ``sigmarail_lab_wired``: in :func:`sigmarail_lab.runtime.lean_framework_interpreter.all_default_wirable_type_ids`
    """

    pydantic_ids = lean_framework_v1_pydantic_type_ids()
    wired = all_default_wirable_type_ids()
    warnings: list[str] = []
    lean_path = _resolve_lean_root(lean_root)
    entries: list[dict[str, Any]] = []
    if lean_path is not None:
        for py in _iter_framework_py_files(lean_path):
            for s in _scan_py(py, lean_path):
                tid = s.type_id
                ent = {
                    "type_id": tid,
                    "slot": s.slot,
                    "source": "lean",
                    "relpath": s.relpath,
                    "description": s.description,
                    "class_doc": s.description,
                    "class_lineno": s.class_lineno,
                    "init_doc": s.init_doc,
                    "init_lineno": s.init_lineno,
                    "init_parameters": s.init_parameters,
                    "json_param_ok": s.json_param_ok,
                    "pydantic_validated": tid in pydantic_ids,
                    "sigmarail_lab_wired": tid in wired,
                }
                entries.append(ent)
    else:
        warnings.append(
            "Lean source tree not found (set LEAN_ROOT or run from a workspace with sibling "
            "``Lean/Algorithm.Framework``). Only Vera screener extension types are listed for Lean rows."
        )

    if include_vera_screener_ids:
        for ex in _vera_screener_extension_entries():
            tid = ex["type_id"]
            ex2 = {**ex, "pydantic_validated": tid in pydantic_ids, "sigmarail_lab_wired": tid in wired}
            entries.append(ex2)

    if slot is not None:
        sl = slot.strip()
        if sl:
            entries = [e for e in entries if e["slot"].casefold() == sl.casefold()]

    if not include_unwired:
        entries = [e for e in entries if e.get("sigmarail_lab_wired") is True]

    # Stable sort: slot, then type_id
    entries.sort(key=lambda x: (x.get("slot", ""), x.get("type_id", "")))

    return {
        "ok": True,
        "lean_root": str(lean_path) if lean_path is not None else None,
        "pydantic_validated_type_ids": sorted(pydantic_ids),
        "sigmarail_lab_wired_type_ids": sorted(wired),
        "types": entries,
        "count": len(entries),
        "warnings": warnings,
    }
