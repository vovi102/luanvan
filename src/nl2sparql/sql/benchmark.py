from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

from nl2sparql.sql.label_layer import (
    DEFAULT_LOCATION,
    DEFAULT_MAXIMUM_BYTES_BILLED,
)

TOTAL_BENCHMARK_BYTES_CAP = 107_374_182_400
START_DATE_LITERAL = "DATE '2026-05-31'"
END_DATE_LITERAL = "DATE '2026-07-01'"
READ_ONLY_SQL_RE = re.compile(
    r"\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXPORT|CALL)\b",
    re.IGNORECASE,
)


class BenchmarkError(ValueError):
    """Raised when the SQL benchmark contract or live result is invalid."""


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    description: str
    difficulty: str
    sql: str
    requires_window: bool


@dataclass(frozen=True)
class BenchmarkDryRun:
    case_id: str
    estimated_bytes: int


@dataclass(frozen=True)
class BenchmarkPreflight:
    cases: tuple[BenchmarkDryRun, ...]
    total_estimated_bytes: int


@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    passed: bool
    diagnostics: dict[str, Any]
    estimated_bytes: int
    processed_bytes: int
    billed_bytes: int
    wall_latency_ms: float
    server_latency_ms: float | None
    slot_millis: int
    cache_hit: bool


@dataclass(frozen=True)
class BenchmarkReport:
    preflight: BenchmarkPreflight
    results: tuple[BenchmarkResult, ...]

    @property
    def all_passed(self) -> bool:
        return len(self.results) == len(self.preflight.cases) and all(
            result.passed for result in self.results
        )


