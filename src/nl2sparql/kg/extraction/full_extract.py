"""Full BigQuery extraction helpers for the Ethereum KG dataset."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import bigquery

from nl2sparql.kg.extraction.bigquery_smoke import (
    BLOCKS_TABLE,
    CONTRACTS_TABLE,
    TOKEN_TRANSFERS_TABLE,
    TRANSACTIONS_TABLE,
)

DEFAULT_DICTIONARY_PATH = Path("src/nl2sparql/linking/dictionary/entities.json")
DEFAULT_OUTPUT_DIR = Path("data/raw/full")
FULL_OUTPUT_FILENAMES = (
    "transactions.csv",
    "blocks.csv",
    "token_transfers.csv",
    "contracts.csv",
)
MAX_BYTES_BILLED = 100 * 10**9
USD_PER_TIB = 5.0


def compute_full_extract_date_range(today: date | None = None) -> tuple[date, date]:
    """Return the lagged 30-day extraction window.

    The public BigQuery Ethereum dataset can lag behind chain head. Using a
    two-day lag avoids extracting dates that may still be incomplete.
    """
    reference_date = today or date.today()
    end_date = reference_date - timedelta(days=2)
    start_date = end_date - timedelta(days=30)
    return start_date, end_date


def load_dictionary_addresses(dictionary_path: Path = DEFAULT_DICTIONARY_PATH) -> list[str]:
    """Load unique lower-case Ethereum addresses from the entity dictionary."""
    raw_entities: list[dict[str, Any]] = json.loads(dictionary_path.read_text(encoding="utf-8"))
    addresses = {str(entity["address"]).lower() for entity in raw_entities if entity.get("address")}
    return sorted(addresses)


def estimate_bigquery_cost_usd(bytes_processed: int) -> float:
    """Estimate BigQuery on-demand query cost in USD from bytes processed."""
    return (bytes_processed / 2**40) * USD_PER_TIB


def assert_within_cost_guard(
    bytes_processed: int,
    maximum_bytes_billed: int = MAX_BYTES_BILLED,
) -> None:
    """Raise when a query estimate is above the configured BigQuery budget."""
    if bytes_processed > maximum_bytes_billed:
        raise ValueError(
            f"BigQuery estimate {bytes_processed} bytes exceeds maximum_bytes_billed "
            f"{maximum_bytes_billed} bytes"
        )


def build_full_extract_queries(
    start_date: date,
    end_date: date,
    labeled_table: str,
) -> dict[str, str]:
    """Build bounded SQL queries for the T2.3 full extraction.

    Args:
        start_date: Inclusive extraction start date. The generated SQL uses
            BigQuery parameters so this value documents the intended call.
        end_date: Inclusive extraction end date. The generated SQL uses
            BigQuery parameters so this value documents the intended call.
        labeled_table: BigQuery table containing one lower-case `address`
            column loaded from the entity dictionary.
    """
    del start_date, end_date
    labeled_ref = _quote_table(labeled_table)

    transactions_cte = f"""
WITH labeled_addresses AS (
  SELECT LOWER(address) AS address
  FROM {labeled_ref}
),
selected_transactions AS (
  SELECT
    `hash`, from_address, to_address, value, gas, gas_price,
    block_number, block_timestamp, transaction_type, receipt_status,
    CASE
      WHEN LOWER(from_address) IN (SELECT address FROM labeled_addresses)
        OR LOWER(to_address) IN (SELECT address FROM labeled_addresses)
      THEN 'tier1'
      ELSE 'tier2'
    END AS tier
  FROM `{TRANSACTIONS_TABLE}`
  WHERE DATE(block_timestamp) BETWEEN @start_date AND @end_date
    AND (
      LOWER(from_address) IN (SELECT address FROM labeled_addresses)
      OR LOWER(to_address) IN (SELECT address FROM labeled_addresses)
      OR MOD(ABS(FARM_FINGERPRINT(`hash`)), 100) = 0
    )
)
""".strip()

    return {
        "transactions.csv": f"""
{transactions_cte}
SELECT
  `hash`, from_address, to_address, value, gas, gas_price,
  block_number, block_timestamp, transaction_type, receipt_status, tier
