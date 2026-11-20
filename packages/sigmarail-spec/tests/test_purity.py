"""VeraSpec must be importable with pydantic alone.

This package ships into the LEAN container, where pandas, clickhouse-connect, fastapi and
QuantConnect are not installed. One careless import breaks *every* backtest, and the
failure is silent locally — so purity is asserted in a fresh interpreter rather than
trusted by convention.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

HEAVY = {
    "pandas", "numpy", "clickhouse_connect", "fastapi", "sqlglot", "yaml",
    "QuantConnect", "AlgorithmImports", "Python", "requests", "sklearn",
}
SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
    )


def test_imports_without_any_heavy_dependency() -> None:
    names = ", ".join(sorted(HEAVY))
    proc = _run(
        "import sys, json\n"
        "import sigmarail_spec, vera_spec\n"
        f"bad = sorted(m for m in sys.modules if m.split('.')[0] in {HEAVY!r})\n"
        "print(json.dumps(bad))\n"
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]", (
        f"SigmaRail Spec pulled in {proc.stdout.strip()} — it ships into the Lean container, "
        f"where these are absent ({names}). Move the code out; do not widen the deps."
    )


def test_only_pydantic_is_declared() -> None:
    pyproject = (SRC.parent / "pyproject.toml").read_text(encoding="utf-8")
    deps = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "pydantic" in deps
    for banned in ("pandas", "clickhouse", "fastapi", "sqlglot", "QuantConnect"):
        assert banned.lower() not in deps.lower(), f"{banned} declared as a dependency"
