"""CR-012: plan generation is three AI calls (field guideline -> design opinion -> JSON), on the plan model.
Fake AI and fake clock only; no real OpenAI call."""

import json
import logging
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import clock
import plan_ai
import prompts
from ai_client import AIClient, AIRetryableError, AIUnavailableError, OpenAIClient, get_ai_client, call_limits
from main import app
from store import get_store

TODAY = date(2026, 10, 21)
REQUEST = {
    "field": "가톨릭 성경 읽기",
    "course": "성경 순서대로 읽기",
    "current_level_order": 1,
    "current_level_name": "입문자",
    "target_level_order": 2,
    "target_level_name": "73권 완독",
    "weekly_hours": 5,
    "target_date": "2026-12-31",
    "start_date": "2026-10-21",
}
GUIDELINE_TEXT = "ZEBRA-GUIDELINE-7731 이 영역은 책과 장 단위로 나눈다."
OPINION_TEXT = "ZEBRA-OPINION-7731 이번에는 구약 앞부분만 다룬다."
PROMPT_INPUT = "ZEBRA-INPUT-7731"


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _plan(minutes=60, n=3, **kw):
    tasks = [{"title": f"과제 {i}", "description": f"창세기 {i}장", "estimated_minutes": minutes} for i in range(1, n + 1)]
    return json.dumps({"tasks": tasks, "advice_title": "조언", "advice_content": "첫 문단\n- 목록", **kw}, ensure_ascii=False)


class StageAI(AIClient):
    """Records every provider call in order: ("text"|"json", system_prompt, payload). The scripts decide
    what each call returns; an Exception instance in a script is raised."""

    def __init__(self, text=None, json_raws=None):
        self.calls = []
        self._text = list(text if text is not None else [GUIDELINE_TEXT, OPINION_TEXT])
        self._json = list(json_raws if json_raws is not None else [_plan()])

    def _next(self, script):
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _raw_text(self, system_prompt, user_payload):
        self.calls.append(("text", system_prompt, user_payload))
        return self._next(self._text)

    def _raw_complete(self, system_prompt, user_payload):
        self.calls.append(("json", system_prompt, user_payload))
        return self._next(self._json)


@pytest.fixture
def use_ai():
    def _set(fake):
        app.dependency_overrides[get_ai_client] = lambda: fake
        return fake

    yield _set
    app.dependency_overrides.pop(get_ai_client, None)


def _generate(client, headers, request=None):
    return client.post("/api/plan/generate", json=request or REQUEST, headers=headers)


