"""lean backtest subprocess invocation and job-state management.

Post-run result insertion follows the same pattern as backtest.yml:
  1. find *-summary.json / *.json / *-order-events.json in the output dir
  2. call VeraTradingLab/scripts/insert_strategy_run.py via subprocess
     with --run-id = job_id so strategy_runs.run_id matches backtest_jobs.job_id
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sigmarail_studio_mcp.backtest_runner.project_registry import (
    default_project_id,
    get_project,
    lean_projects_root,
    resolve_output_rel,
)


def _default_image(project: dict[str, Any] | None = None) -> str:
    """Resolve Lean Docker image: ``LEAN_IMAGE`` env wins, else project yaml, else local."""
    env = os.environ.get("LEAN_IMAGE", "").strip()
    if env:
        return env
    if project and project.get("default_image"):
        return str(project["default_image"]).strip()
    return "lean-local:latest"


def _runner_id() -> str:
    return os.environ.get("RUNNER_ID", socket.gethostname())


def _vera_query_url_for_container() -> str | None:
    """Map host ``VERA_QUERY_URL`` to a URL reachable from Lean Docker.

    Immediate MCP submits often have no host ``VERA_QUERY_URL`` (workerctl does).
    Default to the local query service via ``host.docker.internal``.
    """
    raw = (os.environ.get("VERA_QUERY_URL") or "").strip()
    if not raw:
        docker_host = os.environ.get("VERA_QUERY_DOCKER_HOST", "host.docker.internal").strip()
        port = int(os.environ.get("VERA_QUERY_PORT", "8088").strip() or "8088")
        return f"http://{docker_host}:{port}"
    from urllib.parse import urlparse

    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        docker_host = os.environ.get("VERA_QUERY_DOCKER_HOST", "host.docker.internal").strip()
        port = parsed.port or int(os.environ.get("VERA_QUERY_PORT", "8088").strip())
        scheme = parsed.scheme or "http"
        return f"{scheme}://{docker_host}:{port}".rstrip("/")
    return raw.rstrip("/")


def _can_import_lean(python_exe: str) -> bool:
    """Return True if ``python_exe -c 'import lean'`` succeeds."""
    try:
        result = subprocess.run(
            [python_exe, "-c", "import lean"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def python_for_lean() -> str:
    """Interpreter that can import the QuantConnect ``lean`` package.

    ``lean_backtest_composite.py`` imports ``lean.components...``. Studio / MCP
    venvs often lack that package even when ``lean`` is on PATH. Prefer:

    1. ``VERA_BACKTEST_PYTHON`` / ``LEAN_PYTHON``
    2. ``sys.executable`` if it can ``import lean``
    3. ``python`` next to ``shutil.which('lean')`` (pyenv shim layout)
    4. ``sys.executable`` as last resort (will fail clearly in the log)
    """
    for key in ("VERA_BACKTEST_PYTHON", "LEAN_PYTHON"):
        candidate = (os.environ.get(key) or "").strip()
        if candidate and Path(candidate).is_file() and _can_import_lean(candidate):
            return candidate

    if _can_import_lean(sys.executable):
        return sys.executable

    lean_cli = shutil.which("lean")
    if lean_cli:
        sibling = Path(lean_cli).resolve().parent / "python"
        if sibling.is_file() and _can_import_lean(str(sibling)):
            return str(sibling)
        # pyenv shims: lean → versions/X.Y.Z/bin/lean; try same version python3
        try:
            real = Path(lean_cli).resolve()
            version_python = real.parent / "python3"
            if version_python.is_file() and _can_import_lean(str(version_python)):
                return str(version_python)
        except OSError:
            pass

    return sys.executable


# Heartbeat written by vera-backtest-worker each poll cycle (idle or busy).
DEFAULT_WORKER_HEARTBEAT = Path("/tmp/vera-backtest-worker.heartbeat")


def worker_heartbeat_path() -> Path:
    raw = (os.environ.get("VERA_BACKTEST_WORKER_HEARTBEAT") or "").strip()
    return Path(raw) if raw else DEFAULT_WORKER_HEARTBEAT


def worker_heartbeat_recent(*, within_seconds: int = 120) -> bool:
    """True if the worker touched its heartbeat file recently (daemon alive)."""
    path = worker_heartbeat_path()
    try:
        age = datetime.now().timestamp() - path.stat().st_mtime
    except OSError:
        return False
    return age <= within_seconds


def _merge_extra_env(
    extra_env: dict[str, str] | None,
    *,
    lean_project: str,
) -> dict[str, str]:
    merged = dict(extra_env or {})
    merged.setdefault("lean_project", lean_project)
    return merged


# ---------------------------------------------------------------------------
# ClickHouse job-state writes (backtest_jobs table only)
# ---------------------------------------------------------------------------

def _fetch_submitted_at(client: Any, job_id: str) -> datetime | None:
    """Fetch the original submitted_at for a job so state transitions reuse the same ORDER BY key."""
    rows = client.query(
        "SELECT submitted_at FROM backtest_jobs WHERE job_id = %(jid)s LIMIT 1",
        parameters={"jid": job_id},
    )
    if rows.result_rows:
        return rows.result_rows[0][0]
    return None


def _table_has_column(client: Any, column: str) -> bool:
    rows = client.query(
        "SELECT name FROM system.columns"
        " WHERE database = currentDatabase() AND table = 'backtest_jobs' AND name = %(col)s"
        " LIMIT 1",
        parameters={"col": column},
    )
    return bool(rows.result_rows)


_SIM_DATE_RE = re.compile(r"(?:Debug:\s+|Universe\s+)(\d{4}-\d{2}-\d{2})")


def _parse_progress_from_log(
    log_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[float, str | None, str]:
    """Parse latest simulated date and compute progress percentage from lean-backtest.log."""
    if not log_path.is_file():
        return 0.0, None, ""

    try:
        size = log_path.stat().st_size
        offset = max(0, size - 32768)
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            if offset > 0:
                f.seek(offset)
            text = f.read()

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        last_line = lines[-1] if lines else ""

        sim_date_str = None
        for line in reversed(lines):
            match = _SIM_DATE_RE.search(line)
            if match:
                sim_date_str = match.group(1)
                break

        if not sim_date_str:
            return 0.0, None, last_line

        d_start = date.fromisoformat(start_date)
        d_end = date.fromisoformat(end_date)
        d_curr = date.fromisoformat(sim_date_str)

        total_days = max(1, (d_end - d_start).days)
        passed_days = max(0, min(total_days, (d_curr - d_start).days))
        progress = round(passed_days / total_days, 4)
        return progress, sim_date_str, last_line
    except Exception:
        return 0.0, None, ""


def _insert_job_state(
    client: Any,
    *,
    job_id: str,
    ir_id: str,
    start_date: str,
    end_date: str,
    status: str,
    runner_id: str = "",
    submitted_at: datetime,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    lean_output_path: str = "",
    extra_env: str = "",
    error_message: str = "",
    lean_project: str = "",
    progress_pct: float = 0.0,
    current_sim_date: str | date | None = None,
    elapsed_seconds: int = 0,
    estimated_remaining_seconds: int = 0,
    last_heartbeat: datetime | None = None,
    last_log_line: str = "",
) -> None:
    lean_project = lean_project or default_project_id()

    sim_d = None
    if current_sim_date:
        if isinstance(current_sim_date, str):
            try:
                sim_d = date.fromisoformat(current_sim_date)
            except Exception:
                sim_d = None
        elif isinstance(current_sim_date, date):
            sim_d = current_sim_date

    row_dict: dict[str, Any] = {
        "job_id": job_id,
        "ir_id": ir_id,
        "start_date": date.fromisoformat(start_date),
        "end_date": date.fromisoformat(end_date),
        "status": status,
        "runner_id": runner_id,
        "submitted_at": submitted_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "lean_output_path": lean_output_path,
        "extra_env": extra_env,
        "lean_project": lean_project,
        "error_message": error_message,
        "progress_pct": float(progress_pct),
        "current_sim_date": sim_d,
        "elapsed_seconds": int(elapsed_seconds),
        "estimated_remaining_seconds": int(estimated_remaining_seconds),
        "last_heartbeat": last_heartbeat or datetime.utcnow(),
        "last_log_line": str(last_log_line)[:500],
        "created_at": datetime.utcnow(),
    }

    available_cols = set()
    try:
        col_rows = client.query(
            "SELECT name FROM system.columns WHERE database = currentDatabase() AND table = 'backtest_jobs'"
        ).result_rows
        available_cols = {r[0] for r in col_rows}
    except Exception:
        pass

    if available_cols:
        insert_cols = [col for col in row_dict if col in available_cols]
        insert_vals = [row_dict[col] for col in insert_cols]
        client.insert("backtest_jobs", [insert_vals], column_names=insert_cols)
    else:
        base_cols = [
            "job_id", "ir_id", "start_date", "end_date", "status", "runner_id",
            "submitted_at", "started_at", "completed_at", "lean_output_path",
            "extra_env", "error_message", "created_at"
        ]
        base_vals = [row_dict[c] for c in base_cols]
        client.insert("backtest_jobs", [base_vals], column_names=base_cols)



# ---------------------------------------------------------------------------
# Preflight + log tail
# ---------------------------------------------------------------------------

def preflight(*, worker_window_minutes: int = 30) -> dict[str, Any]:
    """Check prerequisites for local lean backtest execution."""
    messages: list[str] = []

    docker_ok = False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        docker_ok = proc.returncode == 0
        if not docker_ok:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            messages.append(f"docker: {detail[0] if detail else 'docker info failed'}")
    except FileNotFoundError:
        messages.append("docker: executable not found on PATH")
    except subprocess.TimeoutExpired:
        messages.append("docker: docker info timed out")
    except Exception as exc:
        messages.append(f"docker: {exc}")

    lean_cli_ok = shutil.which("lean") is not None
    if not lean_cli_ok:
        messages.append("lean CLI not found on PATH")

    clickhouse_ok = False
    try:
        from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

        client = get_client()
        try:
            client.query("SELECT 1")
            clickhouse_ok = True
        finally:
            client.close()
    except Exception as exc:
        messages.append(f"clickhouse: {exc}")

    worker_recent = worker_heartbeat_recent(
        within_seconds=max(60, worker_window_minutes * 60)
    )
    if clickhouse_ok and not worker_recent:
        try:
            from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

            client = get_client()
            try:
                rows = client.query(
                    "SELECT count() FROM backtest_jobs"
                    " WHERE runner_id != ''"
                    "   AND started_at >= now() - toIntervalMinute(%(mins)s)",
                    parameters={"mins": worker_window_minutes},
                )
                worker_recent = bool(rows.result_rows and rows.result_rows[0][0] > 0)
            finally:
                client.close()
        except Exception as exc:
            messages.append(f"worker check: {exc}")
    if not worker_recent:
        messages.append(
            f"no worker heartbeat/activity in the last {worker_window_minutes} minutes "
            "(run: vera-backtest-workerctl start)"
        )

    ready = docker_ok and lean_cli_ok and clickhouse_ok
    return {
        "docker": docker_ok,
        "lean_cli": lean_cli_ok,
        "clickhouse": clickhouse_ok,
        "worker_recent": worker_recent,
        "ready": ready,
        "messages": messages,
        "lean_python": python_for_lean(),
    }


def tail_log(job_id: str, tail_lines: int = 200) -> dict[str, Any]:
    """Return the last N lines of lean-backtest.log for a job."""
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    tail_lines = max(1, min(int(tail_lines), 5000))
    client = get_client()
    try:
        rows = client.query(
            "SELECT lean_output_path FROM backtest_jobs FINAL"
            " WHERE job_id = %(jid)s LIMIT 1",
            parameters={"jid": job_id},
        )
        if not rows.result_rows or not rows.result_rows[0][0]:
            return {"error": f"job not found or no output path: {job_id}", "lines": []}
        output_path = Path(str(rows.result_rows[0][0]))
    finally:
        client.close()

    log_path = output_path / "lean-backtest.log"
    if not log_path.is_file():
        return {
            "job_id": job_id,
            "log_path": str(log_path),
            "lines": [],
            "error": "log file not found",
        }

    text = log_path.read_text(errors="replace")
    lines = text.splitlines()
    return {
        "job_id": job_id,
        "log_path": str(log_path),
        "lines": lines[-tail_lines:],
    }


# ---------------------------------------------------------------------------
# Post-run: insert results into strategy_runs via insert_strategy_run.py
# ---------------------------------------------------------------------------

def _ir_lineage_from_db(ir_id: str) -> tuple[str, str]:
    """Return (ir_schema_version, ir_content_hash) from strategy_algorithm_specs if present."""
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    client = get_client()
    try:
        rows = client.query(
            "SELECT spec_schema_version, algorithm_json FROM strategy_algorithm_specs FINAL"
            " WHERE ir_id = %(ir_id)s LIMIT 1",
            parameters={"ir_id": ir_id},
        )
        if not rows.result_rows:
            return "", ""
        ver, algo_json = rows.result_rows[0]
        ver_s = str(ver) if ver is not None else ""
        payload = (algo_json or "").encode("utf-8")
        content_hash = hashlib.sha256(payload).hexdigest() if payload else ""
        return ver_s, content_hash
    finally:
        client.close()


def _engine_git_info(lean_root: Path) -> tuple[str, str]:
    """Return (short_sha, branch) of the LEAN engine repo for run provenance."""
    import subprocess

    for repo in (lean_root.parent / "Lean", lean_root):
        if not (repo / ".git").exists():
            continue
        try:
            sha = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            branch = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if sha:
                return sha, (branch or "local")
        except Exception:
            continue
    return "", ""


def _docker_image_info(image: str) -> tuple[str, str]:
    """Return (short_image_id, created) of the docker image used for the run."""
    import subprocess

    if not image:
        return "", ""
    try:
        out = subprocess.run(
            ["docker", "image", "inspect", image,
             "--format", "{{.Id}}|{{.Created}}"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        if out and "|" in out:
            image_id, created = out.split("|", 1)
            short_id = image_id.replace("sha256:", "")[:12]
            return short_id, created
    except Exception:
        pass
    return "", ""


def _insert_strategy_run(
    *,
    lean_root: Path,
    project: dict[str, Any],
    output_path: Path,
    job_id: str,
    ir_id: str,
    start_date: str,
    end_date: str,
    image: str,
) -> None:
    """Replicate the 'Record run in ClickHouse' step from backtest.yml."""
    lean_cli_name = str(project.get("lean_cli_name") or project.get("id"))
    insert_script = lean_root / lean_cli_name / "scripts" / "insert_strategy_run.py"
    if not insert_script.exists():
        raise FileNotFoundError(f"insert_strategy_run.py not found: {insert_script}")

    summary_files = sorted(output_path.glob("*-summary.json"))
    if not summary_files:
        raise RuntimeError(f"No *-summary.json found in {output_path}")
    summary_json = str(summary_files[0])

    order_events_files = sorted(output_path.glob("*-order-events.json"))
    order_events_json = str(order_events_files[0]) if order_events_files else ""

    backtest_files = [
        f for f in sorted(output_path.glob("*.json"))
        if not f.name.endswith("-summary.json") and not f.name.endswith("-order-events.json")
    ]
    backtest_json = str(backtest_files[0]) if backtest_files else ""

    env = dict(os.environ)
    env.setdefault("CLICKHOUSE_HOST", "localhost")
    env.setdefault("CLICKHOUSE_PORT", "8123")
    env.setdefault("CLICKHOUSE_USER", "testuser")
    env.setdefault("CLICKHOUSE_PASSWORD", "testanalysis")
    env.setdefault("CLICKHOUSE_DATABASE", "vera")
    ir_schema_version, ir_content_hash = _ir_lineage_from_db(ir_id)
    repo_name = str(project.get("id") or lean_cli_name)
    commit_sha, git_branch = _engine_git_info(lean_root)
    image_id, image_created = _docker_image_info(image)
    cmd = [
        sys.executable, str(insert_script),
        "--run-id", job_id,
        "--run-type", "base",
        "--summary-json", summary_json,
        "--repo-name", repo_name,
        "--trigger", "mcp",
        "--period-start", start_date,
        "--period-end", end_date,
        "--image", image,
        "--ir-id", ir_id,
    ]
    if commit_sha:
        cmd += ["--commit-sha", commit_sha]
    if git_branch:
        cmd += ["--git-branch", git_branch]
    if image_id:
        cmd += ["--image-id", image_id]
    if image_created:
        cmd += ["--image-created", image_created]
    if ir_schema_version:
        cmd += ["--ir-schema-version", ir_schema_version]
    if ir_content_hash:
        cmd += ["--ir-content-hash", ir_content_hash]
    if order_events_json:
        cmd += ["--order-events-json", order_events_json]
    if backtest_json:
        cmd += ["--backtest-json", backtest_json]
    day_snapshots = output_path / "backtest_day_snapshots.json"
    if day_snapshots.is_file():
        cmd += ["--day-snapshots-json", str(day_snapshots)]
    config_json = lean_root / str(project.get("config_json") or f"{lean_cli_name}/config.json")
    if config_json.exists():
        cmd += ["--config-json", str(config_json)]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"insert_strategy_run.py failed (rc={result.returncode}): {result.stderr.strip()}"
        )


def _build_lean_cmd(
    *,
    lean_root: Path,
    project: dict[str, Any],
    output_rel: str,
    image: str,
    start_date: str,
    end_date: str,
    job_id: str,
    ir_id: str,
    extra_docker_config: str,
    container_ch_host: str,
    container_ch_port: str,
    container_ch_user: str,
    container_ch_password: str,
    container_ch_database: str,
    data_mode: str | None = None,
    extra_env: dict[str, str] | None = None,
    vera_query_url: str | None = None,
    vera_query_api_key: str | None = None,
) -> list[str]:
    """Build argv for lean_backtest_composite.py (matches smoke_backtest_local.sh)."""
    wrapper = lean_root / str(project["composite_wrapper"])
    lean_config = lean_root / str(project["lean_config_overlay"])
    lean_cli_name = str(project.get("lean_cli_name") or project.get("id"))
    if not wrapper.is_file():
        raise FileNotFoundError(f"composite wrapper not found: {wrapper}")
    if not lean_config.is_file():
        raise FileNotFoundError(f"lean config overlay not found: {lean_config}")

    cmd = [
        python_for_lean(), str(wrapper),
        lean_cli_name,
        "--output", output_rel,
        "--image", image,
        "--no-update",
        "--lean-config", str(lean_config),
        "--parameter", "start-date", start_date,
        "--parameter", "end-date", end_date,
        "--parameter", "run-id", job_id,
        "--parameter", "vera-lab-id", ir_id,
        "--parameter", "clickhouse-host", container_ch_host,
        "--parameter", "clickhouse-http-port", container_ch_port,
        "--parameter", "clickhouse-user", container_ch_user,
        "--parameter", "clickhouse-password", container_ch_password,
        "--parameter", "clickhouse-database", container_ch_database,
        "--parameter", "clickhouse-timeout-seconds", "300",
        "--parameter", "initialization-timeout", "1800",
        "--extra-docker-config", extra_docker_config,
    ]
    if vera_query_url:
        cmd.extend(["--parameter", "vera-query-url", vera_query_url])
    if vera_query_api_key:
        cmd.extend(["--parameter", "vera-query-api-key", vera_query_api_key])
    if data_mode:
        cmd.extend(["--parameter", "clickhouse-data-mode", data_mode])
    env = extra_env or {}
    for key in ("initial-cash", "benchmark"):
        val = env.get(key)
        if val is not None and str(val).strip():
            cmd.extend(["--parameter", key, str(val).strip()])
    return cmd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_job(
    ir_id: str,
    start_date: str,
    end_date: str,
    job_id: str | None = None,
    extra_env: dict[str, str] | None = None,
    lean_project: str | None = None,
) -> str:
    """INSERT a pending job record into backtest_jobs. Returns the job_id."""
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    lean_project = lean_project or default_project_id()
    get_project(lean_project)  # validate registry entry
    job_id = job_id or str(uuid.uuid4())
    now = datetime.utcnow()
    merged_env = _merge_extra_env(extra_env, lean_project=lean_project)
    client = get_client()
    try:
        _insert_job_state(
            client,
            job_id=job_id,
            ir_id=ir_id,
            start_date=start_date,
            end_date=end_date,
            status="pending",
            submitted_at=now,
            extra_env=json.dumps(merged_env),
            lean_project=lean_project,
        )
    finally:
        client.close()
    return job_id


def run_job(
    job_id: str,
    ir_id: str,
    start_date: str,
    end_date: str,
    extra_env: dict[str, str] | None = None,
    detach: bool = True,
    lean_project: str | None = None,
) -> dict[str, Any]:
    """Claim and execute a backtest job via lean backtest subprocess.

    detach=True  — fire and forget (MCP interactive use); returns immediately.
    detach=False — blocking (worker daemon); waits for completion and posts results.
    """
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    lean_project = lean_project or default_project_id()
    if extra_env and extra_env.get("lean_project"):
        lean_project = str(extra_env["lean_project"])
    project = get_project(lean_project)

    lean_root = lean_projects_root()
    image = _default_image(project)
    runner_id = _runner_id()
    output_rel = resolve_output_rel(lean_project, job_id, root=lean_root)
    output_path = lean_root / output_rel
    output_path.mkdir(parents=True, exist_ok=True)

    container_ch_host = os.environ.get("CLICKHOUSE_DOCKER_HOST", "host.docker.internal")
    container_ch_port = os.environ.get("CLICKHOUSE_PORT", "8123")
    container_ch_user = os.environ.get("CLICKHOUSE_USER", "testuser")
    container_ch_password = os.environ.get("CLICKHOUSE_PASSWORD", "testanalysis")
    container_ch_database = os.environ.get("CLICKHOUSE_DATABASE", "vera")

    merged_env = _merge_extra_env(extra_env, lean_project=lean_project)
    docker_env: dict[str, str] = {
        "VERA_LAB_ID": ir_id,
        "VERA_DEPLOYMENT_ID": merged_env.get("deployment-id", ""),
        "CLICKHOUSE_HOST": container_ch_host,
        "CLICKHOUSE_PORT": container_ch_port,
        "CLICKHOUSE_USER": container_ch_user,
        "CLICKHOUSE_PASSWORD": container_ch_password,
        "CLICKHOUSE_DATABASE": container_ch_database,
    }
    query_url = _vera_query_url_for_container()
    if query_url:
        docker_env["VERA_QUERY_URL"] = query_url
    query_key = (os.environ.get("VERA_QUERY_API_KEY") or "").strip()
    if query_key:
        docker_env["VERA_QUERY_API_KEY"] = query_key
    docker_env.update({k: v for k, v in merged_env.items() if k != "lean_project"})
    extra_docker_config = json.dumps({"environment": docker_env})

    cmd = _build_lean_cmd(
        lean_root=lean_root,
        project=project,
        output_rel=output_rel,
        image=image,
        start_date=start_date,
        end_date=end_date,
        job_id=job_id,
        ir_id=ir_id,
        extra_docker_config=extra_docker_config,
        container_ch_host=container_ch_host,
        container_ch_port=container_ch_port,
        container_ch_user=container_ch_user,
        container_ch_password=container_ch_password,
        container_ch_database=container_ch_database,
        data_mode=merged_env.get("data_mode") or merged_env.get("data-mode") or merged_env.get("clickhouse-data-mode"),
        extra_env=merged_env,
        vera_query_url=query_url,
        vera_query_api_key=query_key or None,
    )

    log_path = output_path / "lean-backtest.log"
    started_at = datetime.utcnow()

    client = get_client()
    try:
        original_submitted_at = _fetch_submitted_at(client, job_id) or started_at
        _insert_job_state(
            client,
            job_id=job_id,
            ir_id=ir_id,
            start_date=start_date,
            end_date=end_date,
            status="running",
            runner_id=runner_id,
            submitted_at=original_submitted_at,
            started_at=started_at,
            lean_output_path=str(output_path),
            extra_env=json.dumps(merged_env),
            lean_project=lean_project,
        )
    finally:
        client.close()

    if detach:
        detach_cmd = [
            sys.executable, "-m", "sigmarail_studio_mcp.backtest_runner.run_and_insert",
            "--job-id", job_id,
            "--ir-id", ir_id,
            "--start-date", start_date,
            "--end-date", end_date,
            "--extra-env", json.dumps(merged_env),
            "--lean-project", lean_project,
        ]
        with open(log_path, "wb") as log_fh:
            proc = subprocess.Popen(
                detach_cmd,
                cwd=str(lean_root),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return {
            "job_id": job_id,
            "status": "running",
            "lean_project": lean_project,
            "pid": proc.pid,
            "log_path": str(log_path),
            "output_path": str(output_path),
        }

    with open(log_path, "wb") as log_fh:
        proc = subprocess.Popen(
            cmd, cwd=str(lean_root), stdout=log_fh, stderr=subprocess.STDOUT,
        )

        stop_telemetry = threading.Event()

        def _telemetry_worker() -> None:
            client_t = get_client()
            try:
                while not stop_telemetry.is_set():
                    time.sleep(2.0)
                    if proc.poll() is not None:
                        break
                    prog, sim_d, last_line = _parse_progress_from_log(log_path, start_date, end_date)
                    elapsed = int((datetime.utcnow() - started_at).total_seconds())
                    est_rem = max(0, int((elapsed / prog) - elapsed)) if prog > 0.02 else 0

                    try:
                        status_rows = client_t.query(
                            "SELECT status FROM backtest_jobs FINAL WHERE job_id = %(jid)s LIMIT 1",
                            parameters={"jid": job_id},
                        ).result_rows
                        if status_rows and status_rows[0][0] == "cancelled":
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            break
                    except Exception:
                        pass

                    try:
                        _insert_job_state(
                            client_t,
                            job_id=job_id,
                            ir_id=ir_id,
                            start_date=start_date,
                            end_date=end_date,
                            status="running",
                            runner_id=runner_id,
                            submitted_at=original_submitted_at,
                            started_at=started_at,
                            lean_output_path=str(output_path),
                            extra_env=json.dumps(merged_env),
                            lean_project=lean_project,
                            progress_pct=prog,
                            current_sim_date=sim_d,
                            elapsed_seconds=elapsed,
                            estimated_remaining_seconds=est_rem,
                            last_heartbeat=datetime.utcnow(),
                            last_log_line=last_line,
                        )
                    except Exception:
                        pass
            finally:
                client_t.close()

        telemetry_thread = threading.Thread(target=_telemetry_worker, daemon=True)
        telemetry_thread.start()

        returncode = proc.wait()
        stop_telemetry.set()
        telemetry_thread.join(timeout=3.0)

    completed_at = datetime.utcnow()
    succeeded = returncode == 0

    code_snapshot = output_path / "code"
    if code_snapshot.exists():
        shutil.rmtree(code_snapshot, ignore_errors=True)

    log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
    if "Engine.Main(): Analysis Complete" not in log_text:
        succeeded = False

    is_cancelled = False
    client = get_client()
    try:
        status_rows = client.query(
            "SELECT status FROM backtest_jobs FINAL WHERE job_id = %(jid)s LIMIT 1",
            parameters={"jid": job_id},
        ).result_rows
        if status_rows and status_rows[0][0] == "cancelled":
            is_cancelled = True
    finally:
        client.close()

    if is_cancelled:
        final_status = "cancelled"
        error_msg = "Cancelled by user"
    else:
        final_status = "done" if succeeded else "failed"
        error_msg = "" if succeeded else f"lean exited rc={returncode}"

    if succeeded and not is_cancelled:
        try:
            _insert_strategy_run(
                lean_root=lean_root,
                project=project,
                output_path=output_path,
                job_id=job_id,
                ir_id=ir_id,
                start_date=start_date,
                end_date=end_date,
                image=image,
            )
        except Exception as exc:
            final_status = "failed"
            error_msg = f"insert_strategy_run failed: {exc}"

    elapsed_final = int((completed_at - started_at).total_seconds())
    client = get_client()
    try:
        _insert_job_state(
            client,
            job_id=job_id,
            ir_id=ir_id,
            start_date=start_date,
            end_date=end_date,
            status=final_status,
            runner_id=runner_id,
            submitted_at=original_submitted_at,
            started_at=started_at,
            completed_at=completed_at,
            lean_output_path=str(output_path),
            extra_env=json.dumps(merged_env),
            error_message=error_msg,
            lean_project=lean_project,
            progress_pct=1.0 if final_status == "done" else 0.0,
            elapsed_seconds=elapsed_final,
            estimated_remaining_seconds=0,
            last_heartbeat=completed_at,
        )
    finally:
        client.close()

    return {
        "job_id": job_id,
        "status": final_status,
        "lean_project": lean_project,
        "returncode": returncode,
        "log_path": str(log_path),
        "output_path": str(output_path),
        "error_message": error_msg,
    }


def cancel_job(job_id: str) -> dict[str, Any]:
    """Mark job as cancelled in ClickHouse and attempt to terminate matching process."""
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    client = get_client()
    try:
        rows = client.query(
            "SELECT ir_id, start_date, end_date, submitted_at, started_at, lean_output_path, extra_env, lean_project"
            " FROM backtest_jobs FINAL WHERE job_id = %(jid)s LIMIT 1",
            parameters={"jid": job_id},
        ).result_rows
        if not rows:
            return {"job_id": job_id, "cancelled": False, "error": "job not found"}

        ir_id, s_date, e_date, sub_at, st_at, out_p, ex_env, l_proj = rows[0]
        _insert_job_state(
            client,
            job_id=job_id,
            ir_id=str(ir_id),
            start_date=str(s_date),
            end_date=str(e_date),
            status="cancelled",
            submitted_at=sub_at,
            started_at=st_at,
            completed_at=datetime.utcnow(),
            lean_output_path=str(out_p or ""),
            extra_env=str(ex_env or ""),
            lean_project=str(l_proj or ""),
            error_message="Cancelled by user",
            progress_pct=0.0,
            estimated_remaining_seconds=0,
        )
    finally:
        client.close()

    return {"job_id": job_id, "status": "cancelled"}


def investigate_job(
    job_id: str,
    *,
    heartbeat_stale_seconds: int = 180,
    log_stale_seconds: int = 600,
    tail_lines: int = 40,
) -> dict[str, Any]:
    """Deep-dive one job: live telemetry + log forensics + hang verdict.

    Verdicts: ``running`` (healthy), ``pending``, ``hung`` (telemetry/log stale
    while status=running), ``orphaned`` (log shows Analysis Complete but status
    still running — worker died mid-run), ``done`` / ``failed`` / ``cancelled``
    with post-run diagnostics (strategy_runs row present? error lines?).
    Includes concrete next-step hints (e.g. cancel + resubmit).
    """
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    job_id = job_id.strip()
    if not job_id:
        return {"error": "job_id is required", "code": "invalid_argument"}
    tail_lines = max(5, min(int(tail_lines), 200))

    client = get_client()
    try:
        rows = client.query(
            """
            SELECT ir_id, status, start_date, end_date, submitted_at, started_at,
                   completed_at, lean_output_path, error_message, progress_pct,
                   current_sim_date, elapsed_seconds, estimated_remaining_seconds,
                   last_heartbeat, last_log_line
            FROM backtest_jobs FINAL WHERE job_id = %(jid)s LIMIT 1
            """,
            parameters={"jid": job_id},
        ).result_rows
        if not rows:
            return {"error": f"job not found: {job_id}", "code": "not_found"}
        (ir_id, status, s_date, e_date, sub_at, st_at, comp_at, out_p,
         err_msg, prog, sim_d, elapsed, est_rem, last_hb, last_line) = rows[0]

        run_rows: list = []
        try:
            run_rows = client.query(
                "SELECT run_id FROM strategy_runs FINAL WHERE run_id = %(jid)s LIMIT 1",
                parameters={"jid": job_id},
            ).result_rows
        except Exception:
            pass
    finally:
        client.close()

    now = datetime.utcnow()
    out: dict[str, Any] = {
        "job_id": job_id,
        "ir_id": str(ir_id),
        "status": str(status),
        "period": f"{s_date}..{e_date}",
        "error_message": str(err_msg or ""),
        "stored_progress_pct": float(prog or 0.0),
        "stored_sim_date": str(sim_d) if sim_d else None,
        "stored_elapsed_seconds": int(elapsed or 0),
        "stored_est_remaining_seconds": int(est_rem or 0),
        "strategy_run_row": bool(run_rows),
    }

    # --- Log forensics -------------------------------------------------------
    log_path = Path(str(out_p or "")) / "lean-backtest.log" if out_p else None
    log_tail: list[str] = []
    analysis_complete = False
    log_age_seconds: int | None = None
    fresh_prog: float | None = None
    fresh_sim: str | None = None
    if log_path is not None and log_path.is_file():
        try:
            mtime = datetime.utcfromtimestamp(log_path.stat().st_mtime)
            log_age_seconds = int((now - mtime).total_seconds())
        except Exception:
            log_age_seconds = None
        try:
            size = log_path.stat().st_size
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                if size > 65536:
                    f.seek(size - 65536)
                chunk = f.read()
            lines_all = chunk.splitlines()
            analysis_complete = "Engine.Main(): Analysis Complete" in chunk
            log_tail = [ln for ln in lines_all[-tail_lines:]]
            fresh_prog, fresh_sim, _ = _parse_progress_from_log(
                log_path, str(s_date), str(e_date)
            )
        except Exception:
            pass
    elif log_path is not None:
        log_age_seconds = None

    out["log_path"] = str(log_path) if log_path else ""
    out["log_exists"] = bool(log_path and log_path.is_file())
    out["log_age_seconds"] = log_age_seconds
    out["log_fresh_progress_pct"] = fresh_prog
    out["log_fresh_sim_date"] = fresh_sim
    out["analysis_complete"] = analysis_complete
    out["log_tail"] = log_tail

    heartbeat_age: int | None = None
    if last_hb is not None:
        try:
            hb = last_hb
            if isinstance(hb, str):
                hb = datetime.fromisoformat(hb)
            if hb.tzinfo is not None:
                hb = hb.replace(tzinfo=None)
            heartbeat_age = int((now - hb).total_seconds())
        except Exception:
            heartbeat_age = None
    out["heartbeat_age_seconds"] = heartbeat_age

    # --- Verdict -------------------------------------------------------------
    st = str(status)
    hints: list[str] = []
    if st in ("done", "failed", "cancelled"):
        verdict = st
        if st == "done" and not out["strategy_run_row"]:
            hints.append(
                "status=done but no strategy_runs row for this run_id — check insert_strategy_run "
                "errors in worker logs, or re-run the insert"
            )
        if st == "failed":
            err_lines = [ln for ln in log_tail if "error" in ln.lower() or "exception" in ln.lower()]
            hints.append(
                "inspect log_tail (error lines: %d); typical causes: spec compile error, "
                "missing VERA_QUERY_URL, docker image pull" % len(err_lines)
            )
        if st == "cancelled":
            hints.append("resubmit with submit_job when ready")
    elif st == "running":
        if analysis_complete:
            verdict = "orphaned"
            hints.append(
                "log shows 'Analysis Complete' but job never finalized — worker/telemetry died "
                "mid-run; verify worker alive (vera-backtest-workerctl status), then cancel + resubmit"
            )
        elif (heartbeat_age is not None and heartbeat_age > heartbeat_stale_seconds) or (
            log_age_seconds is not None and log_age_seconds > log_stale_seconds
        ):
            verdict = "hung"
            hints.append(
                f"heartbeat_age={heartbeat_age}s log_age={log_age_seconds}s exceed thresholds "
                f"({heartbeat_stale_seconds}s/{log_stale_seconds}s) — engine likely hung; "
                "cancel via cancel_backtest then resubmit"
            )
        else:
            verdict = "running"
            if fresh_prog:
                out["live_progress_pct"] = fresh_prog
                out["live_sim_date"] = fresh_sim
            hints.append("healthy — telemetry fresh; check back again or use wait_for_backtest")
    elif st == "pending":
        verdict = "pending"
        worker_alive = worker_heartbeat_recent()
        out["worker_alive"] = worker_alive
        if not worker_alive:
            hints.append("no recent worker heartbeat — worker is down; start vera-backtest-workerctl")
        else:
            hints.append("queued — worker will claim when a slot frees")
    else:
        verdict = st or "unknown"

    out["verdict"] = verdict
    out["hints"] = hints
    return out


def _lint_guard(spec_json: str) -> None:
    """Refuse an invalid spec at the only INSERT.

    ``save_spec_guarded`` already lints, but that is a *caller*; this function is the single
    write path to ``strategy_algorithm_specs`` and is reachable directly, so leaving it
    ungated means one door stayed open. Honours the same ``VERA_SPEC_LINT`` setting
    (``off`` | ``warn`` | ``enforce``, default ``enforce``).

    Skipped silently when the linter cannot be imported — this package deliberately does not
    depend on VeraBase, and the guarded path still enforces. A gate that cannot run must not
    pretend to have run, so the guarded caller reports the skip separately.
    """
    mode = (os.environ.get("VERA_SPEC_LINT") or "enforce").strip().lower()
    if mode == "off":
        return
    try:
        from vera_query_core.ir import spec_lint
    except Exception:
        return
    try:
        findings = spec_lint.lint_spec_json(
            spec_json,
            runtime_kwargs=spec_lint.resolve_runtime_kwargs(),
            dialect_modules=spec_lint.dialect_modules_from_vera_lab(),
        )
    except Exception:
        return
    errors = [f for f in findings if getattr(f, "severity", "") == "error"]
    if errors and mode == "enforce":
        detail = "; ".join(
            f"{f.code} {f.path}: {f.message}" for f in errors[:6]
        )
        raise ValueError(
            f"spec lint rejected the save: {len(errors)} error(s) — {detail}"
        )


def save_spec(
    ir_id: str,
    title: str,
    spec_json: str,
    notes: str = "",
    spec_schema_version: int | None = None,
    portfolio_json: str | None = None,
    compiler_version: str = "",
    pipeline_json: str | None = None,
    parent_ir_id: str | None = None,
    parent_content_hash: str | None = None,
    mutation_type: str = "init",
    changelog_notes: str = "",
    author_agent: str = "user",
    is_ephemeral: int = 0,
) -> dict[str, Any]:
    """INSERT a VeraLab spec into strategy_algorithm_specs.

    ``spec_json`` is the compiled VeraLabV1 (run artifact). ``pipeline_json``
    (optional) is the authored PipelineDocument for Studio/agent round-trip.
    ``portfolio_json`` (optional) is the PortfolioDocument source of truth.
    """
    from sigmarail_studio_mcp.backtest_runner.ch_client import get_client

    try:
        doc = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"spec_json is not valid JSON: {exc}") from exc

    _lint_guard(spec_json)

    if spec_schema_version is None:
        raw_ver = doc.get("schema_version")
        try:
            spec_schema_version = int(raw_ver) if raw_ver is not None else 1
        except (TypeError, ValueError):
            spec_schema_version = 1

    content_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()

    client = get_client()
    try:
        cols = [
            "ir_id",
            "spec_schema_version",
            "title",
            "algorithm_json",
            "notes",
        ]
        row: list[Any] = [ir_id, spec_schema_version, title, spec_json, notes]
        if portfolio_json is not None:
            cols.append("portfolio_json")
            row.append(portfolio_json)
        if pipeline_json is not None:
            cols.append("pipeline_json")
            row.append(pipeline_json)
        if compiler_version:
            cols.append("compiler_version")
            row.append(compiler_version)
        if parent_ir_id is not None:
            cols.append("parent_ir_id")
            row.append(parent_ir_id)
        if parent_content_hash is not None:
            cols.append("parent_content_hash")
            row.append(parent_content_hash)
        cols.append("mutation_type")
        row.append(mutation_type or "init")
        if changelog_notes:
            cols.append("changelog_notes")
            row.append(changelog_notes)
        if author_agent:
            cols.append("author_agent")
            row.append(author_agent)
        if is_ephemeral:
            cols.append("is_ephemeral")
            row.append(int(is_ephemeral))
        client.insert(
            "strategy_algorithm_specs",
            [row],
            column_names=cols,
        )
    finally:
        client.close()
    return {
        "ir_id": ir_id,
        "inserted": True,
        "spec_schema_version": spec_schema_version,
        "ir_content_hash": content_hash,
    }
