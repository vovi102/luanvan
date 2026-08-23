"""Read-only GoogleSQL verification and bounded BigQuery evidence."""

from __future__ import annotations

import hashlib
import itertools
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from nl2sparql.dataset.noise.artifacts import jsonl_bytes
from nl2sparql.dataset.testset.contracts import FinalCase, TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text

MAX_RESULT_PREVIEW_ROWS = 1_000


@dataclass(frozen=True)
class SqlPolicy:
    """Immutable BigQuery safety and budget policy."""

    per_query_bytes: int = 20 * 2**30
    total_bytes: int = 64 * 2**30
    location: str = "US"


@dataclass(frozen=True)
class LiveEvidenceRecord:
    """Evidence for one verified final-test query."""

    question_id: str
    sql_sha256: str
    row_count: int
    columns: tuple[str, ...]
    processed_bytes: int
    billed_bytes: int
    cache_hit: bool
    job_id: str
    wall_latency_ms: float


@dataclass(frozen=True)
class LiveEvidence:
    """Hash-bound evidence for an entire verification run."""

    status: str
    generated_at: str
    records: tuple[LiveEvidenceRecord, ...]
    total_processed_bytes: int
    total_billed_bytes: int
    input_sha256: str


def _query_config(policy: SqlPolicy, *, dry_run: bool) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        use_legacy_sql=False,
        maximum_bytes_billed=policy.per_query_bytes,
    )


def _query(client: Any, case: FinalCase, policy: SqlPolicy, *, dry_run: bool) -> Any:
    return client.query(
        case.sql,
        job_config=_query_config(policy, dry_run=dry_run),
        location=policy.location,
    )


def _columns(row_iterator: Any) -> tuple[str, ...]:
    schema = getattr(row_iterator, "schema", None)
    if schema is None:
        raise TestSetError("BigQuery result does not expose a schema")
    return tuple(field.name for field in schema)


def _bounded_result_count(row_iterator: Any) -> int:
    """Inspect at most a bounded preview while preserving BigQuery's total count."""
    total_rows = getattr(row_iterator, "total_rows", None)
    limit = MAX_RESULT_PREVIEW_ROWS if total_rows is not None else MAX_RESULT_PREVIEW_ROWS + 1
    preview = list(itertools.islice(iter(row_iterator), limit))
    if total_rows is None:
        if len(preview) > MAX_RESULT_PREVIEW_ROWS:
            raise TestSetError("result count unavailable beyond bounded preview")
        return len(preview)
    count = int(total_rows)
    if count < len(preview):
        raise TestSetError("BigQuery result count is inconsistent with its preview")
    return count


def evidence_input_sha256(rows: Iterable[tuple[str, str]]) -> str:
    """Hash a case-ID/SQL-hash set independently of caller ordering."""
    payload = [
        {"id": question_id, "sql_sha256": sql_sha256} for question_id, sql_sha256 in sorted(rows)
    ]
    return hashlib.sha256(jsonl_bytes(payload)).hexdigest()


def verify_sql(
    client: Any,
    cases: Sequence[FinalCase],
    policy: SqlPolicy | None = None,
) -> LiveEvidence:
    """Preflight and execute read-only SQL cases under the configured caps."""
    policy = SqlPolicy() if policy is None else policy
    if not cases:
        raise TestSetError("at least one SQL case is required")
    for case in cases:
        validate_sql_text(case.sql)
        if not case.expected_columns:
            raise TestSetError(f"{case.id} must declare expected columns")
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise TestSetError("SQL case IDs must be unique")

    dry_runs: list[tuple[FinalCase, Any, int]] = []
    total_estimate = 0
    for case in cases:
        job = _query(client, case, policy, dry_run=True)
        estimate = int(getattr(job, "total_bytes_processed", 0) or 0)
        if estimate > policy.per_query_bytes:
            raise TestSetError(f"{case.id} exceeds per-query budget")
        total_estimate += estimate
        dry_runs.append((case, job, estimate))
    if total_estimate > policy.total_bytes:
        raise TestSetError("aggregate dry-run estimate exceeds budget")

    immediate_runs: list[tuple[FinalCase, int]] = []
    immediate_total = 0
    for case, _initial_dry_run, _estimate in dry_runs:
        immediate_dry_run = _query(client, case, policy, dry_run=True)
        immediate_estimate = int(getattr(immediate_dry_run, "total_bytes_processed", 0) or 0)
        if immediate_estimate > policy.per_query_bytes:
            raise TestSetError(f"{case.id} exceeds per-query budget on immediate preflight")
        immediate_total += immediate_estimate
        immediate_runs.append((case, immediate_estimate))
    if immediate_total > policy.total_bytes:
        raise TestSetError("immediate aggregate dry-run estimate exceeds budget")

    evidence_rows: list[LiveEvidenceRecord] = []
    total_processed = 0
    total_billed = 0
    input_hash_rows: list[tuple[str, str]] = []
    for case, _immediate_estimate in immediate_runs:
        started = time.perf_counter()
        job = _query(client, case, policy, dry_run=False)
        row_iterator = job.result()
        columns = _columns(row_iterator)
        row_count = _bounded_result_count(row_iterator)
        if case.expected_columns and columns != case.expected_columns:
            raise TestSetError(f"{case.id} returned unexpected columns {columns}")
        expected_empty = case.expected_result_size is None
        if not expected_empty and row_count == 0:
            raise TestSetError(f"{case.id} requires a non-empty result")
        if expected_empty and row_count != 0:
            raise TestSetError(f"{case.id} was marked expected-empty but returned rows")
        cache_hit = bool(getattr(job, "cache_hit", False))
        if cache_hit:
            raise TestSetError(f"{case.id} unexpectedly used query cache")
        processed = int(getattr(job, "total_bytes_processed", 0) or 0)
        billed = int(getattr(job, "total_bytes_billed", 0) or 0)
        if processed > policy.per_query_bytes or billed > policy.per_query_bytes:
            raise TestSetError(f"{case.id} exceeded execution budget")
        total_processed += processed
        total_billed += billed
        if total_processed > policy.total_bytes or total_billed > policy.total_bytes:
            raise TestSetError("aggregate execution bytes exceed budget")
        sql_sha256 = hashlib.sha256(case.sql.encode()).hexdigest()
        evidence_rows.append(
            LiveEvidenceRecord(
                question_id=case.id,
                sql_sha256=sql_sha256,
                row_count=row_count,
                columns=columns,
                processed_bytes=processed,
                billed_bytes=billed,
                cache_hit=cache_hit,
                job_id=str(getattr(job, "job_id", "")),
                wall_latency_ms=(time.perf_counter() - started) * 1000,
            )
        )
        input_hash_rows.append((case.id, sql_sha256))
    input_sha256 = evidence_input_sha256(input_hash_rows)
    return LiveEvidence(
        status="ready",
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        records=tuple(evidence_rows),
        total_processed_bytes=total_processed,
        total_billed_bytes=total_billed,
        input_sha256=input_sha256,
    )
