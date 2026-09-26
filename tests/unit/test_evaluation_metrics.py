import math
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nl2sparql.evaluation.contracts import (
    ArtifactRef,
    BootstrapPolicy,
    CanonicalPredictionRun,
    CostEvidence,
    EvaluationError,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    RunProvenance,
)
from nl2sparql.evaluation.metrics import (
    distribution_metric,
    paired_delta,
    ratio_metric,
    reproducibility_metric,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
POLICY = BootstrapPolicy()


def _case(case_id: str, sql: str | None, status: str = "ok") -> PredictionCase:
    return PredictionCase(
        case_id=case_id,
        question=f"Question {case_id}",
        gold_sql="SELECT 1 FROM `p.d.t`",
        difficulty="easy",
        categories=("simple",),
        prediction_status=status,
        predicted_sql=sql,
        raw_output_sha256=SHA_A if sql else None,
        error_code=status if status != "ok" else None,
        inference=InferenceEvidence(None, None, None, CostEvidence("unmeasured", None, None, None)),
        privacy=PrivacyEvidence("documented", "none", None, SHA_A, SHA_B),
    )


def _run(run_id: str, cases: tuple[PredictionCase, ...]) -> CanonicalPredictionRun:
    return CanonicalPredictionRun(
        baseline_id="b0",
        run_id=run_id,
        seed=42,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        test_set_sha256=SHA_A,
        test_case_count=len(cases),
        provenance=RunProvenance(True, True, False, (("config", SHA_B),)),
        source_artifacts=(ArtifactRef("prediction", "application/jsonl", SHA_B, 1),),
        adapter_id="b0-v1",
        adapter_schema_version=1,
        cases=cases,
    )


def test_ratio_uses_full_denominator_and_seeded_interval() -> None:
    first = ratio_metric([1, 0, 1, 0], POLICY)
    second = ratio_metric([1, 0, 1, 0], POLICY)

    assert (first.numerator, first.denominator, first.value) == (2.0, 4, 0.5)
    assert first.interval == second.interval
    assert ratio_metric([1, 1, 1], POLICY).interval.lower == 1.0
    assert ratio_metric([1, 1, 1], POLICY).interval.upper == 1.0
    with pytest.raises(EvaluationError, match="empty"):
        ratio_metric([], POLICY)


def test_distribution_reports_missing_counts_and_interpolated_quantiles() -> None:
    metric = distribution_metric([0.0, 10.0, None, 20.0, 30.0], 5, POLICY)

    assert (metric.expected_count, metric.observed_count, metric.missing_count) == (5, 4, 1)
    assert metric.p50 == 15.0
    assert math.isclose(metric.p95, 28.5)
    assert math.isclose(metric.p99, 29.7)
    assert metric.p50_interval is not None


def test_paired_delta_is_left_minus_right_and_uses_shared_indices() -> None:
    delta = paired_delta([1, 0, 1, 0], [0, 0, 1, 1], POLICY)
    repeat = paired_delta([1, 0, 1, 0], [0, 0, 1, 1], POLICY)

    assert (delta.left_value, delta.right_value, delta.delta) == (0.5, 0.5, 0.0)
    assert delta.interval == repeat.interval
    with pytest.raises(EvaluationError, match="equal non-zero"):
        paired_delta([1], [], POLICY)


def test_reproducibility_uses_all_run_pairs_and_failure_observations() -> None:
    run1 = _run("r1", (_case("q1", "SELECT 1 FROM `p.d.t`"), _case("q2", None, "timeout")))
    run2 = _run("r2", (_case("q1", "select 1 from `p.d.t`"), _case("q2", None, "timeout")))
    run3 = _run(
        "r3",
        (_case("q1", "SELECT 2 FROM `p.d.t`"), _case("q2", None, "generation_error")),
    )

    metric = reproducibility_metric((run1, run2, run3), normalized_sql=True, policy=POLICY)

    assert metric.denominator == 6  # N * k * (k - 1) / 2
    assert metric.numerator == 2.0  # r1/r2 agree on SQL and the timeout observation


def test_reproducibility_rejects_incompatible_identity_or_case_order() -> None:
    cases = (_case("q1", "SELECT 1 FROM `p.d.t`"), _case("q2", None, "timeout"))
    left = _run("r1", cases)
    wrong_test = replace(_run("r2", cases), test_set_sha256=SHA_B)
    wrong_cases = _run("r3", tuple(reversed(cases)))
    wrong_config = replace(
        _run("r4", cases),
        provenance=RunProvenance(True, True, False, (("config", SHA_A),)),
    )

    for incompatible in (wrong_test, wrong_cases, wrong_config):
        with pytest.raises(EvaluationError, match="incompatible"):
            reproducibility_metric((left, incompatible), normalized_sql=True, policy=POLICY)
