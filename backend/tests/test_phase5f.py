"""Phase 5F: whole-course plan. The AI picks tasks, order and minutes; the server places them on a
weekly timeline (schedule.py), validates counts, titles and budget, and every reader copes with
tasks saved before the field existed. Fake AI and in-memory store only."""

import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from ai_client import MAX_RETRIES
from store import get_store
from tests.test_phase4_plan import FakeAIClient, PLAN_REQUEST_BASE, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm_payload, _other_user
from tests.conftest import auth_headers

TODAY = date(2026, 10, 21)  # Wednesday; first week = Mon 2026-10-19


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _plan(tasks, **kw):
    return _raw({"tasks": tasks, "advice_title": "조언", "advice_content": "꾸준히 해 보세요.", **kw})


def _task(i, minutes=60, **kw):
    return {"title": f"과제 {i}", "description": f"설명 {i}", "estimated_minutes": minutes, **kw}


def _tasks(n, minutes=60):
    return [_task(i, minutes) for i in range(1, n + 1)]


def _generate(client, headers, request=None):
    return client.post("/api/plan/generate", json=request or PLAN_REQUEST_BASE, headers=headers)


def _confirm(client, headers, tasks, **kw):
    payload = _confirm_payload(**kw)
    payload["tasks"] = tasks
    return client.post("/api/plan/confirm", json=payload, headers=headers)


def _ctask(title, minutes=60, weekday="none"):
    return {"title": title, "description": "", "estimated_minutes": minutes, "suggested_weekday": weekday}


