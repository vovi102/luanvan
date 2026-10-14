"""Provider-neutral contracts for Stage A v2 diagnostic evidence."""

from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a.diagnostics import (
    DiagnosticError,
    DiagnosticRecorder,
    ProjectBillingState,
    require_unbilled_project,
    serialize_diagnostic_report,
    validate_diagnostic_report,
)
from nl2sparql.dataset.stage_a.evidence import (
    LogicalWitnessResult,
    WitnessDryRun,
    WitnessExecution,
    build_witness_groups,
)
from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries
from nl2sparql.dataset.stage_a_v2 import generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates


def test_require_unbilled_project_uses_exact_private_gcloud_query() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "projectId": "nl2sparql-thesis",
                    "billingEnabled": False,
                    "billingAccountName": "",
                }
            ),
            stderr="private diagnostic detail",
        )

    state = require_unbilled_project("nl2sparql-thesis", runner=runner)

    assert state == ProjectBillingState("nl2sparql-thesis", False, "")
    assert calls == [
        (
            [
                "gcloud",
                "billing",
                "projects",
                "describe",
                "nl2sparql-thesis",
                "--format=json(projectId,billingEnabled,billingAccountName)",
            ],
            {"capture_output": True, "check": False, "text": True},
        )
    ]


@pytest.mark.parametrize(
    ("payload", "returncode", "error", "message"),
    [
        (
            {"projectId": "nl2sparql-thesis", "billingEnabled": True, "billingAccountName": ""},
            0,
            None,
            "billing is enabled",
        ),
        (
            {
                "projectId": "nl2sparql-thesis",
                "billingEnabled": False,
                "billingAccountName": "billingAccounts/123",
            },
            0,
            None,
            "billing account",
        ),
        ("not-json", 0, None, "valid JSON"),
        (
            {"projectId": "other", "billingEnabled": False, "billingAccountName": ""},
            0,
            None,
            "project",
        ),
        ({}, 1, None, "gcloud billing check failed"),
        ({}, 0, FileNotFoundError("gcloud"), "gcloud is required"),
    ],
)
def test_require_unbilled_project_fails_closed(
    payload: object, returncode: int, error: Exception | None, message: str
) -> None:
    def runner(command, **kwargs):
        if error is not None:
            raise error
        stdout = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="secret")

    with pytest.raises(DiagnosticError, match=message):
        require_unbilled_project("nl2sparql-thesis", runner=runner)


@pytest.fixture(scope="module")
def diagnostic_inputs():
    templates = load_templates()
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    records = generate_stage_a_v2_records(templates, pools)
    return records, templates


def _successful_report(records, templates):
    groups_by_id = {group.group_id: group for group in build_witness_groups(records)}
    templates_by_id = {template["id"]: template for template in templates}
    recorder = DiagnosticRecorder(
        project_id="nl2sparql-thesis",
        records=records,
        verified_at="2026-10-14T00:00:00+00:00",
    )
    recorder.record_billing_state(ProjectBillingState("nl2sparql-thesis", False, ""))
    for index, query in enumerate(build_stage_a_v2_witness_queries(records), start=1):
        group = groups_by_id[query.group_ids[0]]
        initial = WitnessDryRun(
            group_id=group.group_id,
            template_id=query.template_id,
            witness_record_id=group.witness_record_id,
            estimated_bytes=index,
            query_id=query.query_id,
            query_sha256=query.query_sha256,
            proof_kind=query.proof_kind,
            group_ids=query.group_ids,
            job_id=f"initial-{index}",
            location="US",
        )
        immediate = replace(initial, estimated_bytes=index + 1, job_id=f"immediate-{index}")
        recorder.record_initial_dry_run(initial)
        recorder.record_immediate_dry_run(immediate)
        logical_results = tuple(
            LogicalWitnessResult(
                group_id=group_id,
                witness_record_id=groups_by_id[group_id].witness_record_id,
                row_count=1,
                columns=tuple(templates_by_id[query.template_id]["expected_columns"]),
            )
            for group_id in query.group_ids
        )
        execution = WitnessExecution(
            group_id=group.group_id,
            template_id=query.template_id,
            witness_record_id=group.witness_record_id,
            row_count=len(query.group_ids),
            columns=(
                ("witness_group_id", *templates_by_id[query.template_id]["expected_columns"])
                if query.proof_kind != "single"
                else tuple(templates_by_id[query.template_id]["expected_columns"])
            ),
            estimated_bytes=immediate.estimated_bytes,
            processed_bytes=index + 2,
            billed_bytes=index + 3,
            wall_latency_ms=float(index),
            server_latency_ms=float(index) / 2,
            slot_millis=index + 4,
            cache_hit=False,
            query_id=query.query_id,
            query_sha256=query.query_sha256,
            proof_kind=query.proof_kind,
            group_ids=query.group_ids,
            job_id=f"execute-{index}",
            location="US",
            immediate_dry_run=immediate,
            logical_results=logical_results,
        )
        recorder.record_execution(execution)
        for result in logical_results:
            recorder.record_logical_result(query.query_id, result)
    return recorder.complete()


