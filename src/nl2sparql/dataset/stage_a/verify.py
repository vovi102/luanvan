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
    StageAVerificationReport,
    WitnessDryRun,
    WitnessEvidenceError,
    WitnessExecution,
    WitnessGroup,
    WitnessPreflight,
)
from nl2sparql.dataset.stage_a.evidence import (
    build_witness_groups as _build_witness_groups,
)
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


def _dry_run_group(
    client: Any,
    group: WitnessGroup,
    *,
    location: str,
    per_witness_bytes_cap: int,
) -> int:
    job = client.query(
        group.sql,
        job_config=_query_config(
            dry_run=True,
            maximum_bytes_billed=per_witness_bytes_cap,
        ),
        location=location,
    )
    return int(getattr(job, "total_bytes_processed", 0) or 0)


def _enforce_witness_cap(
    group: WitnessGroup, estimated_bytes: int, per_witness_bytes_cap: int
) -> None:
    if estimated_bytes > per_witness_bytes_cap:
        cap_gib = per_witness_bytes_cap / 2**30
        raise StageAVerificationError(
            f"Witness {group.group_id} ({group.template_id}) exceeds the "
            f"{cap_gib:g} GiB cap: {estimated_bytes} bytes"
        )


def dry_run_witnesses(
    client: Any,
    records: Sequence[Mapping[str, Any]],
    *,
    location: str = DEFAULT_LOCATION,
    per_witness_bytes_cap: int = PER_TEMPLATE_BYTES_CAP,
    total_bytes_cap: int = TOTAL_WITNESS_BYTES_CAP,
) -> WitnessPreflight:
    """Dry-run every unique witness before any Stage A execution."""
    groups = build_witness_groups(records)
    results: list[WitnessDryRun] = []
    for group in groups:
        estimated_bytes = _dry_run_group(
            client,
            group,
            location=location,
            per_witness_bytes_cap=per_witness_bytes_cap,
        )
        _enforce_witness_cap(group, estimated_bytes, per_witness_bytes_cap)
        results.append(
            WitnessDryRun(
                group_id=group.group_id,
                template_id=group.template_id,
                witness_record_id=group.witness_record_id,
                estimated_bytes=estimated_bytes,
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


def _execute_witness(
    client: Any,
    group: WitnessGroup,
    template: Mapping[str, Any],
    *,
    estimated_bytes: int,
    location: str,
    per_witness_bytes_cap: int,
    clock_ns: Callable[[], int],
) -> WitnessExecution:
    start_ns = clock_ns()
    job = client.query(
        group.sql,
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
            f"Witness {group.witness_record_id} result does not expose columns"
        )
    columns = tuple(field.name for field in schema)
    expected_columns = tuple(template["expected_columns"])
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
    cache_hit = bool(getattr(job, "cache_hit", False))
    if cache_hit:
        raise StageAVerificationError(
            f"Witness {group.witness_record_id} produced an unexpected cache hit"
        )
    return WitnessExecution(
        group_id=group.group_id,
        template_id=group.template_id,
        witness_record_id=group.witness_record_id,
        row_count=len(rows),
        columns=columns,
        estimated_bytes=estimated_bytes,
        processed_bytes=int(getattr(job, "total_bytes_processed", 0) or 0),
        billed_bytes=int(getattr(job, "total_bytes_billed", 0) or 0),
        wall_latency_ms=(end_ns - start_ns) / 1_000_000,
        server_latency_ms=_server_latency_ms(job),
        slot_millis=int(getattr(job, "slot_millis", 0) or 0),
        cache_hit=cache_hit,
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
) -> StageAVerificationReport:
    """Preflight, execute, and propagate non-empty witness proofs."""
    _validate_verified_at(verified_at)
    record_validator(records, templates)
    groups = build_witness_groups(records)
    preflight = dry_run_witnesses(
        client,
        records,
        location=location,
        per_witness_bytes_cap=per_witness_bytes_cap,
        total_bytes_cap=total_bytes_cap,
    )
    templates_by_id = {template["id"]: template for template in templates}
    executions: list[WitnessExecution] = []
    for group in groups:
        estimated_bytes = _dry_run_group(
            client,
            group,
            location=location,
            per_witness_bytes_cap=per_witness_bytes_cap,
        )
        _enforce_witness_cap(group, estimated_bytes, per_witness_bytes_cap)
        executions.append(
            _execute_witness(
                client,
                group,
                templates_by_id[group.template_id],
                estimated_bytes=estimated_bytes,
                location=location,
                per_witness_bytes_cap=per_witness_bytes_cap,
                clock_ns=clock_ns,
            )
        )
    groups_by_id = {group.group_id: group for group in groups}
    executions_by_group = {execution.group_id: execution for execution in executions}
    verified_records: list[dict[str, Any]] = []
    for candidate in records:
        record = copy.deepcopy(candidate)
        group = groups_by_id[record["witness_group_id"]]
        execution = executions_by_group[group.group_id]
        mode = "live_exact" if record["id"] == group.witness_record_id else "live_limit_monotonic"
        record["verification"] = {
            "mode": mode,
            "non_empty": True,
            "witness_group_id": group.group_id,
            "witness_record_id": group.witness_record_id,
            "witness_row_count": execution.row_count,
            "estimated_bytes": execution.estimated_bytes,
            "processed_bytes": execution.processed_bytes,
            "billed_bytes": execution.billed_bytes,
            "wall_latency_ms": execution.wall_latency_ms,
            "server_latency_ms": execution.server_latency_ms,
            "slot_millis": execution.slot_millis,
            "cache_hit": execution.cache_hit,
            "verified_at": verified_at,
        }
        verified_records.append(record)
    return StageAVerificationReport(
        preflight=preflight,
        witnesses=tuple(executions),
        records=tuple(verified_records),
    )
