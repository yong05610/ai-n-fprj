from fastapi.testclient import TestClient


class TestEndpointContracts:
    """Endpoints not yet implemented (Phase 4~6) return 501 once past auth/consent; unauthenticated
    calls to personal-data endpoints must fail with 401 before ever reaching the 501 stub."""

    def test_path_recommend_contract(self, client: TestClient):
        response = client.post("/api/path/recommend", json={"field": "Python 개발"})
        assert response.status_code == 501
        assert response.json()["detail"]["code"] == "NOT_IMPLEMENTED"

    def test_plan_generate_contract(self, client: TestClient):
        payload = {
            "goal_id": "goal_123",
            "field": "Python 개발",
            "course": "기본문법",
            "current_level_order": 1,
            "target_level_order": 4,
            "weekly_hours": 7,
            "target_date": "2026-11-30",
        }
        response = client.post("/api/plan/generate", json=payload)
        assert response.status_code == 501

    def test_goals_endpoints_require_auth(self, client: TestClient):
        assert client.get("/api/goals").status_code == 401
        assert client.get("/api/goals/goal_123").status_code == 401
        assert client.delete("/api/goals/goal_123").status_code == 401

    def test_tasks_endpoints_require_auth(self, client: TestClient):
        assert client.get("/api/tasks").status_code == 401
        assert client.delete("/api/tasks/task_123").status_code == 401

    def test_study_logs_endpoints_require_auth_then_501(self, client: TestClient, consented_headers):
        assert client.get("/api/study-logs").status_code == 401
        assert client.delete("/api/study-logs/log_123").status_code == 401

        response = client.get("/api/study-logs", headers=consented_headers)
        assert response.status_code == 501
        assert response.json()["detail"]["code"] == "NOT_IMPLEMENTED"

    def test_summaries_endpoints_require_auth_then_501(self, client: TestClient, consented_headers):
        assert client.get("/api/data/summary").status_code == 401
        assert client.get("/api/dashboard/summary").status_code == 401

        assert client.get("/api/data/summary", headers=consented_headers).status_code == 501
        assert client.get("/api/dashboard/summary", headers=consented_headers).status_code == 501

    def test_conversations_endpoints_require_auth_then_501(self, client: TestClient, consented_headers):
        assert client.get("/api/conversations").status_code == 401
        assert client.get("/api/conversations/conv_123").status_code == 401

        assert client.get("/api/conversations", headers=consented_headers).status_code == 501
        assert client.get("/api/conversations/conv_123", headers=consented_headers).status_code == 501

    def test_resources_endpoint_is_public_and_not_implemented(self, client: TestClient):
        # Decision (2-2): the resource catalog is public/read-only and carries no UID, so no auth is required.
        assert client.get("/api/resources").status_code == 501

    def test_user_endpoints_require_auth(self, client: TestClient):
        assert client.get("/api/user/profile").status_code == 401
        assert client.post("/api/user/delete-data").status_code == 401
