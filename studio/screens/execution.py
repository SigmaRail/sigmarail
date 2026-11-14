"""Lean execution adapter for Screening Studio (embedded backtest runner)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from screens.ch import get_ch_client

_RUNNER_IMPORT_ERROR: str | None = None
save_spec = None  # type: ignore[misc, assignment]
submit_job = None  # type: ignore[misc, assignment]
run_job = None  # type: ignore[misc, assignment]
_runner_preflight = None  # type: ignore[misc, assignment]
_runner_tail_log = None  # type: ignore[misc, assignment]

try:
    from sigmarail_studio_mcp.backtest_runner.runner import (
        preflight as _runner_preflight,
        run_job,
        save_spec,
        submit_job,
        tail_log as _runner_tail_log,
    )
except ImportError as _exc:
    _RUNNER_IMPORT_ERROR = str(_exc)
    _runner_preflight = None
    _runner_tail_log = None

_DEFAULT_PROJECTS: list[dict[str, Any]] = [
    {
        "id": "SigmaRailTradingLab",
        "label": "SigmaRail Trading Lab",
        "lean_cli_name": "sigmarail-run",
        "spec_kinds": ["VeraLabV1"],
        "enabled": True,
    },
]


def runner_available() -> bool:
    return submit_job is not None and run_job is not None


def spec_save_available() -> bool:
    return save_spec is not None


def runner_unavailable_detail() -> str:
    detail = "backtest runner not available"
    if _RUNNER_IMPORT_ERROR:
        detail = f"{detail}: {_RUNNER_IMPORT_ERROR}"
    return detail


def lean_projects_root() -> Path:
    env = os.environ.get("LEAN_PROJECTS_ROOT", "").strip()
    if env:
        return Path(env)
    studio_root = Path(__file__).resolve().parents[1]
    sibling = studio_root.parent / "LeanProjects"
    if (sibling / "lean.json").exists():
        return sibling
    for parent in Path(__file__).resolve().parents:
        if (parent / "lean.json").exists():
            return parent
    return sibling


def list_lean_projects() -> dict[str, Any]:
    """Load Lean project catalog from lean_projects.yaml (with safe fallback)."""
    registry_path = lean_projects_root() / "lean_projects.yaml"
    if registry_path.is_file():
        try:
            raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            return {
                "projects": _DEFAULT_PROJECTS,
                "registry_path": str(registry_path),
                "error": f"invalid YAML: {exc}",
            }
        projects = raw.get("projects") if isinstance(raw, dict) else raw
        if isinstance(projects, list) and projects:
            enabled = [
                p for p in projects
                if isinstance(p, dict)
                and p.get("enabled", True)
                and p.get("id") not in {"VeraTradingLab", "SigmaRailTradingLab"}
            ]
            return {
                "projects": [*_DEFAULT_PROJECTS, *enabled],
                "registry_path": str(registry_path),
            }
    return {
        "projects": _DEFAULT_PROJECTS,
        "registry_path": str(registry_path),
        "note": "lean_projects.yaml not found — using SigmaRail's generated Trading Lab project",
    }


def _clickhouse_ping() -> tuple[bool, str]:
    try:
        client = get_ch_client()
        try:
            client.query("SELECT 1")
        finally:
            client.close()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _docker_available() -> tuple[bool, str]:
    docker = shutil.which("docker")
    if not docker:
        return False, "docker CLI not found on PATH"
    try:
        proc = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "docker info failed").strip()
        return False, err[:500]
    return True, "ok"


def _lean_cli_available() -> tuple[bool, str]:
    lean = shutil.which("lean")
    if not lean:
        return False, "lean CLI not found on PATH"
    return True, lean


def _worker_recent(*, within_minutes: int = 10) -> tuple[bool, str]:
    # Prefer daemon heartbeat (idle worker still healthy).
    try:
        from sigmarail_studio_mcp.backtest_runner.runner import worker_heartbeat_recent

        if worker_heartbeat_recent(within_seconds=max(90, within_minutes * 60)):
            return True, "worker heartbeat recent"
    except Exception:
        pass

    try:
        client = get_ch_client()
        try:
            rows = client.query(
                "SELECT max(completed_at) AS last_done,"
                "       max(started_at) AS last_started"
                " FROM backtest_jobs FINAL"
                " WHERE status IN ('running', 'done')"
            )
        finally:
            client.close()
    except Exception as exc:
        return False, f"could not query worker activity: {exc}"

    if not rows.result_rows:
        return False, "no recent worker activity in backtest_jobs"

    last_done, last_started = rows.result_rows[0]
    latest = last_done or last_started
    if latest is None:
        return False, "no completed or running jobs yet"

    if isinstance(latest, datetime):
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
        if latest >= cutoff:
            return True, f"activity within {within_minutes}m"
        return False, f"last activity {latest.isoformat()} (>{within_minutes}m ago)"
    return False, "could not parse worker timestamps"


def execution_health() -> dict[str, Any]:
    """Preflight checks for Compose panel (runner preflight when available)."""
    if _runner_preflight is not None:
        try:
            out = _runner_preflight()
            if isinstance(out, dict):
                return out
        except Exception as exc:
            return {
                "docker": False,
                "lean_cli": False,
                "clickhouse": False,
                "worker_recent": False,
                "ready": False,
                "messages": [f"preflight failed: {exc}"],
            }

    messages: list[str] = []
    docker_ok, docker_msg = _docker_available()
    lean_ok, lean_msg = _lean_cli_available()
    ch_ok, ch_msg = _clickhouse_ping()
    worker_ok, worker_msg = _worker_recent()

    if not docker_ok:
        messages.append(f"docker: {docker_msg}")
    if not lean_ok:
        messages.append(f"lean_cli: {lean_msg}")
    if not ch_ok:
        messages.append(f"clickhouse: {ch_msg}")
    if not worker_ok:
        messages.append(f"worker: {worker_msg}")
    if not runner_available():
        messages.append(runner_unavailable_detail())

    ready = runner_available() and ch_ok and (docker_ok or worker_ok)
    return {
        "docker": docker_ok,
        "lean_cli": lean_ok,
        "clickhouse": ch_ok,
        "worker_recent": worker_ok,
        "ready": ready,
        "messages": messages,
        "docker_detail": docker_msg,
        "lean_cli_detail": lean_msg,
        "clickhouse_detail": ch_msg,
        "worker_detail": worker_msg,
    }


def _merge_extra_env(
    extra_env: dict[str, str] | None,
    *,
    lean_project: str,
) -> dict[str, str]:
    merged = dict(extra_env or {})
    merged.setdefault("lean_project", lean_project)
    return merged


def _call_submit_job(
    *,
    ir_id: str,
    start_date: str,
    end_date: str,
    lean_project: str,
    extra_env: dict[str, str] | None,
    job_id: str | None = None,
) -> str:
    merged = _merge_extra_env(extra_env, lean_project=lean_project)
    kwargs: dict[str, Any] = {
        "ir_id": ir_id,
        "start_date": start_date,
        "end_date": end_date,
        "extra_env": merged,
    }
    if job_id:
        kwargs["job_id"] = job_id
    try:
        return submit_job(**kwargs, lean_project=lean_project)
    except TypeError:
        return submit_job(**kwargs)


def _call_run_job(
    *,
    job_id: str,
    ir_id: str,
    start_date: str,
    end_date: str,
    lean_project: str,
    extra_env: dict[str, str] | None,
) -> dict[str, Any]:
    merged = _merge_extra_env(extra_env, lean_project=lean_project)
    kwargs: dict[str, Any] = {
        "job_id": job_id,
        "ir_id": ir_id,
        "start_date": start_date,
        "end_date": end_date,
        "extra_env": merged,
        "detach": True,
    }
    try:
        return run_job(**kwargs, lean_project=lean_project)
    except TypeError:
        return run_job(**kwargs)


def submit_backtest_job(
    *,
    ir_id: str,
    start_date: str,
    end_date: str,
    lean_project: str = "SigmaRailTradingLab",
    immediate: bool = False,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Enqueue (and optionally run) a backtest job."""
    if not runner_available():
        raise RuntimeError(runner_unavailable_detail())

    lean_project = (lean_project or "SigmaRailTradingLab").strip()
    job_id = _call_submit_job(
        ir_id=ir_id,
        start_date=start_date,
        end_date=end_date,
        lean_project=lean_project,
        extra_env=extra_env,
    )
    result: dict[str, Any] = {
        "job_id": job_id,
        "status": "pending",
        "lean_project": lean_project,
    }
    if immediate:
        run_out = _call_run_job(
            job_id=job_id,
            ir_id=ir_id,
            start_date=start_date,
            end_date=end_date,
            lean_project=lean_project,
            extra_env=extra_env,
        )
        result.update(run_out)
    return result


