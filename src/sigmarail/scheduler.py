"""Container-native weekday scheduler for the SigmaRail data updater."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, time as wall_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def next_scheduled_run(
    now: datetime, *, schedule_time: str = "20:00", timezone_name: str = "America/New_York"
) -> datetime:
    """Return the next weekday wall-clock run, honoring timezone and DST."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    try:
        timezone = ZoneInfo(timezone_name)
        hour_text, minute_text = schedule_time.split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("schedule time or timezone is invalid") from exc

    local_now = now.astimezone(timezone)
    for offset in range(8):
        candidate_date = local_now.date() + timedelta(days=offset)
        if candidate_date.weekday() >= 5:
            continue
        candidate = datetime.combine(candidate_date, wall_time(hour, minute), tzinfo=timezone)
        if candidate > local_now:
            return candidate
    raise RuntimeError("could not find the next weekday schedule")


def run_scheduler(
    update_script: Path,
    *,
    schedule_time: str = "20:00",
    timezone_name: str = "America/New_York",
    clock=None,
    sleeper=None,
    runner=None,
) -> None:
    """Wait for each scheduled time and run the single sequential update script."""
    clock = clock or (lambda: datetime.now(ZoneInfo(timezone_name)))
    sleeper = sleeper or time.sleep
    runner = runner or subprocess.run
    while True:
        scheduled = next_scheduled_run(
            clock(), schedule_time=schedule_time, timezone_name=timezone_name
        )
        delay = max(0.0, (scheduled - clock()).total_seconds())
        logger.info("Next SigmaRail data update: %s", scheduled.isoformat())
        sleeper(delay)
        logger.info("Starting SigmaRail scheduled data update")
        try:
            result = runner([str(update_script)], check=False)
            if result.returncode == 0:
                logger.info("SigmaRail data update completed successfully")
            else:
                logger.error("SigmaRail data update failed (exit %s)", result.returncode)
        except OSError:
            logger.exception("Could not start the SigmaRail data update script")


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("SIGMARAIL_SCHEDULE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    schedule_time = os.environ.get("SIGMARAIL_SCHEDULE_TIME", "20:00")
    timezone_name = os.environ.get("SIGMARAIL_SCHEDULE_TIMEZONE", "America/New_York")
    configured_script = os.environ.get("SIGMARAIL_UPDATE_SCRIPT", "")
    update_script = (
        Path(configured_script)
        if configured_script
        else Path(__file__).resolve().parents[2] / "scripts" / "daily-update.sh"
    )
    if not update_script.is_file():
        raise SystemExit(f"SigmaRail update script not found: {update_script}")
    try:
        next_scheduled_run(
            datetime.now(ZoneInfo(timezone_name)),
            schedule_time=schedule_time,
            timezone_name=timezone_name,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    logger.info("SigmaRail data updater scheduler started")
    run_scheduler(update_script, schedule_time=schedule_time, timezone_name=timezone_name)


if __name__ == "__main__":
    main()
