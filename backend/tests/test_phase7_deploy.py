"""Phase 7: start-up checks of a deployed (Render) environment, and the switch for /docs.
Import-time behaviour (main.py runs the checks on import) is tested in a fresh interpreter."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from deploy_config import REQUIRED_SECRETS, assert_safe_deploy_config, cors_origin_problems

BACKEND = Path(__file__).resolve().parents[1]
GOOD = "https://pacemate.vercel.app,https://pacemate-git-main.vercel.app"
SECRET_VALUE = "super-secret-value-123"


def _deployed(monkeypatch, **overrides):
    for name in ("RENDER", "CORS_ORIGINS", "AUTH_MODE", "STORE_BACKEND", *REQUIRED_SECRETS):
        monkeypatch.delenv(name, raising=False)
    env = {"RENDER": "true", "CORS_ORIGINS": GOOD, "FIREBASE_SERVICE_ACCOUNT_JSON": SECRET_VALUE, "OPENAI_API_KEY": SECRET_VALUE, **overrides}
    for key, value in env.items():
        if value is not None:
            monkeypatch.setenv(key, value)


class TestCorsOnRender:
    def test_two_https_origins_are_fine(self, monkeypatch):
        _deployed(monkeypatch)
        assert_safe_deploy_config()

    def test_a_missing_variable_is_refused(self, monkeypatch):
        _deployed(monkeypatch, CORS_ORIGINS=None)
        with pytest.raises(RuntimeError, match="not set"):
            assert_safe_deploy_config()

    @pytest.mark.parametrize(
        "value, rule",
        [
            ("*", "wildcard"),
            ("https://*.vercel.app", "wildcard"),
            ("http://localhost:3000", "localhost"),
            ("https://localhost", "localhost"),
            ("https://127.0.0.1:3000", "127.0.0.1"),
            ("http://pacemate.vercel.app", "non-https"),
            ("https://pacemate.vercel.app/", "ending with '/'"),
            ("https://a.vercel.app,,https://b.vercel.app", "empty entry"),
            ("https://a.vercel.app, ", "empty entry"),
            ("   ", "not set"),
            ("pacemate.vercel.app", "does not start with https://"),
        ],
    )
    def test_each_rule_is_refused_and_named(self, monkeypatch, value, rule):
        _deployed(monkeypatch, CORS_ORIGINS=value)
        with pytest.raises(RuntimeError) as err:
            assert_safe_deploy_config()
        assert rule in str(err.value)

    def test_the_message_never_contains_the_value(self, monkeypatch):
        _deployed(monkeypatch, CORS_ORIGINS="http://secret-origin.example.com/")
        with pytest.raises(RuntimeError) as err:
            assert_safe_deploy_config()
        assert "secret-origin" not in str(err.value) and "example.com" not in str(err.value)

    def test_spaces_after_commas_are_fine(self, monkeypatch):
        _deployed(monkeypatch, CORS_ORIGINS="https://a.vercel.app, https://b.vercel.app")
        assert_safe_deploy_config()

    def test_all_broken_rules_are_listed_once(self):
        problems = cors_origin_problems("http://localhost/,*")
        assert len(problems) == len(set(problems)) >= 4


class TestSecretsOnRender:
    @pytest.mark.parametrize("name", REQUIRED_SECRETS)
    def test_a_missing_secret_is_named_without_values(self, monkeypatch, name):
        _deployed(monkeypatch, **{name: None})
        with pytest.raises(RuntimeError) as err:
            assert_safe_deploy_config()
        assert name in str(err.value) and SECRET_VALUE not in str(err.value)

    def test_an_empty_secret_counts_as_missing(self, monkeypatch):
        _deployed(monkeypatch, OPENAI_API_KEY="  ")
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            assert_safe_deploy_config()

    def test_both_missing_names_both(self, monkeypatch):
        _deployed(monkeypatch, OPENAI_API_KEY=None, FIREBASE_SERVICE_ACCOUNT_JSON=None)
        with pytest.raises(RuntimeError) as err:
            assert_safe_deploy_config()
        assert "OPENAI_API_KEY" in str(err.value) and "FIREBASE_SERVICE_ACCOUNT_JSON" in str(err.value)

    def test_the_cors_rule_comes_before_the_secrets(self, monkeypatch):
        _deployed(monkeypatch, CORS_ORIGINS="*", OPENAI_API_KEY=None)
        with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
            assert_safe_deploy_config()


class TestLocalUnchanged:
    def test_nothing_is_checked_without_render(self, monkeypatch):
        for name in ("RENDER", "CORS_ORIGINS", *REQUIRED_SECRETS):
            monkeypatch.delenv(name, raising=False)
        assert_safe_deploy_config()
        monkeypatch.setenv("CORS_ORIGINS", "*")
        assert_safe_deploy_config()

    def test_the_default_origin_list_is_still_localhost(self, monkeypatch):
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        import main

        assert main._allowed_origins() == ["http://localhost:3000"]


def _run(code: str, **env) -> subprocess.CompletedProcess:
    drop = ("RENDER", "CORS_ORIGINS", "AUTH_MODE", "STORE_BACKEND", "API_DOCS_ENABLED", *REQUIRED_SECRETS)
    clean = {k: v for k, v in os.environ.items() if k not in drop}
    clean.update({k: v for k, v in env.items() if v is not None})
    clean["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=clean, capture_output=True, text=True, timeout=120)


DOCS_PROBE = """
from fastapi.testclient import TestClient
import json, main
c = TestClient(main.app)
print(json.dumps({p: c.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json", "/health")}))
"""

RENDER_OK = dict(RENDER="true", AUTH_MODE="firebase", STORE_BACKEND="firestore", CORS_ORIGINS=GOOD, FIREBASE_SERVICE_ACCOUNT_JSON="{}", OPENAI_API_KEY="k")


class TestImportTime:
    def test_the_app_starts_on_render_with_firebase_modes_and_good_config(self):
        out = _run(DOCS_PROBE, **RENDER_OK)
        assert out.returncode == 0, out.stderr[-500:]

    def test_the_app_refuses_to_start_on_render_with_a_bad_cors_list(self):
        env = {**RENDER_OK, "CORS_ORIGINS": "*", "FIREBASE_SERVICE_ACCOUNT_JSON": "x-secret", "OPENAI_API_KEY": "y-secret"}
        out = _run("import main", **env)
        assert out.returncode != 0 and "CORS_ORIGINS" in out.stderr
        assert "x-secret" not in out.stderr and "y-secret" not in out.stderr

    def test_the_app_refuses_to_start_on_render_without_a_secret(self):
        env = {k: v for k, v in RENDER_OK.items() if k != "OPENAI_API_KEY"}
        out = _run("import main", **env)
        assert out.returncode != 0 and "OPENAI_API_KEY" in out.stderr

    def test_dev_and_memory_are_still_refused_on_render(self):
        assert "AUTH_MODE=dev" in _run("import main", **{**RENDER_OK, "AUTH_MODE": "dev"}).stderr
        assert "STORE_BACKEND=memory" in _run("import main", **{**RENDER_OK, "STORE_BACKEND": "memory"}).stderr

    def test_health_on_render_reports_only_firebase_and_firestore(self):
        out = _run("import main, asyncio, json; print(json.dumps(asyncio.run(main.health())))", **RENDER_OK)
        assert json.loads(out.stdout.strip().splitlines()[-1]) == {"status": "ok", "service": "pacemate-api", "auth_mode": "firebase", "store_backend": "firestore"}

    def test_a_local_run_without_render_ignores_the_new_checks(self):
        out = _run(DOCS_PROBE, AUTH_MODE="dev", STORE_BACKEND="memory", CORS_ORIGINS="*")
        assert out.returncode == 0, out.stderr[-500:]


class TestApiDocsSwitch:
    def _codes(self, value):
        out = _run(DOCS_PROBE, AUTH_MODE="dev", STORE_BACKEND="memory", API_DOCS_ENABLED=value)
        assert out.returncode == 0, out.stderr[-500:]
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_the_default_is_on(self):
        assert self._codes(None) == {"/docs": 200, "/redoc": 200, "/openapi.json": 200, "/health": 200}

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "anything"])
    def test_other_values_keep_it_on(self, value):
        assert self._codes(value)["/docs"] == 200

    @pytest.mark.parametrize("value", ["false", "FALSE", " false ", "0", "no", "off"])
    def test_false_turns_the_three_paths_off_and_keeps_the_api(self, value):
        assert self._codes(value) == {"/docs": 404, "/redoc": 404, "/openapi.json": 404, "/health": 200}
