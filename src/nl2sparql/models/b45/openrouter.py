"""Lazy, budget-aware OpenRouter transport for the B4/B5 baselines."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45.budget import BudgetLedger
from nl2sparql.models.b45.contracts import (
    _LIVE_COMPLETION_MARKER,
    LargeLLMConfig,
    LargeLLMError,
    RemoteCompletion,
    _openrouter_completion,
    canonical_money,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_TRANSIENT_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})
_CONNECTION_ERROR_NAMES = frozenset({"APIConnectionError", "APITimeoutError"})
_REQUIRED_PARAMETERS = frozenset({"seed", "temperature", "max_tokens"})
_MAX_RETRY_DELAY_SECONDS = 30.0


class OpenRouterRequestError(LargeLLMError):
    """A secret-safe OpenRouter failure with a stable machine-readable code."""

    def __init__(self, code: str, *, attempt_count: int = 0) -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("OpenRouter error code must be non-empty")
        if (
            not isinstance(attempt_count, int)
            or isinstance(attempt_count, bool)
            or attempt_count < 0
        ):
            raise ValueError("OpenRouter attempt count must be a non-negative integer")
        self.code = code
        self.attempt_count = attempt_count
        label = code.replace("_", " ")
        super().__init__(f"OpenRouter {label} after {attempt_count} attempt(s)")


@dataclass(frozen=True)
class RetryPolicy:
    """Deterministic retry classification and bounded delay calculation."""

    max_attempts: int = 3
    retryable_statuses: frozenset[int] = _TRANSIENT_STATUSES

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts <= 0
        ):
            raise OpenRouterRequestError("retry_policy_invalid")
        if not isinstance(self.retryable_statuses, frozenset) or any(
            not isinstance(status, int) or isinstance(status, bool)
            for status in self.retryable_statuses
        ):
            raise OpenRouterRequestError("retry_policy_invalid")

    def is_retryable(self, error: BaseException) -> bool:
        """Return whether an SDK exception is safe to retry."""
        status_code = _status_code(error)
        if status_code is not None:
            return status_code in self.retryable_statuses
        return isinstance(error, (ConnectionError, TimeoutError)) or any(
            cls.__name__ in _CONNECTION_ERROR_NAMES for cls in type(error).__mro__
        )

    def delay_seconds(
        self,
        error: BaseException,
        *,
        attempt: int,
        jitter: Callable[[int], float],
    ) -> float:
        """Return the finite non-negative delay before the next attempt."""
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
            raise OpenRouterRequestError("retry_delay_invalid", attempt_count=0)
        retry_after = _retry_after_seconds(error)
        if retry_after is None or retry_after == 0.0:
            try:
                jitter_seconds = float(jitter(attempt))
            except (TypeError, ValueError, OverflowError) as error:
                raise OpenRouterRequestError(
                    "retry_delay_invalid", attempt_count=attempt
                ) from error
            if not math.isfinite(jitter_seconds) or jitter_seconds < 0.0:
                raise OpenRouterRequestError("retry_delay_invalid", attempt_count=attempt)
            delay = 2 ** (attempt - 1) + jitter_seconds
        else:
            delay = retry_after
        if not math.isfinite(delay) or delay < 0.0:
            raise OpenRouterRequestError("retry_delay_invalid", attempt_count=attempt)
        return min(_MAX_RETRY_DELAY_SECONDS, delay)


@dataclass(frozen=True)
class ModelMetadataEvidence:
    """Validated, fingerprinted model/provider endpoint capabilities."""

    model_id: str
    provider_slug: str
    context_length: int
    supported_parameters: tuple[str, ...]
    prompt_price_per_million_usd: Decimal
    completion_price_per_million_usd: Decimal
    metadata_sha256: str

    @property
    def sha256(self) -> str:
        """Return the canonical fingerprint of the accepted raw metadata."""
        return self.metadata_sha256


def _zero_jitter(_attempt: int) -> float:
    return 0.0


class OpenRouterTransport:
    """Issue pinned OpenRouter requests behind a hard budget reservation."""

    def __init__(
        self,
        *,
        sdk: Any,
        ledger: BudgetLedger,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        jitter: Callable[[int], float] = _zero_jitter,
    ) -> None:
        if not isinstance(ledger, BudgetLedger):
            raise OpenRouterRequestError("transport_configuration_invalid")
        if not callable(sleep) or not callable(clock_ns) or not callable(jitter):
            raise OpenRouterRequestError("transport_configuration_invalid")
        self._sdk = sdk
        self._ledger = ledger
        self._sleep = sleep
        self._clock_ns = clock_ns
        self._jitter = jitter

    @classmethod
    def from_env(cls, config: LargeLLMConfig, ledger: BudgetLedger) -> OpenRouterTransport:
        """Construct the live SDK only after confirming an API key is present."""
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise OpenRouterRequestError("missing_api_key")

        try:
            from openai import AsyncOpenAI

            sdk = AsyncOpenAI(
                api_key=api_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=float(config.timeout_seconds),
                max_retries=0,
            )
        except Exception:
            raise OpenRouterRequestError("client_initialization_failed") from None
        return cls(sdk=sdk, ledger=ledger)

    async def complete(
        self,
        messages: tuple[ChatMessage, ...],
        config: LargeLLMConfig,
        *,
        request_id: str,
    ) -> RemoteCompletion:
        """Return one validated, authoritative-cost live completion."""
        reservation = await self._ledger.reserve(request_id, messages)
        if reservation is None:
            raise OpenRouterRequestError("budget_blocked")

        request = _request_payload(messages, config)
        retry_policy = RetryPolicy(max_attempts=config.max_attempts)
        start_ns = _clock_value(self._clock_ns, "clock_invalid")
        attempt = 0
        response: object
        while True:
            attempt += 1
            try:
                response = await self._sdk.chat.completions.create(**request)
            except asyncio.CancelledError:
                await self._ledger.hold(reservation, "request_cancelled")
                raise
            except Exception as error:
                if not retry_policy.is_retryable(error) or attempt >= retry_policy.max_attempts:
                    await self._ledger.hold(reservation, "request_cost_unknown")
                    raise OpenRouterRequestError(
                        _request_error_code(error, exhausted=attempt >= retry_policy.max_attempts),
                        attempt_count=attempt,
                    ) from None
                try:
                    delay = retry_policy.delay_seconds(error, attempt=attempt, jitter=self._jitter)
                    await self._sleep(delay)
                except asyncio.CancelledError:
                    await self._ledger.hold(reservation, "request_cancelled")
                    raise
                except OpenRouterRequestError:
                    await self._ledger.hold(reservation, "retry_delay_invalid")
                    raise
            else:
                break

        end_ns = _clock_value(self._clock_ns, "clock_invalid")
        latency_ms = (end_ns - start_ns) / 1_000_000
        if not math.isfinite(latency_ms) or latency_ms < 0.0:
            await self._ledger.hold(reservation, "clock_invalid")
            raise OpenRouterRequestError("clock_invalid", attempt_count=attempt)

        try:
            charged_cost = _authoritative_cost(response, attempt_count=attempt)
        except OpenRouterRequestError:
            await self._ledger.hold(reservation, "authoritative_cost_invalid")
            raise

        await self._ledger.reconcile(reservation, charged_cost)
        completion_values = _validated_completion_values(
            response,
            config,
            charged_cost=charged_cost,
            latency_ms=latency_ms,
            attempt_count=attempt,
        )
        try:
            return _openrouter_completion(completion_values, _LIVE_COMPLETION_MARKER)
        except LargeLLMError:
            raise OpenRouterRequestError("invalid_response", attempt_count=attempt) from None


def _request_payload(
    messages: tuple[ChatMessage, ...], config: LargeLLMConfig
) -> dict[str, object]:
    if not isinstance(messages, tuple) or any(
        not isinstance(message, ChatMessage) for message in messages
    ):
        raise OpenRouterRequestError("request_invalid")
    return {
        "model": config.model_id,
        "messages": [{"role": message.role, "content": message.content} for message in messages],
        "temperature": float(config.temperature),
        "seed": config.seed,
        "max_tokens": config.max_tokens,
        "n": config.choice_count,
        "provider": {
            "only": [config.provider.provider_slug],
            "allow_fallbacks": config.provider.allow_fallbacks,
            "require_parameters": config.provider.require_parameters,
            "data_collection": config.provider.data_collection,
            "max_price": {
                "prompt": float(config.provider.prompt_price_per_million_usd),
                "completion": float(config.provider.completion_price_per_million_usd),
            },
        },
        "extra_headers": {
            "X-OpenRouter-Metadata": "enabled",
            "HTTP-Referer": "https://github.com/vovi102/luanvan",
            "X-Title": "NL2SQL-Thesis",
        },
    }


def _validated_completion_values(
    response: object,
    config: LargeLLMConfig,
    *,
    charged_cost: Decimal,
    latency_ms: float,
    attempt_count: int,
) -> dict[str, object]:
    choices = _field(response, "choices")
    if (
        not isinstance(choices, Sequence)
        or isinstance(choices, (str, bytes, bytearray))
        or len(choices) != 1
    ):
        raise OpenRouterRequestError("invalid_response", attempt_count=attempt_count)
    choice = choices[0]
    message = _field(choice, "message")
    content = _field(message, "content")
    if not isinstance(content, str) or not content.strip():
        raise OpenRouterRequestError("invalid_response", attempt_count=attempt_count)
    finish_reason = _field(choice, "finish_reason")
    if finish_reason not in {"stop", "length"}:
        raise OpenRouterRequestError("invalid_response", attempt_count=attempt_count)

    model_id = _field(response, "model")
    if model_id != config.model_id:
        raise OpenRouterRequestError("model_mismatch", attempt_count=attempt_count)
    provider_slug = _provider_identity(response, config, attempt_count)

    usage = _field(response, "usage")
    input_tokens = _token_count(_field(usage, "prompt_tokens"), attempt_count)
    output_tokens = _token_count(_field(usage, "completion_tokens"), attempt_count)
    upstream_raw = _field(_field(usage, "cost_details"), "upstream_inference_cost")
    upstream_cost = (
        None
        if upstream_raw is None
        else _decimal_money(upstream_raw, "invalid_usage", attempt_count)
    )

    generation_id = _field(response, "id")
    if not isinstance(generation_id, str) or not generation_id.strip():
        raise OpenRouterRequestError("invalid_response", attempt_count=attempt_count)
    system_fingerprint = _field(response, "system_fingerprint")
    if system_fingerprint is not None and (
        not isinstance(system_fingerprint, str) or not system_fingerprint.strip()
    ):
        raise OpenRouterRequestError("invalid_response", attempt_count=attempt_count)

    return {
        "raw_text": content,
        "generation_id": generation_id,
        "model_id": model_id,
        "provider_slug": provider_slug,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "charged_cost_usd": charged_cost,
        "upstream_cost_usd": upstream_cost,
        "latency_ms": latency_ms,
        "attempt_count": attempt_count,
        "finish_reason": finish_reason,
        "system_fingerprint": system_fingerprint,
    }


def _provider_identity(response: object, config: LargeLLMConfig, attempt_count: int) -> str:
    metadata = _field(response, "openrouter_metadata")
    official_values = (
        _field(metadata, "provider_slug"),
        _field(metadata, "provider_name"),
    )
    provider_value = next(
        (value for value in official_values if isinstance(value, str) and value.strip()),
        None,
    )
    if provider_value is None:
        normalized_values = (
            _field(response, "provider"),
            _field(response, "provider_name"),
        )
        provider_value = next(
            (value for value in normalized_values if isinstance(value, str) and value.strip()),
            None,
        )
    if provider_value is None:
        raise OpenRouterRequestError("invalid_response", attempt_count=attempt_count)
    if _normalized_provider(provider_value) != _normalized_provider(config.provider.provider_slug):
        raise OpenRouterRequestError("provider_mismatch", attempt_count=attempt_count)
    return config.provider.provider_slug


def _authoritative_cost(response: object, *, attempt_count: int) -> Decimal:
    usage = _field(response, "usage")
    return _decimal_money(_field(usage, "cost"), "cost_unresolved", attempt_count)


def _decimal_money(value: object, code: str, attempt_count: int) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise OpenRouterRequestError(code, attempt_count=attempt_count)
    if not isinstance(value, (Decimal, str, int, float)):
        raise OpenRouterRequestError(code, attempt_count=attempt_count)
    try:
        converted = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise OpenRouterRequestError(code, attempt_count=attempt_count) from None
    if not converted.is_finite() or converted < Decimal("0"):
        raise OpenRouterRequestError(code, attempt_count=attempt_count)
    return converted


def _token_count(value: object, attempt_count: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OpenRouterRequestError("invalid_usage", attempt_count=attempt_count)
    return value


def _field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _status_code(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _retry_after_seconds(error: BaseException) -> float | None:
    headers = getattr(getattr(error, "response", None), "headers", None)
    if not isinstance(headers, Mapping):
        return None
    raw = next(
        (
            value
            for key, value in headers.items()
            if isinstance(key, str) and key.casefold() == "retry-after"
        ),
        None,
    )
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        return None
    try:
        delay = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(delay) or delay < 0.0:
        return None
    return delay


def _request_error_code(error: BaseException, *, exhausted: bool) -> str:
    if exhausted and _status_code(error) == 429:
        return "rate_limit_exhausted"
    if exhausted:
        return "retry_exhausted"
    return "request_failed"


def _clock_value(clock_ns: Callable[[], int], code: str) -> int:
    value = clock_ns()
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OpenRouterRequestError(code)
    return value


def _normalized_provider(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def validate_model_metadata(raw: object, config: LargeLLMConfig) -> ModelMetadataEvidence:
    """Validate an exact model/provider endpoint response and fingerprint it."""
    canonical = _canonical_metadata(raw)
    root = _require_mapping(canonical)
    data = root.get("data", root)
    model = _select_model(data, config.model_id)
    if model.get("id") != config.model_id:
        raise OpenRouterRequestError("model_metadata_invalid")

    endpoints = model.get("endpoints")
    if not isinstance(endpoints, list):
        raise OpenRouterRequestError("model_metadata_invalid")
    endpoint = next(
        (
            candidate
            for candidate in endpoints
            if isinstance(candidate, dict)
            and _metadata_provider_matches(candidate, config.provider.provider_slug)
        ),
        None,
    )
    if endpoint is None:
        raise OpenRouterRequestError("model_metadata_invalid")

    parameters = endpoint.get("supported_parameters", model.get("supported_parameters"))
    if not isinstance(parameters, list) or any(not isinstance(item, str) for item in parameters):
        raise OpenRouterRequestError("model_metadata_invalid")
    parameter_set = frozenset(parameters)
    if not _REQUIRED_PARAMETERS.issubset(parameter_set):
        raise OpenRouterRequestError("model_metadata_invalid")

    context_length = endpoint.get("context_length", model.get("context_length"))
    if (
        not isinstance(context_length, int)
        or isinstance(context_length, bool)
        or context_length < config.max_tokens + _required_prompt_bytes(root, model)
    ):
        raise OpenRouterRequestError("model_metadata_invalid")

    pricing = endpoint.get("pricing")
    if not isinstance(pricing, dict):
        raise OpenRouterRequestError("model_metadata_invalid")
    prompt_price = _metadata_price(pricing, "prompt")
    completion_price = _metadata_price(pricing, "completion")
    if (
        prompt_price > config.provider.prompt_price_per_million_usd
        or completion_price > config.provider.completion_price_per_million_usd
    ):
        raise OpenRouterRequestError("model_metadata_invalid")

    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return ModelMetadataEvidence(
        model_id=config.model_id,
        provider_slug=config.provider.provider_slug,
        context_length=context_length,
        supported_parameters=tuple(sorted(parameter_set)),
        prompt_price_per_million_usd=prompt_price,
        completion_price_per_million_usd=completion_price,
        metadata_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def _canonical_metadata(value: object) -> object:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, Mapping):
        return {str(key): _canonical_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_metadata(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise OpenRouterRequestError("model_metadata_invalid")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return canonical_money(value)
    raise OpenRouterRequestError("model_metadata_invalid")


def _require_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise OpenRouterRequestError("model_metadata_invalid")
    return value


def _select_model(data: object, model_id: str) -> dict[str, object]:
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        selected = next(
            (
                candidate
                for candidate in data
                if isinstance(candidate, dict) and candidate.get("id") == model_id
            ),
            None,
        )
        if selected is not None:
            return selected
    raise OpenRouterRequestError("model_metadata_invalid")


def _metadata_provider_matches(endpoint: dict[str, object], expected: str) -> bool:
    for field in ("provider_slug", "provider_name", "name"):
        value = endpoint.get(field)
        if isinstance(value, str) and _normalized_provider(value) == _normalized_provider(expected):
            return True
    return False


def _required_prompt_bytes(root: dict[str, object], model: dict[str, object]) -> int:
    value = root.get("prompt_bytes", model.get("prompt_bytes", 0))
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OpenRouterRequestError("model_metadata_invalid")
    return value


def _metadata_price(pricing: dict[str, object], name: str) -> Decimal:
    per_million_name = f"{name}_per_million_usd"
    if per_million_name in pricing:
        return _decimal_money(pricing[per_million_name], "model_metadata_invalid", 0)
    if name not in pricing:
        raise OpenRouterRequestError("model_metadata_invalid")
    return _decimal_money(pricing[name], "model_metadata_invalid", 0) * Decimal(1_000_000)


__all__ = [
    "ModelMetadataEvidence",
    "OpenRouterRequestError",
    "OpenRouterTransport",
    "RetryPolicy",
    "validate_model_metadata",
]