class TestThreeCalls:
    def test_three_calls_in_order_and_each_stage_gets_the_previous_text(self, client: TestClient, consented_headers, use_ai):
        ai = use_ai(StageAI())
        res = _generate(client, consented_headers)
        assert res.status_code == 200
        assert [c[0] for c in ai.calls] == ["text", "text", "json"]
        assert [c[1] for c in ai.calls] == [
            prompts.PLAN_GUIDE_SYSTEM_PROMPT,
            prompts.PLAN_OPINION_SYSTEM_PROMPT,
            prompts.PLAN_GENERATE_SYSTEM_PROMPT,
        ]
        guide_payload, opinion_payload, json_payload = (c[2] for c in ai.calls)
        # stage 0: the field, the course and the two level names only (no personal conditions)
        assert set(guide_payload) == {"field", "course", "current_level_name", "target_level_name"}
        assert guide_payload["field"] == "가톨릭 성경 읽기"
        # stage 1: the whole plan request plus the guideline; stage 2: the whole plan request plus the opinion
        assert opinion_payload["guideline"] == GUIDELINE_TEXT and "analysis" not in opinion_payload
        assert json_payload["analysis"] == OPINION_TEXT and "guideline" not in json_payload
        for payload in (opinion_payload, json_payload):
            assert payload["max_total_minutes"] > 0 and payload["weekly_minutes"] == 300 and payload["field"] == "가톨릭 성경 읽기"

    def test_the_response_shape_is_the_same_as_before(self, client: TestClient, consented_headers, use_ai):
        use_ai(StageAI())
        body = _generate(client, consented_headers).json()
        assert {"tasks", "advice", "references", "available_minutes", "total_estimated_minutes", "coverage_percent", "week_count"} <= set(body)
        assert body["advice"] == {"title": "조언", "content": "첫 문단\n- 목록"}
        assert len(body["tasks"]) == 3 and body["tasks"][0]["title"] == "과제 1"

    def test_nothing_is_saved(self, client: TestClient, consented_headers, use_ai):
        use_ai(StageAI())
        before = {name: len(get_store().list_collection(name)) for name in ("goals", "tasks")} if hasattr(get_store(), "list_collection") else None
        assert _generate(client, consented_headers).status_code == 200
        assert client.get("/api/goals", headers=consented_headers).json() == []
        if before is not None:
            assert before == {name: len(get_store().list_collection(name)) for name in ("goals", "tasks")}

    def test_stage_two_over_budget_retries_with_previous_total_minutes(self, client: TestClient, consented_headers, use_ai):
        over = _plan(minutes=6000, n=3)  # 18000 minutes: far above the available time
        ai = use_ai(StageAI(json_raws=[over, _plan()]))
        assert _generate(client, consented_headers).status_code == 200
        kinds = [c[0] for c in ai.calls]
        assert kinds == ["text", "text", "json", "json"]  # the text stages are not repeated
        retry_payload = ai.calls[3][2]
        assert retry_payload["previous_total_minutes"] == 18000 and retry_payload["analysis"] == OPINION_TEXT


class TestFailures:
    @pytest.mark.parametrize("script, status", [
        (["", "x"], 502),  # stage 0 empty text
        ([GUIDELINE_TEXT, "   "], 502),  # stage 1 empty text
        ([AIRetryableError("t"), AIRetryableError("t")], 504),  # stage 0 timed out twice
        ([GUIDELINE_TEXT, AIRetryableError("t"), AIRetryableError("t")], 504),  # stage 1 timed out twice
        ([AIUnavailableError("down")], 503),
    ])
    def test_a_text_stage_failure_stops_the_flow(self, client: TestClient, consented_headers, use_ai, script, status):
        ai = use_ai(StageAI(text=script))
        res = _generate(client, consented_headers)
        assert res.status_code == status
        assert "json" not in [c[0] for c in ai.calls]  # stage 2 was never called
        assert client.get("/api/goals", headers=consented_headers).json() == []

    def test_a_text_stage_timeout_is_retried_once(self, client: TestClient, consented_headers, use_ai):
        ai = use_ai(StageAI(text=[AIRetryableError("t"), GUIDELINE_TEXT, OPINION_TEXT]))
        assert _generate(client, consented_headers).status_code == 200
        assert [c[0] for c in ai.calls] == ["text", "text", "text", "json"]

    def test_stage_two_that_never_validates_is_a_schema_error(self, client: TestClient, consented_headers, use_ai):
        ai = use_ai(StageAI(json_raws=["not json"] * 3))
        assert _generate(client, consented_headers).status_code == 502
        assert [c[0] for c in ai.calls] == ["text", "text", "json", "json", "json"]


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestTimeBudget:
    def test_no_retry_starts_when_too_little_time_is_left(self, client: TestClient, consented_headers, use_ai, monkeypatch):
        fake_clock = _Clock()
        monkeypatch.setattr(plan_ai, "monotonic", fake_clock)

        class Slow(StageAI):
            def _raw_complete(self, system_prompt, user_payload):
                fake_clock.now += 100  # every JSON attempt takes 100 s of the 170 s budget
                return super()._raw_complete(system_prompt, user_payload)

        ai = use_ai(Slow(json_raws=[_plan(6000), _plan(6000), _plan()]))
        res = _generate(client, consented_headers)
        # attempt 1 (rejected, 100 s used) -> attempt 2 (rejected, 200 s used) -> budget gone: no third attempt
        assert res.status_code == 504 and res.json()["detail"]["code"] == "AI_TIMEOUT"
        assert [c[0] for c in ai.calls].count("json") == 2

    def test_a_late_stage_is_not_started_without_time(self, client: TestClient, consented_headers, use_ai, monkeypatch):
        fake_clock = _Clock()
        monkeypatch.setattr(plan_ai, "monotonic", fake_clock)

        class SlowText(StageAI):
            def _raw_text(self, system_prompt, user_payload):
                fake_clock.now += 165  # stage 0 leaves 5 s, below the minimum for another call
                return super()._raw_text(system_prompt, user_payload)

        ai = use_ai(SlowText())
        res = _generate(client, consented_headers)
        assert res.status_code == 504 and res.json()["detail"]["code"] == "AI_TIMEOUT"
        assert [c[0] for c in ai.calls] == ["text"]

    def test_each_attempt_gets_the_time_that_is_left(self, monkeypatch):
        fake_clock = _Clock()
        monkeypatch.setattr(plan_ai, "monotonic", fake_clock)
        seen = []

        class Probe(StageAI):
            def _raw_text(self, system_prompt, user_payload):
                from ai_client import _call_limits

                timeout, tokens, model = _call_limits.get()
                seen.append((timeout(), tokens, model))
                fake_clock.now += 20
                return super()._raw_text(system_prompt, user_payload)

        ai = Probe(json_raws=[_plan()])
        plan_ai.generate_plan_draft(ai, {**REQUEST, "max_total_minutes": 10000, "weekly_minutes": 300}, lambda p: None)
        # plan timeout is 60 s by default; the budget (170 s) is not the limit yet
        assert seen[0] == (60.0, plan_ai.GUIDE_MAX_TOKENS, "gpt-5.4-mini")
        assert seen[1] == (60.0, plan_ai.OPINION_MAX_TOKENS, "gpt-5.4-mini")