def list_recent_jobs(
    *,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """List recent backtest jobs (latest row per job_id)."""
    limit = max(1, min(int(limit), 200))
    status_filter = (status or "").strip().lower()
    params: dict[str, Any] = {"lim": limit}
    having = ""
    if status_filter:
        having = " HAVING argMax(status, created_at) = %(status)s"
        params["status"] = status_filter

    sql = (
        "SELECT job_id,"
        "  argMax(ir_id, created_at) AS ir_id,"
        "  argMax(start_date, created_at) AS start_date,"
        "  argMax(end_date, created_at) AS end_date,"
        "  argMax(status, created_at) AS status,"
        "  argMax(runner_id, created_at) AS runner_id,"
        "  min(submitted_at) AS submitted_at,"
        "  argMax(started_at, created_at) AS started_at,"
        "  argMax(completed_at, created_at) AS completed_at,"
        "  argMax(lean_output_path, created_at) AS lean_output_path,"
        "  argMax(lean_project, created_at) AS lean_project,"
        "  argMax(extra_env, created_at) AS extra_env,"
        "  argMax(error_message, created_at) AS error_message,"
        "  argMax(progress_pct, created_at) AS progress_pct,"
        "  argMax(current_sim_date, created_at) AS current_sim_date,"
        "  argMax(elapsed_seconds, created_at) AS elapsed_seconds,"
        "  argMax(estimated_remaining_seconds, created_at) AS estimated_remaining_seconds,"
        "  argMax(last_heartbeat, created_at) AS last_heartbeat,"
        "  argMax(last_log_line, created_at) AS last_log_line,"
        "  max(created_at) AS created_at_max"
        " FROM backtest_jobs"
        " GROUP BY job_id"
        f"{having}"
        " ORDER BY"
        "  CASE WHEN status IN ('running', 'pending') THEN 0 ELSE 1 END ASC,"
        "  submitted_at DESC"
        " LIMIT %(lim)s"
    )

    client = get_ch_client()
    try:
        rows = client.query(sql, parameters=params)
    finally:
        client.close()

    jobs = []
    for r in rows.result_rows:
        row = dict(zip(rows.column_names, r))
        if "created_at_max" in row and "created_at" not in row:
            row["created_at"] = row["created_at_max"]
        jobs.append(row)
    return {"jobs": jobs, "count": len(jobs)}


def cancel_backtest_job(job_id: str) -> dict[str, Any]:
    """Cancel a running or pending backtest job."""
    from screens.backtest_jobs import cancel_job
    return cancel_job(job_id)


def _resolve_log_path(job_id: str) -> Path | None:
    from screens.backtest_jobs import get_job_status

    client = get_ch_client()
    try:
        row = get_job_status(client, job_id)
    finally:
        client.close()
    if not row:
        return None
    output_path = str(row.get("lean_output_path") or "").strip()
    if output_path:
        log_path = Path(output_path) / "lean-backtest.log"
        if log_path.is_file():
            return log_path
    root = lean_projects_root()
    for candidate in (
        root / ".sigmarail" / "runs" / job_id / "project" / "results" / job_id / "lean-backtest.log",
        root / "results" / job_id / "lean-backtest.log",
    ):
        if candidate.is_file():
            return candidate
    return None


def get_job_log_tail(job_id: str, *, tail: int = 200) -> dict[str, Any]:
    """Return trailing lines from lean-backtest.log for a job."""
    job_id = (job_id or "").strip()
    if not job_id:
        raise ValueError("job_id is required")

    tail = max(1, min(int(tail), 2000))

    if _runner_tail_log is not None:
        try:
            try:
                out = _runner_tail_log(job_id, tail_lines=tail)
            except TypeError:
                out = _runner_tail_log(job_id, tail=tail)
            if isinstance(out, dict):
                return out
        except Exception:
            pass

    log_path = _resolve_log_path(job_id)
    if log_path is None:
        return {
            "job_id": job_id,
            "log_path": None,
            "lines": [],
            "text": "",
            "error": "log file not found",
        }

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "job_id": job_id,
            "log_path": str(log_path),
            "lines": [],
            "text": "",
            "error": str(exc),
        }

    lines = content.splitlines()
    tail_lines = lines[-tail:]
    return {
        "job_id": job_id,
        "log_path": str(log_path),
        "lines": tail_lines,
        "text": "\n".join(tail_lines),
        "line_count": len(tail_lines),
    }


__all__ = [
    "execution_health",
    "get_job_log_tail",
    "lean_projects_root",
    "list_lean_projects",
    "list_recent_jobs",
    "runner_available",
    "runner_unavailable_detail",
    "save_spec",
    "spec_save_available",
    "submit_backtest_job",
]
