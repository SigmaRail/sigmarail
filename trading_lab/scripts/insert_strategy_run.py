#!/usr/bin/env python3
"""Insert one row into strategy_runs + optional artifacts (matches CI backtest workflow)."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


import sys

# Ensure this generated SigmaRail project is importable for sigmarail_lab.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from sigmarail_lab.models.strategy_runs import ArtifactRecord, StrategyRunRecord


def _require_env(name: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"Missing required env var: {name}")
    return os.environ[name].strip()


def post_jsoneachrow(host: str, port: str, user: str, password: str, table: str, row: dict) -> None:
    url = f"http://{host}:{port}/?query=INSERT%20INTO%20{table}%20FORMAT%20JSONEachRow"
    payload = (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-ClickHouse-User", user)
    req.add_header("X-ClickHouse-Key", password)
    with urllib.request.urlopen(req, timeout=60) as resp:
        _ = resp.read()


def read_text(path: str, max_bytes: int = 15_000_000) -> str:
    if not path:
        return ""
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError(f"Artifact too large (> {max_bytes} bytes): {path}")
    return data.decode("utf-8", errors="replace")


def build_parameters_blob(
    config_path: Path | None,
    extra: dict | None,
    ir_lineage: dict | None,
    provenance: dict | None = None,
) -> str:
    if config_path and config_path.is_file():
        base = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        base = {}
    if ir_lineage:
        base = dict(base)
        base["_sigmarail_lab"] = ir_lineage
    if provenance:
        base = dict(base)
        base["_provenance"] = provenance
    if extra:
        merged = dict(base)
        merged["_stress"] = extra
        return json.dumps(merged, separators=(",", ":"))
    return json.dumps(base, separators=(",", ":"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument(
        "--run-type",
        default="base",
        help="strategy_runs.run_type (Enum8): base | optimization | variant | stress_test",
    )
    p.add_argument("--summary-json", required=True)
    p.add_argument("--repo-name", required=True)
    p.add_argument("--repo-url", default="")
    p.add_argument("--commit-sha", default="")
    p.add_argument("--git-branch", default="")
    p.add_argument("--trigger", default="manual")
    p.add_argument("--period-start", required=True)
    p.add_argument("--period-end", required=True)
    p.add_argument("--image", default="")
    p.add_argument(
        "--image-id",
        default="",
        help="Docker image ID (sha256) captured by the runner at run time",
    )
    p.add_argument(
        "--image-created",
        default="",
        help="Docker image creation timestamp captured by the runner at run time",
    )
    p.add_argument("--order-events-json", default="")
    p.add_argument("--backtest-json", default="")
    p.add_argument("--benchmark-json", default="", help="Optional adjusted benchmark-series evidence sidecar")
    p.add_argument("--day-snapshots-json", default="", help="Path to backtest_day_snapshots.json")
    p.add_argument("--accounting-json", default="", help="Path to backtest_accounting.json")
    p.add_argument("--config-json", default="", help="Path to config.json for parameters column")
    p.add_argument("--stress-meta-json", default="", help='Merge into parameters as "_stress"')
    p.add_argument("--ir-id", default="", help="strategy_runs.ir_id (from CH spec row)")
    p.add_argument(
        "--ir-schema-version",
        default="",
        help="strategy_runs.ir_schema_version (mirror JSON schema_version)",
    )
    p.add_argument("--ir-content-hash", default="", help="strategy_runs.ir_content_hash (sha256 hex)")
    p.add_argument("--source-sha256", default="", help="SHA-256 of the staged SigmaRail Trading Lab source")
    args = p.parse_args()

    host = _require_env("CLICKHOUSE_HOST")
    port = (os.environ.get("CLICKHOUSE_PORT") or "8123").strip()
    user = _require_env("CLICKHOUSE_USER")
    password = _require_env("CLICKHOUSE_PASSWORD")

    summary = json.loads(read_text(args.summary_json))
    backtest_content = read_text(args.backtest_json)
    try:
        backtest_results = json.loads(backtest_content) if backtest_content else None
    except (ValueError, RecursionError):
        backtest_results = None
    benchmark_path = Path(args.benchmark_json) if args.benchmark_json else None
    if benchmark_path is None and args.backtest_json:
        benchmark_path = Path(args.backtest_json).with_name("benchmark_series.json")
    if benchmark_path and benchmark_path.is_file() and isinstance(backtest_results, dict):
        try:
            benchmark_series = json.loads(read_text(str(benchmark_path)))
        except (ValueError, RecursionError):
            benchmark_series = None
        if isinstance(benchmark_series, dict):
            backtest_results["benchmarkSeries"] = benchmark_series
            backtest_content = json.dumps(backtest_results, separators=(",", ":"))
    extra = json.loads(args.stress_meta_json) if args.stress_meta_json else None
    cfg = Path(args.config_json) if args.config_json else None
    ir_lineage = {}
    if args.ir_id:
        ir_lineage["ir_id"] = args.ir_id
    if args.ir_schema_version:
        try:
            ir_lineage["ir_schema_version"] = int(args.ir_schema_version)
        except ValueError:
            ir_lineage["ir_schema_version"] = args.ir_schema_version
    if args.ir_content_hash:
        ir_lineage["ir_content_hash"] = args.ir_content_hash
    provenance: dict = {}
    if args.image_id:
        provenance["image_id"] = args.image_id
    if args.image_created:
        provenance["image_created"] = args.image_created
    if args.source_sha256:
        provenance["trading_lab_source_sha256"] = args.source_sha256

    parameters = build_parameters_blob(cfg, extra, ir_lineage or None, provenance or None)

    ir_schema_ver = None
    if args.ir_schema_version:
        try:
            ir_schema_ver = int(args.ir_schema_version)
        except ValueError:
            ir_schema_ver = int(float(args.ir_schema_version))

    record = StrategyRunRecord.from_lean_summary(
        summary,
        backtest_results=backtest_results,
        run_id=args.run_id,
        strategy_id=args.repo_name,
        period_start=args.period_start,
        period_end=args.period_end,
        run_type=args.run_type,
        strategy_repo_url=args.repo_url or "local",
        git_commit=args.commit_sha or "local",
        git_branch=args.git_branch or "local",
        trigger=args.trigger,
        image=args.image or "",
        parameters=parameters,
        ir_id=args.ir_id or None,
        ir_schema_version=ir_schema_ver,
        ir_content_hash=args.ir_content_hash or None,
    )

    post_jsoneachrow(host, port, user, password, "strategy_runs", record.to_clickhouse_row())

    def insert_artifact(artifact_type: str, content: str) -> None:
        if not content:
            return
        art = ArtifactRecord(
            run_id=args.run_id,
            strategy_id=args.repo_name,
            run_timestamp=record.run_timestamp,
            artifact_type=artifact_type,
            artifact_json=content,
        )
        post_jsoneachrow(host, port, user, password, "strategy_run_artifacts", art.to_clickhouse_row())

    insert_artifact("summary", json.dumps(summary, separators=(",", ":")))
    insert_artifact("backtest_results", backtest_content)
    insert_artifact("order_events", read_text(args.order_events_json))
    insert_artifact("backtest_day_snapshots", read_text(args.day_snapshots_json))
    insert_artifact("accounting_ledger", read_text(args.accounting_json))

    print(f"Inserted run_id={args.run_id} run_type={args.run_type} into ClickHouse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
