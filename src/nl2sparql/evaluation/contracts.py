"""Immutable contracts shared by the NL2SQL evaluation framework."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, TypeAlias


class EvaluationError(ValueError):
    """Raised when evaluation evidence violates a canonical contract."""


PredictionStatus: TypeAlias = Literal[
    "ok", "no_output", "invalid_sql", "unsafe_sql", "generation_error", "timeout"
]
MeasurementStatus: TypeAlias = Literal["observed", "unmeasured"]
DataEgress: TypeAlias = Literal["none", "provider", "unknown"]
ExecutionStatus: TypeAlias = Literal[
    "ok", "error", "timeout", "guard_blocked", "not_run", "unresolved_cost"
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
    """Exact observed cost or an explicit statement that cost was unmeasured."""

    measurement_status: MeasurementStatus
    amount: Decimal | None
    currency: str | None
    source: str | None

    def __post_init__(self) -> None:
        if self.measurement_status not in ("observed", "unmeasured"):
            raise EvaluationError("unknown measurement_status")
        if self.measurement_status == "unmeasured":
            if self.amount is not None or self.currency is not None or self.source is not None:
                raise EvaluationError("unmeasured cost requires null amount, currency and source")
            return
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite() or self.amount < 0:
            raise EvaluationError("observed cost requires a finite non-negative Decimal amount")
        if self.currency is None or self.source is None:
            raise EvaluationError("observed cost requires currency and source")
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
        for key, digest in self.fingerprints:
            _require_text(key, "fingerprint key")
            _require_sha256(digest, f"fingerprint {key}")


@dataclass(frozen=True)
class CanonicalPredictionRun:
    """Complete ordered prediction artifact independent of baseline-native formats."""

    baseline_id: str
    run_id: str
    seed: int
    generated_at: datetime
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

    def __post_init__(self) -> None:
        if self.status not in (
            "ok",
            "error",
            "timeout",
            "guard_blocked",
            "not_run",
            "unresolved_cost",
        ):
            raise EvaluationError("unknown execution status")
        _require_finite_non_negative(self.latency_ms, "latency_ms", optional=True)
        _require_non_negative_int(self.billed_bytes, "billed_bytes", optional=True)
        if self.status == "ok" and self.job_id is None:
            raise EvaluationError("successful execution requires job_id")


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

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "policy_id")
        _require_text(self.currency, "currency")
        if not self.amount_per_tib.is_finite() or self.amount_per_tib < 0:
            raise EvaluationError("amount_per_tib must be finite and non-negative")
        _require_sha256(self.source_sha256, "source_sha256")


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

    def __post_init__(self) -> None:
        _require_text(self.project, "project")
        _require_text(self.location, "location")
        _require_finite_non_negative(self.timeout_seconds, "timeout_seconds")
        if self.timeout_seconds == 0:
            raise EvaluationError("timeout_seconds must be positive")
        _require_non_negative_int(self.per_query_byte_cap, "per_query_byte_cap")
        _require_non_negative_int(self.aggregate_byte_cap, "aggregate_byte_cap")
        if not self.estimated_cost_cap.is_finite() or self.estimated_cost_cap < 0:
            raise EvaluationError("estimated_cost_cap must be finite and non-negative")


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

    def __post_init__(self) -> None:
        _require_text(self.execution_id, "execution_id")
        _require_sha256(self.prediction_run_sha256, "prediction_run_sha256")
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_sha256(self.journal_terminal_sha256, "journal_terminal_sha256")
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise EvaluationError("execution case IDs must be unique")

    @property
    def status(self) -> Literal["complete", "invalid_gold_failure", "unresolved_cost"]:
        """Derive validity from immutable case outcomes."""
        if any(case.gold.status != "ok" for case in self.cases):
            return "invalid_gold_failure"
        if any(
            query.status == "unresolved_cost"
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

    numerator: float
    denominator: int
    value: float | None
    interval: ConfidenceInterval | None

    def __post_init__(self) -> None:
        _require_finite_non_negative(self.numerator, "numerator")
        _require_non_negative_int(self.denominator, "denominator")
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
    execution_match: bool
    answer_scores: AnswerScores
    inference_latency_ms: float | None
    execution_latency_ms: float | None
    inference_cost: CostEvidence
    execution_cost: CostEvidence
    failure_tags: tuple[str, ...]

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
    CanonicalPredictionRun | ExecutionEvidence | EvaluationReport | ComparisonReport | PrivacyReview
)
