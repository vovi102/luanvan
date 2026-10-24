"""Exact-SQL campaign planning, guarded execution and logical evidence references."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from nl2sparql.evaluation.artifacts import serialize_prediction_run
from nl2sparql.evaluation.contracts import (
    CanonicalPredictionRun,
    EvaluationError,
    ExecutionCaseEvidence,
    ExecutionPolicy,
    ExecutorProvenance,
    SharedCaseBinding,
    SharedExecutionEvidence,
    SharedRunReference,
)
from nl2sparql.evaluation.executor import ExecutionJournal, QueryExecutor, QueryRequest


def sql_digest(sql: str) -> str:
    """Hash exact UTF-8 SQL bytes; never normalize benchmark text."""
    return hashlib.sha256(sql.encode()).hexdigest()


@dataclass(frozen=True)
class SharedExecutionPlan:
    """Input identities and unique physical SQL in gold-first order."""

    runs: tuple[SharedRunReference, ...]
    queries: tuple[tuple[str, str], ...]

    def request(self, key: str) -> QueryRequest:
        """Preserve physical sequence; gold use dominates execution safety."""
        sql = dict(self.queries)[key]
        gold = any(case.gold_query_sha256 == key for run in self.runs for case in run.cases)
        return QueryRequest(key, "gold" if gold else "prediction", sql, True)


def plan_shared_campaign(runs: Sequence[CanonicalPredictionRun]) -> SharedExecutionPlan:
    """Bind all cases and deduplicate only exact SQL within this campaign."""
    if not runs or len({run.run_id for run in runs}) != len(runs):
        raise EvaluationError("shared plan requires unique nonempty runs")
    references = []
    queries = {}
    gold = set()
    for run in sorted(runs, key=lambda item: item.run_id):
        cases = []
        for case in run.cases:
            gold_key = sql_digest(case.gold_sql)
            queries[gold_key] = case.gold_sql
            gold.add(gold_key)
            prediction_key = None
            if case.prediction_status == "ok":
                prediction_key = sql_digest(case.predicted_sql)
                queries[prediction_key] = case.predicted_sql
            cases.append(
                SharedCaseBinding(case.case_id, gold_key, prediction_key, case.prediction_status)
            )
        digest = json.loads(serialize_prediction_run(run))["artifact_sha256"]
        references.append(SharedRunReference(run.run_id, digest, run.test_set_sha256, tuple(cases)))
    ordered = sorted(gold) + sorted(set(queries) - gold)
    return SharedExecutionPlan(tuple(references), tuple((key, queries[key]) for key in ordered))


def _header(plan, campaign_id, source_context_sha256, policy_sha256, executor):
    return {
        "campaign_id": campaign_id,
        "protocol_id": "exact-sql-shared-v1",
        "source_context_sha256": source_context_sha256,
        "policy_sha256": policy_sha256,
        "runs": plan.runs,
        "queries": plan.queries,
        "executor": executor,
    }


def execute_shared_campaign(
    runs: Sequence[CanonicalPredictionRun],
    *,
    campaign_id: str,
    source_context_sha256: str,
    policy: ExecutionPolicy,
    executor: QueryExecutor,
    journal: ExecutionJournal,
) -> SharedExecutionEvidence:
    """Execute unique SQL once; isolate predicted SQL failures, stop on global uncertainty."""
    from dataclasses import replace
    from decimal import Decimal

    from nl2sparql.dataset.testset.contracts import TestSetError
    from nl2sparql.evaluation.artifacts import canonical_json
    from nl2sparql.evaluation.contracts import SharedExecutionEvidence, SharedQueryExecution
    from nl2sparql.evaluation.execution import _guarded, _request_sha, _terminal, _validate_request
    from nl2sparql.evaluation.executor import QueryValidationError

    plan = plan_shared_campaign(runs)
    policy_sha = hashlib.sha256(canonical_json(policy)).hexdigest()
    # Validate all identities before opening the executor boundary.
    SharedExecutionEvidence(
        campaign_id,
        source_context_sha256,
        policy_sha,
        policy,
        executor.provenance,
        plan.runs,
        tuple(
            SharedQueryExecution(k, sql, _terminal("not_run", "planned")) for k, sql in plan.queries
        ),
        "0" * 64,
        None,
    )
    journal.append(
        "shared_header",
        _header(plan, campaign_id, source_context_sha256, policy_sha, executor.provenance),
    )
    executor.bind_execution_journal(journal, execution_id=campaign_id)
    initial = {}
    initial_errors = {}
    terminal = {}
    halt = None
    # Finish the full initial survey before deciding whether any job may be submitted.
    for key, _ in plan.queries:
        request = plan.request(key)
        try:
            _validate_request(request)
        except (TestSetError, ValueError) as exc:
            terminal[key] = _terminal("error", type(exc).__name__)
            journal.append("static_error", {"request": request, "error": str(exc)})
        else:
            try:
                initial[key] = executor.dry_run(request, policy)
            except Exception as exc:
                initial_errors[key] = str(exc)
                journal.append("initial_dry_run_error", {"request": request, "error": str(exc)})
                terminal[key] = _terminal("error", getattr(exc, "reason", type(exc).__name__))
                if not isinstance(exc, QueryValidationError):
                    halt = "initial_preflight_infrastructure_error"
            else:
                journal.append("initial_dry_run", {"request": request, "evidence": initial[key]})
                if not _guarded(initial[key], policy):
                    terminal[key] = _terminal("guard_blocked", "initial_preflight_guard")
        if key in terminal and request.role == "gold" and halt is None:
            halt = "gold_initial_validation_or_preflight_failure"

    pending = {key: value.estimated_bytes for key, value in initial.items() if key not in terminal}
    observed_processed = 0
    observed_billed = 0
    observed_cost = Decimal(0)

    def budget_ok():
        return (
            observed_processed + sum(pending.values()) <= policy.aggregate_byte_cap
            and observed_billed
            + sum(policy.pricing.conservative_billed_bytes(v) for v in pending.values())
            <= policy.billed_byte_cap
            and observed_cost
            + sum((policy.pricing.estimate_cost(v) for v in pending.values()), Decimal(0))
            <= policy.estimated_cost_cap
        )

    if halt is None and not budget_ok():
        halt = "initial_aggregate_guard"
    outcomes = []
    for key, sql in plan.queries:
        request = plan.request(key)
        immediate = None
        immediate_error = None
        if key in terminal:
            outcome = terminal[key]
        elif halt is not None:
            outcome = _terminal("not_run", halt)
        else:
            try:
                immediate = executor.dry_run(request, policy)
            except Exception as exc:
                immediate_error = str(exc)
                journal.append(
                    "immediate_dry_run_error", {"request": request, "error": immediate_error}
                )
                outcome = _terminal("error", getattr(exc, "reason", type(exc).__name__))
                if not isinstance(exc, QueryValidationError):
                    halt = "immediate_preflight_infrastructure_error"
            else:
                journal.append("immediate_dry_run", {"request": request, "evidence": immediate})
                if not _guarded(immediate, policy):
                    outcome = _terminal("guard_blocked", "immediate_preflight_guard")
                else:
                    pending[key] = immediate.estimated_bytes
                    if not budget_ok():
                        outcome = _terminal("guard_blocked", "immediate_aggregate_guard")
                        halt = "immediate_aggregate_guard"
                    else:
                        # Executor exceptions may hide a submission: never continue after one.
                        # A broken journal must escape, never become an isolated SQL failure.
                        outcome = executor.execute(request, policy, immediate)
                        if outcome.submission_attempted:
                            if (
                                outcome.billed_bytes is None
                                or outcome.cost.amount is None
                                or outcome.cost.measurement_status == "unmeasured"
                            ):
                                halt = "unresolved_submitted_job_cost"
                            else:
                                observed_billed += outcome.billed_bytes
                                observed_cost += outcome.cost.amount
                                observed_processed += (
                                    outcome.processed_bytes
                                    if outcome.processed_bytes is not None
                                    else immediate.estimated_bytes
                                )
                            if outcome.status == "timeout" or outcome.cancellation_status in (
                                "unknown",
                                "failed",
                            ):
                                halt = "unresolved_job_completion"
                        if (
                            outcome.status != "ok"
                            and outcome.error_code
                            not in {
                                "invalidQuery",
                                "notFound",
                                "resourcesExceeded",
                                "billingTierLimitExceeded",
                                "maximumBytesBilledExceeded",
                            }
                            and halt is None
                        ):
                            halt = "execution_infrastructure_error"
        pending.pop(key, None)
        if observed_billed > policy.billed_byte_cap:
            halt = "aggregate_billed_byte_guard"
        elif observed_cost > policy.estimated_cost_cap:
            halt = "aggregate_execution_cost_guard"
        elif observed_processed > policy.aggregate_byte_cap:
            halt = "aggregate_processed_byte_guard"
        elif halt is None and not budget_ok():
            halt = "remaining_aggregate_guard"
        outcome = replace(
            outcome,
            initial_preflight=initial.get(key),
            immediate_preflight=immediate,
            request_sha256=_request_sha(request),
            initial_preflight_error=initial_errors.get(key),
            immediate_preflight_error=immediate_error,
        )
        journal.append("execution", {"request": request, "outcome": outcome})
        outcomes.append(SharedQueryExecution(key, sql, outcome))
        if request.role == "gold" and outcome.status != "ok" and halt is None:
            halt = f"gold_{outcome.status}"
    seal = journal.seal({"physical_query_count": len(outcomes), "halt_reason": halt})
    return SharedExecutionEvidence(
        campaign_id,
        source_context_sha256,
        policy_sha,
        policy,
        executor.provenance,
        plan.runs,
        tuple(outcomes),
        seal,
        halt,
    )


def verify_shared_execution_journal(evidence: SharedExecutionEvidence, path: Path) -> None:
    """Verify the physical journal, including exact inputs, preflights, jobs and outcomes."""
    from nl2sparql.evaluation.artifacts import _json_value, _read_journal, canonical_json
    from nl2sparql.evaluation.executor import deterministic_job_id

    records, digest, sealed = _read_journal(path)
    if not sealed or digest != evidence.journal_terminal_sha256:
        raise EvaluationError("shared journal terminal mismatch or unsealed journal")
    plan = SharedExecutionPlan(
        evidence.runs, tuple((q.sql_sha256, q.sql) for q in evidence.queries)
    )
    expected_header = _json_value(
        _header(
            plan,
            evidence.campaign_id,
            evidence.source_context_sha256,
            evidence.policy_sha256,
            evidence.executor,
        )
    )
    headers = [r for r in records if r["record_type"] == "shared_header"]
    if len(headers) != 1 or headers[0]["body"] != expected_header:
        raise EvaluationError("shared journal header binding mismatch")
    if records[-1]["body"] != {
        "physical_query_count": len(evidence.queries),
        "halt_reason": evidence.halt_reason,
    }:
        raise EvaluationError("shared journal seal binding mismatch")
    by_key = {q.sql_sha256: q.outcome for q in evidence.queries}
    seen = set()
    stages = {}
    executed = []
    header_seen = False
    initial_closed = False
    for record in records:
        kind, body = record["record_type"], record["body"]
        if kind == "journal_created":
            if record is not records[0]:
                raise EvaluationError("shared journal creation order mismatch")
            continue
        if kind == "shared_header":
            header_seen = True
            continue
        if kind == "terminal_seal":
            continue
        if not header_seen or not isinstance(body, dict):
            raise EvaluationError("shared journal record before header")
        if kind not in {
            "static_error",
            "initial_dry_run",
            "initial_dry_run_error",
            "immediate_dry_run",
            "immediate_dry_run_error",
            "submission_intent",
            "submitted",
            "execution",
        }:
            raise EvaluationError("shared journal unknown record type")
        if kind == "submitted":
            key = body.get("case_id")
            request = plan.request(key) if key in by_key else None
        else:
            request_body = body.get("request")
            if not isinstance(request_body, dict):
                raise EvaluationError("shared journal invalid request")
            key = request_body.get("case_id")
            request = plan.request(key) if key in by_key else None
            if request is None or _json_value(request) != request_body:
                raise EvaluationError("shared journal request binding mismatch")
        if request is None:
            raise EvaluationError("shared journal foreign query")
        outcome = by_key[key]
        slot = (key, kind)
        if slot in seen or key in executed:
            raise EvaluationError("shared journal duplicate or late event")
        seen.add(slot)
        if kind.startswith("initial_") or kind == "static_error":
            if initial_closed or key in stages:
                raise EvaluationError("shared journal initial preflight order mismatch")
            stages[key] = kind
        else:
            initial_closed = True
            if key not in stages:
                raise EvaluationError("shared journal missing initial validation")
        if kind in ("initial_dry_run", "immediate_dry_run"):
            attribute = "initial_preflight" if kind.startswith("initial") else "immediate_preflight"
            if body != {
                "request": _json_value(request),
                "evidence": _json_value(getattr(outcome, attribute)),
            }:
                raise EvaluationError("shared journal preflight binding mismatch")
        elif kind.endswith("dry_run_error"):
            attribute = (
                "initial_preflight_error"
                if kind.startswith("initial")
                else "immediate_preflight_error"
            )
            if body != {"request": _json_value(request), "error": getattr(outcome, attribute)}:
                raise EvaluationError("shared journal preflight error binding mismatch")
        elif kind in ("submission_intent", "submitted"):
            if not outcome.submission_attempted or (key, "immediate_dry_run") not in seen:
                raise EvaluationError("shared journal submission without immediate preflight")
            expected_id = deterministic_job_id(evidence.campaign_id, request)
            expected = {"case_id": key, "role": request.role, "job_id": expected_id}
            if kind == "submission_intent":
                expected.update(
                    request=_json_value(request), preflight=_json_value(outcome.immediate_preflight)
                )
            elif (key, "submission_intent") not in seen:
                raise EvaluationError("shared journal submission without intent")
            if body != expected or outcome.submission_job_id != expected_id:
                raise EvaluationError("shared journal physical job binding mismatch")
        elif kind == "execution":
            if body != {"request": _json_value(request), "outcome": _json_value(outcome)}:
                raise EvaluationError("shared journal outcome binding mismatch")
            if outcome.request_sha256 != hashlib.sha256(canonical_json(request)).hexdigest():
                raise EvaluationError("shared journal outcome request hash mismatch")
            if outcome.submission_attempted != ((key, "submission_intent") in seen):
                raise EvaluationError("shared journal missing submission intent")
            if outcome.submission_acknowledged != ((key, "submitted") in seen):
                raise EvaluationError("shared journal missing submission acknowledgement")
            for attribute, event in (
                ("initial_preflight", "initial_dry_run"),
                ("immediate_preflight", "immediate_dry_run"),
                ("initial_preflight_error", "initial_dry_run_error"),
                ("immediate_preflight_error", "immediate_dry_run_error"),
            ):
                if (getattr(outcome, attribute) is not None) != ((key, event) in seen):
                    raise EvaluationError("shared journal missing preflight event")
            executed.append(key)
    if executed != [q.sql_sha256 for q in evidence.queries]:
        raise EvaluationError("shared journal physical outcome scope/order mismatch")
    operation_types = {
        "immediate_dry_run",
        "immediate_dry_run_error",
        "submission_intent",
        "submitted",
        "execution",
    }
    actual_operations = [
        (
            r["body"].get("case_id")
            if r["record_type"] == "submitted"
            else r["body"]["request"]["case_id"],
            r["record_type"],
        )
        for r in records
        if r["record_type"] in operation_types
    ]
    expected_operations = []
    for query in evidence.queries:
        key, outcome = query.sql_sha256, query.outcome
        if outcome.immediate_preflight is not None:
            expected_operations.append((key, "immediate_dry_run"))
        if outcome.immediate_preflight_error is not None:
            expected_operations.append((key, "immediate_dry_run_error"))
        if outcome.submission_attempted:
            expected_operations.append((key, "submission_intent"))
        if outcome.submission_acknowledged:
            expected_operations.append((key, "submitted"))
        expected_operations.append((key, "execution"))
    if actual_operations != expected_operations:
        raise EvaluationError("shared journal physical operation sequence/order mismatch")


@dataclass(frozen=True)
class SharedRunView:
    """Internal logical projection; never serialized as per-run execution evidence."""

    campaign: SharedExecutionEvidence
    reference: SharedRunReference
    cases: tuple[ExecutionCaseEvidence, ...]

    @property
    def executor(self) -> ExecutorProvenance:
        return self.campaign.executor

    @property
    def status(self) -> str:
        return self.campaign.status


def bind_shared_run(
    run: CanonicalPredictionRun, campaign: SharedExecutionEvidence
) -> SharedRunView:
    """Validate a canonical run against its actual campaign and resolve physical refs."""
    from nl2sparql.evaluation.contracts import ExecutionCaseEvidence
    from nl2sparql.evaluation.execution import _skipped

    expected = plan_shared_campaign((run,)).runs[0]
    actual = next((ref for ref in campaign.runs if ref.run_id == run.run_id), None)
    if actual != expected:
        raise EvaluationError("shared execution prediction binding does not match canonical run")
    queries = {query.sql_sha256: query.outcome for query in campaign.queries}
    cases = tuple(
        ExecutionCaseEvidence(
            case.case_id,
            queries[case.gold_query_sha256],
            queries[case.prediction_query_sha256]
            if case.prediction_query_sha256 is not None
            else _skipped(case.prediction_status),
        )
        for case in actual.cases
    )
    return SharedRunView(campaign, actual, cases)


def shared_measurement_scope(campaign: SharedExecutionEvidence) -> tuple[tuple[str, object], ...]:
    """Campaign totals count physical submissions exactly once; not per-run metrics."""
    from decimal import Decimal

    from nl2sparql.evaluation.artifacts import serialize_shared_execution_evidence

    submitted = tuple(q.outcome for q in campaign.queries if q.outcome.submission_attempted)
    billing_complete = all(q.billed_bytes is not None for q in submitted)
    cost_complete = all(q.cost.amount is not None for q in submitted)
    return (
        ("protocol_id", campaign.protocol_id),
        (
            "campaign_sha256",
            json.loads(serialize_shared_execution_evidence(campaign))["artifact_sha256"],
        ),
        ("source_context_sha256", campaign.source_context_sha256),
        ("measurement_scope", "whole_campaign_unique_physical_jobs"),
        ("physical_query_count", len(campaign.queries)),
        ("physical_submitted_count", len(submitted)),
        (
            "physical_billed_bytes_total",
            sum(q.billed_bytes for q in submitted) if billing_complete else None,
        ),
        (
            "physical_cost_total",
            str(sum((q.cost.amount for q in submitted), Decimal(0))) if cost_complete else None,
        ),
        (
            "physical_latency_ms_total",
            sum(q.latency_ms for q in submitted)
            if all(q.latency_ms is not None for q in submitted)
            else None,
        ),
        (
            "logical_query_references",
            tuple(
                (
                    run.run_id,
                    tuple(
                        (case.case_id, case.gold_query_sha256, case.prediction_query_sha256)
                        for case in run.cases
                    ),
                )
                for run in campaign.runs
            ),
        ),
    )
