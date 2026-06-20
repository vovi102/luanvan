from decimal import Decimal
from importlib.util import find_spec
from pathlib import Path

import pandas as pd

from nl2sparql.kg.extraction.pilot_extract import (
    PILOT_DATE,
    analyze_edge_cases,
    build_pilot_queries,
    prepare_dataframe_for_csv,
    run_pilot_extraction,
)


def test_pilot_queries_are_bounded_and_select_explicit_columns() -> None:
    queries = build_pilot_queries(PILOT_DATE)

    assert set(queries) == {
        "transactions_pilot.csv",
        "blocks_pilot.csv",
        "token_transfers_pilot.csv",
        "contracts_pilot.csv",
    }
    for sql in queries.values():
        assert "SELECT *" not in sql
        assert "DATE(" in sql
        assert "LIMIT" in sql


def test_pilot_query_limits_match_acceptance_counts() -> None:
    queries = build_pilot_queries(PILOT_DATE)

    assert "LIMIT 100" in queries["transactions_pilot.csv"]
    assert "LIMIT 10" in queries["blocks_pilot.csv"]
    assert "LIMIT 100" in queries["token_transfers_pilot.csv"]
    assert "LIMIT 50" in queries["contracts_pilot.csv"]


def test_prepare_dataframe_for_csv_preserves_decimal_values_as_strings() -> None:
    frame = pd.DataFrame({"value": [Decimal("1000000000000000000.123456789")]})

    prepared = prepare_dataframe_for_csv(frame)

    assert prepared.loc[0, "value"] == "1000000000000000000.123456789"


def test_analyze_edge_cases_detects_expected_transaction_patterns() -> None:
    transactions = pd.DataFrame(
        {
            "to_address": [None, "0xabc", "0xdef", "0xghi"],
            "value": ["0", "1000000000000000000", "999999999999999999999999", "1"],
            "gas_price": ["0", "100", "200", "1"],
            "transaction_type": ["2", "0", "1", None],
        }
    )

    summary = analyze_edge_cases(transactions)

    assert summary["null_to_address"] == 1
    assert summary["zero_value"] == 1
    assert summary["large_integer_value"] == 2
    assert summary["zero_gas_price"] == 1
    assert summary["non_legacy_transaction_type"] == 2


class FakeQueryJob:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def to_dataframe(self) -> pd.DataFrame:
        return self._frame


class FakeBigQueryClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql: str) -> FakeQueryJob:
        self.queries.append(sql)
        return FakeQueryJob(pd.DataFrame({"value": [Decimal("1.25")]}))


def test_run_pilot_extraction_writes_csv_files(tmp_path: Path) -> None:
    client = FakeBigQueryClient()

    outputs = run_pilot_extraction(client, output_dir=tmp_path, force=True)

    assert set(outputs) == {
        "transactions_pilot.csv",
        "blocks_pilot.csv",
        "token_transfers_pilot.csv",
        "contracts_pilot.csv",
    }
    assert len(client.queries) == 4
    assert outputs["transactions_pilot.csv"] == tmp_path / "transactions_pilot.csv"
    assert (tmp_path / "transactions_pilot.csv").read_text(encoding="utf-8").startswith("value")


def test_bigquery_dataframe_dependency_is_available() -> None:
    assert find_spec("db_dtypes") is not None
