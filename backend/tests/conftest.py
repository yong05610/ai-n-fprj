import os
import sys
from pathlib import Path

# Tests run without Firebase credentials: dev tokens + in-memory store.
os.environ["AUTH_MODE"] = "dev"
os.environ["STORE_BACKEND"] = "memory"

# Add backend directory to sys.path so tests can import main and schemas
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from fastapi.testclient import TestClient
from main import app
from store import get_store


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-scoped FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_store():
    get_store().reset()
    yield


def auth_headers(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{uid}"}


@pytest.fixture
def mock_auth_headers() -> dict[str, str]:
    """Bearer headers for a test user (dev auth mode)."""
    return auth_headers("test-uid-alice")


@pytest.fixture
def consented_headers(client: TestClient, mock_auth_headers: dict[str, str]) -> dict[str, str]:
    """Headers for a user who has already accepted the current terms."""
    response = client.post(
        "/api/consent",
        json={"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True},
        headers=mock_auth_headers,
    )
    assert response.status_code == 201
    return mock_auth_headers
