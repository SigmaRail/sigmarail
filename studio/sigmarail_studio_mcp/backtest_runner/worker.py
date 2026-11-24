"""Host-side worker for tenant-owned SigmaRail backtest jobs.

The worker runs beside Docker Desktop so LEAN CLI can launch one isolated
container for each job. The API and Apollo MCP remain in Compose; this process
only polls the PostgreSQL job queue and uses the configured ClickHouse client
for result artifacts.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("sigmarail.backtest.worker")
_STOP = False


def _signal_stop(signum: int, _frame: Any) -> None:
    global _STOP
    logger.info("received signal %s; finishing the active backtest before stopping", signum)
    _STOP = True


def _django_setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    default_repo = Path(__file__).resolve().parents[3]
    repo_root = Path(os.environ.get("SIGMARAIL_REPO_ROOT") or default_repo).expanduser().resolve()
    backend_candidate = repo_root / "packages" / "backend"
    backend_root = str(backend_candidate if backend_candidate.is_dir() else Path("/app"))
    studio_candidate = repo_root / "studio"
    studio_root = str(studio_candidate if studio_candidate.is_dir() else repo_root)
    src_root = str(repo_root / "src")
    current = [part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
    os.environ["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([backend_root, studio_root, src_root, *current]))
    for path in reversed([backend_root, studio_root, src_root]):
        if path not in sys.path:
            sys.path.insert(0, path)
    import django

    django.setup()


def _heartbeat_path() -> Path:
    raw = os.environ.get("SIGMARAIL_BACKTEST_WORKER_HEARTBEAT", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".sigmarail-studio" / "backtest-worker.heartbeat"


def _touch_heartbeat() -> None:
    path = _heartbeat_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch()
    path.chmod(0o600)


def _claim_pending_job() -> dict[str, Any] | None:
    """Atomically reserve the oldest queued job and return its pinned inputs."""
    from django.db import transaction
    from django.utils import timezone as django_timezone

    from apps.sigmarail_bridge.models import WorkspaceBacktestReference

    logger.debug("beginning PostgreSQL queue claim")
    with transaction.atomic():
        logger.debug("querying pending backtest records")
        reference = (
            WorkspaceBacktestReference.objects.select_for_update(skip_locked=True)
            .filter(status="pending")
            .order_by("created_at")
            .first()
        )
        logger.debug("queue query completed; pending_job=%s", bool(reference))
        if reference is None:
            return None

        configuration = reference.configuration if isinstance(reference.configuration, dict) else {}
        strategy = reference.strategy_snapshot
        start_date = str(configuration.get("start_date") or "").strip()
        end_date = str(configuration.get("end_date") or "").strip()
        if not isinstance(strategy, dict) or not start_date or not end_date:
            reference.status = "failed"
            reference.error_message = "Queued backtest is missing its immutable strategy or date range."
            reference.save(update_fields=["status", "error_message", "updated_at"])
            return {"invalid": True, "job_id": reference.job_id, "error": reference.error_message}

        strategy_json = json.dumps(strategy, separators=(",", ":"), sort_keys=True)
        evaluation = configuration.get("evaluation")
        if not isinstance(evaluation, dict):
            evaluation = {}
        worker_id = os.environ.get("RUNNER_ID", socket.gethostname())
        now = django_timezone.now()
        reference.status = "running"
        progress = reference.progress if isinstance(reference.progress, dict) else {}
        progress.update({
            "runner_id": worker_id,
            "worker_claimed_at": now.isoformat(),
            "last_heartbeat": now.isoformat(),
        })
        reference.progress = progress
        reference.save(update_fields=["status", "progress", "updated_at"])
        return {
            "job_id": reference.job_id,
            "ir_id": reference.ir_id,
            "start_date": start_date,
            "end_date": end_date,
            "lean_project": str(configuration.get("lean_project") or "SigmaRailTradingLab"),
            "strategy_content_hash": reference.strategy_content_hash,
            "strategy_schema_version": configuration.get("strategy_schema_version") or 1,
            "strategy_base64": base64.b64encode(strategy_json.encode("utf-8")).decode("ascii"),
            "evaluation": {
                key: str(value)
                for key, value in evaluation.items()
                if key in {"initial-cash", "benchmark"} and value is not None
            },
        }


def _run_claimed_job(job: dict[str, Any]) -> dict[str, Any]:
    from apps.sigmarail_bridge.models import WorkspaceBacktestReference
    from sigmarail_studio_mcp.backtest_runner.runner import run_job

    job_id = str(job["job_id"])
    extra_env = {
        "SIGMARAIL_STRATEGY_BASE64": job["strategy_base64"],
        "SIGMARAIL_STRATEGY_CONTENT_HASH": job["strategy_content_hash"],
        "SIGMARAIL_STRATEGY_SCHEMA_VERSION": str(job["strategy_schema_version"]),
        **job.get("evaluation", {}),
    }
    try:
        result = run_job(
            job_id=job_id,
            ir_id=str(job["ir_id"]),
            start_date=str(job["start_date"]),
            end_date=str(job["end_date"]),
            extra_env=extra_env,
            detach=False,
            lean_project=str(job["lean_project"]),
        )
        logger.info("job %s finished with status %s", job_id, result.get("status", "unknown"))
        return result
    except Exception as exc:
        logger.exception("job %s failed before the LEAN runner could complete", job_id)
        WorkspaceBacktestReference.objects.filter(job_id=job_id, status="running").update(
            status="failed",
            error_message=f"Backtest worker failed: {type(exc).__name__}: {exc}"[:4000],
            updated_at=datetime.now(timezone.utc),
        )
        return {"job_id": job_id, "status": "failed", "error": str(exc)}


def run_worker(*, poll_seconds: float = 5.0, once: bool = False) -> int:
    _django_setup()
    from sigmarail_studio_mcp.backtest_runner.runner import preflight

    _touch_heartbeat()
    checks = preflight()
    logger.info("worker preflight: %s", json.dumps(checks, sort_keys=True, default=str))
    if not checks.get("ready"):
        logger.error("backtest worker prerequisites are not ready")
        return 2

    _touch_heartbeat()
    processed = False
    while not _STOP:
        _touch_heartbeat()
        try:
            logger.debug("checking the PostgreSQL queue for a pending job")
            job = _claim_pending_job()
        except Exception:
            logger.exception("could not inspect or claim the PostgreSQL backtest queue")
            if once:
                return 1
            time.sleep(max(1.0, poll_seconds))
            continue

        if job is None:
            if once:
                return 0
            time.sleep(max(1.0, poll_seconds))
            continue
        if job.get("invalid"):
            logger.error("rejected malformed queued job %s: %s", job.get("job_id"), job.get("error"))
            processed = True
            if once:
                return 1
            continue

        processed = True
        _run_claimed_job(job)
        if once:
            return 0

    return 0 if processed or not once else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run queued SigmaRail LEAN backtests from the primary checkout.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true", help="claim at most one queued job and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _signal_stop)
    signal.signal(signal.SIGINT, _signal_stop)
    return run_worker(poll_seconds=args.poll_seconds, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
