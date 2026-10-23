"""Phase 5 (EXEC): study logs, reflections, server-side timer, dashboard summary.

No AI calls anywhere in this phase - all tests run purely against dev-mode auth and
the in-memory store.
"""

import pytest
from fastapi.testclient import TestClient

import clock
from tests.conftest import auth_headers

GOAL = {
    "field": "Python 개발",
    "course": "기본문법",
    "current_level_order": 1,
    "current_level_name": "입문",
    "target_level_order": 3,
    "target_level_name": "실무 기초",
    "weekly_hours": 7,
    "target_date": "2026-12-31",
}


def _make_goal(client: TestClient, headers: dict) -> dict:
    return client.post("/api/goals", json=GOAL, headers=headers).json()


def _make_task(client: TestClient, headers: dict, goal_id: str, **overrides) -> dict:
    payload = {
        "goal_id": goal_id,
        "plan_week_start": "2026-10-19",
        "title": "반복문 연습",
        "estimated_minutes": 60,
        **overrides,
    }
    return client.post("/api/tasks", json=payload, headers=headers).json()


def _log_payload(task_id: str, **overrides) -> dict:
    return {
        "task_id": task_id,
        "study_date": "2026-10-19",
        "minutes": 30,
        "activity": "for문 예제 5개 풀이",
        **overrides,
    }


@pytest.fixture
def goal_and_task(client: TestClient, consented_headers):
    goal = _make_goal(client, consented_headers)
    task = _make_task(client, consented_headers, goal["id"])
    return goal, task


