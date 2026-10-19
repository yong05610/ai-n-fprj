"""Unit tests for ai_client.py's retry/validation contract, isolated from FastAPI and
from the OpenAI SDK (OpenAIClient's provider-exception mapping is tested separately
with the real openai exception classes, mocked at the HTTP layer)."""

import pytest
from pydantic import BaseModel

from ai_client import (
    MAX_RETRIES,
    AIClient,
    AIRetryableError,
    AIRetryFeedback,
    AISchemaError,
    AITimeoutError,
    AIUnavailableError,
    OpenAIClient,
    ai_configured,
)


class _Echo(BaseModel):
    value: int


class _StubClient(AIClient):
    def __init__(self, raws=None, raises=None):
        self._raws = list(raws or [])
        self._raises = list(raises or [])
        self.calls = 0
        self.payloads_seen = []

    def _raw_complete(self, system_prompt: str, user_payload: dict) -> str:
        self.calls += 1
        self.payloads_seen.append(user_payload)
        if self._raises:
            raise self._raises.pop(0)
        return self._raws.pop(0)


class TestGenerateRetryContract:
    def test_succeeds_on_first_attempt(self):
        client = _StubClient(raws=['{"value": 1}'])
        result = client.generate("sys", {}, _Echo)
        assert result.value == 1
        assert client.calls == 1

    def test_retryable_error_is_retried_up_to_max_then_times_out(self):
        client = _StubClient(raises=[AIRetryableError("slow")] * (MAX_RETRIES + 1))
        with pytest.raises(AITimeoutError):
            client.generate("sys", {}, _Echo)
        assert client.calls == MAX_RETRIES + 1

    def test_recovers_after_a_retryable_error(self):
        client = _StubClient(raws=['{"value": 2}'], raises=[AIRetryableError("slow")])
        result = client.generate("sys", {}, _Echo)
        assert result.value == 2
        assert client.calls == 2

    def test_invalid_json_is_retried_then_raises_schema_error(self):
        client = _StubClient(raws=["not json"] * (MAX_RETRIES + 1))
        with pytest.raises(AISchemaError):
            client.generate("sys", {}, _Echo)
        assert client.calls == MAX_RETRIES + 1

    def test_custom_validator_failure_is_retried_then_raises_schema_error(self):
        client = _StubClient(raws=['{"value": 1}'] * (MAX_RETRIES + 1))

        def must_be_even(parsed: _Echo) -> None:
            if parsed.value % 2 != 0:
                raise ValueError("must be even")

        with pytest.raises(AISchemaError):
            client.generate("sys", {}, _Echo, validator=must_be_even)
        assert client.calls == MAX_RETRIES + 1

    def test_custom_validator_success_short_circuits_retries(self):
        client = _StubClient(raws=['{"value": 2}'])
        result = client.generate("sys", {}, _Echo, validator=lambda p: None)
        assert result.value == 2
        assert client.calls == 1

    def test_retry_feedback_is_merged_into_the_next_attempts_payload(self):
        client = _StubClient(raws=['{"value": 1}', '{"value": 2}'])

        def reject_once_then_pass(parsed: _Echo) -> None:
            if client.calls == 1:
                raise AIRetryFeedback("too small", feedback={"hint": "go bigger", "previous_value": parsed.value})

        result = client.generate("sys", {"base": True}, _Echo, validator=reject_once_then_pass)
        assert result.value == 2
        assert client.calls == 2
        assert client.payloads_seen[0] == {"base": True}
        assert client.payloads_seen[1] == {"base": True, "hint": "go bigger", "previous_value": 1}

    def test_unavailable_error_is_not_caught_or_retried(self):
        client = _StubClient(raises=[AIUnavailableError("down")])
        with pytest.raises(AIUnavailableError):
            client.generate("sys", {}, _Echo)
        assert client.calls == 1

    def test_last_failure_kind_decides_the_final_error_type(self):
        # attempt 1: timeout, attempt 2: bad json (schema), attempt 3: timeout again
        # -> the most recent failure was a timeout, so that's the error that surfaces.
        calls = {"n": 0}

        class _Sequenced(AIClient):
            def _raw_complete(self, system_prompt, user_payload):
                calls["n"] += 1
                if calls["n"] in (1, 3):
                    raise AIRetryableError("slow")
                return "not json"

        with pytest.raises(AITimeoutError):
            _Sequenced().generate("sys", {}, _Echo)
        assert calls["n"] == MAX_RETRIES + 1


class TestAIConfigured:
    def test_ai_configured_reflects_env(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert ai_configured() is False
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert ai_configured() is True


class TestOpenAIClientConstruction:
    def test_raises_unavailable_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(AIUnavailableError):
            OpenAIClient()


class TestOpenAIClientProviderErrorMapping:
    """_raw_complete() must translate openai SDK exceptions into our typed errors
    without ever letting raw provider exception text reach the caller untouched."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
        return OpenAIClient()

    def test_timeout_becomes_retryable(self, client, monkeypatch):
        import httpx2 as httpx
        from openai import APITimeoutError

        def _raise(*args, **kwargs):
            raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))

        monkeypatch.setattr(client._client.chat.completions, "create", _raise)
        with pytest.raises(AIRetryableError):
            client._raw_complete("sys", {})

    def test_connection_error_becomes_unavailable(self, client, monkeypatch):
        import httpx2 as httpx
        from openai import APIConnectionError

        def _raise(*args, **kwargs):
            raise APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))

        monkeypatch.setattr(client._client.chat.completions, "create", _raise)
        with pytest.raises(AIUnavailableError):
            client._raw_complete("sys", {})

    def test_unexpected_provider_error_becomes_unavailable_not_propagated_raw(self, client, monkeypatch):
        def _raise(*args, **kwargs):
            raise RuntimeError("some internal SDK detail nobody should see verbatim")

        monkeypatch.setattr(client._client.chat.completions, "create", _raise)
        with pytest.raises(AIUnavailableError):
            client._raw_complete("sys", {})
