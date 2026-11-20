#!/usr/bin/env python3
"""Build deterministic, source-derived SigmaRail contract artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
LOCK_PATH = ROOT / "spec" / "sources.lock.json"
OUTPUT_ROOT = ROOT / "src" / "sigmarail_spec" / "data"

SOURCES: dict[str, dict[str, Any]] = {
    "sigmarail": {
        "path": ".",
        "paths": ["tools/generate_lineage_manifest.py", "src/sigmarail/query.py", "src/sigmarail/universe.py", "src/sigmarail/sql/schema-manifest.json", "src/sigmarail/sql/schema", "spec/lineage-manifest.json", "src/sigmarail/spec/module-manifest.json"],
        "git": False,
    },
    "trading_lab": {
        "path": ".",
        "paths": [
            "src/sigmarail_lab/ir",
            "src/sigmarail_lab/runtime",
            "src/sigmarail_lab/lean",
            "trading_lab/main.py",
        ],
        "git": False,
    },
    "lean": {
        "path": "Lean",
        "paths": [
            "Algorithm.Framework/Alphas", "Algorithm.Framework/Portfolio",
            "Algorithm.Framework/Execution", "Algorithm.Framework/Risk",
            "Algorithm.Framework/Selection", "Algorithm/Selection", "Algorithm/Execution",
            "Algorithm/Risk", "Algorithm/Alphas", "Algorithm/Portfolio",
        ],
        "git": True,
    },
    "studio": {
        "path": ".",
        "paths": ["studio/api/lean_universe.py", "studio/config/urls.py", "studio/sigmarail_studio_mcp/domains/strategy.py", "studio/sigmarail_studio_mcp/domains/core.py", "studio/sigmarail_studio_mcp/server.py", "studio/sigmarail_studio_mcp/data/module-catalog.json", "studio/AGENTS.md"],
        "git": False,
    },
}

MCP_TOOL_DOMAINS = {
    "data_query": ("core_",),
    "screening": ("screen_",),
    "strategy_authoring": ("strategy_", "lean_discover_types"),
    "backtesting": ("backtest_", "regime_", "optimize_"),
    "live_deployment": ("deploy_",),
    "studio": ("chart_", "studio_"),
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _hash_files(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    excluded_dirs = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
    for item in sorted(paths):
        path = root / item
        if not path.exists():
            raise FileNotFoundError(f"locked source path is absent: {path}")
        candidates = (
            sorted(
                p for p in path.rglob("*")
                if p.is_file()
                and not any(part in excluded_dirs for part in p.relative_to(path).parts)
                and p.suffix != ".pyc"
                and ".egg-info" not in p.parts
            )
            if path.is_dir() else [path]
        )
        for candidate in candidates:
            rel = candidate.relative_to(root).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _git_revision(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_lock(workspace: Path, lean_root: Path) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for key, cfg in SOURCES.items():
        source_root = lean_root if key == "lean" else workspace
        rows[key] = {
            "path": cfg["path"],
            "revision": _git_revision(source_root) if cfg["git"] else None,
            "content_sha256": _hash_files(source_root, cfg["paths"]),
            "hashed_paths": cfg["paths"],
        }
    return {"lock_version": 1, "sources": rows}


def verify_lock(workspace: Path, lean_root: Path, expected: dict[str, Any]) -> None:
    actual = source_lock(workspace, lean_root)
    for key, row in actual["sources"].items():
        pinned = expected.get("sources", {}).get(key)
        if not pinned:
            raise ValueError(f"source lock is missing {key}")
        if pinned.get("path") != row["path"]:
            raise ValueError(f"source lock path changed for {key}")
        if pinned.get("revision") != row["revision"]:
            raise ValueError(
                f"source revision drift for {key}: locked={pinned.get('revision')!r}, current={row['revision']!r}; review and refresh the lock"
            )
        if pinned.get("content_sha256") != row["content_sha256"]:
            raise ValueError(f"source content drift for {key}; review and refresh the lock")


def _sigmarail_lineage(workspace: Path) -> dict[str, Any]:
    """Run the existing SigmaRail generator in a disposable copy, never in its checkout."""
    source = workspace
    with tempfile.TemporaryDirectory(prefix="sigmarail-spec-sql-") as temp:
        temp_root = Path(temp)
        shutil.copytree(source / "src/sigmarail/sql/schema", temp_root / "src/sigmarail/sql/schema")
        shutil.copy2(source / "src/sigmarail/sql/schema-manifest.json", temp_root / "src/sigmarail/sql/schema-manifest.json")
        (temp_root / "tools").mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "tools/generate_lineage_manifest.py", temp_root / "tools/generate_lineage_manifest.py")
        run = subprocess.run(
            [sys.executable, str(temp_root / "tools/generate_lineage_manifest.py")],
            cwd=temp_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if run.returncode:
            raise RuntimeError(f"SigmaRail lineage generation failed:\n{run.stdout}\n{run.stderr}")
        return json.loads((temp_root / "spec/lineage-manifest.json").read_text(encoding="utf-8"))


def _annotation_json_schema(annotation: ast.expr | None) -> dict[str, Any]:
    """Translate the intentionally small annotation subset used by Studio MCP tools."""
    if annotation is None:
        return {}
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        arms = [_annotation_json_schema(annotation.left), _annotation_json_schema(annotation.right)]
        if any(arm.get("type") == "null" for arm in arms):
            return {"anyOf": arms}
        return {"anyOf": arms}
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return {"type": "null"}
    if isinstance(annotation, ast.Name):
        return {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "Any": {},
        }.get(annotation.id, {})
    if isinstance(annotation, ast.Subscript):
        base = ast.unparse(annotation.value)
        inner = annotation.slice
        if base in ("list", "List", "Sequence"):
            return {"type": "array", "items": _annotation_json_schema(inner)}
        if base in ("dict", "Dict", "Mapping"):
            value_annotation = inner.elts[1] if isinstance(inner, ast.Tuple) and len(inner.elts) == 2 else None
            value_schema = _annotation_json_schema(value_annotation)
            if value_schema == {}:
                value_schema = True
            return {
                "type": "object",
                "additionalProperties": value_schema,
            }
        if base in ("Optional", "Union") and isinstance(inner, ast.Tuple):
            return {"anyOf": [_annotation_json_schema(item) for item in inner.elts]}
    if isinstance(annotation, ast.Tuple):
        return {"anyOf": [_annotation_json_schema(item) for item in annotation.elts]}
    return {}


def _studio_mcp_tools(workspace: Path, data_query_schema: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Generate MCP tool contracts from Studio's decorated function signatures and docs."""
    path = workspace / "studio/sigmarail_studio_mcp/server.py"
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tools: dict[str, list[dict[str, Any]]] = {domain: [] for domain in MCP_TOOL_DOMAINS}
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tool_decorator = next(
            (decorator for decorator in node.decorator_list
             if isinstance(decorator, ast.Call)
             and isinstance(decorator.func, ast.Name)
             and decorator.func.id == "_tool"),
            None,
        )
        if tool_decorator is None or not tool_decorator.args or not isinstance(tool_decorator.args[0], ast.Constant):
            continue
        module_id = str(tool_decorator.args[0].value)
        # FastMCP skips the injected Context parameter from client-facing input schemas.
        args = [arg for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                if arg.arg not in ("self", "cls", "ctx", "context")]
        domain = next(
            (domain for domain, prefixes in MCP_TOOL_DOMAINS.items()
             if node.name.startswith(prefixes)),
            None,
        )
        if domain is None:
            continue

        positional_defaults = [None] * (len(node.args.posonlyargs) + len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
        defaults_by_name = {
            arg.arg: default for arg, default in zip(
                [*node.args.posonlyargs, *node.args.args], positional_defaults
            )
        }
        defaults_by_name.update(
            {arg.arg: default for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)}
        )
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg in args:
            if arg.arg in ("self", "cls"):
                continue
            schema = (
                data_query_schema
                if arg.annotation is not None and ast.unparse(arg.annotation) == "core.DataQueryV1"
                else _annotation_json_schema(arg.annotation)
            )
            schema["title"] = arg.arg.replace("_", " ").title()
            properties[arg.arg] = schema
            if arg.arg not in defaults_by_name:
                required.append(arg.arg)

        input_schema: dict[str, Any] = {
            "type": "object",
            "title": f"{node.name}Arguments",
            "properties": properties,
        }
        if required:
            input_schema["required"] = required
        output_schema = _annotation_json_schema(node.returns)
        if output_schema.get("type") == "object":
            output_schema.setdefault("title", f"{node.name}DictOutput")
            if output_schema.get("additionalProperties") is True:
                output_schema["description"] = "Object result; return keys depend on the operation and runtime data."
        tools[domain].append(
            {
                "id": f"studio.mcp.tool.{node.name}",
                "name": node.name,
                "module": module_id,
                "description": ast.get_docstring(node) or "",
                "input_schema": input_schema,
                "output_schema": output_schema,
            }
        )
    for entries in tools.values():
        entries.sort(key=lambda item: item["name"])
    return tools


