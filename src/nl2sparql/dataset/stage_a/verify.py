"""Bounded live witness verification for deterministic Stage A records."""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from google.cloud import bigquery

from nl2sparql.dataset.generate import validate_stage_a_records
from nl2sparql.dataset.stage_a.evidence import (
    LogicalWitnessResult,
    StageAVerificationReport,
    WitnessDryRun,
    WitnessEvidenceError,
    WitnessExecution,
    WitnessGroup,
    WitnessPreflight,
    WitnessQuery,
)
from nl2sparql.dataset.stage_a.evidence import (
    build_witness_groups as _build_witness_groups,
)
from nl2sparql.dataset.stage_a.planning import build_single_witness_queries
from nl2sparql.dataset.templates import PER_TEMPLATE_BYTES_CAP
from nl2sparql.sql.constants import DEFAULT_LOCATION

TOTAL_WITNESS_BYTES_CAP = 103_079_215_104


class StageAVerificationError(ValueError):
    """Raised when witness planning or live evidence violates the contract."""


def build_witness_groups(records: Sequence[Mapping[str, Any]]) -> tuple[WitnessGroup, ...]:
    """Translate provider-neutral grouping errors into verifier errors."""
    try:
        return _build_witness_groups(records)
    except WitnessEvidenceError as exc:
        raise StageAVerificationError(str(exc)) from exc


def _query_config(*, dry_run: bool, maximum_bytes_billed: int) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        use_legacy_sql=False,
        maximum_bytes_billed=maximum_bytes_billed,
    )


WitnessQueryPlanner = Callable[[Sequence[Mapping[str, Any]]], tuple[WitnessQuery, ...]]


def _dry_run_query(
    client: Any,
    query: WitnessQuery,
    *,
    location: str,
    per_witness_bytes_cap: int,
) -> tuple[int, Any]:
    job = client.query(
        query.sql,
        job_config=_query_config(
            dry_run=True,
            maximum_bytes_billed=per_witness_bytes_cap,
        ),
        location=location,
    )
    return int(getattr(job, "total_bytes_processed", 0) or 0), job


def _enforce_witness_cap(
    query: WitnessQuery, estimated_bytes: int, per_witness_bytes_cap: int
) -> None:
    if estimated_bytes > per_witness_bytes_cap:
        cap_gib = per_witness_bytes_cap / 2**30
        raise StageAVerificationError(
            f"Witness query {query.query_id} ({query.template_id}) exceeds the "
            f"{cap_gib:g} GiB cap: {estimated_bytes} bytes"
        )


def dry_run_witnesses(
    client: Any,
    records: Sequence[Mapping[str, Any]],
    *,
    location: str = DEFAULT_LOCATION,
    per_witness_bytes_cap: int = PER_TEMPLATE_BYTES_CAP,
    total_bytes_cap: int = TOTAL_WITNESS_BYTES_CAP,
    query_planner: WitnessQueryPlanner = build_single_witness_queries,
) -> WitnessPreflight:
    """Dry-run every unique physical witness query before any execution."""
    groups_by_id = {group.group_id: group for group in build_witness_groups(records)}
    try:
        queries = query_planner(records)
    except WitnessEvidenceError as exc:
        raise StageAVerificationError(str(exc)) from exc
    results: list[WitnessDryRun] = []
    for query in queries:
        estimated_bytes, job = _dry_run_query(
            client,
            query,
            location=location,
            per_witness_bytes_cap=per_witness_bytes_cap,
        )
        _enforce_witness_cap(query, estimated_bytes, per_witness_bytes_cap)
        first_group = groups_by_id[query.group_ids[0]]
        results.append(
            WitnessDryRun(
                group_id=first_group.group_id,
                template_id=query.template_id,
                witness_record_id=first_group.witness_record_id,
                estimated_bytes=estimated_bytes,
                query_id=query.query_id,
                query_sha256=query.query_sha256,
                proof_kind=query.proof_kind,
                group_ids=query.group_ids,
                job_id=str(getattr(job, "job_id", "") or ""),
                location=str(getattr(job, "location", location) or location),
            )
        )
    total_estimated_bytes = sum(result.estimated_bytes for result in results)
    if total_estimated_bytes > total_bytes_cap:
        cap_gib = total_bytes_cap / 2**30
        raise StageAVerificationError(
            f"Witness aggregate estimate exceeds the {cap_gib:g} GiB cap: "
            f"{total_estimated_bytes} bytes"
        )
    return WitnessPreflight(witnesses=tuple(results), total_estimated_bytes=total_estimated_bytes)


def _server_latency_ms(job: Any) -> float | None:
    started = getattr(job, "started", None)
    ended = getattr(job, "ended", None)
    if started is None or ended is None:
        return None
    return (ended - started).total_seconds() * 1000


def _row_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "items"):
        return dict(row.items())
    if hasattr(row, "__dict__"):
        return dict(vars(row))
    raise StageAVerificationError(f"Witness result row is not mappable: {type(row).__name__}")


