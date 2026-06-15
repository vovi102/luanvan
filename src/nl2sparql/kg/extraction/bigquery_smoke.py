"""Smoke queries and dry-run helpers for BigQuery Ethereum access."""

from __future__ import annotations

from google.cloud import bigquery

ETHEREUM_DATASET = "bigquery-public-data.crypto_ethereum"
TRANSACTIONS_TABLE = f"{ETHEREUM_DATASET}.transactions"
BLOCKS_TABLE = f"{ETHEREUM_DATASET}.blocks"
TOKEN_TRANSFERS_TABLE = f"{ETHEREUM_DATASET}.token_transfers"
CONTRACTS_TABLE = f"{ETHEREUM_DATASET}.contracts"

COUNT_TRANSACTIONS_SQL = f"""
SELECT COUNT(*) AS n
FROM `{TRANSACTIONS_TABLE}`
WHERE DATE(block_timestamp) = '2024-01-01'
""".strip()


def build_monthly_extraction_estimate_sql(start_date: str, end_date: str) -> str:
    """Build a bounded dry-run query for estimating transaction extraction cost.

    Args:
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.

    Returns:
        A BigQuery SQL string that selects only columns needed by the first KG pilot.
    """
    return f"""
SELECT `hash`, from_address, to_address, value, block_timestamp
FROM `{TRANSACTIONS_TABLE}`
WHERE DATE(block_timestamp) BETWEEN '{start_date}' AND '{end_date}'
""".strip()


def make_dry_run_config() -> bigquery.QueryJobConfig:
    """Create a BigQuery dry-run job config with cache disabled."""
    return bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)


def estimate_query_bytes(client: bigquery.Client, sql: str) -> int:
    """Return bytes processed for a BigQuery dry-run query."""
    query_job = client.query(sql, job_config=make_dry_run_config())
    return int(query_job.total_bytes_processed or 0)
