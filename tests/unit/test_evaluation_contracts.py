import math
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nl2sparql.evaluation.contracts import (
    ArtifactRef,
    BootstrapPolicy,
    CanonicalPredictionRun,
    ConfidenceInterval,
    CostEvidence,
    EvaluationError,
    EvaluationReport,
    ExecutionCaseEvidence,
    ExecutionEvidence,
    ExecutorProvenance,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    PrivacyReview,
    QueryExecution,
    Readiness,
    RunProvenance,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _privacy() -> PrivacyEvidence:
    return PrivacyEvidence(
        documentation_status="documented",
        data_egress="none",
        provider=None,
        policy_sha256=SHA_A,
        review_sha256=SHA_B,
    )


def _case(case_id: str = "q-001") -> PredictionCase:
    return PredictionCase(
        case_id=case_id,
        question="How many transfers were recorded?",
        gold_sql="SELECT COUNT(*) FROM `p.d.transfer_facts`",
        difficulty="easy",
        categories=("aggregation",),
        prediction_status="ok",
        predicted_sql="SELECT COUNT(*) FROM `p.d.transfer_facts`",
        raw_output_sha256=SHA_A,
        error_code=None,
        inference=InferenceEvidence(
            latency_ms=12.5,
            input_tokens=10,
            output_tokens=8,
            cost=CostEvidence(
                measurement_status="unmeasured",
                amount=None,
                currency=None,
                source=None,
            ),
        ),
        privacy=_privacy(),
    )


def _run(*cases: PredictionCase, count: int | None = None) -> CanonicalPredictionRun:
    return CanonicalPredictionRun(
        baseline_id="b0",
        run_id="run-001",
        seed=42,
        generated_at=NOW,
        test_set_sha256=SHA_A,
        test_case_count=len(cases) if count is None else count,
        provenance=RunProvenance(
            reviewed=True,
            live_verified=True,
            synthetic=False,
            fingerprints=(("catalog", SHA_B),),
        ),
        source_artifacts=(
            ArtifactRef(
                role="predictions",
                media_type="application/jsonl",
                sha256=SHA_B,
                schema_version=1,
            ),
        ),
        adapter_id="b0-v1",
        adapter_schema_version=1,
        cases=cases,
    )


def _query(status: str) -> QueryExecution:
    return QueryExecution(
        status=status,
        job_id="job-1" if status == "ok" else None,
        latency_ms=4.0 if status == "ok" else None,
        billed_bytes=0 if status == "ok" else None,
        cost=CostEvidence(
            measurement_status="observed" if status == "ok" else "unmeasured",
            amount=Decimal("0") if status == "ok" else None,
            currency="USD" if status == "ok" else None,
            source="bigquery-job" if status == "ok" else None,
        ),
        result=None,
        error_code=None if status == "ok" else "query_failed",
    )


def test_prediction_run_requires_unique_complete_ordered_cases() -> None:
    first = _case("q-001")
    second = _case("q-002")

    run = _run(first, second)

    assert tuple(case.case_id for case in run.cases) == ("q-001", "q-002")
    with pytest.raises(FrozenInstanceError):
        run.run_id = "changed"  # type: ignore[misc]
    with pytest.raises(EvaluationError, match="duplicate case_id"):
        _run(first, first)
    with pytest.raises(EvaluationError, match="test_case_count"):
        _run(first, count=2)


def test_non_ok_prediction_cannot_carry_sql() -> None:
    values = _case().__dict__ | {"prediction_status": "timeout"}
    with pytest.raises(EvaluationError, match="Only ok predictions"):
        PredictionCase(**values)

    values["predicted_sql"] = None
    timeout = PredictionCase(**values)
    assert timeout.error_code is None

    values["prediction_status"] = "invented"
    with pytest.raises(EvaluationError, match="prediction_status"):
        PredictionCase(**values)


def test_unmeasured_cost_requires_null_amount_and_observed_zero_is_explicit() -> None:
    with pytest.raises(EvaluationError, match="unmeasured cost"):
        CostEvidence(
            measurement_status="unmeasured",
            amount=Decimal("0"),
            currency="USD",
            source="assumption",
        )

    measured = CostEvidence(
        measurement_status="observed",
        amount=Decimal("0"),
        currency="USD",
        source="meter",
    )
    assert measured.amount == Decimal("0")


def test_execution_evidence_derives_invalid_status_from_gold_failure() -> None:
    evidence = ExecutionEvidence(
        execution_id="exec-1",
        prediction_run_sha256=SHA_A,
        policy_sha256=SHA_B,
        executor=ExecutorProvenance(kind="fake", identity="scripted", version="1", synthetic=True),
        journal_terminal_sha256=SHA_A,
        cases=(
            ExecutionCaseEvidence(
                case_id="q-001",
                gold=_query("error"),
                prediction=_query("ok"),
            ),
        ),
    )

    assert evidence.status == "invalid_gold_failure"


def test_bootstrap_defaults_are_10000_and_seed_42() -> None:
    policy = BootstrapPolicy()
    assert (policy.samples, policy.seed, policy.confidence_level) == (10_000, 42, 0.95)


def test_report_primary_run_is_explicit_and_replicates_are_distinct() -> None:
    report = EvaluationReport(
        baseline_id="b0",
        primary_run_id="run-primary",
        primary_prediction_sha256=SHA_A,
        primary_execution_sha256=SHA_B,
        replicate_pairs=(("run-replicate", SHA_B, SHA_A),),
        test_set_sha256=SHA_A,
        case_set_sha256=SHA_B,
        expected_case_count=1,
        represented_case_count=1,
        readiness=Readiness(implementation_blockers=(), scientific_blockers=("fake_executor",)),
        bootstrap=BootstrapPolicy(),
        cases=(),
        dimensions=(),
        breakdowns=(),
    )
    assert report.primary_run_id == "run-primary"

    values = report.__dict__ | {"replicate_pairs": (("run-primary", SHA_B, SHA_A),)}
    with pytest.raises(EvaluationError, match="primary run"):
        EvaluationReport(**values)


def test_hashes_floats_sorted_sets_and_privacy_review_are_strict() -> None:
    with pytest.raises(EvaluationError, match="sha256"):
        ArtifactRef("input", "application/json", "A" * 64, 1)
    with pytest.raises(EvaluationError, match="finite"):
        ConfidenceInterval(math.nan, 1.0, 0.95)
    with pytest.raises(EvaluationError, match="sorted unique"):
        PredictionCase(**(_case().__dict__ | {"categories": ("z", "a", "a")}))
    with pytest.raises(EvaluationError, match="sorted unique"):
        Readiness((), ("z", "a"))

    review = PrivacyReview(
        baseline_id="b4",
        test_set_sha256=SHA_A,
        data_egress="provider",
        provider="gemini",
        policy_sha256=SHA_B,
        reviewer_id="reviewer-01",
        reviewed_at=NOW,
        synthetic=False,
    )
    assert review.provider == "gemini"

    with pytest.raises(EvaluationError, match="provider"):
        PrivacyReview(**(review.__dict__ | {"provider": None}))
    with pytest.raises(EvaluationError, match="UTC"):
        PrivacyReview(**(review.__dict__ | {"reviewed_at": datetime(2026, 9, 26)}))