class TestStudyLogCrud:
    def test_create_get_and_list(self, client: TestClient, consented_headers, goal_and_task):
        goal, task = goal_and_task
        created = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers)
        assert created.status_code == 201
        body = created.json()
        assert body["user_id"] == "test-uid-alice"
        assert body["task_id"] == task["id"]
        assert body["goal_id"] == goal["id"]  # derived from the task, not client-sent
        assert body["reflection"] is None

        listed = client.get("/api/study-logs", headers=consented_headers).json()
        assert len(listed) == 1
        assert listed[0]["id"] == body["id"]

    def test_one_task_can_have_multiple_logs(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"], activity="첫 번째 기록"), headers=consented_headers)
        client.post("/api/study-logs", json=_log_payload(task["id"], activity="두 번째 기록"), headers=consented_headers)
        logs = client.get("/api/study-logs", params={"task_id": task["id"]}, headers=consented_headers).json()
        assert len(logs) == 2

    def test_request_goal_id_is_ignored(self, client: TestClient, consented_headers, goal_and_task):
        goal, task = goal_and_task
        payload = {**_log_payload(task["id"]), "goal_id": "someone-elses-goal"}
        body = client.post("/api/study-logs", json=payload, headers=consented_headers).json()
        assert body["goal_id"] == goal["id"]

    def test_create_rejects_nonexistent_task(self, client: TestClient, consented_headers):
        response = client.post("/api/study-logs", json=_log_payload("does-not-exist"), headers=consented_headers)
        assert response.status_code == 404

    def test_update_and_delete(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        created = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers).json()

        updated = client.patch(
            f"/api/study-logs/{created['id']}", json={"minutes": 45, "activity": "수정된 내용"}, headers=consented_headers
        )
        assert updated.status_code == 200
        assert updated.json()["minutes"] == 45

        deleted = client.delete(f"/api/study-logs/{created['id']}", headers=consented_headers)
        assert deleted.status_code == 200
        assert client.get("/api/study-logs", headers=consented_headers).json() == []

    def test_delete_log_keeps_task(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        created = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers).json()
        client.delete(f"/api/study-logs/{created['id']}", headers=consented_headers)
        tasks = client.get("/api/tasks", headers=consented_headers).json()
        assert len(tasks) == 1
        assert tasks[0]["id"] == task["id"]

    def test_reflections_are_attached_correctly_in_bulk(self, client: TestClient, consented_headers, goal_and_task):
        # P5-6: list_study_logs now batches the reflections lookup; this guards that the
        # batched grouping still attaches each log's own reflection, not a mismatched one.
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"], activity="회고 있음", reflection={"content": "첫 회고"}), headers=consented_headers)
        client.post("/api/study-logs", json=_log_payload(task["id"], activity="회고 없음"), headers=consented_headers)
        logs = {log["activity"]: log for log in client.get("/api/study-logs", headers=consented_headers).json()}
        assert logs["회고 있음"]["reflection"]["content"] == "첫 회고"
        assert logs["회고 없음"]["reflection"] is None

    def test_list_response_flags_truncation_header_when_over_the_cap(
        self, client: TestClient, consented_headers, goal_and_task, monkeypatch
    ):
        import main

        _, task = goal_and_task
        monkeypatch.setattr(main, "STUDY_LOG_LIST_LIMIT", 2)
        for i in range(3):
            client.post("/api/study-logs", json=_log_payload(task["id"], activity=f"기록 {i}"), headers=consented_headers)
        response = client.get("/api/study-logs", headers=consented_headers)
        assert len(response.json()) == 2
        assert response.headers.get("x-study-logs-truncated") == "true"

    def test_list_response_has_no_truncation_header_under_the_cap(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers)
        response = client.get("/api/study-logs", headers=consented_headers)
        assert "x-study-logs-truncated" not in response.headers


class TestStudyLogValidation:
    def test_future_study_date_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        future = (clock.today().replace(year=clock.today().year + 1)).isoformat()
        response = client.post("/api/study-logs", json=_log_payload(task["id"], study_date=future), headers=consented_headers)
        assert response.status_code == 400

    def test_today_study_date_allowed(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], study_date=clock.today().isoformat())
        assert client.post("/api/study-logs", json=payload, headers=consented_headers).status_code == 201

    def test_zero_minutes_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        response = client.post("/api/study-logs", json=_log_payload(task["id"], minutes=0), headers=consented_headers)
        assert response.status_code == 422

    def test_over_cap_minutes_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        response = client.post("/api/study-logs", json=_log_payload(task["id"], minutes=1441), headers=consented_headers)
        assert response.status_code == 422

    def test_blank_activity_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        response = client.post("/api/study-logs", json=_log_payload(task["id"], activity="   "), headers=consented_headers)
        assert response.status_code == 422

    def test_started_after_ended_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], started_at="2026-10-19T10:00:00Z", ended_at="2026-10-19T09:00:00Z")
        assert client.post("/api/study-logs", json=payload, headers=consented_headers).status_code == 422

    def test_started_equal_ended_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], started_at="2026-10-19T09:00:00Z", ended_at="2026-10-19T09:00:00Z")
        assert client.post("/api/study-logs", json=payload, headers=consented_headers).status_code == 422

    def test_only_one_of_started_ended_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], started_at="2026-10-19T09:00:00Z")
        assert client.post("/api/study-logs", json=payload, headers=consented_headers).status_code == 422

    def test_valid_started_ended_with_user_supplied_minutes_kept_as_is(
        self, client: TestClient, consented_headers, goal_and_task
    ):
        # 열린 결정 2: minutes는 started_at/ended_at에서 자동 계산되지 않고 사용자 값을 그대로 저장한다.
        _, task = goal_and_task
        payload = _log_payload(
            task["id"], minutes=5, started_at="2026-10-19T09:00:00Z", ended_at="2026-10-19T10:00:00Z"
        )
        body = client.post("/api/study-logs", json=payload, headers=consented_headers).json()
        assert body["minutes"] == 5


