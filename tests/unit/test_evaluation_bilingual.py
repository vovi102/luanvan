import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.evaluation.artifacts import (
    canonical_json,
    load_bilingual_evaluation_report,
    load_gate_decision,
    serialize_bilingual_evaluation_report,
    serialize_gate_decision,
)
from nl2sparql.evaluation.bilingual import compare_language_pairs, evaluate_bilingual_gates
from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CaseEvaluation,
    CostEvidence,
    EvaluationError,
    EvaluationReport,
    GateDecision,
    GateObservation,
    GatePolicy,
    MetricDelta,
    Readiness,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
POLICY = BootstrapPolicy(samples=200, seed=42)
PAIR_IDS = tuple(f"pair-{index:03d}" for index in range(1, 101))
GOLD_HASHES = tuple(
    (pair_id, hashlib.sha256(f"gold-{pair_id}".encode()).hexdigest()) for pair_id in PAIR_IDS
)


def _case(pair_id: str, *, success: bool, latency_ms: float) -> CaseEvaluation:
    return CaseEvaluation(
        case_id=pair_id,
        difficulty="easy",
        categories=("paired",),
        exact_match=success,
        structural_match=success,
        execution_match=success,
        answer_scores=None,
        inference_latency_ms=latency_ms,
        execution_latency_ms=1.0,
        inference_cost=CostEvidence("unmeasured", None, None, None),
        execution_cost=CostEvidence("unmeasured", None, None, None),
        failure_tags=() if success else ("no_output",),
    )


def _report(
    baseline_id: str,
    successful: set[int],
    *,
    latency_ms: float,
) -> EvaluationReport:
    cases = tuple(
        _case(pair_id, success=index in successful, latency_ms=latency_ms)
        for index, pair_id in enumerate(PAIR_IDS)
    )
    return EvaluationReport(
        baseline_id=baseline_id,
        primary_run_id=f"run-{baseline_id}",
        primary_prediction_sha256=hashlib.sha256(f"prediction-{baseline_id}".encode()).hexdigest(),
        primary_execution_sha256=hashlib.sha256(f"execution-{baseline_id}".encode()).hexdigest(),
        replicate_pairs=(),
        test_set_sha256=SHA_A,
        case_set_sha256=SHA_B,
        expected_case_count=100,
        represented_case_count=100,
        readiness=Readiness((), ()),
        bootstrap=POLICY,
        cases=cases,
        dimensions=(("gold_sql_sha256s", GOLD_HASHES),),
        breakdowns=(),
    )


def _reports() -> dict[str, EvaluationReport]:
    return {
        "english_reference": _report("english-only", set(range(95)), latency_ms=10.0),
        "english": _report("direct-en", set(range(94)), latency_ms=12.0),
        "vietnamese": _report("direct-vi", set(range(90)), latency_ms=14.0),
        "vietnamese_unaccented": _report("direct-vi-unaccented", set(range(85)), latency_ms=15.0),
        "translation": _report("translation-first", set(range(88)), latency_ms=30.0),
    }


def test_compare_language_pairs_reports_seeded_gaps_mcnemar_failures_and_latency() -> None:
    reports = _reports()

    first = compare_language_pairs(
        **reports,
        reviewed_count=100,
        live_verified_count=100,
        bootstrap_policy=POLICY,
    )
    second = compare_language_pairs(
        **reports,
        reviewed_count=100,
        live_verified_count=100,
        bootstrap_policy=POLICY,
    )

    assert first.pair_ids == PAIR_IDS
    assert first.english_regression.delta == pytest.approx(0.01)
    assert first.language_gap.delta == pytest.approx(0.04)
    assert first.accent_gap.delta == pytest.approx(0.05)
    assert first.language_gap.interval == second.language_gap.interval

    mcnemar = dict(first.mcnemar)["english_vs_vietnamese"]
    assert (mcnemar.left_only, mcnemar.right_only, mcnemar.exact_p_value) == (4, 0, 0.125)

    failure_modes = dict(first.failure_modes)
    assert dict(failure_modes["english"].counts)["no_output"] == 6
    assert dict(failure_modes["english"].counts)["unsafe_sql"] == 0
    assert dict(failure_modes["translation"].counts)["no_output"] == 12
    assert tuple(failure_modes) == (
        "english_reference",
        "english",
        "vietnamese",
        "vietnamese_unaccented",
        "translation",
    )
    assert all(summary.missing_count == 0 for summary in failure_modes.values())

    translation_latency = dict(first.inference_latency_ms)["translation"]
    assert translation_latency.p50 == 30.0
    assert translation_latency.expected_count == 100


