"""Immutable contracts shared by the NL2SQL evaluation framework."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, TypeAlias, get_args


class EvaluationError(ValueError):
    """Raised when evaluation evidence violates a canonical contract."""


PredictionStatus: TypeAlias = Literal[
    "ok", "no_output", "invalid_sql", "unsafe_sql", "generation_error", "timeout"
]
MeasurementStatus: TypeAlias = Literal["observed", "estimated", "unmeasured"]
DataEgress: TypeAlias = Literal["none", "provider", "unknown"]
ExecutionStatus: TypeAlias = Literal[
    "ok",
    "error",
    "timeout",
    "guard_blocked",
    "not_run",
    "unresolved_cost",
    "skipped_no_output",
    "skipped_invalid_sql",
    "skipped_unsafe_sql",
    "skipped_generation_error",
    "skipped_inference_timeout",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")

TranslationStatus: TypeAlias = Literal[
    "ok",
    "missing_translation",
    "translation_error",
    "translation_timeout",
    "invalid_translation",
    "downstream_no_output",
    "downstream_invalid_sql",
    "downstream_unsafe_sql",
    "downstream_error",
    "downstream_timeout",
]


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{field} must be non-empty text")


def _require_sha256(value: str | None, field: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EvaluationError(f"{field} must be a lowercase 64-hex sha256")


def _require_non_negative_int(value: int | None, field: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationError(f"{field} must be a non-negative integer")


def _require_finite_non_negative(
    value: float | None, field: str, *, optional: bool = False
) -> None:
    if value is None and optional:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise EvaluationError(f"{field} must be a finite non-negative float")


def _require_finite(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvaluationError(f"{field} must be finite")


def _require_sorted_unique(values: tuple[str, ...], field: str) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise EvaluationError(f"{field} must be a tuple of non-empty strings")
    if values != tuple(sorted(set(values))):
        raise EvaluationError(f"{field} must be a sorted unique tuple")


def _require_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise EvaluationError(f"{field} must be timezone-aware UTC")


@dataclass(frozen=True)
class ArtifactRef:
    """Content-addressed reference to one native or canonical input."""

    role: str
    media_type: str
    sha256: str
    schema_version: int | None

    def __post_init__(self) -> None:
        _require_text(self.role, "role")
        _require_text(self.media_type, "media_type")
        _require_sha256(self.sha256, "sha256")
        if self.schema_version is not None and self.schema_version < 1:
            raise EvaluationError("schema_version must be positive when present")


@dataclass(frozen=True)
class CostEvidence:
    """Observed, policy-estimated, or explicitly unmeasured monetary cost."""

    measurement_status: MeasurementStatus
    amount: Decimal | None
    currency: str | None
    source: str | None

    def __post_init__(self) -> None:
        if self.measurement_status not in ("observed", "estimated", "unmeasured"):
            raise EvaluationError("unknown measurement_status")
        if self.measurement_status == "unmeasured":
            if self.amount is not None or self.currency is not None or self.source is not None:
                raise EvaluationError("unmeasured cost requires null amount, currency and source")
            return
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite() or self.amount < 0:
            raise EvaluationError("measured cost requires a finite non-negative Decimal amount")
        if self.currency is None or self.source is None:
            raise EvaluationError("measured cost requires currency and source")
        _require_text(self.currency, "currency")
        _require_text(self.source, "source")


@dataclass(frozen=True)
class PrivacyEvidence:
    """Structured privacy provenance supplied by a native run."""

    documentation_status: Literal["documented", "undocumented"]
    data_egress: DataEgress
    provider: str | None
    policy_sha256: str | None
    review_sha256: str | None

    def __post_init__(self) -> None:
        if self.documentation_status not in ("documented", "undocumented"):
            raise EvaluationError("unknown documentation_status")
        if self.data_egress not in ("none", "provider", "unknown"):
            raise EvaluationError("unknown data_egress")
        if self.data_egress == "provider" and not self.provider:
            raise EvaluationError("provider data egress requires provider identity")
        if self.data_egress == "none" and self.provider is not None:
            raise EvaluationError("provider must be null when data egress is none")
        _require_sha256(self.policy_sha256, "policy_sha256", optional=True)
        _require_sha256(self.review_sha256, "review_sha256", optional=True)


@dataclass(frozen=True)
class TranslationEvidence:
    """Hash-bound evidence for one translation-first baseline prediction."""

    request_id: str
    translator_id: str
    model_id: str
    model_revision: str
    config_sha256: str
    original_text_sha256: str
    translated_text: str | None
    translated_text_sha256: str | None
    translation_latency_ms: float
    downstream_latency_ms: float | None
    total_latency_ms: float
    status: TranslationStatus
    error_code: str | None
    cost: CostEvidence
    privacy: PrivacyEvidence

    def __post_init__(self) -> None:
        for field, value in (
            ("request_id", self.request_id),
            ("translator_id", self.translator_id),
            ("model_id", self.model_id),
        ):
            _require_text(value, field)
        if not isinstance(self.model_revision, str) or not _REVISION_RE.fullmatch(
            self.model_revision
        ):
            raise EvaluationError("model_revision must be a pinned lowercase 40-hex revision")
        _require_sha256(self.config_sha256, "config_sha256")
        _require_sha256(self.original_text_sha256, "original_text_sha256")
        _require_finite_non_negative(self.translation_latency_ms, "translation_latency_ms")
        _require_finite_non_negative(
            self.downstream_latency_ms, "downstream_latency_ms", optional=True
        )
        _require_finite_non_negative(self.total_latency_ms, "total_latency_ms")
        if self.status not in get_args(TranslationStatus):
            raise EvaluationError("unknown translation status")

        translation_failed = self.status in {
            "missing_translation",
            "translation_error",
            "translation_timeout",
            "invalid_translation",
        }
        if translation_failed:
            if self.translated_text is not None or self.translated_text_sha256 is not None:
                raise EvaluationError("failed translation cannot carry translated text")
            if self.downstream_latency_ms is not None:
                raise EvaluationError("failed translation cannot carry downstream latency")
            expected_total = float(self.translation_latency_ms)
        else:
            _require_text(self.translated_text, "translated_text")
            _require_sha256(self.translated_text_sha256, "translated_text_sha256")
            assert self.translated_text is not None
            actual_hash = hashlib.sha256(self.translated_text.encode("utf-8")).hexdigest()
            if actual_hash != self.translated_text_sha256:
                raise EvaluationError("translated text hash does not match translated text")
            if self.downstream_latency_ms is None:
                raise EvaluationError("downstream outcome requires downstream latency")
            expected_total = float(self.translation_latency_ms) + float(self.downstream_latency_ms)
        if not math.isclose(
            float(self.total_latency_ms), expected_total, rel_tol=0.0, abs_tol=1e-9
        ):
            raise EvaluationError("total latency must equal translation plus downstream latency")
        if self.status == "ok" and self.error_code is not None:
            raise EvaluationError("successful translation baseline evidence cannot carry an error")
        if self.status != "ok":
            _require_text(self.error_code, "error_code")


@dataclass(frozen=True)
class PrivacyReview:
    """Hash-bindable manual privacy review for one baseline and test snapshot."""

    baseline_id: str
    test_set_sha256: str
    data_egress: DataEgress
    provider: str | None
    policy_sha256: str | None
    reviewer_id: str
    reviewed_at: datetime
    synthetic: bool

    def __post_init__(self) -> None:
        _require_text(self.baseline_id, "baseline_id")
        _require_sha256(self.test_set_sha256, "test_set_sha256")
        if self.data_egress not in ("none", "provider", "unknown"):
            raise EvaluationError("unknown data_egress")
        if self.data_egress == "provider" and not self.provider:
            raise EvaluationError("provider data egress requires provider identity")
        if self.data_egress == "none" and self.provider is not None:
            raise EvaluationError("provider must be null when data egress is none")
        _require_sha256(self.policy_sha256, "policy_sha256", optional=True)
        _require_text(self.reviewer_id, "reviewer_id")
        _require_utc(self.reviewed_at, "reviewed_at")
        if not isinstance(self.synthetic, bool):
            raise EvaluationError("synthetic must be boolean")


@dataclass(frozen=True)
class InferenceEvidence:
    """Per-case latency, token and inference charge observations."""

    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    cost: CostEvidence

    def __post_init__(self) -> None:
        _require_finite_non_negative(self.latency_ms, "latency_ms", optional=True)
        _require_non_negative_int(self.input_tokens, "input_tokens", optional=True)
        _require_non_negative_int(self.output_tokens, "output_tokens", optional=True)


@dataclass(frozen=True)
class PredictionCase:
    """One authoritative benchmark case paired with one terminal prediction."""

    case_id: str
    question: str
    gold_sql: str
    difficulty: Literal["easy", "medium", "hard"]
    categories: tuple[str, ...]
    prediction_status: PredictionStatus
    predicted_sql: str | None
    raw_output_sha256: str | None
    error_code: str | None
    inference: InferenceEvidence
    privacy: PrivacyEvidence

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_text(self.question, "question")
        _require_text(self.gold_sql, "gold_sql")
        if self.difficulty not in ("easy", "medium", "hard"):
            raise EvaluationError("unknown difficulty")
        _require_sorted_unique(self.categories, "categories")
        if self.prediction_status not in (
            "ok",
            "no_output",
            "invalid_sql",
            "unsafe_sql",
            "generation_error",
            "timeout",
        ):
            raise EvaluationError("unknown prediction_status")
        if self.prediction_status == "ok":
            if self.predicted_sql is None:
                raise EvaluationError("ok prediction requires predicted SQL")
            _require_text(self.predicted_sql, "predicted_sql")
        elif self.predicted_sql is not None:
            raise EvaluationError("Only ok predictions may carry predicted SQL")
        _require_sha256(self.raw_output_sha256, "raw_output_sha256", optional=True)


@dataclass(frozen=True)
class RunProvenance:
    """Review state and stable fingerprints for a prediction run."""

    reviewed: bool
    live_verified: bool
    synthetic: bool
    fingerprints: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, bool) for value in (self.reviewed, self.live_verified, self.synthetic)
        ):
            raise EvaluationError("provenance markers must be boolean")
        keys = tuple(key for key, _ in self.fingerprints)
        if keys != tuple(sorted(set(keys))):
            raise EvaluationError("fingerprint keys must be sorted unique")
        for key, value in self.fingerprints:
            _require_text(key, "fingerprint key")
            _require_text(value, f"fingerprint {key}")


@dataclass(frozen=True)
class CanonicalPredictionRun:
    """Complete ordered prediction artifact independent of baseline-native formats."""

    baseline_id: str
    run_id: str
    seed: int
    generated_at: datetime | None
    test_set_sha256: str
    test_case_count: int
    provenance: RunProvenance
    source_artifacts: tuple[ArtifactRef, ...]
    adapter_id: str
    adapter_schema_version: int
    cases: tuple[PredictionCase, ...]

    def __post_init__(self) -> None:
        _require_text(self.baseline_id, "baseline_id")
        _require_text(self.run_id, "run_id")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise EvaluationError("seed must be an integer")
        if self.generated_at is not None:
            _require_utc(self.generated_at, "generated_at")
        _require_sha256(self.test_set_sha256, "test_set_sha256")
        _require_non_negative_int(self.test_case_count, "test_case_count")
        _require_text(self.adapter_id, "adapter_id")
        if self.adapter_schema_version < 1:
            raise EvaluationError("adapter_schema_version must be positive")
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise EvaluationError("duplicate case_id in prediction run")
        if self.test_case_count != len(self.cases):
            raise EvaluationError("test_case_count must equal the complete case tuple length")
        roles = tuple(ref.role for ref in self.source_artifacts)
        if len(roles) != len(set(roles)):
            raise EvaluationError("source artifact roles must be unique")


@dataclass(frozen=True)
class ResultField:
    """One field in BigQuery result schema order."""

    name: str
    type_name: str
    mode: Literal["NULLABLE", "REQUIRED", "REPEATED"] = "NULLABLE"
    fields: tuple[ResultField, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.type_name, "type_name")
        if self.mode not in ("NULLABLE", "REQUIRED", "REPEATED"):
            raise EvaluationError("unknown result field mode")
        nested_names = tuple(field.name for field in self.fields)
        if len(nested_names) != len(set(nested_names)):
            raise EvaluationError("nested result field names must be unique")


@dataclass(frozen=True)
class QueryResultEvidence:
    """Digest-only typed query result evidence."""

    fields: tuple[ResultField, ...]
    schema_sha256: str
    row_count: int
    arity: int
    order_sensitive: bool
    row_digests: tuple[str, ...]
    result_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.schema_sha256, "schema_sha256")
        _require_non_negative_int(self.row_count, "row_count")
        _require_non_negative_int(self.arity, "arity")
        if self.arity != len(self.fields):
            raise EvaluationError("result arity must equal schema length")
        if self.row_count != len(self.row_digests):
            raise EvaluationError("row_count must equal row digest count")
        if not isinstance(self.order_sensitive, bool):
            raise EvaluationError("order_sensitive must be boolean")
        for digest in self.row_digests:
            _require_sha256(digest, "row_sha256")
        if not self.order_sensitive and self.row_digests != tuple(sorted(self.row_digests)):
            raise EvaluationError("unordered result row digests must be sorted")
        _require_sha256(self.result_sha256, "result_sha256")


@dataclass(frozen=True)
class DryRunEvidence:
    """One BigQuery dry-run estimate."""

    estimated_bytes: int
    observed_at: datetime
    cache_disabled: bool

    def __post_init__(self) -> None:
        _require_non_negative_int(self.estimated_bytes, "estimated_bytes")
        _require_utc(self.observed_at, "observed_at")
        if self.cache_disabled is not True:
            raise EvaluationError("dry-run evidence requires cache_disabled=true")


@dataclass(frozen=True)
class QueryExecution:
    """Terminal execution outcome for one gold or prediction query."""

    status: ExecutionStatus
    job_id: str | None
    latency_ms: float | None
    billed_bytes: int | None
    cost: CostEvidence
    result: QueryResultEvidence | None
    error_code: str | None
    processed_bytes: int | None = None
    cache_hit: bool | None = None
    cancellation_status: Literal["not_requested", "succeeded", "failed", "unknown"] = (
        "not_requested"
    )
    submission_attempted: bool = False
    submission_job_id: str | None = None
    initial_preflight: DryRunEvidence | None = None
    immediate_preflight: DryRunEvidence | None = None
    request_sha256: str | None = None
    initial_preflight_error: str | None = None
    immediate_preflight_error: str | None = None
    submission_acknowledged: bool = False

    def __post_init__(self) -> None:
        if self.status not in (
            "ok",
            "error",
            "timeout",
            "guard_blocked",
            "not_run",
            "unresolved_cost",
            "skipped_no_output",
            "skipped_invalid_sql",
            "skipped_unsafe_sql",
            "skipped_generation_error",
            "skipped_inference_timeout",
        ):
            raise EvaluationError("unknown execution status")
        _require_finite_non_negative(self.latency_ms, "latency_ms", optional=True)
        _require_non_negative_int(self.billed_bytes, "billed_bytes", optional=True)
        _require_non_negative_int(self.processed_bytes, "processed_bytes", optional=True)
        if self.cache_hit is not None and not isinstance(self.cache_hit, bool):
            raise EvaluationError("cache_hit must be boolean or null")
        if self.cancellation_status not in (
            "not_requested",
            "succeeded",
            "failed",
            "unknown",
        ):
            raise EvaluationError("unknown cancellation_status")
        if not isinstance(self.submission_attempted, bool):
            raise EvaluationError("submission_attempted must be boolean")
        if self.job_id is not None and not self.submission_attempted:
            object.__setattr__(self, "submission_attempted", True)
        if self.job_id is not None and self.submission_job_id is None:
            object.__setattr__(self, "submission_job_id", self.job_id)
        if self.submission_attempted and self.submission_job_id is None:
            raise EvaluationError("attempted submission requires its deterministic job ID")
        if not self.submission_attempted and self.submission_job_id is not None:
            raise EvaluationError("unattempted execution cannot carry a submission job ID")
        if self.job_id is not None and not self.submission_acknowledged:
            object.__setattr__(self, "submission_acknowledged", True)
        if self.submission_acknowledged and not self.submission_attempted:
            raise EvaluationError("acknowledged submission requires an attempted submission")
        if self.job_id is not None and self.job_id != self.submission_job_id:
            raise EvaluationError("returned job ID differs from submitted job ID")
        _require_sha256(self.request_sha256, "request_sha256", optional=True)
        if self.initial_preflight_error is not None:
            _require_text(self.initial_preflight_error, "initial_preflight_error")
        if self.immediate_preflight_error is not None:
            _require_text(self.immediate_preflight_error, "immediate_preflight_error")
        if self.status == "ok":
            if self.job_id is None or self.result is None or self.billed_bytes is None:
                raise EvaluationError(
                    "successful execution requires job, result and billed-byte evidence"
                )
            if self.cost.measurement_status == "unmeasured" or self.error_code is not None:
                raise EvaluationError("successful execution requires measured cost and no error")
        if self.status == "unresolved_cost":
            if self.job_id is None or self.result is None:
                raise EvaluationError("unresolved cost requires a submitted completed job")
            if self.billed_bytes is not None or self.cost.measurement_status != "unmeasured":
                raise EvaluationError("unresolved cost requires unknown billing evidence")
        if self.status.startswith("skipped_") or self.status in ("guard_blocked", "not_run"):
            if (
                any(
                    value is not None
                    for value in (
                        self.job_id,
                        self.latency_ms,
                        self.billed_bytes,
                        self.result,
                        self.processed_bytes,
                        self.cache_hit,
                    )
                )
                or self.cost.measurement_status != "unmeasured"
                or self.submission_attempted
                or self.submission_job_id is not None
                or self.submission_acknowledged
            ):
                raise EvaluationError("non-submitted execution cannot carry job evidence")


@dataclass(frozen=True)
class ExecutionCaseEvidence:
    """Gold and prediction execution outcomes for one case."""

    case_id: str
    gold: QueryExecution
    prediction: QueryExecution

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")


@dataclass(frozen=True)
class PricingPolicy:
    """Pinned billing conversion policy."""

    policy_id: str
    currency: str
    amount_per_tib: Decimal
    source_sha256: str
    minimum_billed_bytes: int = 10 * 2**20
    billing_increment_bytes: int = 2**20

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "policy_id")
        _require_text(self.currency, "currency")
        if not self.amount_per_tib.is_finite() or self.amount_per_tib < 0:
            raise EvaluationError("amount_per_tib must be finite and non-negative")
        _require_sha256(self.source_sha256, "source_sha256")
        _require_non_negative_int(self.minimum_billed_bytes, "minimum_billed_bytes")
        _require_non_negative_int(self.billing_increment_bytes, "billing_increment_bytes")
        if self.billing_increment_bytes == 0:
            raise EvaluationError("billing_increment_bytes must be positive")

    def conservative_billed_bytes(self, processed_bytes: int) -> int:
        """Apply the pinned nonzero floor and increment, always rounding upward."""
        _require_non_negative_int(processed_bytes, "processed_bytes")
        if processed_bytes == 0:
            return 0
        floored = max(processed_bytes, self.minimum_billed_bytes)
        increment = self.billing_increment_bytes
        return ((floored + increment - 1) // increment) * increment

    def estimate_cost(self, processed_bytes: int) -> Decimal:
        billed = self.conservative_billed_bytes(processed_bytes)
        return Decimal(billed) / Decimal(2**40) * self.amount_per_tib


@dataclass(frozen=True)
class ExecutionPolicy:
    """Explicit live-execution safety and budget boundary."""

    project: str
    location: str
    timeout_seconds: float
    per_query_byte_cap: int
    aggregate_byte_cap: int
    estimated_cost_cap: Decimal
    pricing: PricingPolicy
    aggregate_billed_byte_cap: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.project, "project")
        _require_text(self.location, "location")
        _require_finite_non_negative(self.timeout_seconds, "timeout_seconds")
        if self.timeout_seconds == 0:
            raise EvaluationError("timeout_seconds must be positive")
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        _require_non_negative_int(self.per_query_byte_cap, "per_query_byte_cap")
        _require_non_negative_int(self.aggregate_byte_cap, "aggregate_byte_cap")
        _require_non_negative_int(
            self.aggregate_billed_byte_cap,
            "aggregate_billed_byte_cap",
            optional=True,
        )
        if self.aggregate_billed_byte_cap == 0:
            raise EvaluationError("aggregate_billed_byte_cap must be positive when present")
        if not self.estimated_cost_cap.is_finite() or self.estimated_cost_cap < 0:
            raise EvaluationError("estimated_cost_cap must be finite and non-negative")

    @property
    def billed_byte_cap(self) -> int:
        """Return the explicit billed cap or the legacy aggregate cap fallback."""
        return self.aggregate_billed_byte_cap or self.aggregate_byte_cap


@dataclass(frozen=True)
class ExecutorProvenance:
    """Stable identity of the injected execution adapter."""

    kind: Literal["fake", "bigquery"]
    identity: str
    version: str
    synthetic: bool

    def __post_init__(self) -> None:
        if self.kind not in ("fake", "bigquery"):
            raise EvaluationError("unknown executor kind")
        _require_text(self.identity, "identity")
        _require_text(self.version, "version")


@dataclass(frozen=True)
class ExecutionEvidence:
    """Sealed execution evidence derived from one canonical prediction run."""

    execution_id: str
    prediction_run_sha256: str
    policy_sha256: str
    executor: ExecutorProvenance
    journal_terminal_sha256: str
    cases: tuple[ExecutionCaseEvidence, ...]
    policy: ExecutionPolicy | None = None
    test_set_sha256: str | None = None
    estimated_bytes_total: int | None = None
    billed_bytes_total: int | None = None
    execution_cost: CostEvidence | None = None

    def __post_init__(self) -> None:
        _require_text(self.execution_id, "execution_id")
        _require_sha256(self.prediction_run_sha256, "prediction_run_sha256")
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_sha256(self.journal_terminal_sha256, "journal_terminal_sha256")
        _require_sha256(self.test_set_sha256, "test_set_sha256", optional=True)
        _require_non_negative_int(
            self.estimated_bytes_total, "estimated_bytes_total", optional=True
        )
        _require_non_negative_int(self.billed_bytes_total, "billed_bytes_total", optional=True)
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise EvaluationError("execution case IDs must be unique")

    @property
    def status(
        self,
    ) -> Literal["complete", "invalid_gold_failure", "unresolved_cost", "policy_breach"]:
        """Derive validity from immutable case outcomes."""
        if any(
            query.error_code
            in (
                "aggregate_billed_byte_cap_exceeded",
                "aggregate_execution_cost_cap_exceeded",
            )
            for case in self.cases
            for query in (case.gold, case.prediction)
        ):
            return "policy_breach"
        if any(case.gold.status != "ok" or case.gold.result is None for case in self.cases):
            return "invalid_gold_failure"
        if any(
            query.status == "unresolved_cost"
            or (
                query.submission_attempted
                and (query.billed_bytes is None or query.cost.measurement_status == "unmeasured")
            )
            for case in self.cases
            for query in (case.gold, case.prediction)
        ):
            return "unresolved_cost"
        return "complete"


@dataclass(frozen=True)
class BootstrapPolicy:
    """Deterministic bootstrap configuration."""

    samples: int = 10_000
    seed: int = 42
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        if self.samples < 1:
            raise EvaluationError("bootstrap samples must be positive")
        _require_finite(self.confidence_level, "confidence_level")
        if not 0 < self.confidence_level < 1:
            raise EvaluationError("confidence_level must be between zero and one")


@dataclass(frozen=True)
class ConfidenceInterval:
    """Finite confidence interval with an explicit confidence level."""

    lower: float
    upper: float
    confidence_level: float

    def __post_init__(self) -> None:
        _require_finite(self.lower, "lower")
        _require_finite(self.upper, "upper")
        _require_finite(self.confidence_level, "confidence_level")
        if self.lower > self.upper:
            raise EvaluationError("confidence interval lower bound exceeds upper bound")
        if not 0 < self.confidence_level < 1:
            raise EvaluationError("confidence_level must be between zero and one")


@dataclass(frozen=True)
class RatioMetric:
    """A rate that never loses its numerator or denominator."""

    numerator: float | None
    denominator: int
    value: float | None
    interval: ConfidenceInterval | None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.denominator, "denominator")
        if self.numerator is None:
            if self.value is not None or self.interval is not None:
                raise EvaluationError("invalid ratio requires null value and interval")
            return
        _require_finite_non_negative(self.numerator, "numerator")
        if self.numerator > self.denominator:
            raise EvaluationError("numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.value is not None:
                raise EvaluationError("zero denominator requires null value")
        elif self.value is None or not math.isclose(self.value, self.numerator / self.denominator):
            raise EvaluationError("ratio value must equal numerator / denominator")


@dataclass(frozen=True)
class DistributionMetric:
    """Compact finite latency or cost distribution summary."""

    expected_count: int
    observed_count: int
    missing_count: int
    p50: float | None
    p95: float | None
    p99: float | None
    p50_interval: ConfidenceInterval | None
    p95_interval: ConfidenceInterval | None
    p99_interval: ConfidenceInterval | None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.expected_count, "expected_count")
        _require_non_negative_int(self.observed_count, "observed_count")
        _require_non_negative_int(self.missing_count, "missing_count")
        if self.observed_count + self.missing_count != self.expected_count:
            raise EvaluationError("observed and missing counts must equal expected_count")
        for name, value in (("p50", self.p50), ("p95", self.p95), ("p99", self.p99)):
            _require_finite_non_negative(value, name, optional=True)
        values = (self.p50, self.p95, self.p99)
        intervals = (self.p50_interval, self.p95_interval, self.p99_interval)
        if self.observed_count == 0 and any(value is not None for value in values + intervals):
            raise EvaluationError("empty distribution requires null percentiles")
        if self.observed_count > 0 and any(value is None for value in values + intervals):
            raise EvaluationError("observed distribution requires percentiles and intervals")


@dataclass(frozen=True)
class AnswerScores:
    """Per-case answer precision, recall and F1."""

    precision: float
    recall: float
    f1: float

    def __post_init__(self) -> None:
        for name, value in (
            ("precision", self.precision),
            ("recall", self.recall),
            ("f1", self.f1),
        ):
            _require_finite(value, name)
            if not 0 <= value <= 1:
                raise EvaluationError(f"{name} must be between zero and one")


@dataclass(frozen=True)
class CaseEvaluation:
    """Compact derived record retained in evaluation reports."""

    case_id: str
    difficulty: str
    categories: tuple[str, ...]
    exact_match: bool
    structural_match: bool
    execution_match: bool | None
    answer_scores: AnswerScores | None
    inference_latency_ms: float | None
    execution_latency_ms: float | None
    inference_cost: CostEvidence
    execution_cost: CostEvidence
    failure_tags: tuple[str, ...]
    gold_execution_latency_ms: float | None = None
    gold_execution_cost: CostEvidence | None = None

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_sorted_unique(self.categories, "categories")
        _require_sorted_unique(self.failure_tags, "failure_tags")
        _require_finite_non_negative(
            self.inference_latency_ms, "inference_latency_ms", optional=True
        )
        _require_finite_non_negative(
            self.execution_latency_ms, "execution_latency_ms", optional=True
        )
        _require_finite_non_negative(
            self.gold_execution_latency_ms, "gold_execution_latency_ms", optional=True
        )
        if self.execution_match is not None and not isinstance(self.execution_match, bool):
            raise EvaluationError("execution_match must be boolean or null")


@dataclass(frozen=True)
class Readiness:
    """Derived implementation and scientific readiness blockers."""

    implementation_blockers: tuple[str, ...]
    scientific_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sorted_unique(self.implementation_blockers, "implementation_blockers")
        _require_sorted_unique(self.scientific_blockers, "scientific_blockers")

    @property
    def implementation_status(self) -> Literal["ready", "blocked"]:
        """Return implementation readiness derived from blockers."""
        return "blocked" if self.implementation_blockers else "ready"

    @property
    def scientific_status(self) -> Literal["ready", "blocked"]:
        """Return scientific readiness derived from both blocker classes."""
        return "blocked" if self.implementation_blockers or self.scientific_blockers else "ready"


@dataclass(frozen=True)
class EvaluationReport:
    """Offline deterministic six-dimensional report for one primary run."""

    baseline_id: str
    primary_run_id: str
    primary_prediction_sha256: str
    primary_execution_sha256: str
    replicate_pairs: tuple[tuple[str, str, str], ...]
    test_set_sha256: str
    case_set_sha256: str
    expected_case_count: int
    represented_case_count: int
    readiness: Readiness
    bootstrap: BootstrapPolicy
    cases: tuple[CaseEvaluation, ...]
    dimensions: tuple[tuple[str, Any], ...]
    breakdowns: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        _require_text(self.baseline_id, "baseline_id")
        _require_text(self.primary_run_id, "primary_run_id")
        for field, digest in (
            ("primary_prediction_sha256", self.primary_prediction_sha256),
            ("primary_execution_sha256", self.primary_execution_sha256),
            ("test_set_sha256", self.test_set_sha256),
            ("case_set_sha256", self.case_set_sha256),
        ):
            _require_sha256(digest, field)
        _require_non_negative_int(self.expected_case_count, "expected_case_count")
        _require_non_negative_int(self.represented_case_count, "represented_case_count")
        if self.represented_case_count > self.expected_case_count:
            raise EvaluationError("represented cases cannot exceed expected population")
        replicate_ids = tuple(item[0] for item in self.replicate_pairs)
        if self.primary_run_id in replicate_ids:
            raise EvaluationError("replicate cannot reuse the primary run identity")
        if len(replicate_ids) != len(set(replicate_ids)):
            raise EvaluationError("replicate run IDs must be distinct")
        for _, prediction_sha, execution_sha in self.replicate_pairs:
            _require_sha256(prediction_sha, "replicate prediction sha256")
            _require_sha256(execution_sha, "replicate execution sha256")


@dataclass(frozen=True)
class MetricDelta:
    """Paired left-minus-right metric delta."""

    metric: str
    left_value: float
    right_value: float
    delta: float
    interval: ConfidenceInterval

    def __post_init__(self) -> None:
        _require_text(self.metric, "metric")
        for name, value in (
            ("left_value", self.left_value),
            ("right_value", self.right_value),
            ("delta", self.delta),
        ):
            _require_finite(value, name)
        if not math.isclose(self.delta, self.left_value - self.right_value):
            raise EvaluationError("metric delta must equal left minus right")


@dataclass(frozen=True)
class McNemarResult:
    """Exact paired-binary discordance evidence."""

    left_only: int
    right_only: int
    exact_p_value: float

    def __post_init__(self) -> None:
        _require_non_negative_int(self.left_only, "left_only")
        _require_non_negative_int(self.right_only, "right_only")
        _require_finite(self.exact_p_value, "exact_p_value")
        if not 0 <= self.exact_p_value <= 1:
            raise EvaluationError("exact_p_value must be between zero and one")


@dataclass(frozen=True)
class FailureModeSummary:
    """Complete per-slice failure counts over the represented population."""

    expected_count: int
    represented_count: int
    missing_count: int
    counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.expected_count, "expected_count")
        _require_non_negative_int(self.represented_count, "represented_count")
        _require_non_negative_int(self.missing_count, "missing_count")
        if self.represented_count + self.missing_count != self.expected_count:
            raise EvaluationError("represented and missing failure counts must equal expected")
        names = tuple(name for name, _ in self.counts)
        if names != tuple(sorted(set(names))):
            raise EvaluationError("failure count names must be sorted unique")
        for name, count in self.counts:
            _require_text(name, "failure count name")
            _require_non_negative_int(count, f"failure count {name}")


_BILINGUAL_SLICES = (
    "english_reference",
    "english",
    "vietnamese",
    "vietnamese_unaccented",
    "translation",
)


@dataclass(frozen=True)
class BilingualEvaluationReport:
    """Paired five-system bilingual comparison over exactly 100 cases."""

    english_reference_report_sha256: str
    english_report_sha256: str
    vietnamese_report_sha256: str
    vietnamese_unaccented_report_sha256: str
    translation_report_sha256: str
    frozen_input_sha256: str
    test_set_sha256: str
    case_set_sha256: str
    pair_ids: tuple[str, ...]
    reviewed_count: int
    live_verified_count: int
    accuracies: tuple[tuple[str, RatioMetric], ...]
    english_regression: MetricDelta
    language_gap: MetricDelta
    accent_gap: MetricDelta
    mcnemar: tuple[tuple[str, McNemarResult], ...]
    failure_modes: tuple[tuple[str, FailureModeSummary], ...]
    inference_latency_ms: tuple[tuple[str, DistributionMetric], ...]
    bootstrap: BootstrapPolicy

    def __post_init__(self) -> None:
        for field, digest in (
            ("english_reference_report_sha256", self.english_reference_report_sha256),
            ("english_report_sha256", self.english_report_sha256),
            ("vietnamese_report_sha256", self.vietnamese_report_sha256),
            (
                "vietnamese_unaccented_report_sha256",
                self.vietnamese_unaccented_report_sha256,
            ),
            ("translation_report_sha256", self.translation_report_sha256),
            ("frozen_input_sha256", self.frozen_input_sha256),
            ("test_set_sha256", self.test_set_sha256),
            ("case_set_sha256", self.case_set_sha256),
        ):
            _require_sha256(digest, field)
        if len(self.pair_ids) != 100:
            raise EvaluationError("bilingual report requires exactly 100 pair IDs")
        if len(set(self.pair_ids)) != len(self.pair_ids):
            raise EvaluationError("bilingual report pair IDs must be unique")
        if any(not isinstance(pair_id, str) or not pair_id for pair_id in self.pair_ids):
            raise EvaluationError("bilingual report pair IDs must be non-empty text")
        _require_non_negative_int(self.reviewed_count, "reviewed_count")
        _require_non_negative_int(self.live_verified_count, "live_verified_count")
        for field, values in (
            ("accuracies", self.accuracies),
            ("failure_modes", self.failure_modes),
            ("inference_latency_ms", self.inference_latency_ms),
        ):
            names = tuple(name for name, _ in values)
            if names != _BILINGUAL_SLICES:
                raise EvaluationError(f"{field} must cover every bilingual slice in order")
        mcnemar_names = tuple(name for name, _ in self.mcnemar)
        if mcnemar_names != (
            "english_vs_vietnamese",
            "vietnamese_vs_unaccented",
            "vietnamese_vs_translation",
        ):
            raise EvaluationError("mcnemar evidence must cover every registered comparison")
        if self.english_regression.metric != "english_regression":
            raise EvaluationError("English regression metric identity mismatch")
        if self.language_gap.metric != "language_gap":
            raise EvaluationError("language gap metric identity mismatch")
        if self.accent_gap.metric != "accent_gap":
            raise EvaluationError("accent gap metric identity mismatch")


@dataclass(frozen=True)
class GatePolicy:
    """Pinned pre-registered bilingual acceptance thresholds."""

    english_regression_max: float = 0.02
    language_gap_max: float = 0.10
    accent_gap_max: float = 0.10
    required_pair_count: int = 100
    tolerance: float = 1e-12

    def __post_init__(self) -> None:
        if (
            self.english_regression_max != 0.02
            or self.language_gap_max != 0.10
            or self.accent_gap_max != 0.10
            or self.required_pair_count != 100
            or self.tolerance != 1e-12
        ):
            raise EvaluationError("bilingual gate policy is pre-registered and immutable")

    @property
    def sha256(self) -> str:
        body = {
            "accent_gap_max": self.accent_gap_max,
            "english_regression_max": self.english_regression_max,
            "language_gap_max": self.language_gap_max,
            "required_pair_count": self.required_pair_count,
            "tolerance": self.tolerance,
        }
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GateObservation:
    """One observed value evaluated against one frozen threshold."""

    name: str
    observed: float
    threshold: float
    operator: Literal["max", "exact"]
    passed: bool
    tolerance: float

    def __post_init__(self) -> None:
        _require_text(self.name, "gate observation name")
        _require_finite(self.observed, "gate observed value")
        _require_finite(self.threshold, "gate threshold")
        if self.operator not in ("max", "exact"):
            raise EvaluationError("unknown gate operator")
        if not isinstance(self.passed, bool):
            raise EvaluationError("gate pass result must be boolean")
        _require_finite_non_negative(self.tolerance, "gate tolerance")
        expected = (
            self.observed <= self.threshold + self.tolerance
            if self.operator == "max"
            else self.observed == self.threshold
        )
        if self.passed != expected:
            raise EvaluationError("gate pass flag must equal its computed result")


@dataclass(frozen=True)
class GateDecision:
    """Immutable result of applying the pre-registered policy to one report."""

    bilingual_report_sha256: str
    frozen_input_sha256: str
    policy_sha256: str
    observations: tuple[GateObservation, ...]
    passed: bool
    failed_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.bilingual_report_sha256, "bilingual_report_sha256")
        _require_sha256(self.frozen_input_sha256, "frozen_input_sha256")
        _require_sha256(self.policy_sha256, "policy_sha256")
        names = tuple(item.name for item in self.observations)
        if names != (
            "english_regression",
            "language_gap",
            "accent_gap",
            "reviewed_count",
            "live_verified_count",
            "interval_completeness",
            "failure_count_completeness",
        ):
            raise EvaluationError("gate decision must contain every registered observations")
        expected_failures = tuple(
            sorted(item.name for item in self.observations if not item.passed)
        )
        if self.failed_gates != expected_failures:
            raise EvaluationError("failed gates must match failed observations")
        if self.passed != (not self.failed_gates):
            raise EvaluationError("overall gate result must match failed gates")


@dataclass(frozen=True)
class ComparisonReport:
    """Deterministic paired comparison of two compatible evaluation reports."""

    left_report_sha256: str
    right_report_sha256: str
    test_set_sha256: str
    case_set_sha256: str
    deltas: tuple[MetricDelta, ...]
    readiness: Readiness
    bootstrap: BootstrapPolicy

    def __post_init__(self) -> None:
        for field, digest in (
            ("left_report_sha256", self.left_report_sha256),
            ("right_report_sha256", self.right_report_sha256),
            ("test_set_sha256", self.test_set_sha256),
            ("case_set_sha256", self.case_set_sha256),
        ):
            _require_sha256(digest, field)


@dataclass(frozen=True)
class ManualFailureReview:
    """Hash-bound manual failure labels, including optional semantic drift."""

    case_id: str
    reviewer_id: str
    tags: tuple[str, ...]
    note_sha256: str
    review_artifact_sha256: str
    source: Literal["manual_review"] = "manual_review"

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_text(self.reviewer_id, "reviewer_id")
        _require_sorted_unique(self.tags, "tags")
        _require_sha256(self.note_sha256, "note_sha256")
        _require_sha256(self.review_artifact_sha256, "review_artifact_sha256")
        if self.source != "manual_review":
            raise EvaluationError("manual failure review source must be manual_review")


CanonicalArtifact: TypeAlias = (
    CanonicalPredictionRun
    | ExecutionEvidence
    | EvaluationReport
    | ComparisonReport
    | PrivacyReview
    | TranslationEvidence
    | BilingualEvaluationReport
    | GateDecision
)