FROM selected_transactions
""".strip(),
        "blocks.csv": f"""
{transactions_cte}
SELECT DISTINCT
  b.number, b.`hash`, b.timestamp, b.miner, b.gas_used, b.gas_limit,
  b.transaction_count
FROM `{BLOCKS_TABLE}` AS b
JOIN selected_transactions AS t
  ON b.number = t.block_number
WHERE DATE(b.timestamp) BETWEEN @start_date AND @end_date
""".strip(),
        "token_transfers.csv": f"""
{transactions_cte}
SELECT
  tt.transaction_hash, tt.from_address, tt.to_address, tt.value,
  tt.token_address, tt.block_timestamp, tt.log_index
FROM `{TOKEN_TRANSFERS_TABLE}` AS tt
JOIN selected_transactions AS t
  ON tt.transaction_hash = t.`hash`
WHERE DATE(tt.block_timestamp) BETWEEN @start_date AND @end_date
""".strip(),
        "contracts.csv": f"""
WITH labeled_addresses AS (
  SELECT LOWER(address) AS address
  FROM {labeled_ref}
)
SELECT
  c.address, c.is_erc20, c.is_erc721, c.block_timestamp
FROM `{CONTRACTS_TABLE}` AS c
WHERE DATE(c.block_timestamp) <= @end_date
  AND LOWER(c.address) IN (SELECT address FROM labeled_addresses)
""".strip(),
    }


def _quote_table(table_name: str) -> str:
    if table_name.startswith("`") and table_name.endswith("`"):
        return table_name
    return f"`{table_name}`"


def write_manifest(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    start_date: date | None = None,
    end_date: date | None = None,
    rows: dict[str, int] | None = None,
    bytes_processed: dict[str, int] | None = None,
    bytes_billed: dict[str, int] | None = None,
    mode: str = "dry-run",
    dictionary_path: Path | None = None,
    dictionary_count: int | None = None,
) -> Path:
    """Write full extraction metadata to `manifest.json`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    period_start, period_end = (
        (start_date, end_date)
        if start_date is not None and end_date is not None
        else compute_full_extract_date_range()
    )
    billed = bytes_billed or {}
    total_bytes_billed = sum(billed.values())
    manifest: dict[str, Any] = {
        "mode": mode,
        "extraction_date": datetime.now(UTC).date().isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "data_period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "rows": rows or {},
        "bytes_processed": bytes_processed or {},
        "bytes_billed": billed,
        "total_bytes_billed": total_bytes_billed,
        "estimated_cost_usd": estimate_bigquery_cost_usd(total_bytes_billed),
        "dictionary": {
            "path": str(dictionary_path) if dictionary_path is not None else None,
            "address_count": dictionary_count,
        },
        "source_tables": {
            "transactions": TRANSACTIONS_TABLE,
            "blocks": BLOCKS_TABLE,
            "token_transfers": TOKEN_TRANSFERS_TABLE,
            "contracts": CONTRACTS_TABLE,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def validate_csv_outputs(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, int]:
    """Validate that all full extraction CSV outputs can be read by pandas."""
    rows: dict[str, int] = {}
    for filename in FULL_OUTPUT_FILENAMES:
        csv_path = output_dir / filename
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing expected full extraction output: {csv_path}")
        frame = pd.read_csv(csv_path)
        rows[filename] = len(frame)
    return rows


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "items"):
        return dict(row.items())
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    raise TypeError(f"Unsupported BigQuery row type: {type(row)!r}")


def _csv_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _write_query_results_csv(job: Any, csv_path: Path, page_size: int = 10_000) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    fieldnames: list[str] | None = None
    result = job.result(page_size=page_size)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer: csv.DictWriter[str] | None = None
        for page in result.pages:
            for row in page:
                record = _row_to_dict(row)
                if writer is None:
                    fieldnames = list(record)
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                writer.writerow({key: _csv_value(value) for key, value in record.items()})
                row_count += 1

        if writer is None:
            schema = getattr(result, "schema", None) or getattr(job, "schema", None) or []
            fieldnames = [field.name for field in schema]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()

    return row_count


def run_full_extract_dry_run(
    client: Any,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    start_date: date | None = None,
    end_date: date | None = None,
    labeled_table: str = "project.dataset.labeled_addresses",
    dictionary_path: Path | None = None,
    dictionary_count: int | None = None,
    maximum_bytes_billed: int = MAX_BYTES_BILLED,
) -> Path:
    """Run BigQuery dry-run estimates for all full extraction queries."""
    period_start, period_end = (
        (start_date, end_date)
        if start_date is not None and end_date is not None
        else compute_full_extract_date_range()
    )
    queries = build_full_extract_queries(
        start_date=period_start,
        end_date=period_end,
        labeled_table=labeled_table,
    )
    config = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
        maximum_bytes_billed=maximum_bytes_billed,
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", period_start),
            bigquery.ScalarQueryParameter("end_date", "DATE", period_end),
        ],
    )

    bytes_processed: dict[str, int] = {}
    bytes_billed: dict[str, int] = {}
    for filename, sql in queries.items():
        job = client.query(sql, job_config=config)
        processed = int(getattr(job, "total_bytes_processed", 0) or 0)
        billed = int(getattr(job, "total_bytes_billed", processed) or processed)
        assert_within_cost_guard(processed, maximum_bytes_billed=maximum_bytes_billed)
        bytes_processed[filename] = processed
        bytes_billed[filename] = billed

    assert_within_cost_guard(
        sum(bytes_processed.values()),
        maximum_bytes_billed=maximum_bytes_billed,
    )
    return write_manifest(
        output_dir=output_dir,
        start_date=period_start,
        end_date=period_end,
        rows={},
        bytes_processed=bytes_processed,
        bytes_billed=bytes_billed,
        mode="dry-run",
        dictionary_path=dictionary_path,
        dictionary_count=dictionary_count,
    )