def _load_entities(workspace: Path) -> dict[str, dict[str, Any]]:
    try:
        import yaml
    except ImportError:
        return {}
    root = workspace / "src/sigmarail/sql/schema"
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.entities.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in doc.get("entities") or []:
            binds = item.get("binds") or {}
            table, column = binds.get("table"), binds.get("column")
            if table and column:
                result[f"{table}.{column}"] = {
                    key: item[key] for key in ("id", "title", "definition", "kind", "computability") if key in item
                }
    return result


def _transforms(workspace: Path, lineage: dict[str, Any]) -> dict[str, Any]:
    schema_root = workspace / "src/sigmarail/sql/schema"
    tables = {table["name"]: table for table in lineage.get("tables", [])}
    records: list[dict[str, Any]] = []
    view_head = re.compile(
        r"(?is)CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>`?xform_[A-Za-z0-9_]+`?)\s*\((?P<columns>.*?)\)\s*COMMENT\s+'(?P<comment>(?:''|[^'])*)'\s*AS\b"
    )
    for path in sorted(schema_root.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        for match in view_head.finditer(sql):
            view = match.group("name").strip("`")
            meta = json.loads(match.group("comment").replace("''", "'"))
            target = str(meta["target"])
            table = tables.get(target)
            if table is None:
                raise ValueError(f"xform view {view} targets missing schema object {target}")
            columns = [re.sub(r"--[^\n]*", "", item).strip().strip("`") for item in match.group("columns").split(",")]
            columns = [item for item in columns if item]
            records.append(
                {
                    "id": f"sigmarail.transform.{target}",
                    "view": view,
                    "target": target,
                    "order": int(meta.get("order", 0)),
                    "inputs": sorted(set(meta.get("sources") or [])),
                    "outputs": columns,
                    "chunk_size": meta.get("chunk_size"),
                    "sql_file": path.relative_to(workspace).as_posix(),
                    "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                    "lineage_roots": table.get("sharadar_roots", []),
                    "source_list_verified_by_sigmarail_generator": True,
                }
            )
    return {"version": 1, "transforms": sorted(records, key=lambda row: (row["order"], row["target"]))}


def _source_models(workspace: Path, lean_root: Path) -> dict[str, Any]:
    """Load source Pydantic models from the locked checkout and export JSON schemas."""
    sys.path[:0] = [
        str(ROOT / "src"),
        str(workspace / "src"),
    ]
    from pydantic import TypeAdapter
    from sigmarail_spec.data_query import DataQueryV1
    import sigmarail_spec.expr as expr
    from sigmarail_spec.expr import BoolExprItem, SpecExpr
    from sigmarail_lab.ir.lean_framework_json import LeanFrameworkV1Document
    from sigmarail_lab.ir.sigmarail_lab_v1_json import VeraLabV1Document
    from sigmarail_lab.ir.runtime_param_table import payload as runtime_payload
    from sigmarail_lab.ir import sigmarail_screener_framework_types as screener_types
    from sigmarail_lab.ir.lean_framework_discovery import _scan_py, discover_lean_framework_types
    from sigmarail_spec.universe_query import UniverseQueryV1
    from sigmarail_spec.strategy import PipelineDocument

    classes: dict[str, type] = {}
    for value in vars(expr).values():
        fields = getattr(value, "model_fields", None)
        discriminator = fields.get("type") if fields else None
        name = getattr(discriminator, "default", None)
        if isinstance(name, str):
            classes[name] = value
    expressions = {
        "version": "C-VERA-EXPR-V1",
        "boolean_schema": TypeAdapter(BoolExprItem).json_schema(),
        "spec_schema": TypeAdapter(SpecExpr).json_schema(),
        "nodes": [
            {
                "id": f"expression.node.{name}",
                "type": name,
                "fields": list(cls.model_fields),
                "summary": ((cls.__doc__ or "").strip().splitlines() or [""])[0],
            }
            for name, cls in sorted(classes.items())
        ],
        "limits": {"max_boolean_depth": expr.MAX_BOOL_DEPTH, "max_formula_depth": expr.MAX_FORMULA_DEPTH},
    }
    runtime = runtime_payload()
    lean_types = discover_lean_framework_types(
        lean_root=lean_root, include_unwired=True
    )["types"]
    trading_lab_root = workspace
    trading_lab_types = []
    for path in sorted((trading_lab_root / "src/sigmarail_lab/runtime").rglob("*.py")):
        if path.name.startswith("_"):
            continue
        trading_lab_types.extend(_scan_py(path, trading_lab_root))
    slot_type_ids: dict[str, set[str]] = {
        "UniverseSelection": set(screener_types.ALLOWED_UNIVERSE_SELECTION_TYPES),
        "Alpha": set(screener_types.ALLOWED_ALPHA_TYPES),
        "PortfolioConstruction": set(screener_types.ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES),
        "RiskManagement": set(screener_types.ALLOWED_RISK_MANAGEMENT_TYPES),
        "Execution": set(screener_types.ALLOWED_EXECUTION_TYPES),
    }
    discovered_types = [
        (item["slot"], item["type_id"]) for item in lean_types
    ] + [
        (item.slot, item.type_id) for item in trading_lab_types
    ]
    for slot, type_id in discovered_types:
        if slot in slot_type_ids:
            slot_type_ids[slot].add(type_id)
    runtime_types = runtime["types"]
    slot_type_ids = {
        slot: ids & runtime_types.keys() for slot, ids in slot_type_ids.items()
    }
    classified_type_ids = set().union(*slot_type_ids.values())
    return {
        "expressions": expressions,
        "strategy": {
            "studio_authoring_schema": PipelineDocument.model_json_schema(),
            "lean_framework_schema": LeanFrameworkV1Document.model_json_schema(),
            "executable_strategy_schema": VeraLabV1Document.model_json_schema(),
            "universe_query_schema": UniverseQueryV1.model_json_schema(),
            "data_query_schema": DataQueryV1.model_json_schema(),
        },
        "runtime_capabilities": runtime,
        "runtime_types_by_slot": {
            slot: sorted(type_ids) for slot, type_ids in slot_type_ids.items()
        },
        "unclassified_runtime_type_ids": sorted(set(runtime_types) - classified_type_ids),
        "mcp_tools": _studio_mcp_tools(workspace, DataQueryV1.model_json_schema()),
    }


def _field_catalog(lineage: dict[str, Any], entities: dict[str, Any]) -> dict[str, Any]:
    included = {table["name"]: table for table in lineage.get("tables", [])}
    fields: list[dict[str, Any]] = []
    for table_name, table in included.items():
        for col in table["columns"]:
            name = col["name"]
            fields.append({
                "id": col.get("id") or f"sigmarail.field.{table_name}.{name}.{name}",
                "name": name,
                "table": table_name,
                "column": name,
                "type": col["type"],
                "description": col.get("comment", ""),
                "sql": f"{table_name}.{name}",
                "lineage_roots": col.get("lineage_roots", []),
                "metadata": entities.get(f"{table_name}.{name}", {}),
            })
    return {"version": 1, "fields": sorted(fields, key=lambda row: (row["table"], row["name"]))}


FIELD_DOMAINS = {
    "price_technical": {
        "screener_price_tech_daily", "symbol_technical_features_daily",
        "screener_vcp_pivot_daily", "screener_stage_weekly_daily", "ticker_rvab_daily",
    },
    "fundamentals": {"screener_fundamentals_daily"},
    "institutional": {"screener_ownership_daily"},
}


STRATEGY_SLOTS = {
    "universe-selection": {"slot": "UniverseSelection", "purpose": "Select dated candidates through universe queries."},
    "alpha": {"slot": "Alpha", "purpose": "Emit insights from selected securities and measures."},
    "portfolio-construction": {"slot": "PortfolioConstruction", "purpose": "Convert insights and holdings into portfolio targets."},
    "risk-management": {"slot": "RiskManagement", "purpose": "Apply position exits, stops, and risk actions."},
    "execution": {"slot": "Execution", "purpose": "Submit target orders using the selected fill session."},
}


def _render_documents(workspace: Path, lean_root: Path, lock: dict[str, Any]) -> dict[str, bytes]:
    lineage = _sigmarail_lineage(workspace)
    core_module = json.loads(
        (workspace / "src/sigmarail/spec/module-manifest.json").read_text(encoding="utf-8")
    )
    studio_modules = json.loads(
        (workspace / "studio/sigmarail_studio_mcp/data/module-catalog.json").read_text(encoding="utf-8")
    )
    module_schema = json.loads((ROOT / "spec/modules/module-manifest-v1.schema.json").read_text(encoding="utf-8"))
    entities = _load_entities(workspace)
    transforms = _transforms(workspace, lineage)
    models = _source_models(workspace, lean_root)
    declared_studio_modules = {row["name"] for row in studio_modules["modules"]}
    emitted_studio_modules = {
        tool["module"] for tools in models["mcp_tools"].values() for tool in tools
    }
    if not emitted_studio_modules <= declared_studio_modules:
        raise ValueError(f"MCP tools reference undeclared Studio modules: {sorted(emitted_studio_modules - declared_studio_modules)}")
    fields = _field_catalog(lineage, entities)
    annotations_path = ROOT / "metadata/annotations.json"
    annotations_text = annotations_path.read_text(encoding="utf-8")
    annotations = json.loads(annotations_text)

    # Link derived transform outputs to the declared schema columns; this remains table-level
    # lineage because no claim of exact expression-level SQL provenance is made here.
    transform_by_target = {item["target"]: item for item in transforms["transforms"]}
    for table in lineage.get("tables", []):
        transform = transform_by_target.get(table["name"])
        if transform:
            table["transform_id"] = transform["id"]

    capabilities = models["runtime_capabilities"]
    slots = {key.replace("-", "_"): value for key, value in STRATEGY_SLOTS.items()}
    runtime_types = capabilities.get("types", {})
    # Slot membership is generated from the framework schema and runtime capability table;
    # model-specific prose remains a source annotation, not inferred from class names.
    strategy = {
        "version": 1,
        "studio_authoring_schema": models["strategy"]["studio_authoring_schema"],
        "lean_framework_schema": models["strategy"]["lean_framework_schema"],
        "executable_strategy_schema": models["strategy"]["executable_strategy_schema"],
        "universe_query_schema": models["strategy"]["universe_query_schema"],
        "slots": slots,
        "wire_format": {"kind": "VeraLabV1", "schema_version": 2},
        "capability_types": {name: runtime_types[name] for name in sorted(runtime_types)},
        "runtime_type_ids_by_slot": models["runtime_types_by_slot"],
        "unclassified_runtime_type_ids": models["unclassified_runtime_type_ids"],
    }
    expressions_by_domain = {
        domain: {
            "version": models["expressions"]["version"],
            "domain": domain,
            "core_uri": "sigmarail-spec://v1/expressions/core",
            "scope": "Current consumer contract slice. SigmaRail SQL does not currently parse or evaluate this AST.",
            "field_ids": [field["id"] for field in fields["fields"] if field["table"] in domain_tables],
        }
        for domain, domain_tables in FIELD_DOMAINS.items()
    }
    data = {
        "lineage.json": lineage,
        "modules/core.json": core_module,
        "modules/studio.json": studio_modules,
        "modules/module-manifest-v1.schema.json": module_schema,
        "transforms.json": transforms,
        "fields.json": fields,
        "expressions.json": models["expressions"],
        **{
            f"fields/{domain}.json": {"version": 1, "domain": domain, "fields": [field for field in fields["fields"] if field["table"] in tables]}
            for domain, tables in FIELD_DOMAINS.items()
        },
        "fields/other.json": {"version": 1, "domain": "other", "fields": [field for field in fields["fields"] if field["table"] not in set().union(*FIELD_DOMAINS.values())]},
        **{f"expressions/{domain}.json": value for domain, value in expressions_by_domain.items()},
        "strategy/authoring.json": {
            "version": 1,
            "pipeline_document_schema": strategy["studio_authoring_schema"],
            "universe_query_schema": strategy["universe_query_schema"],
            "authoring_flow": ["PipelineDocument", "VeraLabV1", "LEAN Framework"],
        },
        "strategy/execution.json": {
            "version": 1,
            "wire_format": strategy["wire_format"],
            "executable_strategy_schema": strategy["executable_strategy_schema"],
            "lean_framework_schema": strategy["lean_framework_schema"],
            "slots": slots,
            "runtime_type_ids_by_slot": models["runtime_types_by_slot"],
            "unclassified_runtime_type_ids": models["unclassified_runtime_type_ids"],
        },
        "strategy/universe-query.json": strategy["universe_query_schema"],
        "data/query-v1.json": models["strategy"]["data_query_schema"],
        "runtime-capabilities.json": capabilities,
        "annotations.json": annotations,
        **{
            f"strategy/slots/{name}.json": {
                "version": 1,
                "slot": details["slot"],
                "purpose": details["purpose"],
                "type_ids": sorted(models["runtime_types_by_slot"][details["slot"]]),
                "capability_types": {
                    key: runtime_types[key]
                    for key in models["runtime_types_by_slot"][details["slot"]]
                },
                "contract_refs": {
                    "authoring": "sigmarail-spec://v1/strategy/authoring",
                    "execution": "sigmarail-spec://v1/strategy/execution",
                    "runtime_capabilities": "sigmarail-spec://v1/strategy/runtime-capabilities",
                    "expression_core": "sigmarail-spec://v1/expressions/core",
                },
            }
            for name, details in STRATEGY_SLOTS.items()
        },
        "mcp/index.json": {
            "version": 1,
            "source": "sigmarail/studio/sigmarail_studio_mcp/server.py",
            "domains": {
                domain: {
                    "document_uri": f"sigmarail-spec://v1/mcp/tools/{domain}",
                    "tool_count": len(tools),
                    "tools": [tool["name"] for tool in tools],
                }
                for domain, tools in models["mcp_tools"].items()
            },
            "activation_catalog": "sigmarail-spec://v1/modules/studio",
            "default_modules": studio_modules["default_enabled"],
            "optional_modules": [row["name"] for row in studio_modules["modules"] if not row["default_enabled"]],
        },
        **{
            f"mcp/tools/{domain}.json": {
                "version": 1,
                "domain": domain,
                "tools": tools,
            }
            for domain, tools in models["mcp_tools"].items()
        },
    }
    index_rows = [
        ("index", "sigmarail-spec://v1/index", "Contract index", "index.json"),
        ("data.schema", "sigmarail-spec://v1/data/schema", "SigmaRail SQL schema and lineage", "lineage.json"),
        ("semantics.annotations", "sigmarail-spec://v1/semantics/annotations", "Reviewed semantic annotations", "annotations.json"),
        ("data.transforms", "sigmarail-spec://v1/data/transforms", "SigmaRail SQL transform catalog", "transforms.json"),
        ("data.fields", "sigmarail-spec://v1/data/fields", "SigmaRail queryable field catalog", "fields.json"),
        ("data.query", "sigmarail-spec://v1/data/query/v1", "Module-aware data query request schema", "data/query-v1.json"),
        ("modules.core", "sigmarail-spec://v1/modules/core", "Built-in SigmaRail core module manifest", "modules/core.json"),
        ("modules.studio", "sigmarail-spec://v1/modules/studio", "Studio module activation catalog", "modules/studio.json"),
        ("modules.schema", "sigmarail-spec://v1/modules/schema", "SigmaRail module manifest schema v1", "modules/module-manifest-v1.schema.json"),
        *((f"data.fields.{domain}", f"sigmarail-spec://v1/data/fields/{domain}", f"SigmaRail {domain.replace('_', ' ')} fields", f"fields/{domain}.json") for domain in (*FIELD_DOMAINS, "other")),
        ("expressions.core", "sigmarail-spec://v1/expressions/core", "Expression AST and semantics", "expressions.json"),
        *((f"expressions.{domain}", f"sigmarail-spec://v1/expressions/{domain}", f"Expression contract for {domain.replace('_', ' ')}", f"expressions/{domain}.json") for domain in FIELD_DOMAINS),
        ("strategy.authoring", "sigmarail-spec://v1/strategy/authoring", "Studio authoring contract", "strategy/authoring.json"),
        ("strategy.execution", "sigmarail-spec://v1/strategy/execution", "LEAN execution contract", "strategy/execution.json"),
        ("strategy.universe-query", "sigmarail-spec://v1/strategy/universe-query", "VeraBase universe query schema", "strategy/universe-query.json"),
        ("strategy.runtime-capabilities", "sigmarail-spec://v1/strategy/runtime-capabilities", "LEAN model parameters and actions", "runtime-capabilities.json"),
        *((f"strategy.slot.{name}", f"sigmarail-spec://v1/strategy/slots/{name}", f"Strategy slot: {details['slot']}", f"strategy/slots/{name}.json") for name, details in STRATEGY_SLOTS.items()),
        ("mcp.index", "sigmarail-spec://v1/mcp", "MCP tool catalog", "mcp/index.json"),
        *((f"mcp.tools.{domain}", f"sigmarail-spec://v1/mcp/tools/{domain}", f"MCP {domain.replace('_', ' ')} tools", f"mcp/tools/{domain}.json") for domain in MCP_TOOL_DOMAINS),
    ]
    descriptions = {
        "index": "Compact entry point with retrieval guidance for the versioned SigmaRail contract.",
        "data.schema": "Sharadar-only SigmaRail tables, columns, types, comments, and lineage.",
        "semantics.annotations": "Reviewed semantic annotations not derivable from source code.",
        "data.transforms": "Generated xform view targets, dependencies, outputs, and SQL provenance.",
        "data.fields": "Queryable SigmaRail fields matched to schema columns and current query mappings.",
        "data.query": "Versioned bounded query AST over registered module datasets and declared joins.",
        "modules.core": "SQL-generated module manifest for SigmaRail core datasets, fields, joins, and capabilities.",
        "modules.schema": "JSON Schema for installing and describing SigmaRail core and optional modules.",
        "expressions.core": "Canonical expression AST, JSON schemas, evaluation semantics, and limits.",
        "strategy.authoring": "Studio PipelineDocument and universe-query authoring schemas.",
        "strategy.execution": "VeraLabV1 and LEAN framework execution schemas and slot index.",
        "strategy.universe-query": "SigmaRail universe query JSON schema.",
        "strategy.runtime-capabilities": "Generated runtime type parameters, actions, and behavior flags.",
        "mcp.index": "Compact catalog of the SigmaRail-aligned MCP tool operations and their resource URIs.",
    }
    for domain in (*FIELD_DOMAINS, "other"):
        descriptions[f"data.fields.{domain}"] = f"SigmaRail {domain.replace('_', ' ')} field slice."
    for domain in FIELD_DOMAINS:
        descriptions[f"expressions.{domain}"] = (
            f"Expression core reference and field IDs for {domain.replace('_', ' ')}."
        )
    for domain in MCP_TOOL_DOMAINS:
        descriptions[f"mcp.tools.{domain}"] = (
            f"Generated MCP input and output schemas for the current {domain.replace('_', ' ')} tool surface."
        )
    for name, details in STRATEGY_SLOTS.items():
        descriptions[f"strategy.slot.{name}"] = (
            f"Focused {details['slot']} slot types and parameters, with references to shared schemas."
        )
    documents = [
        {
            "id": row[0], "uri": row[1], "title": row[2], "path": row[3],
            "description": descriptions.get(row[0], row[2]),
        }
        for row in index_rows
    ]
    index = {
        "spec_id": "sigmarail-spec",
        "spec_version": "0.2.0",
        "description": "Compact index for SigmaRail data, expressions, Studio authoring, and LEAN strategy capabilities.",
        "documents": documents,
        "retrieval_order": ["index", "modules.core", "data.schema", "data.fields", "data.query", "expressions.core", "strategy.authoring", "strategy.execution"],
        "retrieval_profiles": {
            "sharadar_query": ["index", "modules.core", "data.schema", "data.fields/{domain}", "data.query", "data.transforms", "mcp.tools.screening"],
            "strategy_authoring": [
                "index", "expressions.core", "data.fields/{domain}",
                "strategy.authoring", "strategy/slots/{slot}",
                "mcp.tools.strategy_authoring",
            ],
            "strategy_execution": [
                "index", "strategy.execution", "strategy/slots/{slot}",
                "strategy.runtime-capabilities",
                "mcp.index",
            ],
        },
    }
    data["index.json"] = index
    provenance = {
        "version": 1,
        "sources": lock["sources"],
        "generator": {"path": "tools/build.py", "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "runtime_provenance": json.loads((ROOT / "metadata/runtime-provenance.json").read_text(encoding="utf-8")),
        "annotations_sha256": hashlib.sha256(annotations_text.encode("utf-8")).hexdigest(),
    }
    data["provenance.json"] = provenance
    return {name: _canonical_bytes(value) for name, value in data.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT, help="SigmaRail repository root")
    default_lean = os.environ.get("SIGMARAIL_LEAN_SOURCE")
    if not default_lean:
        candidates = (REPO_ROOT.parent / "Lean", REPO_ROOT.parent.parent / "Lean")
        default_lean = str(next((path for path in candidates if path.is_dir()), candidates[0]))
    parser.add_argument("--lean-source", type=Path, default=Path(default_lean), help="custom LEAN engine checkout (pinned in the source lock)")
    parser.add_argument("--check", action="store_true", help="Compare generated outputs without writing")
    parser.add_argument("--write-lock", action="store_true", help="Refresh pinned source revisions and digests")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    lean_root = args.lean_source.resolve()
    if not lean_root.is_dir():
        parser.error(f"custom LEAN source checkout does not exist: {lean_root}")
    lock = source_lock(workspace, lean_root)
    if args.write_lock:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_bytes(_canonical_bytes(lock))
        print(f"Updated source lock: {LOCK_PATH.relative_to(ROOT)}")
        return 0
    expected_lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    verify_lock(workspace, lean_root, expected_lock)
    outputs = _render_documents(workspace, lean_root, expected_lock)
    mismatches: list[str] = []
    for name, body in sorted(outputs.items()):
        destination = OUTPUT_ROOT / name
        if args.check:
            if not destination.is_file() or destination.read_bytes() != body:
                mismatches.append(name)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
    if args.check:
        if mismatches:
            print("Generated artifacts are stale or missing:")
            print("\n".join(f"  {name}" for name in mismatches))
            return 1
        print(f"Generated artifacts are current ({len(outputs)} files)")
        return 0
    print(f"Wrote {len(outputs)} generated documents to {OUTPUT_ROOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
