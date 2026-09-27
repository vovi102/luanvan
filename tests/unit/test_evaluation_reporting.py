import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nl2sparql.evaluation.artifacts import (
    load_comparison_report,
    load_evaluation_report,
    serialize_comparison_report,
    serialize_evaluation_report,
    serialize_prediction_run,
)
from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CanonicalPredictionRun,
    CostEvidence,
    EvaluationError,
    ExecutionCaseEvidence,
    ExecutionEvidence,
    ExecutorProvenance,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    QueryExecution,
    ResultField,
    RunProvenance,
)
from nl2sparql.evaluation.reporting import build_report, compare_reports
from nl2sparql.evaluation.result_semantics import canonicalize_result

SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = datetime(2026, 9, 26, tzinfo=UTC)
POLICY = BootstrapPolicy(samples=100, seed=42)
GOLD = "SELECT value FROM `project.dataset.table`"


def _result(values: list[str]):
    return canonicalize_result(
        [(value,) for value in values],
        (ResultField("value", "STRING"),),
        order_sensitive=False,
    )


def _query(values: list[str], *, latency: float = 2.0) -> QueryExecution:
    return QueryExecution(
        "ok",
        "job",
        latency,
        10,
        CostEvidence("estimated", Decimal("0.01"), "USD", "policy"),
        _result(values),
        None,
        processed_bytes=10,
        cache_hit=False,
    )


def _run(run_id: str = "run-1", *, synthetic: bool = False) -> CanonicalPredictionRun:
    predictions = (
        ("ok", GOLD),
        ("ok", "SELECT value FROM `project.dataset.table` WHERE value = 'x'"),
        ("no_output", None),
        ("ok", GOLD),
    )
    cases = tuple(
        PredictionCase(
            case_id=f"q{index}",
            question=f"Question {index}",
            gold_sql=GOLD,
            difficulty=("easy", "easy", "medium", "hard")[index - 1],
            categories=("shared",) if index == 1 else ("shared", f"type-{index}"),
            prediction_status=status,
            predicted_sql=sql,
            raw_output_sha256=SHA_A if status == "ok" else None,
            error_code=None if status == "ok" else status,
            inference=InferenceEvidence(
                float(index),
                1,
                1,
                CostEvidence("observed", Decimal("0.001"), "USD", "provider"),
            ),
            privacy=PrivacyEvidence("documented", "none", None, SHA_A, SHA_B),
        )
        for index, (status, sql) in enumerate(predictions, start=1)
    )
    return CanonicalPredictionRun(
        "b0",
        run_id,
        42,
        NOW,
        SHA_A,
        4,
        RunProvenance(True, True, synthetic, (("model", "model-v1"),)),
        (),
        "test",
        1,
        cases,
    )


def _artifact_sha(payload: bytes) -> str:
    return str(json.loads(payload)["artifact_sha256"])


def _evidence(run: CanonicalPredictionRun, *, fake: bool = False) -> ExecutionEvidence:
    pairs = (
        (_query(["a"]), _query(["a"])),
        (_query(["a", "b"]), _query(["a", "c"])),
        (
            _query(["a"]),
            QueryExecution(
                "skipped_no_output",
                None,
                None,
                None,
                CostEvidence("unmeasured", None, None, None),
                None,
                "skipped_no_output",
            ),
        ),
        (_query([]), _query([])),
    )
    return ExecutionEvidence(
        f"exec-{run.run_id}",
        _artifact_sha(serialize_prediction_run(run)),
        SHA_B,
        ExecutorProvenance("fake" if fake else "bigquery", "test", "1", fake),
        SHA_A,
        tuple(
            ExecutionCaseEvidence(case.case_id, gold, prediction)
            for case, (gold, prediction) in zip(run.cases, pairs, strict=True)
        ),
    )


def _dimensions(report):
    return dict(report.dimensions)


def test_primary_metrics_keep_full_denominator_and_overlapping_breakdowns() -> None:
    run = _run()
    report = build_report(
        primary_run=run,
        primary_evidence=_evidence(run),
        bootstrap_policy=POLICY,
    )
    dimensions = _dimensions(report)

    assert dimensions["exact_match"].numerator == 2
    assert dimensions["structural_match"].numerator == 2
    assert dimensions["execution_accuracy"].numerator == 2
    assert dimensions["answer_f1"].numerator == 2.5
    assert dimensions["answer_f1"].denominator == 4
    assert dimensions["inference_latency_ms"].missing_count == 0
    assert dimensions["prediction_execution_latency_ms"].missing_count == 1
    assert dimensions["inference_cost_usd"].observed_count == 4
    assert dimensions["execution_cost_usd"].observed_count == 3
    assert dimensions["failure_rates"]
    breakdowns = dict(report.breakdowns)
    assert dict(breakdowns["difficulty"])["easy"]["case_count"] == 2
    assert dict(breakdowns["category"])["shared"]["case_count"] == 4


