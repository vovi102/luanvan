"""OpenRouter adapter using the project's OpenAI-compatible SDK."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import openai
from openai import AsyncOpenAI

from nl2sparql.dataset.paraphrase.prompts import PromptRequest
from nl2sparql.dataset.paraphrase.runner import CompletionAPIError, CompletionResult

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterConfigurationError(ValueError):
    """Raised when OpenRouter cannot be configured safely."""


class OpenRouterClient:
    def __init__(
        self,
        *,
        sdk: Any,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self._sdk = sdk
        self._clock_ns = clock_ns

    @classmethod
    def from_env(cls) -> OpenRouterClient:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise OpenRouterConfigurationError(
                "OPENROUTER_API_KEY is required for live paraphrasing"
            )
        return cls(
            sdk=AsyncOpenAI(
                api_key=api_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=60.0,
                max_retries=0,
            )
        )

    async def complete(self, request: PromptRequest) -> CompletionResult:
        start_ns = self._clock_ns()
        try:
            response = await self._sdk.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=request.temperature,
                max_tokens=300,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": f"{request.stage}_response",
                        "strict": True,
                        "schema": request.response_schema,
                    },
                },
                extra_body={"provider": {"require_parameters": True}},
            )
        except (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        ) as exc:
            raise CompletionAPIError(str(exc), retryable=True) from exc
        except openai.APIError as exc:
            raise CompletionAPIError(str(exc), retryable=False) from exc
        end_ns = self._clock_ns()
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise CompletionAPIError("OpenRouter returned no text content", retryable=False)
        usage = response.usage
        usage_values = usage.model_dump() if hasattr(usage, "model_dump") else vars(usage)
        return CompletionResult(
            content=content,
            generation_id=str(response.id),
            model=str(response.model),
            prompt_tokens=int(usage_values.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_values.get("completion_tokens", 0) or 0),
            total_tokens=int(usage_values.get("total_tokens", 0) or 0),
            cost_usd=usage_values.get("cost"),
            latency_ms=(end_ns - start_ns) / 1_000_000,
        )