# ----------------------------------------------------------------------------- generate
class TestGenerate:
    def test_response_has_the_period_and_the_server_placement(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_plan([_task(1, 120), _task(2, 90), _task(3, 150), _task(4, 240)])]))
        request = {**PLAN_REQUEST_BASE, "weekly_hours": 5, "target_date": "2026-11-06"}  # Wed 10/21 .. Fri 11/06 = 17 days
        body = _generate(client, consented_headers, request).json()
        # 3 calendar weeks for the placement, but the time is 300 x 17 / 7 = 728 minutes (not 3 x 300)
        assert (body["week_count"], body["available_minutes"], body["total_estimated_minutes"]) == (3, 728, 600)
        assert body["coverage_percent"] == 82
        assert body["plan_week_start"] == "2026-10-19" and body["plan_week_end"] == "2026-11-08"  # Sunday of the target's week
        assert [t["timeline_start_minutes"] for t in body["tasks"]] == [0, 120, 210, 360]
        assert [t["plan_week_start"] for t in body["tasks"]] == ["2026-10-19", "2026-10-19", "2026-10-19", "2026-10-26"]
        assert [t["suggested_weekday"] for t in body["tasks"]] == ["mon", "wed", "fri", "tue"]  # design example
        assert [t["title"] for t in body["tasks"]] == ["과제 1", "과제 2", "과제 3", "과제 4"]  # order kept

    def test_the_model_gets_the_budget_ready_made_and_no_instruction_to_compute(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3))]))
        _generate(client, consented_headers)
        sent = fake.payloads_seen[0]
        assert {"weekly_hours", "weekly_minutes", "period_days", "week_count", "max_total_minutes"} <= set(sent)
        assert sent["period_days"] == 72 and sent["week_count"] == 10.3  # 72 days by the calendar, in weeks
        assert sent["max_total_minutes"] == sent["weekly_minutes"] * sent["period_days"] // 7 == 4320

    def test_nothing_is_saved(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_plan(_tasks(3))]))
        assert _generate(client, consented_headers).status_code == 200
        assert get_store().find("goals", user_id="test-uid-alice") == [] and get_store().find("tasks", user_id="test-uid-alice") == []

    def test_the_weekday_is_never_taken_from_the_ai(self, client: TestClient, consented_headers, override_ai):
        tasks = [{**t, "suggested_weekday": "sun"} for t in _tasks(3)]
        override_ai(FakeAIClient(raws=[_plan(tasks)]))
        body = _generate(client, consented_headers).json()
        assert [t["suggested_weekday"] for t in body["tasks"]] == ["mon", "tue", "wed"]

    @pytest.mark.parametrize("count", [1, 2, 61])
    def test_task_count_outside_3_to_60_is_rejected_with_feedback(self, client: TestClient, consented_headers, override_ai, count):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(count, 10))] * (MAX_RETRIES + 1)))
        assert _generate(client, consented_headers).status_code == 502
        assert fake.calls == MAX_RETRIES + 1 and "3개 이상 60개 이하" in fake.payloads_seen[1]["validation_error"]

    @pytest.mark.parametrize("count", [3, 60])
    def test_the_limits_are_inclusive(self, client: TestClient, consented_headers, override_ai, count):
        override_ai(FakeAIClient(raws=[_plan(_tasks(count, 30))]))
        assert len(_generate(client, consented_headers).json()["tasks"]) == count

    def test_duplicate_titles_are_rejected_with_a_count_not_the_title(self, client: TestClient, consented_headers, override_ai, caplog):
        dup = [_task(1), {**_task(2), "title": "  과제   1 "}, _task(3), {**_task(4), "title": "과제 3"}]
        fake = override_ai(FakeAIClient(raws=[_plan(dup), _plan(_tasks(3))]))
        with caplog.at_level(logging.DEBUG):
            assert _generate(client, consented_headers).status_code == 200
        assert fake.calls == 2
        assert fake.payloads_seen[1]["validation_error"] == "과제 제목이 서로 달라야 합니다. 중복된 제목이 2개 있습니다."
        assert "과제 1" not in fake.payloads_seen[1]["validation_error"]
        assert "과제 1" not in "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("pacemate"))

    def test_titles_differing_only_in_case_are_duplicates(self, client: TestClient, consented_headers, override_ai):
        tasks = [{**_task(1), "title": "Python Basics"}, {**_task(2), "title": "python basics"}, _task(3)]
        override_ai(FakeAIClient(raws=[_plan(tasks)] * (MAX_RETRIES + 1)))
        assert _generate(client, consented_headers).status_code == 502

    def test_total_over_the_available_time_gets_the_budget_feedback(self, client: TestClient, consented_headers, override_ai):
        # 420 x 72 / 7 = 4320
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 2000)), _plan(_tasks(3, 60))]))
        assert _generate(client, consented_headers).status_code == 200
        assert fake.payloads_seen[1]["previous_total_minutes"] == 6000 and fake.payloads_seen[1]["max_total_minutes"] == 4320

    def test_a_total_exactly_at_the_limit_is_accepted(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_plan(_tasks(3, 1440))]))  # 3 x 1440 = 4320
        assert _generate(client, consented_headers).status_code == 200

    def test_a_task_shorter_than_10_minutes_or_longer_than_6000_is_a_schema_error(self, client: TestClient, consented_headers, override_ai):
        for minutes in (9, 6001):
            override_ai(FakeAIClient(raws=[_plan([_task(1, minutes), _task(2), _task(3)])] * (MAX_RETRIES + 1)))
            assert _generate(client, consented_headers).status_code == 502

    def test_one_task_may_be_longer_than_a_week(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_plan([_task(1, 1000), _task(2, 600), _task(3, 60)])]))  # week = 420
        body = _generate(client, consented_headers).json()
        assert body["total_estimated_minutes"] == 1660 and [t["plan_week_start"] for t in body["tasks"]] == ["2026-10-19", "2026-11-02", "2026-11-09"]

    def test_empty_title_or_description_is_rejected(self, client: TestClient, consented_headers, override_ai):
        tasks = [{**_task(1), "description": "   "}, _task(2), _task(3)]
        override_ai(FakeAIClient(raws=[_plan(tasks)] * (MAX_RETRIES + 1)))
        assert _generate(client, consented_headers).status_code == 502

    def test_a_long_plan_asks_for_a_long_budget_only_in_this_call(self):
        import ai_client

        assert ai_client.plan_timeout_seconds() > ai_client.ai_timeout_seconds()
        assert ai_client.plan_max_output_tokens() > ai_client.ai_max_output_tokens()


