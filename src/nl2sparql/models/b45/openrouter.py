"""Lazy, budget-aware OpenRouter transport for the B4/B5 baselines."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b12.prompts import prompt_sha256
from nl2sparql.models.b45.attempts import (
    AttemptEvidence,
    AttemptEvidencePersistenceError,
    AttemptEvidenceSink,
    AttemptStatus,
)
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
    """Secret-safe OpenRouter failure with stable machine-readable evidence.

    Attributes:
        code: Stable machine-readable failure code.
        attempt_count: Number of remote attempts completed before the failure.
        prompt_sha256: Optional non-secret SHA-256 of the exact prompt.
        authoritative_cost_usd: Billed cost reconciled before this failure, or zero
            when the failure happened before billing was known.
    """

    def __init__(
        self,
        code: str,
        *,
        attempt_count: int = 0,
        prompt_sha256: str | None = None,
        authoritative_cost_usd: Decimal = Decimal("0"),
    ) -> None:
        """Create a sanitized OpenRouter error.

        Args:
            code: Non-empty stable failure code.
            attempt_count: Non-negative count of completed SDK attempts.
            authoritative_cost_usd: Billed cost already reconciled, or zero when
                billing was not available.

        Raises:
            ValueError: If ``code`` is empty or ``attempt_count`` is negative.
        """
        if not isinstance(code, str) or not code:
            raise ValueError("OpenRouter error code must be non-empty")
        if (
            not isinstance(attempt_count, int)
            or isinstance(attempt_count, bool)
            or attempt_count < 0
        ):
            raise ValueError("OpenRouter attempt count must be a non-negative integer")
        if prompt_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", prompt_sha256):
            raise ValueError("OpenRouter prompt fingerprint must be a lowercase SHA-256 digest")
        if (
            not isinstance(authoritative_cost_usd, Decimal)
            or not authoritative_cost_usd.is_finite()
            or authoritative_cost_usd < Decimal("0")
        ):
            raise ValueError("OpenRouter authoritative cost must be a finite non-negative Decimal")
        self.code = code
        self.attempt_count = attempt_count
        self.prompt_sha256 = prompt_sha256
        self.authoritative_cost_usd = authoritative_cost_usd
        label = code.replace("_", " ")
        super().__init__(f"OpenRouter {label} after {attempt_count} attempt(s)")


@dataclass(frozen=True)
class RetryPolicy:
    """Deterministic retry classification and bounded delay calculation.

    Attributes:
        max_attempts: Maximum number of SDK attempts before exhaustion.
        retryable_statuses: HTTP statuses that are safe to retry.
    """

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
        """Return whether an SDK exception is safe to retry.

        Args:
            error: SDK or transport exception raised by one request attempt.

        Returns:
            ``True`` when the exception represents a transient condition.
        """
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
        """Return the finite non-negative delay before the next attempt.

        Args:
            error: SDK or transport exception raised by the failed attempt.
            attempt: One-based attempt number that just failed.
            jitter: Deterministic jitter callback for exponential backoff.

        Returns:
            Bounded delay in seconds, capped at thirty seconds.

        Raises:
            OpenRouterRequestError: If the attempt or injected delay values are
                negative, non-finite, or otherwise invalid.
        """
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
    """Validated, fingerprinted model/provider endpoint capabilities.

    Attributes:
        model_id: Exact model identifier accepted from metadata.
        provider_slug: Configured provider slug accepted from endpoint metadata.
        context_length: Endpoint-local context length in bytes/tokens as reported
            by OpenRouter metadata.
        supported_parameters: Sorted endpoint-local generation parameters.
        prompt_price_per_million_usd: Endpoint prompt price normalized to a
            per-million-token USD value.
        completion_price_per_million_usd: Endpoint completion price normalized
            to a per-million-token USD value.
        metadata_sha256: SHA-256 of the canonical raw metadata payload.
    """

    model_id: str
    provider_slug: str
    context_length: int
    supported_parameters: tuple[str, ...]
    prompt_price_per_million_usd: Decimal
    completion_price_per_million_usd: Decimal
    metadata_sha256: str

    @property
    def sha256(self) -> str:
        """Return the canonical fingerprint of the accepted raw metadata.

        Returns:
            The same SHA-256 digest carried by ``metadata_sha256``.
        """
        return self.metadata_sha256


def _zero_jitter(_attempt: int) -> float:
    return 0.0


async def _shield_operation(operation: Awaitable[Any]) -> Any:
    """Finish one accounting operation even when its caller is cancelled."""
    task = asyncio.ensure_future(operation)
    cancelled = False
    try:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
                continue
        result = task.result()
    except asyncio.CancelledError:
        cancelled = True
        result = None
    if cancelled:
        raise asyncio.CancelledError
    return result


def _annotate_cancellation(
    error: asyncio.CancelledError,
    *,
    prompt_sha256: str,
    attempt_count: int,
    authoritative_cost_usd: Decimal = Decimal("0"),
    reservation_id: str | None = None,
) -> None:
    """Attach non-secret accounting evidence to a propagated cancellation."""
    error.code = "request_cancelled"  # type: ignore[attr-defined]
    error.prompt_sha256 = prompt_sha256  # type: ignore[attr-defined]
    error.attempt_count = attempt_count  # type: ignore[attr-defined]
    error.authoritative_cost_usd = authoritative_cost_usd  # type: ignore[attr-defined]
    if reservation_id is not None:
        error.reservation_id = reservation_id  # type: ignore[attr-defined]


def _conservative_json_number(value: Decimal) -> float:
    """Convert a Decimal to JSON number form without rounding above its ceiling."""
    if not isinstance(value, Decimal) or not value.is_finite() or value < Decimal("0"):
        raise OpenRouterRequestError("request_invalid")
    converted = float(value)
    if not math.isfinite(converted):
        raise OpenRouterRequestError("request_invalid")
    # Decimal.from_float exposes the exact binary value represented by the
    # outgoing JSON number.  Move down one representable float when conversion
    # rounded upward, preserving a conservative provider ceiling.
    while Decimal.from_float(converted) > value:
        lower = math.nextafter(converted, -math.inf)
        if lower == converted:
            break
        converted = lower
    return converted


def _ensure_ledger_config_matches(config: LargeLLMConfig, ledger: BudgetLedger) -> None:
    if not isinstance(config, LargeLLMConfig) or not isinstance(ledger, BudgetLedger):
        raise OpenRouterRequestError("transport_configuration_invalid")
    if ledger.config_sha256 != config.sha256:
        raise OpenRouterRequestError("transport_configuration_mismatch")


class OpenRouterTransport:
    """Issue pinned OpenRouter requests behind a hard budget reservation.

    Attributes:
        No public mutable attributes. Use ``from_env`` for live construction and
        ``complete`` to issue validated requests.
    """

    def __init__(
        self,
        *,
        sdk: Any,
        ledger: BudgetLedger,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        jitter: Callable[[int], float] = _zero_jitter,
        attempt_sink: AttemptEvidenceSink | None = None,
    ) -> None:
        """Create a transport around injected SDK and timing dependencies.

        Args:
            sdk: SDK-like object exposing ``chat.completions.create``.
            ledger: Budget ledger already constructed for this transport's
                configuration.
            sleep: Async sleep function used between retry attempts.
            clock_ns: Monotonic nanosecond clock used for latency evidence.
            jitter: Deterministic jitter callback used by retry backoff.

        Raises:
            OpenRouterRequestError: If dependencies are not usable.
        """
        if not isinstance(ledger, BudgetLedger):
            raise OpenRouterRequestError("transport_configuration_invalid")
        if not callable(sleep) or not callable(clock_ns) or not callable(jitter):
            raise OpenRouterRequestError("transport_configuration_invalid")
        if attempt_sink is not None and not callable(getattr(attempt_sink, "append_attempt", None)):
            raise OpenRouterRequestError("transport_attempt_sink_invalid")
        self._sdk = sdk
        self._ledger = ledger
        self._config_sha256 = ledger.config_sha256
        self._sleep = sleep
        self._clock_ns = clock_ns
        self._jitter = jitter
        self._attempt_sink = attempt_sink

    async def _append_attempt(
        self,
        *,
        request_id: str,
        reservation: object,
        attempt: int,
        status: AttemptStatus,
        prompt_sha256: str,
        authoritative_cost_usd: Decimal | None = None,
    ) -> None:
        """Persist a secret-safe checkpoint before the transport advances."""
        if self._attempt_sink is None:
            return
        reservation_id = getattr(reservation, "request_id", None)
        ceiling = getattr(reservation, "maximum_cost_usd", None)
        if not isinstance(reservation_id, str) or not isinstance(ceiling, Decimal):
            raise OpenRouterRequestError("attempt_evidence_invalid", attempt_count=attempt)
        cancelled = False
        try:
            checkpoint = await _shield_operation(self._ledger.snapshot())
        except asyncio.CancelledError:
            # ``_shield_operation`` deliberately propagates cancellation after
            # the snapshot task finishes, so obtain its now-stable value before
            # persisting the transition that caused the cancellation.
            cancelled = True
            checkpoint = await _shield_operation(self._ledger.snapshot())
        evidence = AttemptEvidence(
            case_id=request_id,
            request_id=request_id,
            reservation_id=reservation_id,
            attempt_number=attempt,
            status=status,
            prompt_sha256=prompt_sha256,
            reservation_ceiling_usd=ceiling,
            budget_checkpoint=checkpoint,
            authoritative_cost_usd=authoritative_cost_usd,
        )
        try:
            await _shield_operation(self._attempt_sink.append_attempt(evidence))
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            raise AttemptEvidencePersistenceError() from None
        if cancelled:
            raise asyncio.CancelledError

    def _next_attempt_number(self, request_id: str) -> int:
        """Read a durable attempt ordinal without exposing sink failures."""
        if self._attempt_sink is None:
            return 1
        next_number = getattr(self._attempt_sink, "next_attempt_number", None)
        if not callable(next_number):
            return 1
        try:
            attempt = next_number(request_id)
        except Exception:
            raise AttemptEvidencePersistenceError() from None
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
            raise AttemptEvidencePersistenceError()
        return attempt

    @classmethod
    def from_env(
        cls,
        config: LargeLLMConfig,
        ledger: BudgetLedger,
        *,
        attempt_sink: AttemptEvidenceSink | None = None,
    ) -> OpenRouterTransport:
        """Construct the live SDK only after confirming local configuration.

        Args:
            config: Large-LLM configuration that must match the supplied ledger.
            ledger: Budget ledger bound to the same configuration.

        Returns:
            A live OpenRouter transport with SDK retries disabled.

        Raises:
            OpenRouterRequestError: If the config/ledger fingerprints diverge,
                the API key is missing, or SDK initialization fails.
        """
        _ensure_ledger_config_matches(config, ledger)
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise OpenRouterRequestError("missing_api_key")

        initialization_failed = False
        try:
            from openai import AsyncOpenAI
        except Exception:
            initialization_failed = True
        else:
            try:
                sdk = AsyncOpenAI(
                    api_key=api_key,
                    base_url=OPENROUTER_BASE_URL,
                    timeout=float(config.timeout_seconds),
                    max_retries=0,
                )
            except Exception:
                initialization_failed = True

        if initialization_failed:
            raise OpenRouterRequestError("client_initialization_failed")
        return cls(sdk=sdk, ledger=ledger, attempt_sink=attempt_sink)

    async def complete(
        self,
        messages: tuple[ChatMessage, ...],
        config: LargeLLMConfig,
        *,
        request_id: str,
    ) -> RemoteCompletion:
        """Return one validated, authoritative-cost live completion.

        Args:
            messages: Ordered chat messages to send without logging their text.
            config: Large-LLM configuration bound to this transport's ledger.
            request_id: Unique stable request identifier for budget accounting.

        Returns:
            A validated live ``RemoteCompletion`` with provider and billing
            evidence.

        Raises:
            OpenRouterRequestError: If config binding, budget reservation,
                request execution, usage, provider identity, or completion
                validation fails.
            asyncio.CancelledError: If cancellation interrupts the request or
                retry wait; the reservation remains held.
        """
        self._ensure_config_matches(config)
        request = _request_payload(messages, config)
        prompt_fingerprint = prompt_sha256(messages)
        retry_policy = RetryPolicy(max_attempts=config.max_attempts)
        start_ns = _clock_value(self._clock_ns, "clock_invalid")
        first_attempt = self._next_attempt_number(request_id)
        attempt = first_attempt - 1
        attempts_this_call = 0
        response: object

        async def hold_reservation(reservation: object, reason: str, status: AttemptStatus) -> None:
            cancelled = False
            try:
                await _shield_operation(
                    self._ledger.hold(reservation, reason)  # type: ignore[arg-type]
                )
            except asyncio.CancelledError:
                cancelled = True
            try:
                await self._append_attempt(
                    request_id=request_id,
                    reservation=reservation,
                    attempt=attempt,
                    status=status,
                    prompt_sha256=prompt_fingerprint,
                )
            except asyncio.CancelledError:
                cancelled = True
            if cancelled:
                cancellation = asyncio.CancelledError()
                _annotate_cancellation(
                    cancellation,
                    prompt_sha256=prompt_fingerprint,
                    attempt_count=attempt,
                    reservation_id=getattr(reservation, "request_id", None),
                )
                raise cancellation

        while True:
            attempt += 1
            reservation_id = f"{request_id}:attempt-{attempt}"
            duplicate_number = 0
            while True:
                try:
                    reservation = await self._ledger.reserve(reservation_id, messages)
                    break
                except asyncio.CancelledError as cancelled:
                    _annotate_cancellation(
                        cancelled,
                        prompt_sha256=prompt_fingerprint,
                        attempt_count=attempt - 1,
                        reservation_id=reservation_id,
                    )
                    raise
                except LargeLLMError as error:
                    # A resumed run may retain an earlier liability under the
                    # deterministic base ID.  Never reuse that ID: allocate a
                    # distinct reservation while keeping the prior one intact.
                    if not str(error).startswith("duplicate budget request ID"):
                        raise
                    duplicate_number += 1
                    reservation_id = f"{request_id}:attempt-{attempt}:resume-{duplicate_number}"
            if reservation is None:
                raise OpenRouterRequestError(
                    "budget_blocked",
                    attempt_count=attempt - 1,
                    prompt_sha256=prompt_fingerprint,
                )
            try:
                await self._append_attempt(
                    request_id=request_id,
                    reservation=reservation,
                    attempt=attempt,
                    status="reserved",
                    prompt_sha256=prompt_fingerprint,
                )
            except asyncio.CancelledError as cancelled:
                _annotate_cancellation(
                    cancelled,
                    prompt_sha256=prompt_fingerprint,
                    attempt_count=attempt,
                    reservation_id=reservation.request_id,
                )
                raise
            terminal_error: OpenRouterRequestError | None = None
            delay: float | None = None
            attempts_this_call += 1
            try:
                response = await self._sdk.chat.completions.create(**request)
            except asyncio.CancelledError as cancelled:
                await hold_reservation(reservation, "request_cancelled", "cancelled")
                _annotate_cancellation(
                    cancelled,
                    prompt_sha256=prompt_fingerprint,
                    attempt_count=attempt,
                    reservation_id=reservation.request_id,
                )
                raise
            except Exception as error:
                exhausted = attempts_this_call >= retry_policy.max_attempts
                if not retry_policy.is_retryable(error) or exhausted:
                    await hold_reservation(reservation, "request_cost_unknown", "terminal_failure")
                    terminal_error = OpenRouterRequestError(
                        _request_error_code(error, exhausted=exhausted),
                        attempt_count=attempt,
                        prompt_sha256=prompt_fingerprint,
                    )
                else:
                    try:
                        delay = retry_policy.delay_seconds(
                            error, attempt=attempt, jitter=self._jitter
                        )
                    except OpenRouterRequestError as delay_error:
                        await hold_reservation(
                            reservation, "retry_delay_invalid", "terminal_failure"
                        )
                        terminal_error = OpenRouterRequestError(
                            delay_error.code,
                            attempt_count=delay_error.attempt_count,
                            prompt_sha256=prompt_fingerprint,
                        )
                    else:
                        await hold_reservation(
                            reservation, "retryable_request_failure", "retryable_failure"
                        )
            if terminal_error is not None:
                raise terminal_error
            if delay is not None:
                try:
                    await self._sleep(delay)
                except asyncio.CancelledError as cancelled:
                    _annotate_cancellation(
                        cancelled,
                        prompt_sha256=prompt_fingerprint,
                        attempt_count=attempt,
                        reservation_id=reservation.request_id,
                    )
                    raise
                continue
            else:
                break

        end_ns = _clock_value(self._clock_ns, "clock_invalid")
        latency_ms = (end_ns - start_ns) / 1_000_000
        if not math.isfinite(latency_ms) or latency_ms < 0.0:
            await hold_reservation(reservation, "clock_invalid", "terminal_failure")
            raise OpenRouterRequestError(
                "clock_invalid", attempt_count=attempt, prompt_sha256=prompt_fingerprint
            )

        try:
            charged_cost = _authoritative_cost(response, attempt_count=attempt)
        except OpenRouterRequestError as error:
            await hold_reservation(reservation, "authoritative_cost_invalid", "terminal_failure")
            raise OpenRouterRequestError(
                error.code,
                attempt_count=error.attempt_count,
                prompt_sha256=prompt_fingerprint,
            ) from None

        billed_error: OpenRouterRequestError | None = None
        completion: RemoteCompletion | None = None
        try:
            completion_values = _validated_completion_values(
                response,
                config,
                charged_cost=charged_cost,
                latency_ms=latency_ms,
                attempt_count=attempt,
            )
            completion = _openrouter_completion(completion_values, _LIVE_COMPLETION_MARKER)
        except OpenRouterRequestError as error:
            billed_error = OpenRouterRequestError(
                error.code,
                attempt_count=error.attempt_count,
                prompt_sha256=prompt_fingerprint,
                authoritative_cost_usd=charged_cost,
            )
        except LargeLLMError:
            billed_error = OpenRouterRequestError(
                "invalid_response",
                attempt_count=attempt,
                prompt_sha256=prompt_fingerprint,
                authoritative_cost_usd=charged_cost,
            )
        except Exception:
            billed_error = OpenRouterRequestError(
                "invalid_response",
                attempt_count=attempt,
                prompt_sha256=prompt_fingerprint,
                authoritative_cost_usd=charged_cost,
            )
        accounting_cancelled = False
        try:
            await _shield_operation(self._ledger.reconcile(reservation, charged_cost))
        except asyncio.CancelledError:
            accounting_cancelled = True
        try:
            await self._append_attempt(
                request_id=request_id,
                reservation=reservation,
                attempt=attempt,
                status="terminal_failure" if billed_error is not None else "completed",
                prompt_sha256=prompt_fingerprint,
                authoritative_cost_usd=charged_cost,
            )
        except asyncio.CancelledError:
            accounting_cancelled = True
        if accounting_cancelled:
            snapshot = await _shield_operation(self._ledger.snapshot())
            reconciled = reservation.request_id not in snapshot.unresolved_request_ids
            cancelled = asyncio.CancelledError()
            _annotate_cancellation(
                cancelled,
                prompt_sha256=prompt_fingerprint,
                attempt_count=attempt,
                authoritative_cost_usd=charged_cost if reconciled else Decimal("0"),
                reservation_id=reservation.request_id,
            )
            raise cancelled
        if billed_error is not None:
            raise billed_error
        assert completion is not None
        return completion

    def _ensure_config_matches(self, config: LargeLLMConfig) -> None:
        if (
            not isinstance(config, LargeLLMConfig)
            or config.sha256 != self._config_sha256
            or self._ledger.config_sha256 != self._config_sha256
        ):
            raise OpenRouterRequestError("transport_configuration_mismatch")


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
                "prompt": _conservative_json_number(config.provider.prompt_price_per_million_usd),
                "completion": _conservative_json_number(
                    config.provider.completion_price_per_million_usd
                ),
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


def validate_model_metadata(
    raw: object, config: LargeLLMConfig, *, prompt_bytes: int
) -> ModelMetadataEvidence:
    """Validate an exact model/provider endpoint response and fingerprint it.

    Args:
        raw: Raw OpenRouter metadata payload.
        config: Required model, provider, parameter, and pricing policy.
        prompt_bytes: Explicit UTF-8 prompt byte count for the request whose
            metadata is being accepted.

    Returns:
        Immutable evidence for the exact accepted endpoint capabilities.

    Raises:
        OpenRouterRequestError: If the metadata lacks endpoint-local capability
            evidence, the prompt byte count is invalid, or any policy check
            fails closed.
    """
    if not isinstance(prompt_bytes, int) or isinstance(prompt_bytes, bool) or prompt_bytes < 0:
        raise OpenRouterRequestError("model_metadata_invalid")
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

    parameters = endpoint.get("supported_parameters")
    if not isinstance(parameters, list) or any(not isinstance(item, str) for item in parameters):
        raise OpenRouterRequestError("model_metadata_invalid")
    parameter_set = frozenset(parameters)
    if not _REQUIRED_PARAMETERS.issubset(parameter_set):
        raise OpenRouterRequestError("model_metadata_invalid")

    context_length = endpoint.get("context_length")
    if (
        not isinstance(context_length, int)
        or isinstance(context_length, bool)
        or context_length < config.max_tokens + prompt_bytes
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


def _metadata_price(pricing: dict[str, object], name: str) -> Decimal:
    per_million_name = f"{name}_per_million_usd"
    if per_million_name in pricing:
        return _metadata_decimal(pricing[per_million_name])
    if name not in pricing:
        raise OpenRouterRequestError("model_metadata_invalid")
    return _metadata_decimal(pricing[name]) * Decimal(1_000_000)


def _metadata_decimal(value: object) -> Decimal:
    """Parse injected metadata numbers without understating binary floats."""
    if isinstance(value, bool) or value is None:
        raise OpenRouterRequestError("model_metadata_invalid")
    if not isinstance(value, (Decimal, str, int, float)):
        raise OpenRouterRequestError("model_metadata_invalid")
    try:
        if isinstance(value, Decimal):
            converted = value
        elif isinstance(value, float):
            converted = Decimal.from_float(value)
        else:
            converted = Decimal(value)
    except (InvalidOperation, ValueError):
        raise OpenRouterRequestError("model_metadata_invalid") from None
    if not converted.is_finite() or converted < Decimal("0"):
        raise OpenRouterRequestError("model_metadata_invalid")
    return converted


__all__ = [
    "ModelMetadataEvidence",
    "OpenRouterRequestError",
    "OpenRouterTransport",
    "RetryPolicy",
    "validate_model_metadata",
]
