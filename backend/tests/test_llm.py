import pytest
from pydantic import BaseModel

from pipeline.llm import GeminiClient, LLMCall, RateLimitError


class Out(BaseModel):
    answer: str


class FakeResponse:
    def __init__(self, text):
        self.text = text

        class Usage:
            prompt_token_count = 7
            candidates_token_count = 3

        self.usage_metadata = Usage()


def make_client(side_effects):
    """GeminiClient with generate_content stubbed; no real API."""
    client = GeminiClient.__new__(GeminiClient)
    client._model = "test-model"
    client._max_retries = 3
    client._base_delay = 0.0  # no sleep in tests
    calls = {"n": 0}

    def fake_generate(**kwargs):
        effect = side_effects[calls["n"]]
        calls["n"] += 1
        if isinstance(effect, Exception):
            raise effect
        return effect

    client._generate = fake_generate
    return client, calls


def test_success_returns_parsed_and_call():
    client, _ = make_client([FakeResponse('{"answer": "42"}')])
    out, call = client.generate_structured("q?", Out)
    assert out == Out(answer="42")
    assert call == LLMCall(prompt="q?", raw_response='{"answer": "42"}', tokens_in=7, tokens_out=3)


def test_retries_on_429_then_succeeds():
    client, calls = make_client([
        RateLimitError("429 RESOURCE_EXHAUSTED"),
        FakeResponse('{"answer": "ok"}'),
    ])
    out, _ = client.generate_structured("q?", Out)
    assert out.answer == "ok"
    assert calls["n"] == 2


def test_gives_up_after_max_retries():
    client, _ = make_client([RateLimitError("429")] * 3)
    with pytest.raises(RateLimitError):
        client.generate_structured("q?", Out)


def test_non_rate_limit_error_not_retried():
    client, calls = make_client([ValueError("boom")])
    with pytest.raises(ValueError):
        client.generate_structured("q?", Out)
    assert calls["n"] == 1
