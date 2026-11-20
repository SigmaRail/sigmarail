"""Opt-in LEAN-to-SigmaRail end-to-end smoke using disposable synthetic data.

Run with ``SIGMARAIL_LEAN_SMOKE=1 pytest --sigmarail-clickhouse tests/test_lean_smoke.py``.
The smoke uses a temporary LEAN workspace and temporary settings that point only at
the test fixture's ``sigmarail_test`` database.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from sigmarail_studio_mcp.backtest_runner.project_staging import stage_lean_project


pytestmark = pytest.mark.skipif(
    os.environ.get("SIGMARAIL_LEAN_SMOKE") != "1",
    reason="set SIGMARAIL_LEAN_SMOKE=1 to run the Docker-backed LEAN/API smoke",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _universe_spec() -> dict:
    """Use registered prices, with lightweight rank/screen aliases computed in SQL."""
    return {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "atr_14_pct"],
        "where": {
            "type": "gt",
            "left": {"type": "col", "name": "close"},
            "right": {"type": "lit", "value": 0},
        },
        "computed": [
            {
                "alias": "overall_score",
                "kind": "number",
                "expr": {
                    "type": "formula",
                    "op": "/",
                    "args": [
                        {"type": "col", "name": "close"},
                        {"type": "lit", "value": 1},
                    ],
                },
            },
            {
                "alias": "minervini_tt_all_conditions_full",
                "kind": "bool",
                "where": {
                    "type": "gt",
                    "left": {"type": "col", "name": "close"},
                    "right": {"type": "lit", "value": 0},
                },
            },
        ],
        "order_by": [{"field": "overall_score", "direction": "desc"}],
        "limit_per_day": 100,
    }


def test_custom_lean_engine_loads_synthetic_universe_from_sigmarail_api(
    request, pytestconfig, sigmarail_test_database, sigmarail_clickhouse_service, tmp_path
):
    """Exercise the real API handshake, computed SQL, LEAN HTTP client, and CH bar provider."""
    root = Path(pytestconfig.rootpath)
    studio_root = root / "studio"
    trading_lab_root = Path(
        os.environ.get(
            "SIGMARAIL_TRADING_LAB_SOURCE",
            str(root / "trading_lab"),
        )
    )
    studio_python = Path(
        os.environ.get(
            "SIGMARAIL_STUDIO_PYTHON",
            sys.executable,
        )
    )
    lean_python = Path(
        os.environ.get(
            "SIGMARAIL_LEAN_PYTHON",
            sys.executable,
        )
    )
    spec_source_raw = (os.environ.get("SIGMARAIL_SPEC_SOURCE") or "").strip()
    spec_source = Path(spec_source_raw).resolve() if spec_source_raw else None
    image = os.environ.get("SIGMARAIL_LEAN_IMAGE", "lean-local:latest")
    assert studio_python.is_file(), f"Studio Python not found: {studio_python}"
    assert lean_python.is_file(), f"LEAN CLI Python not found: {lean_python}"
    assert trading_lab_root.is_dir(), f"SigmaRail Trading Lab source not found: {trading_lab_root}"

    ch = request.getfixturevalue("sigmarail_clickhouse_service")
    assert ch is not None
    port = _free_port()
    config_home = tmp_path / "sigmarail-config"
    config_home.mkdir()
    (config_home / "config-test.yaml").write_text(
        "database:\n"
        "  host: 127.0.0.1\n"
        f"  port: {ch['native_port']}\n"
        f"  http_port: {ch['http_port']}\n"
        "  user: default\n"
        "  password: ''\n"
        "  database: sigmarail_test\n"
        "  production_database: sigmarail\n",
        encoding="utf-8",
    )
    server_env = os.environ.copy()
    server_env.update(
        {
            "SIGMARAIL_MODE": "test",
            "SIGMARAIL_HOME": str(config_home),
            "SIGMARAIL_TEST_CLICKHOUSE_HOST": "127.0.0.1",
            "SIGMARAIL_TEST_CLICKHOUSE_HTTP_PORT": str(ch["http_port"]),
            "SIGMARAIL_TEST_CLICKHOUSE_NATIVE_PORT": str(ch["native_port"]),
            "SIGMARAIL_TEST_CLICKHOUSE_USER": "default",
            "SIGMARAIL_TEST_CLICKHOUSE_PASSWORD": "",
            "PYTHONPATH": os.pathsep.join(
                [
                    str(studio_root),
                    str(root / "src"),
                    *([str(spec_source)] if spec_source and spec_source.is_dir() else []),
                ]
            ),
            "DJANGO_SETTINGS_MODULE": "config.settings",
        }
    )
    api_log = (tmp_path / "sigmarail-api.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [str(studio_python), "manage.py", "runserver", f"0.0.0.0:{port}", "--noreload"],
        cwd=studio_root,
        env=server_env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if server.poll() is not None:
                pytest.fail(f"SigmaRail API exited early:\n{(tmp_path / 'sigmarail-api.log').read_text()}")
            try:
                meta_response = requests.get(f"{base_url}/v1/meta", timeout=1)
                if meta_response.ok:
                    break
            except requests.RequestException:
                time.sleep(0.25)
        else:
            pytest.fail(f"SigmaRail API did not start:\n{(tmp_path / 'sigmarail-api.log').read_text()}")

        meta = meta_response.json()
        assert meta["dialect"]["id"] == "C-VERA-EXPR-V1"
        assert meta["registry_digest"].startswith("sha256:")
        body = {
            "start_date": "2024-12-02",
            "end_date": "2024-12-06",
            "mode": "detail",
            "export_format": "objects",
            "limit": 5000,
            "spec": _universe_spec(),
        }
        preview = requests.post(f"{base_url}/v1/universe/run", json=body, timeout=90)
        assert preview.ok, preview.text
        assert preview.json()["row_count"] > 0, preview.json()
        api_row = preview.json()["rows"][0]
        assert float(api_row["overall_score"]) > 0
        assert api_row["minervini_tt_all_conditions_full"] == 1

        workspace = tmp_path / "lean-workspace"
        workspace.mkdir()
        (workspace / "data").mkdir()
        (workspace / "lean.json").write_text(
            json.dumps(
                {
                    "organization-id": "00000000000000000000000000000000",
                    "data-folder": "data",
                    "id": "sigmarail-smoke",
                }
            ),
            encoding="utf-8",
        )
        staged = stage_lean_project(
            workspace,
            job_id="sigmarail-smoke",
            strategy_id="strategy-smoke",
        )
        project = staged.root
        smoke_ir = json.loads(
            (trading_lab_root / "fixtures/ir/minimal_hybrid.json").read_text(
                encoding="utf-8"
            )
        )
        smoke_ir["VeraBase"]["Universe"] = _universe_spec()
        (project / "sigmarail-smoke.json").write_text(
            json.dumps(smoke_ir, indent=2), encoding="utf-8"
        )

        lean_config = {
            "data-folder": "data",
            "python-additional-paths": ["/LeanCLI"],
            "initialization-timeout": 1800,
            "clickhouse-host": "host.docker.internal",
            "clickhouse-http-port": ch["http_port"],
            "clickhouse-user": "default",
            "clickhouse-password": "",
            "clickhouse-database": "sigmarail_test",
            "clickhouse-data-mode": "in_memory",
            "clickhouse-backtest-start": "2024-12-02",
            "clickhouse-backtest-end": "2024-12-06",
            "clickhouse-history-pad-days": 365,
            "clickhouse-timeout-seconds": 180,
            "data-provider": "QuantConnect.Lean.Engine.DataFeeds.CompositeDataProvider",
            "composite-data-providers": (
                '["QuantConnect.Lean.Engine.DataFeeds.ClickHouseDataProvider",'
                '"QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider"]'
            ),
            "environments": {"backtesting": {"data-provider": "QuantConnect.Lean.Engine.DataFeeds.CompositeDataProvider"}},
        }
        config_path = workspace / "lean-smoke.json"
        config_path.write_text(json.dumps(lean_config), encoding="utf-8")
        extra_docker = {
            "environment": {
                "CLICKHOUSE_HOST": "host.docker.internal",
                "CLICKHOUSE_PORT": str(ch["http_port"]),
                "CLICKHOUSE_USER": "default",
                "CLICKHOUSE_PASSWORD": "",
                "CLICKHOUSE_DATABASE": "sigmarail_test",
                "SIGMARAIL_STRATEGY_PATH": "sigmarail-smoke.json",
                "SIGMARAIL_STRATEGY_ROOT": "/LeanCLI",
                "PYTHONPATH": "/LeanCLI",
                "SIGMARAIL_API_URL": f"http://host.docker.internal:{port}",
            }
        }
        output = workspace / "backtests" / "sigmarail-smoke"
        command = [
            str(lean_python),
            str(trading_lab_root / "scripts/lean_backtest_composite.py"),
            str(project),
            "--output",
            str(output),
            "--image",
            image,
            "--no-update",
            "--lean-config",
            str(config_path),
            "--parameter",
            "start-date",
            "2024-12-02",
            "--parameter",
            "end-date",
            "2024-12-06",
            "--extra-docker-config",
            json.dumps(extra_docker),
        ]
        run = subprocess.run(
            command,
            cwd=workspace,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        log = run.stdout + "\n" + run.stderr
        (tmp_path / "lean-backtest.log").write_text(log, encoding="utf-8")
        assert run.returncode == 0, f"LEAN smoke failed (see {tmp_path / 'lean-backtest.log'}):\n{log[-12000:]}"
        results = list(output.rglob("*.json"))
        assert results, f"LEAN returned success without result artifacts; log:\n{log[-12000:]}"
        engine_log = output / "log.txt"
        assert engine_log.is_file(), f"LEAN engine log missing; CLI log:\n{log[-12000:]}"
        engine_text = engine_log.read_text(encoding="utf-8", errors="replace")
        assert "SigmaRailDailyScreener: dialect=C-VERA-EXPR-V1" in engine_text, engine_text[-12000:]
        assert re.search(r"daily_screener loaded: [1-9][0-9]* rows", engine_text), engine_text[-12000:]
        assert "SigmaRail strategy resolution failed" not in engine_text, engine_text[-12000:]
        summaries = list(output.glob("*-summary.json"))
        assert len(summaries) == 1, f"expected one LEAN summary, found {summaries}"
        summary = json.loads(summaries[0].read_text(encoding="utf-8"))
        assert int(summary["statistics"]["Total Orders"]) > 0, summary["statistics"]
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        api_log.close()
