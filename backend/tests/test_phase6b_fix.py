"""Phase 6B fix: the server computes insight numbers and checks the numbers in the AI's text (R1),
and `difficulty` needs at least two reflections (R2).

The regression data is the case the PM found with a real model: 4 records of 30, 31, 32 and
20 minutes (113 minutes in total) and ONE reflection. The model wrote "4시간 53분" (the real
total is 1시간 53분) and "반복적으로" although there was a single reflection.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
import insight_rules
import main
from ai_client import MAX_RETRIES
from store import get_store
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm

TODAY = date(2026, 10, 22)  # Thursday, so offsets 0..3 are all inside the current week
FACTS = insight_rules.build_facts(
    record_minutes=[30, 31, 32, 20],
    record_count_by_task=[4],
    window_total_minutes=113,
    this_week_minutes=113,
    weekly_target_minutes=420,
    window_record_count=4,
    reflection_count=1,
    completed_tasks=0,
    total_tasks=1,
)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _ai(summary="좋은 흐름이에요.", difficulty="", next_action="다음에는 짧은 복습부터 시작해 보세요."):
    return _raw({"summary": summary, "difficulty": difficulty, "next_action": next_action})


def _pm_case(client, headers, reflections=1):
    """Four records (113 minutes) with `reflections` reflection(s); returns the goal id."""
    res = _confirm(client, headers, start="2026-10-22", target="2026-12-31")
    goal_id, task_id = res.json()["goal"]["id"], res.json()["tasks"][0]["id"]
    for offset, minutes in enumerate([30, 31, 32, 20]):
        body = {"task_id": task_id, "study_date": f"2026-10-{22 - offset}", "minutes": minutes, "activity": f"활동 {offset}"}
        if offset < reflections:
            body["reflection"] = {"content": "for 문과 while 문 차이가 아직 헷갈린다" if offset == 0 else f"회고 {offset}", "tags": []}
        assert client.post("/api/study-logs", json=body, headers=headers).status_code == 201
    return goal_id


def _make(client, headers, goal_id, key="k1"):
    return client.post(f"/api/goals/{goal_id}/insight", json={"client_request_id": key}, headers=headers)


# ----------------------------------------------------------------------------- display rule
class TestFormatMinutes:
    @pytest.mark.parametrize(
        "minutes,label",
        [(0, "0분"), (1, "1분"), (45, "45분"), (59, "59분"), (60, "1시간"), (61, "1시간 1분"), (113, "1시간 53분"),
         (119, "1시간 59분"), (120, "2시간"), (121, "2시간 1분"), (420, "7시간"), (1500, "25시간")],
    )
    def test_labels(self, minutes, label):
        assert insight_rules.format_minutes(minutes) == label


# ----------------------------------------------------------------------------- extraction rules
class TestExtraction:
    def _bad(self, text, facts=FACTS):
        return insight_rules.find_unsupported_quantities([text], facts)

    def test_the_real_error_is_found(self):
        assert self._bad("총 4시간 53분의 학습을 했어요.") == ["4시간 53분"]

    @pytest.mark.parametrize(
        "text",
        [
            "총 1시간 53분 학습했어요.",
            "총 113분 학습했어요.",
            "이번 주 목표 7시간 중 1시간 53분을 했어요.",
            "목표는 주 420분이에요.",
            "가장 길게 한 날은 32분이에요.",
            "4건의 기록이 있어요.",
            "회고는 1건이에요.",
            "4번 학습했어요.",
            "0분",
            "시간과 분 같은 단어만 있고 숫자는 없어요.",
        ],
    )
    def test_values_the_server_provided_pass(self, text):
        assert self._bad(text) == []

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("총 4시간 53분", ["4시간 53분"]),
            ("총 53분", ["53분"]),
            ("총 4시간", ["4시간"]),
            ("하루 평균 28분", ["28분"]),  # an average the model computed itself
            ("5건의 기록", ["5건"]),
            ("3회 학습", ["3회"]),
            ("10번 복습", ["10번"]),
            ("1시간 53분 중 1시간 54분", ["1시간 54분"]),
            ("12시간 53분이고 15분", ["12시간 53분", "15분"]),
        ],
    )
    def test_other_values_are_found(self, text, expected):
        assert self._bad(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "10월 23일부터 시작했어요.",
            "3일 동안 학습했어요.",
            "목요일에 했어요.",
            "2번째 과제예요.",
            "세 시간 정도(한글 숫자는 검사하지 않아요).",
            "1주일 동안",
        ],
    )
    def test_dates_weekdays_ordinals_and_word_numbers_are_not_checked(self, text):
        assert self._bad(text) == []

    def test_spacing_variants_are_read_the_same_way(self):
        assert self._bad("총 4 시간 53 분") == ["4 시간 53 분"]
        assert self._bad("총 1 시간 53 분") == []
        assert self._bad("총 1시간53분") == []

    def test_every_text_part_is_checked(self):
        assert insight_rules.find_unsupported_quantities(["괜찮은 요약", "문제 99건", "다음엔 77분"], FACTS) == ["99건", "77분"]


# ----------------------------------------------------------------------------- regression, R1
class TestRegressionNumbers:
    def test_the_server_sends_ready_made_numbers(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai()]))
        goal_id = _pm_case(client, consented_headers)
        assert _make(client, consented_headers, goal_id).status_code == 201
        progress = fake.payloads_seen[0]["progress"]
        assert progress["window_record_count"] == 4
        assert (progress["window_total_minutes"], progress["window_total_label"]) == (113, "1시간 53분")
        assert (progress["this_week_minutes"], progress["this_week_label"]) == (113, "1시간 53분")
        assert (progress["weekly_target_minutes"], progress["weekly_target_label"]) == (420, "7시간")
        assert progress["reflection_count"] == 1

    def test_a_wrong_total_is_rejected_retried_and_nothing_is_saved(self, client: TestClient, consented_headers, override_ai):
        wrong = _ai(summary="총 4시간 53분의 학습을 했고 113분으로 기록되어 있어요.")  # the PM's real case
        fake = override_ai(FakeAIClient(raws=[wrong] * (MAX_RETRIES + 1)))
        goal_id = _pm_case(client, consented_headers)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 502 and res.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1
        assert get_store().get("insights", goal_id) is None
        # the retry tells the model which expression was wrong (not an error message to the user)
        assert "4시간 53분" in fake.payloads_seen[1]["validation_error"]
        assert "validation_error" not in fake.payloads_seen[0]

    @pytest.mark.parametrize("summary", ["총 1시간 53분 학습했어요.", "총 113분 학습했어요.", "총 1시간 53분(113분) 학습했고 4건 기록했어요."])
    def test_the_correct_total_passes(self, client: TestClient, consented_headers, override_ai, summary):
        fake = override_ai(FakeAIClient(raws=[_ai(summary=summary)]))
        goal_id = _pm_case(client, consented_headers)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and res.json()["insight"]["summary"] == summary and fake.calls == 1

    def test_wrong_then_right_succeeds_on_the_retry(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(summary="총 4시간 53분 했어요."), _ai(summary="총 1시간 53분 했어요.")]))
        goal_id = _pm_case(client, consented_headers)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and fake.calls == 2
        assert res.json()["insight"]["summary"] == "총 1시간 53분 했어요."

    @pytest.mark.parametrize("field", ["summary", "difficulty", "next_action"])
    def test_a_wrong_number_in_any_part_is_rejected(self, client: TestClient, consented_headers, override_ai, field):
        kwargs = {field: "다음에는 99분 동안 복습해 보세요."}
        # difficulty needs two reflections to be allowed at all, so give it two for this check
        fake = override_ai(FakeAIClient(raws=[_ai(**kwargs)] * (MAX_RETRIES + 1)))
        goal_id = _pm_case(client, consented_headers, reflections=2)
        assert _make(client, consented_headers, goal_id).status_code == 502 and fake.calls == MAX_RETRIES + 1

    def test_counts_and_single_record_values_are_checked_too(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(summary="5건 기록했어요.")] * (MAX_RETRIES + 1)))
        goal_id = _pm_case(client, consented_headers)
        assert _make(client, consented_headers, goal_id).status_code == 502
        override_ai(FakeAIClient(raws=[_ai(summary="가장 길게 한 날은 32분이에요.")]))
        assert _make(client, consented_headers, goal_id, "other").status_code == 201

    def test_dates_and_day_counts_are_not_checked(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(summary="10월 19일부터 4일 동안 이어서 학습했어요.")]))
        goal_id = _pm_case(client, consented_headers)
        assert _make(client, consented_headers, goal_id).status_code == 201

    def test_the_weekly_target_and_task_counts_are_allowed(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(next_action="주 7시간 목표 중 1시간 53분을 했고 과제는 1건 중 0건 완료예요.")]))
        goal_id = _pm_case(client, consented_headers)
        assert _make(client, consented_headers, goal_id).status_code == 201


# ----------------------------------------------------------------------------- regression, R2
class TestDifficultyNeedsTwoReflections:
    def test_one_reflection_and_a_filled_difficulty_is_rejected(self, client: TestClient, consented_headers, override_ai):
        filled = _ai(difficulty="for 문과 while 문의 차이가 반복적으로 언급되었어요.")  # the PM's real case
        fake = override_ai(FakeAIClient(raws=[filled] * (MAX_RETRIES + 1)))
        goal_id = _pm_case(client, consented_headers, reflections=1)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 502 and fake.calls == MAX_RETRIES + 1
        assert fake.payloads_seen[1]["validation_error"] == "회고가 2건 미만이면 difficulty 를 비워야 합니다."
        assert get_store().get("insights", goal_id) is None

    def test_one_reflection_and_an_empty_difficulty_passes(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(difficulty="")]))
        goal_id = _pm_case(client, consented_headers, reflections=1)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and res.json()["insight"]["difficulty"] == ""

    def test_filled_then_empty_succeeds_on_the_retry(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(difficulty="반복된 어려움"), _ai(difficulty="")]))
        goal_id = _pm_case(client, consented_headers, reflections=1)
        assert _make(client, consented_headers, goal_id).status_code == 201 and fake.calls == 2

    def test_two_or_more_reflections_may_fill_it(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(difficulty="딕셔너리가 반복해서 어려웠어요.")]))
        goal_id = _pm_case(client, consented_headers, reflections=2)
        res = _make(client, consented_headers, goal_id)
        assert res.status_code == 201 and res.json()["insight"]["difficulty"] == "딕셔너리가 반복해서 어려웠어요."

    def test_the_model_is_told_how_many_reflections_there_are(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(), _ai()]))
        goal_id = _pm_case(client, consented_headers, reflections=2)
        _make(client, consented_headers, goal_id)
        assert fake.payloads_seen[0]["progress"]["reflection_count"] == 2
        assert len(fake.payloads_seen[0]["reflections"]) == 2

    def test_the_prompt_states_both_rules(self):
        from prompts import INSIGHT_SYSTEM_PROMPT as P

        assert "스스로 더하거나" in P and "*_label" in P and "window_total_label" in P
        assert "서로 다른 회고 두 건 이상" in P and "reflection_count" in P
        assert "추천 요일은 마감일이 아니다" in P  # the earlier rules are still there
