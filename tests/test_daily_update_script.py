from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _fake_command(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run_daily_update(tmp_path: Path, *, fail_load: bool = False) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _fake_command(fake_bin / "python", "exit 0")
    _fake_command(fake_bin / "flock", "exit 0")
    _fake_command(
        fake_bin / "sigmarail-load",
        'echo load >> "$SIGMARAIL_UPDATE_CALL_LOG"; [ "${FAIL_LOAD:-0}" = 0 ]',
    )
    _fake_command(fake_bin / "sigmarail-populate", 'echo populate >> "$SIGMARAIL_UPDATE_CALL_LOG"')
    calls = tmp_path / "calls.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            # Keep daily-update.sh from switching PATH back to the real repo venv.
            # That would resolve the actual load/populate entry points and can write production.
            "SIGMARAIL_VENV": str(tmp_path / "no-venv"),
            "SIGMARAIL_LOG_DIR": str(tmp_path / "logs"),
            "SIGMARAIL_UPDATE_CALL_LOG": str(calls),
            "FAIL_LOAD": "1" if fail_load else "0",
        }
    )
    script = Path(__file__).parents[1] / "scripts" / "daily-update.sh"
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)


def test_daily_update_runs_load_then_populate(tmp_path):
    result = _run_daily_update(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines() == ["load", "populate"]


def test_daily_update_skips_populate_after_load_failure(tmp_path):
    result = _run_daily_update(tmp_path, fail_load=True)

    assert result.returncode != 0
    assert (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines() == ["load"]
