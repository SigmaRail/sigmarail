"""ClickHouse client helper for Screening Studio API."""

from __future__ import annotations

from typing import Any


def get_ch_client() -> Any:
    """Return a fresh ClickHouse client.

    Studio and Core share SigmaRail's database configuration and test-mode
    safety checks. A fresh client per request also avoids sharing a
    clickhouse-connect client across concurrent DRF requests.
    """
    from sigmarail.database import get_client

    return get_client()
