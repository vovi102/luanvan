from datetime import date
import json
from pathlib import Path

import pytest

from nl2sparql.kg.extraction.full_extract import (
    MAX_BYTES_BILLED,
    assert_within_cost_guard,
    build_full_extract_queries,
    compute_full_extract_date_range,
    load_dictionary_addresses,
)


def test_load_dictionary_addresses_deduplicates_and_lowercases(tmp_path: Path) -> None:
    dictionary_path = tmp_path / "entities.json"
    dictionary_path.write_text(
        json.dumps(
            [
                {"address": "0xABCDEF0000000000000000000000000000000000"},
                {"address": "0xabcdef0000000000000000000000000000000000"},
                {"address": "0x1234500000000000000000000000000000000000"},
            ]
        ),
        encoding="utf-8",
    )

    addresses = load_dictionary_addresses(dictionary_path)

    assert addresses == [
        "0x1234500000000000000000000000000000000000",
        "0xabcdef0000000000000000000000000000000000",
    ]


def test_compute_full_extract_date_range_uses_lagged_30_day_window() -> None:
    start_date, end_date = compute_full_extract_date_range(today=date(2026, 6, 28))

    assert start_date.isoformat() == "2026-05-27"
    assert end_date.isoformat() == "2026-06-26"


def test_full_extract_queries_use_dictionary_filter_and_background_sample() -> None:
    queries = build_full_extract_queries(
        start_date=date(2026, 5, 27),
        end_date=date(2026, 6, 26),
        labeled_table="project.dataset.labeled_addresses",
    )

    assert set(queries) == {
        "transactions.csv",
        "blocks.csv",
        "token_transfers.csv",
        "contracts.csv",
    }
    transactions_sql = queries["transactions.csv"]
    assert "SELECT *" not in transactions_sql
    assert "`bigquery-public-data.crypto_ethereum.transactions`" in transactions_sql
    assert "`project.dataset.labeled_addresses`" in transactions_sql
    assert "FARM_FINGERPRINT" in transactions_sql
    assert "tier1" in transactions_sql
    assert "tier2" in transactions_sql
    assert "DATE(block_timestamp) BETWEEN @start_date AND @end_date" in transactions_sql


def test_cost_guard_rejects_queries_above_budget() -> None:
    with pytest.raises(ValueError, match="exceeds maximum_bytes_billed"):
        assert_within_cost_guard(MAX_BYTES_BILLED + 1)
