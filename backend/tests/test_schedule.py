"""Phase 5F: schedule placement. The shared vectors (tests/fixtures/schedule_cases.json) are also
read by the frontend node tests, so both implementations must give the same numbers."""

import json
import os
from datetime import date

import pytest

import schedule

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "schedule_cases.json")
with open(FIXTURE, encoding="utf-8") as f:
    VECTORS = json.load(f)


@pytest.mark.parametrize("case", VECTORS["schedule"], ids=lambda c: c["name"])
def test_placements_match_the_shared_vectors(case):
    assert schedule.place_tasks(case["minutes"], case["weekly_minutes"]) == case["placements"]


@pytest.mark.parametrize("case", VECTORS["schedule"], ids=lambda c: c["name"])
def test_week_portions_match_the_shared_vectors(case):
    weekly, cursor = case["weekly_minutes"], 0
    for minutes, expected in zip(case["minutes"], case["portions"]):
        portions = schedule.week_portions(cursor, minutes, weekly)
        assert [[w, m] for w, m in sorted(portions.items())] == expected
        assert sum(portions.values()) == minutes  # nothing lost, nothing counted twice
        cursor += minutes


@pytest.mark.parametrize("case", VECTORS["schedule"], ids=lambda c: c["name"])
def test_no_week_is_over_its_weekly_minutes(case):
    weekly, cursor, per_week = case["weekly_minutes"], 0, {}
    for minutes in case["minutes"]:
        for week, part in schedule.week_portions(cursor, minutes, weekly).items():
            per_week[week] = per_week.get(week, 0) + part
        cursor += minutes
    assert all(total <= weekly for total in per_week.values())
    assert sum(per_week.values()) == sum(case["minutes"])


@pytest.mark.parametrize("case", VECTORS["week_count"], ids=lambda c: f"{c['start_date']}..{c['target_date']}")
def test_week_count_matches_the_shared_vectors(case):
    got = schedule.week_count(date.fromisoformat(case["start_date"]), date.fromisoformat(case["target_date"]))
    assert got == case["week_count"]


def test_available_minutes():
    assert schedule.available_minutes(5, 12) == 3600 and schedule.available_minutes(10, 1) == 600


def test_design_example_by_hand():
    placements = schedule.place_tasks([120, 90, 150, 240], 300)
    assert [p["timeline_start_minutes"] for p in placements] == [0, 120, 210, 360]
    assert [p["start_week_index"] for p in placements] == [0, 0, 0, 1]
    assert schedule.week_portions(210, 150, 300) == {0: 90, 1: 60}
    assert schedule.week_portions(360, 240, 300) == {1: 240}


def test_default_weekday_is_never_out_of_range_even_at_the_last_minute():
    assert schedule.default_weekday(299, 300) == "sun" and schedule.default_weekday(300, 300) == "mon"


def _task(id_, order, minutes, start=None, created="2026-10-21T00:00:00Z"):
    task = {"id": id_, "order_index": order, "estimated_minutes": minutes, "created_at": created}
    if start is not None:
        task["timeline_start_minutes"] = start
    return task


class TestStoredTasks:
    def test_stored_starts_are_kept(self):
        tasks = [_task("a", 0, 100, 0), _task("b", 1, 100, 100)]
        assert schedule.timeline_starts(tasks) == {"a": 0, "b": 100}

    def test_goal_without_the_field_is_accumulated_in_order_index_order(self):
        tasks = [_task("b", 1, 90), _task("a", 0, 120), _task("c", 2, 60)]
        assert schedule.timeline_starts(tasks) == {"a": 0, "b": 120, "c": 210}

    def test_a_goal_with_some_missing_starts_is_recomputed_as_a_whole_without_error(self):
        tasks = [_task("a", 0, 100, 0), _task("b", 1, 100)]
        assert schedule.timeline_starts(tasks) == {"a": 0, "b": 100}

    def test_tasks_in_week_lists_started_and_continued_tasks(self):
        first = date(2026, 10, 19)
        tasks = [_task("a", 0, 120, 0), _task("b", 1, 90, 120), _task("c", 2, 150, 210), _task("d", 3, 240, 360)]
        week0 = schedule.tasks_in_week(tasks, first, 300, date(2026, 10, 19))
        week1 = schedule.tasks_in_week(tasks, first, 300, date(2026, 10, 26))
        assert [(r["task"]["id"], r["week_minutes"], r["starts_here"]) for r in week0] == [("a", 120, True), ("b", 90, True), ("c", 90, True)]
        assert [(r["task"]["id"], r["week_minutes"], r["starts_here"]) for r in week1] == [("c", 60, False), ("d", 240, True)]
        assert schedule.tasks_in_week(tasks, first, 300, date(2026, 11, 2)) == []
        assert schedule.tasks_in_week(tasks, first, 300, date(2026, 10, 12)) == []  # before the plan

    def test_tasks_in_week_works_for_old_data(self):
        first = date(2026, 10, 19)
        old = [_task("a", 0, 100), _task("b", 1, 100)]
        assert [r["task"]["id"] for r in schedule.tasks_in_week(old, first, 300, first)] == ["a", "b"]
