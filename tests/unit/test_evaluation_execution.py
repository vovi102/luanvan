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


def _policy(aggregate_cap: int = 100) -> ExecutionPolicy:
    return ExecutionPolicy(
        project="project",
        location="US",
        timeout_seconds=30.0,
        per_query_byte_cap=50,
        aggregate_byte_cap=aggregate_cap,
        estimated_cost_cap=Decimal("1"),
        pricing=PricingPolicy("test", "USD", Decimal("5"), SHA_A),
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


def test_gold_failure_invalidates_evidence_but_prediction_timeout_is_terminal_false() -> None:
    run = _run()
    fake = _fake(run)
    fake.executions[("q1", "gold")] = _execution("error")
    fake.executions[("q2", "prediction")] = _execution("timeout")

    evidence = execute_run(
        run,
        execution_id="exec-1",
        policy=_policy(),
        executor=fake,
        journal=MemoryExecutionJournal(),
    )

    assert evidence.status == "invalid_gold_failure"
    assert evidence.cases[0].gold.status == "error"
    assert evidence.cases[1].prediction.status == "timeout"


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
    assert len(evidence.policy_sha256) == 64
    assert evidence.journal_terminal_sha256 == journal.terminal_sha256
    assert json.loads(canonical_json(BootstrapPolicy()))["samples"] == 10_000
