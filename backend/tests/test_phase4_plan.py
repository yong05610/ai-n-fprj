"""Phase 4 (PLAN): path recommendation, plan draft generation, plan confirmation.

All tests run against a FakeAIClient (no real OpenAI call) via a FastAPI
dependency override, per docs/phase4_dev_prompt.md's test requirements.
"""

import json

import pytest
from fastapi.testclient import TestClient

from ai_client import AIRetryableError, AIClient, MAX_RETRIES, get_ai_client
from main import app

VALID_PATH_RESPONSE = {
    "courses": [
        {
            "title": "기본문법",
            "description": "변수와 제어문",
            "levels": [
                {"order": 1, "name": "입문자", "description": "문법을 처음 접함"},
                {"order": 2, "name": "실무 기초", "description": "간단한 스크립트 작성 가능"},
            ],
        }
    ],
    "suggested_roles": ["백엔드 개발자", "데이터 엔지니어"],
}

VALID_PLAN_RESPONSE = {
    "tasks": [
        {"title": "변수와 자료형", "description": "기본 문법 실습", "estimated_minutes": 60, "suggested_weekday": "mon"},
        {"title": "조건문 연습", "description": "if문 실습", "estimated_minutes": 60, "suggested_weekday": "none"},
    ],
    "advice_title": "짧게 나누어 꾸준히",
    "advice_content": "주 7시간을 짧은 세션으로 나누어 진행해 보세요.",
}

PLAN_REQUEST_BASE = {
    "field": "Python 개발",
    "course": "기본문법",
    "current_level_order": 1,
    "current_level_name": "입문자",
    "target_level_order": 2,
    "target_level_name": "실무 기초",
    "weekly_hours": 7,
    "target_date": "2026-12-31",
    "plan_week_start": "2026-10-19",
}


class FakeAIClient(AIClient):
    """Returns canned raw JSON strings in order, or raises canned exceptions. Counts calls
    and records each attempt's user_payload (so retry-feedback tests can inspect it)."""

    def __init__(self, raws=None, raises=None):
        self._raws = list(raws or [])
        self._raises = list(raises or [])
        self.calls = 0
        self.payloads_seen = []

    def _raw_complete(self, system_prompt: str, user_payload: dict) -> str:
        self.calls += 1
        self.payloads_seen.append(user_payload)
        if self._raises:
            raise self._raises.pop(0)
        return self._raws.pop(0)