class TestStudyLogOwnershipAndAuth:
    def test_cannot_log_against_another_uids_task(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        bob = auth_headers("test-uid-bob")
        client.post("/api/consent", json={"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}, headers=bob)
        response = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=bob)
        assert response.status_code == 403

    def test_cannot_update_or_delete_another_uids_log(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        log = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers).json()
        bob = auth_headers("test-uid-bob")
        client.post("/api/consent", json={"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}, headers=bob)
        assert client.patch(f"/api/study-logs/{log['id']}", json={"minutes": 10}, headers=bob).status_code == 403
        assert client.delete(f"/api/study-logs/{log['id']}", headers=bob).status_code == 403

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.get("/api/study-logs").status_code == 401
        assert client.post("/api/study-logs", json=_log_payload("x")).status_code == 401
        assert client.post("/api/study-logs", json=_log_payload("x"), headers=mock_auth_headers).status_code == 403


class TestStudyLogIdempotency:
    def test_same_client_request_id_returns_existing(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], client_request_id="retry-1")
        first = client.post("/api/study-logs", json=payload, headers=consented_headers)
        assert first.status_code == 201
        second = client.post("/api/study-logs", json=payload, headers=consented_headers)
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert len(client.get("/api/study-logs", headers=consented_headers).json()) == 1

    def test_different_client_request_id_creates_new(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"], client_request_id="a"), headers=consented_headers)
        client.post("/api/study-logs", json=_log_payload(task["id"], client_request_id="b"), headers=consented_headers)
        assert len(client.get("/api/study-logs", headers=consented_headers).json()) == 2


class TestReflection:
    def test_create_with_log_and_read_back(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], reflection={"content": "반복문이 헷갈렸다", "tags": ["복습", "복습", " ", "반복문"]})
        body = client.post("/api/study-logs", json=payload, headers=consented_headers).json()
        assert body["reflection"]["content"] == "반복문이 헷갈렸다"
        assert body["reflection"]["tags"] == ["복습", "반복문"]  # deduped, blank dropped

    def test_update_reflection_content(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], reflection={"content": "처음 회고", "tags": []})
        log = client.post("/api/study-logs", json=payload, headers=consented_headers).json()

        updated = client.patch(
            f"/api/study-logs/{log['id']}", json={"reflection": {"content": "수정한 회고", "tags": ["수정"]}}, headers=consented_headers
        )
        assert updated.json()["reflection"]["content"] == "수정한 회고"
        assert updated.json()["reflection"]["tags"] == ["수정"]

    def test_add_reflection_to_log_created_without_one(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        log = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers).json()
        updated = client.patch(
            f"/api/study-logs/{log['id']}", json={"reflection": {"content": "나중에 추가한 회고"}}, headers=consented_headers
        )
        assert updated.json()["reflection"]["content"] == "나중에 추가한 회고"

    def test_delete_reflection_only_keeps_log(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], reflection={"content": "지울 회고", "tags": []})
        log = client.post("/api/study-logs", json=payload, headers=consented_headers).json()

        updated = client.patch(f"/api/study-logs/{log['id']}", json={"delete_reflection": True}, headers=consented_headers)
        assert updated.status_code == 200
        assert updated.json()["reflection"] is None
        assert client.get("/api/study-logs", headers=consented_headers).json()[0]["id"] == log["id"]

    def test_reflection_and_delete_reflection_together_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        log = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers).json()
        response = client.patch(
            f"/api/study-logs/{log['id']}",
            json={"reflection": {"content": "x"}, "delete_reflection": True},
            headers=consented_headers,
        )
        assert response.status_code == 422

    def test_blank_reflection_content_rejected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], reflection={"content": "   "})
        assert client.post("/api/study-logs", json=payload, headers=consented_headers).status_code == 422

    def test_deleting_log_deletes_its_reflection(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = _log_payload(task["id"], reflection={"content": "삭제될 회고"})
        log = client.post("/api/study-logs", json=payload, headers=consented_headers).json()
        client.delete(f"/api/study-logs/{log['id']}", headers=consented_headers)
        # recreate a log and confirm no stray reflection leaks into it
        new_log = client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers).json()
        assert new_log["reflection"] is None


