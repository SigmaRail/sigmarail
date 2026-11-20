"""Every example must actually run.

Documentation that does not execute rots, and this package's whole reason for existing is that
two copies of a shared thing drifted apart. Executing the examples in a subprocess keeps the
README, `docs/EXPRESSIONS.md` and the code from disagreeing.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("[0-9]*.py"))


def test_examples_exist() -> None:
    assert EXAMPLES, "no examples found — the README links to examples/"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_example_runs(example: pathlib.Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(example)],
        capture_output=True, text=True, cwd=str(ROOT.parent),
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert proc.returncode == 0, f"{example.name} failed:\n{proc.stdout}\n{proc.stderr}"
    assert proc.stdout.strip(), f"{example.name} printed nothing"


def test_examples_are_pydantic_only() -> None:
    """They ship as documentation for a container-safe package, so they must be too."""
    heavy = {"pandas", "numpy", "clickhouse_connect", "fastapi", "sqlglot", "yaml", "QuantConnect"}
    code = (
        "import runpy, sys\n"
        f"runpy.run_path({str(EXAMPLES[0])!r}, run_name='__main__')\n"
        f"print(sorted({{m.split('.')[0] for m in sys.modules}} & {heavy!r}))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[-1] == "[]", proc.stdout
