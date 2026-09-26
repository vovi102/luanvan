"""Fail-closed orchestration for static checks, preflight and query execution."""

from __future__ import annotations

import hashlib
import json
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
    QueryExecution,
)
from nl2sparql.evaluation.executor import ExecutionJournal, QueryExecutor, QueryRequest
from nl2sparql.evaluation.sql_semantics import analyze_sql


def _unmeasured() -> CostEvidence:
    return CostEvidence("unmeasured", None, None, None)


def _terminal(status: str, error_code: str) -> QueryExecution:
    return QueryExecution(status, None, None, None, _unmeasured(), None, error_code)


def _prediction_request(case: object) -> QueryRequest | None:
    status = case.prediction_status
    if status != "ok":
        return None
    analysis = analyze_sql(case.gold_sql)
    return QueryRequest(
        case.case_id,
        "prediction",
        case.predicted_sql,
        analysis.result_order == "sequence",
    )


def _validate_request(request: QueryRequest) -> None:
    validate_sql_text(request.sql)
    analyze_sql(request.sql)


def _guarded(estimate: DryRunEvidence, policy: ExecutionPolicy) -> bool:
    if estimate.estimated_bytes > policy.per_query_byte_cap:
        return False
    cost = Decimal(estimate.estimated_bytes) / Decimal(2**40) * policy.pricing.amount_per_tib
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
    gold_requests: dict[str, QueryRequest] = {}
    prediction_requests: dict[str, QueryRequest] = {}
    static_errors: dict[tuple[str, str], str] = {}
    for case in run.cases:
        gold_analysis = analyze_sql(case.gold_sql)
        gold = QueryRequest(
            case.case_id,
            "gold",
            case.gold_sql,
            gold_analysis.result_order == "sequence",
        )
        try:
            _validate_request(gold)
        except (TestSetError, ValueError) as exc:
            static_errors[(case.case_id, "gold")] = type(exc).__name__
        gold_requests[case.case_id] = gold
        try:
            predicted = _prediction_request(case)
            if predicted is not None:
                _validate_request(predicted)
                prediction_requests[case.case_id] = predicted
        except (TestSetError, ValueError) as exc:
            static_errors[(case.case_id, "prediction")] = type(exc).__name__

    first_preflights: dict[tuple[str, str], DryRunEvidence] = {}
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
            journal.append(
                "initial_dry_run_error", {"request": request, "error": type(exc).__name__}
            )

    aggregate = sum(item.estimated_bytes for item in first_preflights.values())
    aggregate_blocked = aggregate > policy.aggregate_byte_cap or any(
        not _guarded(item, policy) for item in first_preflights.values()
    )
    outcomes: list[ExecutionCaseEvidence] = []
    for case in run.cases:
        pair: dict[str, QueryExecution] = {}
        for role in ("gold", "prediction"):
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
            if aggregate_blocked:
                pair[role] = _terminal("guard_blocked", "aggregate_preflight_guard")
            elif key in static_errors:
                pair[role] = _terminal("error", static_errors[key])
            else:
                try:
                    immediate = executor.dry_run(request, policy)
                    journal.append("immediate_dry_run", {"request": request, "evidence": immediate})
                    if not _guarded(immediate, policy):
                        pair[role] = _terminal("guard_blocked", "immediate_preflight_guard")
                    else:
                        pair[role] = executor.execute(request, policy, immediate)
                except Exception as exc:  # executor boundary is intentionally fail-closed
                    pair[role] = _terminal("error", type(exc).__name__)
            journal.append(
                "execution",
                {"case_id": case.case_id, "role": role, "outcome": pair[role]},
            )
        outcomes.append(ExecutionCaseEvidence(case.case_id, pair["gold"], pair["prediction"]))
    terminal = journal.seal({"case_count": len(outcomes)})
    return ExecutionEvidence(
        execution_id=execution_id,
        prediction_run_sha256=prediction_sha,
        policy_sha256=policy_sha,
        executor=executor.provenance,
        journal_terminal_sha256=terminal,
        cases=tuple(outcomes),
    )