@pytest.mark.parametrize(
    "mutation, message",
    [
        (
            lambda reports: (
                reports
                | {
                    "vietnamese": replace(
                        reports["vietnamese"],
                        cases=tuple(reversed(reports["vietnamese"].cases)),
                    )
                }
            ),
            "ordered pair IDs",
        ),
        (
            lambda reports: (
                reports
                | {
                    "vietnamese": replace(
                        reports["vietnamese"],
                        cases=(reports["vietnamese"].cases[0],) + reports["vietnamese"].cases[:-1],
                    )
                }
            ),
            "unique pair IDs",
        ),
        (
            lambda reports: (
                reports
                | {
                    "vietnamese": replace(
                        reports["vietnamese"], cases=reports["vietnamese"].cases[:-1]
                    )
                }
            ),
            "exactly 100",
        ),
        (
            lambda reports: (
                reports | {"vietnamese": replace(reports["vietnamese"], test_set_sha256="c" * 64)}
            ),
            "test-set",
        ),
        (
            lambda reports: (
                reports
                | {
                    "vietnamese": replace(
                        reports["vietnamese"],
                        dimensions=(
                            (
                                "gold_sql_sha256s",
                                GOLD_HASHES[:-1] + ((PAIR_IDS[-1], "c" * 64),),
                            ),
                        ),
                    )
                }
            ),
            "gold SQL",
        ),
    ],
)
def test_compare_language_pairs_rejects_incompatible_pair_evidence(
    mutation: object,
    message: str,
) -> None:
    reports = mutation(_reports())  # type: ignore[operator]

    with pytest.raises(EvaluationError, match=message):
        compare_language_pairs(
            **reports,
            reviewed_count=100,
            live_verified_count=100,
            bootstrap_policy=POLICY,
        )


def test_missing_execution_remains_a_zero_success_observation() -> None:
    reports = _reports()
    first = reports["vietnamese"].cases[0]
    reports["vietnamese"] = replace(
        reports["vietnamese"],
        cases=(replace(first, execution_match=None, failure_tags=()),)
        + reports["vietnamese"].cases[1:],
    )

    result = compare_language_pairs(
        **reports,
        reviewed_count=100,
        live_verified_count=100,
        bootstrap_policy=POLICY,
    )

    assert dict(result.accuracies)["vietnamese"].numerator == 89
    assert dict(dict(result.failure_modes)["vietnamese"].counts)["missing_execution"] == 1


def _bilingual_report():
    return compare_language_pairs(
        **_reports(),
        reviewed_count=100,
        live_verified_count=100,
        bootstrap_policy=POLICY,
    )


def _delta(name: str, value: float, original: MetricDelta) -> MetricDelta:
    return MetricDelta(name, value, 0.0, value, original.interval)


def test_gate_thresholds_are_inclusive_and_decision_binds_every_observation() -> None:
    report = _bilingual_report()
    report = replace(
        report,
        english_regression=_delta("english_regression", 0.02, report.english_regression),
        language_gap=_delta("language_gap", 0.10, report.language_gap),
        accent_gap=_delta("accent_gap", 0.10, report.accent_gap),
    )

    decision = evaluate_bilingual_gates(report, GatePolicy())

    assert decision.passed is True
    assert decision.failed_gates == ()
    observations = {item.name: item for item in decision.observations}
    assert observations["english_regression"].observed == 0.02
    assert observations["english_regression"].threshold == 0.02
    assert observations["reviewed_count"].observed == 100.0
    assert observations["live_verified_count"].observed == 100.0
    assert observations["interval_completeness"].passed is True
    assert observations["failure_count_completeness"].passed is True
    assert decision.bilingual_report_sha256
    assert decision.policy_sha256 == GatePolicy().sha256


