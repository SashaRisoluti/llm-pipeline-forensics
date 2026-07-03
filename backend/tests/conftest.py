import pytest

from pipeline.llm import LLMCall


class MockLLM:
    """Returns queued Pydantic objects in order; records prompts."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    def generate_structured(self, prompt, schema):
        self.prompts.append(prompt)
        obj = self.responses.pop(0)
        if isinstance(obj, Exception):
            raise obj
        return obj, LLMCall(
            prompt=prompt, raw_response=obj.model_dump_json(),
            tokens_in=10, tokens_out=5,
        )


@pytest.fixture
def mock_llm():
    return MockLLM


@pytest.fixture
def tmp_env(tmp_path):
    """data dirs for tracing tests"""
    traces = tmp_path / "traces"
    traces.mkdir()
    return {"db": tmp_path / "forensics.db", "traces": traces, "evals": tmp_path / "evals"}
