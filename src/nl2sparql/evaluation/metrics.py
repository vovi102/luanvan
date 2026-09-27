"""Pure deterministic statistics for NL2SQL evaluation."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from itertools import combinations

from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CanonicalPredictionRun,
    ConfidenceInterval,
    DistributionMetric,
    EvaluationError,
    MetricDelta,
    PredictionCase,
    RatioMetric,
)
from nl2sparql.evaluation.sql_semantics import analyze_sql


def _validated(values: Sequence[float], *, rates: bool = False) -> tuple[float, ...]:
    converted = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in converted):
        raise EvaluationError("metric inputs must be finite")
    if rates and any(value < 0 or value > 1 for value in converted):
        raise EvaluationError("rate observations must be between zero and one")
    return converted


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise EvaluationError("cannot calculate a quantile from empty values")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return float(sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction)


def _confidence_interval(values: Sequence[float], policy: BootstrapPolicy) -> ConfidenceInterval:
    ordered = sorted(values)
    alpha = (1 - policy.confidence_level) / 2
    return ConfidenceInterval(
        lower=_quantile(ordered, alpha),
        upper=_quantile(ordered, 1 - alpha),
        confidence_level=policy.confidence_level,
    )


def _bootstrap_means(values: tuple[float, ...], policy: BootstrapPolicy) -> tuple[float, ...]:
    generator = random.Random(policy.seed)
    size = len(values)
    return tuple(
        sum(values[generator.randrange(size)] for _ in range(size)) / size
        for _ in range(policy.samples)
    )


def ratio_metric(scores: Sequence[float], policy: BootstrapPolicy) -> RatioMetric:
    """Build a full-denominator mean rate and deterministic bootstrap interval."""
    values = _validated(scores, rates=True)
    if not values:
        raise EvaluationError("ratio metric input cannot be empty")
    numerator = sum(values)
    return RatioMetric(
        numerator=numerator,
        denominator=len(values),
        value=numerator / len(values),
        interval=_confidence_interval(_bootstrap_means(values, policy), policy),
    )


def distribution_metric(
    values: Sequence[float | None], expected_count: int, policy: BootstrapPolicy
) -> DistributionMetric:
    """Summarize observed values while retaining expected and missing counts."""
    if expected_count < 0 or len(values) != expected_count:
        raise EvaluationError("distribution values must match expected_count")
    observed = _validated(tuple(value for value in values if value is not None))
    if any(value < 0 for value in observed):
        raise EvaluationError("distribution observations must be non-negative")
    missing = expected_count - len(observed)
    if not observed:
        return DistributionMetric(
            expected_count=expected_count,
            observed_count=0,
            missing_count=missing,
            p50=None,
            p95=None,
            p99=None,
            p50_interval=None,
            p95_interval=None,
            p99_interval=None,
        )

    ordered = sorted(observed)
    generator = random.Random(policy.seed)
    bootstrap_quantiles: dict[float, list[float]] = {0.5: [], 0.95: [], 0.99: []}
    for _ in range(policy.samples):
        sample = sorted(observed[generator.randrange(len(observed))] for _ in observed)
        for probability in bootstrap_quantiles:
            bootstrap_quantiles[probability].append(_quantile(sample, probability))
    return DistributionMetric(
        expected_count=expected_count,
        observed_count=len(observed),
        missing_count=missing,
        p50=_quantile(ordered, 0.5),
        p95=_quantile(ordered, 0.95),
        p99=_quantile(ordered, 0.99),
        p50_interval=_confidence_interval(bootstrap_quantiles[0.5], policy),
        p95_interval=_confidence_interval(bootstrap_quantiles[0.95], policy),
        p99_interval=_confidence_interval(bootstrap_quantiles[0.99], policy),
    )


def _run_identity(run: CanonicalPredictionRun) -> tuple[object, ...]:
    return (
        run.baseline_id,
        run.seed,
        run.test_set_sha256,
        run.test_case_count,
        run.provenance.fingerprints,
        run.adapter_id,
        run.adapter_schema_version,
        tuple(case.case_id for case in run.cases),
    )


def _observation(case: PredictionCase, normalized_sql: bool) -> str:
    if case.prediction_status != "ok":
        return f"failure:{case.prediction_status}:{case.error_code or ''}"
    if normalized_sql:
        assert case.predicted_sql is not None
        return f"sql:{analyze_sql(case.predicted_sql).canonical_sql}"
    return f"raw:{case.raw_output_sha256 or ''}"


def reproducibility_metric(
    runs: Sequence[CanonicalPredictionRun],
    *,
    normalized_sql: bool,
    policy: BootstrapPolicy,
) -> RatioMetric:
    """Measure per-case agreement across every compatible pair of runs."""
    if len(runs) < 2:
        raise EvaluationError("reproducibility requires at least two runs")
    if len({run.run_id for run in runs}) != len(runs):
        raise EvaluationError("reproducibility run IDs must be distinct")
    identity = _run_identity(runs[0])
    if any(_run_identity(run) != identity for run in runs[1:]):
        raise EvaluationError("incompatible reproducibility run identity")

    scores: list[float] = []
    for left, right in combinations(runs, 2):
        scores.extend(
            float(
                _observation(left_case, normalized_sql) == _observation(right_case, normalized_sql)
            )
            for left_case, right_case in zip(left.cases, right.cases, strict=True)
        )
    return ratio_metric(scores, policy)


def paired_delta(
    left: Sequence[float], right: Sequence[float], policy: BootstrapPolicy
) -> MetricDelta:
    """Calculate a paired left-minus-right mean with shared-index bootstrap."""
    left_values = _validated(left)
    right_values = _validated(right)
    if not left_values or len(left_values) != len(right_values):
        raise EvaluationError("paired inputs must have equal non-zero lengths")
    differences = tuple(a - b for a, b in zip(left_values, right_values, strict=True))
    generator = random.Random(policy.seed)
    size = len(differences)
    bootstrap = tuple(
        sum(differences[generator.randrange(size)] for _ in range(size)) / size
        for _ in range(policy.samples)
    )
    left_value = sum(left_values) / size
    right_value = sum(right_values) / size
    return MetricDelta(
        metric="paired_mean",
        left_value=left_value,
        right_value=right_value,
        delta=left_value - right_value,
        interval=_confidence_interval(bootstrap, policy),
    )
