"""Phase 5D: advice saved at plan confirmation, GET /api/goals/{id}/references."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from tests.test_phase5b_multi import _confirm, _confirm_payload, _other_user

TODAY = date(2026, 10, 21)

ADVICE = {"advice_title": "짧게 나누어 꾸준히", "advice_content": "주 7시간을 짧은 세션으로 나누어 진행해 보세요."}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _post(client, headers, **overrides):
    return client.post("/api/plan/confirm", json=_confirm_payload(**overrides), headers=headers)


class TestAdviceOnConfirm:
    def test_advice_is_saved_and_returned_everywhere_the_goal_is(self, client: TestClient, consented_headers):
        res = _post(client, consented_headers, **ADVICE)
        assert res.status_code == 201
        goal = res.json()["goal"]
        assert goal["advice_title"] == ADVICE["advice_title"] and goal["advice_content"] == ADVICE["advice_content"]
        got = client.get(f"/api/goals/{goal['id']}", headers=consented_headers).json()
        assert got["advice_title"] == ADVICE["advice_title"] and got["advice_content"] == ADVICE["advice_content"]
        listed = client.get("/api/goals", headers=consented_headers).json()[0]
        assert listed["advice_content"] == ADVICE["advice_content"]

    def test_goal_without_advice_has_null_fields(self, client: TestClient, consented_headers):
        goal = _post(client, consented_headers).json()["goal"]
        assert goal["advice_title"] is None and goal["advice_content"] is None
        got = client.get(f"/api/goals/{goal['id']}", headers=consented_headers).json()
        assert got["advice_title"] is None and got["advice_content"] is None

    def test_goals_created_through_post_goals_have_no_advice(self, client: TestClient, consented_headers):
        body = {
            "field": "Python 개발", "course": "기본문법", "current_level_order": 1, "current_level_name": "입문",
            "target_level_order": 2, "target_level_name": "실무", "weekly_hours": 5, "target_date": "2026-12-31",
        }
        goal = client.post("/api/goals", json=body, headers=consented_headers).json()
        assert goal["advice_title"] is None and goal["advice_content"] is None

    @pytest.mark.parametrize("only", [{"advice_title": "제목만"}, {"advice_content": "내용만"}])
    def test_only_one_of_the_two_is_422_and_saves_nothing(self, client: TestClient, consented_headers, only):
        res = _post(client, consented_headers, **only)
        assert res.status_code == 422
        assert client.get("/api/goals", headers=consented_headers).json() == []

    @pytest.mark.parametrize(
        "bad",
        [
            {"advice_title": "가" * 201, "advice_content": "내용"},
            {"advice_title": "제목", "advice_content": "가" * 4001},
            {"advice_title": "", "advice_content": "내용"},
            {"advice_title": "   ", "advice_content": "내용"},
            {"advice_title": "제목", "advice_content": "   "},
        ],
    )
    def test_length_and_blank_limits(self, client: TestClient, consented_headers, bad):
        assert _post(client, consented_headers, **bad).status_code == 422
        assert client.get("/api/goals", headers=consented_headers).json() == []

    def test_limits_are_inclusive(self, client: TestClient, consented_headers):
        res = _post(client, consented_headers, advice_title="가" * 200, advice_content="나" * 4000)
        assert res.status_code == 201
        assert len(res.json()["goal"]["advice_content"]) == 4000

    def test_idempotent_retry_returns_the_stored_goal_and_does_not_rewrite_advice(self, client: TestClient, consented_headers):
        first = _post(client, consented_headers, client_request_id="a-1", **ADVICE)
        retry = _post(client, consented_headers, client_request_id="a-1", advice_title="다른 제목", advice_content="다른 내용")
        assert (first.status_code, retry.status_code) == (201, 200)
        assert retry.json()["goal"]["id"] == first.json()["goal"]["id"]
        assert retry.json()["goal"]["advice_title"] == ADVICE["advice_title"]
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 1

    def test_advice_text_is_not_logged(self, client: TestClient, consented_headers, caplog):
        import logging

        with caplog.at_level(logging.DEBUG):
            assert _post(client, consented_headers, advice_title="비밀제목ZXC", advice_content="비밀내용QWE").status_code == 201
        assert "비밀제목ZXC" not in caplog.text and "비밀내용QWE" not in caplog.text


class TestGoalReferences:
    def test_matching_field_returns_reviewed_documents_without_notice(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers).json()["goal"]  # field "Python 개발"
        res = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["references_notice"] is None
        assert {r["title"] for r in body["references"]} >= {"Python 공식 튜토리얼 — 기본 문법", "Python 자료구조 공식 가이드"}
        first = body["references"][0]
        assert set(first) == {"title", "category", "source_name", "url", "is_verified"} and first["is_verified"] is True
        assert first["source_name"] == "Python 공식 문서"  # shown as "{source} · {category}" on the plan screen
        assert first["category"].startswith("Python 개발 /")

    def test_same_result_as_plan_generate_would_use(self, client: TestClient, consented_headers):
        import resources_catalog

        goal = _confirm(client, consented_headers).json()["goal"]
        expected = [m["title"] for m in resources_catalog.match_references(goal["field"], goal["course"])]
        got = [r["title"] for r in client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()["references"]]
        assert got == expected

    def test_field_without_material_gets_the_notice_and_no_references(self, client: TestClient, consented_headers):
        payload = _confirm_payload(course="로켓 설계")
        payload["field"] = "우주공학"
        goal = client.post("/api/plan/confirm", json=payload, headers=consented_headers).json()["goal"]
        body = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()
        assert body["references"] == []
        assert "검토 자료를 찾지 못했습니다" in body["references_notice"]
        assert "우주공학" in body["references_notice"]  # the suggested search keywords name the field

    def test_other_users_goal_is_403_unknown_is_404_and_consent_is_required(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers).json()["goal"]
        bob = _other_user(client)
        res = client.get(f"/api/goals/{goal['id']}/references", headers=bob)
        assert res.status_code == 403 and res.json()["detail"]["code"] == "FORBIDDEN"
        assert client.get("/api/goals/nope/references", headers=consented_headers).status_code == 404
        assert client.get(f"/api/goals/{goal['id']}/references").status_code == 401

    def test_requires_consent(self, client: TestClient, mock_auth_headers):
        assert client.get("/api/goals/anything/references", headers=mock_auth_headers).status_code == 403
