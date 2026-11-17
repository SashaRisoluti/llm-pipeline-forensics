from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from pipeline.llm import LLMCall


class MockLLM:
    """Returns queued Pydantic objects in order; records prompts."""

    def __init__(self, responses: list[BaseModel | Exception] | None = None) -> None:
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    def generate_structured[T: BaseModel](
        self, prompt: str, schema: type[T]
    ) -> tuple[T, LLMCall]:
        self.prompts.append(prompt)
        obj = self.responses.pop(0)
        if isinstance(obj, Exception):
            raise obj
        return cast(T, obj), LLMCall(
            prompt=prompt, raw_response=obj.model_dump_json(),
            tokens_in=10, tokens_out=5,
        )


@pytest.fixture
def mock_llm() -> type[MockLLM]:
    return MockLLM


@pytest.fixture
def tmp_env(tmp_path: Path) -> dict[str, Path]:
    """data dirs for tracing tests"""
    traces = tmp_path / "traces"
    traces.mkdir()
    return {"db": tmp_path / "forensics.db", "traces": traces, "evals": tmp_path / "evals"}
