"""Provider-agnostic AI client with typed errors, bounded retries, and schema validation.

Design notes:
- `AIClient.generate()` holds all retry/validation logic and is provider-agnostic;
  subclasses only implement `_raw_complete()` (one provider call -> raw JSON text).
  This keeps the retry contract unit-testable without touching the OpenAI SDK.
- Three externally-visible error types map to distinct HTTP error codes in main.py:
  AIUnavailableError (not configured / unreachable, not retried), AITimeoutError
  (every attempt timed out), AISchemaError (every attempt failed schema or
  semantic validation). `AIRetryableError` is an internal signal a subclass raises
  from `_raw_complete()` to mean "that attempt failed transiently, worth a retry".
- Never log prompt/response content - only the failure category.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Callable, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("pacemate.ai")

T = TypeVar("T", bound=BaseModel)

MAX_RETRIES = 2  # total attempts = 1 + MAX_RETRIES


class AIUnavailableError(Exception):
    """AI provider is not configured or unreachable. Not retried within the request."""


class AITimeoutError(Exception):
    """The provider call did not complete in time, even after retries."""


class AISchemaError(Exception):
    """The AI output failed schema or semantic validation, even after retries."""


class AIRetryableError(Exception):
    """Internal signal from a subclass: this attempt failed transiently, retry it."""


class AIRetryFeedback(ValueError):
    """Raise from a `validator` to fail the current attempt *and* tell the next
    retry's user payload something concrete about what went wrong (e.g. "you
    went 300 minutes over budget"). Treated exactly like a plain ValueError for
    the schema/semantic-failure path; `feedback` is merged into `user_payload`
    before the next attempt.
    """

    def __init__(self, message: str, feedback: dict, reason: str = "other") -> None:
        super().__init__(message)
        self.feedback = feedback
        # A short category (never user text) so callers can count why attempts were rejected.
        self.reason = reason


def ai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def ai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def ai_timeout_seconds() -> float:
    return float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))


def ai_max_output_tokens() -> int:
    return int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1500"))


# Per-call overrides (Phase 5F: a whole-course plan is a much longer answer than the other calls;
# CR-012: the plan calls also use their own model). A context variable keeps
# `_raw_complete(system_prompt, user_payload)` unchanged for every client and fake; only OpenAIClient
# reads it. `timeout_seconds` may be a function so the plan flow can hand every attempt the time that is
# left of its overall budget.
_call_limits: ContextVar[Optional[tuple]] = ContextVar("ai_call_limits", default=None)


@contextmanager
def call_limits(
    timeout_seconds: Union[float, Callable[[], float], None] = None,
    max_output_tokens: Optional[int] = None,
    model: Optional[str] = None,
):
    token = _call_limits.set((timeout_seconds, max_output_tokens, model))
    try:
        yield
    finally:
        _call_limits.reset(token)


def plan_timeout_seconds() -> float:
    return float(os.getenv("OPENAI_PLAN_TIMEOUT_SECONDS", "60"))


def plan_max_output_tokens() -> int:
    return int(os.getenv("OPENAI_PLAN_MAX_OUTPUT_TOKENS", "8000"))


def plan_model() -> str:
    """CR-012: the model of the three plan-generation calls only (tutor, insight, path... keep OPENAI_MODEL)."""
    return os.getenv("OPENAI_PLAN_MODEL") or "gpt-5.4-mini"


class AIClient(ABC):
    @abstractmethod
    def _raw_complete(self, system_prompt: str, user_payload: dict) -> str:
        """Return the raw JSON text from one provider call.

        Raise AIRetryableError for a transient failure worth retrying (timeout),
        or AIUnavailableError for a non-retryable failure (not configured,
        can't connect, auth/rate-limit errors).
        """

    def _raw_text(self, system_prompt: str, user_payload: dict) -> str:
        """CR-012: one free-text provider call (no JSON mode). Same error contract as `_raw_complete`.
        Not abstract: only the clients that serve the plan flow implement it."""
        raise AIUnavailableError("이 AI 클라이언트는 자유 글 호출을 지원하지 않습니다.")

    def generate_text(
        self,
        system_prompt: str,
        user_payload: dict,
        max_attempts: int = 2,
        should_continue: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Free text, not JSON. A timeout is retried (up to `max_attempts` in all); an empty answer (for a
        reasoning model usually a cut-off one) is a failure, never retried. Nothing is validated or logged."""
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            if attempt > 1 and should_continue is not None and not should_continue():
                break
            try:
                text = self._raw_text(system_prompt, user_payload)
            except AIRetryableError as exc:
                last_error = exc
                continue
            if not (text or "").strip():
                logger.warning("ai_call_failed kind=empty")
                raise AISchemaError("AI 응답이 비어 있습니다.")
            return text
        logger.warning("ai_call_failed kind=timeout")
        raise AITimeoutError("AI 응답이 시간 안에 완료되지 않았습니다.") from last_error

    def generate(
        self,
        system_prompt: str,
        user_payload: dict,
        response_model: Type[T],
        validator: Optional[Callable[[T], None]] = None,
        on_reject: Optional[Callable[[Exception, int], None]] = None,
        should_continue: Optional[Callable[[], bool]] = None,
    ) -> T:
        """`on_reject(error, attempt)` is called for every attempt that is thrown away (1-based);
        it receives the exception only so the caller can log a category, never any content.
        `should_continue()` (CR-012, optional) is asked before every retry; False stops with a timeout error."""
        last_error: Optional[Exception] = None
        last_kind = "timeout"
        payload = dict(user_payload)
        for attempt in range(1, MAX_RETRIES + 2):
            if attempt > 1 and should_continue is not None and not should_continue():
                logger.warning("ai_call_failed kind=timeout")
                raise AITimeoutError("AI 응답이 시간 안에 완료되지 않았습니다.") from last_error
            try:
                raw = self._raw_complete(system_prompt, payload)
            except AIRetryableError as exc:
                last_error, last_kind = exc, "timeout"
                if on_reject is not None:
                    on_reject(exc, attempt)
                continue
            try:
                parsed = response_model.model_validate_json(raw)
                if validator is not None:
                    validator(parsed)
                return parsed
            except AIRetryFeedback as exc:
                last_error, last_kind = exc, "schema"
                payload = {**payload, **exc.feedback}
                if on_reject is not None:
                    on_reject(exc, attempt)
                continue
            except (ValidationError, ValueError) as exc:
                last_error, last_kind = exc, "schema"
                if on_reject is not None:
                    on_reject(exc, attempt)
                continue

        if last_kind == "timeout":
            logger.warning("ai_call_failed kind=timeout")
            raise AITimeoutError("AI 응답이 시간 안에 완료되지 않았습니다.") from last_error
        logger.warning("ai_call_failed kind=schema")
        raise AISchemaError("AI 응답이 스키마 또는 검증 규칙을 만족하지 않습니다.") from last_error


class OpenAIClient(AIClient):
    def __init__(self) -> None:
        if not ai_configured():
            raise AIUnavailableError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
        from openai import APIConnectionError, APITimeoutError, OpenAI

        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=ai_timeout_seconds())
        self._timeout_error = APITimeoutError
        self._connection_error = APIConnectionError

    def _raw_complete(self, system_prompt: str, user_payload: dict) -> str:
        return self._call(system_prompt, user_payload, json_mode=True)

    def _raw_text(self, system_prompt: str, user_payload: dict) -> str:
        return self._call(system_prompt, user_payload, json_mode=False)

    def _call(self, system_prompt: str, user_payload: dict, json_mode: bool) -> str:
        timeout, max_tokens, model = _call_limits.get() or (None, None, None)
        if callable(timeout):
            timeout = timeout()
        client = self._client.with_options(timeout=timeout) if timeout else self._client
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            completion = client.chat.completions.create(
                model=model or ai_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                # max_completion_tokens (not the deprecated max_tokens) is required by
                # newer models (e.g. reasoning models) and still accepted by older ones.
                max_completion_tokens=max_tokens or ai_max_output_tokens(),
                **extra,
            )
        except self._timeout_error as exc:
            raise AIRetryableError("provider call timed out") from exc
        except self._connection_error as exc:
            logger.error("ai_call_failed kind=unavailable")
            raise AIUnavailableError("AI 서비스에 연결할 수 없습니다.") from exc
        except Exception as exc:  # auth errors, rate limits, etc. - fail fast, don't retry
            logger.error("ai_call_failed kind=unavailable")
            raise AIUnavailableError("AI 서비스 호출에 실패했습니다.") from exc
        return completion.choices[0].message.content or "{}"


class _LazyOpenAIClient(AIClient):
    """Defers OpenAIClient() construction (and its "is OPENAI_API_KEY set" check)
    until the first actual call.

    FastAPI resolves `Depends(get_ai_client)` before the endpoint body runs, so an
    eager AIUnavailableError here would fire even for requests that fail ordinary
    input validation before ever needing the AI - never retryable).
    """

    def __init__(self) -> None:
        self._inner: Optional[AIClient] = None

    def _raw_complete(self, system_prompt: str, user_payload: dict) -> str:
        if self._inner is None:
            self._inner = OpenAIClient()
        return self._inner._raw_complete(system_prompt, user_payload)

    def _raw_text(self, system_prompt: str, user_payload: dict) -> str:
        if self._inner is None:
            self._inner = OpenAIClient()
        return self._inner._raw_text(system_prompt, user_payload)


@lru_cache(maxsize=1)
def get_ai_client() -> AIClient:
    return _LazyOpenAIClient()