def _logical_results(
    query: WitnessQuery,
    groups_by_id: Mapping[str, WitnessGroup],
    records_by_id: Mapping[str, Mapping[str, Any]],
    templates_by_id: Mapping[str, Mapping[str, Any]],
    rows: list[Any],
    columns: tuple[str, ...],
) -> tuple[LogicalWitnessResult, ...]:
    expected_columns = tuple(templates_by_id[query.template_id]["expected_columns"])
    if query.proof_kind == "single":
        group = groups_by_id[query.group_ids[0]]
        if columns != expected_columns:
            raise StageAVerificationError(
                f"Witness {group.witness_record_id} returned columns {columns}; "
                f"expected {expected_columns}"
            )
        if not rows:
            raise StageAVerificationError(
                f"Witness {group.witness_record_id} requires a non-empty result"
            )
        if group.template_id == "T_COUNT_TX_IN_RANGE":
            transaction_count = _row_mapping(rows[0]).get("transaction_count")
            if (
                not isinstance(transaction_count, int)
                or isinstance(transaction_count, bool)
                or transaction_count <= 0
            ):
                raise StageAVerificationError(
                    f"Witness {group.witness_record_id} requires a positive transaction_count"
                )
        return (
            LogicalWitnessResult(
                group_id=group.group_id,
                witness_record_id=group.witness_record_id,
                row_count=len(rows),
                columns=columns,
            ),
        )
    if query.proof_kind != "tx_hash_batch":
        raise StageAVerificationError(f"Unsupported witness proof kind: {query.proof_kind}")
    batch_columns = ("witness_group_id", *expected_columns)
    if columns != batch_columns:
        raise StageAVerificationError(
            f"Witness batch {query.query_id} returned columns {columns}; expected {batch_columns}"
        )
    rows_by_group: dict[str, dict[str, Any]] = {}
    requested = set(query.group_ids)
    for row in rows:
        values = _row_mapping(row)
        group_id = values.get("witness_group_id")
        if not isinstance(group_id, str) or group_id not in requested:
            raise StageAVerificationError(
                f"Witness batch {query.query_id} returned an unexpected group ID"
            )
        if group_id in rows_by_group:
            raise StageAVerificationError(
                f"Witness batch {query.query_id} returned a duplicate group ID"
            )
        rows_by_group[group_id] = values
    if set(rows_by_group) != requested:
        raise StageAVerificationError(
            f"Witness batch {query.query_id} result membership is incomplete"
        )
    logical_results: list[LogicalWitnessResult] = []
    for group_id in query.group_ids:
        group = groups_by_id[group_id]
        record = records_by_id[group.witness_record_id]
        expected_hash = record["slot_values"]["transaction_hash"]
        if rows_by_group[group_id].get("transaction_hash") != expected_hash:
            raise StageAVerificationError(
                f"Witness batch {query.query_id} returned the wrong transaction hash"
            )
        logical_results.append(
            LogicalWitnessResult(
                group_id=group_id,
                witness_record_id=group.witness_record_id,
                row_count=1,
                columns=expected_columns,
            )
        )
    return tuple(logical_results)


def _execute_witness(
    client: Any,
    query: WitnessQuery,
    groups_by_id: Mapping[str, WitnessGroup],
    records_by_id: Mapping[str, Mapping[str, Any]],
    templates_by_id: Mapping[str, Mapping[str, Any]],
    *,
    immediate_dry_run: WitnessDryRun,
    location: str,
    per_witness_bytes_cap: int,
    clock_ns: Callable[[], int],
) -> WitnessExecution:
    start_ns = clock_ns()
    job = client.query(
        query.sql,
        job_config=_query_config(
            dry_run=False,
            maximum_bytes_billed=per_witness_bytes_cap,
        ),
        location=location,
    )
    row_iterator = job.result()
    rows = list(row_iterator)
    end_ns = clock_ns()
    schema = getattr(row_iterator, "schema", None)
    if schema is None:
        raise StageAVerificationError(
            f"Witness query {query.query_id} result does not expose columns"
        )
    columns = tuple(field.name for field in schema)
    logical_results = _logical_results(
        query,
        groups_by_id,
        records_by_id,
        templates_by_id,
        rows,
        columns,
    )
    cache_hit = bool(getattr(job, "cache_hit", False))
    if cache_hit:
        raise StageAVerificationError(
            f"Witness query {query.query_id} produced an unexpected cache hit"
        )
    first_group = groups_by_id[query.group_ids[0]]
    return WitnessExecution(
        group_id=first_group.group_id,
        template_id=query.template_id,
        witness_record_id=first_group.witness_record_id,
        row_count=len(rows),
        columns=columns,
        estimated_bytes=immediate_dry_run.estimated_bytes,
        processed_bytes=int(getattr(job, "total_bytes_processed", 0) or 0),
        billed_bytes=int(getattr(job, "total_bytes_billed", 0) or 0),
        wall_latency_ms=(end_ns - start_ns) / 1_000_000,
        server_latency_ms=_server_latency_ms(job),
        slot_millis=int(getattr(job, "slot_millis", 0) or 0),
        cache_hit=cache_hit,
        query_id=query.query_id,
        query_sha256=query.query_sha256,
        proof_kind=query.proof_kind,
        group_ids=query.group_ids,
        job_id=str(getattr(job, "job_id", "") or ""),
        location=str(getattr(job, "location", location) or location),
        immediate_dry_run=immediate_dry_run,
        logical_results=logical_results,
    )


