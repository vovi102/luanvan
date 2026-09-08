"""Ordered asynchronous evaluation for the B4/B5 large-LLM baselines."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol

import sqlglot
from sqlglot.errors import SqlglotError

from nl2sparql.models.b12.evaluate import EvaluationCase, load_evaluation_cases
from nl2sparql.models.b45.budget import BudgetLedger, BudgetSnapshot
from nl2sparql.models.b45.contracts import (
    LargeBaselineEvidence,
    LargeLLMConfig,
    LargeLLMError,
    LargeLLMPrediction,
)
from nl2sparql.models.b45.openrouter import ModelMetadataEvidence, OpenRouterRequestError

OutcomeStatus = Literal[
    "completed", "extraction_failed", "request_failed", "budget_blocked", "cost_unresolved"
]
Difficulty = Literal["easy", "medium", "hard"]
BaselineName = Literal["b4", "b5"]

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class EvaluationOutcome:
    """One source case joined to either a prediction or a safe failure code.

    Attributes:
        case_id: Stable source-case identifier.
        question_sha256: SHA-256 of the exact UTF-8 source question.
        gold_sql: Expected safe GoogleSQL for the case.
        difficulty: Accepted evaluation difficulty label.
        categories: Sorted unique evaluation category labels.
        status: Stable generation or failure classification.
        prediction: Validated prediction for generated outcomes, otherwise ``None``.
        safe_error_code: Secret-safe failure code, otherwise ``None``.
        baseline: Baseline identity bound to this journal record.
        input_sha256: Exact evaluation snapshot fingerprint when available.
        config_sha256: Exact generation configuration fingerprint.
        catalog_sha256: Exact catalog snapshot fingerprint.
        summary_sha256: Exact catalog summary fingerprint.
        training_sha256: Exact B5 training fingerprint, or ``None`` for B4.
        model_id: Exact configured remote model identifier.
        provider_slug: Exact configured remote provider.
        model_metadata_sha256: Exact accepted endpoint metadata fingerprint.
        source_synthetic: Whether the source case was synthetic.
        source_trusted: Whether the source case came from trusted reviewed live evidence.
        training_accepted: Whether B5 training provenance was accepted.
        prompt_sha256: Non-secret prompt fingerprint for attempted or blocked requests.
        attempt_count: Number of safe transport attempts completed.
        authoritative_cost_usd: Exact billed cost for this outcome, independent of
            whether a prediction was produced.
        budget_checkpoint: Durable budget state after this outcome was accepted.
    """

    case_id: str
    question_sha256: str
    gold_sql: str
    difficulty: Difficulty
    categories: tuple[str, ...]
    status: OutcomeStatus
    prediction: LargeLLMPrediction | None
    safe_error_code: str | None
    baseline: BaselineName
    input_sha256: str | None
    config_sha256: str
    catalog_sha256: str
    summary_sha256: str
    training_sha256: str | None
    model_id: str
    provider_slug: str
    model_metadata_sha256: str | None
    source_synthetic: bool
    source_trusted: bool
    training_accepted: bool
    prompt_sha256: str | None
    attempt_count: int
    budget_checkpoint: BudgetSnapshot
    authoritative_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise LargeLLMError("evaluation outcome case ID must not be empty")
        for label, value in (
            ("question fingerprint", self.question_sha256),
            ("config fingerprint", self.config_sha256),
            ("catalog fingerprint", self.catalog_sha256),
            ("summary fingerprint", self.summary_sha256),
        ):
            if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
                raise LargeLLMError(f"evaluation outcome {label} is invalid")
        if self.input_sha256 is not None and _SHA256_RE.fullmatch(self.input_sha256) is None:
            raise LargeLLMError("evaluation outcome input fingerprint is invalid")
        if self.baseline not in {"b4", "b5"}:
            raise LargeLLMError("evaluation outcome baseline must be b4 or b5")
        if self.baseline == "b4" and self.training_sha256 is not None:
            raise LargeLLMError("B4 evaluation outcome must not have training provenance")
        if self.baseline == "b5" and (
            self.training_sha256 is None or _SHA256_RE.fullmatch(self.training_sha256) is None
        ):
            raise LargeLLMError("B5 evaluation outcome requires a training fingerprint")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise LargeLLMError("evaluation outcome model ID must not be empty")
        if not isinstance(self.provider_slug, str) or not self.provider_slug:
            raise LargeLLMError("evaluation outcome provider must not be empty")
        if (
            self.model_metadata_sha256 is not None
            and _SHA256_RE.fullmatch(self.model_metadata_sha256) is None
        ):
            raise LargeLLMError("evaluation outcome model metadata fingerprint is invalid")
        if not isinstance(self.source_synthetic, bool) or not isinstance(self.source_trusted, bool):
            raise LargeLLMError("evaluation outcome source provenance is invalid")
        if not isinstance(self.training_accepted, bool):
            raise LargeLLMError("evaluation outcome training acceptance is invalid")
        if self.baseline == "b4" and self.training_accepted:
            raise LargeLLMError("B4 evaluation outcome must not accept training provenance")
        if self.prompt_sha256 is not None and _SHA256_RE.fullmatch(self.prompt_sha256) is None:
            raise LargeLLMError("evaluation outcome prompt fingerprint is invalid")
        if (
            not isinstance(self.attempt_count, int)
            or isinstance(self.attempt_count, bool)
            or self.attempt_count < 0
        ):
            raise LargeLLMError("evaluation outcome attempt count is invalid")
        if not isinstance(self.budget_checkpoint, BudgetSnapshot):
            raise LargeLLMError("evaluation outcome budget checkpoint is invalid")
        expected_cost = (
            self.prediction.completion.charged_cost_usd
            if isinstance(self.prediction, LargeLLMPrediction)
            else _ZERO
        )
        if self.authoritative_cost_usd is None:
            object.__setattr__(self, "authoritative_cost_usd", expected_cost)
        if (
            not isinstance(self.authoritative_cost_usd, Decimal)
            or not self.authoritative_cost_usd.is_finite()
            or self.authoritative_cost_usd < _ZERO
        ):
            raise LargeLLMError(
                "evaluation outcome authoritative cost must be a finite non-negative Decimal"
            )
        if self.prediction is not None and self.authoritative_cost_usd != expected_cost:
            raise LargeLLMError("evaluation outcome authoritative cost disagrees with prediction")
        if not isinstance(self.gold_sql, str) or not self.gold_sql.strip():
            raise LargeLLMError("evaluation outcome gold SQL must not be empty")
        if self.difficulty not in {"easy", "medium", "hard"}:
            raise LargeLLMError("evaluation outcome difficulty is invalid")
        if (
            not isinstance(self.categories, tuple)
            or not self.categories
            or self.categories != tuple(sorted(set(self.categories)))
        ):
            raise LargeLLMError("evaluation outcome categories must be sorted and unique")
        if self.status not in {
            "completed",
            "extraction_failed",
            "request_failed",
            "budget_blocked",
            "cost_unresolved",
        }:
            raise LargeLLMError("evaluation outcome status is invalid")

        has_prediction = self.status in {"completed", "extraction_failed"}
        if has_prediction:
            if not isinstance(self.prediction, LargeLLMPrediction):
                raise LargeLLMError("generated evaluation outcome requires a prediction")
            expected_status = (
                "completed" if self.prediction.extraction_status == "ok" else "extraction_failed"
            )
            if self.status != expected_status:
                raise LargeLLMError("evaluation outcome status disagrees with SQL extraction")
            if self.safe_error_code is not None:
                raise LargeLLMError("generated evaluation outcome must not have an error code")
            prediction_identity = (
                hashlib.sha256(self.prediction.question.encode("utf-8")).hexdigest(),
                self.prediction.baseline,
                self.prediction.config_sha256,
                self.prediction.catalog_sha256,
                self.prediction.summary_sha256,
                self.prediction.training_sha256,
                self.prediction.completion.model_id,
            )
            outcome_identity = (
                self.question_sha256,
                self.baseline,
                self.config_sha256,
                self.catalog_sha256,
                self.summary_sha256,
                self.training_sha256,
                self.model_id,
            )
            if prediction_identity != outcome_identity:
                raise LargeLLMError("evaluation outcome identity disagrees with prediction")
            if self.prompt_sha256 != self.prediction.prompt_sha256:
                raise LargeLLMError("evaluation outcome prompt disagrees with prediction")
            if self.attempt_count != self.prediction.completion.attempt_count:
                raise LargeLLMError("evaluation outcome attempt count disagrees with prediction")
        else:
            if self.prediction is not None:
                raise LargeLLMError("failed evaluation outcome must not have a prediction")
            if (
                not isinstance(self.safe_error_code, str)
                or _ERROR_CODE_RE.fullmatch(self.safe_error_code) is None
            ):
                raise LargeLLMError("failed evaluation outcome requires a safe error code")
            if (
                self.status in {"budget_blocked", "cost_unresolved"} or self.attempt_count > 0
            ) and self.prompt_sha256 is None:
                raise LargeLLMError("attempted evaluation outcome requires prompt fingerprint")


class OutcomeJournal(Protocol):
    """Durable append seam called as soon as one new case completes."""

    def append(self, outcome: EvaluationOutcome) -> None:
        """Persist one fully validated outcome.

        Args:
            outcome: Immutable case and run evidence to append durably.

        Raises:
            Exception: Implementations propagate durability failures to abort the run.
        """
        ...


@dataclass(frozen=True)
class LargeEvaluationMetrics:
    """Operational outcome, latency, token, and exact-cost aggregates.

    Attributes:
        total: Number of source cases represented.
        completed: Number with successfully extracted safe SQL.
        extraction_failed: Number generated but rejected by extraction.
        request_failed: Number whose remote request failed.
        budget_blocked: Number stopped before a request by the hard cost cap.
        cost_unresolved: Number whose provider charge remains unresolved.
        p50_latency_ms: Median latency over outcomes carrying predictions.
        p95_latency_ms: Interpolated 95th percentile prediction latency.
        input_tokens: Total provider-reported input tokens.
        output_tokens: Total provider-reported output tokens.
        charged_cost_usd: Exact authoritative Decimal charges.
        cost_per_1k_queries_usd: Exact cost scaled to one thousand source cases.
        extraction_status_counts: Sorted extraction-status counts.
        difficulty_counts: Sorted source difficulty counts.
        category_counts: Sorted source category counts.
    """

    total: int
    completed: int
    extraction_failed: int
    request_failed: int
    budget_blocked: int
    cost_unresolved: int
    p50_latency_ms: float
    p95_latency_ms: float
    input_tokens: int
    output_tokens: int
    charged_cost_usd: Decimal
    cost_per_1k_queries_usd: Decimal
    extraction_status_counts: tuple[tuple[str, int], ...]
    difficulty_counts: tuple[tuple[str, int], ...]
    category_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        count_values = (
            self.total,
            self.completed,
            self.extraction_failed,
            self.request_failed,
            self.budget_blocked,
            self.cost_unresolved,
            self.input_tokens,
            self.output_tokens,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in count_values
        ):
            raise LargeLLMError("evaluation metric counts must be non-negative integers")
        if sum(count_values[1:6]) != self.total:
            raise LargeLLMError("evaluation outcome counts must sum to total")
        if any(
            not isinstance(value, float) or not math.isfinite(value) or value < 0.0
            for value in (self.p50_latency_ms, self.p95_latency_ms)
        ):
            raise LargeLLMError("evaluation latencies must be finite non-negative floats")
        if any(
            not isinstance(value, Decimal) or not value.is_finite() or value < _ZERO
            for value in (self.charged_cost_usd, self.cost_per_1k_queries_usd)
        ):
            raise LargeLLMError("evaluation costs must be finite non-negative Decimals")
        for counts in (
            self.extraction_status_counts,
            self.difficulty_counts,
            self.category_counts,
        ):
            if (
                not isinstance(counts, tuple)
                or counts != tuple(sorted(counts))
                or len({name for name, _count in counts}) != len(counts)
                or any(
                    not isinstance(name, str)
                    or not name
                    or not isinstance(count, int)
                    or isinstance(count, bool)
                    or count <= 0
                    for name, count in counts
                )
            ):
                raise LargeLLMError("evaluation grouped counts must be sorted and positive")


@dataclass(frozen=True)
class LargeEvaluationRun:
    """One ordered B4/B5 run with immutable accounting and identity evidence.

    Attributes:
        run_id: Stable identifier distinct across repeated scientific runs.
        baseline: Evaluated B4 or B5 strategy.
        outcomes: Outcomes in exact source-case order.
        metrics: Aggregated operational and cost evidence.
        scientific_ready: Whether no scientific blockers remain.
        blockers: Sorted stable reasons scientific use is disallowed.
        seed: Fixed generation seed.
        generated_at_utc: UTC generation timestamp.
        input_sha256: Exact evaluation snapshot fingerprint when available.
        config_sha256: Exact generation configuration fingerprint.
        budget: Immutable final budget checkpoint.
        catalog_sha256: Exact catalog snapshot fingerprint.
        summary_sha256: Exact compiled catalog summary fingerprint.
        training_sha256: Exact B5 training fingerprint, or ``None`` for B4.
        model_id: Exact configured remote model identifier.
        provider_slug: Exact configured provider.
        model_metadata_sha256: Accepted endpoint metadata fingerprint, if supplied.
    """

    run_id: str
    baseline: BaselineName
    outcomes: tuple[EvaluationOutcome, ...]
    metrics: LargeEvaluationMetrics
    scientific_ready: bool
    blockers: tuple[str, ...]
    seed: int
    generated_at_utc: str
    input_sha256: str | None
    config_sha256: str
    budget: BudgetSnapshot
    catalog_sha256: str
    summary_sha256: str
    training_sha256: str | None
    model_id: str
    provider_slug: str
    model_metadata_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or _RUN_ID_RE.fullmatch(self.run_id) is None:
            raise LargeLLMError("evaluation run ID is invalid")
        if self.baseline not in {"b4", "b5"}:
            raise LargeLLMError("evaluation run baseline must be b4 or b5")
        if (
            not isinstance(self.outcomes, tuple)
            or any(not isinstance(outcome, EvaluationOutcome) for outcome in self.outcomes)
            or len({outcome.case_id for outcome in self.outcomes}) != len(self.outcomes)
        ):
            raise LargeLLMError("evaluation run outcomes must have unique case IDs")
        if not isinstance(self.metrics, LargeEvaluationMetrics):
            raise LargeLLMError("evaluation run metrics are invalid")
        if self.metrics.total != len(self.outcomes):
            raise LargeLLMError("evaluation run metrics total must match outcomes")
        if not isinstance(self.scientific_ready, bool):
            raise LargeLLMError("scientific readiness must be boolean")
        if (
            not isinstance(self.blockers, tuple)
            or self.blockers != tuple(sorted(set(self.blockers)))
            or any(_ERROR_CODE_RE.fullmatch(value) is None for value in self.blockers)
            or self.scientific_ready == bool(self.blockers)
        ):
            raise LargeLLMError("scientific blockers are invalid or inconsistent")
        if self.seed != 42 or not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise LargeLLMError("evaluation seed must be 42")
        if not isinstance(self.generated_at_utc, str) or not self.generated_at_utc.endswith("Z"):
            raise LargeLLMError("evaluation timestamp must be UTC")
        if self.input_sha256 is not None and _SHA256_RE.fullmatch(self.input_sha256) is None:
            raise LargeLLMError("evaluation input fingerprint is invalid")
        if (
            not isinstance(self.config_sha256, str)
            or _SHA256_RE.fullmatch(self.config_sha256) is None
        ):
            raise LargeLLMError("evaluation config fingerprint is invalid")
        if not isinstance(self.budget, BudgetSnapshot):
            raise LargeLLMError("evaluation budget snapshot is invalid")
        try:
            self.budget.__post_init__()
        except LargeLLMError as error:
            raise LargeLLMError(f"evaluation budget snapshot is invalid: {error}") from error
        if self.metrics != _metrics(self.outcomes):
            raise LargeLLMError("evaluation run metrics must be derived from outcomes")
        if self.budget.spent_usd != self.metrics.charged_cost_usd:
            raise LargeLLMError("evaluation run budget must match derived metrics")
        for label, value in (
            ("catalog fingerprint", self.catalog_sha256),
            ("summary fingerprint", self.summary_sha256),
        ):
            if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
                raise LargeLLMError(f"evaluation run {label} is invalid")
        if self.baseline == "b4" and self.training_sha256 is not None:
            raise LargeLLMError("B4 evaluation run must not have training provenance")
        if self.baseline == "b5" and (
            self.training_sha256 is None or _SHA256_RE.fullmatch(self.training_sha256) is None
        ):
            raise LargeLLMError("B5 evaluation run requires a training fingerprint")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise LargeLLMError("evaluation run model ID must not be empty")
        if not isinstance(self.provider_slug, str) or not self.provider_slug:
            raise LargeLLMError("evaluation run provider must not be empty")
        if (
            self.model_metadata_sha256 is not None
            and _SHA256_RE.fullmatch(self.model_metadata_sha256) is None
        ):
            raise LargeLLMError("evaluation run model metadata fingerprint is invalid")
        run_identity = (
            self.baseline,
            self.config_sha256,
            self.catalog_sha256,
            self.summary_sha256,
            self.training_sha256,
            self.model_id,
            self.provider_slug,
            self.model_metadata_sha256,
        )
        if any(
            (
                outcome.baseline,
                outcome.config_sha256,
                outcome.catalog_sha256,
                outcome.summary_sha256,
                outcome.training_sha256,
                outcome.model_id,
                outcome.provider_slug,
                outcome.model_metadata_sha256,
            )
            != run_identity
            for outcome in self.outcomes
        ):
            raise LargeLLMError("evaluation run identity disagrees with an outcome")
        if self.input_sha256 is not None and any(
            outcome.input_sha256 != self.input_sha256 for outcome in self.outcomes
        ):
            raise LargeLLMError("evaluation run input fingerprint disagrees with an outcome")
        if self.input_sha256 is None and "trusted_test_set_provenance_missing" not in self.blockers:
            raise LargeLLMError(
                "missing aggregate input fingerprint requires a test provenance blocker"
            )
        expected_blockers = _derived_run_blockers(self, self.metrics)
        if self.blockers != expected_blockers or self.scientific_ready != (not expected_blockers):
            raise LargeLLMError(
                "evaluation run readiness and blockers must be derived from outcomes"
            )


@dataclass(frozen=True)
class ReproducibilityReport:
    """Observed pairwise agreement across exactly three comparable runs.

    Attributes:
        run_count: Validated number of distinct runs, always three.
        pair_count: Number of pairwise run comparisons, always three.
        case_count: Number of ordered cases in each run.
        raw_output_agreement: Fraction of raw/failure observations that agree.
        normalized_sql_agreement: Fraction of normalized SQL/failure observations
            that agree.
    """

    run_count: int
    pair_count: int
    case_count: int
    raw_output_agreement: float
    normalized_sql_agreement: float


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _counts(values: Sequence[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(values).items()))


def _baseline_config(baseline: object) -> LargeLLMConfig:
    selected = getattr(baseline, "config", None)
    if not isinstance(selected, LargeLLMConfig):
        raise LargeLLMError("baseline must expose a validated config property")
    return selected


def _budget_ledger(baseline: object) -> BudgetLedger:
    selected = getattr(baseline, "budget_ledger", None)
    if not isinstance(selected, BudgetLedger):
        raise LargeLLMError("baseline must expose a validated budget ledger property")
    return selected


def _baseline_evidence(baseline: object) -> LargeBaselineEvidence:
    selected = getattr(baseline, "evaluation_evidence", None)
    if not isinstance(selected, LargeBaselineEvidence):
        raise LargeLLMError("baseline must expose validated evaluation evidence")
    return selected


def _question_sha256(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _validate_cases(cases: Sequence[EvaluationCase]) -> tuple[EvaluationCase, ...]:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise LargeLLMError("evaluation requires ordered EvaluationCase values")
    accepted = tuple(cases)
    if not accepted or any(not isinstance(case, EvaluationCase) for case in accepted):
        raise LargeLLMError("evaluation requires non-empty ordered EvaluationCase values")
    identifiers = tuple(case.case_id for case in accepted)
    if len(identifiers) != len(set(identifiers)):
        raise LargeLLMError("evaluation cases contain duplicate case IDs")
    return accepted


def _validate_completed(
    completed_outcomes: Sequence[EvaluationOutcome],
    cases: tuple[EvaluationCase, ...],
    *,
    evidence: LargeBaselineEvidence,
    model_metadata_sha256: str | None,
) -> dict[str, EvaluationOutcome]:
    if not isinstance(completed_outcomes, Sequence) or isinstance(completed_outcomes, (str, bytes)):
        raise LargeLLMError("completed outcomes must be an ordered sequence")
    accepted = tuple(completed_outcomes)
    if any(not isinstance(outcome, EvaluationOutcome) for outcome in accepted):
        raise LargeLLMError("completed outcomes must be EvaluationOutcome values")
    by_id = {outcome.case_id: outcome for outcome in accepted}
    if len(by_id) != len(accepted):
        raise LargeLLMError("completed outcomes contain duplicate case IDs")
    sources = {case.case_id: case for case in cases}
    for outcome in accepted:
        source = sources.get(outcome.case_id)
        if source is None or (
            outcome.question_sha256,
            outcome.gold_sql,
            outcome.difficulty,
            outcome.categories,
            outcome.baseline,
            outcome.input_sha256,
            outcome.config_sha256,
            outcome.catalog_sha256,
            outcome.summary_sha256,
            outcome.training_sha256,
            outcome.model_id,
            outcome.provider_slug,
            outcome.model_metadata_sha256,
            outcome.source_synthetic,
            outcome.source_trusted,
            outcome.training_accepted,
        ) != (
            _question_sha256(source.question),
            source.gold_sql,
            source.difficulty,
            source.categories,
            evidence.baseline,
            source.input_sha256,
            evidence.config_sha256,
            evidence.catalog_sha256,
            evidence.summary_sha256,
            evidence.training_sha256,
            evidence.model_id,
            evidence.provider_slug,
            model_metadata_sha256,
            source.synthetic,
            source._trusted_source,
            evidence.training_accepted,
        ):
            raise LargeLLMError("completed outcome does not match its source case")
    return by_id


def _outcome_from_prediction(
    case: EvaluationCase,
    prediction: LargeLLMPrediction,
    *,
    evidence: LargeBaselineEvidence,
    model_metadata_sha256: str | None,
    budget_checkpoint: BudgetSnapshot,
) -> EvaluationOutcome:
    if prediction.question != case.question:
        raise LargeLLMError("prediction question does not match its source case")
    if prediction.baseline != evidence.baseline:
        raise LargeLLMError("prediction baseline does not match evaluator baseline")
    return EvaluationOutcome(
        case_id=case.case_id,
        question_sha256=_question_sha256(case.question),
        gold_sql=case.gold_sql,
        difficulty=case.difficulty,
        categories=case.categories,
        status="completed" if prediction.extraction_status == "ok" else "extraction_failed",
        prediction=prediction,
        safe_error_code=None,
        baseline=evidence.baseline,
        input_sha256=case.input_sha256,
        config_sha256=evidence.config_sha256,
        catalog_sha256=evidence.catalog_sha256,
        summary_sha256=evidence.summary_sha256,
        training_sha256=evidence.training_sha256,
        model_id=evidence.model_id,
        provider_slug=evidence.provider_slug,
        model_metadata_sha256=model_metadata_sha256,
        source_synthetic=case.synthetic,
        source_trusted=case._trusted_source,
        training_accepted=evidence.training_accepted,
        prompt_sha256=prediction.prompt_sha256,
        attempt_count=prediction.completion.attempt_count,
        budget_checkpoint=budget_checkpoint,
        authoritative_cost_usd=prediction.completion.charged_cost_usd,
    )


def _failure_outcome(
    case: EvaluationCase,
    error: LargeLLMError,
    evidence: LargeBaselineEvidence,
    *,
    model_metadata_sha256: str | None,
    budget_checkpoint: BudgetSnapshot,
) -> EvaluationOutcome:
    code = error.code if isinstance(error, OpenRouterRequestError) else "prediction_failed"
    prompt = getattr(error, "prompt_sha256", None)
    if prompt is not None and not isinstance(prompt, str):
        prompt = None
    attempt_count = getattr(error, "attempt_count", 0)
    if not isinstance(attempt_count, int) or isinstance(attempt_count, bool) or attempt_count < 0:
        attempt_count = 0
    authoritative_cost = getattr(error, "authoritative_cost_usd", _ZERO)
    if (
        not isinstance(authoritative_cost, Decimal)
        or not authoritative_cost.is_finite()
        or authoritative_cost < _ZERO
    ):
        authoritative_cost = _ZERO
    status: OutcomeStatus
    if code == "budget_blocked":
        status = "budget_blocked"
    elif code == "cost_unresolved":
        status = "cost_unresolved"
    else:
        status = "request_failed"
    return EvaluationOutcome(
        case_id=case.case_id,
        question_sha256=_question_sha256(case.question),
        gold_sql=case.gold_sql,
        difficulty=case.difficulty,
        categories=case.categories,
        status=status,
        prediction=None,
        safe_error_code=code,
        baseline=evidence.baseline,
        input_sha256=case.input_sha256,
        config_sha256=evidence.config_sha256,
        catalog_sha256=evidence.catalog_sha256,
        summary_sha256=evidence.summary_sha256,
        training_sha256=evidence.training_sha256,
        model_id=evidence.model_id,
        provider_slug=evidence.provider_slug,
        model_metadata_sha256=model_metadata_sha256,
        source_synthetic=case.synthetic,
        source_trusted=case._trusted_source,
        training_accepted=evidence.training_accepted,
        prompt_sha256=prompt,
        attempt_count=attempt_count,
        budget_checkpoint=budget_checkpoint,
        authoritative_cost_usd=authoritative_cost,
    )


async def _predict_case(
    baseline: object,
    case: EvaluationCase,
    *,
    evidence: LargeBaselineEvidence,
    ledger: BudgetLedger,
    model_metadata_sha256: str | None,
) -> EvaluationOutcome:
    predict = getattr(baseline, "predict_detailed", None)
    if not callable(predict):
        raise LargeLLMError("baseline must provide async predict_detailed")
    parameters = inspect.signature(predict).parameters
    kwargs: dict[str, str] = {"request_id": case.case_id}
    if evidence.baseline == "b5" or "target_id" in parameters:
        kwargs["target_id"] = case.case_id
    try:
        prediction = await predict(case.question, **kwargs)
    except asyncio.CancelledError:
        raise
    except LargeLLMError as error:
        return _failure_outcome(
            case,
            error,
            evidence,
            model_metadata_sha256=model_metadata_sha256,
            budget_checkpoint=await ledger.snapshot(),
        )
    if not isinstance(prediction, LargeLLMPrediction):
        raise LargeLLMError("baseline must return LargeLLMPrediction")
    return _outcome_from_prediction(
        case,
        prediction,
        evidence=evidence,
        model_metadata_sha256=model_metadata_sha256,
        budget_checkpoint=await ledger.snapshot(),
    )


def _metrics(outcomes: tuple[EvaluationOutcome, ...]) -> LargeEvaluationMetrics:
    predictions = tuple(
        outcome.prediction for outcome in outcomes if outcome.prediction is not None
    )
    latencies = [prediction.latency_ms for prediction in predictions]
    input_tokens = sum(prediction.completion.input_tokens for prediction in predictions)
    output_tokens = sum(prediction.completion.output_tokens for prediction in predictions)
    charged_cost = sum((outcome.authoritative_cost_usd for outcome in outcomes), start=_ZERO)
    return LargeEvaluationMetrics(
        total=len(outcomes),
        completed=sum(outcome.status == "completed" for outcome in outcomes),
        extraction_failed=sum(outcome.status == "extraction_failed" for outcome in outcomes),
        request_failed=sum(outcome.status == "request_failed" for outcome in outcomes),
        budget_blocked=sum(outcome.status == "budget_blocked" for outcome in outcomes),
        cost_unresolved=sum(outcome.status == "cost_unresolved" for outcome in outcomes),
        p50_latency_ms=_quantile(latencies, 0.50),
        p95_latency_ms=_quantile(latencies, 0.95),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        charged_cost_usd=charged_cost,
        cost_per_1k_queries_usd=charged_cost * Decimal(1000) / Decimal(len(outcomes)),
        extraction_status_counts=_counts(
            [prediction.extraction_status for prediction in predictions]
        ),
        difficulty_counts=_counts([outcome.difficulty for outcome in outcomes]),
        category_counts=_counts(
            [category for outcome in outcomes for category in outcome.categories]
        ),
    )


def _derived_run_blockers(
    run: LargeEvaluationRun, metrics: LargeEvaluationMetrics
) -> tuple[str, ...]:
    predictions = tuple(
        outcome.prediction for outcome in run.outcomes if outcome.prediction is not None
    )
    blockers: set[str] = {"non_three_run_evidence"}
    if any(prediction.completion.synthetic_backend for prediction in predictions):
        blockers.add("synthetic_backend")
    if any(outcome.source_synthetic for outcome in run.outcomes):
        blockers.add("synthetic_test_set")
    if (
        run.input_sha256 is None
        or any(outcome.input_sha256 != run.input_sha256 for outcome in run.outcomes)
        or any(not outcome.source_trusted for outcome in run.outcomes)
    ):
        blockers.add("trusted_test_set_provenance_missing")
    if run.baseline == "b5" and any(not outcome.training_accepted for outcome in run.outcomes):
        blockers.add("trusted_training_provenance_missing")
    if len(run.outcomes) != 100:
        blockers.add("expected_100_cases")
    if metrics.completed != len(run.outcomes):
        blockers.add("incomplete_generation")
    if (
        metrics.cost_unresolved
        or run.budget.unresolved_request_ids
        or run.budget.reserved_usd > _ZERO
    ):
        blockers.add("unresolved_cost")
    if run.budget.stop_reason == "pricing_violation":
        blockers.add("pricing_violation")
    if run.budget.spent_usd > run.budget.cap_usd or metrics.charged_cost_usd > run.budget.cap_usd:
        blockers.add("cost_over_cap")
    if run.model_metadata_sha256 is None:
        blockers.add("missing_model_metadata")
    if any(prediction.completion.model_id != run.model_id for prediction in predictions):
        blockers.add("model_drift")
    if any(prediction.completion.provider_slug != run.provider_slug for prediction in predictions):
        blockers.add("provider_drift")
    if any(prediction.config_sha256 != run.config_sha256 for prediction in predictions):
        blockers.add("config_drift")
    if len({prediction.catalog_sha256 for prediction in predictions}) > 1:
        blockers.add("catalog_drift")
    if run.baseline == "b5" and len({prediction.training_sha256 for prediction in predictions}) > 1:
        blockers.add("training_drift")
    return tuple(sorted(blockers))


def _blockers(
    cases: tuple[EvaluationCase, ...],
    outcomes: tuple[EvaluationOutcome, ...],
    metrics: LargeEvaluationMetrics,
    config: LargeLLMConfig,
    metadata: ModelMetadataEvidence | None,
    budget: BudgetSnapshot,
    evidence: LargeBaselineEvidence,
) -> tuple[str, ...]:
    predictions = tuple(
        outcome.prediction for outcome in outcomes if outcome.prediction is not None
    )
    blockers: set[str] = {"non_three_run_evidence"}
    if any(prediction.completion.synthetic_backend for prediction in predictions):
        blockers.add("synthetic_backend")
    if any(case.synthetic for case in cases):
        blockers.add("synthetic_test_set")
    input_fingerprints = {case.input_sha256 for case in cases}
    if (
        None in input_fingerprints
        or len(input_fingerprints) != 1
        or not all(case._trusted_source for case in cases)
    ):
        blockers.add("trusted_test_set_provenance_missing")
    if evidence.baseline == "b5" and not evidence.training_accepted:
        blockers.add("trusted_training_provenance_missing")
    if len(cases) != 100:
        blockers.add("expected_100_cases")
    if metrics.completed != len(cases):
        blockers.add("incomplete_generation")
    if metrics.cost_unresolved or budget.unresolved_request_ids or budget.reserved_usd > _ZERO:
        blockers.add("unresolved_cost")
    if budget.stop_reason == "pricing_violation":
        blockers.add("pricing_violation")
    if budget.spent_usd > budget.cap_usd or metrics.charged_cost_usd > config.max_cost_usd:
        blockers.add("cost_over_cap")
    if metadata is None:
        blockers.add("missing_model_metadata")
    else:
        if metadata.model_id != config.model_id:
            blockers.add("model_drift")
        if metadata.provider_slug != config.provider.provider_slug:
            blockers.add("provider_drift")
        if (
            metadata.prompt_price_per_million_usd > config.provider.prompt_price_per_million_usd
            or metadata.completion_price_per_million_usd
            > config.provider.completion_price_per_million_usd
        ):
            blockers.add("pricing_violation")
    if any(prediction.completion.model_id != config.model_id for prediction in predictions):
        blockers.add("model_drift")
    if any(
        prediction.completion.provider_slug != config.provider.provider_slug
        for prediction in predictions
    ):
        blockers.add("provider_drift")
    if any(prediction.config_sha256 != config.sha256 for prediction in predictions):
        blockers.add("config_drift")
    if len({prediction.catalog_sha256 for prediction in predictions}) > 1:
        blockers.add("catalog_drift")
    if (
        evidence.baseline == "b5"
        and len({prediction.training_sha256 for prediction in predictions}) > 1
    ):
        blockers.add("training_drift")
    return tuple(sorted(blockers))


async def evaluate_large_baseline(
    cases: Sequence[EvaluationCase],
    baseline: object,
    *,
    run_id: str,
    concurrency: int,
    model_metadata: ModelMetadataEvidence | None,
    journal: OutcomeJournal | None = None,
    completed_outcomes: Sequence[EvaluationOutcome] = (),
) -> LargeEvaluationRun:
    """Evaluate cases concurrently while preserving source order.

    Args:
        cases: Non-empty ordered B1/B2 evaluation cases.
        baseline: Async B4/B5-compatible baseline exposing read-only configuration,
            budget, and run identity evidence.
        run_id: Stable identifier for this single evaluation run.
        concurrency: Worker bound, which must equal the pinned configuration.
        model_metadata: Accepted endpoint metadata or ``None`` to retain a blocker.
        journal: Optional durable append implementation called after each new outcome.
        completed_outcomes: Previously journaled outcomes eligible for strict resume.

    Returns:
        An immutable run whose outcomes remain in source-case order.

    Raises:
        LargeLLMError: If inputs, baseline evidence, resumption evidence, or generated
            predictions violate the evaluation contract.
        asyncio.CancelledError: After all outstanding workers are cancelled and joined.
        Exception: If journal durability fails; outstanding workers are cancelled first.
    """
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise LargeLLMError("evaluation run ID is invalid")
    accepted_cases = _validate_cases(cases)
    selected_config = _baseline_config(baseline)
    ledger = _budget_ledger(baseline)
    evidence = _baseline_evidence(baseline)
    if ledger.config_sha256 != selected_config.sha256:
        raise LargeLLMError("baseline config and budget ledger do not match")
    if evidence.config_sha256 != selected_config.sha256:
        raise LargeLLMError("baseline config and evaluation evidence do not match")
    if (
        not isinstance(concurrency, int)
        or isinstance(concurrency, bool)
        or concurrency != selected_config.concurrency
    ):
        raise LargeLLMError("evaluation concurrency must equal config concurrency")
    if model_metadata is not None and not isinstance(model_metadata, ModelMetadataEvidence):
        raise LargeLLMError("model metadata evidence is invalid")
    model_metadata_sha256 = model_metadata.metadata_sha256 if model_metadata is not None else None
    if journal is not None and not callable(getattr(journal, "append", None)):
        raise LargeLLMError("outcome journal must provide append")
    completed = _validate_completed(
        completed_outcomes,
        accepted_cases,
        evidence=evidence,
        model_metadata_sha256=model_metadata_sha256,
    )
    accepted_completed = tuple(completed_outcomes)
    if accepted_completed:
        expected_checkpoint = accepted_completed[-1].budget_checkpoint
        if await ledger.snapshot() != expected_checkpoint:
            raise LargeLLMError("budget checkpoint must be restored before resume")
    semaphore = asyncio.Semaphore(concurrency)

    async def worker(index: int, case: EvaluationCase) -> tuple[int, EvaluationOutcome]:
        async with semaphore:
            outcome = await _predict_case(
                baseline,
                case,
                evidence=evidence,
                ledger=ledger,
                model_metadata_sha256=model_metadata_sha256,
            )
            if journal is not None:
                journal.append(outcome)
            return index, outcome

    tasks = [
        asyncio.create_task(worker(index, case))
        for index, case in enumerate(accepted_cases)
        if case.case_id not in completed
    ]
    try:
        generated = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    indexed = [
        (index, completed[case.case_id])
        for index, case in enumerate(accepted_cases)
        if case.case_id in completed
    ]
    indexed.extend(generated)
    outcomes = tuple(outcome for _index, outcome in sorted(indexed, key=lambda item: item[0]))
    metrics = _metrics(outcomes)
    budget = await ledger.snapshot()
    blockers = _blockers(
        accepted_cases,
        outcomes,
        metrics,
        selected_config,
        model_metadata,
        budget,
        evidence,
    )
    input_fingerprints = {case.input_sha256 for case in accepted_cases}
    return LargeEvaluationRun(
        run_id=run_id,
        baseline=evidence.baseline,
        outcomes=outcomes,
        metrics=metrics,
        scientific_ready=not blockers,
        blockers=blockers,
        seed=selected_config.seed,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        input_sha256=(next(iter(input_fingerprints)) if len(input_fingerprints) == 1 else None),
        config_sha256=selected_config.sha256,
        budget=budget,
        catalog_sha256=evidence.catalog_sha256,
        summary_sha256=evidence.summary_sha256,
        training_sha256=evidence.training_sha256,
        model_id=evidence.model_id,
        provider_slug=evidence.provider_slug,
        model_metadata_sha256=model_metadata_sha256,
    )


def _comparison_identity(run: LargeEvaluationRun) -> tuple[object, ...]:
    if run.input_sha256 is None:
        raise LargeLLMError("reproducibility input fingerprint is missing")
    return (
        run.baseline,
        tuple(outcome.case_id for outcome in run.outcomes),
        run.input_sha256,
        run.config_sha256,
        run.catalog_sha256,
        run.summary_sha256,
        run.training_sha256,
        run.model_id,
        run.provider_slug,
        run.model_metadata_sha256,
    )


def _normalized_sql(prediction: LargeLLMPrediction) -> str:
    if prediction.sql is None:
        raise LargeLLMError("completed prediction is missing safe SQL")
    try:
        return sqlglot.parse_one(prediction.sql, read="bigquery").sql(
            dialect="bigquery", normalize=True, pretty=False
        )
    except (SqlglotError, TypeError, ValueError) as error:
        raise LargeLLMError("completed prediction contains invalid safe SQL") from error


def _agrees(left: EvaluationOutcome, right: EvaluationOutcome, *, normalized: bool) -> bool:
    if left.status != "completed" or right.status != "completed":
        return left.status == right.status
    if left.prediction is None or right.prediction is None:
        return False
    if normalized:
        return _normalized_sql(left.prediction) == _normalized_sql(right.prediction)
    return left.prediction.raw_output == right.prediction.raw_output


def compare_large_reproducibility(
    runs: Sequence[LargeEvaluationRun],
) -> ReproducibilityReport:
    """Measure pairwise agreement across exactly three comparable runs.

    Args:
        runs: Ordered sequence of exactly three immutable large-evaluation runs.

    Returns:
        Aggregate raw-output and normalized-safe-SQL agreement over all three
        run pairs and every ordered case.

    Raises:
        LargeLLMError: If run IDs are not distinct, input evidence is missing,
            run-level identities drift, or completed SQL cannot be normalized.
    """
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes)):
        raise LargeLLMError("reproducibility runs must be an ordered sequence")
    accepted = tuple(runs)
    if len(accepted) != 3 or any(not isinstance(run, LargeEvaluationRun) for run in accepted):
        raise LargeLLMError("reproducibility requires exactly three LargeEvaluationRun values")
    if len({run.run_id for run in accepted}) != 3:
        raise LargeLLMError("reproducibility run IDs must be distinct")
    reference = _comparison_identity(accepted[0])
    labels = (
        "baseline",
        "ordered case IDs",
        "input fingerprint",
        "config fingerprint",
        "catalog fingerprint",
        "summary fingerprint",
        "training fingerprint",
        "model",
        "provider",
        "model metadata fingerprint",
    )
    for run in accepted[1:]:
        identity = _comparison_identity(run)
        for label, expected, actual in zip(labels, reference, identity, strict=True):
            if actual != expected:
                raise LargeLLMError(f"reproducibility {label} mismatch")

    pairs = ((accepted[0], accepted[1]), (accepted[0], accepted[2]), (accepted[1], accepted[2]))
    comparison_count = len(reference[1]) * len(pairs)
    if comparison_count == 0:
        raise LargeLLMError("reproducibility requires at least one ordered case")
    raw_agreements = 0
    normalized_agreements = 0
    for left, right in pairs:
        for left_outcome, right_outcome in zip(left.outcomes, right.outcomes, strict=True):
            raw_agreements += _agrees(left_outcome, right_outcome, normalized=False)
            normalized_agreements += _agrees(left_outcome, right_outcome, normalized=True)
    return ReproducibilityReport(
        run_count=3,
        pair_count=3,
        case_count=len(reference[1]),
        raw_output_agreement=raw_agreements / comparison_count,
        normalized_sql_agreement=normalized_agreements / comparison_count,
    )


__all__ = [
    "EvaluationOutcome",
    "LargeEvaluationMetrics",
    "LargeEvaluationRun",
    "OutcomeJournal",
    "OutcomeStatus",
    "ReproducibilityReport",
    "compare_large_reproducibility",
    "evaluate_large_baseline",
    "load_evaluation_cases",
]
