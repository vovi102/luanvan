import json
from datetime import UTC, datetime
from decimal import Decimal

from nl2sparql.evaluation.artifacts import canonical_json
from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CanonicalPredictionRun,
    CostEvidence,
    DryRunEvidence,
    ExecutionPolicy,
    InferenceEvidence,
    PredictionCase,
    PricingPolicy,
    PrivacyEvidence,
    QueryExecution,
    ResultField,
    RunProvenance,
)
from nl2sparql.evaluation.execution import execute_run
from nl2sparql.evaluation.executor import MemoryExecutionJournal, ScriptedQueryExecutor
from nl2sparql.evaluation.result_semantics import canonicalize_result

SQL = "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = datetime(2026, 9, 26, tzinfo=UTC)


def _cost() -> CostEvidence:
    return CostEvidence("observed", Decimal("0"), "USD", "fake")


def _execution(status: str = "ok") -> QueryExecution:
    result = canonicalize_result(
        [("0x1",)], (ResultField("transaction_hash", "STRING"),), order_sensitive=False
    )
    return QueryExecution(
        status=status,
        job_id="job" if status == "ok" else None,
        latency_ms=1.0 if status == "ok" else None,
        billed_bytes=1 if status == "ok" else None,
        cost=_cost() if status == "ok" else CostEvidence("unmeasured", None, None, None),
        result=result if status == "ok" else None,
        error_code=None if status == "ok" else status,
    )


def _run(*, second_status: str = "ok") -> CanonicalPredictionRun:
    cases = []
    for index, status in enumerate(("ok", second_status), start=1):
        cases.append(
            PredictionCase(
                case_id=f"q{index}",
                question=f"Question {index}",
                gold_sql=SQL,
                difficulty="easy",
                categories=("simple",),
                prediction_status=status,
                predicted_sql=SQL if status == "ok" else None,
                raw_output_sha256=SHA_A if status == "ok" else None,
                error_code=None if status == "ok" else status,
                inference=InferenceEvidence(
                    1.0, None, None, CostEvidence("unmeasured", None, None, None)
                ),
                privacy=PrivacyEvidence("documented", "none", None, SHA_A, SHA_B),
            )
        )
    return CanonicalPredictionRun(
        baseline_id="b0",
        run_id="run-1",
        seed=42,
        generated_at=NOW,
        test_set_sha256=SHA_A,
        test_case_count=2,
        provenance=RunProvenance(True, True, True, (("config", SHA_B),)),
        source_artifacts=(),
        adapter_id="test",
        adapter_schema_version=1,
        cases=tuple(cases),
    )


def _policy(
    aggregate_cap: int = 100, *, aggregate_billed_cap: int | None = None
) -> ExecutionPolicy:
    return ExecutionPolicy(
        project="project",
        location="US",
        timeout_seconds=30.0,
        per_query_byte_cap=50,
        aggregate_byte_cap=aggregate_cap,
        estimated_cost_cap=Decimal("1"),
        pricing=PricingPolicy(
            "test",
            "USD",
            Decimal("5"),
            SHA_A,
            minimum_billed_bytes=0,
            billing_increment_bytes=1,
        ),
        aggregate_billed_byte_cap=aggregate_billed_cap,
    )


def _fake(run: CanonicalPredictionRun) -> ScriptedQueryExecutor:
    dry_runs = {}
    executions = {}
    for case in run.cases:
        for role in ("gold", "prediction"):
            if role == "prediction" and case.prediction_status != "ok":
                continue
            dry_runs[(case.case_id, role)] = [
                DryRunEvidence(1, NOW, True),
                DryRunEvidence(1, NOW, True),
            ]
            executions[(case.case_id, role)] = _execution()
    return ScriptedQueryExecutor(dry_runs=dry_runs, executions=executions)


def test_all_initial_preflights_precede_sequential_immediate_preflight_and_jobs() -> None:
    run = _run()
    fake = _fake(run)
    journal = MemoryExecutionJournal()

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=journal,
    )

    assert evidence.status == "complete"
    assert fake.calls[:4] == [
        "dry:q1:gold",
        "dry:q2:gold",
        "dry:q1:prediction",
        "dry:q2:prediction",
    ]
    assert fake.calls[4:] == [
        "dry:q1:gold",
        "execute:q1:gold",
        "dry:q1:prediction",
        "execute:q1:prediction",
        "dry:q2:gold",
        "execute:q2:gold",
        "dry:q2:prediction",
        "execute:q2:prediction",
    ]
    record_types = [record["record_type"] for record in journal.records]
    assert record_types[-1] == "terminal_seal"
    assert record_types.count("execution") == 4


