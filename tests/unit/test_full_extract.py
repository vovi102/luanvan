from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from nl2sparql.kg.extraction.full_extract import (
    MAX_BYTES_BILLED,
    assert_within_cost_guard,
    build_full_extract_queries,
    compute_full_extract_date_range,
    load_dictionary_addresses,
    validate_csv_outputs,
    write_manifest,
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


def test_write_manifest_records_rows_cost_and_period(tmp_path: Path) -> None:
    manifest_path = write_manifest(
        output_dir=tmp_path,
        start_date=date(2026, 5, 27),
        end_date=date(2026, 6, 26),
        rows={"transactions.csv": 2},
        bytes_processed={"transactions.csv": 1024},
        bytes_billed={"transactions.csv": 2048},
        mode="dry-run",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["mode"] == "dry-run"
    assert manifest["data_period"] == {"start": "2026-05-27", "end": "2026-06-26"}
    assert manifest["rows"]["transactions.csv"] == 2
    assert manifest["bytes_billed"]["transactions.csv"] == 2048
    assert manifest["estimated_cost_usd"] > 0


def test_validate_csv_outputs_confirms_pandas_can_read_expected_files(tmp_path: Path) -> None:
    pd.DataFrame({"hash": ["0x1"]}).to_csv(tmp_path / "transactions.csv", index=False)
    pd.DataFrame({"number": [1]}).to_csv(tmp_path / "blocks.csv", index=False)
    pd.DataFrame({"transaction_hash": ["0x1"]}).to_csv(
        tmp_path / "token_transfers.csv",
        index=False,
    )
    pd.DataFrame({"address": ["0xabc"]}).to_csv(tmp_path / "contracts.csv", index=False)

    rows = validate_csv_outputs(tmp_path)

    assert rows == {
        "transactions.csv": 1,
        "blocks.csv": 1,
        "token_transfers.csv": 1,
        "contracts.csv": 1,
    }
