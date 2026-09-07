"""Immutable contracts shared by the B4 and B5 GoogleSQL baselines."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Literal

from nl2sparql.models.b12.contracts import ExtractionStatus, SelectedExample, validate_question

MODEL_ID = "meta-llama/llama-3.3-70b-instruct"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_40_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LIVE_COMPLETION_MARKER = object()
_MISSING = object()


class LargeLLMError(ValueError):
    """Raised when B4/B5 configuration, responses, or artifacts are invalid."""


def canonical_money(value: Decimal) -> str:
    """Return a stable non-exponential representation of a finite Decimal.

    Args:
        value: Decimal value to serialize without binary floating-point conversion.

    Returns:
        The normalized decimal string, with zero represented as ``"0"``.

    Raises:
        LargeLLMError: If ``value`` is not a finite Decimal.
    """
    if not isinstance(value, Decimal) or not value.is_finite():
        raise LargeLLMError("money must be a finite Decimal")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or _CONTROL_RE.search(value) is not None:
        raise LargeLLMError(f"{label} must be non-empty and control-free")
    return value


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LargeLLMError(f"{label} must be a lowercase SHA-256 digest")


def _revision(value: object, label: str) -> None:
    if not isinstance(value, str) or _HEX_40_RE.fullmatch(value) is None:
        raise LargeLLMError(f"{label} must be a pinned lowercase 40-hex revision")


def _non_negative_money(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < Decimal("0"):
        raise LargeLLMError(f"{label} must be a finite non-negative Decimal")
    return value


def _positive_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= Decimal("0"):
        raise LargeLLMError(f"{label} must be a finite positive Decimal")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LargeLLMError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LargeLLMError(f"{label} must be a non-negative integer")
    return value


def _finite_latency(value: object, label: str = "latency_ms") -> float:
    if (
        not isinstance(value, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0.0
    ):
        raise LargeLLMError(f"{label} must be a finite non-negative float")
    return value


def _canonical_json(value: object) -> object:
    if isinstance(value, Decimal):
        return canonical_money(value)
    if isinstance(value, dict):
        return {str(key): _canonical_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical_json(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ProviderPolicy:
    """Pinned OpenRouter provider and maximum accepted token prices."""

    provider_slug: str
    prompt_price_per_million_usd: Decimal
    completion_price_per_million_usd: Decimal
    allow_fallbacks: bool = False
    require_parameters: bool = True
    data_collection: Literal["deny"] = "deny"

    def __post_init__(self) -> None:
        _required_text(self.provider_slug, "provider_slug")
        _non_negative_money(self.prompt_price_per_million_usd, "prompt price")
        _non_negative_money(self.completion_price_per_million_usd, "completion price")
        if self.allow_fallbacks is not False:
            raise LargeLLMError("allow_fallbacks must be false")
        if self.require_parameters is not True:
            raise LargeLLMError("require_parameters must be true")
        if self.data_collection != "deny":
            raise LargeLLMError("data_collection must be deny")


@dataclass(frozen=True)
class LargeLLMConfig:
    """Scientific generation, retry, concurrency, and budget configuration."""

    provider: ProviderPolicy
    model_id: str = MODEL_ID
    temperature: Decimal = Decimal("0")
    seed: int = 42
    max_tokens: int = 512
    choice_count: int = 1
    max_cost_usd: Decimal = Decimal("20.00")
    concurrency: int = 5
    timeout_seconds: Decimal = Decimal("60")
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ProviderPolicy):
            raise LargeLLMError("provider must be a ProviderPolicy")
        if self.model_id != MODEL_ID:
            raise LargeLLMError(f"model_id must be {MODEL_ID!r}")
        if not isinstance(self.temperature, Decimal) or self.temperature != Decimal("0"):
            raise LargeLLMError("temperature must be Decimal('0')")
        if self.seed != 42 or not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise LargeLLMError("seed must be 42")
        if (
            self.max_tokens != 512
            or not isinstance(self.max_tokens, int)
            or isinstance(self.max_tokens, bool)
        ):
            raise LargeLLMError("max_tokens must be 512")
        if (
            self.choice_count != 1
            or not isinstance(self.choice_count, int)
            or isinstance(self.choice_count, bool)
        ):
            raise LargeLLMError("choice_count must be 1")
        _positive_decimal(self.max_cost_usd, "max_cost_usd")
        if self.max_cost_usd > Decimal("20.00"):
            raise LargeLLMError("max_cost_usd must be at most USD 20")
        _positive_int(self.concurrency, "concurrency")
        _positive_decimal(self.timeout_seconds, "timeout_seconds")
        _positive_int(self.max_attempts, "max_attempts")

    @property
    def sha256(self) -> str:
        """Return a canonical fingerprint of every run-affecting setting."""
        payload = json.dumps(_canonical_json(asdict(self)), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RemoteCompletion:
    """One validated remote completion with provider and billing evidence."""

    raw_text: str
    generation_id: str
    model_id: str
    provider_slug: str
    input_tokens: int
    output_tokens: int
    charged_cost_usd: Decimal
    upstream_cost_usd: Decimal | None
    latency_ms: float
    attempt_count: int
    finish_reason: str
    system_fingerprint: str | None
    synthetic_backend: bool = field(init=False, default=True)

    def __post_init__(self) -> None:
        if not isinstance(self.raw_text, str) or _CONTROL_RE.search(self.raw_text) is not None:
            raise LargeLLMError("completion raw_text must be a control-free string")
        _required_text(self.generation_id, "generation_id")
        _required_text(self.model_id, "completion model_id")
        _required_text(self.provider_slug, "completion provider_slug")
        _non_negative_int(self.input_tokens, "input token count")
        _non_negative_int(self.output_tokens, "output token count")
        _non_negative_money(self.charged_cost_usd, "charged cost")
        if self.upstream_cost_usd is not None:
            _non_negative_money(self.upstream_cost_usd, "upstream cost")
        _finite_latency(self.latency_ms)
        _positive_int(self.attempt_count, "attempt_count")
        if self.finish_reason not in {"stop", "length"}:
            raise LargeLLMError("finish_reason must be stop or length")
        if self.system_fingerprint is not None:
            _required_text(self.system_fingerprint, "system_fingerprint")

    @classmethod
    def synthetic(
        cls,
        *,
        raw_text: str,
        model_id: str,
        provider_slug: str,
        input_tokens: int,
        output_tokens: int,
        charged_cost_usd: Decimal,
        latency_ms: float,
        generation_id: str = "synthetic",
        upstream_cost_usd: Decimal | None = None,
        attempt_count: int = 1,
        finish_reason: str = "stop",
        system_fingerprint: str | None = None,
    ) -> RemoteCompletion:
        """Create an explicitly synthetic completion for local tests.

        Args:
            raw_text: Completion text returned by the local transport.
            model_id: Model identifier reported by the transport.
            provider_slug: Provider label reported by the transport.
            input_tokens: Non-negative input-token count.
            output_tokens: Non-negative output-token count.
            charged_cost_usd: Decimal cost reported by the transport.
            latency_ms: End-to-end completion latency.
            generation_id: Stable local generation identifier.
            upstream_cost_usd: Optional upstream inference cost.
            attempt_count: Number of transport attempts.
            finish_reason: Completion finish reason.
            system_fingerprint: Optional backend fingerprint.

        Returns:
            A completion permanently marked as synthetic.
        """
        return cls(
            raw_text=raw_text,
            generation_id=generation_id,
            model_id=model_id,
            provider_slug=provider_slug,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            charged_cost_usd=charged_cost_usd,
            upstream_cost_usd=upstream_cost_usd,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
            finish_reason=finish_reason,
            system_fingerprint=system_fingerprint,
        )


def _openrouter_completion(response: Mapping[str, object], marker: object) -> RemoteCompletion:
    """Issue live completion provenance to the OpenRouter adapter only."""
    if marker is not _LIVE_COMPLETION_MARKER:
        raise LargeLLMError("live completion provenance is restricted to the OpenRouter adapter")

    required = (
        "raw_text",
        "generation_id",
        "model_id",
        "provider_slug",
        "input_tokens",
        "output_tokens",
        "charged_cost_usd",
        "upstream_cost_usd",
        "latency_ms",
        "attempt_count",
        "finish_reason",
        "system_fingerprint",
    )
    values = {name: response.get(name, _MISSING) for name in required}
    if any(value is _MISSING for value in values.values()):
        raise LargeLLMError("live completion response is missing required provenance")
    completion = RemoteCompletion(**values)  # type: ignore[arg-type]
    object.__setattr__(completion, "synthetic_backend", False)
    return completion


@dataclass(frozen=True)
class LargeLLMPrediction:
    """One B4/B5 result with SQL extraction and complete remote provenance."""

    baseline: Literal["b4", "b5"]
    question: str
    raw_output: str
    sql: str | None
    extraction_status: ExtractionStatus
    completion: RemoteCompletion
    catalog_sha256: str
    summary_sha256: str
    prompt_sha256: str
    config_sha256: str
    latency_ms: float
    training_sha256: str | None = None
    encoder_id: str | None = None
    encoder_revision: str | None = None
    training_accepted: bool = False
    selected_examples: tuple[SelectedExample, ...] = ()

    def __post_init__(self) -> None:
        if self.baseline not in {"b4", "b5"}:
            raise LargeLLMError("baseline must be b4 or b5")
        try:
            validate_question(self.question)
        except ValueError as error:
            raise LargeLLMError(str(error)) from error
        if not isinstance(self.completion, RemoteCompletion):
            raise LargeLLMError("completion must be a RemoteCompletion")
        if not isinstance(self.raw_output, str) or self.raw_output != self.completion.raw_text:
            raise LargeLLMError("raw output must equal the completion text")
        if self.extraction_status not in {"ok", "empty", "prose", "invalid_sql", "unsafe_sql"}:
            raise LargeLLMError("extraction status is invalid")
        if self.extraction_status == "ok":
            if (
                not isinstance(self.sql, str)
                or not self.sql.strip()
                or _CONTROL_RE.search(self.sql) is not None
            ):
                raise LargeLLMError("ok prediction SQL must be non-empty and control-free")
        elif self.sql is not None:
            raise LargeLLMError("failed prediction must not contain SQL")
        for label, value in (
            ("catalog fingerprint", self.catalog_sha256),
            ("summary fingerprint", self.summary_sha256),
            ("prompt fingerprint", self.prompt_sha256),
            ("config fingerprint", self.config_sha256),
        ):
            _digest(value, label)
        _finite_latency(self.latency_ms)
        if not isinstance(self.training_accepted, bool):
            raise LargeLLMError("training acceptance marker must be boolean")
        if not isinstance(self.selected_examples, tuple) or any(
            not isinstance(item, SelectedExample) for item in self.selected_examples
        ):
            raise LargeLLMError("selected examples must be an immutable tuple")

        provenance = (self.training_sha256, self.encoder_id, self.encoder_revision)
        if self.baseline == "b4":
            if (
                any(value is not None for value in provenance)
                or self.training_accepted
                or self.selected_examples
            ):
                raise LargeLLMError("B4 prediction must not contain B5 provenance")
            return

        if self.training_sha256 is None:
            raise LargeLLMError("B5 prediction requires a training fingerprint")
        _digest(self.training_sha256, "training fingerprint")
        _required_text(self.encoder_id, "encoder ID")
        _revision(self.encoder_revision, "encoder revision")
        if len(self.selected_examples) != 5:
            raise LargeLLMError("B5 prediction requires exactly five selected examples")
        identifiers = tuple(example.record_id for example in self.selected_examples)
        if len(identifiers) != len(set(identifiers)):
            raise LargeLLMError("B5 selected example IDs must be unique")