def test_non_executable_prediction_is_explicitly_skipped_and_kept() -> None:
    run = _run(second_status="no_output")
    fake = _fake(run)
    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert len(evidence.cases) == 2
    assert evidence.cases[1].prediction.status == "skipped_no_output"
    assert all(call != "dry:q2:prediction" for call in fake.calls)


def test_gold_live_failure_invalidates_evidence_and_stops_later_submissions() -> None:
    run = _run()
    fake = _fake(run)
    fake.executions[("q1", "gold")] = _execution("error")

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert evidence.status == "invalid_gold_failure"
    assert evidence.cases[0].gold.status == "error"
    assert evidence.cases[0].prediction.status == "not_run"
    assert evidence.cases[1].gold.status == "not_run"
    assert fake.calls[-1] == "execute:q1:gold"


def test_prediction_timeout_is_terminal_false_and_does_not_stop_later_gold() -> None:
    run = _run()
    fake = _fake(run)
    fake.executions[("q1", "prediction")] = _execution("timeout")

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert evidence.status == "complete"
    assert evidence.cases[0].prediction.status == "timeout"
    assert evidence.cases[1].gold.status == "ok"


def test_gold_initial_dry_run_failure_prevents_every_live_submission() -> None:
    run = _run()
    fake = _fake(run)
    fake.dry_runs[("q2", "gold")][0] = RuntimeError("dry run unavailable")

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert not any(call.startswith("execute:") for call in fake.calls)
    assert evidence.status == "invalid_gold_failure"
    assert evidence.cases[1].gold.status == "error"
    assert evidence.cases[0].gold.status == "not_run"


def test_invalid_gold_sql_is_recorded_and_prevents_live_submission() -> None:
    run = _run()
    run = CanonicalPredictionRun(
        **(
            run.__dict__
            | {
                "cases": (
                    PredictionCase(
                        **(
                            run.cases[0].__dict__
                            | {"gold_sql": "DELETE FROM `project.dataset.table`"}
                        )
                    ),
                    run.cases[1],
                )
            }
        )
    )
    fake = _fake(run)

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert not any(call.startswith("execute:") for call in fake.calls)
    assert evidence.cases[0].gold.status == "error"
    assert evidence.status == "invalid_gold_failure"


def test_aggregate_estimate_guard_blocks_before_any_live_job() -> None:
    run = _run()
    fake = _fake(run)
    for key in fake.dry_runs:
        fake.dry_runs[key][0] = DryRunEvidence(30, NOW, True)

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(aggregate_cap=100),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert not any(call.startswith("execute:") for call in fake.calls)
    assert evidence.status == "invalid_gold_failure"
    assert all(case.gold.status == "guard_blocked" for case in evidence.cases)


def test_separate_aggregate_billed_guard_blocks_before_live_jobs() -> None:
    run = _run()
    fake = _fake(run)

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(aggregate_billed_cap=3),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert not any(call.startswith("execute:") for call in fake.calls)
    assert all(case.gold.status == "guard_blocked" for case in evidence.cases)


def test_observed_billing_overrun_invalidates_gold_and_stops_later_jobs() -> None:
    run = _run()
    fake = _fake(run)
    fake.executions[("q1", "gold")] = QueryExecution(
        "ok",
        "job",
        1.0,
        5,
        _cost(),
        _execution().result,
        None,
    )

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(aggregate_billed_cap=4),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert evidence.cases[0].gold.error_code == "aggregate_billed_byte_cap_exceeded"
    assert evidence.cases[0].prediction.status == "not_run"
    assert evidence.status == "invalid_gold_failure"


def test_larger_immediate_dry_run_rechecks_aggregate_before_submit() -> None:
    run = _run()
    fake = _fake(run)
    for estimates in fake.dry_runs.values():
        estimates[0] = DryRunEvidence(20, NOW, True)
    fake.dry_runs[("q1", "gold")][1] = DryRunEvidence(50, NOW, True)

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(aggregate_cap=100),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert "execute:q1:gold" not in fake.calls
    assert not any(call.startswith("execute:") for call in fake.calls)
    assert evidence.cases[0].gold.status == "guard_blocked"
    assert evidence.cases[0].gold.error_code == "immediate_aggregate_guard"


def test_evidence_binds_policy_executor_and_terminal_journal_hash() -> None:
    run = _run()
    fake = _fake(run)
    journal = MemoryExecutionJournal()
    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=journal,
    )

    assert evidence.executor.kind == "fake"
    assert evidence.executor.synthetic is True
    assert evidence.policy == _policy()
    assert len(evidence.policy_sha256) == 64
    assert evidence.journal_terminal_sha256 == journal.terminal_sha256
    assert json.loads(canonical_json(BootstrapPolicy()))["samples"] == 10_000
