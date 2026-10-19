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
from functools import lru_cache
from typing import Callable, Optional, Type, TypeVar

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


def ai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def ai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def ai_timeout_seconds() -> float:
    return float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))


def ai_max_output_tokens() -> int:
    return int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1500"))


class AIClient(ABC):
    @abstractmethod
    def _raw_complete(self, system_prompt: str, user_payload: dict) -> str:
        """Return the raw JSON text from one provider call.

        Raise AIRetryableError for a transient failure worth retrying (timeout),
        or AIUnavailableError for a non-retryable failure (not configured,
        can't connect, auth/rate-limit errors).
        """

    def generate(
        self,
        system_prompt: str,
        user_payload: dict,
        response_model: Type[T],
        validator: Optional[Callable[[T], None]] = None,
    ) -> T:
        last_error: Optional[Exception] = None
        last_kind = "timeout"
        for _ in range(MAX_RETRIES + 1):
            try:
                raw = self._raw_complete(system_prompt, user_payload)
            except AIRetryableError as exc:
                last_error, last_kind = exc, "timeout"
                continue
            try:
                parsed = response_model.model_validate_json(raw)
                if validator is not None:
                    validator(parsed)
                return parsed
            except (ValidationError, ValueError) as exc:
                last_error, last_kind = exc, "schema"
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
        try:
            completion = self._client.chat.completions.create(
                model=ai_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                # max_completion_tokens (not the deprecated max_tokens) is required by
                # newer models (e.g. reasoning models) and still accepted by older ones.
                max_completion_tokens=ai_max_output_tokens(),
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


@lru_cache(maxsize=1)
def get_ai_client() -> AIClient:
    return _LazyOpenAIClient()