def test_diagnostic_report_records_physical_metrics_once_and_all_logical_edges(
    diagnostic_inputs,
) -> None:
    records, templates = diagnostic_inputs
    report = _successful_report(records, templates)

    validate_diagnostic_report(report, records)
    assert report["mode"] == "diagnostic"
    assert report["status"] == "passed"
    assert report["acceptance_authorized"] is False
    assert report["summary"]["logical_witness_count"] == 206
    assert report["summary"]["physical_query_count"] == 126
    assert report["summary"]["cache_hit_count"] == 0
    assert report["summary"]["total_processed_bytes"] == sum(range(3, 129))
    assert report["summary"]["total_billed_bytes"] == sum(range(4, 130))
    assert len(report["initial_dry_runs"]) == 126
    assert len(report["immediate_dry_runs"]) == 126
    assert len(report["executions"]) == 126
    assert len(report["logical_results"]) == 206
    assert json.loads(serialize_diagnostic_report(report)) == report


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report["executions"].pop(), "physical"),
        (
            lambda report: report["executions"][0].__setitem__("query_sha256", "0" * 64),
            "query",
        ),
        (lambda report: report["logical_results"].pop(), "logical"),
        (
            lambda report: report["candidate"].__setitem__("records_sha256", "0" * 64),
            "candidate",
        ),
        (
            lambda report: report["summary"].__setitem__("total_processed_bytes", -1),
            "processed",
        ),
        (lambda report: report["executions"][0].__setitem__("cache_hit", True), "cache"),
    ],
)
def test_diagnostic_report_validation_rejects_tampering(
    diagnostic_inputs, mutation, message: str
) -> None:
    records, templates = diagnostic_inputs
    report = copy.deepcopy(_successful_report(records, templates))
    mutation(report)

    with pytest.raises(DiagnosticError, match=message):
        validate_diagnostic_report(report, records)


def test_failure_report_preserves_first_failed_gate(diagnostic_inputs) -> None:
    records, _ = diagnostic_inputs
    recorder = DiagnosticRecorder(
        project_id="nl2sparql-thesis",
        records=records,
        verified_at="2026-10-14T00:00:00+00:00",
    )
    recorder.record_failure("initial_preflight", ValueError("quota exhausted"))
    recorder.record_failure("execution", RuntimeError("later failure"))

    report = recorder.failure_report()

    assert report["status"] == "failed"
    assert report["failure"] == {
        "gate": "initial_preflight",
        "error_type": "ValueError",
        "message": "quota exhausted",
    }
    assert report["acceptance_authorized"] is False


def test_successful_report_accepts_provider_dry_runs_without_persistent_job_ids(diagnostic_inputs):
    records, templates = diagnostic_inputs
    report = _successful_report(records, templates)
    for dry_run in report["initial_dry_runs"] + report["immediate_dry_runs"]:
        dry_run["job_id"] = ""
    validate_diagnostic_report(report, records)


def _partial_failed_report():
    return json.loads(
        Path("docs/evidence/stage-a-v2-supported-intents-diagnostic.json").read_text()
    )


def test_failed_diagnostic_validates_exact_candidate_and_partial_observations(diagnostic_inputs):
    records, _ = diagnostic_inputs
    validate_diagnostic_report(_partial_failed_report(), records)
    with pytest.raises(DiagnosticError, match="candidate"):
        validate_diagnostic_report(_partial_failed_report(), [])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.__setitem__("candidate", {"bad": "digest"}),
        lambda report: report.pop("executions"),
        lambda report: report.__setitem__("billing", None),
        lambda report: report["executions"][0].__setitem__("query_sha256", "0" * 64),
        lambda report: report["executions"][0].__setitem__("job_id", ""),
        lambda report: report["executions"][0].__setitem__("cache_hit", True),
        lambda report: report["logical_results"].pop(),
        lambda report: report["summary"].__setitem__("total_processed_bytes", -1),
        lambda report: report["immediate_dry_runs"].clear(),
        lambda report: report["executions"][0].__setitem__("row_count", 0),
        lambda report: report["logical_results"][0].__setitem__("row_count", 2),
        lambda report: report["logical_results"][0].__setitem__("columns", ["invented"]),
    ],
)
def test_failed_diagnostic_rejects_corrupted_partial_evidence(diagnostic_inputs, mutation):
    records, _ = diagnostic_inputs
    report = _partial_failed_report()
    mutation(report)
    with pytest.raises(DiagnosticError):
        validate_diagnostic_report(report, records)


def test_billing_guard_failure_allows_no_observations_but_still_binds_candidate(diagnostic_inputs):
    records, _ = diagnostic_inputs
    recorder = DiagnosticRecorder(
        project_id="nl2sparql-thesis",
        records=records,
        verified_at="2026-10-14T00:00:00+00:00",
    )
    recorder.record_failure("billing_guard", DiagnosticError("billing enabled"))
    report = recorder.failure_report()
    validate_diagnostic_report(report, records)
    report["candidate"] = {}
    with pytest.raises(DiagnosticError, match="candidate"):
        validate_diagnostic_report(report, records)