def _validate_verified_at(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StageAVerificationError("verified_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise StageAVerificationError("verified_at must include a timezone")


def verify_stage_a(
    client: Any,
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    *,
    verified_at: str,
    location: str = DEFAULT_LOCATION,
    per_witness_bytes_cap: int = PER_TEMPLATE_BYTES_CAP,
    total_bytes_cap: int = TOTAL_WITNESS_BYTES_CAP,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    record_validator: Callable[
        [Sequence[dict[str, Any]], Sequence[dict[str, Any]]], None
    ] = validate_stage_a_records,
    query_planner: WitnessQueryPlanner = build_single_witness_queries,
) -> StageAVerificationReport:
    """Preflight, execute, and propagate non-empty witness proofs."""
    _validate_verified_at(verified_at)
    record_validator(records, templates)
    groups = build_witness_groups(records)
    groups_by_id = {group.group_id: group for group in groups}
    records_by_id = {str(record["id"]): record for record in records}
    try:
        queries = query_planner(records)
    except WitnessEvidenceError as exc:
        raise StageAVerificationError(str(exc)) from exc
    preflight = dry_run_witnesses(
        client,
        records,
        location=location,
        per_witness_bytes_cap=per_witness_bytes_cap,
        total_bytes_cap=total_bytes_cap,
        query_planner=query_planner,
    )
    preflight_by_query = {item.query_id: item for item in preflight.witnesses}
    templates_by_id = {template["id"]: template for template in templates}
    executions: list[WitnessExecution] = []
    for query in queries:
        estimated_bytes, dry_run_job = _dry_run_query(
            client,
            query,
            location=location,
            per_witness_bytes_cap=per_witness_bytes_cap,
        )
        _enforce_witness_cap(query, estimated_bytes, per_witness_bytes_cap)
        initial = preflight_by_query.get(query.query_id)
        if (
            initial is None
            or initial.query_sha256 != query.query_sha256
            or initial.group_ids != query.group_ids
        ):
            raise StageAVerificationError(
                f"Witness query {query.query_id} changed after initial preflight"
            )
        first_group = groups_by_id[query.group_ids[0]]
        immediate_dry_run = WitnessDryRun(
            group_id=first_group.group_id,
            template_id=query.template_id,
            witness_record_id=first_group.witness_record_id,
            estimated_bytes=estimated_bytes,
            query_id=query.query_id,
            query_sha256=query.query_sha256,
            proof_kind=query.proof_kind,
            group_ids=query.group_ids,
            job_id=str(getattr(dry_run_job, "job_id", "") or ""),
            location=str(getattr(dry_run_job, "location", location) or location),
        )
        executions.append(
            _execute_witness(
                client,
                query,
                groups_by_id,
                records_by_id,
                templates_by_id,
                immediate_dry_run=immediate_dry_run,
                location=location,
                per_witness_bytes_cap=per_witness_bytes_cap,
                clock_ns=clock_ns,
            )
        )
    executions_by_group: dict[str, tuple[WitnessExecution, LogicalWitnessResult]] = {}
    for execution in executions:
        for result in execution.logical_results:
            if result.group_id in executions_by_group:
                raise StageAVerificationError(
                    f"Witness group {result.group_id} has multiple physical proofs"
                )
            executions_by_group[result.group_id] = (execution, result)
    if set(executions_by_group) != set(groups_by_id):
        raise StageAVerificationError("Physical witness plan does not cover every logical group")
    verified_records: list[dict[str, Any]] = []
    for candidate in records:
        record = copy.deepcopy(candidate)
        group = groups_by_id[record["witness_group_id"]]
        execution, logical_result = executions_by_group[group.group_id]
        mode = "live_exact" if record["id"] == group.witness_record_id else "live_limit_monotonic"
        record["verification"] = {
            "mode": mode,
            "non_empty": True,
            "witness_group_id": group.group_id,
            "witness_record_id": group.witness_record_id,
            "witness_row_count": logical_result.row_count,
            "estimated_bytes": execution.estimated_bytes,
            "processed_bytes": execution.processed_bytes,
            "billed_bytes": execution.billed_bytes,
            "wall_latency_ms": execution.wall_latency_ms,
            "server_latency_ms": execution.server_latency_ms,
            "slot_millis": execution.slot_millis,
            "cache_hit": execution.cache_hit,
            "physical_query_id": execution.query_id,
            "query_sha256": execution.query_sha256,
            "job_id": execution.job_id,
            "location": execution.location,
            "verified_at": verified_at,
        }
        verified_records.append(record)
    return StageAVerificationReport(
        preflight=preflight,
        witnesses=tuple(executions),
        records=tuple(verified_records),
    )
