"""Ops fix: the running modes are visible - startup log lines and GET /health.

A real incident: a server kept running with AUTH_MODE=dev STORE_BACKEND=memory from a terminal and
nobody could tell. Only mode names may appear: never a secret, URL, project id or UID.
"""

import logging

import pytest
from fastapi.testclient import TestClient

import main

INFO_LINE = "startup auth_mode=%s store_backend=%s"
MEMORY_WARNING = "data is NOT persisted: store_backend=memory (data disappears when the server stops)"
DEV_WARNING = "auth_mode=dev: fake dev tokens are accepted (local development only)"


def _modes(monkeypatch, auth, store):
    monkeypatch.setenv("AUTH_MODE", auth)
    monkeypatch.setenv("STORE_BACKEND", store)


def _lines(caplog):
    return [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "pacemate.startup"]


class TestHealth:
    @pytest.mark.parametrize(
        "auth,store,expected",
        [
            ("dev", "memory", ("dev", "memory")),
            ("firebase", "firestore", ("firebase", "firestore")),
            ("dev", "firestore", ("dev", "firestore")),
            ("firebase", "memory", ("firebase", "memory")),
            (" DEV ", " Memory ", ("dev", "memory")),  # the same normalisation the code branches on
            ("anything-else", "somewhere", ("firebase", "firestore")),  # only "dev" / "memory" switch the mode on
        ],
    )
    def test_the_modes_follow_the_environment(self, client: TestClient, monkeypatch, auth, store, expected):
        _modes(monkeypatch, auth, store)
        body = client.get("/health").json()
        assert (body["auth_mode"], body["store_backend"]) == expected
        assert body["status"] == "ok" and body["service"] == "pacemate-api"
        assert set(body) == {"status", "service", "auth_mode", "store_backend", "password_login_enabled"}

    def test_no_authentication_is_needed(self, client: TestClient):
        assert client.get("/health").status_code == 200  # no Authorization header

    def test_a_deployed_environment_reports_firebase_and_firestore(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("RENDER", "true")
        _modes(monkeypatch, "firebase", "firestore")
        body = client.get("/health").json()
        assert (body["auth_mode"], body["store_backend"]) == ("firebase", "firestore")

    def test_the_response_never_carries_a_secret_url_or_id(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_JSON", '{"private_key": "SECRET-KEY-XYZ", "project_id": "my-project-id"}')
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-abc")
        _modes(monkeypatch, "firebase", "firestore")
        text = client.get("/health").text
        for forbidden in ("SECRET-KEY-XYZ", "my-project-id", "sk-secret-abc", "http", "uid"):
            assert forbidden not in text


class TestStartupLog:
    def test_memory_and_dev_log_the_mode_and_both_warnings(self, monkeypatch, caplog):
        _modes(monkeypatch, "dev", "memory")
        with caplog.at_level(logging.DEBUG):
            main.log_startup_modes()
        assert _lines(caplog) == [
            ("INFO", "startup auth_mode=dev store_backend=memory"),
            ("WARNING", MEMORY_WARNING),
            ("WARNING", DEV_WARNING),
        ]

    def test_firebase_and_firestore_log_one_info_line_and_no_warning(self, monkeypatch, caplog):
        _modes(monkeypatch, "firebase", "firestore")
        with caplog.at_level(logging.DEBUG):
            main.log_startup_modes()
        assert _lines(caplog) == [("INFO", "startup auth_mode=firebase store_backend=firestore")]

    def test_memory_with_firebase_auth_warns_about_data_only(self, monkeypatch, caplog):
        _modes(monkeypatch, "firebase", "memory")
        with caplog.at_level(logging.DEBUG):
            main.log_startup_modes()
        assert _lines(caplog) == [("INFO", "startup auth_mode=firebase store_backend=memory"), ("WARNING", MEMORY_WARNING)]

    def test_dev_auth_with_firestore_warns_about_the_fake_tokens_only(self, monkeypatch, caplog):
        _modes(monkeypatch, "dev", "firestore")
        with caplog.at_level(logging.DEBUG):
            main.log_startup_modes()
        assert _lines(caplog) == [("INFO", "startup auth_mode=dev store_backend=firestore"), ("WARNING", DEV_WARNING)]

    def test_the_line_is_written_when_the_app_starts(self, monkeypatch, caplog):
        _modes(monkeypatch, "dev", "memory")
        with caplog.at_level(logging.DEBUG):
            with TestClient(main.app):  # entering the context runs the startup (lifespan)
                pass
        assert ("INFO", "startup auth_mode=dev store_backend=memory") in _lines(caplog)

    def test_no_secret_url_project_id_or_uid_reaches_the_log(self, monkeypatch, caplog):
        monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_JSON", '{"private_key": "SECRET-KEY-XYZ", "project_id": "my-project-id"}')
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-abc")
        monkeypatch.setenv("CORS_ORIGINS", "https://secret.example.com")
        _modes(monkeypatch, "dev", "memory")
        with caplog.at_level(logging.DEBUG):
            main.log_startup_modes()
        text = "\n".join(message for _, message in _lines(caplog))
        for forbidden in ("SECRET-KEY-XYZ", "my-project-id", "sk-secret-abc", "secret.example.com", "http", "test-uid"):
            assert forbidden not in text

    def test_the_line_is_visible_when_no_logging_is_configured(self, monkeypatch):
        """Under uvicorn the root logger has no handler; the startup logger then brings its own."""
        import io

        logger = logging.getLogger("pacemate.startup")
        saved = (list(logger.handlers), logger.level, logger.propagate)
        root = logging.getLogger()
        saved_root = list(root.handlers)
        try:
            for handler in saved_root:
                root.removeHandler(handler)
            logger.handlers.clear()
            logger.propagate = True
            _modes(monkeypatch, "dev", "memory")
            buffer = io.StringIO()
            real_stream_handler = logging.StreamHandler
            monkeypatch.setattr(logging, "StreamHandler", lambda *a, **k: real_stream_handler(buffer))
            main.log_startup_modes()
            output = buffer.getvalue()
            assert "startup auth_mode=dev store_backend=memory" in output and "NOT persisted" in output
        finally:
            logger.handlers[:] = saved[0]
            logger.setLevel(saved[1])
            logger.propagate = saved[2]
            for handler in saved_root:
                root.addHandler(handler)
