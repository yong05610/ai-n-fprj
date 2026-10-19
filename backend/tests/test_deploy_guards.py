"""Deployment safety guards (2-6) and Firebase token-verification branches (Phase 3 review §5)."""

import pytest

import auth
import store


class TestDeploySafetyGuards:
    def test_dev_auth_mode_rejected_on_render(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("RENDER", "true")
        with pytest.raises(RuntimeError):
            auth.assert_safe_auth_config()

    def test_dev_auth_mode_allowed_without_render(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.delenv("RENDER", raising=False)
        auth.assert_safe_auth_config()  # must not raise

    def test_memory_store_rejected_on_render(self, monkeypatch):
        monkeypatch.setenv("STORE_BACKEND", "memory")
        monkeypatch.setenv("RENDER", "true")
        with pytest.raises(RuntimeError):
            store.assert_safe_store_config()

    def test_memory_store_allowed_without_render(self, monkeypatch):
        monkeypatch.setenv("STORE_BACKEND", "memory")
        monkeypatch.delenv("RENDER", raising=False)
        store.assert_safe_store_config()  # must not raise


class TestFirebaseTokenVerificationBranches:
    """verify_id_token branches, mocked so these run without real Firebase credentials."""

    @pytest.fixture(autouse=True)
    def _firebase_mode(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "firebase")
        monkeypatch.setattr(auth, "firebase_configured", lambda: True)
        monkeypatch.setattr(auth, "get_firebase_app", lambda: object())

    def test_expired_token_is_401(self, monkeypatch):
        from firebase_admin import auth as fb_auth

        def _raise(token, app=None):
            raise fb_auth.ExpiredIdTokenError("expired", cause=None)

        monkeypatch.setattr(fb_auth, "verify_id_token", _raise)
        with pytest.raises(Exception) as exc_info:
            auth._verify_firebase_token("expired-token")
        assert exc_info.value.status_code == 401

    def test_invalid_token_is_401(self, monkeypatch):
        from firebase_admin import auth as fb_auth

        def _raise(token, app=None):
            raise fb_auth.InvalidIdTokenError("invalid")

        monkeypatch.setattr(fb_auth, "verify_id_token", _raise)
        with pytest.raises(Exception) as exc_info:
            auth._verify_firebase_token("forged-token")
        assert exc_info.value.status_code == 401

    def test_certificate_fetch_error_is_503(self, monkeypatch):
        from firebase_admin import auth as fb_auth

        def _raise(token, app=None):
            raise fb_auth.CertificateFetchError("network down", cause=None)

        monkeypatch.setattr(fb_auth, "verify_id_token", _raise)
        with pytest.raises(Exception) as exc_info:
            auth._verify_firebase_token("any-token")
        assert exc_info.value.status_code == 503

    def test_not_configured_is_503_before_calling_verify(self, monkeypatch):
        monkeypatch.setattr(auth, "firebase_configured", lambda: False)
        with pytest.raises(Exception) as exc_info:
            auth._verify_firebase_token("any-token")
        assert exc_info.value.status_code == 503
