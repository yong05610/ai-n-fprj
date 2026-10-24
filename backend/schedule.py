"""Whole-course schedule placement (Phase 5F, docs/phase5f_design.md section 3).

Pure functions, no I/O. The AI only decides the tasks, their order and their minutes; everything
here is computed deterministically by the server (and mirrored by frontend/lib/schedule.ts, which
reads the same test vectors: backend/tests/fixtures/schedule_cases.json).

Model: tasks are laid end to end on a timeline measured in minutes. Week k (0 = the week that holds
the start date) is the interval [k * weekly_minutes, (k + 1) * weekly_minutes). A task occupies
[timeline_start, timeline_start + minutes) and appears in every week it overlaps.
"""

from datetime import date, timedelta
from typing import Iterable, Optional, Sequence

import clock

WEEKDAYS = clock.WEEKDAY_BY_INDEX  # ("mon", ..., "sun")


def week_count(start_date: date, target_date: date) -> int:
    """Weeks (Monday-based, both ends included) from the week of start_date to the week of target_date."""
    first = clock.week_monday(start_date)
    last = clock.week_monday(target_date)
    return max(1, (last - first).days // 7 + 1)


def available_minutes(weekly_hours: int, weeks: int) -> int:
    return weekly_hours * 60 * weeks


def default_weekday(timeline_start: int, weekly_minutes: int) -> str:
    """Weekday of the position inside the starting week: floor((start % week) / week * 7)."""
    offset = timeline_start % weekly_minutes
    return WEEKDAYS[(offset * 7) // weekly_minutes]


def start_week_index(timeline_start: int, weekly_minutes: int) -> int:
    return timeline_start // weekly_minutes


def place_tasks(minutes_in_order: Sequence[int], weekly_minutes: int) -> list[dict]:
    """One placement per task, in the given order: timeline start, start week index and default weekday."""
    placements = []
    cursor = 0
    for minutes in minutes_in_order:
        placements.append(
            {
                "timeline_start_minutes": cursor,
                "start_week_index": start_week_index(cursor, weekly_minutes),
                "suggested_weekday": default_weekday(cursor, weekly_minutes),
            }
        )
        cursor += minutes
    return placements


def week_portions(timeline_start: int, minutes: int, weekly_minutes: int) -> dict[int, int]:
    """Scheduled minutes of one task per week index: the overlap of [start, start + minutes) with each week."""
    portions: dict[int, int] = {}
    end = timeline_start + minutes
    week = timeline_start // weekly_minutes
    while week * weekly_minutes < end:
        lo = max(timeline_start, week * weekly_minutes)
        hi = min(end, (week + 1) * weekly_minutes)
        if hi > lo:
            portions[week] = hi - lo
        week += 1
    return portions


def week_start_date(first_week_monday: date, index: int) -> date:
    return first_week_monday + timedelta(days=7 * index)


def timeline_starts(tasks: Iterable[dict]) -> dict[str, int]:
    """timeline_start_minutes per task id of ONE goal, for stored tasks.

    Read compatibility: tasks saved before Phase 5F have no `timeline_start_minutes`. For a goal
    where any task lacks it, every start is recomputed by accumulating the estimated minutes in
    order_index order, so old data never raises. A goal whose tasks all carry the field keeps the
    stored values (the schedule is frozen after confirmation).
    """
    ordered = sorted(tasks, key=lambda t: (t.get("order_index", 0), t.get("created_at", "")))
    if all(t.get("timeline_start_minutes") is not None for t in ordered):
        return {t["id"]: t["timeline_start_minutes"] for t in ordered}
    starts, cursor = {}, 0
    for t in ordered:
        starts[t["id"]] = cursor
        cursor += t["estimated_minutes"]
    return starts


def tasks_in_week(tasks: Sequence[dict], first_week_monday: date, weekly_minutes: int, week_monday: date) -> list[dict]:
    """Tasks that have scheduled minutes in the week starting on `week_monday`, with that week's portion.

    Each result is {"task": task, "week_minutes": n, "starts_here": bool}. Old tasks without a
    timeline are placed through `timeline_starts` (read compatibility). Order: order_index.
    """
    index = (week_monday - first_week_monday).days // 7
    if index < 0:
        return []
    starts = timeline_starts(tasks)
    result = []
    for t in sorted(tasks, key=lambda t: (t.get("order_index", 0), t.get("created_at", ""))):
        start = starts[t["id"]]
        portion = week_portions(start, t["estimated_minutes"], weekly_minutes).get(index)
        if portion:
            result.append({"task": t, "week_minutes": portion, "starts_here": start // weekly_minutes == index})
    return result


def first_week_monday(start_date: Optional[date]) -> Optional[date]:
    return clock.week_monday(start_date) if start_date else None
