"""The dialect reference must document every node the models declare.

`docs/EXPRESSIONS.md` is the page a user reads to learn the dialect. If the models gain a node
and the doc does not, the doc starts lying — and a wrong reference is worse than none.
"""

from __future__ import annotations

import inspect
import pathlib

from sigmarail_spec import expr

DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "EXPRESSIONS.md"


def _dialect_nodes() -> set[str]:
    found = set()
    for obj in vars(expr).values():
        if not inspect.isclass(obj) or getattr(obj, "__module__", "") != "sigmarail_spec.expr":
            continue
        fields = getattr(obj, "model_fields", None) or {}
        default = getattr(fields.get("type"), "default", None)
        if isinstance(default, str):
            found.add(default)
    return found


def test_doc_exists() -> None:
    assert DOC.is_file()


def test_every_node_is_documented() -> None:
    text = DOC.read_text(encoding="utf-8")
    missing = sorted(n for n in _dialect_nodes() if f"`{n}`" not in text)
    assert not missing, f"undocumented dialect node(s): {missing} — update {DOC.name}"


def test_documented_nodes_exist() -> None:
    """And the reverse: no doc row for a node that was removed."""
    import re

    text = DOC.read_text(encoding="utf-8")
    # Only rows whose second cell is a backticked class name — that skips the header row
    # (`| `type` | Class | Fields |`) and any prose table.
    documented = set(re.findall(r"^\| `([a-z_]+)` \| `[A-Za-z]", text, re.M))
    stale = sorted(documented - _dialect_nodes())
    assert not stale, f"{DOC.name} documents non-existent node(s): {stale}"


def test_evaluator_semantics_are_stated() -> None:
    """The two fallback conventions are the easiest thing to get wrong; the doc must say so."""
    text = DOC.read_text(encoding="utf-8")
    for phrase in ("fail-open", "fail-closed", "evaluate_where_ast", "evaluate_slot_bool"):
        assert phrase in text, f"{DOC.name} no longer documents {phrase!r}"


README = pathlib.Path(__file__).resolve().parents[1] / "README.md"


def _python_blocks(text: str) -> list[str]:
    import re

    return re.findall(r"```python\n(.*?)```", text, re.S)


def test_readme_python_blocks_execute() -> None:
    """The front-page example must run, not just look plausible.

    This test exists because it did not: the quick start composed `parse_bool_expr` (which
    returns a pydantic model) with `evaluate_where_ast` (which takes a dict) and raised
    AttributeError. A README that crashes is worse than no README.
    """
    import os
    import subprocess
    import sys

    blocks = _python_blocks(README.read_text(encoding="utf-8"))
    assert blocks, "no python blocks found in README.md"
    for i, block in enumerate(blocks, 1):
        proc = subprocess.run(
            [sys.executable, "-c", block], capture_output=True, text=True,
            cwd=str(README.parent),
            env={**os.environ, "PYTHONPATH": str(README.parent / "src")},
        )
        assert proc.returncode == 0, (
            f"README.md python block {i} failed:\n{proc.stdout}\n{proc.stderr}")


