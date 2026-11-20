"""Static contract checks for the LEAN adapter without loading the LEAN engine."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lean_entrypoint_imports_sigmarail_algorithm() -> None:
    entrypoint = ast.parse((ROOT / "trading_lab" / "main.py").read_text(encoding="utf-8"))
    imports = [node for node in entrypoint.body if isinstance(node, ast.ImportFrom)]
    assert any(
        node.module == "sigmarail_lab.lean.algorithm"
        and any(
            alias.name == "ClickHouseUniverseAlgorithm"
            and alias.asname == "_SigmaRailAlgorithm"
            for alias in node.names
        )
        for node in imports
    )
    assert any(
        isinstance(node, ast.ClassDef)
        and node.name == "ClickHouseUniverseAlgorithm"
        and any(
            isinstance(base, ast.Name) and base.id == "_SigmaRailAlgorithm"
            for base in node.bases
        )
        for node in entrypoint.body
    )


def test_qcalgorithm_uses_shared_five_slot_interpreter() -> None:
    algorithm_path = ROOT / "src" / "sigmarail_lab" / "lean" / "algorithm.py"
    tree = ast.parse(algorithm_path.read_text(encoding="utf-8"))
    algorithm = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ClickHouseUniverseAlgorithm"
    )
    assert any(isinstance(base, ast.Name) and base.id == "QCAlgorithm" for base in algorithm.bases)

    calls = [
        node
        for node in ast.walk(algorithm)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "wire_framework_bundle_v1"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) >= 2
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "self"
    assert isinstance(call.args[1], ast.Name) and call.args[1].id == "fb"
    assert any(keyword.arg == "store" for keyword in call.keywords)
