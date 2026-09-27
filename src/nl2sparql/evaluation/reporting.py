"""Pure, deterministic offline evaluation reports and paired comparisons."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import replace

from nl2sparql.evaluation.artifacts import (
    canonical_json,
    serialize_evaluation_report,
    serialize_execution_evidence,
    serialize_prediction_run,
)
from nl2sparql.evaluation.contracts import (
    AnswerScores,
    BootstrapPolicy,
    CanonicalPredictionRun,
    CaseEvaluation,
    ComparisonReport,
    CostEvidence,
    DistributionMetric,
    EvaluationError,
    EvaluationReport,
    ExecutionEvidence,
    ManualFailureReview,
    MetricDelta,
    RatioMetric,
    Readiness,
)
from nl2sparql.evaluation.failures import classify_failure
from nl2sparql.evaluation.metrics import (
    distribution_metric,
    paired_delta,
    ratio_metric,
    reproducibility_metric,
)
from nl2sparql.evaluation.result_semantics import answer_scores, results_equal
from nl2sparql.evaluation.sql_semantics import exact_match, structural_match

DEFAULT_BOOTSTRAP_POLICY = BootstrapPolicy()


def _artifact_sha(payload: bytes) -> str:
    document = json.loads(payload)
    digest = document.get("artifact_sha256")
    if not isinstance(digest, str):
        raise EvaluationError("canonical artifact is missing its self-hash")
    return digest


def _prediction_sha(run: CanonicalPredictionRun) -> str:
    return _artifact_sha(serialize_prediction_run(run))


def _execution_sha(evidence: ExecutionEvidence) -> str:
    return _artifact_sha(serialize_execution_evidence(evidence))


def _report_sha(report: EvaluationReport) -> str:
    return _artifact_sha(serialize_evaluation_report(report))


def _case_ids(run: CanonicalPredictionRun) -> tuple[str, ...]:
    return tuple(case.case_id for case in run.cases)


def _validate_pair(run: CanonicalPredictionRun, evidence: ExecutionEvidence) -> None:
    if evidence.prediction_run_sha256 != _prediction_sha(run):
        raise EvaluationError("execution prediction binding does not match canonical run")
    evidence_ids = tuple(case.case_id for case in evidence.cases)
    if evidence_ids != _case_ids(run):
        raise EvaluationError("execution case IDs do not match canonical run")


def _identity(run: CanonicalPredictionRun) -> tuple[object, ...]:
    return (
        run.baseline_id,
        run.seed,
        run.test_set_sha256,
        run.test_case_count,
        run.provenance.fingerprints,
        run.adapter_id,
        run.adapter_schema_version,
        _case_ids(run),
    )


def _zero_scores() -> AnswerScores:
    return AnswerScores(0.0, 0.0, 0.0)


def _case_evaluations(
    run: CanonicalPredictionRun,
    evidence: ExecutionEvidence,
    manual_reviews: Sequence[ManualFailureReview],
) -> tuple[CaseEvaluation, ...]:
    reviews = {review.case_id: review for review in manual_reviews}
    unknown = set(reviews) - set(_case_ids(run))
    if unknown or len(reviews) != len(manual_reviews):
        raise EvaluationError("manual review case IDs must be unique and represented")

    output: list[CaseEvaluation] = []
    for prediction, execution in zip(run.cases, evidence.cases, strict=True):
        exact = False
        structural = False
        if prediction.prediction_status == "ok" and prediction.predicted_sql is not None:
            exact = exact_match(prediction.predicted_sql, prediction.gold_sql)
            structural = structural_match(prediction.predicted_sql, prediction.gold_sql)

        gold_valid = execution.gold.status == "ok" and execution.gold.result is not None
        prediction_valid = (
            execution.prediction.status == "ok" and execution.prediction.result is not None
        )
        if not gold_valid:
            execution_match: bool | None = None
            scores: AnswerScores | None = None
        elif not prediction_valid:
            execution_match = False
            scores = _zero_scores()
        else:
            assert execution.gold.result is not None
            assert execution.prediction.result is not None
            execution_match = results_equal(execution.gold.result, execution.prediction.result)
            scores = answer_scores(execution.gold.result, execution.prediction.result)

        automated = classify_failure(
            prediction=prediction,
            gold_execution=execution.gold,
            predicted_execution=execution.prediction,
            execution_match=execution_match is True,
        )
        manual = reviews.get(prediction.case_id)
        tags = set(automated)
        if manual is not None:
            tags.update(manual.tags)
        output.append(
            CaseEvaluation(
                case_id=prediction.case_id,
                difficulty=prediction.difficulty,
                categories=prediction.categories,
                exact_match=exact,
                structural_match=structural,
                execution_match=execution_match,
                answer_scores=scores,
                inference_latency_ms=prediction.inference.latency_ms,
                execution_latency_ms=execution.prediction.latency_ms,
                inference_cost=prediction.inference.cost,
                execution_cost=execution.prediction.cost,
                failure_tags=tuple(sorted(tags)),
                gold_execution_latency_ms=execution.gold.latency_ms,
                gold_execution_cost=execution.gold.cost,
            )
        )
    return tuple(output)


def _invalid_ratio(denominator: int) -> RatioMetric:
    return RatioMetric(None, denominator, None, None)


def _rate(
    cases: Sequence[CaseEvaluation],
    getter: Callable[[CaseEvaluation], float | None],
    policy: BootstrapPolicy,
) -> RatioMetric:
    values = tuple(getter(case) for case in cases)
    if any(value is None for value in values):
        return _invalid_ratio(len(cases))
    return ratio_metric(tuple(float(value) for value in values if value is not None), policy)


def _cost_values(costs: Sequence[CostEvidence | None]) -> tuple[float | None, ...]:
    return tuple(
        float(cost.amount)
        if cost is not None
        and cost.measurement_status in ("observed", "estimated")
        and cost.amount is not None
        else None
        for cost in costs
    )


def _distribution(
    values: Sequence[float | None], policy: BootstrapPolicy
) -> DistributionMetric:
    return distribution_metric(values, len(values), policy)


def _failure_rates(
    cases: Sequence[CaseEvaluation], policy: BootstrapPolicy
) -> tuple[tuple[str, RatioMetric], ...]:
    tags = sorted({tag for case in cases for tag in case.failure_tags})
    return tuple(
        (
            tag,
            ratio_metric(tuple(float(tag in case.failure_tags) for case in cases), policy),
        )
        for tag in tags
    )


def _headline_dimensions(
    cases: Sequence[CaseEvaluation], policy: BootstrapPolicy
) -> tuple[tuple[str, object], ...]:
    return (
        ("exact_match", _rate(cases, lambda case: float(case.exact_match), policy)),
        ("structural_match", _rate(cases, lambda case: float(case.structural_match), policy)),
        (
            "execution_accuracy",
            _rate(
                cases,
                lambda case: None
                if case.execution_match is None
                else float(case.execution_match),
                policy,
            ),
        ),
        (
            "answer_precision",
            _rate(
                cases,
                lambda case: None if case.answer_scores is None else case.answer_scores.precision,
                policy,
            ),
        ),
        (
            "answer_recall",
            _rate(
                cases,
                lambda case: None if case.answer_scores is None else case.answer_scores.recall,
                policy,
            ),
        ),
        (
            "answer_f1",
            _rate(
                cases,
                lambda case: None if case.answer_scores is None else case.answer_scores.f1,
                policy,
            ),
        ),
        (
            "inference_latency_ms",
            _distribution(tuple(case.inference_latency_ms for case in cases), policy),
        ),
        (
            "prediction_execution_latency_ms",
            _distribution(tuple(case.execution_latency_ms for case in cases), policy),
        ),
        (
            "gold_execution_latency_ms",
            _distribution(tuple(case.gold_execution_latency_ms for case in cases), policy),
        ),
        (
            "inference_cost_usd",
            _distribution(_cost_values(tuple(case.inference_cost for case in cases)), policy),
        ),
        (
            "execution_cost_usd",
            _distribution(_cost_values(tuple(case.execution_cost for case in cases)), policy),
        ),
        (
            "gold_execution_cost_usd",
            _distribution(_cost_values(tuple(case.gold_execution_cost for case in cases)), policy),
        ),
        ("failure_rates", _failure_rates(cases, policy)),
    )


def _breakdown_record(
    cases: Sequence[CaseEvaluation], policy: BootstrapPolicy
) -> dict[str, object]:
    return {
        "case_count": len(cases),
        "exact_match": _rate(cases, lambda case: float(case.exact_match), policy),
        "structural_match": _rate(cases, lambda case: float(case.structural_match), policy),
        "execution_accuracy": _rate(
            cases,
            lambda case: None if case.execution_match is None else float(case.execution_match),
            policy,
        ),
        "answer_f1": _rate(
            cases,
            lambda case: None if case.answer_scores is None else case.answer_scores.f1,
            policy,
        ),
    }


def _breakdowns(
    cases: Sequence[CaseEvaluation], policy: BootstrapPolicy
) -> tuple[tuple[str, object], ...]:
    difficulties: dict[str, list[CaseEvaluation]] = defaultdict(list)
    categories: dict[str, list[CaseEvaluation]] = defaultdict(list)
    for case in cases:
        difficulties[case.difficulty].append(case)
        for category in case.categories:
            categories[category].append(case)
    return (
        (
            "difficulty",
            tuple(
                (name, _breakdown_record(group, policy))
                for name, group in sorted(difficulties.items())
            ),
        ),
        (
            "category",
            tuple(
                (name, _breakdown_record(group, policy))
                for name, group in sorted(categories.items())
            ),
        ),
    )


def _readiness(
    runs: Sequence[CanonicalPredictionRun],
    evidences: Sequence[ExecutionEvidence],
) -> Readiness:
    blockers: set[str] = set()
    if any(run.provenance.synthetic for run in runs):
        blockers.add("synthetic_input")
    if any(
        evidence.executor.synthetic or evidence.executor.kind == "fake"
        for evidence in evidences
    ):
        blockers.add("fake_executor")
    if any(not run.provenance.reviewed or not run.provenance.live_verified for run in runs):
        blockers.add("missing_finalized_test_provenance")
    if any(
        case.privacy.documentation_status != "documented"
        or case.privacy.policy_sha256 is None
        or case.privacy.review_sha256 is None
        for run in runs
        for case in run.cases
    ):
        blockers.add("missing_privacy_evidence")
    if any(evidence.status == "invalid_gold_failure" for evidence in evidences):
        blockers.add("gold_execution_failure")
    if any(evidence.status == "unresolved_cost" for evidence in evidences):
        blockers.add("unresolved_submitted_job_cost")
    if len(runs) < 2:
        blockers.add("incomplete_reproducibility")
    genuine = sum(
        not run.provenance.synthetic
        and not evidence.executor.synthetic
        and evidence.executor.kind != "fake"
        for run, evidence in zip(runs, evidences, strict=True)
    )
    if genuine < 3:
        blockers.add("missing_genuine_baseline_runs")
    return Readiness((), tuple(sorted(blockers)))


def build_report(
    *,
    primary_run: CanonicalPredictionRun,
    primary_evidence: ExecutionEvidence,
    replicate_pairs: Sequence[tuple[CanonicalPredictionRun, ExecutionEvidence]] = (),
    bootstrap_policy: BootstrapPolicy = DEFAULT_BOOTSTRAP_POLICY,
    manual_reviews: Sequence[ManualFailureReview] = (),
) -> EvaluationReport:
    """Build a report solely from verified immutable prediction/execution evidence."""
    _validate_pair(primary_run, primary_evidence)
    sorted_replicates = tuple(sorted(replicate_pairs, key=lambda pair: pair[0].run_id))
    if any(_identity(run) != _identity(primary_run) for run, _ in sorted_replicates):
        raise EvaluationError("replicate identity does not match primary run")
    if any(run.run_id == primary_run.run_id for run, _ in sorted_replicates):
        raise EvaluationError("replicate cannot reuse primary run ID")
    if len({run.run_id for run, _ in sorted_replicates}) != len(sorted_replicates):
        raise EvaluationError("replicate run IDs must be distinct")
    for run, evidence in sorted_replicates:
        _validate_pair(run, evidence)

    cases = _case_evaluations(primary_run, primary_evidence, manual_reviews)
    all_runs = (primary_run, *(run for run, _ in sorted_replicates))
    all_evidence = (primary_evidence, *(evidence for _, evidence in sorted_replicates))
    dimensions = list(_headline_dimensions(cases, bootstrap_policy))
    if len(all_runs) >= 2:
        dimensions.extend(
            (
                (
                    "reproducibility_raw",
                    reproducibility_metric(
                        all_runs, normalized_sql=False, policy=bootstrap_policy
                    ),
                ),
                (
                    "reproducibility_normalized_sql",
                    reproducibility_metric(
                        all_runs, normalized_sql=True, policy=bootstrap_policy
                    ),
                ),
            )
        )
    else:
        dimensions.extend(
            (("reproducibility_raw", None), ("reproducibility_normalized_sql", None))
        )

    ids = _case_ids(primary_run)
    return EvaluationReport(
        baseline_id=primary_run.baseline_id,
        primary_run_id=primary_run.run_id,
        primary_prediction_sha256=_prediction_sha(primary_run),
        primary_execution_sha256=_execution_sha(primary_evidence),
        replicate_pairs=tuple(
            (run.run_id, _prediction_sha(run), _execution_sha(evidence))
            for run, evidence in sorted_replicates
        ),
        test_set_sha256=primary_run.test_set_sha256,
        case_set_sha256=hashlib.sha256(canonical_json(ids)).hexdigest(),
        expected_case_count=primary_run.test_case_count,
        represented_case_count=len(cases),
        readiness=_readiness(all_runs, all_evidence),
        bootstrap=bootstrap_policy,
        cases=cases,
        dimensions=tuple(dimensions),
        breakdowns=_breakdowns(cases, bootstrap_policy),
    )


def _paired_metric(
    metric: str,
    left: Sequence[float | None],
    right: Sequence[float | None],
    policy: BootstrapPolicy,
) -> tuple[MetricDelta | None, str | None]:
    if any(value is None for value in (*left, *right)):
        return None, f"incomplete_paired_{metric}"
    delta = paired_delta(
        tuple(float(value) for value in left if value is not None),
        tuple(float(value) for value in right if value is not None),
        policy,
    )
    return replace(delta, metric=metric), None


def compare_reports(
    left: EvaluationReport,
    right: EvaluationReport,
    *,
    bootstrap_policy: BootstrapPolicy = DEFAULT_BOOTSTRAP_POLICY,
) -> ComparisonReport:
    """Build a paired left-minus-right comparison without winner semantics."""
    if left.test_set_sha256 != right.test_set_sha256:
        raise EvaluationError("comparison requires identical test-set identity")
    if left.case_set_sha256 != right.case_set_sha256:
        raise EvaluationError("comparison requires identical case-set identity")
    left_map = {case.case_id: case for case in left.cases}
    right_map = {case.case_id: case for case in right.cases}
    if set(left_map) != set(right_map):
        raise EvaluationError("comparison requires identical case IDs")
    ids = tuple(case.case_id for case in left.cases)
    left_cases = tuple(left_map[case_id] for case_id in ids)
    right_cases = tuple(right_map[case_id] for case_id in ids)

    extractors: tuple[
        tuple[str, Callable[[CaseEvaluation], float | None]], ...
    ] = (
        ("exact_match", lambda case: float(case.exact_match)),
        ("structural_match", lambda case: float(case.structural_match)),
        (
            "execution_accuracy",
            lambda case: None if case.execution_match is None else float(case.execution_match),
        ),
        (
            "answer_precision",
            lambda case: None if case.answer_scores is None else case.answer_scores.precision,
        ),
        (
            "answer_recall",
            lambda case: None if case.answer_scores is None else case.answer_scores.recall,
        ),
        (
            "answer_f1",
            lambda case: None if case.answer_scores is None else case.answer_scores.f1,
        ),
        ("inference_latency_ms", lambda case: case.inference_latency_ms),
        ("prediction_execution_latency_ms", lambda case: case.execution_latency_ms),
        ("gold_execution_latency_ms", lambda case: case.gold_execution_latency_ms),
        (
            "inference_cost_usd",
            lambda case: float(case.inference_cost.amount)
            if case.inference_cost.amount is not None
            else None,
        ),
        (
            "execution_cost_usd",
            lambda case: float(case.execution_cost.amount)
            if case.execution_cost.amount is not None
            else None,
        ),
        (
            "gold_execution_cost_usd",
            lambda case: float(case.gold_execution_cost.amount)
            if case.gold_execution_cost is not None
            and case.gold_execution_cost.amount is not None
            else None,
        ),
    )
    deltas: list[MetricDelta] = []
    blockers = set(left.readiness.scientific_blockers) | set(
        right.readiness.scientific_blockers
    )
    blockers.update(left.readiness.implementation_blockers)
    blockers.update(right.readiness.implementation_blockers)
    for metric, extractor in extractors:
        delta, blocker = _paired_metric(
            metric,
            tuple(extractor(case) for case in left_cases),
            tuple(extractor(case) for case in right_cases),
            bootstrap_policy,
        )
        if delta is not None:
            deltas.append(delta)
        if blocker is not None:
            blockers.add(blocker)
    return ComparisonReport(
        left_report_sha256=_report_sha(left),
        right_report_sha256=_report_sha(right),
        test_set_sha256=left.test_set_sha256,
        case_set_sha256=left.case_set_sha256,
        deltas=tuple(deltas),
        readiness=Readiness((), tuple(sorted(blockers))),
        bootstrap=bootstrap_policy,
    )