def _raw(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


@pytest.fixture
def override_ai():
    """Yields a setter: override_ai(fake_client) swaps in a FakeAIClient for the request."""
    applied = []

    def _set(fake: FakeAIClient) -> FakeAIClient:
        app.dependency_overrides[get_ai_client] = lambda: fake
        applied.append(fake)
        return fake

    yield _set
    app.dependency_overrides.pop(get_ai_client, None)


class TestPathRecommend:
    def test_success_assigns_course_ids_and_passes_through_levels(
        self, client: TestClient, consented_headers, override_ai
    ):
        override_ai(FakeAIClient(raws=[_raw(VALID_PATH_RESPONSE)]))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["field"] == "Python 개발"
        assert body["courses"][0]["id"] == "course-1"
        assert body["courses"][0]["levels"][0]["name"] == "입문자"
        assert body["suggested_roles"] == ["백엔드 개발자", "데이터 엔지니어"]

    def test_blank_field_rejected(self, client: TestClient, consented_headers):
        response = client.post("/api/path/recommend", json={"field": "   "}, headers=consented_headers)
        assert response.status_code == 422

    def test_schema_violation_retries_then_fails(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=["not json"] * (MAX_RETRIES + 1)))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1
        # The generic error message must never leak the raw provider output.
        assert "not json" not in response.text

    def test_non_ascending_level_order_treated_as_schema_error(self, client: TestClient, consented_headers, override_ai):
        bad = {
            "courses": [
                {
                    "title": "기본문법",
                    "description": "변수와 제어문",
                    "levels": [
                        {"order": 2, "name": "실무 기초", "description": "..."},
                        {"order": 1, "name": "입문자", "description": "..."},
                    ],
                }
            ],
            "suggested_roles": [],
        }
        override_ai(FakeAIClient(raws=[_raw(bad)] * (MAX_RETRIES + 1)))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "AI_SCHEMA_ERROR"

    def test_too_many_suggested_roles_treated_as_schema_error(self, client: TestClient, consented_headers, override_ai):
        bad = {**VALID_PATH_RESPONSE, "suggested_roles": ["a", "b", "c", "d", "e", "f"]}
        override_ai(FakeAIClient(raws=[_raw(bad)] * (MAX_RETRIES + 1)))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 502

    def test_timeout_retries_then_fails(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raises=[AIRetryableError("slow")] * (MAX_RETRIES + 1)))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 504
        assert response.json()["detail"]["code"] == "AI_TIMEOUT"
        assert fake.calls == MAX_RETRIES + 1

    def test_succeeds_after_one_retry(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=["not json", _raw(VALID_PATH_RESPONSE)]))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 200
        assert fake.calls == 2

    def test_unavailable_is_not_retried(self, client: TestClient, consented_headers, override_ai):
        from ai_client import AIUnavailableError

        fake = override_ai(FakeAIClient(raises=[AIUnavailableError("down")]))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "AI_UNAVAILABLE"
        assert fake.calls == 1

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.post("/api/path/recommend", json={"field": "x"}).status_code == 401
        assert client.post("/api/path/recommend", json={"field": "x"}, headers=mock_auth_headers).status_code == 403

    def test_single_level_course_retried_then_fails(self, client: TestClient, consented_headers, override_ai):
        # P4-8 repro: a real gpt-4o-mini call returned exactly one level per course,
        # leaving no target level for the user to pick.
        one_level = {
            "courses": [{"title": "기본문법", "description": "변수와 제어문", "levels": [{"order": 1, "name": "입문자", "description": "..."}]}],
            "suggested_roles": [],
        }
        fake = override_ai(FakeAIClient(raws=[_raw(one_level)] * (MAX_RETRIES + 1)))
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1

    def test_two_level_course_passes(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_raw(VALID_PATH_RESPONSE)]))  # already 2 levels
        response = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert response.status_code == 200
        assert len(response.json()["courses"][0]["levels"]) == 2


