from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Verify that /health returns status 200 and expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok", "service": "pacemate-api"}


def test_openapi_json(client: TestClient):
    """Verify OpenAPI schema generation is complete and valid."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "PaceMate API"
    assert "paths" in schema

    # Verify key endpoints are registered in OpenAPI schema
    expected_paths = [
        "/health",
        "/api/path/recommend",
        "/api/plan/generate",
        "/api/goals",
        "/api/goals/{goal_id}",
        "/api/tasks",
        "/api/tasks/{task_id}",
        "/api/study-logs",
        "/api/study-logs/{log_id}",
        "/api/data/summary",
        "/api/dashboard/summary",
        "/api/conversations",
        "/api/conversations/{conversation_id}",
        "/api/conversations/{conversation_id}/messages",
        "/api/resources",
        "/api/user/profile",
        "/api/user/delete-data",
        "/api/consent",
    ]
    for path in expected_paths:
        assert path in schema["paths"], f"Expected endpoint {path} not found in OpenAPI paths"
