"""Direct Gemini Developer API adapter for free-tier T3.3 paraphrasing."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from nl2sparql.dataset.paraphrase.prompts import PromptRequest
from nl2sparql.dataset.paraphrase.runner import CompletionAPIError, CompletionResult

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiConfigurationError(ValueError):
    """Raised when the direct Gemini client cannot be configured safely."""


def _safe_quota_metadata(response: Any) -> tuple[str, bool]:
    try:
        payload = response.json()
    except (AttributeError, TypeError, ValueError):
        return "", False
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "", False
    reason = error.get("code")
    daily = reason == "quota_exceeded"
    quota_id = ""
    quota_value = ""
    retry_after = ""
    details = error.get("details", [])
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, dict):
                continue
            detail_type = str(detail.get("@type", ""))
            if detail_type.endswith("google.rpc.QuotaFailure"):
                violations = detail.get("violations", [])
                if isinstance(violations, list) and violations and isinstance(violations[0], dict):
                    violation = violations[0]
                    quota_id = str(violation.get("quotaId", ""))
                    quota_value = str(violation.get("quotaValue", ""))
            elif detail_type.endswith("google.rpc.RetryInfo"):
                retry_after = str(detail.get("retryDelay", ""))
    safe = re.compile(r"^[A-Za-z0-9._/-]{1,160}$")
    quota_id = quota_id if safe.fullmatch(quota_id) else ""
    quota_value = quota_value if safe.fullmatch(quota_value) else ""
    retry_after = retry_after if safe.fullmatch(retry_after) else ""
    daily = daily or "perday" in quota_id.replace("_", "").lower()
    parts = []
    if quota_id:
        parts.append(f"quota={quota_id}")
    if quota_value:
        parts.append(f"quota_value={quota_value}")
    if retry_after:
        parts.append(f"retry_after={retry_after}")
    return (f" ({', '.join(parts)})" if parts else ""), daily


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        http: Any,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self._api_key = api_key
        self._http = http
        self._clock_ns = clock_ns

    @classmethod
    def from_env(cls) -> GeminiClient:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY is required for live paraphrasing")
        if os.environ.get("GEMINI_FREE_TIER_CONFIRMED") != "1":
            raise GeminiConfigurationError(
                "GEMINI_FREE_TIER_CONFIRMED=1 is required to attest that the API key "
                "belongs to an unbilled Free Tier project"
            )
        return cls(api_key=api_key, http=httpx.AsyncClient(timeout=60.0))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(self, request: PromptRequest) -> CompletionResult:
        start_ns = self._clock_ns()
        try:
            response = await self._http.post(
                f"{GEMINI_BASE_URL}/models/{request.model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json={
                    "systemInstruction": {
                        "parts": [{"text": request.system_prompt}],
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": request.user_prompt}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": request.temperature,
                        "maxOutputTokens": request.max_output_tokens,
                        "thinkingConfig": {
                            "thinkingLevel": request.thinking_level,
                        },
                        "responseMimeType": "application/json",
                        "responseJsonSchema": request.response_schema,
                    },
                },
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise CompletionAPIError(str(exc), retryable=True) from exc
        end_ns = self._clock_ns()
        if response.status_code >= 400:
            quota_metadata, daily_quota = _safe_quota_metadata(response)
            raise CompletionAPIError(
                f"Gemini API returned HTTP {response.status_code}{quota_metadata}",
                retryable=(response.status_code == 429 and not daily_quota)
                or response.status_code >= 500,
            )
        try:
            payload = response.json()
            content = payload["candidates"][0]["content"]["parts"][0]["text"]
            finish_reason = payload["candidates"][0]["finishReason"]
            generation_id = payload["responseId"]
            usage = payload["usageMetadata"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CompletionAPIError(
                "Gemini returned an invalid response", retryable=False
            ) from exc
        if not isinstance(content, str) or not content or not generation_id:
            raise CompletionAPIError("Gemini returned no text content", retryable=False)
        if finish_reason != "STOP":
            raise CompletionAPIError(
                f"Gemini stopped with finish reason {finish_reason}", retryable=False
            )
        return CompletionResult(
            content=content,
            generation_id=str(generation_id),
            model=str(payload.get("modelVersion") or request.model),
            prompt_tokens=int(usage.get("promptTokenCount", 0) or 0),
            completion_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
            total_tokens=int(usage.get("totalTokenCount", 0) or 0),
            cost_usd=0.0,
            latency_ms=(end_ns - start_ns) / 1_000_000,
        )
