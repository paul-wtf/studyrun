from datetime import UTC, datetime, timedelta

from studyrun.ai.clock import local_day_bounds, local_month_bounds


def _utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_berlin_day_late_evening():
    now = datetime.fromisoformat("2026-11-23T23:30:00+01:00")
    assert local_day_bounds(now, "Europe/Berlin") == (
        _utc(2026, 11, 22, 23),
        _utc(2026, 11, 23, 23),
    )


def test_berlin_day_after_midnight():
    now = datetime.fromisoformat("2026-11-24T00:30:00+01:00")
    assert local_day_bounds(now, "Europe/Berlin") == (
        _utc(2026, 11, 23, 23),
        _utc(2026, 11, 24, 23),
    )


def test_berlin_day_dst():
    now = _utc(2027, 3, 28, 12)
    start, end = local_day_bounds(now, "Europe/Berlin")
    assert end - start == timedelta(hours=23)


def test_berlin_month():
    now = _utc(2026, 11, 23, 12)
    assert local_month_bounds(now, "Europe/Berlin") == (
        _utc(2026, 10, 31, 23),
        _utc(2026, 11, 30, 23),
    )
