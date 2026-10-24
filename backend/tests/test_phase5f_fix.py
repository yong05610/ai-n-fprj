"""Phase 5F fix: the time budget follows the real days of the period (R1), and the model gets a
realistic-amount hint while the server only reports the coverage (R2). Fake AI, memory store."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from ai_client import MAX_RETRIES
from prompts import PLAN_GENERATE_SYSTEM_PROMPT
from tests.test_phase4_plan import FakeAIClient, PLAN_REQUEST_BASE, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm_payload

TODAY = date(2026, 10, 21)  # Wednesday

# The PM's case: start on a Sunday, target 60 days later = 61 days, 5 hours a week.
SUNDAY_START, TARGET_61 = "2026-10-25", "2026-12-24"
PM_REQUEST = {**PLAN_REQUEST_BASE, "weekly_hours": 5, "start_date": SUNDAY_START, "target_date": TARGET_61}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _plan(tasks):
    return _raw({"tasks": tasks, "advice_title": "조언", "advice_content": "꾸준히 해 보세요."})


def _tasks(n, minutes):
    return [{"title": f"과제 {i}", "description": f"설명 {i}", "estimated_minutes": minutes} for i in range(1, n + 1)]


def _confirm(client, headers, tasks, **kw):
    payload = _confirm_payload(**kw)
    payload["tasks"] = [{"title": t["title"], "description": "", "estimated_minutes": t["estimated_minutes"]} for t in tasks]
    return client.post("/api/plan/confirm", json=payload, headers=headers)


class TestAvailableByRealDays:
    def test_the_pm_case_is_2614_minutes_not_3000(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 100))]))
        res = client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers)
        body = res.json()
        assert body["available_minutes"] == 2614  # floor(300 x 61 / 7)
        assert body["week_count"] == 10  # the calendar weeks for the placement are unchanged
        assert fake.payloads_seen[0]["max_total_minutes"] == 2614

    def test_a_monday_to_sunday_week_is_the_weekly_minutes(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_plan(_tasks(3, 140))]))
        request = {**PLAN_REQUEST_BASE, "weekly_hours": 7, "start_date": "2026-10-26", "target_date": "2026-11-01"}
        body = client.post("/api/plan/generate", json=request, headers=consented_headers).json()
        assert body["available_minutes"] == 420 and body["week_count"] == 1 and body["total_estimated_minutes"] == 420

    def test_the_limit_is_exact_in_generate(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 872) + [{"title": "끝", "description": "d", "estimated_minutes": 10}]), _plan(_tasks(3, 871))]))
        # 3 x 872 + 10 = 2626 > 2614 -> rejected with the new maximum as feedback; 3 x 871 = 2613 is accepted
        assert client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers).status_code == 200
        assert fake.payloads_seen[1]["previous_total_minutes"] == 2626 and fake.payloads_seen[1]["max_total_minutes"] == 2614

    def test_confirm_uses_the_same_limit(self, client: TestClient, consented_headers):
        kw = {"start": SUNDAY_START, "target": TARGET_61, "weekly_hours": 5}
        assert _confirm(client, consented_headers, _tasks(2, 871) + [{"title": "마지막", "description": "", "estimated_minutes": 872}], **kw).status_code == 201  # 2614
        res = _confirm(client, consented_headers, _tasks(2, 871) + [{"title": "마지막", "description": "", "estimated_minutes": 873}], course="B", **kw)
        assert res.status_code == 400 and "43시간 35분" in res.json()["detail"]["message"] and "43시간 34분" in res.json()["detail"]["message"]

    def test_manual_tasks_and_patches_use_the_same_limit(self, client: TestClient, consented_headers):
        kw = {"start": SUNDAY_START, "target": TARGET_61, "weekly_hours": 5}
        data = _confirm(client, consented_headers, _tasks(3, 800), **kw).json()  # 2400 of 2614
        body = {"goal_id": data["goal"]["id"], "plan_week_start": "2026-10-19", "title": "추가", "estimated_minutes": 215}
        assert client.post("/api/tasks", json=body, headers=consented_headers).status_code == 400  # 2615
        assert client.post("/api/tasks", json={**body, "estimated_minutes": 214}, headers=consented_headers).status_code == 201  # 2614
        task = data["tasks"][0]
        assert client.patch(f"/api/tasks/{task['id']}", json={"estimated_minutes": 801}, headers=consented_headers).status_code == 400
        assert client.patch(f"/api/tasks/{task['id']}", json={"estimated_minutes": 800}, headers=consented_headers).status_code == 200

    def test_the_dashboard_reports_the_same_available_minutes(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, _tasks(3, 100), start=SUNDAY_START, target=TARGET_61, weekly_hours=5)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["plan_available_minutes"] == 2614 and body["plan_total_minutes"] == 300

    def test_placement_and_week_listing_still_use_monday_weeks(self, client: TestClient, consented_headers):
        # weekly 300: the first task fills week 1 (Mon 10/19 week holds the Sunday start), the next starts week 2
        data = _confirm(client, consented_headers, [{"title": "a", "description": "", "estimated_minutes": 300}, _tasks(1, 100)[0] | {"title": "b"}, _tasks(1, 100)[0] | {"title": "c"}], start=SUNDAY_START, target=TARGET_61, weekly_hours=5).json()
        assert [t["plan_week_start"] for t in data["tasks"]] == ["2026-10-19", "2026-10-26", "2026-10-26"]
        assert [t["timeline_start_minutes"] for t in data["tasks"]] == [0, 300, 400]


class TestCoverageAndHints:
    def test_coverage_percent_is_in_the_response(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_plan(_tasks(3, 400))]))  # 1200 of 2614
        body = client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers).json()
        assert body["coverage_percent"] == 46 and body["total_estimated_minutes"] == 1200

    def test_a_thin_plan_is_not_rejected_only_reported(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 10))]))  # 30 of 2614 = 1 %
        res = client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers)
        assert res.status_code == 200 and fake.calls == 1  # no retry: the hint ranges are advice, not rules
        assert res.json()["coverage_percent"] == 1

    def test_a_plan_outside_the_suggested_ranges_is_accepted(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 20))]))  # 3 tasks < the suggested 9..17, 60 min < 1307
        assert client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers).status_code == 200 and fake.calls == 1

    def test_the_model_gets_the_ranges_computed_by_the_server(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 100))]))
        client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers)
        sent = fake.payloads_seen[0]
        assert (sent["period_days"], sent["week_count"]) == (61, 8.7)
        assert sent["suggested_task_count_range"] == [9, 17]
        assert sent["suggested_total_range_minutes"] == [1307, 2614]

    def test_long_periods_clamp_the_task_range_to_60(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_plan(_tasks(3, 100))]))
        request = {**PLAN_REQUEST_BASE, "weekly_hours": 15, "start_date": "2026-10-26", "target_date": "2027-04-25"}  # 26 weeks
        body = client.post("/api/plan/generate", json=request, headers=consented_headers).json()
        assert fake.payloads_seen[0]["suggested_task_count_range"] == [26, 52]
        assert body["available_minutes"] == 23400 and body["coverage_percent"] == 1

    def test_the_hard_rules_are_still_enforced(self, client: TestClient, consented_headers, override_ai):
        # too few tasks, too long, duplicate titles: rejected as before
        dup = [{"title": "같음", "description": "d", "estimated_minutes": 30}] * 3
        for raw in (_plan(_tasks(2, 30)), _plan(_tasks(3, 2000)), _plan(dup)):
            override_ai(FakeAIClient(raws=[raw] * (MAX_RETRIES + 1)))
            assert client.post("/api/plan/generate", json=PM_REQUEST, headers=consented_headers).status_code == 502


class TestPrompt:
    def test_the_prompt_asks_for_a_realistic_amount_without_padding_and_names_the_hint_fields(self):
        for needle in ("suggested_task_count_range", "suggested_total_range_minutes", "period_days", "세분화", "프로젝트", "억지로 늘려 채우지 않고", "같은 과제를 반복하지 않는다", "권고일 뿐"):
            assert needle in PLAN_GENERATE_SYSTEM_PROMPT
        assert "3개 이상 60개 이하" in PLAN_GENERATE_SYSTEM_PROMPT  # the hard limits remain
