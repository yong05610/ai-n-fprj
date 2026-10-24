"""Phase 6B fix 2: with fewer than two reflections the model is not asked for `difficulty`
(R4-1), the R2 safety net stays (R4-2), and every rejected attempt logs only a category (R4-3).
"""

import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
import main
from ai_client import MAX_RETRIES, AIClient, AIRetryFeedback
from ai_schemas import AIInsight, AIInsightBasic
from prompts import INSIGHT_SYSTEM_PROMPT, INSIGHT_SYSTEM_PROMPT_BASIC
from store import get_store
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm

TODAY = date(2026, 10, 22)


class PromptRecordingAI(FakeAIClient):
    """FakeAIClient that also remembers the system prompt of every attempt."""

    def __init__(self, raws=None, raises=None):
        super().__init__(raws=raws, raises=raises)
        self.prompts: list[str] = []

    def _raw_complete(self, system_prompt, user_payload):
        self.prompts.append(system_prompt)
        return super()._raw_complete(system_prompt, user_payload)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _case(client, headers, reflections):
    """Four records (30, 31, 32, 20 = 113 minutes) with `reflections` reflection(s)."""
    res = _confirm(client, headers, start="2026-10-22", target="2026-12-31")
    goal_id, task_id = res.json()["goal"]["id"], res.json()["tasks"][0]["id"]
    for offset, minutes in enumerate([30, 31, 32, 20]):
        body = {"task_id": task_id, "study_date": f"2026-10-{22 - offset}", "minutes": minutes, "activity": f"활동 {offset}"}
        if offset < reflections:
            body["reflection"] = {"content": f"회고 {offset}", "tags": []}
        assert client.post("/api/study-logs", json=body, headers=headers).status_code == 201
    return goal_id


def _make(client, headers, goal_id, key="k1"):
    return client.post(f"/api/goals/{goal_id}/insight", json={"client_request_id": key}, headers=headers)


def _basic(summary="총 1시간 53분 학습했어요.", next_action="다음에는 짧은 복습부터 시작해 보세요."):
    return _raw({"summary": summary, "next_action": next_action})


def _full(summary="총 1시간 53분 학습했어요.", difficulty="딕셔너리가 반복해서 어려웠어요.", next_action="다음에는 짧은 복습부터 시작해 보세요."):
    return _raw({"summary": summary, "difficulty": difficulty, "next_action": next_action})


def _rejects(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("insight_validation_reject")]