# ----------------------------------------------------------------------------- confirm
class TestConfirm:
    def test_the_server_places_the_tasks_and_ignores_client_values(self, client: TestClient, consented_headers):
        tasks = [
            {**_ctask("A", 120), "plan_week_start": "2030-01-07", "timeline_start_minutes": 999, "order_index": 7},
            {**_ctask("B", 90), "timeline_start_minutes": 5},
            _ctask("C", 150),
            _ctask("D", 240),
        ]
        res = _confirm(client, consented_headers, tasks, weekly_hours=5, target="2026-11-06")
        assert res.status_code == 201
        body = res.json()["tasks"]
        assert [t["timeline_start_minutes"] for t in body] == [0, 120, 210, 360]
        assert [t["plan_week_start"] for t in body] == ["2026-10-19"] * 3 + ["2026-10-26"]
        assert [t["order_index"] for t in body] == [0, 1, 2, 3]
        assert [t["suggested_weekday"] for t in body] == ["mon", "wed", "fri", "tue"]  # none -> server default

    def test_a_weekday_the_user_picked_is_kept(self, client: TestClient, consented_headers):
        res = _confirm(client, consented_headers, [_ctask("A", 60, "sat"), _ctask("B", 60), _ctask("C", 60, "thu")])
        # sat and thu were picked by the user; the middle one (60 of 420) gets the server default tue
        assert [t["suggested_weekday"] for t in res.json()["tasks"]] == ["sat", "tue", "thu"]

    @pytest.mark.parametrize("count", [1, 2, 61])
    def test_task_count_must_be_3_to_60(self, client: TestClient, consented_headers, count):
        res = _confirm(client, consented_headers, [_ctask(f"t{i}", 10) for i in range(count)])
        assert res.status_code == 400 and res.json()["detail"]["details"]["field"] == "tasks"
        assert get_store().find("goals", user_id="test-uid-alice") == []

    def test_60_tasks_are_accepted(self, client: TestClient, consented_headers):
        assert _confirm(client, consented_headers, [_ctask(f"t{i}", 10) for i in range(60)]).status_code == 201

    def test_duplicate_titles_are_a_400_even_with_different_case_or_spacing(self, client: TestClient, consented_headers):
        res = _confirm(client, consented_headers, [_ctask("Intro  Basics"), _ctask("intro basics"), _ctask("Other")])
        assert res.status_code == 400 and get_store().find("tasks", user_id="test-uid-alice") == []

    def test_over_the_available_time_is_a_400_that_names_both_totals(self, client: TestClient, consented_headers):
        # 2026-10-21 .. 2026-11-30 = 41 days -> 420 x 41 / 7 = 2460 minutes (41 hours)
        res = _confirm(client, consented_headers, [_ctask("a", 1000), _ctask("b", 1000), _ctask("c", 1000)])
        assert res.status_code == 400
        message = res.json()["detail"]["message"]
        assert "50시간" in message and "41시간" in message  # 3000 minutes vs 2460 minutes
        assert get_store().find("goals", user_id="test-uid-alice") == []

    def test_exactly_the_available_time_is_accepted(self, client: TestClient, consented_headers):
        assert _confirm(client, consented_headers, [_ctask("a", 820), _ctask("b", 820), _ctask("c", 820)]).status_code == 201  # 2460
        assert _confirm(client, consented_headers, [_ctask("a", 820), _ctask("b", 820), _ctask("c", 821)], course="B").status_code == 400  # 2461 > 2460

    def test_a_multi_week_plan_stores_the_week_and_timeline_per_task(self, client: TestClient, consented_headers):
        res = _confirm(client, consented_headers, [_ctask("a", 600), _ctask("b", 300), _ctask("c", 300)])  # week = 420
        stored = sorted(get_store().find("tasks", user_id="test-uid-alice"), key=lambda t: t["order_index"])
        assert [t["timeline_start_minutes"] for t in stored] == [0, 600, 900]
        assert [t["plan_week_start"] for t in stored] == ["2026-10-19", "2026-10-26", "2026-11-02"]
        assert res.json()["goal"]["start_date"] == "2026-10-21"

    def test_idempotent_replay_returns_the_same_plan(self, client: TestClient, consented_headers):
        payload = {**_confirm_payload(), "client_request_id": "k5f"}
        first = client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        again = client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json()["tasks"] == first.json()["tasks"] and len(get_store().find("goals", user_id="test-uid-alice")) == 1

    def test_goal_and_data_deletion_still_remove_the_tasks(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers, _tasks_for_confirm(5)).json()["goal"]
        client.delete(f"/api/goals/{goal['id']}", headers=consented_headers)
        assert get_store().find("tasks", user_id="test-uid-alice") == []


def _tasks_for_confirm(n):
    return [_ctask(f"과제 {i}", 30) for i in range(n)]


# ----------------------------------------------------------------------------- manual task budget
def _goal(client, headers, tasks, **kw):
    return _confirm(client, headers, tasks, **kw).json()


