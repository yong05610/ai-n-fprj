"""Phase 5B (MULTI): overlap rule for new goals, learning switch, goals_overview, analytics.

No AI calls; dev-mode auth and the in-memory store only. "Today" is pinned through clock.today
so the weekly boundary tests don't depend on the real date.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from store import get_store
from tests.conftest import auth_headers

TODAY = date(2026, 10, 21)  # Wednesday; week = 2026-10-19 (Mon) ~ 2026-10-25 (Sun)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _confirm_payload(course="기본문법", week_start="2026-10-19", target="2026-11-30", **overrides) -> dict:
    return {
        "field": "Python 개발",
        "course": course,
        "current_level_order": 1,
        "current_level_name": "입문자",
        "target_level_order": 2,
        "target_level_name": "실무 기초",
        "weekly_hours": 7,
        "target_date": target,
        "plan_week_start": week_start,
        "tasks": [{"title": "변수", "estimated_minutes": 60, "suggested_weekday": "mon"}],
        **overrides,
    }


def _goal_payload(course="영어 회화", target="2026-12-31") -> dict:
    return {
        "field": "영어",
        "course": course,
        "current_level_order": 1,
        "current_level_name": "입문",
        "target_level_order": 3,
        "target_level_name": "중급",
        "weekly_hours": 5,
        "target_date": target,
    }


def _confirm(client, headers, **kw):
    return client.post("/api/plan/confirm", json=_confirm_payload(**kw), headers=headers)


def _active_goal_id(client, headers) -> str:
    return client.get("/api/user/profile", headers=headers).json()["active_goal_id"]


def _other_user(client) -> dict:
    bob = auth_headers("test-uid-bob")
    client.post("/api/consent", json={"terms_version": "v1.0", "privacy_agreed": True, "ai_use_agreed": True}, headers=bob)
    return bob


class TestOverlapOnPlanConfirm:
    def test_first_goal_gets_start_date_from_plan_week_start(self, client: TestClient, consented_headers):
        res = _confirm(client, consented_headers)
        assert res.status_code == 201
        assert res.json()["goal"]["start_date"] == "2026-10-19"

    def test_same_period_is_rejected_with_409_and_details(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A과정")
        res = _confirm(client, consented_headers, course="B과정")
        assert res.status_code == 409
        err = res.json()["detail"]
        assert err["code"] == "GOAL_PERIOD_OVERLAP"
        assert "A과정" in err["message"] and "2026-10-19" in err["message"] and "2026-11-30" in err["message"]
        assert err["details"]["course"] == "A과정"
        assert err["details"]["start_date"] == "2026-10-19"
        assert err["details"]["target_date"] == "2026-11-30"

    def test_rejection_saves_nothing(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A과정")
        before_goal = _active_goal_id(client, consented_headers)
        _confirm(client, consented_headers, course="B과정")
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 1
        assert len(client.get("/api/tasks", headers=consented_headers).json()) == 1
        assert _active_goal_id(client, consented_headers) == before_goal

    def test_overlap_by_a_single_day_is_rejected(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, week_start="2026-10-19", target="2026-11-30")
        # New period starts on the first goal's last day (2026-11-30 is a Monday).
        res = _confirm(client, consented_headers, course="B", week_start="2026-11-30", target="2026-12-31")
        assert res.status_code == 409

    def test_adjacent_periods_are_allowed(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, week_start="2026-10-19", target="2026-11-29")
        res = _confirm(client, consented_headers, course="B", week_start="2026-11-30", target="2026-12-31")
        assert res.status_code == 201

    def test_new_period_enclosing_existing_is_rejected(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, week_start="2026-11-02", target="2026-11-15")
        res = _confirm(client, consented_headers, course="B", week_start="2026-10-19", target="2026-12-31")
        assert res.status_code == 409

    @pytest.mark.parametrize("status_value", ["completed", "archived"])
    def test_non_active_goals_are_not_compared(self, client: TestClient, consented_headers, status_value):
        first = _confirm(client, consented_headers).json()["goal"]
        client.patch(f"/api/goals/{first['id']}", json={"status": status_value}, headers=consented_headers)
        assert _confirm(client, consented_headers, course="B").status_code == 201

    def test_idempotent_retry_returns_200_not_overlap(self, client: TestClient, consented_headers):
        payload = _confirm_payload(client_request_id="retry-1")
        first = client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        assert first.status_code == 201
        second = client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        assert second.status_code == 200
        assert second.json()["goal"]["id"] == first.json()["goal"]["id"]
        assert second.json()["goal"]["start_date"] == "2026-10-19"

    def test_other_users_goals_are_irrelevant(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers)
        bob = _other_user(client)
        assert _confirm(client, bob).status_code == 201

    def test_invalid_input_is_reported_before_overlap(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers)
        res = client.post(
            "/api/plan/confirm", json=_confirm_payload(course="B", week_start="2026-10-20"), headers=consented_headers
        )
        assert res.status_code == 400  # not a Monday: ordinary validation comes first


class TestOverlapOnGoalsPost:
    def test_goal_post_uses_this_weeks_monday_as_start_date(self, client: TestClient, consented_headers):
        res = client.post("/api/goals", json=_goal_payload(), headers=consented_headers)
        assert res.status_code == 201
        assert res.json()["start_date"] == "2026-10-19"

    def test_goal_post_rejects_overlap_with_active_goal(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A과정")
        res = client.post("/api/goals", json=_goal_payload(), headers=consented_headers)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "GOAL_PERIOD_OVERLAP"
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 1

    def test_goal_post_allowed_after_other_goal_period_ends(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, week_start="2026-10-12", target="2026-10-18")
        res = client.post("/api/goals", json=_goal_payload(), headers=consented_headers)
        assert res.status_code == 201

    def test_patch_target_date_is_deliberately_not_checked(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, week_start="2026-10-19", target="2026-11-01")
        second = _confirm(client, consented_headers, course="B", week_start="2026-11-02", target="2026-11-30").json()["goal"]
        res = client.patch(f"/api/goals/{second['id']}", json={"target_date": "2026-12-31"}, headers=consented_headers)
        assert res.status_code == 200
        # Extending the first goal into the second one's period is also allowed (user decision).
        first_id = [g for g in client.get("/api/goals", headers=consented_headers).json() if g["course"] == "기본문법"][0]["id"]
        assert client.patch(f"/api/goals/{first_id}", json={"target_date": "2026-11-20"}, headers=consented_headers).status_code == 200


class TestLegacyGoalWithoutStartDate:
    def test_start_date_falls_back_to_created_at_kst_date(self, client: TestClient, consented_headers):
        store = get_store()
        # 2026-10-20 16:00 UTC = 2026-10-21 01:00 KST: the Seoul date, not the UTC date.
        legacy = store.create(
            "goals",
            {
                **{k: v for k, v in _goal_payload(course="옛 학습", target="2026-11-30").items()},
                "user_id": "test-uid-alice",
                "status": "active",
                "created_at": "2026-10-20T16:00:00Z",
                "updated_at": "2026-10-20T16:00:00Z",
            },
        )
        assert "start_date" not in legacy
        listed = client.get("/api/goals", headers=consented_headers).json()
        assert listed[0]["start_date"] == "2026-10-21"
        assert client.get(f"/api/goals/{legacy['id']}", headers=consented_headers).json()["start_date"] == "2026-10-21"
        assert "start_date" not in store.get("goals", legacy["id"])  # read-side only, not migrated

    def test_legacy_goal_takes_part_in_overlap_check(self, client: TestClient, consented_headers):
        get_store().create(
            "goals",
            {
                **_goal_payload(course="옛 학습", target="2026-11-30"),
                "user_id": "test-uid-alice",
                "status": "active",
                "created_at": "2026-10-20T16:00:00Z",
                "updated_at": "2026-10-20T16:00:00Z",
            },
        )
        res = _confirm(client, consented_headers, week_start="2026-11-23", target="2026-12-31")
        assert res.status_code == 409
        assert res.json()["detail"]["details"]["start_date"] == "2026-10-21"


class TestLearningSwitch:
    def _two_goals(self, client, headers):
        a = _confirm(client, headers, course="A과정", week_start="2026-10-19", target="2026-10-31").json()["goal"]
        b = _confirm(client, headers, course="B과정", week_start="2026-11-02", target="2026-11-30").json()["goal"]
        return a, b

    def test_new_registration_becomes_recent_learning(self, client: TestClient, consented_headers):
        a, b = self._two_goals(client, consented_headers)
        assert _active_goal_id(client, consented_headers) == b["id"]

    def test_switch_to_own_active_goal(self, client: TestClient, consented_headers):
        a, b = self._two_goals(client, consented_headers)
        res = client.patch("/api/user/profile", json={"active_goal_id": a["id"]}, headers=consented_headers)
        assert res.status_code == 200 and res.json()["active_goal_id"] == a["id"]
        assert _active_goal_id(client, consented_headers) == a["id"]

    def test_switch_to_other_users_goal_is_rejected(self, client: TestClient, consented_headers):
        a, _ = self._two_goals(client, consented_headers)
        bob = _other_user(client)
        res = client.patch("/api/user/profile", json={"active_goal_id": a["id"]}, headers=bob)
        assert res.status_code == 403
        assert _active_goal_id(client, bob) is None

    def test_switch_to_unknown_goal_is_404(self, client: TestClient, consented_headers):
        assert client.patch("/api/user/profile", json={"active_goal_id": "nope"}, headers=consented_headers).status_code == 404

    @pytest.mark.parametrize("status_value", ["completed", "archived"])
    def test_switch_to_inactive_goal_is_rejected(self, client: TestClient, consented_headers, status_value):
        a, b = self._two_goals(client, consented_headers)
        client.patch(f"/api/goals/{a['id']}", json={"status": status_value}, headers=consented_headers)
        res = client.patch("/api/user/profile", json={"active_goal_id": a["id"]}, headers=consented_headers)
        assert res.status_code == 400
        assert _active_goal_id(client, consented_headers) == b["id"]

    def test_switch_keeps_running_timer(self, client: TestClient, consented_headers):
        a, b = self._two_goals(client, consented_headers)
        task_a = client.get("/api/tasks", params={"goal_id": a["id"]}, headers=consented_headers).json()[0]
        assert client.post("/api/timer/start", json={"task_id": task_a["id"]}, headers=consented_headers).status_code in (200, 201)
        client.patch("/api/user/profile", json={"active_goal_id": a["id"]}, headers=consented_headers)
        client.patch("/api/user/profile", json={"active_goal_id": b["id"]}, headers=consented_headers)
        active = client.get("/api/timer/active", headers=consented_headers).json()
        assert active["active"] is True and active["task_id"] == task_a["id"]

    def test_deleting_current_goal_clears_active_goal_id(self, client: TestClient, consented_headers):
        a, b = self._two_goals(client, consented_headers)
        client.delete(f"/api/goals/{b['id']}", headers=consented_headers)
        assert _active_goal_id(client, consented_headers) is None

    def test_goal_list_is_newest_first_and_has_start_date(self, client: TestClient, consented_headers):
        a, b = self._two_goals(client, consented_headers)
        listed = client.get("/api/goals", headers=consented_headers).json()
        assert [g["id"] for g in listed] == [b["id"], a["id"]]
        assert [g["start_date"] for g in listed] == ["2026-11-02", "2026-10-19"]


def _two_goals_with_data(client, headers):
    """Goal A: 2 tasks (1 completed), 30+45 min this week. Goal B: 1 task, 20 min this week."""
    a = _confirm(
        client, headers, course="A과정", week_start="2026-10-19", target="2026-10-31",
        tasks=[
            {"title": "A1", "estimated_minutes": 60, "suggested_weekday": "mon"},
            {"title": "A2", "estimated_minutes": 60, "suggested_weekday": "tue"},
        ],
    ).json()
    b = _confirm(client, headers, course="B과정", week_start="2026-11-02", target="2026-11-30").json()
    a_tasks = sorted(a["tasks"], key=lambda t: t["order_index"])
    client.patch(f"/api/tasks/{a_tasks[0]['id']}", json={"status": "completed"}, headers=headers)
    for task_id, study_date, minutes in (
        (a_tasks[0]["id"], "2026-10-19", 30),  # Monday
        (a_tasks[1]["id"], "2026-10-21", 45),  # Wednesday
        (b["tasks"][0]["id"], "2026-10-21", 20),
        (a_tasks[1]["id"], "2026-10-18", 99),  # previous Sunday: outside this week
    ):
        res = client.post(
            "/api/study-logs",
            json={"task_id": task_id, "study_date": study_date, "minutes": minutes, "activity": "학습"},
            headers=headers,
        )
        assert res.status_code == 201, res.text
    return a["goal"], b["goal"]


class TestDashboardGoalsOverview:
    def test_overview_lists_every_active_goal_without_mixing(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        by_id = {g["goal_id"]: g for g in body["goals_overview"]}
        assert set(by_id) == {a["id"], b["id"]}
        assert (by_id[a["id"]]["completed_task_count"], by_id[a["id"]]["total_task_count"], by_id[a["id"]]["progress_percentage"]) == (1, 2, 50)
        assert (by_id[b["id"]]["completed_task_count"], by_id[b["id"]]["total_task_count"], by_id[b["id"]]["progress_percentage"]) == (0, 1, 0)
        assert by_id[a["id"]]["course"] == "A과정" and by_id[a["id"]]["start_date"] == "2026-10-19"
        assert [g["goal_id"] for g in body["goals_overview"]] == [a["id"], b["id"]]  # earliest schedule first

    def test_recent_learning_block_follows_active_goal_id(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert "B과정" in body["active_goal_title"]  # B was registered last
        assert body["total_task_count"] == 1 and body["weekly_study_minutes"] == 20
        client.patch("/api/user/profile", json={"active_goal_id": a["id"]}, headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert "A과정" in body["active_goal_title"]
        assert body["total_task_count"] == 2 and body["weekly_study_minutes"] == 75

    def test_completed_and_archived_goals_are_excluded(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        client.patch(f"/api/goals/{a['id']}", json={"status": "completed"}, headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert [g["goal_id"] for g in body["goals_overview"]] == [b["id"]]

    def test_other_users_data_is_not_included(self, client: TestClient, consented_headers):
        _two_goals_with_data(client, consented_headers)
        bob = _other_user(client)
        body = client.get("/api/dashboard/summary", headers=bob).json()
        assert body["goals_overview"] == []
        _confirm(client, bob, course="밥 학습")
        mine = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert all(g["course"] != "밥 학습" for g in mine["goals_overview"])

    def test_empty_and_single_goal(self, client: TestClient, consented_headers):
        assert client.get("/api/dashboard/summary", headers=consented_headers).json()["goals_overview"] == []
        _confirm(client, consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert len(body["goals_overview"]) == 1

    def test_stale_active_goal_id_still_returns_overview(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        client.delete(f"/api/goals/{b['id']}", headers=consented_headers)  # clears active_goal_id
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["active_goal_title"] == ""
        assert [g["goal_id"] for g in body["goals_overview"]] == [a["id"]]


class TestAnalyticsOverview:
    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.get("/api/analytics/overview").status_code == 401
        assert client.get("/api/analytics/overview", headers=mock_auth_headers).status_code == 403

    def test_empty(self, client: TestClient, consented_headers):
        body = client.get("/api/analytics/overview", headers=consented_headers).json()
        assert body == {"week_start": "2026-10-19", "week_end": "2026-10-25", "goals": []}

    def test_per_goal_weekly_minutes_and_progress(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        goals = {g["goal_id"]: g for g in client.get("/api/analytics/overview", headers=consented_headers).json()["goals"]}
        assert goals[a["id"]]["weekly_minutes_by_day"] == [30, 0, 45, 0, 0, 0, 0]  # prior Sunday's 99 excluded
        assert goals[b["id"]]["weekly_minutes_by_day"] == [0, 0, 20, 0, 0, 0, 0]
        assert goals[a["id"]]["progress_percentage"] == 50 and goals[a["id"]]["total_task_count"] == 2

    def test_numbers_match_dashboard_overview_and_weekly_records(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        analytics = client.get("/api/analytics/overview", headers=consented_headers).json()["goals"]
        overview = client.get("/api/dashboard/summary", headers=consented_headers).json()["goals_overview"]
        for x, y in zip(analytics, overview):
            for key in ("goal_id", "course", "start_date", "target_date", "completed_task_count", "total_task_count", "progress_percentage"):
                assert x[key] == y[key]
        weekly_logs = client.get("/api/study-logs", params={"period": "week"}, headers=consented_headers).json()
        assert sum(sum(g["weekly_minutes_by_day"]) for g in analytics) == sum(l["minutes"] for l in weekly_logs) == 95

    def test_study_logs_goal_filter_separates_goals(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        only_b = client.get("/api/study-logs", params={"goal_id": b["id"], "period": "all"}, headers=consented_headers).json()
        assert [l["minutes"] for l in only_b] == [20]
        only_a = client.get("/api/study-logs", params={"goal_id": a["id"], "period": "all"}, headers=consented_headers).json()
        assert sorted(l["minutes"] for l in only_a) == [30, 45, 99]

    def test_completed_goal_excluded(self, client: TestClient, consented_headers):
        a, b = _two_goals_with_data(client, consented_headers)
        client.patch(f"/api/goals/{b['id']}", json={"status": "archived"}, headers=consented_headers)
        goals = client.get("/api/analytics/overview", headers=consented_headers).json()["goals"]
        assert [g["goal_id"] for g in goals] == [a["id"]]

    def test_other_users_not_included(self, client: TestClient, consented_headers):
        _two_goals_with_data(client, consented_headers)
        bob = _other_user(client)
        assert client.get("/api/analytics/overview", headers=bob).json()["goals"] == []

    def test_week_boundary_monday_midnight_kst(self, client: TestClient, consented_headers, monkeypatch):
        a, b = _two_goals_with_data(client, consented_headers)
        # Sunday 2026-10-25 23:59 KST is still the same week; Monday 10-26 starts a new one.
        monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 25))
        sunday = client.get("/api/analytics/overview", headers=consented_headers).json()
        assert sunday["week_start"] == "2026-10-19" and sunday["goals"][0]["weekly_minutes_by_day"][0] == 30
        monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 26))
        monday = client.get("/api/analytics/overview", headers=consented_headers).json()
        assert monday["week_start"] == "2026-10-26"
        assert all(sum(g["weekly_minutes_by_day"]) == 0 for g in monday["goals"])
