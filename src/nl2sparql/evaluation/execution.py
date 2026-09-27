"""Fail-closed orchestration for static checks, preflight and query execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.evaluation.artifacts import canonical_json, serialize_prediction_run
from nl2sparql.evaluation.contracts import (
    CanonicalPredictionRun,
    CostEvidence,
    DryRunEvidence,
    ExecutionCaseEvidence,
    ExecutionEvidence,
    ExecutionPolicy,
    PredictionCase,
    QueryExecution,
)
from nl2sparql.evaluation.executor import ExecutionJournal, QueryExecutor, QueryRequest
from nl2sparql.evaluation.sql_semantics import analyze_sql


def _unmeasured() -> CostEvidence:
    return CostEvidence("unmeasured", None, None, None)


def _terminal(status: str, error_code: str) -> QueryExecution:
    return QueryExecution(status, None, None, None, _unmeasured(), None, error_code)


def _prediction_request(case: PredictionCase, *, order_sensitive: bool) -> QueryRequest | None:
    status = case.prediction_status
    if status != "ok":
        return None
    return QueryRequest(
        case.case_id,
        "prediction",
        case.predicted_sql,
        order_sensitive,
    )


def _validate_request(request: QueryRequest) -> None:
    validate_sql_text(request.sql)
    analyze_sql(request.sql)


def _request_sha(request: QueryRequest) -> str:
    return hashlib.sha256(canonical_json(request)).hexdigest()


def _guarded(estimate: DryRunEvidence, policy: ExecutionPolicy) -> bool:
    if estimate.estimated_bytes > policy.per_query_byte_cap:
        return False
    cost = policy.pricing.estimate_cost(estimate.estimated_bytes)
    return cost <= policy.estimated_cost_cap


def _skipped(status: str) -> QueryExecution:
    mapping = {
        "no_output": "skipped_no_output",
        "invalid_sql": "skipped_invalid_sql",
        "unsafe_sql": "skipped_unsafe_sql",
        "generation_error": "skipped_generation_error",
        "timeout": "skipped_inference_timeout",
    }
    terminal = mapping[status]
    return _terminal(terminal, terminal)


def execute_run(
    run: CanonicalPredictionRun,
    *,
    execution_id: str,
    policy: ExecutionPolicy,
    executor: QueryExecutor,
    journal: ExecutionJournal,
) -> ExecutionEvidence:
    """Execute a complete run with global preflight and immediate re-preflight."""
    prediction_document = json.loads(serialize_prediction_run(run))
    prediction_sha = prediction_document["artifact_sha256"]
    policy_sha = hashlib.sha256(canonical_json(policy)).hexdigest()
    journal.append(
        "header",
        {
            "execution_id": execution_id,
            "prediction_run_sha256": prediction_sha,
            "policy_sha256": policy_sha,
            "executor": executor.provenance,
        },
    )
    bind_journal = getattr(executor, "bind_execution_journal", None)
    if bind_journal is not None:
        bind_journal(journal, execution_id=execution_id)
    gold_requests: dict[str, QueryRequest] = {}
    prediction_requests: dict[str, QueryRequest] = {}
    static_errors: dict[tuple[str, str], str] = {}
    for case in run.cases:
        order_sensitive = False
        try:
            gold_analysis = analyze_sql(case.gold_sql)
            order_sensitive = gold_analysis.result_order == "sequence"
            gold = QueryRequest(case.case_id, "gold", case.gold_sql, order_sensitive)
            _validate_request(gold)
        except (TestSetError, ValueError) as exc:
            static_errors[(case.case_id, "gold")] = type(exc).__name__
            gold = QueryRequest(case.case_id, "gold", case.gold_sql, False)
        gold_requests[case.case_id] = gold
        try:
            predicted = _prediction_request(case, order_sensitive=order_sensitive)
            if predicted is not None:
                _validate_request(predicted)
                prediction_requests[case.case_id] = predicted
        except (TestSetError, ValueError) as exc:
            static_errors[(case.case_id, "prediction")] = type(exc).__name__

    first_preflights: dict[tuple[str, str], DryRunEvidence] = {}
    initial_preflight_errors: dict[tuple[str, str], str] = {}
    for request in (*gold_requests.values(), *prediction_requests.values()):
        key = (request.case_id, request.role)
        if key in static_errors:
            continue
        try:
            estimate = executor.dry_run(request, policy)
            first_preflights[key] = estimate
            journal.append("initial_dry_run", {"request": request, "evidence": estimate})
        except Exception as exc:  # executor boundary is intentionally fail-closed
            static_errors[key] = type(exc).__name__
            initial_preflight_errors[key] = type(exc).__name__
            journal.append(
                "initial_dry_run_error", {"request": request, "error": type(exc).__name__}
            )

    effective_estimates = {key: item.estimated_bytes for key, item in first_preflights.items()}
    billed_estimates = {
        key: policy.pricing.conservative_billed_bytes(item.estimated_bytes)
        for key, item in first_preflights.items()
    }
    aggregate = sum(effective_estimates.values())
    pending_billed_estimate = sum(billed_estimates.values())
    observed_billed = 0
    pending_cost_estimate = sum(
        (policy.pricing.estimate_cost(value) for value in effective_estimates.values()),
        start=Decimal(0),
    )
    observed_cost = Decimal(0)
    aggregate_blocked = (
        aggregate > policy.aggregate_byte_cap
        or pending_billed_estimate > policy.billed_byte_cap
        or pending_cost_estimate > policy.estimated_cost_cap
        or any(not _guarded(item, policy) for item in first_preflights.values())
    )
    live_halt_reason = (
        "gold_initial_validation_or_preflight_failure"
        if any(role == "gold" for _, role in static_errors)
        else None
    )
    outcomes: list[ExecutionCaseEvidence] = []
    for case in run.cases:
        pair: dict[str, QueryExecution] = {}
        for role in ("gold", "prediction"):
            immediate: DryRunEvidence | None = None
            immediate_error: str | None = None
            request = (
                gold_requests[case.case_id]
                if role == "gold"
                else prediction_requests.get(case.case_id)
            )
            if request is None:
                pair[role] = _skipped(case.prediction_status)
                journal.append(
                    "skipped", {"case_id": case.case_id, "role": role, "status": pair[role].status}
                )
                continue
            key = (case.case_id, role)
            if key in static_errors:
                pair[role] = _terminal("error", static_errors[key])
            elif aggregate_blocked:
                pair[role] = _terminal("guard_blocked", "aggregate_preflight_guard")
            elif live_halt_reason is not None:
                pair[role] = _terminal("not_run", live_halt_reason)
            else:
                try:
                    immediate = executor.dry_run(request, policy)
                    journal.append("immediate_dry_run", {"request": request, "evidence": immediate})
                    revised_aggregate = (
                        aggregate - effective_estimates[key] + immediate.estimated_bytes
                    )
                    revised_pending_cost = (
                        pending_cost_estimate
                        - policy.pricing.estimate_cost(effective_estimates[key])
                        + policy.pricing.estimate_cost(immediate.estimated_bytes)
                    )
                    immediate_billed_estimate = policy.pricing.conservative_billed_bytes(
                        immediate.estimated_bytes
                    )
                    revised_pending_billed = (
                        pending_billed_estimate - billed_estimates[key] + immediate_billed_estimate
                    )
                    if (
                        revised_aggregate > policy.aggregate_byte_cap
                        or observed_billed + revised_pending_billed > policy.billed_byte_cap
                        or observed_cost + revised_pending_cost > policy.estimated_cost_cap
                    ):
                        pair[role] = _terminal("guard_blocked", "immediate_aggregate_guard")
                        pending_billed_estimate -= billed_estimates[key]
                        pending_cost_estimate -= policy.pricing.estimate_cost(
                            effective_estimates[key]
                        )
                    elif not _guarded(immediate, policy):
                        pair[role] = _terminal("guard_blocked", "immediate_preflight_guard")
                        pending_billed_estimate -= billed_estimates[key]
                        pending_cost_estimate -= policy.pricing.estimate_cost(
                            effective_estimates[key]
                        )
                    else:
                        aggregate = revised_aggregate
                        effective_estimates[key] = immediate.estimated_bytes
                        billed_estimates[key] = immediate_billed_estimate
                        pending_billed_estimate = revised_pending_billed - immediate_billed_estimate
                        pending_cost_estimate = revised_pending_cost - policy.pricing.estimate_cost(
                            immediate.estimated_bytes
                        )
                        pair[role] = executor.execute(request, policy, immediate)
                        if pair[role].submission_attempted:
                            if (
                                pair[role].billed_bytes is None
                                or pair[role].cost.amount is None
                                or pair[role].cost.measurement_status == "unmeasured"
                            ):
                                live_halt_reason = "unresolved_submitted_job_cost"
                            else:
                                observed_billed += pair[role].billed_bytes
                                observed_cost += pair[role].cost.amount
                                if observed_billed > policy.billed_byte_cap:
                                    pair[role] = replace(
                                        pair[role],
                                        status="error",
                                        error_code="aggregate_billed_byte_cap_exceeded",
                                    )
                                    live_halt_reason = "aggregate_billed_byte_guard"
                                elif observed_cost > policy.estimated_cost_cap:
                                    pair[role] = replace(
                                        pair[role],
                                        status="error",
                                        error_code="aggregate_execution_cost_cap_exceeded",
                                    )
                                    live_halt_reason = "aggregate_execution_cost_guard"
                                elif (
                                    observed_billed + pending_billed_estimate
                                    > policy.billed_byte_cap
                                ):
                                    live_halt_reason = "aggregate_billed_byte_guard"
                                elif (
                                    observed_cost + pending_cost_estimate
                                    > policy.estimated_cost_cap
                                ):
                                    live_halt_reason = "aggregate_execution_cost_guard"
                except Exception as exc:  # executor boundary is intentionally fail-closed
                    if immediate is None:
                        immediate_error = type(exc).__name__
                        journal.append(
                            "immediate_dry_run_error",
                            {"request": request, "error": immediate_error},
                        )
                    pair[role] = _terminal("error", type(exc).__name__)
            pair[role] = replace(
                pair[role],
                initial_preflight=first_preflights.get((case.case_id, role)),
                immediate_preflight=immediate,
                request_sha256=_request_sha(request),
                initial_preflight_error=initial_preflight_errors.get((case.case_id, role)),
                immediate_preflight_error=immediate_error,
            )
            journal.append(
                "execution",
                {
                    "case_id": case.case_id,
                    "role": role,
                    "request": request,
                    "outcome": pair[role],
                },
            )
            if role == "gold" and pair[role].status != "ok":
                live_halt_reason = f"gold_{pair[role].status}"
        outcomes.append(ExecutionCaseEvidence(case.case_id, pair["gold"], pair["prediction"]))
    terminal = journal.seal({"case_count": len(outcomes)})
    submitted = tuple(
        query
        for case in outcomes
        for query in (case.gold, case.prediction)
        if query.submission_attempted
    )
    billing_complete = all(
        query.billed_bytes is not None and query.cost.amount is not None for query in submitted
    )
    currencies = {query.cost.currency for query in submitted if query.cost.currency is not None}
    if submitted and billing_complete and len(currencies) <= 1:
        aggregate_cost = CostEvidence(
            "estimated"
            if any(query.cost.measurement_status == "estimated" for query in submitted)
            else "observed",
            sum(
                (query.cost.amount for query in submitted if query.cost.amount is not None),
                Decimal(0),
            ),
            next(iter(currencies), policy.pricing.currency),
            "execution-evidence-aggregate",
        )
    elif submitted:
        aggregate_cost = _unmeasured()
    else:
        aggregate_cost = CostEvidence(
            "estimated", Decimal(0), policy.pricing.currency, "no-live-submissions"
        )
    return ExecutionEvidence(
        execution_id=execution_id,
        prediction_run_sha256=prediction_sha,
        policy_sha256=policy_sha,
        executor=executor.provenance,
        journal_terminal_sha256=terminal,
        cases=tuple(outcomes),
        policy=policy,
        test_set_sha256=run.test_set_sha256,
        estimated_bytes_total=sum(
            (query.immediate_preflight or query.initial_preflight).estimated_bytes
            for case in outcomes
            for query in (case.gold, case.prediction)
            if query.immediate_preflight is not None or query.initial_preflight is not None
        ),
        billed_bytes_total=(
            sum(query.billed_bytes for query in submitted if query.billed_bytes is not None)
            if billing_complete
            else None
        ),
        execution_cost=aggregate_cost,
    )
