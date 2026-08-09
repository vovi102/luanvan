from __future__ import annotations

import re
from dataclasses import dataclass

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
    AND dictionary_sha256 = '190f73a91b7affa8b8396cc189e4a6b332dc6f7f0109037a0d44edb14531c536'
    AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="transaction_count",
        description="Canonical transaction facts match the pinned extraction count.",
        difficulty="simple",
        requires_window=True,
        sql="""WITH stats AS (
  SELECT COUNT(*) AS observed_count
  FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(
    DATE '2026-05-31', DATE '2026-07-01'
  )
)
SELECT observed_count, 4431329 AS expected_count,
  observed_count = 4431329 AS passed
FROM stats""",
    ),
    BenchmarkCase(
        case_id="block_count",
        description="Canonical block facts match the pinned extraction count.",
        difficulty="simple",
        requires_window=True,
        sql="""WITH stats AS (
  SELECT COUNT(*) AS observed_count
  FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(
    DATE '2026-05-31', DATE '2026-07-01'
  )
)
SELECT observed_count, 221548 AS expected_count,
  observed_count = 221548 AS passed
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
SELECT stats.*, 4431329 AS expected_count,
  observed_count = 4431329
    AND unique_transaction_count = 4431329 AS passed
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
SELECT stats.*, 4001230 AS expected_count,
  observed_count = 4001230
    AND unique_event_count = 4001230
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
