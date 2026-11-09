"""CR-014 (E-3): GET /api/tasks says, per task, whether it is placed in this week - with the same
rule as the dashboard (schedule.tasks_in_week). Memory store only."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from tests.test_phase5b_multi import _other_user
from tests.test_phase5f import _confirm, _ctask, _dashboard, _goal

PLAN = [_ctask("1장", 120), _ctask("2장", 90), _ctask("3장", 150), _ctask("4장", 240)]  # weekly 300, 4 weeks


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 21))  # Wednesday of week 1


def _flags(client, headers, **query):
    rows = client.get("/api/tasks", params=query, headers=headers).json()
    return {r["title"]: r["in_current_week"] for r in rows}


def _setup(client, headers):
    return _goal(client, headers, PLAN, weekly_hours=5, target="2026-11-13")


def test_first_week_marks_the_tasks_placed_in_it(client: TestClient, consented_headers):
    _setup(client, consented_headers)
    assert _flags(client, consented_headers) == {"1장": True, "2장": True, "3장": True, "4장": False}


def test_a_task_spanning_two_weeks_is_in_both(client: TestClient, consented_headers, monkeypatch):
    _setup(client, consented_headers)
    monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 27))  # week 2: 3장 continues (60 min), 4장 starts
    assert _flags(client, consented_headers) == {"1장": False, "2장": False, "3장": True, "4장": True}


def test_a_week_with_nothing_placed_has_no_task_in_it(client: TestClient, consented_headers, monkeypatch):
    _setup(client, consented_headers)
    monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 10))
    assert set(_flags(client, consented_headers).values()) == {False}


def test_a_filtered_list_still_uses_the_whole_learning_timeline(client: TestClient, consented_headers, monkeypatch):
    data = _setup(client, consented_headers)
    monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 27))
    rows = client.get("/api/tasks", params={"goal_id": data["goal"]["id"], "plan_week_start": "2026-10-19"}, headers=consented_headers).json()
    # whatever the filter returns, 3장 (continued into week 2) is still marked from the full timeline
    assert {r["title"]: r["in_current_week"] for r in rows}.get("3장", True) is True


def test_same_tasks_as_the_dashboard_for_every_week(client: TestClient, consented_headers, monkeypatch):
    _setup(client, consented_headers)
    for day in (date(2026, 10, 21), date(2026, 10, 27), date(2026, 11, 3), date(2026, 11, 10)):
        monkeypatch.setattr(clock, "today", lambda day=day: day)
        flags = _flags(client, consented_headers)
        dash = {t["title"] for t in _dashboard(client, consented_headers)["today_tasks"]}
        assert {k for k, v in flags.items() if v} == dash, day


def test_each_learning_uses_its_own_timeline(client: TestClient, consented_headers):
    _setup(client, consented_headers)
    _confirm(client, consented_headers, [_ctask("영어 1", 60), _ctask("영어 2", 60), _ctask("영어 3", 60)], weekly_hours=5, target="2026-11-13")
    flags = _flags(client, consented_headers)
    assert flags["영어 1"] and flags["영어 3"] and flags["1장"] and not flags["4장"]


def test_other_users_tasks_are_never_returned(client: TestClient, consented_headers):
    _setup(client, consented_headers)
    bob = _other_user(client)
    _confirm(client, bob, [_ctask("밥 과제", 30), _ctask("밥 2", 30), _ctask("밥 3", 30)])
    assert "밥 과제" not in _flags(client, consented_headers)
    assert set(_flags(client, bob)) == {"밥 과제", "밥 2", "밥 3"}


def test_existing_fields_are_unchanged(client: TestClient, consented_headers):
    _setup(client, consented_headers)
    row = client.get("/api/tasks", headers=consented_headers).json()[0]
    for key in ("id", "goal_id", "title", "description", "estimated_minutes", "status", "record_count", "total_minutes", "timeline_start_minutes"):
        assert key in row
    # the field is optional in the contract: other endpoints (create/patch) do not fill it
    from schemas import TaskResponse
    assert TaskResponse.model_fields["in_current_week"].default is None
    patched = client.patch(f"/api/tasks/{row['id']}", json={"status": "completed"}, headers=consented_headers).json()
    assert patched.get("in_current_week") is None
