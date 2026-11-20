"""Component 4 Tier 3: Django REST integration for optimize/deploy endpoints.

Requires a reachable ClickHouse (skipped otherwise). Uses ephemeral
``e2e-`` prefixed sweep sessions and cleans them up.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from screens.optimizer import list_optimizer_sessions


def _ch_reachable() -> bool:
    try:
        from screens.ch import get_ch_client

        client = get_ch_client()
        try:
            client.query("SELECT 1")
        finally:
            client.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(os.environ.get("SIGMARAIL_SKIP_CH") == "1", reason="SIGMARAIL_SKIP_CH=1")
def test_list_optimizer_sessions_shape():
    if not _ch_reachable():
        pytest.skip("ClickHouse unreachable")
    sessions = list_optimizer_sessions(limit=1)
    assert isinstance(sessions, list)


def test_promotion_gate_missing_run(sigmarail_test_database):
    if not _ch_reachable():
        pytest.skip("ClickHouse unreachable")
    from screens.ch import get_ch_client
    from screens.live_promotion import check_promotion_gate

    assert sigmarail_test_database.query("SELECT count() FROM strategy_runs").result_rows == [(0,)]
    client = get_ch_client()
    try:
        res = check_promotion_gate(
            client,
            ir_id="e2e-nope",
            approval_backtest_run_id=f"run-missing-{uuid.uuid4().hex[:8]}",
        )
    finally:
        client.close()
    assert res.get("ok") is False
    assert res.get("code") == "not_found"