def test_any_gold_failure_invalidates_execution_and_answer_without_dropping_cases() -> None:
    run = _run()
    evidence = _evidence(run)
    bad_gold = replace(evidence.cases[1].gold, status="error", job_id=None, result=None)
    evidence = replace(
        evidence,
        cases=(evidence.cases[0], replace(evidence.cases[1], gold=bad_gold), *evidence.cases[2:]),
    )

    report = build_report(
        primary_run=run,
        primary_evidence=evidence,
        bootstrap_policy=POLICY,
    )

    assert len(report.cases) == 4
    assert _dimensions(report)["execution_accuracy"].numerator is None
    assert _dimensions(report)["execution_accuracy"].value is None
    assert _dimensions(report)["answer_f1"].numerator is None
    assert "gold_execution_failure" in report.readiness.scientific_blockers


def test_replicates_never_change_primary_headlines_and_three_genuine_runs_are_ready() -> None:
    primary = _run("primary")
    r2 = _run("replicate-2")
    r3 = _run("replicate-3")
    first = build_report(
        primary_run=primary,
        primary_evidence=_evidence(primary),
        replicate_pairs=((r2, _evidence(r2)), (r3, _evidence(r3))),
        bootstrap_policy=POLICY,
    )
    reversed_report = build_report(
        primary_run=primary,
        primary_evidence=_evidence(primary),
        replicate_pairs=((r3, _evidence(r3)), (r2, _evidence(r2))),
        bootstrap_policy=POLICY,
    )

    assert first.primary_run_id == "primary"
    assert _dimensions(first)["exact_match"] == _dimensions(reversed_report)["exact_match"]
    assert first.replicate_pairs == reversed_report.replicate_pairs
    assert "missing_genuine_baseline_runs" not in first.readiness.scientific_blockers
    assert first.readiness.scientific_status == "ready"


def test_report_rejects_execution_binding_and_replicate_identity_mismatches() -> None:
    run = _run()
    with pytest.raises(EvaluationError, match="prediction binding"):
        build_report(
            primary_run=run,
            primary_evidence=replace(_evidence(run), prediction_run_sha256=SHA_B),
            bootstrap_policy=POLICY,
        )
    wrong = replace(_run("r2"), baseline_id="b1")
    with pytest.raises(EvaluationError, match="replicate identity"):
        build_report(
            primary_run=run,
            primary_evidence=_evidence(run),
            replicate_pairs=((wrong, _evidence(wrong)),),
            bootstrap_policy=POLICY,
        )


def test_comparison_is_paired_left_minus_right_and_marks_incomplete_measures() -> None:
    left_run = _run("left")
    right_run = replace(_run("right"), baseline_id="b1")
    left = build_report(
        primary_run=left_run,
        primary_evidence=_evidence(left_run),
        bootstrap_policy=POLICY,
    )
    right_evidence = _evidence(right_run)
    right_evidence = replace(
        right_evidence,
        cases=tuple(
            replace(pair, prediction=_query(["wrong"])) for pair in right_evidence.cases
        ),
    )
    right = build_report(
        primary_run=right_run,
        primary_evidence=right_evidence,
        bootstrap_policy=POLICY,
    )

    comparison = compare_reports(left, right, bootstrap_policy=POLICY)
    deltas = {delta.metric: delta for delta in comparison.deltas}

    assert deltas["execution_accuracy"].delta > 0
    assert deltas["answer_f1"].delta > 0
    assert "prediction_execution_latency_ms" not in deltas
    assert "incomplete_paired_prediction_execution_latency_ms" in (
        comparison.readiness.scientific_blockers
    )


def test_synthetic_fake_and_missing_privacy_blockers_are_derived_and_sorted() -> None:
    run = _run(synthetic=True)
    first = run.cases[0]
    run = replace(
        run,
        cases=(
            replace(
                first,
                privacy=PrivacyEvidence("undocumented", "unknown", None, None, None),
            ),
            *run.cases[1:],
        ),
    )
    report = build_report(
        primary_run=run,
        primary_evidence=_evidence(run, fake=True),
        bootstrap_policy=POLICY,
    )

    blockers = report.readiness.scientific_blockers
    assert blockers == tuple(sorted(blockers))
    assert {"synthetic_input", "fake_executor", "missing_privacy_evidence"} <= set(blockers)


def test_report_and_comparison_round_trip_with_typed_dimension_values(tmp_path: Path) -> None:
    left_run = _run("left")
    right_run = replace(_run("right"), baseline_id="b1")
    left = build_report(
        primary_run=left_run,
        primary_evidence=_evidence(left_run),
        bootstrap_policy=POLICY,
    )
    right = build_report(
        primary_run=right_run,
        primary_evidence=_evidence(right_run),
        bootstrap_policy=POLICY,
    )
    comparison = compare_reports(left, right, bootstrap_policy=POLICY)
    report_path = tmp_path / "report.json"
    comparison_path = tmp_path / "comparison.json"
    report_path.write_bytes(serialize_evaluation_report(left))
    comparison_path.write_bytes(serialize_comparison_report(comparison))

    assert load_evaluation_report(report_path) == left
    assert load_comparison_report(comparison_path) == comparison