def run_full_extract_live(
    client: Any,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    start_date: date | None = None,
    end_date: date | None = None,
    labeled_table: str = "project.dataset.labeled_addresses",
    dictionary_path: Path | None = None,
    dictionary_count: int | None = None,
    maximum_bytes_billed: int = MAX_BYTES_BILLED,
) -> Path:
    """Run live BigQuery extraction queries and stream results to CSV files."""
    period_start, period_end = (
        (start_date, end_date)
        if start_date is not None and end_date is not None
        else compute_full_extract_date_range()
    )
    queries = build_full_extract_queries(
        start_date=period_start,
        end_date=period_end,
        labeled_table=labeled_table,
    )
    config = bigquery.QueryJobConfig(
        dry_run=False,
        use_query_cache=False,
        maximum_bytes_billed=maximum_bytes_billed,
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", period_start),
            bigquery.ScalarQueryParameter("end_date", "DATE", period_end),
        ],
    )

    rows: dict[str, int] = {}
    bytes_processed: dict[str, int] = {}
    bytes_billed: dict[str, int] = {}
    for filename, sql in queries.items():
        job = client.query(sql, job_config=config)
        rows[filename] = _write_query_results_csv(job, output_dir / filename)
        processed = int(getattr(job, "total_bytes_processed", 0) or 0)
        billed = int(getattr(job, "total_bytes_billed", processed) or processed)
        assert_within_cost_guard(processed, maximum_bytes_billed=maximum_bytes_billed)
        bytes_processed[filename] = processed
        bytes_billed[filename] = billed

    assert_within_cost_guard(
        sum(bytes_processed.values()),
        maximum_bytes_billed=maximum_bytes_billed,
    )
    return write_manifest(
        output_dir=output_dir,
        start_date=period_start,
        end_date=period_end,
        rows=rows,
        bytes_processed=bytes_processed,
        bytes_billed=bytes_billed,
        mode="live",
        dictionary_path=dictionary_path,
        dictionary_count=dictionary_count,
    )
