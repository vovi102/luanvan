"""Read-only GoogleSQL verification and bounded BigQuery evidence."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from nl2sparql.dataset.noise.artifacts import jsonl_bytes
from nl2sparql.dataset.testset.contracts import FinalCase, TestSetError

MANAGED_PREFIX = "nl2sparql-thesis.nl2sparql_analytics."
MUTATION_RE = re.compile(
    r"\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXPORT|CALL)\b",
    re.IGNORECASE,
)


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


def validate_sql_text(sql: str) -> None:
    """Reject unsafe or unmanaged SQL before sending it to BigQuery."""
    if not isinstance(sql, str) or not sql.strip():
        raise TestSetError("SQL must not be empty")
    stripped = sql.strip()
    if ";" in stripped or "--" in stripped or "/*" in stripped or "*/" in stripped:
        raise TestSetError("SQL must be one statement without comments")
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        raise TestSetError("SQL must start with SELECT or WITH")
    if MUTATION_RE.search(stripped):
        raise TestSetError("SQL contains a mutation keyword")
    if re.search(r"\bSELECT\s+\*|,\s*\*\b", stripped, re.IGNORECASE):
        raise TestSetError("SQL must project explicit columns")
    tables = re.findall(r"`([^`]+)`", stripped)
    if not tables or any(not table.startswith(MANAGED_PREFIX) for table in tables):
        raise TestSetError("SQL must use managed analytical objects")


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

    evidence_rows: list[LiveEvidenceRecord] = []
    total_processed = 0
    total_billed = 0
    input_hash_rows: list[dict[str, object]] = []
    for case, _initial_dry_run, _estimate in dry_runs:
        immediate_dry_run = _query(client, case, policy, dry_run=True)
        immediate_estimate = int(getattr(immediate_dry_run, "total_bytes_processed", 0) or 0)
        if immediate_estimate > policy.per_query_bytes:
            raise TestSetError(f"{case.id} exceeds per-query budget on immediate preflight")
        started = time.perf_counter()
        job = _query(client, case, policy, dry_run=False)
        row_iterator = job.result()
        rows = list(row_iterator)
        columns = _columns(row_iterator)
        if case.expected_columns and columns != case.expected_columns:
            raise TestSetError(f"{case.id} returned unexpected columns {columns}")
        expected_empty = case.expected_result_size is None
        if not expected_empty and not rows:
            raise TestSetError(f"{case.id} requires a non-empty result")
        if expected_empty and rows:
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
        sql_sha256 = hashlib.sha256(case.sql.encode()).hexdigest()
        evidence_rows.append(
            LiveEvidenceRecord(
                question_id=case.id,
                sql_sha256=sql_sha256,
                row_count=len(rows),
                columns=columns,
                processed_bytes=processed,
                billed_bytes=billed,
                cache_hit=cache_hit,
                job_id=str(getattr(job, "job_id", "")),
                wall_latency_ms=(time.perf_counter() - started) * 1000,
            )
        )
        input_hash_rows.append({"id": case.id, "sql_sha256": sql_sha256})
    if total_processed > policy.total_bytes or total_billed > policy.total_bytes:
        raise TestSetError("aggregate execution bytes exceed budget")
    input_sha256 = hashlib.sha256(jsonl_bytes(input_hash_rows)).hexdigest()
    return LiveEvidence(
        status="ready",
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        records=tuple(evidence_rows),
        total_processed_bytes=total_processed,
        total_billed_bytes=total_billed,
        input_sha256=input_sha256,
    )
