"""Full BigQuery extraction helpers for the Ethereum KG dataset."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

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
    addresses = {
        str(entity["address"]).lower()
        for entity in raw_entities
        if entity.get("address")
    }
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