# ----------------------------------------------------------------------------- R4-1
class TestDifficultyNotRequested:
    def test_the_basic_prompt_never_mentions_difficulty(self):
        assert "difficulty" not in INSIGHT_SYSTEM_PROMPT_BASIC
        assert '{"summary":"...","next_action":"..."}' in INSIGHT_SYSTEM_PROMPT_BASIC
        assert "이번 요청은 summary 와 next_action 만 출력한다." in INSIGHT_SYSTEM_PROMPT_BASIC

    def test_the_full_prompt_still_asks_for_it(self):
        assert '"difficulty"' in INSIGHT_SYSTEM_PROMPT and "서로 다른 회고 두 건 이상" in INSIGHT_SYSTEM_PROMPT

    def test_both_prompts_share_the_numeric_and_tone_rules(self):
        for prompt in (INSIGHT_SYSTEM_PROMPT, INSIGHT_SYSTEM_PROMPT_BASIC):
            assert "스스로 더하거나" in prompt and "window_total_label" in prompt
            assert "추천 요일은 마감일이 아니다" in prompt
            assert "부족하다" in prompt and "평가 어조" in prompt  # R4-4: no evaluative wording about the goal
            assert "validation_error" in prompt

    def test_the_basic_schema_has_no_requested_difficulty_and_the_full_one_does(self):
        assert AIInsight.model_json_schema()["required"] == ["summary", "next_action"]  # difficulty defaults to ""
        assert "difficulty" in AIInsight.model_fields
        assert set(AIInsightBasic.model_json_schema()["required"]) == {"summary", "next_action"}

    def test_one_reflection_uses_the_basic_prompt_and_stores_an_empty_difficulty(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(PromptRecordingAI(raws=[_basic()]))
        goal_id = _case(client, consented_headers, reflections=1)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and fake.calls == 1
        assert fake.prompts == [INSIGHT_SYSTEM_PROMPT_BASIC]
        assert res.json()["insight"]["difficulty"] == ""
        assert get_store().get("insights", goal_id)["difficulty"] == ""

    def test_two_reflections_use_the_full_prompt_and_keep_the_difficulty(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(PromptRecordingAI(raws=[_full()]))
        goal_id = _case(client, consented_headers, reflections=2)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and fake.prompts == [INSIGHT_SYSTEM_PROMPT]
        assert res.json()["insight"]["difficulty"] == "딕셔너리가 반복해서 어려웠어요."

    def test_two_reflections_may_still_leave_it_empty(self, client: TestClient, consented_headers, override_ai):
        override_ai(PromptRecordingAI(raws=[_full(difficulty="")]))
        goal_id = _case(client, consented_headers, reflections=2)
        assert _make(client, consented_headers, goal_id).json()["insight"]["difficulty"] == ""

    def test_the_prompt_is_chosen_again_on_every_request(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(PromptRecordingAI(raws=[_basic(), _full()]))
        goal_id = _case(client, consented_headers, reflections=1)
        _make(client, consented_headers, goal_id, "a")
        # a second reflection arrives, then the insight is made again
        logs = client.get("/api/study-logs", params={"period": "all"}, headers=consented_headers).json()
        target = next(log for log in logs if log["reflection"] is None)
        client.patch(f"/api/study-logs/{target['id']}", json={"reflection": {"content": "새 회고", "tags": []}}, headers=consented_headers)
        get_store().update("insights", goal_id, {"generated_at": "2000-01-01T00:00:00Z"})  # past the cooldown
        _make(client, consented_headers, goal_id, "b")
        assert fake.prompts == [INSIGHT_SYSTEM_PROMPT_BASIC, INSIGHT_SYSTEM_PROMPT]


# ----------------------------------------------------------------------------- R4-2 (safety net stays)
class TestSafetyNetStays:
    def test_a_stray_difficulty_with_one_reflection_is_still_rejected(self, client: TestClient, consented_headers, override_ai):
        stray = _full(difficulty="for 문 차이가 반복적으로 언급되었어요.")
        fake = override_ai(PromptRecordingAI(raws=[stray] * (MAX_RETRIES + 1)))
        goal_id = _case(client, consented_headers, reflections=1)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 502 and fake.calls == MAX_RETRIES + 1
        assert fake.payloads_seen[1]["validation_error"] == "회고가 2건 미만이면 difficulty 를 비워야 합니다."
        assert get_store().get("insights", goal_id) is None

    def test_the_stray_value_is_not_dropped_silently_by_the_basic_schema(self):
        parsed = AIInsightBasic.model_validate_json(_full(difficulty="몰래 들어온 값"))
        assert parsed.difficulty == "몰래 들어온 값"
        facts = main.insight_rules.build_facts([30], [1], 30, 30, 420, 1, 1, 0, 1)
        with pytest.raises(AIRetryFeedback) as caught:
            main._validate_ai_insight(parsed, facts, reflection_count=1)
        assert caught.value.reason == "difficulty_without_reflections"


# ----------------------------------------------------------------------------- R4-3 (reject reasons, categories only)
class TestRejectLogging:
    def test_each_rejected_attempt_logs_a_reason_and_the_attempt_number(self, client: TestClient, consented_headers, override_ai, caplog):
        override_ai(PromptRecordingAI(raws=[_full(difficulty="반복된 어려움")] * (MAX_RETRIES + 1)))
        goal_id = _case(client, consented_headers, reflections=1)
        with caplog.at_level(logging.INFO, logger="pacemate.insight"):
            assert _make(client, consented_headers, goal_id).status_code == 502
        assert _rejects(caplog) == [
            "insight_validation_reject reason=difficulty_without_reflections attempt=1",
            "insight_validation_reject reason=difficulty_without_reflections attempt=2",
            "insight_validation_reject reason=difficulty_without_reflections attempt=3",
        ]

    @pytest.mark.parametrize(
        "raw,reason",
        [
            (_basic(summary="총 4시간 53분 했어요."), "quantity"),
            (_basic(next_action="이번 주 계획이 연체 상태예요."), "forbidden_term"),
            (_basic(summary=""), "empty_part"),
            (_raw({"summary": "내용"}), "empty_part"),  # next_action missing
            (_basic(summary="가" * 301), "length"),
            ("이건 JSON 이 아니에요", "other"),
        ],
    )
    def test_reason_categories(self, client: TestClient, consented_headers, override_ai, caplog, raw, reason):
        override_ai(PromptRecordingAI(raws=[raw, _basic()]))
        goal_id = _case(client, consented_headers, reflections=1)
        with caplog.at_level(logging.INFO, logger="pacemate.insight"):
            assert _make(client, consented_headers, goal_id).status_code == 201  # rejected once, then accepted
        assert _rejects(caplog) == [f"insight_validation_reject reason={reason} attempt=1"]

    def test_a_successful_first_attempt_logs_nothing(self, client: TestClient, consented_headers, override_ai, caplog):
        override_ai(PromptRecordingAI(raws=[_basic()]))
        goal_id = _case(client, consented_headers, reflections=1)
        with caplog.at_level(logging.INFO, logger="pacemate.insight"):
            _make(client, consented_headers, goal_id)
        assert _rejects(caplog) == []

    def test_no_user_text_numbers_or_ids_reach_the_log_lines(self, client: TestClient, consented_headers, override_ai, caplog):
        secret = "비밀요약내용ZXC 4시간 53분"
        override_ai(PromptRecordingAI(raws=[_basic(summary=secret)] * (MAX_RETRIES + 1)))
        goal_id = _case(client, consented_headers, reflections=1)
        with caplog.at_level(logging.DEBUG):
            assert _make(client, consented_headers, goal_id).status_code == 502
        lines = _rejects(caplog)
        assert len(lines) == MAX_RETRIES + 1
        everything = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("pacemate"))  # the test client's own httpx line shows the URL
        for forbidden in ("비밀요약내용ZXC", "4시간", "53분", "test-uid", goal_id, "회고 0"):
            assert forbidden not in everything
        for line in lines:  # nothing but the fixed shape
            assert line.startswith("insight_validation_reject reason=") and " attempt=" in line

    def test_timeouts_are_counted_as_other(self, client: TestClient, consented_headers, override_ai, caplog):
        from ai_client import AIRetryableError

        override_ai(PromptRecordingAI(raises=[AIRetryableError("t"), AIRetryableError("t")], raws=[_basic()]))
        goal_id = _case(client, consented_headers, reflections=1)
        with caplog.at_level(logging.INFO, logger="pacemate.insight"):
            assert _make(client, consented_headers, goal_id).status_code == 201
        assert _rejects(caplog) == [
            "insight_validation_reject reason=other attempt=1",
            "insight_validation_reject reason=other attempt=2",
        ]

    def test_other_ai_users_of_generate_are_not_affected(self):
        class OneShot(AIClient):
            def _raw_complete(self, system_prompt, user_payload):
                return json.dumps({"summary": "x", "next_action": "y"})

        assert OneShot().generate("p", {}, AIInsightBasic).summary == "x"  # on_reject is optional
