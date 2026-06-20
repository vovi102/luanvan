"""Pilot extraction helpers for small BigQuery Ethereum samples."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from google.cloud import bigquery
from loguru import logger

from nl2sparql.kg.extraction.bigquery_smoke import (
    BLOCKS_TABLE,
    CONTRACTS_TABLE,
    TOKEN_TRANSFERS_TABLE,
    TRANSACTIONS_TABLE,
)

PILOT_DATE = "2024-01-15"
DEFAULT_OUTPUT_DIR = Path("data/raw/pilot")
MAX_EXACT_FLOAT_INTEGER = Decimal(2**53 - 1)


class QueryJobLike(Protocol):
    """Minimal BigQuery query job interface used by the pilot extractor."""

    def to_dataframe(self) -> pd.DataFrame:
        """Return query results as a DataFrame."""


class BigQueryClientLike(Protocol):
    """Minimal BigQuery client interface used by the pilot extractor."""

    def query(self, sql: str) -> QueryJobLike:
        """Run a SQL query and return a query job."""


def build_pilot_queries(pilot_date: str = PILOT_DATE) -> dict[str, str]:
    """Build bounded SQL queries for the first BigQuery extraction pilot.

    Args:
        pilot_date: Date filter in YYYY-MM-DD format.

    Returns:
        Mapping from output CSV filename to BigQuery SQL.
    """
    return {
        "transactions_pilot.csv": f"""
SELECT
  `hash`, from_address, to_address, value, gas, gas_price,
  block_number, block_timestamp, transaction_type, receipt_status
FROM `{TRANSACTIONS_TABLE}`
WHERE DATE(block_timestamp) = '{pilot_date}'
LIMIT 100
""".strip(),
        "blocks_pilot.csv": f"""
SELECT number, `hash`, timestamp, miner, gas_used, gas_limit, transaction_count
FROM `{BLOCKS_TABLE}`
WHERE DATE(timestamp) = '{pilot_date}'
LIMIT 10
""".strip(),
        "token_transfers_pilot.csv": f"""
SELECT transaction_hash, from_address, to_address, value, token_address, block_timestamp
FROM `{TOKEN_TRANSFERS_TABLE}`
WHERE DATE(block_timestamp) = '{pilot_date}'
LIMIT 100
""".strip(),
        "contracts_pilot.csv": f"""
SELECT address, is_erc20, is_erc721, block_timestamp
FROM `{CONTRACTS_TABLE}`
WHERE DATE(block_timestamp) = '{pilot_date}'
LIMIT 50
""".strip(),
    }


def prepare_dataframe_for_csv(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a CSV-safe copy that preserves exact BigQuery numeric values.

    BigQuery NUMERIC/BIGNUMERIC values often arrive as ``Decimal`` instances.
    Keeping them as strings avoids precision loss in CSV round-trips.

    Args:
        frame: DataFrame returned by the BigQuery client.

    Returns:
        A copy with Decimal values converted to their exact string form.
    """
    prepared = frame.copy()
    for column in prepared.columns:
        prepared[column] = prepared[column].map(_to_csv_safe_value)
    return prepared


def analyze_edge_cases(transactions: pd.DataFrame) -> dict[str, int]:
    """Summarize transaction edge cases relevant to downstream RML mapping.

    Args:
        transactions: DataFrame with transaction sample rows.

    Returns:
        Count summary for known edge-case patterns.
    """
    summary = {
        "null_to_address": 0,
        "zero_value": 0,
        "large_integer_value": 0,
        "zero_gas_price": 0,
        "non_legacy_transaction_type": 0,
    }
    if "to_address" in transactions:
        summary["null_to_address"] = int(transactions["to_address"].isna().sum())
    if "value" in transactions:
        summary["zero_value"] = _count_decimal_equal(transactions["value"], Decimal("0"))
        summary["large_integer_value"] = _count_decimal_greater_than(
            transactions["value"], MAX_EXACT_FLOAT_INTEGER
        )
    if "gas_price" in transactions:
        summary["zero_gas_price"] = _count_decimal_equal(transactions["gas_price"], Decimal("0"))
    if "transaction_type" in transactions:
        normalized = transactions["transaction_type"].astype("string")
        summary["non_legacy_transaction_type"] = int(
            (normalized.notna() & (normalized != "0")).sum()
        )
    return summary


def write_edge_case_report(summary: dict[str, int], output_path: Path) -> None:
    """Write a Markdown report with pilot edge-case counts.

    Args:
        summary: Output from :func:`analyze_edge_cases`.
        output_path: Destination Markdown path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# BigQuery Pilot Edge Cases",
        "",
        "Generated from the T1.2 BigQuery pilot transaction sample.",
        "",
        f"- Contract creation rows (`to_address` null): {summary.get('null_to_address', 0)}",
        f"- Zero-value transactions: {summary.get('zero_value', 0)}",
        "- Values above the exact IEEE-754 integer range: "
        f"{summary.get('large_integer_value', 0)}",
        f"- Zero gas price rows: {summary.get('zero_gas_price', 0)}",
        "- Typed transactions (`transaction_type` not legacy `0`): "
        f"{summary.get('non_legacy_transaction_type', 0)}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_pilot_extraction(
    client: BigQueryClientLike,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    pilot_date: str = PILOT_DATE,
    force: bool = False,
) -> dict[str, Path]:
    """Run all pilot queries and write CSV files.

    Args:
        client: BigQuery client or compatible fake in tests.
        output_dir: Directory where pilot CSV files should be written.
        pilot_date: Date filter in YYYY-MM-DD format.
        force: Overwrite existing CSV files when true.

    Returns:
        Mapping from output filename to local CSV path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}

    for filename, sql in build_pilot_queries(pilot_date).items():
        output_path = output_dir / filename
        outputs[filename] = output_path
        if output_path.exists() and not force:
            logger.info("Skipping existing pilot CSV: {}", output_path)
            continue

        logger.info("Running BigQuery pilot query for {}", filename)
        frame = client.query(sql).to_dataframe()
        prepare_dataframe_for_csv(frame).to_csv(output_path, index=False)
        logger.info("Wrote {} rows to {}", len(frame), output_path)

    transactions_path = outputs.get("transactions_pilot.csv")
    if transactions_path is not None and transactions_path.exists():
        transactions = pd.read_csv(transactions_path)
        write_edge_case_report(
            analyze_edge_cases(transactions),
            output_dir / "edge_case_summary.md",
        )

    return outputs


def estimate_pilot_query_bytes(
    client: bigquery.Client,
    pilot_date: str = PILOT_DATE,
) -> dict[str, int]:
    """Dry-run pilot queries and return estimated bytes processed per CSV."""
    config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    estimates: dict[str, int] = {}
    for filename, sql in build_pilot_queries(pilot_date).items():
        query_job = client.query(sql, job_config=config)
        estimates[filename] = int(query_job.total_bytes_processed or 0)
    return estimates


def _to_csv_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _count_decimal_equal(values: pd.Series, target: Decimal) -> int:
    count = 0
    for value in values.dropna():
        try:
            if Decimal(str(value)) == target:
                count += 1
        except Exception:
            continue
    return count


def _count_decimal_greater_than(values: pd.Series, threshold: Decimal) -> int:
    count = 0
    for value in values.dropna():
        try:
            if Decimal(str(value)) > threshold:
                count += 1
        except Exception:
            continue
    return count
