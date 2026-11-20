from __future__ import annotations

import json
import pytest

from sigmarail_spec import get_document, get_document_text, list_documents


def test_retrieval_supports_ids_uris_and_encoded_nested_paths() -> None:
    index = get_document("sigmarail-spec://v1/index")
    assert index["spec_id"] == "sigmarail-spec"
    assert get_document("sigmarail-spec://v1/strategy/slots/alpha")["slot"] == "Alpha"
    assert json.loads(get_document_text("sigmarail-spec://v1/strategy/slots%2Falpha"))["slot"] == "Alpha"
    assert get_document("data.schema")["tables"]
    assert get_document("sigmarail-spec://v1/semantics/annotations")["version"] == 1
    assert len(list_documents()) == len(index["documents"])


def test_index_exposes_all_requested_field_expression_and_strategy_slices() -> None:
    uris = {item["uri"] for item in list_documents()}
    assert {
        "sigmarail-spec://v1/data/fields/price_technical",
        "sigmarail-spec://v1/data/fields/fundamentals",
        "sigmarail-spec://v1/data/fields/institutional",
        "sigmarail-spec://v1/expressions/core",
        "sigmarail-spec://v1/expressions/price_technical",
        "sigmarail-spec://v1/expressions/fundamentals",
        "sigmarail-spec://v1/expressions/institutional",
        "sigmarail-spec://v1/strategy/slots/universe-selection",
        "sigmarail-spec://v1/strategy/slots/alpha",
        "sigmarail-spec://v1/strategy/slots/portfolio-construction",
        "sigmarail-spec://v1/strategy/slots/risk-management",
        "sigmarail-spec://v1/strategy/slots/execution",
    } <= uris


def test_index_exposes_filtered_mcp_tool_contracts_from_current_studio() -> None:
    index = get_document("index")
    catalog = get_document("mcp.index")
    assert "mcp.tools.screening" in index["retrieval_profiles"]["sharadar_query"]
    assert catalog["domains"]["screening"]["tool_count"] > 0
    assert catalog["domains"]["strategy_authoring"]["tool_count"] > 0
    assert catalog["domains"]["backtesting"]["tool_count"] > 0

    screening = get_document("mcp.tools.screening")["tools"]
    tools = {tool["name"]: tool for tool in screening}
    assert "screen_stocks" in tools
    assert tools["screen_stocks"]["description"]
    assert tools["screen_stocks"]["input_schema"]["type"] == "object"
    assert tools["screen_stocks"]["output_schema"]

    all_tools = [
        tool["name"]
        for domain in catalog["domains"]
        for tool in get_document(catalog["domains"][domain]["document_uri"])["tools"]
    ]
    assert not any(name.startswith(("catalog_", "kb_", "portfolio_", "research_")) for name in all_tools)


def test_strategy_slot_documents_are_focused_and_partition_runtime_types() -> None:
    from sigmarail_spec import get_document

    execution = get_document("strategy.execution")
    all_runtime_types = set(get_document("strategy.runtime-capabilities")["types"])
    slot_names = (
        "universe-selection", "alpha", "portfolio-construction", "risk-management", "execution"
    )
    slot_docs = [
        get_document(f"sigmarail-spec://v1/strategy/slots/{name}") for name in slot_names
    ]
    ids_by_slot = {doc["slot"]: set(doc["type_ids"]) for doc in slot_docs}
    classified = set().union(*ids_by_slot.values())
    unclassified = set(execution["unclassified_runtime_type_ids"])

    assert classified | unclassified == all_runtime_types
    assert sum(map(len, ids_by_slot.values())) == len(classified)
    assert ids_by_slot["Alpha"] >= {"VeraPyramidAlphaModel", "VeraCompositeAlphaModel"}
    assert ids_by_slot["RiskManagement"] >= {"VeraHedgeModel", "TrailingStopRiskManagementModel"}
    assert ids_by_slot["UniverseSelection"] >= {"VeraScreenerUniverseSelectionModel"}
    for doc in slot_docs:
        assert "lean_framework_schema" not in doc
        assert "executable_strategy_schema" not in doc
        assert set(doc["capability_types"]) == set(doc["type_ids"])