@pytest.mark.parametrize(
    ("mutation", "failed_gate"),
    [
        (
            lambda report: replace(
                report,
                english_regression=_delta(
                    "english_regression",
                    math.nextafter(0.02 + GatePolicy().tolerance, math.inf),
                    report.english_regression,
                ),
            ),
            "english_regression",
        ),
        (
            lambda report: replace(
                report,
                language_gap=_delta(
                    "language_gap",
                    math.nextafter(0.10 + GatePolicy().tolerance, math.inf),
                    report.language_gap,
                ),
            ),
            "language_gap",
        ),
        (
            lambda report: replace(
                report,
                accent_gap=_delta(
                    "accent_gap",
                    math.nextafter(0.10 + GatePolicy().tolerance, math.inf),
                    report.accent_gap,
                ),
            ),
            "accent_gap",
        ),
        (lambda report: replace(report, reviewed_count=99), "reviewed_count"),
        (lambda report: replace(report, live_verified_count=99), "live_verified_count"),
        (
            lambda report: replace(
                report,
                accuracies=(
                    (report.accuracies[0][0], replace(report.accuracies[0][1], interval=None)),
                    *report.accuracies[1:],
                ),
            ),
            "interval_completeness",
        ),
        (
            lambda report: replace(
                report,
                failure_modes=(
                    (
                        report.failure_modes[0][0],
                        replace(
                            report.failure_modes[0][1],
                            represented_count=99,
                            missing_count=1,
                        ),
                    ),
                    *report.failure_modes[1:],
                ),
            ),
            "failure_count_completeness",
        ),
    ],
)
def test_each_preregistered_gate_fails_without_filtering_the_report(
    mutation: object,
    failed_gate: str,
) -> None:
    report = mutation(_bilingual_report())  # type: ignore[operator]

    decision = evaluate_bilingual_gates(report, GatePolicy())

    assert decision.passed is False
    assert failed_gate in decision.failed_gates
    assert report.pair_ids == PAIR_IDS
    assert len(report.accuracies) == 5


def test_bilingual_report_and_gate_decision_round_trip_and_reject_tampering(
    tmp_path: Path,
) -> None:
    report = _bilingual_report()
    decision = evaluate_bilingual_gates(report, GatePolicy())
    report_path = tmp_path / "bilingual-report.json"
    decision_path = tmp_path / "gate-decision.json"
    report_path.write_bytes(serialize_bilingual_evaluation_report(report))
    decision_path.write_bytes(serialize_gate_decision(decision))

    assert load_bilingual_evaluation_report(report_path) == report
    assert load_gate_decision(decision_path) == decision

    document = json.loads(decision_path.read_bytes())
    document["body"]["passed"] = not document["body"]["passed"]
    decision_path.write_bytes(canonical_json(document))
    with pytest.raises(EvaluationError, match="self-hash"):
        load_gate_decision(decision_path)


def test_gate_contract_rejects_forged_results_and_incomplete_observation_sets() -> None:
    with pytest.raises(EvaluationError, match="computed result"):
        GateObservation("english_regression", 0.03, 0.02, "max", True, 1e-12)

    decision = evaluate_bilingual_gates(_bilingual_report(), GatePolicy())
    with pytest.raises(EvaluationError, match="registered observations"):
        GateDecision(
            decision.bilingual_report_sha256,
            decision.frozen_input_sha256,
            decision.policy_sha256,
            decision.observations[:-1],
            True,
            (),
        )