class TestManualTaskBudget:
    def test_the_whole_learning_must_stay_within_the_available_time(self, client: TestClient, consented_headers):
        data = _goal(client, consented_headers, [_ctask("a", 800), _ctask("b", 800), _ctask("c", 800)])  # 2400 of 2460
        body = {"goal_id": data["goal"]["id"], "plan_week_start": "2026-10-19", "title": "추가", "estimated_minutes": 61}
        res = client.post("/api/tasks", json=body, headers=consented_headers)
        assert res.status_code == 400 and "가용 시간" in res.json()["detail"]["message"]
        assert client.post("/api/tasks", json={**body, "estimated_minutes": 60}, headers=consented_headers).status_code == 201

    def test_a_task_in_a_later_week_is_no_longer_limited_by_that_weeks_minutes(self, client: TestClient, consented_headers):
        data = _goal(client, consented_headers, _tasks_for_confirm(3))
        body = {"goal_id": data["goal"]["id"], "plan_week_start": "2026-11-02", "title": "먼 주", "estimated_minutes": 1500}
        assert client.post("/api/tasks", json=body, headers=consented_headers).status_code == 201

    def test_patching_minutes_checks_the_total_and_does_not_move_other_tasks(self, client: TestClient, consented_headers):
        data = _goal(client, consented_headers, [_ctask("a", 100), _ctask("b", 100), _ctask("c", 100)])
        ids = [t["id"] for t in data["tasks"]]
        res = client.patch(f"/api/tasks/{ids[0]}", json={"estimated_minutes": 500}, headers=consented_headers)
        assert res.status_code == 200 and res.json()["timeline_start_minutes"] == 0
        by_id = {t["id"]: t for t in client.get("/api/tasks", headers=consented_headers).json()}
        assert [by_id[i]["timeline_start_minutes"] for i in ids] == [0, 100, 200]  # frozen schedule
        assert client.patch(f"/api/tasks/{ids[1]}", json={"estimated_minutes": 3000}, headers=consented_headers).status_code == 400

    def test_a_hand_made_task_goes_to_the_end_of_the_timeline(self, client: TestClient, consented_headers):
        data = _goal(client, consented_headers, [_ctask("a", 100), _ctask("b", 100), _ctask("c", 100)])
        body = {"goal_id": data["goal"]["id"], "plan_week_start": "2026-10-19", "title": "끝에", "estimated_minutes": 50}
        assert client.post("/api/tasks", json=body, headers=consented_headers).json()["timeline_start_minutes"] == 300


# ----------------------------------------------------------------------------- dashboard
def _dashboard(client, headers):
    return client.get("/api/dashboard/summary", headers=headers).json()


class TestDashboardAcrossWeeks:
    PLAN = [_ctask("1장", 120), _ctask("2장", 90), _ctask("3장", 150), _ctask("4장", 240)]  # weekly 300

    def _setup(self, client, headers):
        return _goal(client, headers, self.PLAN, weekly_hours=5, target="2026-11-13")  # 4 weeks = 1200

    def test_first_week(self, client: TestClient, consented_headers):
        self._setup(client, consented_headers)
        body = _dashboard(client, consented_headers)
        assert {t["title"] for t in body["today_tasks"]} == {"1장", "2장", "3장"}
        assert body["week_scheduled_minutes"] == 300 and body["plan_total_minutes"] == 600 and body["plan_available_minutes"] == 1028  # 300 x 24 days / 7
        assert body["total_task_count"] == 4 and body["progress_percentage"] == 0

    def test_second_week_has_the_continued_task_and_the_next_one(self, client: TestClient, consented_headers, monkeypatch):
        self._setup(client, consented_headers)
        monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 27))  # Tuesday of week 2
        body = _dashboard(client, consented_headers)
        by_title = {t["title"]: t for t in body["today_tasks"]}
        assert set(by_title) == {"3장", "4장"}
        assert (by_title["3장"]["week_minutes"], by_title["3장"]["continued"]) == (60, True)
        assert (by_title["4장"]["week_minutes"], by_title["4장"]["continued"]) == (240, False)
        assert body["week_scheduled_minutes"] == 300
        assert body["today_scheduled_minutes"] == 240  # only 4장 has tuesday as its recommended weekday
        assert body["total_task_count"] == 4  # progress still counts the whole plan

    def test_a_week_with_nothing_scheduled_is_empty_but_valid(self, client: TestClient, consented_headers, monkeypatch):
        self._setup(client, consented_headers)
        monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 10))  # week 4: all 600 minutes are done by week 2
        body = _dashboard(client, consented_headers)
        assert body["today_tasks"] == [] and body["week_scheduled_minutes"] == 0 and body["today_scheduled_minutes"] == 0
        assert body["all_tasks_completed_this_week"] is False

    def test_completing_all_of_this_weeks_tasks(self, client: TestClient, consented_headers, monkeypatch):
        data = self._setup(client, consented_headers)
        monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 27))
        for t in data["tasks"][2:]:
            client.patch(f"/api/tasks/{t['id']}", json={"status": "completed"}, headers=consented_headers)
        body = _dashboard(client, consented_headers)
        assert body["all_tasks_completed_this_week"] is True and body["progress_percentage"] == 50

    def test_no_learning_has_zero_plan_numbers(self, client: TestClient, consented_headers):
        body = _dashboard(client, consented_headers)
        assert (body["week_scheduled_minutes"], body["today_scheduled_minutes"], body["plan_total_minutes"], body["plan_available_minutes"]) == (0, 0, 0, 0)


