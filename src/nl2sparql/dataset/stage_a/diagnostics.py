"""Provider-neutral evidence contracts for Stage A diagnostic execution."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from nl2sparql.dataset.stage_a.evidence import (
    LogicalWitnessResult,
    WitnessDryRun,
    WitnessExecution,
    build_witness_groups,
)
from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries

DIAGNOSTIC_SCHEMA_VERSION = "stage-a-v2-diagnostic-v1"


class DiagnosticError(ValueError):
    """Raised when diagnostic execution or evidence violates its contract."""


@dataclass(frozen=True)
class ProjectBillingState:
    project_id: str
    billing_enabled: bool
    billing_account_name: str


def require_unbilled_project(
    project: str,
    *,
    runner: Callable[..., CompletedProcess[str]] = subprocess.run,
) -> ProjectBillingState:
    """Fail closed unless gcloud reports an unlinked, billing-disabled project."""
    command = [
        "gcloud",
        "billing",
        "projects",
        "describe",
        project,
        "--format=json(projectId,billingEnabled,billingAccountName)",
    ]
    try:
        completed = runner(command, capture_output=True, check=False, text=True)
    except (FileNotFoundError, OSError) as exc:
        raise DiagnosticError("gcloud is required to verify disabled billing") from exc
    if completed.returncode != 0:
        raise DiagnosticError("gcloud billing check failed")
    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise DiagnosticError("gcloud billing check did not return valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise DiagnosticError("gcloud billing check did not return a JSON object")
    if payload.get("projectId") != project:
        raise DiagnosticError("gcloud billing check returned the wrong project")
    billing_enabled = payload.get("billingEnabled")
    if billing_enabled is not False:
        raise DiagnosticError("project billing is enabled or could not be proven disabled")
    billing_account_name = payload.get("billingAccountName")
    if billing_account_name != "":
        raise DiagnosticError("project has a non-empty billing account")
    return ProjectBillingState(
        project_id=project,
        billing_enabled=False,
        billing_account_name="",
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _candidate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    digests = [
        {"record_id": record.get("id"), "record_sha256": record.get("record_sha256")}
        for record in records
    ]
    return {
        "record_count": len(records),
        "artifact_sha256": hashlib.sha256(
            b"".join(_canonical_json(record) + b"\n" for record in records)
        ).hexdigest(),
        "records_sha256": _sha256(digests),
        "record_digests": digests,
    }


def _dry_run_mapping(item: WitnessDryRun) -> dict[str, Any]:
    value = asdict(item)
    value["group_ids"] = list(item.group_ids)
    return value


def _execution_mapping(item: WitnessExecution) -> dict[str, Any]:
    return {
        "group_id": item.group_id,
        "template_id": item.template_id,
        "witness_record_id": item.witness_record_id,
        "row_count": item.row_count,
        "columns": list(item.columns),
        "estimated_bytes": item.estimated_bytes,
        "processed_bytes": item.processed_bytes,
        "billed_bytes": item.billed_bytes,
        "wall_latency_ms": item.wall_latency_ms,
        "server_latency_ms": item.server_latency_ms,
        "slot_millis": item.slot_millis,
        "cache_hit": item.cache_hit,
        "query_id": item.query_id,
        "query_sha256": item.query_sha256,
        "proof_kind": item.proof_kind,
        "group_ids": list(item.group_ids),
        "job_id": item.job_id,
        "location": item.location,
    }


def _logical_mapping(query_id: str, item: LogicalWitnessResult) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "group_id": item.group_id,
        "witness_record_id": item.witness_record_id,
        "row_count": item.row_count,
        "columns": list(item.columns),
    }


class DiagnosticRecorder:
    """Collect verifier observations without influencing verification decisions."""

    def __init__(
        self,
        *,
        project_id: str,
        records: Sequence[Mapping[str, Any]],
        verified_at: str,
    ) -> None:
        self.project_id = project_id
        self.records = records
        self.verified_at = verified_at
        self._billing_state: ProjectBillingState | None = None
        self._initial_dry_runs: list[dict[str, Any]] = []
        self._immediate_dry_runs: list[dict[str, Any]] = []
        self._executions: list[dict[str, Any]] = []
        self._logical_results: list[dict[str, Any]] = []
        self._failure: dict[str, str] | None = None

    def record_billing_state(self, state: ProjectBillingState) -> None:
        self._billing_state = state

    def record_initial_dry_run(self, item: WitnessDryRun) -> None:
        self._initial_dry_runs.append(_dry_run_mapping(item))

    def record_immediate_dry_run(self, item: WitnessDryRun) -> None:
        self._immediate_dry_runs.append(_dry_run_mapping(item))

    def record_execution(self, item: WitnessExecution) -> None:
        self._executions.append(_execution_mapping(item))

    def record_logical_result(self, query_id: str, item: LogicalWitnessResult) -> None:
        self._logical_results.append(_logical_mapping(query_id, item))

    def record_failure(self, gate: str, error: BaseException) -> None:
        if self._failure is None:
            self._failure = {
                "gate": gate,
                "error_type": type(error).__name__,
                "message": str(error),
            }

    def _report(self, status: str) -> dict[str, Any]:
        processed = sum(int(item["processed_bytes"]) for item in self._executions)
        billed = sum(int(item["billed_bytes"]) for item in self._executions)
        cache_hits = sum(item["cache_hit"] is True for item in self._executions)
        billing = None
        if self._billing_state is not None:
            billing = {
                "project_id": self._billing_state.project_id,
                "billing_enabled": self._billing_state.billing_enabled,
                "billing_account_empty": self._billing_state.billing_account_name == "",
            }
        return {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "mode": "diagnostic",
            "status": status,
            "acceptance_authorized": False,
            "project_id": self.project_id,
            "verified_at": self.verified_at,
            "billing": billing,
            "candidate": _candidate(self.records),
            "initial_dry_runs": list(self._initial_dry_runs),
            "immediate_dry_runs": list(self._immediate_dry_runs),
            "executions": list(self._executions),
            "logical_results": list(self._logical_results),
            "summary": {
                "logical_witness_count": len(self._logical_results),
                "physical_query_count": len(self._executions),
                "total_initial_estimated_bytes": sum(
                    int(item["estimated_bytes"]) for item in self._initial_dry_runs
                ),
                "total_immediate_estimated_bytes": sum(
                    int(item["estimated_bytes"]) for item in self._immediate_dry_runs
                ),
                "total_processed_bytes": processed,
                "total_billed_bytes": billed,
                "cache_hit_count": cache_hits,
            },
            "failure": self._failure,
        }

    def complete(self) -> dict[str, Any]:
        if self._failure is not None:
            raise DiagnosticError("cannot complete a failed diagnostic")
        return self._report("passed")

    def failure_report(self) -> dict[str, Any]:
        if self._failure is None:
            raise DiagnosticError("failure report requires a recorded failure")
        return self._report("failed")


def serialize_diagnostic_report(report: Mapping[str, Any]) -> bytes:
    """Serialize a diagnostic report deterministically with a trailing newline."""
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticError(message)


def validate_diagnostic_report(
    report: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    """Validate candidate provenance and complete or retained partial evidence."""
    _require(report.get("schema_version") == DIAGNOSTIC_SCHEMA_VERSION, "diagnostic schema")
    _require(report.get("mode") == "diagnostic", "diagnostic mode")
    _require(report.get("acceptance_authorized") is False, "diagnostic cannot authorize acceptance")
    _require(
        isinstance(report.get("project_id"), str) and bool(report.get("project_id")),
        "diagnostic project is missing",
    )
    status = report.get("status")
    _require(status in {"passed", "failed"}, "diagnostic status")
    if status == "failed":
        failure = report.get("failure")
        _require(isinstance(failure, Mapping), "failed diagnostic requires failure evidence")
        for name in ("gate", "error_type", "message"):
            _require(
                isinstance(failure.get(name), str) and bool(failure[name]),
                f"failed diagnostic requires failure {name}",
            )
    else:
        _require(report.get("failure") is None, "passed diagnostic cannot contain failure")
    expected_candidate = _candidate(records)
    _require(report.get("candidate") == expected_candidate, "candidate digest evidence mismatch")
    billing = report.get("billing")
    if billing is None and status == "failed" and failure["gate"] == "billing_guard":
        _require(
            all(
                report.get(name) == []
                for name in (
                    "initial_dry_runs",
                    "immediate_dry_runs",
                    "executions",
                    "logical_results",
                )
            ),
            "billing guard failure cannot contain provider observations",
        )
    else:
        _require(isinstance(billing, Mapping), "diagnostic billing evidence is missing")
        _require(
            billing.get("project_id") == report["project_id"], "diagnostic billing project mismatch"
        )
        _require(billing.get("billing_enabled") is False, "diagnostic billing must be disabled")
        _require(
            billing.get("billing_account_empty") is True, "diagnostic billing account must be empty"
        )

    queries = build_stage_a_v2_witness_queries(records)
    groups = build_witness_groups(records)
    expected_queries = {query.query_id: query for query in queries}
    expected_groups = {group.group_id: group for group in groups}
    initial = report.get("initial_dry_runs")
    immediate = report.get("immediate_dry_runs")
    executions = report.get("executions")
    logical = report.get("logical_results")
    _require(isinstance(initial, list), "initial physical evidence is missing")
    _require(isinstance(immediate, list), "immediate physical evidence is missing")
    _require(isinstance(executions, list), "execution physical evidence is missing")
    _require(isinstance(logical, list), "logical evidence is missing")
    if status == "passed":
        _require(
            len(initial) == len(immediate) == len(executions) == len(queries),
            "physical query evidence is incomplete",
        )

    def indexed(items: list[Any], label: str) -> dict[str, Mapping[str, Any]]:
        values: dict[str, Mapping[str, Any]] = {}
        for item in items:
            _require(isinstance(item, Mapping), f"{label} evidence is malformed")
            query_id = item.get("query_id")
            _require(isinstance(query_id, str) and query_id in expected_queries, f"{label} query")
            _require(query_id not in values, f"duplicate {label} query")
            values[query_id] = item
        return values

    initial_by_query = indexed(initial, "initial")
    immediate_by_query = indexed(immediate, "immediate")
    execution_by_query = indexed(executions, "execution")
    _require(
        set(execution_by_query) <= set(immediate_by_query) <= set(initial_by_query),
        "physical execution requires initial and immediate evidence",
    )
    for query_id, initial_item in initial_by_query.items():
        query = expected_queries[query_id]
        immediate_item = immediate_by_query.get(query_id)
        execution_item = execution_by_query.get(query_id)
        for item in (initial_item, immediate_item, execution_item):
            if item is None:
                continue
            _require(item.get("query_sha256") == query.query_sha256, "query digest mismatch")
            _require(item.get("group_ids") == list(query.group_ids), "physical membership mismatch")
            _require(item.get("template_id") == query.template_id, "physical template mismatch")
            _require(item.get("proof_kind") == query.proof_kind, "physical proof kind mismatch")
            _require(
                isinstance(item.get("location"), str) and bool(item["location"]),
                "physical location is missing",
            )
        if execution_item is not None:
            _require(execution_item.get("cache_hit") is False, "cache hit is forbidden")
            _require(
                isinstance(execution_item.get("row_count"), int)
                and not isinstance(execution_item["row_count"], bool)
                and execution_item["row_count"] > 0,
                "retained execution must be non-empty",
            )
            columns = execution_item.get("columns")
            _require(
                isinstance(columns, list)
                and bool(columns)
                and all(isinstance(name, str) and bool(name) for name in columns),
                "execution columns are missing",
            )
            _require(
                execution_item.get("estimated_bytes") == immediate_item.get("estimated_bytes"),
                "immediate estimate mismatch",
            )
            _require(
                execution_item["location"]
                == immediate_item["location"]
                == initial_item["location"],
                "physical location mismatch",
            )
        for label, item, names in (
            ("initial", initial_item, ("estimated_bytes",)),
            ("immediate", immediate_item, ("estimated_bytes",)),
            (
                "execution",
                execution_item,
                ("estimated_bytes", "processed_bytes", "billed_bytes", "slot_millis"),
            ),
        ):
            if item is None:
                continue
            for name in names:
                value = item.get(name)
                _require(
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                    f"{label} {name} must be a non-negative integer",
                )
        # The real provider dry runs observed in our evidence have no persisted job ID.
        _require(
            isinstance(initial_item.get("job_id"), str),
            "initial job ID field is missing",
        )
        if immediate_item is not None:
            _require(
                isinstance(immediate_item.get("job_id"), str), "immediate job ID field is missing"
            )
        if execution_item is not None:
            _require(
                isinstance(execution_item.get("job_id"), str) and bool(execution_item["job_id"]),
                "execution job ID is missing",
            )

    logical_by_group: dict[str, Mapping[str, Any]] = {}
    for item in logical:
        _require(isinstance(item, Mapping), "logical evidence is malformed")
        group_id = item.get("group_id")
        _require(isinstance(group_id, str) and group_id in expected_groups, "logical group")
        _require(group_id not in logical_by_group, "duplicate logical group")
        query_id = item.get("query_id")
        _require(
            isinstance(query_id, str)
            and query_id in execution_by_query
            and group_id in expected_queries[query_id].group_ids,
            "logical-to-physical edge mismatch",
        )
        _require(
            item.get("witness_record_id") == expected_groups[group_id].witness_record_id,
            "logical witness mismatch",
        )
        _require(
            isinstance(item.get("row_count"), int)
            and not isinstance(item.get("row_count"), bool)
            and item["row_count"] > 0,
            "logical result must be non-empty",
        )
        _require(
            item.get("columns")
            == [
                name
                for name in execution_by_query[query_id]["columns"]
                if name != "witness_group_id"
            ],
            "logical columns mismatch",
        )
        logical_by_group[group_id] = item
    observed_groups = {
        group_id
        for query_id in execution_by_query
        for group_id in expected_queries[query_id].group_ids
    }
    _require(set(logical_by_group) == observed_groups, "logical coverage is incomplete")
    for query_id, execution in execution_by_query.items():
        _require(
            sum(
                logical_by_group[group_id]["row_count"]
                for group_id in expected_queries[query_id].group_ids
            )
            == execution["row_count"],
            "logical and physical row totals mismatch",
        )
    if status == "passed":
        _require(observed_groups == set(expected_groups), "logical coverage is incomplete")

    summary = report.get("summary")
    _require(isinstance(summary, Mapping), "diagnostic summary is missing")
    _require(summary.get("logical_witness_count") == len(logical), "logical count mismatch")
    _require(summary.get("physical_query_count") == len(executions), "physical count mismatch")
    _require(
        summary.get("total_initial_estimated_bytes")
        == sum(int(item["estimated_bytes"]) for item in initial),
        "initial byte total mismatch",
    )
    _require(
        summary.get("total_immediate_estimated_bytes")
        == sum(int(item["estimated_bytes"]) for item in immediate),
        "immediate byte total mismatch",
    )
    _require(
        summary.get("total_processed_bytes")
        == sum(int(item["processed_bytes"]) for item in executions),
        "processed byte total mismatch",
    )
    _require(
        summary.get("total_billed_bytes") == sum(int(item["billed_bytes"]) for item in executions),
        "billed byte total mismatch",
    )
    _require(summary.get("cache_hit_count") == 0, "cache count mismatch")


def write_diagnostic_report(path: Path, report: Mapping[str, Any]) -> None:
    """Atomically replace one diagnostic report without touching dataset artifacts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(serialize_diagnostic_report(report))
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
