"""Component 4 Tier 1: spec lineage serialization contracts.

Verifies ``save_spec`` accepts lineage kwargs and emits them in the ClickHouse
insert, and that the list/detail readers surface a ``lineage`` block.
"""
from __future__ import annotations

import inspect

from sigmarail_studio_mcp.backtest_runner.runner import save_spec
from screens import backtest_jobs


def test_save_spec_accepts_lineage_kwargs():
    sig = inspect.signature(save_spec)
    for kw in ("parent_ir_id", "parent_content_hash", "mutation_type", "changelog_notes", "author_agent"):
        assert kw in sig.parameters, f"save_spec missing kwarg {kw}"


def test_save_spec_inserts_lineage_columns():
    captured: dict = {}

    class FakeClient:
        def insert(self, table, rows, column_names=None):
            captured["table"] = table
            captured["columns"] = list(column_names or [])
            captured["rows"] = rows

        def close(self):
            pass

    import sigmarail_studio_mcp.backtest_runner.ch_client as ch_mod

    orig = ch_mod.get_client
    ch_mod.get_client = lambda: FakeClient()  # type: ignore[assignment]
    try:
        save_spec(
            ir_id="test-lineage",
            title="lineage probe",
            spec_json='{"schema_version": 1}',
            parent_ir_id="parent-1",
            mutation_type="fork",
            changelog_notes="tightened stop",
            author_agent="agent-x",
        )
    finally:
        ch_mod.get_client = orig
    assert "parent_ir_id" in captured["columns"]
    assert "mutation_type" in captured["columns"]
    assert "changelog_notes" in captured["columns"]
    assert "author_agent" in captured["columns"]


def test_list_specs_reader_includes_lineage():
    src = inspect.getsource(backtest_jobs.list_specs)
    assert "parent_ir_id" in src
    assert '"lineage"' in src or "'lineage'" in src


def test_get_spec_reader_includes_lineage():
    src = inspect.getsource(backtest_jobs.get_spec_by_ir_id)
    assert "parent_ir_id" in src
    assert '"lineage"' in src or "'lineage'" in src
