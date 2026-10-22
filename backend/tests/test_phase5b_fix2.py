"""Phase 5B fix round 2: user-chosen start date (F1), full overlap report (F2), role ideas (F5)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from ai_client import AIRetryableError, MAX_RETRIES
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm, _other_user

TODAY = date(2026, 10, 21)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


class TestStartDateChosenByUser:
    def test_far_future_goals_only_block_when_two_of_them_are_inside_the_new_period(
        self, client: TestClient, consented_headers
    ):
        assert _confirm(client, consented_headers, course="먼 미래1", start="2027-01-25", target="2027-01-30").status_code == 201
        # One existing goal inside the new period is fine (R1).
        assert _confirm(client, consented_headers, course="B", start="2026-10-21", target="2027-03-31").status_code == 201
        # Now two goals cover 2027-01-25..30; a third swallowing them is refused.
        swallowed = _confirm(client, consented_headers, course="C", start="2026-10-21", target="2027-03-31")
        assert swallowed.status_code == 409
        later = _confirm(client, consented_headers, course="D", start="2027-04-01", target="2027-05-31")
        assert later.status_code == 201

    def test_non_monday_start_derives_that_weeks_monday(self, client: TestClient, consented_headers):
        res = _confirm(client, consented_headers, start="2026-10-28").json()  # Wednesday
        assert res["goal"]["start_date"] == "2026-10-28"
        assert {t["plan_week_start"] for t in res["tasks"]} == {"2026-10-26"}

    def test_past_start_date_is_rejected(self, client: TestClient, consented_headers):
        assert _confirm(client, consented_headers, start="2026-10-20").status_code == 400

    def test_start_date_is_isolated_per_user(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers)
        bob = _other_user(client)
        assert _confirm(client, bob).status_code == 201


class TestAllOverlapsReported:
    def test_new_goal_crossing_two_goals_reports_both(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="첫째", start="2026-10-21", target="2026-11-10")
        _confirm(client, consented_headers, course="둘째", start="2026-11-01", target="2026-12-10")
        res = _confirm(client, consented_headers, course="걸침", start="2026-11-05", target="2026-12-01")
        assert res.status_code == 409
        err = res.json()["detail"]
        assert err["code"] == "GOAL_PERIOD_OVERLAP"
        overlaps = err["details"]["overlaps"]
        assert [o["course"] for o in overlaps] == ["첫째", "둘째"]
        assert overlaps[0]["start_date"] == "2026-10-21" and overlaps[0]["target_date"] == "2026-11-10"
        assert err["details"]["conflict_from"] == "2026-11-05" and err["details"]["conflict_to"] == "2026-11-10"
        assert "첫째" in err["message"] and "둘째" in err["message"] and "두 학습" in err["message"]
        # Flat fields still mirror the first overlap for older clients.
        assert err["details"]["course"] == "첫째"
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 2  # nothing saved

    def test_only_goals_in_the_crowded_stretch_are_listed(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="겹침1", start="2026-10-21", target="2026-11-10")
        _confirm(client, consented_headers, course="겹침2", start="2026-10-25", target="2026-11-10")
        _confirm(client, consented_headers, course="무관", start="2026-12-01", target="2026-12-10")
        err = _confirm(client, consented_headers, course="새", start="2026-11-01", target="2026-11-20").json()["detail"]
        assert [o["course"] for o in err["details"]["overlaps"]] == ["겹침1", "겹침2"]


VALID_IDEAS = {"suggested_roles": ["백엔드 개발자", "데이터 분석가", "ML 엔지니어"]}


class TestRoleIdeas:
    def test_success_returns_roles_and_calls_ai_once(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_raw(VALID_IDEAS)]))
        res = client.post("/api/path/ideas", json={"field": "Python 개발"}, headers=consented_headers)
        assert res.status_code == 200
        assert res.json() == {"field": "Python 개발", "suggested_roles": VALID_IDEAS["suggested_roles"]}
        assert fake.calls == 1
        assert fake.payloads_seen[0] == {"field": "Python 개발"}  # only the field goes to the model

    def test_five_roles_are_allowed(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_raw({"suggested_roles": ["a1", "b2", "c3", "d4", "e5"]})]))
        assert client.post("/api/path/ideas", json={"field": "X 분야"}, headers=consented_headers).status_code == 200

    @pytest.mark.parametrize(
        "bad",
        [
            {"suggested_roles": ["하나", "둘"]},  # too few
            {"suggested_roles": ["1", "2", "3", "4", "5", "6"]},  # too many
            {"suggested_roles": ["가", "나", "   "]},  # blank
            {"suggested_roles": ["가", "나", "x" * 41]},  # too long
            {"suggested_roles": ["개발자", "개발자", "분석가"]},  # duplicate
            {"suggested_roles": ["Dev", "dev", "분석가"]},  # duplicate ignoring case
        ],
    )
    def test_rule_violation_is_retried_then_rejected_not_silently_fixed(
        self, client: TestClient, consented_headers, override_ai, bad
    ):
        fake = override_ai(FakeAIClient(raws=[_raw(bad)] * (MAX_RETRIES + 1)))
        res = client.post("/api/path/ideas", json={"field": "Python 개발"}, headers=consented_headers)
        assert res.status_code == 502
        assert res.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1

    def test_violation_then_valid_answer_succeeds_on_retry(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_raw({"suggested_roles": ["하나"]}), _raw(VALID_IDEAS)]))
        res = client.post("/api/path/ideas", json={"field": "Python 개발"}, headers=consented_headers)
        assert res.status_code == 200 and fake.calls == 2

    def test_timeout_maps_to_504(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raises=[AIRetryableError("t")] * (MAX_RETRIES + 1)))
        res = client.post("/api/path/ideas", json={"field": "Python 개발"}, headers=consented_headers)
        assert res.status_code == 504

    def test_blank_field_is_422(self, client: TestClient, consented_headers):
        assert client.post("/api/path/ideas", json={"field": "   "}, headers=consented_headers).status_code == 422

    def test_requires_auth_and_consent(self, client: TestClient, mock_auth_headers):
        assert client.post("/api/path/ideas", json={"field": "Python"}).status_code == 401
        assert client.post("/api/path/ideas", json={"field": "Python"}, headers=mock_auth_headers).status_code == 403

    def test_recommend_still_works_without_roles(self, client: TestClient, consented_headers, override_ai):
        from tests.test_phase4_plan import VALID_PATH_RESPONSE

        no_roles = {"courses": VALID_PATH_RESPONSE["courses"]}
        override_ai(FakeAIClient(raws=[_raw(no_roles)]))
        res = client.post("/api/path/recommend", json={"field": "Python 개발"}, headers=consented_headers)
        assert res.status_code == 200 and res.json()["suggested_roles"] == []