class TestModelAndJsonMode:
    """What really reaches the OpenAI SDK, with the SDK call replaced."""

    @pytest.fixture
    def openai_client(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
        monkeypatch.delenv("OPENAI_PLAN_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        client = OpenAIClient()
        sent = []

        def fake_create(**kwargs):
            sent.append(kwargs)
            msg = SimpleNamespace(content="안녕" if "response_format" not in kwargs else "{}")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
        # with_options() returns a copy of the SDK client; keep the patched one so the call stays in the test
        monkeypatch.setattr(client._client, "with_options", lambda **kw: client._client)
        return client, sent

    def test_plan_stages_use_the_plan_model_text_without_json_mode_and_json_with_it(self, openai_client, monkeypatch):
        client, sent = openai_client
        draft_json = json.loads(_plan())

        def create(**kwargs):
            sent.append(kwargs)
            content = json.dumps(draft_json, ensure_ascii=False) if "response_format" in kwargs else "글"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        monkeypatch.setattr(client._client.chat.completions, "create", create)
        plan_ai.generate_plan_draft(client, {**REQUEST, "max_total_minutes": 10000, "weekly_minutes": 300}, lambda p: None)
        assert [s["model"] for s in sent] == ["gpt-5.4-mini"] * 3
        assert ["response_format" in s for s in sent] == [False, False, True]
        assert sent[2]["response_format"] == {"type": "json_object"}
        assert [s["max_completion_tokens"] for s in sent] == [6000, 8000, 8000]
        assert all("temperature" not in s and "max_tokens" not in s for s in sent)

    def test_the_plan_model_can_be_set_by_the_environment(self, openai_client, monkeypatch):
        client, sent = openai_client
        monkeypatch.setenv("OPENAI_PLAN_MODEL", "plan-model-x")
        with call_limits(30, 100, plan_ai.plan_model()):
            client._raw_text("s", {})
        assert sent[0]["model"] == "plan-model-x"

    def test_other_calls_keep_the_default_model_and_json_mode(self, openai_client):
        client, sent = openai_client
        client._raw_complete("s", {})  # the tutor, insight, path... go this way
        assert sent[0]["model"] == "gpt-4o-mini" and sent[0]["response_format"] == {"type": "json_object"}

    def test_the_default_model_for_the_others_follows_openai_model(self, openai_client, monkeypatch):
        client, sent = openai_client
        monkeypatch.setenv("OPENAI_MODEL", "other-default")
        client._raw_complete("s", {})
        assert sent[0]["model"] == "other-default"

    def test_a_client_without_free_text_is_unavailable_not_a_crash(self):
        class JsonOnly(AIClient):
            def _raw_complete(self, system_prompt, user_payload):
                return "{}"

        with pytest.raises(AIUnavailableError):
            JsonOnly().generate_text("s", {})


class TestLogs:
    def test_logs_carry_stage_names_and_seconds_but_no_text_or_input(self, client: TestClient, consented_headers, use_ai, caplog):
        request = {**REQUEST, "field": f"{PROMPT_INPUT} 분야"}
        use_ai(StageAI())
        with caplog.at_level(logging.DEBUG):
            assert _generate(client, consented_headers, request).status_code == 200
        text = "\n".join(r.getMessage() for r in caplog.records)
        for secret in ("ZEBRA-GUIDELINE-7731", "ZEBRA-OPINION-7731", PROMPT_INPUT, "창세기", "첫 문단"):
            assert secret not in text
        assert "plan_stage stage=guide result=ok" in text and "stage=opinion" in text and "stage=json" in text

    def test_a_failure_log_has_the_kind_only(self, client: TestClient, consented_headers, use_ai, caplog):
        use_ai(StageAI(text=[GUIDELINE_TEXT, ""]))
        with caplog.at_level(logging.DEBUG):
            assert _generate(client, consented_headers).status_code == 502
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "plan_stage stage=opinion result=failed kind=AISchemaError" in text and "ZEBRA" not in text


class TestPromptsAndConfig:
    def test_the_guideline_is_not_stored_or_reused(self, client: TestClient, consented_headers, use_ai):
        ai = use_ai(StageAI(text=[GUIDELINE_TEXT, OPINION_TEXT, "SECOND-GUIDELINE", OPINION_TEXT], json_raws=[_plan(), _plan()]))
        _generate(client, consented_headers)
        _generate(client, consented_headers)
        guide_calls = [c for c in ai.calls if c[1] == prompts.PLAN_GUIDE_SYSTEM_PROMPT]
        assert len(guide_calls) == 2  # rebuilt for every request

    def test_the_three_prompts_exist_and_the_json_prompt_keeps_the_korean_rule(self):
        assert "영역별 학습 설계 지침" in prompts.PLAN_GUIDE_SYSTEM_PROMPT and "한국어 1500자 이내" in prompts.PLAN_GUIDE_SYSTEM_PROMPT
        assert "학습 설계 전문가이자 독학 학습자의 페이스메이커" in prompts.PLAN_OPINION_SYSTEM_PROMPT and "한국어 2500자 이내" in prompts.PLAN_OPINION_SYSTEM_PROMPT
        assert prompts.KOREAN_OUTPUT_RULE in prompts.PLAN_GENERATE_SYSTEM_PROMPT
        assert prompts.PLAN_GENERATE_SYSTEM_PROMPT.rstrip().endswith("덧붙이지 않는다.")

    def test_env_example_names_the_plan_model_without_a_value(self):
        import pathlib

        example = (pathlib.Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
        assert "OPENAI_PLAN_MODEL" in example
        line = [l for l in example.splitlines() if "OPENAI_PLAN_MODEL" in l and "=" in l][0]
        assert line.lstrip().startswith("#")  # commented: the default works without a value
