"""Phase 3 (AUTH): consent gate, token-derived UID, ownership, goal/task CRUD, data deletion."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers

CONSENT = {"terms_version": "v1.0", "privacy_agreed": True, "ai_use_agreed": True}
GOAL = {
    "field": "Python 개발",
    "course": "기본문법",
    "current_level_num": 1,
    "current_level_name": "입문",
    "target_level_num": 3,
    "target_level_name": "실무 기초",
    "weekly_hours": 7,
    "target_date": "2026-12-31",
}


def _consent(client: TestClient, headers: dict[str, str]) -> None:
    assert client.post("/api/consent", json=CONSENT, headers=headers).status_code == 201


def _task(goal_id: str, **overrides) -> dict:
    return {
        "goal_id": goal_id,
        "plan_week_start": "2026-10-19",
        "title": "자료형 실습",
        "estimated_minutes": 60,
        **overrides,
    }


class TestAuthentication:
    def test_missing_token_is_401_with_error_contract(self, client: TestClient):
        response = client.get("/api/goals")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_malformed_token_is_401(self, client: TestClient):
        response = client.get("/api/goals", headers={"Authorization": "Bearer not-a-dev-token"})
        assert response.status_code == 401

    def test_validation_error_uses_error_contract(self, client: TestClient, consented_headers):
        response = client.post("/api/goals", json={"field": ""}, headers=consented_headers)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


class TestConsent:
    def test_personal_endpoints_blocked_before_consent(self, client: TestClient, mock_auth_headers):
        response = client.get("/api/goals", headers=mock_auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "CONSENT_REQUIRED"
        assert client.post("/api/goals", json=GOAL, headers=mock_auth_headers).status_code == 403

    def test_consent_records_minimal_fields_and_creates_profile(self, client: TestClient, mock_auth_headers):
        response = client.post("/api/consent", json=CONSENT, headers=mock_auth_headers)
        assert response.status_code == 201
        body = response.json()
        assert body["user_id"] == "test-uid-alice"
        assert body["terms_version"] == "v1.0"
        assert body["consented_at"].endswith("Z")

        profile = client.get("/api/user/profile", headers=mock_auth_headers).json()
        assert profile["uid"] == "test-uid-alice"
        assert profile["consent_version"] == "v1.0"

    def test_consent_requires_all_agreements(self, client: TestClient, mock_auth_headers):
        payload = {**CONSENT, "ai_use_agreed": False}
        assert client.post("/api/consent", json=payload, headers=mock_auth_headers).status_code == 400

    def test_outdated_terms_version_rejected(self, client: TestClient, mock_auth_headers):
        payload = {**CONSENT, "terms_version": "v0.9"}
        response = client.post("/api/consent", json=payload, headers=mock_auth_headers)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "TERMS_VERSION_MISMATCH"

    def test_consent_requires_token(self, client: TestClient):
        assert client.post("/api/consent", json=CONSENT).status_code == 401


class TestGoalsAndTasks:
    def test_goal_crud_and_active_goal(self, client: TestClient, consented_headers):
        created = client.post("/api/goals", json=GOAL, headers=consented_headers)
        assert created.status_code == 201
        goal = created.json()
        assert goal["user_id"] == "test-uid-alice"
        assert goal["status"] == "active"

        profile = client.get("/api/user/profile", headers=consented_headers).json()
        assert profile["active_goal_id"] == goal["id"]

        listed = client.get("/api/goals", headers=consented_headers).json()
        assert [g["id"] for g in listed] == [goal["id"]]

        patched = client.patch(f"/api/goals/{goal['id']}", json={"weekly_hours": 10}, headers=consented_headers)
        assert patched.status_code == 200
        assert patched.json()["weekly_hours"] == 10

        assert client.delete(f"/api/goals/{goal['id']}", headers=consented_headers).status_code == 200
        assert client.get(f"/api/goals/{goal['id']}", headers=consented_headers).status_code == 404
        assert client.get("/api/user/profile", headers=consented_headers).json()["active_goal_id"] is None

    def test_body_user_id_is_ignored(self, client: TestClient, consented_headers):
        goal = client.post("/api/goals", json={**GOAL, "user_id": "someone-else"}, headers=consented_headers).json()
        assert goal["user_id"] == "test-uid-alice"

    def test_goal_level_order_validated(self, client: TestClient, consented_headers):
        payload = {**GOAL, "current_level_num": 4, "target_level_num": 2}
        assert client.post("/api/goals", json=payload, headers=consented_headers).status_code == 400

    def test_task_crud_and_filters(self, client: TestClient, consented_headers):
        goal = client.post("/api/goals", json=GOAL, headers=consented_headers).json()
        first = client.post("/api/tasks", json=_task(goal["id"], order_index=1), headers=consented_headers).json()
        second = client.post(
            "/api/tasks",
            json=_task(goal["id"], title="조건문", order_index=0, suggested_weekday="wed"),
            headers=consented_headers,
        ).json()
        assert first["status"] == "pending"
        assert first["suggested_weekday"] == "none"

        listed = client.get(
            "/api/tasks", params={"goal_id": goal["id"], "plan_week_start": "2026-10-19"}, headers=consented_headers
        ).json()
        assert [t["id"] for t in listed] == [second["id"], first["id"]]

        toggled = client.patch(f"/api/tasks/{first['id']}", json={"status": "completed"}, headers=consented_headers)
        assert toggled.json()["status"] == "completed"

        assert client.delete(f"/api/tasks/{first['id']}", headers=consented_headers).status_code == 200
        assert len(client.get("/api/tasks", headers=consented_headers).json()) == 1

    def test_task_week_start_must_be_monday(self, client: TestClient, consented_headers):
        goal = client.post("/api/goals", json=GOAL, headers=consented_headers).json()
        response = client.post("/api/tasks", json=_task(goal["id"], plan_week_start="2026-10-21"), headers=consented_headers)
        assert response.status_code == 400

    def test_invalid_weekday_rejected(self, client: TestClient, consented_headers):
        goal = client.post("/api/goals", json=GOAL, headers=consented_headers).json()
        response = client.post("/api/tasks", json=_task(goal["id"], suggested_weekday="monday"), headers=consented_headers)
        assert response.status_code == 422

    def test_goal_delete_cascades_tasks(self, client: TestClient, consented_headers):
        goal = client.post("/api/goals", json=GOAL, headers=consented_headers).json()
        client.post("/api/tasks", json=_task(goal["id"]), headers=consented_headers)
        client.delete(f"/api/goals/{goal['id']}", headers=consented_headers)
        assert client.get("/api/tasks", headers=consented_headers).json() == []


class TestOwnershipIsolation:
    def test_other_uid_cannot_read_or_modify(self, client: TestClient, consented_headers):
        goal = client.post("/api/goals", json=GOAL, headers=consented_headers).json()
        task = client.post("/api/tasks", json=_task(goal["id"]), headers=consented_headers).json()

        bob = auth_headers("test-uid-bob")
        _consent(client, bob)

        assert client.get("/api/goals", headers=bob).json() == []
        assert client.get("/api/tasks", headers=bob).json() == []
        assert client.get(f"/api/goals/{goal['id']}", headers=bob).status_code == 403
        assert client.patch(f"/api/goals/{goal['id']}", json={"weekly_hours": 1}, headers=bob).status_code == 403
        assert client.delete(f"/api/goals/{goal['id']}", headers=bob).status_code == 403
        assert client.patch(f"/api/tasks/{task['id']}", json={"status": "completed"}, headers=bob).status_code == 403
        assert client.delete(f"/api/tasks/{task['id']}", headers=bob).status_code == 403
        # Bob cannot attach a task to Alice's goal or point his profile at it.
        assert client.post("/api/tasks", json=_task(goal["id"]), headers=bob).status_code == 403
        assert client.patch("/api/user/profile", json={"active_goal_id": goal["id"]}, headers=bob).status_code == 403

        # Alice's data is untouched.
        assert client.get(f"/api/tasks", headers=consented_headers).json()[0]["status"] == "pending"


class TestDataDeletion:
    def test_delete_data_removes_only_own_documents(self, client: TestClient, consented_headers):
        client.post("/api/goals", json=GOAL, headers=consented_headers)
        bob = auth_headers("test-uid-bob")
        _consent(client, bob)
        client.post("/api/goals", json=GOAL, headers=bob)

        response = client.post("/api/user/delete-data", headers=consented_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Alice must consent again before using personal features.
        assert client.get("/api/goals", headers=consented_headers).status_code == 403
        _consent(client, consented_headers)
        assert client.get("/api/goals", headers=consented_headers).json() == []

        assert len(client.get("/api/goals", headers=bob).json()) == 1