# ----------------------------------------------------------------------------- old data
class TestOldDataCompatibility:
    """Tasks saved before Phase 5F have no timeline_start_minutes (and old goals no start_date)."""

    def _old_learning(self, uid="test-uid-alice", with_start_date=True):
        store = get_store()
        goal = {
            "user_id": uid, "field": "Python 개발", "course": "옛 과정", "current_level_order": 1, "current_level_name": "입문",
            "target_level_order": 2, "target_level_name": "실무", "weekly_hours": 7, "target_date": "2026-12-31", "status": "active",
            "created_at": "2026-10-20T01:00:00Z", "updated_at": "2026-10-20T01:00:00Z",
        }
        if with_start_date:
            goal["start_date"] = "2026-10-19"
        goal = store.create("goals", goal)
        for i, minutes in enumerate((120, 90, 60)):
            store.create("tasks", {
                "user_id": uid, "goal_id": goal["id"], "plan_week_start": "2026-10-19", "title": f"옛 과제 {i}", "description": "",
                "estimated_minutes": minutes, "suggested_weekday": "none", "status": "pending", "order_index": i,
                "created_at": "2026-10-20T01:00:00Z", "updated_at": "2026-10-20T01:00:00Z",
            })
        store.update("users", uid, {"active_goal_id": goal["id"]})
        return goal

    def test_task_list_computes_the_missing_start(self, client: TestClient, consented_headers):
        goal = self._old_learning()
        tasks = client.get("/api/tasks", params={"goal_id": goal["id"]}, headers=consented_headers)
        assert tasks.status_code == 200
        assert [t["timeline_start_minutes"] for t in tasks.json()] == [0, 120, 210]

    def test_task_list_filtered_by_week_still_computes_from_all_tasks_of_the_goal(self, client: TestClient, consented_headers):
        goal = self._old_learning()
        res = client.get("/api/tasks", params={"goal_id": goal["id"], "plan_week_start": "2026-10-19"}, headers=consented_headers).json()
        assert [t["timeline_start_minutes"] for t in res] == [0, 120, 210]

    def test_dashboard_shows_the_old_tasks_in_their_week(self, client: TestClient, consented_headers):
        self._old_learning()
        body = _dashboard(client, consented_headers)
        assert len(body["today_tasks"]) == 3 and body["week_scheduled_minutes"] == 270 and body["plan_total_minutes"] == 270

    def test_old_goal_without_start_date_does_not_break_the_dashboard_or_task_budget(self, client: TestClient, consented_headers):
        goal = self._old_learning(with_start_date=False)
        assert _dashboard(client, consented_headers)["plan_available_minutes"] > 0
        body = {"goal_id": goal["id"], "plan_week_start": "2026-10-19", "title": "새로", "estimated_minutes": 30}
        assert client.post("/api/tasks", json=body, headers=consented_headers).status_code == 201

    def test_analytics_study_logs_and_insight_inputs_still_work(self, client: TestClient, consented_headers):
        goal = self._old_learning()
        assert client.get("/api/analytics/overview", headers=consented_headers).status_code == 200
        assert client.get("/api/study-logs", headers=consented_headers).status_code == 200
        assert client.get(f"/api/goals/{goal['id']}/insight", headers=consented_headers).status_code == 200

    def test_a_goal_with_a_mix_of_old_and_new_tasks_never_errors(self, client: TestClient, consented_headers):
        goal = self._old_learning()
        client.post("/api/tasks", json={"goal_id": goal["id"], "plan_week_start": "2026-10-19", "title": "새 과제", "estimated_minutes": 30}, headers=consented_headers)
        assert client.get("/api/tasks", params={"goal_id": goal["id"]}, headers=consented_headers).status_code == 200
        assert _dashboard(client, consented_headers)["total_task_count"] == 4


# ----------------------------------------------------------------------------- access
def test_other_users_tasks_do_not_appear_in_my_dashboard_numbers(client: TestClient, consented_headers):
    _goal(client, consented_headers, _tasks_for_confirm(3))
    bob = _other_user(client)
    _confirm(client, bob, _tasks_for_confirm(4))
    assert _dashboard(client, consented_headers)["total_task_count"] == 3
    assert _dashboard(client, bob)["total_task_count"] == 4
