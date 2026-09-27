from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


def timestamp(value: Any) -> datetime | None:
    """Parse ISO instants; date-only fixture fields mean midnight India time."""
    if not isinstance(value, (str, datetime)) or not value:
        return None
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def wall_now() -> datetime:
    return datetime.now(UTC)


def date_text(value: Any, *, with_time: bool = False) -> str:
    dt = timestamp(value)
    if not dt:
        return ""
    dt = dt.astimezone(IST)
    text = f"{dt:%a}, {dt.day} {dt:%b %Y}"
    if with_time:
        text += f", {dt.strftime('%I:%M%p').lstrip('0').lower()} IST"
    return text


def days_until(value: Any, now: datetime) -> int | None:
    dt = timestamp(value)
    return (dt.astimezone(IST).date() - now.astimezone(IST).date()).days if dt else None


def plus_seconds(now: datetime, seconds: int) -> str:
    return iso(now + timedelta(seconds=seconds))
