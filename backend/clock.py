"""Service-wide "today" and week-boundary helpers, pinned to Asia/Seoul.

The host process may run in any timezone (Render containers default to UTC),
so `date.today()` drifts from the Korean service day near midnight KST. Phase 4
and Phase 5 both depend on "today" and "this week" meaning the same thing;
route all such checks through this module instead of calling date.today()
directly.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SERVICE_TZ = ZoneInfo("Asia/Seoul")


def today() -> date:
    return datetime.now(SERVICE_TZ).date()


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_sunday(day: date) -> date:
    return week_monday(day) + timedelta(days=6)


def is_within_week(day: date, week_start: date) -> bool:
    return week_start <= day <= week_start + timedelta(days=6)


def date_from_utc_iso(value: str) -> date:
    """The Asia/Seoul calendar date a UTC ISO-8601 instant falls on."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(SERVICE_TZ).date()


WEEKDAY_BY_INDEX = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday(): Monday = 0
