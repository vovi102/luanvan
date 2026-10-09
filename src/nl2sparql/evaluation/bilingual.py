"""Strict paired bilingual comparisons over frozen canonical reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

from nl2sparql.evaluation.artifacts import (
    canonical_json,
    serialize_bilingual_evaluation_report,
    serialize_evaluation_report,
)
from nl2sparql.evaluation.contracts import (
    BilingualEvaluationReport,
    BootstrapPolicy,
    EvaluationError,
    EvaluationReport,
    FailureModeSummary,
    GateDecision,
    GateObservation,
    GatePolicy,
    MetricDelta,
)
from nl2sparql.evaluation.failures import FAILURE_MODE_TAGS
from nl2sparql.evaluation.metrics import (
    distribution_metric,
    mcnemar_exact,
    paired_delta,
    ratio_metric,
)

_DEFAULT_BOOTSTRAP_POLICY = BootstrapPolicy()

_SLICE_NAMES = (
    "english_reference",
    "english",
    "vietnamese",
    "vietnamese_unaccented",
    "translation",
)


def _artifact_sha(report: EvaluationReport) -> str:
    value = json.loads(serialize_evaluation_report(report)).get("artifact_sha256")
    if not isinstance(value, str):
        raise EvaluationError("canonical evaluation report is missing its self-hash")
    return value


def _pair_ids(report: EvaluationReport) -> tuple[str, ...]:
    return tuple(case.case_id for case in report.cases)


def _gold_hashes(report: EvaluationReport) -> tuple[tuple[str, str], ...]:
    names = tuple(name for name, _ in report.dimensions)
    if len(names) != len(set(names)):
        raise EvaluationError("evaluation report dimension names must be unique")
    value = dict(report.dimensions).get("gold_sql_sha256s")
    if not isinstance(value, tuple) or len(value) != 100:
        raise EvaluationError("bilingual report requires complete gold SQL hashes")
    output: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise EvaluationError("bilingual report gold SQL hash evidence is invalid")
        output.append((item[0], item[1]))
    return tuple(output)


def _validate_reports(reports: Sequence[EvaluationReport]) -> tuple[str, ...]:
    first = reports[0]
    ids = _pair_ids(first)
    if len(ids) != 100 or any(
        report.expected_case_count != 100
        or report.represented_case_count != 100
        or len(report.cases) != 100
        for report in reports
    ):
        raise EvaluationError("bilingual comparison requires exactly 100 represented pairs")
    for report in reports:
        report_ids = _pair_ids(report)
        if len(set(report_ids)) != len(report_ids):
            raise EvaluationError("bilingual comparison requires unique pair IDs")
        if report_ids != ids:
            raise EvaluationError("bilingual comparison requires identical ordered pair IDs")
    if any(report.test_set_sha256 != first.test_set_sha256 for report in reports[1:]):
        raise EvaluationError("bilingual comparison requires compatible test-set hashes")
    if any(report.case_set_sha256 != first.case_set_sha256 for report in reports[1:]):
        raise EvaluationError("bilingual comparison requires compatible case-set hashes")
    gold = _gold_hashes(first)
    if tuple(pair_id for pair_id, _ in gold) != ids:
        raise EvaluationError("gold SQL hashes must follow ordered pair IDs")
    if any(_gold_hashes(report) != gold for report in reports[1:]):
        raise EvaluationError("bilingual comparison requires matching gold SQL hashes")
    return ids


def _scores(report: EvaluationReport) -> tuple[bool, ...]:
    return tuple(case.execution_match is True for case in report.cases)


def _delta(
    name: str,
    left: tuple[bool, ...],
    right: tuple[bool, ...],
    policy: BootstrapPolicy,
) -> MetricDelta:
    result = paired_delta(tuple(map(float, left)), tuple(map(float, right)), policy)
    return replace(result, metric=name)


def _failure_summary(report: EvaluationReport, vocabulary: tuple[str, ...]) -> FailureModeSummary:
    counts: Counter[str] = Counter()
    for case in report.cases:
        tags = set(case.failure_tags)
        if case.execution_match is None:
            tags.add("missing_execution")
        elif case.execution_match is False and not tags:
            tags.add("unclassified")
        counts.update(tags)
    return FailureModeSummary(
        expected_count=report.expected_case_count,
        represented_count=len(report.cases),
        missing_count=report.expected_case_count - len(report.cases),
        counts=tuple((name, counts[name]) for name in vocabulary),
    )


def _failure_vocabulary(reports: Sequence[EvaluationReport]) -> tuple[str, ...]:
    names = set(FAILURE_MODE_TAGS) | {
        tag for report in reports for case in report.cases for tag in case.failure_tags
    }
    if any(case.execution_match is None for report in reports for case in report.cases):
        names.add("missing_execution")
    if any(
        case.execution_match is False and not case.failure_tags
        for report in reports
        for case in report.cases
    ):
        names.add("unclassified")
    return tuple(sorted(names))


def compare_language_pairs(
    *,
    english_reference: EvaluationReport,
    english: EvaluationReport,
    vietnamese: EvaluationReport,
    vietnamese_unaccented: EvaluationReport,
    translation: EvaluationReport,
    reviewed_count: int,
    live_verified_count: int,
    bootstrap_policy: BootstrapPolicy = _DEFAULT_BOOTSTRAP_POLICY,
) -> BilingualEvaluationReport:
    """Build a denominator-preserving paired comparison from five frozen reports."""
    reports = (
        english_reference,
        english,
        vietnamese,
        vietnamese_unaccented,
        translation,
    )
    pair_ids = _validate_reports(reports)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (reviewed_count, live_verified_count)
    ):
        raise EvaluationError("reviewed and live-verified counts must be non-negative integers")

    score_sets = tuple(_scores(report) for report in reports)
    accuracies = tuple(
        (name, ratio_metric(tuple(map(float, scores)), bootstrap_policy))
        for name, scores in zip(_SLICE_NAMES, score_sets, strict=True)
    )
    english_regression = _delta(
        "english_regression", score_sets[0], score_sets[1], bootstrap_policy
    )
    language_gap = _delta("language_gap", score_sets[1], score_sets[2], bootstrap_policy)
    accent_gap = _delta("accent_gap", score_sets[2], score_sets[3], bootstrap_policy)
    mcnemar = (
        ("english_vs_vietnamese", mcnemar_exact(score_sets[1], score_sets[2])),
        ("vietnamese_vs_unaccented", mcnemar_exact(score_sets[2], score_sets[3])),
        ("vietnamese_vs_translation", mcnemar_exact(score_sets[2], score_sets[4])),
    )
    vocabulary = _failure_vocabulary(reports)
    failures = tuple(
        (name, _failure_summary(report, vocabulary))
        for name, report in zip(_SLICE_NAMES, reports, strict=True)
    )
    latencies = tuple(
        (
            name,
            distribution_metric(
                tuple(case.inference_latency_ms for case in report.cases),
                len(report.cases),
                bootstrap_policy,
            ),
        )
        for name, report in zip(_SLICE_NAMES, reports, strict=True)
    )
    report_hashes = tuple(_artifact_sha(report) for report in reports)
    frozen_input_sha256 = hashlib.sha256(
        canonical_json(
            {
                "report_sha256s": report_hashes,
                "pair_ids": pair_ids,
                "reviewed_count": reviewed_count,
                "live_verified_count": live_verified_count,
            }
        )
    ).hexdigest()
    return BilingualEvaluationReport(
        english_reference_report_sha256=report_hashes[0],
        english_report_sha256=report_hashes[1],
        vietnamese_report_sha256=report_hashes[2],
        vietnamese_unaccented_report_sha256=report_hashes[3],
        translation_report_sha256=report_hashes[4],
        frozen_input_sha256=frozen_input_sha256,
        test_set_sha256=english_reference.test_set_sha256,
        case_set_sha256=english_reference.case_set_sha256,
        pair_ids=pair_ids,
        reviewed_count=reviewed_count,
        live_verified_count=live_verified_count,
        accuracies=accuracies,
        english_regression=english_regression,
        language_gap=language_gap,
        accent_gap=accent_gap,
        mcnemar=mcnemar,
        failure_modes=failures,
        inference_latency_ms=latencies,
        synthetic=any(
            blocker in {"synthetic_input", "fake_executor"}
            for report in reports
            for blocker in report.readiness.scientific_blockers
        ),
        bootstrap=bootstrap_policy,
    )


def _gate_observation(
    name: str,
    observed: float,
    threshold: float,
    operator: str,
    *,
    tolerance: float,
) -> GateObservation:
    if operator == "max":
        passed = observed <= threshold + tolerance
        typed_operator = "max"
    elif operator == "exact":
        passed = observed == threshold
        typed_operator = "exact"
    else:  # pragma: no cover - private caller exhausts the registered operators.
        raise EvaluationError("unknown gate operator")
    return GateObservation(name, observed, threshold, typed_operator, passed, tolerance)


def evaluate_bilingual_gates(
    report: BilingualEvaluationReport,
    policy: GatePolicy,
) -> GateDecision:
    """Evaluate every pre-registered gate without changing the source report."""
    if not isinstance(report, BilingualEvaluationReport) or not isinstance(policy, GatePolicy):
        raise EvaluationError("bilingual gates require canonical report and policy contracts")
    interval_metrics = (
        *(metric for _, metric in report.accuracies),
        report.english_regression,
        report.language_gap,
        report.accent_gap,
    )
    interval_count = sum(metric.interval is not None for metric in interval_metrics)
    complete_failure_summaries = sum(
        summary.expected_count == policy.required_pair_count
        and summary.represented_count == policy.required_pair_count
        and summary.missing_count == 0
        for _, summary in report.failure_modes
    )
    observations = (
        _gate_observation(
            "english_regression",
            report.english_regression.delta,
            policy.english_regression_max,
            "max",
            tolerance=policy.tolerance,
        ),
        _gate_observation(
            "language_gap",
            report.language_gap.delta,
            policy.language_gap_max,
            "max",
            tolerance=policy.tolerance,
        ),
        _gate_observation(
            "accent_gap",
            report.accent_gap.delta,
            policy.accent_gap_max,
            "max",
            tolerance=policy.tolerance,
        ),
        _gate_observation(
            "reviewed_count",
            float(report.reviewed_count),
            float(policy.required_pair_count),
            "exact",
            tolerance=policy.tolerance,
        ),
        _gate_observation(
            "live_verified_count",
            float(report.live_verified_count),
            float(policy.required_pair_count),
            "exact",
            tolerance=policy.tolerance,
        ),
        _gate_observation(
            "interval_completeness",
            float(interval_count),
            float(len(interval_metrics)),
            "exact",
            tolerance=policy.tolerance,
        ),
        _gate_observation(
            "failure_count_completeness",
            float(complete_failure_summaries),
            float(len(report.failure_modes)),
            "exact",
            tolerance=policy.tolerance,
        ),
    )
    document = json.loads(serialize_bilingual_evaluation_report(report))
    report_sha256 = document.get("artifact_sha256")
    if not isinstance(report_sha256, str):
        raise EvaluationError("canonical bilingual report is missing its self-hash")
    failed = tuple(sorted(item.name for item in observations if not item.passed))
    return GateDecision(
        bilingual_report_sha256=report_sha256,
        frozen_input_sha256=report.frozen_input_sha256,
        policy_sha256=policy.sha256,
        observations=observations,
        passed=not failed,
        failed_gates=failed,
    )