def test_fields_and_transforms_resolve_to_schema_and_exclusions_stay_excluded() -> None:
    schema = get_document("data.schema")
    tables = {table["name"]: table for table in schema["tables"]}
    columns = {name: {column["name"] for column in table["columns"]} for name, table in tables.items()}
    fields = get_document("data.fields")["fields"]
    assert fields
    assert all(field["table"] in columns and field["column"] in columns[field["table"]] for field in fields)

    excluded = {
        row["table"] for row in schema.get("deferred_external_tables", [])
    } | {
        row["table"] for row in schema.get("deferred_application_layers", [])
    }
    assert not excluded.intersection(columns)

    transforms = get_document("data.transforms")["transforms"]
    assert transforms
    assert all(row["target"] in tables and row["view"].startswith("xform_") for row in transforms)
    assert all(set(row["outputs"]) <= columns[row["target"]] for row in transforms)


def test_domain_field_slices_partition_all_fields_without_loss() -> None:
    all_ids = {field["id"] for field in get_document("data.fields")["fields"]}
    slices = [
        get_document(f"sigmarail-spec://v1/data/fields/{name}")["fields"]
        for name in ("price_technical", "fundamentals", "institutional", "other")
    ]
    flattened = [field["id"] for group in slices for field in group]
    assert len(flattened) == len(set(flattened))
    assert set(flattened) == all_ids


def test_expression_runtime_is_canonical_package_module() -> None:
    from sigmarail_spec.expr import BoolExprItem, SpecExpr
    from sigmarail_spec.evaluate import evaluate_slot_bool

    assert BoolExprItem is not None and SpecExpr is not None
    assert evaluate_slot_bool({"x": 1}, {"type": "gte", "left": {"type": "col", "name": "x"}, "right": {"type": "lit", "value": 1}})


def test_legacy_sigmarail_spec_imports_reexport_canonical_types() -> None:
    from sigmarail_spec.expr import SpecExpr as CanonicalSpecExpr
    from vera_spec.expr import SpecExpr as LegacySpecExpr

    assert LegacySpecExpr is CanonicalSpecExpr


def test_source_tree_digest_ignores_bytecode_and_cache_directories(tmp_path) -> None:
    from pathlib import Path
    import runpy

    hash_files = runpy.run_path(str(Path(__file__).parents[1] / "tools/build.py"))["_hash_files"]
    tree = tmp_path / "src"
    tree.mkdir()
    (tree / "module.py").write_text("value = 1\n")
    first = hash_files(tmp_path, ["src"])
    cache = tree / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-311.pyc").write_bytes(b"unstable bytecode")
    assert hash_files(tmp_path, ["src"]) == first


def test_lean_vendor_manifest_covers_all_generated_runtime_files() -> None:
    from pathlib import Path
    import hashlib
    import json
    import runpy

    expected_files = runpy.run_path(str(Path(__file__).parents[1] / "tools/sync_lean_vendor.py"))["expected_files"](Path("unused"))
    manifest = json.loads(expected_files[".vendored.json"])
    payload_names = set(expected_files) - {".vendored.json"}
    assert set(manifest["files"]) == payload_names
    assert all(hashlib.sha256(expected_files[name]).hexdigest() == manifest["files"][name] for name in payload_names)


def test_builder_is_deterministic_and_check_mode_does_not_write() -> None:
    from pathlib import Path
    import json
    import os
    import runpy

    root = Path(__file__).parents[1]
    builder = runpy.run_path(str(root / "tools/build.py"))
    workspace = Path(__file__).resolve().parents[3]
    lean_value = os.environ.get("SIGMARAIL_LEAN_SOURCE")
    lean_candidates = (workspace.parent / "Lean", workspace.parent.parent / "Lean")
    lean_root = Path(lean_value).resolve() if lean_value else next(
        (path for path in lean_candidates if path.is_dir()), lean_candidates[0]
    )
    if not lean_root.is_dir():
        pytest.skip("contract regeneration requires the pinned custom LEAN source checkout")
    lock = json.loads((root / "spec/sources.lock.json").read_text())
    first = builder["_render_documents"](workspace, lean_root, lock)
    second = builder["_render_documents"](workspace, lean_root, lock)
    assert first == second

    before = {name: (root / "src/sigmarail_spec/data" / name).read_bytes() for name in first}
    assert builder["main"]([
        "--workspace", str(workspace), "--lean-source", str(lean_root), "--check"
    ]) == 0
    after = {name: (root / "src/sigmarail_spec/data" / name).read_bytes() for name in first}
    assert after == before
