from fastapi.testclient import TestClient


class TestEndpointContracts:
    """Endpoints not yet implemented (Phase 4~6) return 501; Phase 3 endpoints require auth."""

    def test_path_recommend_contract(self, client: TestClient):
        response = client.post("/api/path/recommend", json={"field": "Python 개발"})
        assert response.status_code == 501
        assert "Phase 1 schema skeleton" in response.json()["detail"]

    def test_plan_generate_contract(self, client: TestClient):
        payload = {
            "field": "Python 개발",
            "selected_courses": ["기본문법"],
            "current_level": 1,
            "target_level": 4,
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

    def test_study_logs_endpoints_contract(self, client: TestClient):
        assert client.get("/api/study-logs").status_code == 501
        assert client.delete("/api/study-logs/log_123").status_code == 501

    def test_summaries_endpoints_contract(self, client: TestClient):
        assert client.get("/api/data/summary").status_code == 501
        assert client.get("/api/dashboard/summary").status_code == 501

    def test_conversations_endpoints_contract(self, client: TestClient):
        assert client.get("/api/conversations").status_code == 501
        assert client.get("/api/conversations/conv_123").status_code == 501

    def test_resources_endpoint_contract(self, client: TestClient):
        assert client.get("/api/resources").status_code == 501

    def test_user_endpoints_require_auth(self, client: TestClient):
        assert client.get("/api/user/profile").status_code == 401
        assert client.post("/api/user/delete-data").status_code == 401
