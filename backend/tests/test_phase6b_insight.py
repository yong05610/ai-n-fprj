"""Phase 6B: AI learning insight (stored per learning, created only on request).

Fake AI clients only. "Today" is pinned to 2026-10-22 so the 14-day window is deterministic.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import clock
import main
from ai_client import MAX_RETRIES, AIRetryableError
from store import get_store
from tests.conftest import auth_headers
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm, _other_user

TODAY = date(2026, 10, 22)
UID = "test-uid-alice"


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _day(offset: int) -> str:
    return (TODAY - timedelta(days=offset)).isoformat()


def _ai(summary="최근 14일 동안의 학습 기록을 바탕으로 한 요약이에요.", difficulty="", next_action="다음에는 짧은 복습부터 시작해 보세요.") -> str:
    return _raw({"summary": summary, "difficulty": difficulty, "next_action": next_action})


def _goal(client, headers, course="기본문법", start="2026-10-22", target="2026-12-31"):
    res = _confirm(client, headers, course=course, start=start, target=target)
    assert res.status_code == 201, res.text
    return res.json()["goal"]["id"], res.json()["tasks"][0]["id"]


def _log(client, headers, task_id, offset=0, text=None, minutes=30, activity="학습 활동"):
    body = {"task_id": task_id, "study_date": _day(offset), "minutes": minutes, "activity": activity}
    if text is not None:
        body["reflection"] = {"content": text, "tags": []}
    res = client.post("/api/study-logs", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _ready(client, headers, **kw):
    """A learning with 4 records in the window and 2 reflections."""
    goal_id, task_id = _goal(client, headers, **kw)
    logs = [_log(client, headers, task_id, offset=i, text=("회고 " + str(i)) if i < 2 else None) for i in range(4)]
    return goal_id, task_id, logs


def _make(client, headers, goal_id, key="k1"):
    return client.post(f"/api/goals/{goal_id}/insight", json={"client_request_id": key}, headers=headers)


def _age(goal_id, seconds):
    old = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")
    get_store().update("insights", goal_id, {"generated_at": old})


# ----------------------------------------------------------------------------- not enough material
class TestInsufficient:
    def test_too_few_records_means_no_ai_call_and_nothing_stored(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[]))
        goal_id, task_id = _goal(client, consented_headers)
        _log(client, consented_headers, task_id, 0, text="회고")
        _log(client, consented_headers, task_id, 1)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 200
        body = res.json()
        assert body["insight"] is None and body["is_insufficient"] is True
        assert body["message"] == "기록과 회고를 더 남기면 인사이트를 볼 수 있어요. (기록 2/3, 회고 1/1)"
        assert (body["record_count"], body["reflection_count"]) == (2, 1)
        assert fake.calls == 0 and get_store().get("insights", goal_id) is None

    def test_no_reflection_means_insufficient(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[]))
        goal_id, task_id = _goal(client, consented_headers)
        for i in range(3):
            _log(client, consented_headers, task_id, i)
        body = _make(client, consented_headers, goal_id).json()
        assert body["is_insufficient"] is True and "(기록 3/3, 회고 0/1)" in body["message"] and fake.calls == 0

    def test_records_older_than_the_window_do_not_count(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[]))
        goal_id, task_id = _goal(client, consented_headers)
        _log(client, consented_headers, task_id, 0, text="회고")
        _log(client, consented_headers, task_id, 13)  # oldest day inside the window (today - 13)
        _log(client, consented_headers, task_id, 14)  # one day too old
        body = _make(client, consented_headers, goal_id).json()
        assert body["is_insufficient"] is True and (body["record_count"]) == 2 and fake.calls == 0

    def test_insufficient_does_not_overwrite_or_start_the_cooldown(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, task_id, logs = _ready(client, consented_headers)
        assert _make(client, consented_headers, goal_id, "a").status_code == 201
        for log in logs:  # now only 0 records remain
            client.delete(f"/api/study-logs/{log['id']}", headers=consented_headers)
        res = _make(client, consented_headers, goal_id, "b")
        assert res.status_code == 200 and res.json()["is_insufficient"] is True
        assert get_store().get("insights", goal_id)["client_request_id"] == "a"  # the earlier insight is untouched
        assert fake.calls == 1


# ----------------------------------------------------------------------------- creating
class TestCreate:
    def test_creates_and_stores_one_document_per_learning(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(difficulty="딕셔너리가 반복해서 어려웠어요.")]))
        goal_id, _, _ = _ready(client, consented_headers)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201
        item = res.json()["insight"]
        assert item["summary"] == "최근 14일 동안의 학습 기록을 바탕으로 한 요약이에요." and item["difficulty"] == "딕셔너리가 반복해서 어려웠어요."
        assert item["next_action"] and item["generated_at"].endswith("Z")
        assert (item["record_count"], item["reflection_count"], item["is_stale"]) == (4, 2, False)
        assert res.json()["is_insufficient"] is False
        assert fake.calls == 1
        doc = get_store().get("insights", goal_id)  # document id = goal id
        assert doc["user_id"] == UID and doc["goal_id"] == goal_id and doc["client_request_id"] == "k1"
        assert {"summary", "difficulty", "next_action", "generated_at", "record_count", "reflection_count", "created_at", "updated_at"} <= set(doc)
        assert len(get_store().find("insights", user_id=UID)) == 1

    def test_what_the_model_receives(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, task_id, _ = _ready(client, consented_headers)
        _make(client, consented_headers, goal_id)
        sent = fake.payloads_seen[0]
        assert sent["learning"]["course"] == "기본문법" and sent["learning"]["weekly_hours"] == 7
        assert sent["window"] == {"from": _day(13), "to": _day(0), "days": 14}
        assert len(sent["records"]) == 4 and sent["records"][0]["study_date"] == _day(0)  # newest first
        assert set(sent["records"][0]) == {"study_date", "minutes", "activity", "task_title"}
        assert [r["content"] for r in sent["reflections"]] == ["회고 0", "회고 1"]
        assert set(sent["reflections"][0]) == {"study_date", "task_title", "content", "tags"}
        # The server does the arithmetic (Phase 6B fix): totals and their display labels are sent ready-made.
        assert sent["progress"] == {
            "completed_tasks": 0,
            "total_tasks": 3,
            "window_record_count": 4,
            "window_total_minutes": 120,
            "window_total_label": "2시간",
            "this_week_minutes": 120,
            "this_week_label": "2시간",
            "weekly_target_minutes": 420,
            "weekly_target_label": "7시간",
            "reflection_count": 2,
        }
        blob = str(sent)
        assert UID not in blob and goal_id not in blob and task_id not in blob  # no identifiers go to the model

    def test_a_new_insight_overwrites_the_old_one_and_keeps_created_at(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(summary="첫 번째"), _ai(summary="두 번째")]))
        goal_id, _, _ = _ready(client, consented_headers)
        _make(client, consented_headers, goal_id, "a")
        created_at = get_store().get("insights", goal_id)["created_at"]
        _age(goal_id, 120)
        res = _make(client, consented_headers, goal_id, "b")
        assert res.status_code == 201 and res.json()["insight"]["summary"] == "두 번째"
        assert len(get_store().find("insights", user_id=UID)) == 1  # no history is kept
        assert get_store().get("insights", goal_id)["created_at"] == created_at

    def test_same_client_request_id_returns_the_stored_result_without_ai(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, _, _ = _ready(client, consented_headers)
        first = _make(client, consented_headers, goal_id, "same")
        again = _make(client, consented_headers, goal_id, "same")
        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json()["insight"]["generated_at"] == first.json()["insight"]["generated_at"]
        assert fake.calls == 1

    def test_cooldown_blocks_a_new_request_but_not_a_replay(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(), _ai(summary="나중")]))
        goal_id, _, _ = _ready(client, consented_headers)
        assert _make(client, consented_headers, goal_id, "a").status_code == 201
        blocked = _make(client, consented_headers, goal_id, "b")
        assert blocked.status_code == 429
        err = blocked.json()["detail"]
        assert err["code"] == "INSIGHT_COOLDOWN" and 1 <= err["details"]["retry_after_seconds"] <= 60
        assert str(err["details"]["retry_after_seconds"]) in err["message"]
        assert _make(client, consented_headers, goal_id, "a").status_code == 200  # replay is exempt
        assert fake.calls == 1
        _age(goal_id, 61)
        assert _make(client, consented_headers, goal_id, "b").status_code == 201 and fake.calls == 2

    def test_the_cooldown_is_per_learning(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(), _ai()]))
        a, _, _ = _ready(client, consented_headers, course="A", start="2026-10-22", target="2026-11-30")
        b, _, _ = _ready(client, consented_headers, course="B", start="2026-10-22", target="2026-11-30")
        assert _make(client, consented_headers, a, "a").status_code == 201
        assert _make(client, consented_headers, b, "b").status_code == 201

    @pytest.mark.parametrize("word", list(main.INSIGHT_FORBIDDEN_TERMS))
    def test_forbidden_wording_is_rejected_retried_and_nothing_is_saved(self, client: TestClient, consented_headers, override_ai, word):
        fake = override_ai(FakeAIClient(raws=[_ai(next_action=f"이번 주 계획이 {word} 상태예요.")] * (MAX_RETRIES + 1)))
        goal_id, _, _ = _ready(client, consented_headers)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 502 and res.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1
        assert get_store().get("insights", goal_id) is None

    @pytest.mark.parametrize(
        "bad",
        [
            _ai(summary="가" * 301),
            _ai(next_action="나" * 301),
            _ai(difficulty="다" * 301),
            _ai(summary=""),
            _ai(next_action="   "),
            _raw({"summary": "내용"}),  # next_action missing
        ],
    )
    def test_schema_and_length_violations_are_rejected(self, client: TestClient, consented_headers, override_ai, bad):
        override_ai(FakeAIClient(raws=[bad] * (MAX_RETRIES + 1)))
        goal_id, _, _ = _ready(client, consented_headers)
        assert _make(client, consented_headers, goal_id).status_code == 502
        assert get_store().get("insights", goal_id) is None

    def test_difficulty_may_be_empty_and_limits_are_inclusive(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(summary="가" * 300, difficulty="", next_action="나" * 300)]))
        goal_id, _, _ = _ready(client, consented_headers)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and res.json()["insight"]["difficulty"] == ""

    def test_a_violation_then_a_valid_answer_succeeds_and_the_model_is_told_why(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(summary="계획이 연체되었어요."), _ai()]))
        goal_id, _, _ = _ready(client, consented_headers)
        assert _make(client, consented_headers, goal_id).status_code == 201 and fake.calls == 2
        assert "validation_error" in fake.payloads_seen[1] and "validation_error" not in fake.payloads_seen[0]

    def test_ai_failure_keeps_the_earlier_insight(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(summary="이전 인사이트")]))
        goal_id, _, _ = _ready(client, consented_headers)
        _make(client, consented_headers, goal_id, "a")
        _age(goal_id, 120)
        override_ai(FakeAIClient(raises=[AIRetryableError("t")] * (MAX_RETRIES + 1)))
        assert _make(client, consented_headers, goal_id, "b").status_code == 504
        doc = get_store().get("insights", goal_id)
        assert doc["summary"] == "이전 인사이트" and doc["client_request_id"] == "a"
        # the same key can be retried once the AI works again
        override_ai(FakeAIClient(raws=[_ai(summary="새 인사이트")]))
        assert _make(client, consented_headers, goal_id, "b").json()["insight"]["summary"] == "새 인사이트"


# ----------------------------------------------------------------------------- reading
class TestRead:
    def test_no_saved_insight_gives_null_and_never_calls_the_ai(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[]))
        goal_id, _, _ = _ready(client, consented_headers)
        res = client.get(f"/api/goals/{goal_id}/insight", headers=consented_headers)
        assert res.status_code == 200 and res.json()["insight"] is None and fake.calls == 0

    def test_get_returns_the_saved_one_without_calling_the_ai(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, _, _ = _ready(client, consented_headers)
        created = _make(client, consented_headers, goal_id).json()["insight"]
        got = client.get(f"/api/goals/{goal_id}/insight", headers=consented_headers).json()["insight"]
        assert got == created and fake.calls == 1

    def test_each_learning_has_its_own_insight_and_records_do_not_mix(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(summary="A 의 인사이트")]))
        a, _, _ = _ready(client, consented_headers, course="A", start="2026-10-22", target="2026-11-30")
        b, b_task = _goal(client, consented_headers, course="B", start="2026-10-22", target="2026-11-30")
        _log(client, consented_headers, b_task, 0, text="B 회고")  # B has too little
        _make(client, consented_headers, a)
        assert len(fake.payloads_seen[0]["records"]) == 4  # only A's own records
        assert client.get(f"/api/goals/{b}/insight", headers=consented_headers).json()["insight"] is None
        assert _make(client, consented_headers, b, "kb").json()["is_insufficient"] is True


class TestStale:
    def _created(self, client, headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, task_id, logs = _ready(client, headers)
        assert _make(client, headers, goal_id).status_code == 201
        return goal_id, task_id, logs

    def _stale(self, client, headers, goal_id):
        return client.get(f"/api/goals/{goal_id}/insight", headers=headers).json()["insight"]["is_stale"]

    def test_fresh_insight_is_not_stale(self, client, consented_headers, override_ai):
        goal_id, _, _ = self._created(client, consented_headers, override_ai)
        assert self._stale(client, consented_headers, goal_id) is False

    def test_adding_a_record_in_the_window_makes_it_stale(self, client, consented_headers, override_ai):
        goal_id, task_id, _ = self._created(client, consented_headers, override_ai)
        _log(client, consented_headers, task_id, 5)
        assert self._stale(client, consented_headers, goal_id) is True

    def test_editing_a_record_makes_it_stale(self, client, consented_headers, override_ai):
        goal_id, _, logs = self._created(client, consented_headers, override_ai)
        get_store().update("study_logs", logs[3]["id"], {"updated_at": "2099-01-01T00:00:00Z"})  # as a later edit would
        assert self._stale(client, consented_headers, goal_id) is True

    def test_editing_through_the_api_makes_it_stale(self, client, consented_headers, override_ai, monkeypatch):
        goal_id, _, logs = self._created(client, consented_headers, override_ai)
        monkeypatch.setattr(main, "_now_iso", lambda: "2099-01-01T00:00:00Z")
        assert client.patch(f"/api/study-logs/{logs[2]['id']}", json={"minutes": 99}, headers=consented_headers).status_code == 200
        assert self._stale(client, consented_headers, goal_id) is True

    def test_deleting_a_record_makes_it_stale(self, client, consented_headers, override_ai):
        goal_id, _, logs = self._created(client, consented_headers, override_ai)
        client.delete(f"/api/study-logs/{logs[3]['id']}", headers=consented_headers)
        assert self._stale(client, consented_headers, goal_id) is True

    def test_editing_a_reflection_makes_it_stale(self, client, consented_headers, override_ai, monkeypatch):
        goal_id, _, logs = self._created(client, consented_headers, override_ai)
        monkeypatch.setattr(main, "_now_iso", lambda: "2099-01-01T00:00:00Z")
        client.patch(f"/api/study-logs/{logs[0]['id']}", json={"reflection": {"content": "고친 회고", "tags": []}}, headers=consented_headers)
        assert self._stale(client, consented_headers, goal_id) is True

    def test_deleting_a_reflection_makes_it_stale(self, client, consented_headers, override_ai):
        goal_id, _, logs = self._created(client, consented_headers, override_ai)
        client.patch(f"/api/study-logs/{logs[1]['id']}", json={"delete_reflection": True}, headers=consented_headers)
        assert self._stale(client, consented_headers, goal_id) is True

    def test_a_new_reflection_makes_it_stale(self, client, consented_headers, override_ai):
        goal_id, _, logs = self._created(client, consented_headers, override_ai)
        client.patch(f"/api/study-logs/{logs[3]['id']}", json={"reflection": {"content": "새 회고", "tags": []}}, headers=consented_headers)
        assert self._stale(client, consented_headers, goal_id) is True

    def test_changes_outside_the_input_do_not_make_it_stale(self, client, consented_headers, override_ai):
        goal_id, task_id, _ = self._created(client, consented_headers, override_ai)
        _log(client, consented_headers, task_id, 30)  # a month old: not part of the window
        client.patch(f"/api/tasks/{task_id}", json={"status": "completed"}, headers=consented_headers)
        assert self._stale(client, consented_headers, goal_id) is False

    def test_the_window_moving_on_makes_it_stale(self, client, consented_headers, override_ai, monkeypatch):
        goal_id, _, _ = self._created(client, consented_headers, override_ai)
        monkeypatch.setattr(clock, "today", lambda: TODAY + timedelta(days=12))  # the oldest records (days 2 and 3 back) leave the window
        assert self._stale(client, consented_headers, goal_id) is True

    def test_regenerating_clears_the_flag(self, client, consented_headers, override_ai):
        goal_id, task_id, _ = self._created(client, consented_headers, override_ai)
        _log(client, consented_headers, task_id, 5)
        assert self._stale(client, consented_headers, goal_id) is True
        override_ai(FakeAIClient(raws=[_ai(summary="갱신")]))
        _age(goal_id, 120)
        assert _make(client, consented_headers, goal_id, "again").json()["insight"]["is_stale"] is False
        assert self._stale(client, consented_headers, goal_id) is False


# ----------------------------------------------------------------------------- input rules
class TestInputs:
    def test_window_boundary_and_the_newest_five_reflections(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, task_id = _goal(client, consented_headers)
        for i in range(7):  # reflections on days 0..6 (newest = day 0)
            _log(client, consented_headers, task_id, i, text=f"회고 {i}")
        _log(client, consented_headers, task_id, 13, text="창 안의 가장 오래된 날")
        _log(client, consented_headers, task_id, 14, text="창 밖")
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201
        sent = fake.payloads_seen[0]
        assert len(sent["records"]) == 8  # days 0..6 and 13; day 14 is outside
        assert [r["content"] for r in sent["reflections"]] == [f"회고 {i}" for i in range(5)]  # newest five, not limited to the window
        assert (res.json()["insight"]["record_count"], res.json()["insight"]["reflection_count"]) == (8, 5)

    def test_an_edited_reflection_is_sent_in_its_latest_form_and_a_deleted_one_not_at_all(self, client, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(), _ai()]))
        goal_id, task_id, logs = _ready(client, consented_headers)
        client.patch(f"/api/study-logs/{logs[0]['id']}", json={"reflection": {"content": "수정된 회고", "tags": []}}, headers=consented_headers)
        _make(client, consented_headers, goal_id, "a")
        assert "수정된 회고" in [r["content"] for r in fake.payloads_seen[0]["reflections"]]
        client.patch(f"/api/study-logs/{logs[0]['id']}", json={"delete_reflection": True}, headers=consented_headers)
        _age(goal_id, 120)
        _make(client, consented_headers, goal_id, "b")
        assert [r["content"] for r in fake.payloads_seen[1]["reflections"]] == ["회고 1"]

    def test_the_client_cannot_supply_records(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[]))
        goal_id, task_id = _goal(client, consented_headers)
        res = client.post(
            f"/api/goals/{goal_id}/insight",
            json={"client_request_id": "k", "records": [{"activity": "x"}] * 5, "reflections": ["y"]},
            headers=consented_headers,
        )
        assert res.status_code == 200 and res.json()["is_insufficient"] is True and fake.calls == 0


# ----------------------------------------------------------------------------- access, deletion, logs
class TestAccessAndCleanup:
    def test_other_users_and_missing_goals(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, _, _ = _ready(client, consented_headers)
        bob = _other_user(client)
        assert client.get(f"/api/goals/{goal_id}/insight", headers=bob).status_code == 403
        res = _make(client, bob, goal_id)
        assert res.status_code == 403 and res.json()["detail"]["code"] == "FORBIDDEN"
        assert client.get("/api/goals/nope/insight", headers=consented_headers).status_code == 404
        assert _make(client, consented_headers, "nope").status_code == 404
        assert client.get(f"/api/goals/{goal_id}/insight").status_code == 401

    def test_consent_is_required(self, client: TestClient, mock_auth_headers):
        assert client.get("/api/goals/x/insight", headers=mock_auth_headers).status_code == 403
        assert client.post("/api/goals/x/insight", json={"client_request_id": "k"}, headers=mock_auth_headers).status_code == 403

    def test_client_request_id_is_required(self, client: TestClient, consented_headers):
        goal_id, _ = _goal(client, consented_headers)
        assert client.post(f"/api/goals/{goal_id}/insight", json={}, headers=consented_headers).status_code == 422

    def test_deleting_the_goal_deletes_its_insight_only(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(), _ai()]))
        a, _, _ = _ready(client, consented_headers, course="A", start="2026-10-22", target="2026-11-30")
        b, _, _ = _ready(client, consented_headers, course="B", start="2026-10-22", target="2026-11-30")
        _make(client, consented_headers, a, "a")
        _make(client, consented_headers, b, "b")
        client.delete(f"/api/goals/{a}", headers=consented_headers)
        assert get_store().get("insights", a) is None and get_store().get("insights", b) is not None

    def test_the_data_deletion_request_removes_insights(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai()]))
        goal_id, _, _ = _ready(client, consented_headers)
        _make(client, consented_headers, goal_id)
        assert "insights" in main.USER_OWNED_COLLECTIONS
        client.post("/api/user/delete-data", headers=consented_headers)
        assert get_store().find("insights", user_id=UID) == []

    def test_no_user_text_reaches_the_logs(self, client: TestClient, consented_headers, override_ai, caplog):
        override_ai(FakeAIClient(raws=[_ai(summary="모델응답ASD", next_action="다음행동ZXC")]))
        goal_id, task_id = _goal(client, consented_headers)
        for i in range(3):
            _log(client, consented_headers, task_id, i, text="비밀회고QWE" if i == 0 else None, activity="비밀활동RTY")
        with caplog.at_level(logging.DEBUG):
            assert _make(client, consented_headers, goal_id).status_code == 201
        for secret in ("비밀회고QWE", "비밀활동RTY", "모델응답ASD", "다음행동ZXC"):
            assert secret not in caplog.text


# ----------------------------------------------------------------------------- dashboard
class TestDashboard:
    def _insight(self, client, headers):
        return client.get("/api/dashboard/summary", headers=headers).json()["insight"]

    def test_three_cases_and_the_dashboard_never_calls_the_ai(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(summary="저장된 요약 문장")]))
        goal_id, task_id = _goal(client, consented_headers)
        # 1) not enough material -> the old guidance
        _log(client, consented_headers, task_id, 0, text="회고")
        got = self._insight(client, consented_headers)
        assert got["is_insufficient"] is True and got["text"] == "기록과 회고를 더 남기면 인사이트를 볼 수 있어요."
        # 2) enough material, nothing generated -> a hint to create it
        _log(client, consented_headers, task_id, 1)
        _log(client, consented_headers, task_id, 2)
        got = self._insight(client, consented_headers)
        assert got["is_insufficient"] is False and got["text"] == "실행 기록 화면에서 인사이트를 만들어 보세요." and got["notice"] == ""
        assert fake.calls == 0
        # 3) generated -> its summary and the fixed notice (also while it is stale)
        assert _make(client, consented_headers, goal_id).status_code == 201
        got = self._insight(client, consented_headers)
        assert got["text"] == "저장된 요약 문장" and got["notice"] == "내 실행 기록과 회고 기반 · AI 생성 안내" and got["is_insufficient"] is False
        _log(client, consented_headers, task_id, 3)  # makes the saved insight stale
        assert self._insight(client, consented_headers)["text"] == "저장된 요약 문장"
        assert fake.calls == 1  # only the explicit POST used the AI

    def test_the_dashboard_follows_the_current_learning(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(summary="A 의 요약")]))
        a, _, _ = _ready(client, consented_headers, course="A", start="2026-10-22", target="2026-11-30")
        b, b_task = _goal(client, consented_headers, course="B", start="2026-10-22", target="2026-11-30")
        _make(client, consented_headers, a)
        client.patch("/api/user/profile", json={"active_goal_id": b}, headers=consented_headers)
        assert self._insight(client, consented_headers)["text"] == "기록과 회고를 더 남기면 인사이트를 볼 수 있어요."
        client.patch("/api/user/profile", json={"active_goal_id": a}, headers=consented_headers)
        assert self._insight(client, consented_headers)["text"] == "A 의 요약"
