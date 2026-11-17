import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from google.genai import types


@dataclass
class LLMCall:
    prompt: str
    raw_response: str
    tokens_in: int
    tokens_out: int


class RateLimitError(Exception):
    pass


class LLMProvider(Protocol):
    def generate_structured[T: BaseModel](
        self, prompt: str, schema: type[T]
    ) -> tuple[T, LLMCall]: ...


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return isinstance(exc, RateLimitError) or "429" in text or "RESOURCE_EXHAUSTED" in text


class GeminiClient:
    def __init__(
        self, model: str | None = None, max_retries: int = 5, base_delay: float = 2.0
    ) -> None:
        from google import genai

        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self._max_retries = max_retries
        self._base_delay = base_delay

    def _generate(
        self, *, prompt: str, schema: type[BaseModel]
    ) -> "types.GenerateContentResponse":
        return self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )

    def generate_structured[T: BaseModel](
        self, prompt: str, schema: type[T]
    ) -> tuple[T, LLMCall]:
        delay = self._base_delay
        for attempt in range(self._max_retries):
            try:
                resp = self._generate(prompt=prompt, schema=schema)
            except Exception as exc:
                if not _is_rate_limit(exc) or attempt == self._max_retries - 1:
                    raise
                time.sleep(delay + random.uniform(0, delay / 2))
                delay *= 2
                continue
            usage = resp.usage_metadata
            text = resp.text or ""
            call = LLMCall(
                prompt=prompt,
                raw_response=text,
                tokens_in=(usage.prompt_token_count or 0) if usage else 0,
                tokens_out=(usage.candidates_token_count or 0) if usage else 0,
            )
            return schema.model_validate_json(text), call
        raise ValueError("max_retries must be at least 1")


PROVIDERS: dict[str, Callable[[], LLMProvider]] = {"gemini": GeminiClient}


def make_provider(name: str | None = None) -> LLMProvider:
    """Build the provider named by `name`, else $LLM_PROVIDER, else gemini."""
    name = name or os.environ.get("LLM_PROVIDER", "gemini")
    if name not in PROVIDERS:
        raise ValueError(f"unknown LLM provider {name!r}; known: {sorted(PROVIDERS)}")
    return PROVIDERS[name]()
