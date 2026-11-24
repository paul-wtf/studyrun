from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def _to_utc(local: datetime) -> datetime:
    return local.astimezone(UTC)


def local_day_bounds(now: datetime, tz: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    start = datetime(local.year, local.month, local.day, tzinfo=zone)
    next_day = local.date() + timedelta(days=1)
    end = datetime(next_day.year, next_day.month, next_day.day, tzinfo=zone)
    return _to_utc(start), _to_utc(end)


def local_month_bounds(now: datetime, tz: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    start = datetime(local.year, local.month, 1, tzinfo=zone)
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    end = datetime(year, month, 1, tzinfo=zone)
    return _to_utc(start), _to_utc(end)
