"""Phase 5C R1: at most two active goals on any single day (a third is rejected, 409).

The instruction's examples (A 10/1~10/31, B 10/10~10/20; C 10/12~10/15 rejected, 10/21~10/25
allowed, 10/1~10/9 allowed, 10/9~10/12 rejected) are shifted into November because a start
date must be today (pinned to 2026-10-21) or later: A 11/1~11/30, B 11/10~11/20.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
from tests.test_phase5b_multi import _confirm, _other_user

TODAY = date(2026, 10, 21)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


@pytest.fixture
def a_and_b(client: TestClient, consented_headers):
    assert _confirm(client, consented_headers, course="A", start="2026-11-01", target="2026-11-30").status_code == 201
    assert _confirm(client, consented_headers, course="B", start="2026-11-10", target="2026-11-20").status_code == 201


class TestInstructionExamples:
    def test_c_inside_both_is_rejected(self, client: TestClient, consented_headers, a_and_b):
        res = _confirm(client, consented_headers, course="C", start="2026-11-12", target="2026-11-15")
        assert res.status_code == 409
        d = res.json()["detail"]["details"]
        assert (d["conflict_from"], d["conflict_to"], d["max_concurrent"]) == ("2026-11-12", "2026-11-15", 2)
        assert {o["course"] for o in d["overlaps"]} == {"A", "B"}

    def test_c_after_b_ends_is_allowed(self, client: TestClient, consented_headers, a_and_b):
        assert _confirm(client, consented_headers, course="C", start="2026-11-21", target="2026-11-25").status_code == 201

    def test_c_before_b_starts_is_allowed(self, client: TestClient, consented_headers, a_and_b):
        assert _confirm(client, consented_headers, course="C", start="2026-11-01", target="2026-11-09").status_code == 201

    def test_c_touching_the_crowded_days_by_one_day_is_rejected(self, client: TestClient, consented_headers, a_and_b):
        res = _confirm(client, consented_headers, course="C", start="2026-11-09", target="2026-11-12")
        assert res.status_code == 409
        d = res.json()["detail"]["details"]
        assert (d["conflict_from"], d["conflict_to"]) == ("2026-11-10", "2026-11-12")


class TestBoundariesAndCounting:
    def test_only_one_overlapping_goal_is_allowed(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A", start="2026-11-01", target="2026-11-30")
        assert _confirm(client, consented_headers, course="B", start="2026-11-15", target="2026-12-15").status_code == 201

    def test_a_single_shared_day_with_two_goals_is_rejected_both_ends_inclusive(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A", start="2026-11-01", target="2026-11-10")
        _confirm(client, consented_headers, course="B", start="2026-11-10", target="2026-11-20")  # A and B share 11/10 only
        # one-day goals only hold 60 minutes (Phase 5F fix: available time by real days), so small tasks
        small = [{"title": f"작은 과제 {i}", "estimated_minutes": 10, "suggested_weekday": "none"} for i in range(3)]
        assert _confirm(client, consented_headers, course="C", start="2026-11-10", target="2026-11-10", tasks=small).status_code == 409
        assert _confirm(client, consented_headers, course="D", start="2026-11-09", target="2026-11-09", tasks=small).status_code == 201
        assert _confirm(client, consented_headers, course="E", start="2026-11-11", target="2026-11-11", tasks=small).status_code == 201

    def test_two_goals_that_never_share_a_day_do_not_block_a_spanning_goal(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A", start="2026-11-01", target="2026-11-10")
        _confirm(client, consented_headers, course="B", start="2026-11-11", target="2026-11-20")
        assert _confirm(client, consented_headers, course="C", start="2026-10-21", target="2026-12-31").status_code == 201

    @pytest.mark.parametrize("status_value", ["completed", "archived"])
    def test_completed_and_archived_goals_are_not_counted(
        self, client: TestClient, consented_headers, a_and_b, status_value
    ):
        goals = client.get("/api/goals", headers=consented_headers).json()
        a = next(g for g in goals if g["course"] == "A")
        client.patch(f"/api/goals/{a['id']}", json={"status": status_value}, headers=consented_headers)
        assert _confirm(client, consented_headers, course="C", start="2026-11-12", target="2026-11-15").status_code == 201

    def test_rejection_saves_nothing_and_keeps_current_learning(self, client: TestClient, consented_headers, a_and_b):
        before = client.get("/api/user/profile", headers=consented_headers).json()["active_goal_id"]
        assert _confirm(client, consented_headers, course="C", start="2026-11-12", target="2026-11-15").status_code == 409
        assert len(client.get("/api/goals", headers=consented_headers).json()) == 2
        assert len(client.get("/api/tasks", headers=consented_headers).json()) == 6  # two goals x 3 tasks
        assert client.get("/api/user/profile", headers=consented_headers).json()["active_goal_id"] == before

    def test_idempotent_retry_of_an_accepted_goal_is_200_even_when_now_crowded(self, client: TestClient, consented_headers):
        payload_kwargs = {"client_request_id": "k-1"}
        first = client.post(
            "/api/plan/confirm",
            json={**_payload("A", "2026-11-01", "2026-11-30"), **payload_kwargs},
            headers=consented_headers,
        )
        assert first.status_code == 201
        _confirm(client, consented_headers, course="B", start="2026-11-01", target="2026-11-30")
        retry = client.post(
            "/api/plan/confirm",
            json={**_payload("A", "2026-11-01", "2026-11-30"), **payload_kwargs},
            headers=consented_headers,
        )
        assert retry.status_code == 200

    def test_other_users_goals_are_not_counted(self, client: TestClient, consented_headers, a_and_b):
        bob = _other_user(client)
        assert _confirm(client, bob, course="C", start="2026-11-12", target="2026-11-15").status_code == 201

    def test_past_start_date_is_still_400(self, client: TestClient, consented_headers, a_and_b):
        assert _confirm(client, consented_headers, course="C", start="2026-10-20", target="2026-11-15").status_code == 400

    def test_goals_post_path_uses_the_same_rule(self, client: TestClient, consented_headers):
        body = {
            "field": "영어", "course": "G1", "current_level_order": 1, "current_level_name": "입문",
            "target_level_order": 3, "target_level_name": "중급", "weekly_hours": 5, "target_date": "2026-12-31",
        }
        assert client.post("/api/goals", json=body, headers=consented_headers).status_code == 201
        assert client.post("/api/goals", json={**body, "course": "G2"}, headers=consented_headers).status_code == 201
        res = client.post("/api/goals", json={**body, "course": "G3"}, headers=consented_headers)
        assert res.status_code == 409 and res.json()["detail"]["code"] == "GOAL_PERIOD_OVERLAP"


def _payload(course: str, start: str, target: str) -> dict:
    from tests.test_phase5b_multi import _confirm_payload

    return _confirm_payload(course=course, start=start, target=target)
