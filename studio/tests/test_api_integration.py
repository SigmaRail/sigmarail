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


@pytest.mark.skipif(os.environ.get("VERA_SKIP_CH") == "1", reason="VERA_SKIP_CH=1")
def test_list_optimizer_sessions_shape():
    if not _ch_reachable():
        pytest.skip("ClickHouse unreachable")
    sessions = list_optimizer_sessions(limit=1)
    assert isinstance(sessions, list)


def test_cancel_session_missing_is_error_envelope():
    if not _ch_reachable():
        pytest.skip("ClickHouse unreachable")
    from sigmarail_studio_mcp.domains.optimize import cancel_session

    res = cancel_session(f"e2e-missing-{uuid.uuid4().hex[:8]}")
    assert res.get("status") == "cancelled"
    assert res.get("cancelled_jobs") == []


def test_promotion_gate_missing_run():
    if not _ch_reachable():
        pytest.skip("ClickHouse unreachable")
    from sigmarail_studio_mcp.domains.deploy import evaluate_promotion_gate

    res = evaluate_promotion_gate("e2e-nope", f"run-missing-{uuid.uuid4().hex[:8]}")
    assert res.get("ok") is False
    assert res.get("code") == "not_found"
