from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from sigmarail.scheduler import next_scheduled_run


def test_schedule_uses_next_weekday_at_local_time():
    zone = ZoneInfo("America/New_York")
    now = datetime(2026, 11, 24, 19, 59, tzinfo=zone)

    result = next_scheduled_run(now)

    assert result == datetime(2026, 11, 24, 20, 0, tzinfo=zone)


def test_schedule_skips_weekend():
    zone = ZoneInfo("America/New_York")
    now = datetime(2026, 11, 27, 20, 0, tzinfo=zone)

    result = next_scheduled_run(now)

    assert result == datetime(2026, 11, 30, 20, 0, tzinfo=zone)


def test_schedule_preserves_local_time_across_dst():
    zone = ZoneInfo("America/New_York")
    now = datetime(2026, 3, 6, 20, 1, tzinfo=zone)

    result = next_scheduled_run(now)

    assert result == datetime(2026, 3, 9, 20, 0, tzinfo=zone)
    assert result.utcoffset().total_seconds() == -4 * 60 * 60


@pytest.mark.parametrize("schedule_time", ["24:00", "20", "x:y"])
def test_schedule_rejects_invalid_time(schedule_time):
    with pytest.raises(ValueError, match="schedule time or timezone is invalid"):
        next_scheduled_run(
            datetime(2026, 11, 24, 19, 0, tzinfo=ZoneInfo("America/New_York")),
            schedule_time=schedule_time,
        )


def test_schedule_requires_aware_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        next_scheduled_run(datetime(2026, 11, 24, 19, 0))