class TestPlanGenerate:
    def test_success_returns_draft_without_persisting_anything(self, client: TestClient, consented_headers, override_ai):
        from store import get_store

        override_ai(FakeAIClient(raws=[_raw(VALID_PLAN_RESPONSE)]))
        response = client.post("/api/plan/generate", json=PLAN_REQUEST_BASE, headers=consented_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["plan_week_start"] == "2026-10-19"
        assert body["total_estimated_minutes"] == 120
        assert len(body["tasks"]) == 2
        assert body["references"]  # Python 개발/기본문법 matches the catalog
        assert body["references_notice"] is None

        assert get_store().find("goals", user_id="test-uid-alice") == []
        assert get_store().find("tasks", user_id="test-uid-alice") == []

    def test_no_catalog_match_returns_notice_and_empty_references(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_raw(VALID_PLAN_RESPONSE)]))
        payload = {**PLAN_REQUEST_BASE, "field": "우주공학", "course": "로켓 설계"}
        response = client.post("/api/plan/generate", json=payload, headers=consented_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["references"] == []
        assert "검토 자료를 찾지 못했습니다" in body["references_notice"]

    def test_rejects_same_level(self, client: TestClient, consented_headers):
        payload = {**PLAN_REQUEST_BASE, "target_level_order": 1}
        assert client.post("/api/plan/generate", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_past_target_date(self, client: TestClient, consented_headers):
        payload = {**PLAN_REQUEST_BASE, "target_date": "2020-01-01"}
        assert client.post("/api/plan/generate", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_non_monday_week_start(self, client: TestClient, consented_headers):
        payload = {**PLAN_REQUEST_BASE, "plan_week_start": "2026-10-20"}
        assert client.post("/api/plan/generate", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_week_start_after_target_date(self, client: TestClient, consented_headers):
        payload = {**PLAN_REQUEST_BASE, "target_date": "2026-10-20", "plan_week_start": "2026-10-26"}
        assert client.post("/api/plan/generate", json=payload, headers=consented_headers).status_code == 400

    def test_defaults_plan_week_start_to_this_week_monday_when_omitted(self, client: TestClient, consented_headers, override_ai):
        import clock

        override_ai(FakeAIClient(raws=[_raw(VALID_PLAN_RESPONSE)]))
        payload = {k: v for k, v in PLAN_REQUEST_BASE.items() if k != "plan_week_start"}
        response = client.post("/api/plan/generate", json=payload, headers=consented_headers)
        assert response.status_code == 200
        assert response.json()["plan_week_start"] == clock.week_monday(clock.today()).isoformat()

    def test_ai_exceeding_weekly_budget_is_retried_then_fails_without_silent_truncation(
        self, client: TestClient, consented_headers, override_ai
    ):
        over_budget = {**VALID_PLAN_RESPONSE, "tasks": [{"title": "과로", "description": "너무 많음", "estimated_minutes": 10_000, "suggested_weekday": "none"}]}
        fake = override_ai(FakeAIClient(raws=[_raw(over_budget)] * (MAX_RETRIES + 1)))
        response = client.post("/api/plan/generate", json=PLAN_REQUEST_BASE, headers=consented_headers)
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1

    def test_initial_payload_includes_precomputed_max_total_minutes(
        self, client: TestClient, consented_headers, override_ai
    ):
        # P4-9: the model must not have to compute weekly_hours*60 itself.
        fake = override_ai(FakeAIClient(raws=[_raw(VALID_PLAN_RESPONSE)]))
        client.post("/api/plan/generate", json=PLAN_REQUEST_BASE, headers=consented_headers)
        assert fake.payloads_seen[0]["max_total_minutes"] == PLAN_REQUEST_BASE["weekly_hours"] * 60

    def test_over_budget_retry_gets_previous_total_as_feedback_then_succeeds(
        self, client: TestClient, consented_headers, override_ai
    ):
        # P4-9 repro: a real gpt-4o-mini call returned 660/570/420 minutes against a
        # 360-minute budget, three times in a row. The fix tells the next attempt how
        # far over it was instead of just repeating the same unmet instruction.
        over_budget = {
            **VALID_PLAN_RESPONSE,
            "tasks": [{"title": "과로", "description": "너무 많음", "estimated_minutes": 660, "suggested_weekday": "none"}],
        }
        fake = override_ai(FakeAIClient(raws=[_raw(over_budget), _raw(VALID_PLAN_RESPONSE)]))
        response = client.post("/api/plan/generate", json=PLAN_REQUEST_BASE, headers=consented_headers)
        assert response.status_code == 200
        assert fake.calls == 2
        second_attempt_payload = fake.payloads_seen[1]
        assert second_attempt_payload["previous_total_minutes"] == 660
        assert second_attempt_payload["max_total_minutes"] == PLAN_REQUEST_BASE["weekly_hours"] * 60

    def test_invalid_suggested_weekday_treated_as_schema_error(self, client: TestClient, consented_headers, override_ai):
        bad_raw = '{"tasks":[{"title":"t","description":"d","estimated_minutes":30,"suggested_weekday":"monday"}],"advice_title":"a","advice_content":"b"}'
        override_ai(FakeAIClient(raws=[bad_raw] * (MAX_RETRIES + 1)))
        response = client.post("/api/plan/generate", json=PLAN_REQUEST_BASE, headers=consented_headers)
        assert response.status_code == 502

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.post("/api/plan/generate", json=PLAN_REQUEST_BASE).status_code == 401
        assert client.post("/api/plan/generate", json=PLAN_REQUEST_BASE, headers=mock_auth_headers).status_code == 403


CONFIRM_REQUEST = {
    "field": "Python 개발",
    "course": "기본문법",
    "current_level_order": 1,
    "current_level_name": "입문자",
    "current_level_description": "문법을 처음 접함",
    "target_level_order": 2,
    "target_level_name": "실무 기초",
    "target_level_description": "간단한 스크립트 작성 가능",
    "weekly_hours": 7,
    "target_date": "2026-12-31",
    "plan_week_start": "2026-10-19",
    "tasks": [
        {"title": "변수와 자료형", "description": "기본 문법 실습", "estimated_minutes": 60, "suggested_weekday": "mon"},
        {"title": "조건문 연습", "description": "if문 실습", "estimated_minutes": 60, "suggested_weekday": "none"},
    ],
}

# A period that starts after CONFIRM_REQUEST's (2026-10-19 ~ 2026-12-31) ends (Phase 5B overlap rule).
LATER_PERIOD = {"plan_week_start": "2027-01-04", "target_date": "2027-03-31"}


class TestPlanConfirm:
    def test_success_saves_goal_and_tasks_and_they_are_retrievable(self, client: TestClient, consented_headers):
        response = client.post("/api/plan/confirm", json=CONFIRM_REQUEST, headers=consented_headers)
        assert response.status_code == 201
        body = response.json()
        assert body["goal"]["current_level_description"] == "문법을 처음 접함"
        assert len(body["tasks"]) == 2
        goal_id = body["goal"]["id"]

        tasks = client.get(
            "/api/tasks", params={"goal_id": goal_id, "plan_week_start": "2026-10-19"}, headers=consented_headers
        ).json()
        assert len(tasks) == 2
        assert {t["status"] for t in tasks} == {"pending"}

        active_goal = client.get("/api/user/profile", headers=consented_headers).json()["active_goal_id"]
        assert active_goal == goal_id

    def test_rejects_same_level(self, client: TestClient, consented_headers):
        payload = {**CONFIRM_REQUEST, "target_level_order": 1}
        assert client.post("/api/plan/confirm", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_past_target_date(self, client: TestClient, consented_headers):
        payload = {**CONFIRM_REQUEST, "target_date": "2020-01-01"}
        assert client.post("/api/plan/confirm", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_non_monday_week_start(self, client: TestClient, consented_headers):
        payload = {**CONFIRM_REQUEST, "plan_week_start": "2026-10-20"}
        assert client.post("/api/plan/confirm", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_week_start_after_target_date(self, client: TestClient, consented_headers):
        payload = {**CONFIRM_REQUEST, "target_date": "2026-10-20", "plan_week_start": "2026-10-26"}
        assert client.post("/api/plan/confirm", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_total_minutes_exceeding_weekly_hours(self, client: TestClient, consented_headers):
        # weekly_hours=7 -> 420 min cap; two 300-minute tasks (each within the per-task
        # le=6000 schema bound) together breach the weekly budget.
        over_budget_task = {**CONFIRM_REQUEST["tasks"][0], "estimated_minutes": 300}
        payload = {**CONFIRM_REQUEST, "tasks": [over_budget_task, {**over_budget_task, "title": "다른 과업"}]}
        assert client.post("/api/plan/confirm", json=payload, headers=consented_headers).status_code == 400

    def test_rejects_invalid_weekday(self, client: TestClient, consented_headers):
        payload = {**CONFIRM_REQUEST, "tasks": [{**CONFIRM_REQUEST["tasks"][0], "suggested_weekday": "monday"}]}
        assert client.post("/api/plan/confirm", json=payload, headers=consented_headers).status_code == 422

    def test_nothing_is_saved_when_validation_fails(self, client: TestClient, consented_headers):
        from store import get_store

        payload = {**CONFIRM_REQUEST, "target_date": "2020-01-01"}
        client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        assert get_store().find("goals", user_id="test-uid-alice") == []

    def test_other_uid_cannot_see_confirmed_plan(self, client: TestClient, consented_headers):
        from tests.conftest import auth_headers

        created = client.post("/api/plan/confirm", json=CONFIRM_REQUEST, headers=consented_headers).json()
        bob = auth_headers("test-uid-bob")
        client.post("/api/consent", json={"terms_version": "v1.0", "privacy_agreed": True, "ai_use_agreed": True}, headers=bob)
        assert client.get(f"/api/goals/{created['goal']['id']}", headers=bob).status_code == 403

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.post("/api/plan/confirm", json=CONFIRM_REQUEST).status_code == 401
        assert client.post("/api/plan/confirm", json=CONFIRM_REQUEST, headers=mock_auth_headers).status_code == 403

    def test_retry_with_same_client_request_id_does_not_duplicate(self, client: TestClient, consented_headers):
        payload = {**CONFIRM_REQUEST, "client_request_id": "retry-key-1"}
        first = client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        assert first.status_code == 201
        first_goal_id = first.json()["goal"]["id"]

        second = client.post("/api/plan/confirm", json=payload, headers=consented_headers)
        assert second.status_code == 200
        assert second.json()["goal"]["id"] == first_goal_id
        assert len(second.json()["tasks"]) == len(first.json()["tasks"])

        assert len(client.get("/api/goals", headers=consented_headers).json()) == 1

    def test_different_client_request_id_creates_a_new_goal(self, client: TestClient, consented_headers):
        client.post("/api/plan/confirm", json={**CONFIRM_REQUEST, "client_request_id": "key-a"}, headers=consented_headers)
        # Phase 5B: the second goal must not overlap the first goal's period.
        client.post(
            "/api/plan/confirm",
            json={**CONFIRM_REQUEST, "client_request_id": "key-b", **LATER_PERIOD},
            headers=consented_headers,
        )
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 2

    def test_omitting_client_request_id_keeps_old_always_create_behavior(self, client: TestClient, consented_headers):
        client.post("/api/plan/confirm", json=CONFIRM_REQUEST, headers=consented_headers)
        client.post("/api/plan/confirm", json={**CONFIRM_REQUEST, **LATER_PERIOD}, headers=consented_headers)
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 2


class TestTaskWeeklyTimeBudgetSharedWithAIPath:
    """The manual POST /api/tasks / PATCH /api/tasks/{id} path must enforce the same
    weekly time-budget and target-date-range rules as the AI-driven plan (4.5)."""

    def _goal(self, client: TestClient, headers: dict) -> dict:
        payload = {
            "field": "Python 개발",
            "course": "기본문법",
            "current_level_order": 1,
            "current_level_name": "입문",
            "target_level_order": 3,
            "target_level_name": "실무 기초",
            "weekly_hours": 2,  # 120 minutes/week, deliberately small
            "target_date": "2026-10-25",
        }
        return client.post("/api/goals", json=payload, headers=headers).json()

    def test_task_exceeding_weekly_budget_rejected(self, client: TestClient, consented_headers):
        goal = self._goal(client, consented_headers)
        first = {
            "goal_id": goal["id"],
            "plan_week_start": "2026-10-19",
            "title": "1번 과업",
            "estimated_minutes": 100,
        }
        assert client.post("/api/tasks", json=first, headers=consented_headers).status_code == 201

        second = {**first, "title": "2번 과업", "estimated_minutes": 30}
        response = client.post("/api/tasks", json=second, headers=consented_headers)
        assert response.status_code == 400

    def test_task_week_after_goal_target_date_rejected(self, client: TestClient, consented_headers):
        goal = self._goal(client, consented_headers)
        task = {
            "goal_id": goal["id"],
            "plan_week_start": "2026-10-26",  # after target_date 2026-10-25
            "title": "너무 늦은 과업",
            "estimated_minutes": 30,
        }
        assert client.post("/api/tasks", json=task, headers=consented_headers).status_code == 400

    def test_update_task_minutes_rechecked_against_weekly_budget(self, client: TestClient, consented_headers):
        goal = self._goal(client, consented_headers)
        task = client.post(
            "/api/tasks",
            json={"goal_id": goal["id"], "plan_week_start": "2026-10-19", "title": "과업", "estimated_minutes": 60},
            headers=consented_headers,
        ).json()

        ok = client.patch(f"/api/tasks/{task['id']}", json={"estimated_minutes": 120}, headers=consented_headers)
        assert ok.status_code == 200

        too_much = client.patch(f"/api/tasks/{task['id']}", json={"estimated_minutes": 121}, headers=consented_headers)
        assert too_much.status_code == 400