BENCHMARK_CASES = (
    BenchmarkCase(
        case_id="label_contract",
        description="Stable label view preserves accepted counts, roles, and digest.",
        difficulty="small",
        requires_window=False,
        sql="""WITH stats AS (
  SELECT
    COUNT(*) AS entity_count,
    COUNT(DISTINCT address) AS unique_address_count,
    COUNTIF(address_role = 'operational') AS operational_count,
    COUNTIF(address_role = 'token') AS token_count,
    COUNTIF(address_role = 'treasury') AS treasury_count,
    COUNT(DISTINCT dictionary_sha256) AS digest_count,
    ANY_VALUE(dictionary_sha256) AS dictionary_sha256
  FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`
)
SELECT
  stats.*,
  entity_count = 5135
    AND unique_address_count = 5135
    AND operational_count = 14
    AND token_count = 5091
    AND treasury_count = 30
    AND digest_count = 1
    AND dictionary_sha256 = 'cdc7856df81f2cce61290ef27a8872477f1b77da998a6aa88ca0ed75cc19617e'
    AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="transaction_count",
        description="Canonical transaction facts match the independent raw-source count.",
        difficulty="simple",
        requires_window=True,
        sql="""WITH stats AS (
  SELECT COUNT(*) AS observed_count
  FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(
    DATE '2026-05-31', DATE '2026-07-01'
  )
)
SELECT observed_count, 65621456 AS expected_count,
  observed_count = 65621456 AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="block_count",
        description="Canonical block facts match the independent raw-source count.",
        difficulty="simple",
        requires_window=True,
        sql="""WITH stats AS (
  SELECT COUNT(*) AS observed_count
  FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(
    DATE '2026-05-31', DATE '2026-07-01'
  )
)
SELECT observed_count, 222310 AS expected_count,
  observed_count = 222310 AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="contract_dimension_contract",
        description="Contract dimension is unique and respects its exclusive end bound.",
        difficulty="complex",
        requires_window=False,
        sql="""WITH stats AS (
  SELECT
    COUNT(*) AS entity_count,
    COUNT(DISTINCT address) AS unique_address_count,
    COUNTIF(created_at >= TIMESTAMP(DATE '2026-07-01')) AS end_bound_violations
  FROM `nl2sparql-thesis.nl2sparql_analytics.contract_dimension`(
    DATE '2026-07-01'
  )
)
SELECT stats.*,
  entity_count > 0
    AND entity_count = unique_address_count
    AND end_bound_violations = 0 AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="labeled_transaction_cardinality",
        description="Endpoint label joins preserve transaction cardinality and identity.",
        difficulty="complex",
        requires_window=True,
        sql="""WITH stats AS (
  SELECT
    COUNT(*) AS observed_count,
    COUNT(DISTINCT transaction_hash) AS unique_transaction_count
  FROM `nl2sparql-thesis.nl2sparql_analytics.labeled_transactions`(
    DATE '2026-05-31', DATE '2026-07-01'
  )
)
SELECT stats.*, 65621456 AS expected_count,
  observed_count = 65621456
    AND unique_transaction_count = 65621456 AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="labeled_token_transfer_contract",
        description="Token labels preserve event keys and normalized-value semantics.",
        difficulty="complex",
        requires_window=True,
        sql="""WITH stats AS (
  SELECT
    COUNT(*) AS observed_count,
    COUNT(DISTINCT CONCAT(transaction_hash, '#', CAST(log_index AS STRING)))
      AS unique_event_count,
    COUNTIF(
      normalized_amount IS NOT NULL
      AND (
        value_cast_valid IS NOT TRUE
        OR is_erc20 IS NOT TRUE
        OR COALESCE(is_erc721, FALSE) IS NOT FALSE
        OR token_decimals NOT BETWEEN 0 AND 38
      )
    ) AS precision_violations
  FROM `nl2sparql-thesis.nl2sparql_analytics.labeled_token_transfers`(
    DATE '2026-05-31', DATE '2026-07-01'
  )
)
SELECT stats.*, 125320919 AS expected_count,
  observed_count = 125320919
    AND unique_event_count = 125320919
    AND precision_violations = 0 AS passed
FROM stats""",
    ),
)


def validate_benchmark_cases(
    cases: tuple[BenchmarkCase, ...] = BENCHMARK_CASES,
) -> None:
    """Fail closed for unsafe, ambiguous, or unbounded benchmark definitions."""
    if len(cases) != 6:
        raise BenchmarkError(f"Expected exactly 6 benchmark cases, received {len(cases)}")
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise BenchmarkError("Benchmark case IDs must not contain duplicate values")
    for case in cases:
        if not case.case_id or not case.description:
            raise BenchmarkError("Benchmark case ID and description must not be empty")
        if case.difficulty not in {"small", "simple", "complex"}:
            raise BenchmarkError(f"Unknown benchmark difficulty for {case.case_id}")
        if not case.sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise BenchmarkError(f"Benchmark SQL must be read-only: {case.case_id}")
        if READ_ONLY_SQL_RE.search(case.sql):
            raise BenchmarkError(f"Benchmark SQL must be read-only: {case.case_id}")
        if not re.search(r"\bpassed\b", case.sql, re.IGNORECASE):
            raise BenchmarkError(f"Benchmark case must expose passed: {case.case_id}")
        if case.requires_window and not (
            START_DATE_LITERAL in case.sql and END_DATE_LITERAL in case.sql
        ):
            raise BenchmarkError(f"Benchmark case lacks approved date bounds: {case.case_id}")
        if "`bigquery-public-data." in case.sql:
            raise BenchmarkError(
                f"Benchmark must use managed analytical interfaces: {case.case_id}"
            )


validate_benchmark_cases()


def _query_config(*, dry_run: bool) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        use_legacy_sql=False,
        maximum_bytes_billed=DEFAULT_MAXIMUM_BYTES_BILLED,
    )


def _dry_run_case(client: Any, case: BenchmarkCase, *, location: str) -> int:
    job = client.query(
        case.sql,
        job_config=_query_config(dry_run=True),
        location=location,
    )
    return int(getattr(job, "total_bytes_processed", 0) or 0)


def dry_run_benchmark(
    client: Any,
    *,
    cases: tuple[BenchmarkCase, ...] = BENCHMARK_CASES,
    location: str = DEFAULT_LOCATION,
    per_case_bytes_cap: int = DEFAULT_MAXIMUM_BYTES_BILLED,
    total_bytes_cap: int = TOTAL_BENCHMARK_BYTES_CAP,
) -> BenchmarkPreflight:
    """Dry-run the complete workload and enforce per-case and aggregate caps."""
    validate_benchmark_cases(cases)
    results: list[BenchmarkDryRun] = []
    for case in cases:
        estimated_bytes = _dry_run_case(client, case, location=location)
        if estimated_bytes > per_case_bytes_cap:
            raise BenchmarkError(
                f"{case.case_id} exceeds the 50 GiB per-case cap: {estimated_bytes} bytes"
            )
        results.append(BenchmarkDryRun(case_id=case.case_id, estimated_bytes=estimated_bytes))
    total_estimated_bytes = sum(result.estimated_bytes for result in results)
    if total_estimated_bytes > total_bytes_cap:
        raise BenchmarkError(
            f"Benchmark aggregate estimate exceeds the 100 GiB cap: {total_estimated_bytes} bytes"
        )
    return BenchmarkPreflight(
        cases=tuple(results),
        total_estimated_bytes=total_estimated_bytes,
    )


def _row_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "items"):
        return dict(row.items())
    if hasattr(row, "__dict__"):
        return dict(vars(row))
    raise BenchmarkError(f"Benchmark result row is not mappable: {type(row).__name__}")


def _server_latency_ms(job: Any) -> float | None:
    started = getattr(job, "started", None)
    ended = getattr(job, "ended", None)
    if started is None or ended is None:
        return None
    return (ended - started).total_seconds() * 1000


def _execute_case(
    client: Any,
    case: BenchmarkCase,
    *,
    estimated_bytes: int,
    location: str,
    clock_ns: Callable[[], int],
) -> BenchmarkResult:
    start_ns = clock_ns()
    job = client.query(
        case.sql,
        job_config=_query_config(dry_run=False),
        location=location,
    )
    rows = list(job.result())
    end_ns = clock_ns()
    if len(rows) != 1:
        raise BenchmarkError(f"{case.case_id} must return exactly one row; received {len(rows)}")
    values = _row_mapping(rows[0])
    passed = values.pop("passed", None)
    if not isinstance(passed, bool):
        raise BenchmarkError(f"{case.case_id} must return a boolean passed field")
    if not passed:
        raise BenchmarkError(f"Benchmark assertion failed for {case.case_id}: diagnostics={values}")
    return BenchmarkResult(
        case_id=case.case_id,
        passed=passed,
        diagnostics=values,
        estimated_bytes=estimated_bytes,
        processed_bytes=int(getattr(job, "total_bytes_processed", 0) or 0),
        billed_bytes=int(getattr(job, "total_bytes_billed", 0) or 0),
        wall_latency_ms=(end_ns - start_ns) / 1_000_000,
        server_latency_ms=_server_latency_ms(job),
        slot_millis=int(getattr(job, "slot_millis", 0) or 0),
        cache_hit=bool(getattr(job, "cache_hit", False)),
    )


def execute_benchmark(
    client: Any,
    *,
    cases: tuple[BenchmarkCase, ...] = BENCHMARK_CASES,
    location: str = DEFAULT_LOCATION,
    per_case_bytes_cap: int = DEFAULT_MAXIMUM_BYTES_BILLED,
    total_bytes_cap: int = TOTAL_BENCHMARK_BYTES_CAP,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> BenchmarkReport:
    """Preflight all cases, then execute each after an immediate fresh dry run."""
    preflight = dry_run_benchmark(
        client,
        cases=cases,
        location=location,
        per_case_bytes_cap=per_case_bytes_cap,
        total_bytes_cap=total_bytes_cap,
    )
    results: list[BenchmarkResult] = []
    for case in cases:
        estimated_bytes = _dry_run_case(client, case, location=location)
        if estimated_bytes > per_case_bytes_cap:
            raise BenchmarkError(
                f"{case.case_id} exceeds the 50 GiB per-case cap: {estimated_bytes} bytes"
            )
        results.append(
            _execute_case(
                client,
                case,
                estimated_bytes=estimated_bytes,
                location=location,
                clock_ns=clock_ns,
            )
        )
    return BenchmarkReport(preflight=preflight, results=tuple(results))
