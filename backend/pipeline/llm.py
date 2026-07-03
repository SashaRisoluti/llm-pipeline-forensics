import os
import random
import time
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass
class LLMCall:
    prompt: str
    raw_response: str
    tokens_in: int
    tokens_out: int


class RateLimitError(Exception):
    pass


class LLMClient(Protocol):
    def generate_structured(
        self, prompt: str, schema: type[BaseModel]
    ) -> tuple[BaseModel, LLMCall]: ...


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return isinstance(exc, RateLimitError) or "429" in text or "RESOURCE_EXHAUSTED" in text


class GeminiClient:
    def __init__(self, model: str | None = None, max_retries: int = 5, base_delay: float = 2.0):
        from google import genai

        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        self._max_retries = max_retries
        self._base_delay = base_delay

    def _generate(self, *, prompt: str, schema: type[BaseModel]):
        return self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )

    def generate_structured(self, prompt: str, schema: type[BaseModel]):
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
            call = LLMCall(
                prompt=prompt,
                raw_response=resp.text,
                tokens_in=usage.prompt_token_count or 0,
                tokens_out=usage.candidates_token_count or 0,
            )
            return schema.model_validate_json(resp.text), call
