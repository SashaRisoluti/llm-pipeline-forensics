from typing import Any

import pytest
from pydantic import BaseModel

from pipeline.llm import (
    PROVIDERS,
    GeminiClient,
    LLMCall,
    LLMProvider,
    RateLimitError,
    make_provider,
)
from tests.conftest import MockLLM


class Out(BaseModel):
    answer: str


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

        class Usage:
            prompt_token_count = 7
            candidates_token_count = 3

        self.usage_metadata: Any = Usage()


def make_client(side_effects: list[Any]) -> tuple[GeminiClient, dict[str, int]]:
    """GeminiClient with generate_content stubbed; no real API."""
    client = GeminiClient.__new__(GeminiClient)
    client._model = "test-model"
    client._max_retries = 3
    client._base_delay = 0.0  # no sleep in tests
    calls = {"n": 0}

    def fake_generate(**kwargs: Any) -> Any:
        effect = side_effects[calls["n"]]
        calls["n"] += 1
        if isinstance(effect, Exception):
            raise effect
        return effect

    client._generate = fake_generate  # type: ignore[method-assign]
    return client, calls


def test_success_returns_parsed_and_call() -> None:
    client, _ = make_client([FakeResponse('{"answer": "42"}')])
    out, call = client.generate_structured("q?", Out)
    assert out == Out(answer="42")
    assert call == LLMCall(prompt="q?", raw_response='{"answer": "42"}', tokens_in=7, tokens_out=3)


def test_missing_usage_metadata_counts_zero_tokens() -> None:
    resp = FakeResponse('{"answer": "x"}')
    resp.usage_metadata = None
    client, _ = make_client([resp])
    _, call = client.generate_structured("q?", Out)
    assert (call.tokens_in, call.tokens_out) == (0, 0)


def test_retries_on_429_then_succeeds() -> None:
    client, calls = make_client([
        RateLimitError("429 RESOURCE_EXHAUSTED"),
        FakeResponse('{"answer": "ok"}'),
    ])
    out, _ = client.generate_structured("q?", Out)
    assert out.answer == "ok"
    assert calls["n"] == 2


def test_gives_up_after_max_retries() -> None:
    client, _ = make_client([RateLimitError("429")] * 3)
    with pytest.raises(RateLimitError):
        client.generate_structured("q?", Out)


def test_non_rate_limit_error_not_retried() -> None:
    client, calls = make_client([ValueError("boom")])
    with pytest.raises(ValueError):
        client.generate_structured("q?", Out)
    assert calls["n"] == 1


def test_make_provider_defaults_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    sentinel = MockLLM([])
    monkeypatch.setitem(PROVIDERS, "gemini", lambda: sentinel)
    assert make_provider() is sentinel


def test_make_provider_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = MockLLM([])
    monkeypatch.setitem(PROVIDERS, "fake", lambda: sentinel)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert make_provider() is sentinel


def test_make_provider_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="nope.*gemini"):
        make_provider("nope")


def test_implementations_satisfy_protocol() -> None:
    # mypy is the real gate: both must type-check as LLMProvider
    providers: list[LLMProvider] = [MockLLM([]), GeminiClient.__new__(GeminiClient)]
    assert len(providers) == 2
