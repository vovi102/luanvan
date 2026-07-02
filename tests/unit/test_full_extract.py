import importlib.util
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from nl2sparql.kg.extraction.full_extract import (
    MAX_BYTES_BILLED,
    assert_within_cost_guard,
    build_full_extract_queries,
    compute_full_extract_date_range,
    load_dictionary_addresses,
    run_full_extract_dry_run,
    run_full_extract_live,
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


class FakeDryRunJob:
    def __init__(self, processed: int) -> None:
        self.total_bytes_processed = processed
        self.total_bytes_billed = processed


class FakeDryRunClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql: str, job_config=None) -> FakeDryRunJob:
        self.queries.append(sql)
        return FakeDryRunJob(1024)


def test_run_full_extract_dry_run_writes_manifest(tmp_path: Path) -> None:
    client = FakeDryRunClient()

    manifest_path = run_full_extract_dry_run(
        client,
        output_dir=tmp_path,
        start_date=date(2026, 5, 27),
        end_date=date(2026, 6, 26),
        labeled_table="project.dataset.labeled_addresses",
        dictionary_count=4520,
    )

    assert manifest_path == tmp_path / "manifest.json"
    assert len(client.queries) == 4
    assert manifest_path.exists()


class FakeLiveResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.pages = [rows]


class FakeLiveJob:
    def __init__(self, rows: list[dict[str, object]], processed: int = 1024) -> None:
        self._rows = rows
        self.total_bytes_processed = processed
        self.total_bytes_billed = processed

    def result(self, page_size: int | None = None) -> FakeLiveResult:
        assert page_size is not None
        return FakeLiveResult(self._rows)


class FakeLiveClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.job_configs: list[object] = []
        self._jobs = [
            FakeLiveJob([{"hash": "0x1", "tier": "tier1"}]),
            FakeLiveJob([{"number": 1, "hash": "0xb"}]),
            FakeLiveJob([{"transaction_hash": "0x1", "log_index": 0}]),
            FakeLiveJob([{"address": "0xabc", "is_erc20": True}]),
        ]

    def query(self, sql: str, job_config=None) -> FakeLiveJob:
        self.queries.append(sql)
        self.job_configs.append(job_config)
        return self._jobs.pop(0)


def test_run_full_extract_live_streams_csvs_and_writes_manifest(tmp_path: Path) -> None:
    client = FakeLiveClient()

    manifest_path = run_full_extract_live(
        client,
        output_dir=tmp_path,
        start_date=date(2026, 5, 27),
        end_date=date(2026, 6, 26),
        labeled_table="project.dataset.labeled_addresses",
        dictionary_count=4520,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = validate_csv_outputs(tmp_path)

    assert len(client.queries) == 4
    assert all(not config.dry_run for config in client.job_configs)
    assert rows == {
        "transactions.csv": 1,
        "blocks.csv": 1,
        "token_transfers.csv": 1,
        "contracts.csv": 1,
    }
    assert manifest["mode"] == "live"
    assert manifest["rows"] == rows


def _load_full_extract_script():
    script_path = Path("scripts/04_bigquery_full_extract.py").resolve()
    spec = importlib.util.spec_from_file_location("bigquery_full_extract_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_extract_cli_force_runs_live_extraction(tmp_path: Path, monkeypatch) -> None:
    module = _load_full_extract_script()
    calls: dict[str, object] = {}

    def fake_client():
        return object()

    def fake_run_live(client, **kwargs):
        calls["client"] = client
        calls["kwargs"] = kwargs
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        return manifest_path

    monkeypatch.setattr(module.bigquery, "Client", fake_client)
    monkeypatch.setattr(module, "run_full_extract_live", fake_run_live)
    monkeypatch.setattr(module, "load_dictionary_addresses", lambda dictionary_path: ["0xabc"])

    result = CliRunner().invoke(
        module.main,
        [
            "--force",
            "--output-dir",
            str(tmp_path),
            "--labeled-table",
            "project.dataset.labeled_addresses",
        ],
    )

    assert result.exit_code == 0
    assert calls["kwargs"]["output_dir"] == tmp_path
    assert calls["kwargs"]["labeled_table"] == "project.dataset.labeled_addresses"
