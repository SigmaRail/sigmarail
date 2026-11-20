#!/usr/bin/env python3
"""Run ``lean backtest`` with CompositeDataProvider forced after CLI Local defaults.

Lean CLI ``--data-provider-historical`` defaults to ``Local``, which writes
``environments.backtesting.data-provider = DefaultDataProvider``. Lean's Config.Get
prefers the environment key over the top-level ``data-provider``, so ClickHouse
bars never load even when lean.json asks for Composite.

This wrapper patches ``LeanRunner.run_lean`` to re-assert Composite (+ keep
``composite-data-providers``) on both top-level and the active environment, then
delegates to ``lean backtest``.
"""

from __future__ import annotations

import sys
from typing import Any

COMPOSITE = "QuantConnect.Lean.Engine.DataFeeds.CompositeDataProvider"
COMPOSITE_LIST = (
    '["QuantConnect.Lean.Engine.DataFeeds.ClickHouseDataProvider",'
    '"QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider"]'
)


def _force_composite(lean_config: dict[str, Any]) -> None:
    lean_config["data-provider"] = COMPOSITE
    lean_config["composite-data-providers"] = COMPOSITE_LIST
    # Decade PreHydrate needs more than Lean's 300s Initialize default.
    lean_config.setdefault("initialization-timeout", 1800)
    lean_config.setdefault("clickhouse-timeout-seconds", 300)
    env_name = lean_config.get("environment") or "backtesting"
    envs = lean_config.setdefault("environments", {})
    env = envs.setdefault(env_name, {})
    if isinstance(env, dict):
        env["data-provider"] = COMPOSITE


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    from lean.components.docker.lean_runner import LeanRunner

    original = LeanRunner.run_lean

    def run_lean(self, lean_config, *args, **kwargs):  # type: ignore[no-untyped-def]
        _force_composite(lean_config)
        return original(self, lean_config, *args, **kwargs)

    LeanRunner.run_lean = run_lean  # type: ignore[method-assign]

    # ``lean.main`` expects sys.argv like ``lean backtest ...``
    sys.argv = ["lean", "backtest", *argv]
    from lean.main import main as lean_main

    try:
        lean_main()
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
