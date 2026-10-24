"""Behavioral tests for unique physical queries and full logical populations."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nl2sparql.evaluation import artifacts, contracts
from nl2sparql.evaluation.contracts import (
    CanonicalPredictionRun,
    CostEvidence,
    EvaluationError,
    ExecutionPolicy,
    ExecutorProvenance,
    InferenceEvidence,
    PredictionCase,
    PricingPolicy,
    PrivacyEvidence,
    QueryExecution,
    RunProvenance,
)

NOW = datetime(2026, 10, 24, tzinfo=UTC)
SHA = "a" * 64
SQL_A = (
    "SELECT COUNT(*) FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
    "(DATE '2026-06-01', DATE '2026-06-08')"
)
SQL_B = (
    "SELECT COUNT(*) FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`"
    "(DATE '2026-06-01', DATE '2026-06-08')"
)


def make_run(run_id="r1", *, predictions=(SQL_A, SQL_B)):
    return CanonicalPredictionRun(
        "b2",
        run_id,
        42,
        NOW,
        SHA,
        len(predictions),
        RunProvenance(True, True, True, (("catalog", SHA),)),
        (),
        "test",
        1,
        tuple(
            PredictionCase(
                f"q{i}",
                f"Question {i}",
                SQL_A,
                "easy",
                ("test",),
                "ok" if sql is not None else "no_output",
                sql,
                SHA if sql is not None else None,
                None if sql is not None else "no_output",
                InferenceEvidence(1.0, 1, 1, CostEvidence("unmeasured", None, None, None)),
                PrivacyEvidence("documented", "none", None, SHA, SHA),
            )
            for i, sql in enumerate(predictions, 1)
        ),
    )


def make_policy():
    return ExecutionPolicy(
        "project",
        "US",
        30,
        50,
        100,
        Decimal("1"),
        PricingPolicy(
            "test", "USD", Decimal("5"), SHA, minimum_billed_bytes=0, billing_increment_bytes=1
        ),
        100,
    )


def test_plan_deduplicates_exact_sql_across_runs_and_roles_without_losing_cases():
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    plan = plan_shared_campaign((make_run(), make_run("r2")))
    assert len(plan.queries) == 2
    assert len(plan.runs) == 2
    assert [len(run.cases) for run in plan.runs] == [2, 2]
    first = plan.runs[0].cases[0]
    assert first.gold_query_sha256 == first.prediction_query_sha256
    assert plan.request(first.gold_query_sha256).role == "gold"
    assert plan.runs[1].cases[0].gold_query_sha256 == first.gold_query_sha256


def test_shared_codec_round_trip_and_foreign_query_binding_are_rejected(tmp_path: Path):
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    plan = plan_shared_campaign((make_run(),))
    outcome = QueryExecution(
        "guard_blocked",
        None,
        None,
        None,
        CostEvidence("unmeasured", None, None, None),
        None,
        "test_guard",
    )
    query_type = contracts.SharedQueryExecution
    evidence_type = contracts.SharedExecutionEvidence
    policy = make_policy()
    import hashlib

    evidence = evidence_type(
        "campaign",
        SHA,
        hashlib.sha256(artifacts.canonical_json(policy)).hexdigest(),
        policy,
        ExecutorProvenance("fake", "test", "1", True),
        plan.runs,
        tuple(query_type(key, sql, outcome) for key, sql in plan.queries),
        SHA,
        None,
    )
    path = tmp_path / "shared.json"
    path.write_bytes(artifacts.serialize_shared_execution_evidence(evidence))
    loaded = artifacts.load_and_verify_artifact(path)
    assert loaded == evidence
    assert loaded.status == "invalid_gold_failure"
    bad_case = replace(plan.runs[0].cases[0], gold_query_sha256="b" * 64)
    with pytest.raises(EvaluationError, match="query binding"):
        replace(evidence, runs=(replace(plan.runs[0], cases=(bad_case, *plan.runs[0].cases[1:])),))


def make_executor(plan, *, estimates=None):
    from nl2sparql.evaluation.contracts import DryRunEvidence, ResultField
    from nl2sparql.evaluation.executor import ScriptedQueryExecutor
    from nl2sparql.evaluation.result_semantics import canonicalize_result

    dry = {}
    live = {}
    for key, sql in plan.queries:
        request = plan.request(key)
        amount = (estimates or {}).get(sql, 1)
        dry[(key, request.role)] = [DryRunEvidence(amount, NOW, True)] * 2
        live[(key, request.role)] = QueryExecution(
            "ok",
            "job",
            2.0,
            1,
            CostEvidence("estimated", Decimal("0.01"), "USD", "test"),
            canonicalize_result([(1,)], (ResultField("count", "INTEGER"),), order_sensitive=True),
            None,
            processed_bytes=1,
            cache_hit=False,
        )
    return ScriptedQueryExecutor(dry_runs=dry, executions=live)


def execute(runs, *, fake=None, policy=None, journal=None):
    from nl2sparql.evaluation.executor import MemoryExecutionJournal
    from nl2sparql.evaluation.shared_execution import execute_shared_campaign, plan_shared_campaign

    plan = plan_shared_campaign(runs)
    return execute_shared_campaign(
        runs,
        campaign_id="campaign",
        source_context_sha256=SHA,
        policy=policy or make_policy(),
        executor=fake or make_executor(plan),
        journal=journal or MemoryExecutionJournal(),
    )


def test_one_physical_job_is_shared_across_roles_and_replicates():
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    runs = (make_run(), make_run("r2"))
    plan = plan_shared_campaign(runs)
    fake = make_executor(plan)
    evidence = execute(runs, fake=fake)
    assert evidence.status == "complete"
    assert len(evidence.queries) == 2
    assert len([call for call in fake.calls if call.startswith("execute:")]) == 2
    assert len([call for call in fake.calls if call.startswith("dry:")]) == 4
    assert all(len(run.cases) == 2 for run in evidence.runs)


def test_initial_over_cap_prediction_does_not_poison_eligible_aggregate_budget():
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    runs = (make_run(),)
    plan = plan_shared_campaign(runs)
    fake = make_executor(plan, estimates={SQL_B: 1000})
    evidence = execute(
        runs,
        fake=fake,
        policy=replace(make_policy(), aggregate_byte_cap=2, aggregate_billed_byte_cap=2),
    )
    by_sql = {query.sql: query.outcome for query in evidence.queries}
    assert by_sql[SQL_A].status == "ok"
    assert by_sql[SQL_B].status == "guard_blocked"
    assert by_sql[SQL_B].submission_attempted is False
    assert evidence.status == "complete"
    assert len([call for call in fake.calls if call.startswith("execute:")]) == 1


def test_prediction_compile_failure_is_preserved_while_gold_executes():
    from nl2sparql.evaluation.executor import QueryValidationError
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign, sql_digest

    runs = (make_run(),)
    fake = make_executor(plan_shared_campaign(runs))
    fake.dry_runs[(sql_digest(SQL_B), "prediction")][0] = QueryValidationError(
        "notFound", "table was not found"
    )
    evidence = execute(runs, fake=fake)
    by_sql = {query.sql: query.outcome for query in evidence.queries}
    assert by_sql[SQL_A].status == "ok"
    assert by_sql[SQL_B].status == "error"
    assert by_sql[SQL_B].initial_preflight_error == "table was not found"
    assert evidence.status == "complete"


def test_prediction_infrastructure_error_stops_every_live_submission():
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign, sql_digest

    runs = (make_run(),)
    fake = make_executor(plan_shared_campaign(runs))
    fake.dry_runs[(sql_digest(SQL_B), "prediction")][0] = RuntimeError("permission unavailable")
    evidence = execute(runs, fake=fake)
    assert not any(call.startswith("execute:") for call in fake.calls)
    assert evidence.halt_reason == "initial_preflight_infrastructure_error"
    assert evidence.status == "invalid_gold_failure"


def test_gold_guard_failure_stops_before_any_live_job_even_if_discovered_late():
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    runs = (make_run(),)
    fake = make_executor(plan_shared_campaign(runs), estimates={SQL_A: 1000})
    evidence = execute(runs, fake=fake)
    assert not any(call.startswith("execute:") for call in fake.calls)
    assert evidence.status == "invalid_gold_failure"


def test_immediate_prediction_cap_failure_does_not_submit_or_block_other_prediction():
    from nl2sparql.evaluation.contracts import DryRunEvidence
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign, sql_digest

    sql_c = SQL_B + " LIMIT 1"
    runs = (make_run(predictions=(SQL_B, sql_c)),)
    fake = make_executor(plan_shared_campaign(runs))
    fake.dry_runs[(sql_digest(SQL_B), "prediction")][1] = DryRunEvidence(1000, NOW, True)
    evidence = execute(runs, fake=fake)
    by_sql = {query.sql: query.outcome for query in evidence.queries}
    assert by_sql[SQL_A].status == "ok"
    assert by_sql[SQL_B].status == "guard_blocked"
    assert by_sql[sql_c].status == "ok"
    assert evidence.status == "complete"


def test_shared_journal_binds_physical_results_and_rejects_tampered_outcome(tmp_path):
    from nl2sparql.evaluation.artifacts import FileExecutionJournal
    from nl2sparql.evaluation.shared_execution import verify_shared_execution_journal

    path = tmp_path / "shared.jsonl"
    journal = FileExecutionJournal.create(path, header={}, protected_paths=())
    evidence = execute((make_run(),), journal=journal)
    verify_shared_execution_journal(evidence, path)
    changed = replace(
        evidence.queries[0], outcome=replace(evidence.queries[0].outcome, latency_ms=99)
    )
    with pytest.raises(EvaluationError, match="outcome"):
        verify_shared_execution_journal(
            replace(evidence, queries=(changed, *evidence.queries[1:])), path
        )


def test_shared_report_keeps_failed_prediction_in_denominator_and_physical_cost_once():
    from nl2sparql.evaluation.contracts import BootstrapPolicy
    from nl2sparql.evaluation.reporting import build_report
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    runs = (make_run(), make_run("r2"), make_run("r3"))
    evidence = execute(
        runs, fake=make_executor(plan_shared_campaign(runs), estimates={SQL_B: 1000})
    )
    report = build_report(
        primary_run=runs[0],
        primary_evidence=evidence,
        replicate_pairs=tuple((run, evidence) for run in runs[1:]),
        bootstrap_policy=BootstrapPolicy(samples=10),
    )
    assert report.expected_case_count == report.represented_case_count == 2
    assert [case.execution_match for case in report.cases] == [True, False]
    assert all(case.execution_latency_ms is None for case in report.cases)
    assert all(case.gold_execution_latency_ms is None for case in report.cases)
    assert all(case.execution_cost.measurement_status == "unmeasured" for case in report.cases)
    dimension = dict(report.dimensions)["shared_execution"]
    assert dict(dimension)["physical_submitted_count"] == 1
    assert dict(dimension)["physical_billed_bytes_total"] == 1
    assert len({pair[2] for pair in report.replicate_pairs}) == 1


def test_shared_report_rejects_changed_prediction_binding():
    from nl2sparql.evaluation.reporting import build_report

    run = make_run()
    evidence = execute((run,))
    changed = replace(run, cases=(replace(run.cases[0], question="tampered"), *run.cases[1:]))
    with pytest.raises(EvaluationError, match="binding"):
        build_report(primary_run=changed, primary_evidence=evidence)


def test_shared_comparison_uses_logical_gold_order_not_physical_sequence():
    from nl2sparql.evaluation.contracts import BootstrapPolicy, ResultField
    from nl2sparql.evaluation.reporting import build_report
    from nl2sparql.evaluation.result_semantics import canonicalize_result
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    for ordered, expected in ((False, True), (True, False)):
        run = make_run(predictions=(SQL_B,))
        if ordered:
            run = replace(run, cases=(replace(run.cases[0], gold_sql=SQL_A + " ORDER BY 1"),))
        plan = plan_shared_campaign((run,))
        fake = make_executor(plan)
        for key, _sql in plan.queries:
            request = plan.request(key)
            result = canonicalize_result(
                [(1,), (2,), (1,)] if request.role == "gold" else [(1,), (1,), (2,)],
                (ResultField("count", "INTEGER"),),
                order_sensitive=True,
            )
            fake.executions[(key, request.role)] = replace(
                fake.executions[(key, request.role)], result=result
            )
        report = build_report(
            primary_run=run,
            primary_evidence=execute((run,), fake=fake),
            bootstrap_policy=BootstrapPolicy(samples=10),
        )
        assert report.cases[0].execution_match is expected
        assert report.cases[0].answer_scores.f1 == 1.0


def test_journal_write_failure_escapes_before_any_live_submission():
    from nl2sparql.evaluation.executor import MemoryExecutionJournal
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    class BrokenJournal(MemoryExecutionJournal):
        def append(self, kind, body):
            if kind == "initial_dry_run":
                raise OSError("disk full")
            return super().append(kind, body)

    run = make_run()
    fake = make_executor(plan_shared_campaign((run,)))
    with pytest.raises(OSError, match="disk full"):
        execute((run,), fake=fake, journal=BrokenJournal())
    assert not any(call.startswith("execute:") for call in fake.calls)


def test_shared_cli_help_and_unapproved_execute_never_construct_credentials(tmp_path):
    from click.testing import CliRunner

    from nl2sparql.evaluation.cli import create_cli

    def forbidden(*args, **kwargs):
        raise AssertionError("credentials must remain untouched")

    cli = create_cli(bigquery_executor_factory=forbidden)
    runner = CliRunner()
    for command in ("plan-shared", "execute-shared"):
        result = runner.invoke(cli, [command, "--help"])
        assert result.exit_code == 0, result.output
    result = runner.invoke(
        cli,
        [
            "execute-shared",
            "--config",
            str(tmp_path / "absent.json"),
            "--output",
            str(tmp_path / "out.json"),
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ],
    )
    assert result.exit_code != 0
    assert "allow-bigquery" in result.output
    assert not (tmp_path / "journal.jsonl").exists()


def test_shared_cli_validates_canonical_campaign_and_journal(tmp_path):
    from click.testing import CliRunner

    from nl2sparql.evaluation.artifacts import FileExecutionJournal
    from nl2sparql.evaluation.cli import create_cli

    journal = tmp_path / "journal.jsonl"
    evidence = execute(
        (make_run(),), journal=FileExecutionJournal.create(journal, header={}, protected_paths=())
    )
    path = tmp_path / "evidence.json"
    path.write_bytes(artifacts.serialize_shared_execution_evidence(evidence))
    runner = CliRunner()
    assert runner.invoke(create_cli(), ["validate", str(path)]).exit_code != 0
    result = runner.invoke(create_cli(), ["validate", str(path), "--journal", str(journal)])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("mode", ["unknown_billing", "timeout", "over_billed", "over_processed"])
def test_shared_submitted_uncertainty_and_actual_overrun_halt_remaining_jobs(mode):
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    run = make_run()
    plan = plan_shared_campaign((run,))
    fake = make_executor(plan)
    key = plan.queries[0][0]
    slot = (key, "gold")
    original = fake.executions[slot]
    if mode == "unknown_billing":
        outcome = replace(
            original,
            status="unresolved_cost",
            billed_bytes=None,
            cost=CostEvidence("unmeasured", None, None, None),
            error_code="unknown",
        )
    elif mode == "timeout":
        outcome = replace(
            original, status="timeout", error_code="bigquery_timeout", cancellation_status="unknown"
        )
    elif mode == "over_billed":
        outcome = replace(original, billed_bytes=101)
    else:
        outcome = replace(original, processed_bytes=101)
    fake.executions[slot] = outcome
    evidence = execute((run,), fake=fake)
    assert sum(call.startswith("execute:") for call in fake.calls) == 1
    assert evidence.queries[1].outcome.status == "not_run"
    assert evidence.status != "complete"
    if mode.startswith("over_"):
        assert evidence.status == "policy_breach"


def test_shared_artifact_rejects_physical_result_with_lost_sequence():
    from nl2sparql.evaluation.contracts import ResultField
    from nl2sparql.evaluation.result_semantics import canonicalize_result

    evidence = execute((make_run(),))
    result = canonicalize_result(
        [(1,), (2,)], (ResultField("value", "INTEGER"),), order_sensitive=False
    )
    with pytest.raises(EvaluationError, match="sequence"):
        replace(evidence.queries[0], outcome=replace(evidence.queries[0].outcome, result=result))


def test_shared_gold_failure_keeps_full_null_report():
    from nl2sparql.evaluation.contracts import BootstrapPolicy
    from nl2sparql.evaluation.reporting import build_report
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign

    run = make_run()
    evidence = execute(
        (run,), fake=make_executor(plan_shared_campaign((run,)), estimates={SQL_A: 1000})
    )
    report = build_report(
        primary_run=run, primary_evidence=evidence, bootstrap_policy=BootstrapPolicy(samples=10)
    )
    assert report.represented_case_count == 2
    assert all(case.execution_match is None for case in report.cases)
    assert "gold_execution_failure" in report.readiness.scientific_blockers


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "unknown_allowance",
        "billing",
        "stale",
        "wrong_scope",
        "small_reservation",
        "quota_hash",
    ],
)
def test_free_only_live_gates_require_fresh_exact_scope_and_verified_allowance(tmp_path, mutation):
    import hashlib

    from nl2sparql.evaluation.shared_config import require_live_approval

    quota = tmp_path / "quota.json"
    quota.write_text('{"balance": 100}')
    config = {
        "allow_bigquery": True,
        "live_approval": {
            "scope_sha256": SHA,
            "reviewer_id": "conversation-user",
            "approved_at_utc": NOW.isoformat(),
        },
        "free_only": {
            "billing_enabled": False,
            "paid_spend_authorized_usd": "0",
            "project": "project",
            "location": "US",
            "verified_remaining_bytes": 100,
            "reservation_bytes": 100,
            "observed_at_utc": NOW.isoformat(),
            "valid_until_utc": "2026-10-25T00:00:00+00:00",
            "evidence": {
                "path": str(quota),
                "file_sha256": hashlib.sha256(quota.read_bytes()).hexdigest(),
            },
        },
    }
    free = config["free_only"]
    if mutation == "unknown_allowance":
        free["verified_remaining_bytes"] = None
    elif mutation == "billing":
        free["billing_enabled"] = True
    elif mutation == "stale":
        free["observed_at_utc"] = "2026-10-01T00:00:00+00:00"
    elif mutation == "wrong_scope":
        config["live_approval"]["scope_sha256"] = "b" * 64
    elif mutation == "small_reservation":
        free["reservation_bytes"] = 99
    elif mutation == "quota_hash":
        quota.write_text("changed evidence")
    if mutation == "none":
        require_live_approval(config, SHA, make_policy(), now=NOW)
    else:
        with pytest.raises(EvaluationError):
            require_live_approval(config, SHA, make_policy(), now=NOW)


def test_offline_pinned_config_and_cli_plan_validate_all_real_run_hashes(tmp_path):
    import json

    from click.testing import CliRunner

    from nl2sparql.evaluation.cli import create_cli
    from nl2sparql.evaluation.shared_config import load_shared_config

    config_path = Path("configs/t54/shared-campaign-2026-10-24.json")
    config, runs, policy, scope, digest, _ = load_shared_config(config_path)
    assert len(runs) == 12
    assert sum(len(run.cases) for run in runs) == 1200
    assert len(scope["queries"]) == 143
    assert policy.per_query_byte_cap == 24 * 2**30
    result = CliRunner().invoke(
        create_cli(),
        ["plan-shared", "--config", str(config_path), "--output", str(tmp_path / "plan.json")],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["scope_sha256"] == digest
    config["prediction_runs"][0]["file_sha256"] = "b" * 64
    bad = tmp_path / "bad-config.json"
    bad.write_text(json.dumps(config))
    with pytest.raises(EvaluationError, match="hash mismatch"):
        load_shared_config(bad)


def test_unselected_run_unknown_billing_blocks_every_shared_report():
    from nl2sparql.evaluation.contracts import BootstrapPolicy
    from nl2sparql.evaluation.reporting import build_report
    from nl2sparql.evaluation.shared_execution import plan_shared_campaign, sql_digest

    selected = tuple(make_run(f"r{i}", predictions=(SQL_A,)) for i in range(3))
    other = make_run("unselected", predictions=(SQL_B,))
    runs = (*selected, other)
    fake = make_executor(plan_shared_campaign(runs))
    key = (sql_digest(SQL_B), "prediction")
    fake.executions[key] = replace(
        fake.executions[key],
        status="unresolved_cost",
        billed_bytes=None,
        error_code="unknown_billing",
        cost=CostEvidence("unmeasured", None, None, None),
    )
    evidence = execute(runs, fake=fake)
    assert evidence.status == "unresolved_cost"
    report = build_report(
        primary_run=selected[0],
        primary_evidence=evidence,
        replicate_pairs=tuple((run, evidence) for run in selected[1:]),
        bootstrap_policy=BootstrapPolicy(samples=10),
    )
    assert "unresolved_submitted_job_cost" in report.readiness.scientific_blockers


def test_shared_journal_rejects_interleaved_submissions_before_gold_outcome(tmp_path):
    import json

    from nl2sparql.evaluation.executor import MemoryExecutionJournal
    from nl2sparql.evaluation.shared_execution import verify_shared_execution_journal

    journal = MemoryExecutionJournal()
    evidence = execute((make_run(),), journal=journal)
    records = json.loads(artifacts.canonical_json(journal.records))
    header_initial = [
        r for r in records if r["record_type"] in ("shared_header", "initial_dry_run")
    ]
    operations = [
        r
        for r in records
        if r["record_type"] in ("immediate_dry_run", "submission_intent", "submitted")
    ]
    outcomes = [r for r in records if r["record_type"] == "execution"]
    forged = MemoryExecutionJournal()
    for record in (*header_initial, *operations, *outcomes):
        forged.append(record["record_type"], record["body"])
    terminal = forged.seal(records[-1]["body"])
    path = tmp_path / "interleaved.jsonl"
    path.write_bytes(b"".join(artifacts.canonical_json(r) for r in forged.records))
    with pytest.raises(EvaluationError, match="order|sequence"):
        verify_shared_execution_journal(replace(evidence, journal_terminal_sha256=terminal), path)
