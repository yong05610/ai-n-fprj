"""Firebase ID token verification and UID resolution.

The UID used for every read/write is taken only from the verified token,
never from request bodies or query strings.

AUTH_MODE
- "firebase" (default): verify Firebase ID tokens with firebase-admin.
- "dev": local development/tests only. Accepts "dev-<uid>" bearer tokens so the
  app runs without Firebase credentials. Refused on Render (RENDER env is set).
"""

import json
import os
import re
from functools import lru_cache
from typing import Optional

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from errors import api_error

security = HTTPBearer(auto_error=False)

DEV_TOKEN_PREFIX = "dev-"
_DEV_UID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,128}$")


def auth_mode() -> str:
    return os.getenv("AUTH_MODE", "firebase").strip().lower()


def assert_safe_auth_config() -> None:
    """Fail fast if dev auth is enabled on a deployed environment."""
    if auth_mode() == "dev" and os.getenv("RENDER"):
        raise RuntimeError("AUTH_MODE=dev must not be used in a deployed (Render) environment.")


def firebase_configured() -> bool:
    return bool(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))


@lru_cache(maxsize=1)
def get_firebase_app():
    """Initialize firebase-admin once from environment credentials."""
    import firebase_admin
    from firebase_admin import credentials

    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if raw:
        cred = credentials.Certificate(json.loads(raw))
    elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        cred = credentials.ApplicationDefault()
    else:
        raise RuntimeError("Firebase credentials are not configured.")
    return firebase_admin.initialize_app(cred)


def _unauthorized(message: str = "로그인이 필요합니다. 다시 시작해 주세요."):
    return api_error(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", message)


def _verify_dev_token(token: str) -> str:
    if not token.startswith(DEV_TOKEN_PREFIX):
        raise _unauthorized("유효하지 않은 인증 토큰입니다.")
    uid = token[len(DEV_TOKEN_PREFIX):]
    if not _DEV_UID_PATTERN.match(uid):
        raise _unauthorized("유효하지 않은 인증 토큰입니다.")
    return uid


def _verify_firebase_token(token: str) -> str:
    if not firebase_configured():
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_NOT_CONFIGURED",
            "인증 서버 설정이 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.",
        )
    from firebase_admin import auth as fb_auth

    try:
        decoded = fb_auth.verify_id_token(token, app=get_firebase_app())
    except fb_auth.ExpiredIdTokenError:
        raise _unauthorized("인증이 만료되었습니다. 페이지를 새로고침해 주세요.")
    except (fb_auth.InvalidIdTokenError, fb_auth.UserDisabledError, ValueError):
        raise _unauthorized("유효하지 않은 인증 토큰입니다.")
    except fb_auth.CertificateFetchError:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_UNAVAILABLE",
            "인증 확인에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        )
    uid = decoded.get("uid")
    if not uid:
        raise _unauthorized("유효하지 않은 인증 토큰입니다.")
    return uid


def get_current_uid(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """FastAPI dependency: resolve the caller's UID from the Bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized()
    token = credentials.credentials
    if auth_mode() == "dev":
        return _verify_dev_token(token)
    return _verify_firebase_token(token)


def create_login_token(uid: str) -> str:
    """Custom token for a UID found by password login. Dev mode returns the dev bearer token itself.
    The frontend signs in with it; from then on the UID again comes only from the verified ID token."""
    if auth_mode() == "dev":
        return f"{DEV_TOKEN_PREFIX}{uid}"
    if not firebase_configured():
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_NOT_CONFIGURED",
            "인증 서버 설정이 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.",
        )
    from firebase_admin import auth as fb_auth

    token = fb_auth.create_custom_token(uid, app=get_firebase_app())
    return token.decode("ascii") if isinstance(token, bytes) else str(token)


def delete_auth_user(uid: str) -> None:
    """Remove the anonymous Firebase account after a data deletion request."""
    if auth_mode() == "dev" or not firebase_configured():
        return
    from firebase_admin import auth as fb_auth

    try:
        fb_auth.delete_user(uid, app=get_firebase_app())
    except fb_auth.UserNotFoundError:
        pass