class TestTaskAndGoalDeletionCascade:
    def test_deleting_task_deletes_its_logs_and_reflections(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post(
            "/api/study-logs", json=_log_payload(task["id"], reflection={"content": "회고"}), headers=consented_headers
        )
        client.delete(f"/api/tasks/{task['id']}", headers=consented_headers)
        assert client.get("/api/study-logs", headers=consented_headers).json() == []

    def test_deleting_goal_cascades_through_tasks_to_logs(self, client: TestClient, consented_headers, goal_and_task):
        goal, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers)
        client.delete(f"/api/goals/{goal['id']}", headers=consented_headers)
        assert client.get("/api/study-logs", headers=consented_headers).json() == []
        assert client.get("/api/tasks", headers=consented_headers).json() == []


class TestTaskStatsOnTasksEndpoint:
    def test_record_count_and_total_minutes_reflected(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"], minutes=30), headers=consented_headers)
        client.post("/api/study-logs", json=_log_payload(task["id"], minutes=20), headers=consented_headers)
        tasks = client.get("/api/tasks", headers=consented_headers).json()
        assert tasks[0]["record_count"] == 2
        assert tasks[0]["total_minutes"] == 50

    def test_stats_reflected_immediately_after_create_and_patch(self, client: TestClient, consented_headers, goal_and_task):
        goal, _ = goal_and_task
        created = _make_task(client, consented_headers, goal["id"], title="새 과제")
        assert created["record_count"] == 0
        assert created["total_minutes"] == 0

        patched = client.patch(f"/api/tasks/{created['id']}", json={"status": "completed"}, headers=consented_headers)
        assert patched.json()["record_count"] == 0


class TestTimer:
    def test_no_active_timer_initially(self, client: TestClient, consented_headers):
        response = client.get("/api/timer/active", headers=consented_headers)
        assert response.status_code == 200
        assert response.json() == {"active": False, "task_id": None, "goal_id": None, "started_at": None}

    def test_start_requires_task(self, client: TestClient, consented_headers):
        assert client.post("/api/timer/start", json={}, headers=consented_headers).status_code == 422

    def test_start_then_active_then_cancel(self, client: TestClient, consented_headers, goal_and_task):
        goal, task = goal_and_task
        started = client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        assert started.status_code == 201
        assert started.json()["active"] is True
        assert started.json()["task_id"] == task["id"]
        assert started.json()["goal_id"] == goal["id"]

        active = client.get("/api/timer/active", headers=consented_headers).json()
        assert active["active"] is True
        assert active["task_id"] == task["id"]

        cancelled = client.post("/api/timer/cancel", json={}, headers=consented_headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["active"] is False
        assert client.get("/api/timer/active", headers=consented_headers).json()["active"] is False
        # Cancelling creates no study_log.
        assert client.get("/api/study-logs", headers=consented_headers).json() == []

    def test_second_start_rejected_with_409_and_running_task_info(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        second_task = _make_task(client, consented_headers, (goal_and_task[0])["id"], title="다른 과제")
        response = client.post("/api/timer/start", json={"task_id": second_task["id"]}, headers=consented_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TIMER_ALREADY_RUNNING"
        assert response.json()["detail"]["details"]["task_id"] == task["id"]

    def test_start_retried_with_same_client_request_id_is_idempotent(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        payload = {"task_id": task["id"], "client_request_id": "start-key-1"}
        first = client.post("/api/timer/start", json=payload, headers=consented_headers)
        assert first.status_code == 201
        second = client.post("/api/timer/start", json=payload, headers=consented_headers)
        assert second.status_code == 200
        assert second.json()["task_id"] == task["id"]

    def test_finish_without_active_timer_rejected(self, client: TestClient, consented_headers):
        response = client.post("/api/timer/finish", json={"activity": "x"}, headers=consented_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TIMER_NOT_RUNNING"

    def test_finish_creates_study_log_and_clears_timer(self, client: TestClient, consented_headers, goal_and_task):
        goal, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        finished = client.post(
            "/api/timer/finish",
            json={"activity": "타이머로 학습", "minutes": 25, "reflection": {"content": "타이머 회고"}},
            headers=consented_headers,
        )
        assert finished.status_code == 201
        body = finished.json()
        assert body["task_id"] == task["id"]
        assert body["goal_id"] == goal["id"]
        assert body["minutes"] == 25
        assert body["started_at"] is not None and body["ended_at"] is not None
        assert body["reflection"]["content"] == "타이머 회고"

        assert client.get("/api/timer/active", headers=consented_headers).json()["active"] is False

    def test_finish_retry_with_same_client_request_id_returns_200_not_409(
        self, client: TestClient, consented_headers, goal_and_task
    ):
        # P5-1 repro: a client that never saw the first finish's response retries with the
        # same client_request_id. It must get the saved record back (200), not 409
        # TIMER_NOT_RUNNING (the first call already cleared the active timer).
        _, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        payload = {"activity": "한 번만 쓸 내용", "minutes": 20, "client_request_id": "finish-key-1"}
        first = client.post("/api/timer/finish", json=payload, headers=consented_headers)
        assert first.status_code == 201
        first_id = first.json()["id"]

        retry = client.post("/api/timer/finish", json=payload, headers=consented_headers)
        assert retry.status_code == 200
        assert retry.json()["id"] == first_id

        logs = client.get("/api/study-logs", params={"task_id": task["id"]}, headers=consented_headers).json()
        assert len(logs) == 1

    def test_finish_without_active_timer_and_without_matching_client_request_id_still_409(
        self, client: TestClient, consented_headers
    ):
        # Regression guard: a client_request_id that doesn't match any saved log must not
        # bypass the "is a timer even running" check.
        response = client.post(
            "/api/timer/finish", json={"activity": "x", "client_request_id": "never-used-key"}, headers=consented_headers
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TIMER_NOT_RUNNING"

    def test_finish_rejects_when_active_timers_task_was_deleted_out_from_under_it(
        self, client: TestClient, consented_headers, goal_and_task
    ):
        # P5-2 defense-in-depth: simulate a dangling active_timer (normal delete_task/
        # delete_goal paths already clean this up - this covers any path that doesn't).
        from store import get_store

        _, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        get_store().update("tasks", task["id"], {})  # no-op touch; task still exists here
        get_store().delete("tasks", task["id"])  # now simulate the task having vanished

        response = client.post("/api/timer/finish", json={"activity": "x"}, headers=consented_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TIMER_TASK_GONE"
        assert client.get("/api/timer/active", headers=consented_headers).json()["active"] is False
        assert client.get("/api/study-logs", headers=consented_headers).json() == []

    def test_finish_without_minutes_override_computes_from_elapsed(self, client: TestClient, consented_headers, goal_and_task, monkeypatch):
        import main

        _, task = goal_and_task
        start_instant = {"n": 0}

        def fake_now_iso():
            # First call = start time, second = finish time (10 minutes later).
            start_instant["n"] += 1
            return "2026-10-19T09:00:00Z" if start_instant["n"] == 1 else "2026-10-19T09:10:00Z"

        monkeypatch.setattr(main, "_now_iso", fake_now_iso)
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        finished = client.post("/api/timer/finish", json={"activity": "자동 계산"}, headers=consented_headers)
        assert finished.json()["minutes"] == 10

    def test_refresh_restores_active_timer(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        # A second "page load" is just another GET - no client-side state needed.
        restored = client.get("/api/timer/active", headers=consented_headers).json()
        assert restored["active"] is True
        assert restored["task_id"] == task["id"]

    def test_deleting_the_active_tasks_timer_clears_it(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        client.delete(f"/api/tasks/{task['id']}", headers=consented_headers)
        assert client.get("/api/timer/active", headers=consented_headers).json()["active"] is False

    def test_deleting_the_goal_clears_a_timer_on_one_of_its_tasks(self, client: TestClient, consented_headers, goal_and_task):
        # P5-2 repro: deleting the goal (which cascades to its tasks) previously left
        # users.active_timer pointing at a task that no longer exists.
        goal, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        assert client.delete(f"/api/goals/{goal['id']}", headers=consented_headers).status_code == 200
        assert client.get("/api/timer/active", headers=consented_headers).json()["active"] is False

    def test_data_deletion_clears_active_timer(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/timer/start", json={"task_id": task["id"]}, headers=consented_headers)
        client.post("/api/user/delete-data", headers=consented_headers)
        client.post("/api/consent", json={"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}, headers=consented_headers)
        assert client.get("/api/timer/active", headers=consented_headers).json()["active"] is False

    def test_cannot_start_on_another_uids_task(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        bob = auth_headers("test-uid-bob")
        client.post("/api/consent", json={"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}, headers=bob)
        assert client.post("/api/timer/start", json={"task_id": task["id"]}, headers=bob).status_code == 403

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.get("/api/timer/active").status_code == 401
        assert client.get("/api/timer/active", headers=mock_auth_headers).status_code == 403
        assert client.post("/api/timer/start", json={"task_id": "x"}).status_code == 401


class TestDashboardSummary:
    def test_empty_state_when_no_active_goal(self, client: TestClient, consented_headers):
        response = client.get("/api/dashboard/summary", headers=consented_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["active_goal_title"] == ""
        assert body["total_task_count"] == 0
        assert body["progress_percentage"] == 0
        assert len(body["weekly_hits"]) == 7
        assert all(h["has_activity"] is False for h in body["weekly_hits"])
        assert body["insight"]["is_insufficient"] is True

    def test_progress_and_level_text_with_goal_and_tasks(self, client: TestClient, consented_headers, goal_and_task):
        goal, task = goal_and_task
        _make_task(client, consented_headers, goal["id"], title="두 번째 과제")
        client.patch(f"/api/tasks/{task['id']}", json={"status": "completed"}, headers=consented_headers)

        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["active_goal_title"] == f"{goal['field']} · {goal['course']}"
        assert body["level_progress_text"] == f"{goal['current_level_name']} → {goal['target_level_name']}"
        assert "1" not in body["level_progress_text"] and "3" not in body["level_progress_text"]  # no level numbers
        assert body["total_task_count"] == 2
        assert body["completed_task_count"] == 1
        assert body["progress_percentage"] == 50
        assert body["weekly_target_minutes"] == goal["weekly_hours"] * 60

    def test_completed_task_stays_visible_with_is_completed_true(self, client: TestClient, consented_headers, goal_and_task):
        # P5-4 repro: a completed task previously vanished from today_tasks entirely, and
        # is_completed was hardcoded False even when it hadn't been filtered out yet.
        _, task = goal_and_task
        client.patch(f"/api/tasks/{task['id']}", json={"status": "completed"}, headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        matching = next((t for t in body["today_tasks"] if t["id"] == task["id"]), None)
        assert matching is not None
        assert matching["is_completed"] is True

    def test_uncompleting_a_task_flips_is_completed_back(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.patch(f"/api/tasks/{task['id']}", json={"status": "completed"}, headers=consented_headers)
        client.patch(f"/api/tasks/{task['id']}", json={"status": "pending"}, headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        matching = next(t for t in body["today_tasks"] if t["id"] == task["id"])
        assert matching["is_completed"] is False

    def test_all_tasks_completed_this_week_flag(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        assert client.get("/api/dashboard/summary", headers=consented_headers).json()["all_tasks_completed_this_week"] is False
        client.patch(f"/api/tasks/{task['id']}", json={"status": "completed"}, headers=consented_headers)
        assert client.get("/api/dashboard/summary", headers=consented_headers).json()["all_tasks_completed_this_week"] is True

    def test_incomplete_tasks_keep_priority_over_completed_within_the_display_cap(
        self, client: TestClient, consented_headers, goal_and_task
    ):
        goal, first_task = goal_and_task
        client.patch(f"/api/tasks/{first_task['id']}", json={"status": "completed"}, headers=consented_headers)
        extra = [_make_task(client, consented_headers, goal["id"], title=f"과제 {i}", order_index=i) for i in range(5)]
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        ids = [t["id"] for t in body["today_tasks"]]
        assert len(ids) == 5  # capped
        assert first_task["id"] not in ids  # completed task bumped out by incomplete ones

    def test_weekly_study_minutes_only_counts_this_week(self, client: TestClient, consented_headers, goal_and_task, monkeypatch):
        import main

        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"], study_date="2026-10-19", minutes=40), headers=consented_headers)
        client.post("/api/study-logs", json=_log_payload(task["id"], study_date="2026-10-12", minutes=999), headers=consented_headers)

        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["weekly_study_minutes"] == 40
        assert body["total_study_log_count"] == 2  # all-time count for the active goal

    def test_today_recommended_task_prefers_matching_weekday(self, client: TestClient, consented_headers, goal_and_task):
        goal, first_task = goal_and_task
        today_weekday = clock.WEEKDAY_BY_INDEX[clock.today().weekday()]
        matching = _make_task(client, consented_headers, goal["id"], title="오늘 과제", suggested_weekday=today_weekday, order_index=5)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["today_tasks"][0]["id"] == matching["id"]

    def test_past_weekday_incomplete_task_is_not_dropped_or_flagged_overdue(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        # suggested_weekday "none" never matches today, but the task must still show up.
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        ids = [t["id"] for t in body["today_tasks"]]
        assert task["id"] in ids

    def test_record_count_on_today_task_reflects_logs(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"]), headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        matching = next(t for t in body["today_tasks"] if t["id"] == task["id"])
        assert matching["record_count"] == 1

    def test_insight_insufficient_then_sufficient_after_enough_records(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        assert client.get("/api/dashboard/summary", headers=consented_headers).json()["insight"]["is_insufficient"] is True

        for i in range(3):
            client.post(
                "/api/study-logs",
                json=_log_payload(task["id"], activity=f"기록 {i}", reflection={"content": f"회고 {i}"} if i == 0 else None),
                headers=consented_headers,
            )
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["insight"]["is_insufficient"] is False
        assert "Phase 6" in body["insight"]["text"]

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.get("/api/dashboard/summary").status_code == 401
        assert client.get("/api/dashboard/summary", headers=mock_auth_headers).status_code == 403


class TestWeekBoundaryHandling:
    """Asia/Seoul week boundary (Monday 00:00 - Sunday 23:59), not UTC."""

    def test_monday_just_after_midnight_kst_is_this_week(self, client: TestClient, consented_headers, goal_and_task, monkeypatch):
        import main
        from datetime import date

        _, task = goal_and_task
        monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 19))  # Monday
        client.post("/api/study-logs", json=_log_payload(task["id"], study_date="2026-10-19", minutes=15), headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["weekly_study_minutes"] == 15

    def test_sunday_end_of_week_still_counts(self, client: TestClient, consented_headers, goal_and_task, monkeypatch):
        _, task = goal_and_task
        monkeypatch.setattr(clock, "today", lambda: __import__("datetime").date(2026, 10, 25))  # Sunday
        client.post("/api/study-logs", json=_log_payload(task["id"], study_date="2026-10-25", minutes=20), headers=consented_headers)
        body = client.get("/api/dashboard/summary", headers=consented_headers).json()
        assert body["weekly_study_minutes"] == 20

    def test_period_week_excludes_last_weeks_log(self, client: TestClient, consented_headers, goal_and_task):
        _, task = goal_and_task
        client.post("/api/study-logs", json=_log_payload(task["id"], study_date="2026-10-12"), headers=consented_headers)  # last Monday
        week_logs = client.get("/api/study-logs", params={"period": "week"}, headers=consented_headers).json()
        assert week_logs == []
        all_logs = client.get("/api/study-logs", params={"period": "all"}, headers=consented_headers).json()
        assert len(all_logs) == 1
