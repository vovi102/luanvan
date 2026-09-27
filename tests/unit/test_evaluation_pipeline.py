import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from nl2sparql.evaluation import (
    B0AdaptRequest,
    adapt_baseline_artifacts,
    build_report,
    compare_reports,
    execute_run,
    load_and_verify_artifact,
)
from nl2sparql.evaluation.artifacts import (
    FileExecutionJournal,
    canonical_json,
    publish_immutable,
    serialize_comparison_report,
    serialize_evaluation_report,
    serialize_execution_evidence,
    serialize_prediction_run,
)
from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CostEvidence,
    DryRunEvidence,
    QueryExecution,
    ResultField,
)
from nl2sparql.evaluation.executor import ScriptedQueryExecutor
from nl2sparql.evaluation.result_semantics import canonicalize_result

SQL = "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
NOW = datetime(2026, 9, 26, tzinfo=UTC)


def _native_b0(tmp_path: Path) -> B0AdaptRequest:
    gold = {
        "ambiguity_flag": False,
        "categories": ["entity_lookup"],
        "cq_ids": ["CQ01"],
        "difficulty": "easy",
        "evidence_sha256": hashlib.sha256(SQL.encode()).hexdigest(),
        "expected_result_size": 1,
        "id": "q1",
        "nl": "Question",
        "pool_b_writer": "writer",
        "pool_c_reviewers": ["reviewer"],
        "schema_elements": ["transaction_facts.transaction_hash"],
        "source": "author",
        "sql": SQL,
        "verified_at": "2026-09-26T00:00:00Z",
        "verified_executable": True,
    }
    test_set = tmp_path / "test.jsonl"
    test_payload = (json.dumps(gold, sort_keys=True) + "\n").encode()
    test_set.write_bytes(test_payload)
    test_sha = hashlib.sha256(test_payload).hexdigest()
    prediction = {
        "case_id": "q1",
        "predicted_sql": SQL,
        "template_id": "T1",
        "match_mode": "seed",
        "exact_match": True,
        "structural_match": True,
        "latency_ms": 1.0,
        "rejection_reason": None,
    }
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(json.dumps(prediction, sort_keys=True) + "\n", encoding="utf-8")
    report_body = {
        "schema_version": 1,
        "case_count": 1,
        "matched_count": 1,
        "input_sha256": test_sha,
        "synthetic": True,
        "config_sha256": "b" * 64,
    }
    report = tmp_path / "native-report.json"
    report.write_bytes(
        canonical_json(
            report_body | {"report_sha256": hashlib.sha256(canonical_json(report_body)).hexdigest()}
        )
    )
    return B0AdaptRequest(test_set, predictions, report, "run-1", synthetic=True)


def _execution() -> QueryExecution:
    result = canonicalize_result(
        [("0x1",)], (ResultField("transaction_hash", "STRING"),), order_sensitive=False
    )
    return QueryExecution(
        "ok",
        "job",
        1.0,
        1,
        CostEvidence("estimated", Decimal("0"), "USD", "test"),
        result,
        None,
    )


def test_synthetic_native_to_comparison_pipeline_is_deterministic_and_blocked(
    tmp_path: Path,
) -> None:
    run = adapt_baseline_artifacts(_native_b0(tmp_path))
    run_path = tmp_path / "run.json"
    publish_immutable(run_path, serialize_prediction_run(run))
    loaded_run = load_and_verify_artifact(run_path)
    request_keys = (("q1", "gold"), ("q1", "prediction"))
    executor = ScriptedQueryExecutor(
        dry_runs={
            key: [DryRunEvidence(1, NOW, True), DryRunEvidence(1, NOW, True)]
            for key in request_keys
        },
        executions={key: _execution() for key in request_keys},
    )
    from nl2sparql.evaluation.contracts import ExecutionPolicy, PricingPolicy

    policy = ExecutionPolicy(
        "project",
        "EU",
        30,
        100,
        200,
        Decimal("1"),
        PricingPolicy("test", "USD", Decimal("5"), "a" * 64),
    )
    journal = FileExecutionJournal.create(
        tmp_path / "execution.jsonl", header={"kind": "synthetic"}, protected_paths=(run_path,)
    )
    evidence = execute_run(
        loaded_run,
        execution_id="exec-1",
        policy=policy,
        executor=executor,
        journal=journal,
    )
    evidence_path = tmp_path / "evidence.json"
    publish_immutable(evidence_path, serialize_execution_evidence(evidence))
    loaded_evidence = load_and_verify_artifact(evidence_path)
    bootstrap = BootstrapPolicy(samples=100, seed=42)
    report = build_report(
        primary_run=loaded_run,
        primary_evidence=loaded_evidence,
        bootstrap_policy=bootstrap,
    )
    second = build_report(
        primary_run=loaded_run,
        primary_evidence=loaded_evidence,
        bootstrap_policy=bootstrap,
    )
    comparison = compare_reports(report, second, bootstrap_policy=bootstrap)

    assert serialize_evaluation_report(report) == serialize_evaluation_report(second)
    assert serialize_comparison_report(comparison) == serialize_comparison_report(
        compare_reports(report, second, bootstrap_policy=bootstrap)
    )
    assert report.readiness.implementation_status == "ready"
    assert {"synthetic_input", "fake_executor"} <= set(report.readiness.scientific_blockers)
