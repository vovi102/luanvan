# T1.2 BigQuery Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible pilot extractor that exports small Ethereum BigQuery samples to CSV and documents observed data edge cases.

**Architecture:** Add a focused `pilot_extract` module under `src/nl2sparql/kg/extraction/` that owns SQL definitions, dry-run configuration, CSV serialization, and lightweight dataframe analysis. Keep the top-level script as a thin CLI wrapper so unit tests can exercise behavior without calling BigQuery.

**Tech Stack:** Python 3.11, `google-cloud-bigquery`, `pandas`, `click`, `pytest`, `ruff`.

---

### Task 1: Pilot SQL Definitions

**Files:**
- Create: `src/nl2sparql/kg/extraction/pilot_extract.py`
- Create: `tests/unit/test_pilot_extract.py`
- Create: `src/nl2sparql/kg/extraction/pilot_extract.sql`

- [x] **Step 1: Write failing tests for SQL safety**

```python
from nl2sparql.kg.extraction.pilot_extract import PILOT_DATE, build_pilot_queries


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
```

- [x] **Step 2: Verify tests fail**

Run: `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest tests/unit/test_pilot_extract.py -q`

Expected: import failure for missing `pilot_extract`.

- [x] **Step 3: Implement SQL definitions**

Create `pilot_extract.py` with constants for the four public BigQuery tables and `build_pilot_queries(pilot_date: str) -> dict[str, str]`.

Create `pilot_extract.sql` containing the same four SQL statements for thesis/reproducibility review.

- [x] **Step 4: Verify tests pass**

Run: `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest tests/unit/test_pilot_extract.py -q`

Expected: SQL tests pass.

### Task 2: CSV Serialization and Edge Case Analysis

**Files:**
- Modify: `src/nl2sparql/kg/extraction/pilot_extract.py`
- Modify: `tests/unit/test_pilot_extract.py`
- Create: `src/nl2sparql/kg/extraction/edge_cases.md`

- [x] **Step 1: Write failing tests for CSV-safe dataframe handling**

```python
from decimal import Decimal

import pandas as pd

from nl2sparql.kg.extraction.pilot_extract import (
    analyze_edge_cases,
    prepare_dataframe_for_csv,
)


def test_prepare_dataframe_for_csv_preserves_decimal_values_as_strings() -> None:
    frame = pd.DataFrame({"value": [Decimal("1000000000000000000.123456789")]})

    prepared = prepare_dataframe_for_csv(frame)

    assert prepared.loc[0, "value"] == "1000000000000000000.123456789"


def test_analyze_edge_cases_detects_expected_transaction_patterns() -> None:
    transactions = pd.DataFrame(
        {
            "to_address": [None, "0xabc", "0xdef"],
            "value": ["0", "1000000000000000000", "999999999999999999999999"],
            "gas_price": ["0", "100", "200"],
            "transaction_type": ["2", "0", "1"],
        }
    )

    summary = analyze_edge_cases(transactions)

    assert summary["null_to_address"] == 1
    assert summary["zero_value"] == 1
    assert summary["zero_gas_price"] == 1
    assert summary["non_legacy_transaction_type"] == 2
```

- [x] **Step 2: Verify tests fail**

Run: `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest tests/unit/test_pilot_extract.py -q`

Expected: missing functions fail.

- [x] **Step 3: Implement helpers and edge-case documentation**

Add `prepare_dataframe_for_csv`, `analyze_edge_cases`, and `write_edge_case_report` to `pilot_extract.py`.

Create `edge_cases.md` documenting contract creation (`to_address` null), zero-value contract calls, large integer values, zero gas price, and typed transactions.

- [x] **Step 4: Verify tests pass**

Run: `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest tests/unit/test_pilot_extract.py -q`

Expected: all pilot unit tests pass.

### Task 3: BigQuery Runner and CLI

**Files:**
- Modify: `src/nl2sparql/kg/extraction/pilot_extract.py`
- Create: `scripts/02_bigquery_pilot_extract.py`
- Modify: `tests/unit/test_pilot_extract.py`

- [x] **Step 1: Write failing tests for runner behavior using a fake client**

```python
from pathlib import Path

import pandas as pd

from nl2sparql.kg.extraction.pilot_extract import run_pilot_extraction


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
        return FakeQueryJob(pd.DataFrame({"value": [1]}))


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
    assert (tmp_path / "transactions_pilot.csv").read_text(encoding="utf-8").startswith("value")
```

- [x] **Step 2: Verify tests fail**

Run: `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest tests/unit/test_pilot_extract.py -q`

Expected: missing `run_pilot_extraction` fails.

- [x] **Step 3: Implement runner and CLI wrapper**

Add `run_pilot_extraction(client, output_dir, pilot_date, force)` to query each SQL, prepare dataframes, and write CSVs under `data/raw/pilot/`.

Create `scripts/02_bigquery_pilot_extract.py` with `click` options `--output-dir`, `--pilot-date`, `--force`, and `--dry-run`.

- [x] **Step 4: Verify tests pass**

Run: `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest tests/unit/test_pilot_extract.py -q`

Expected: runner tests pass.

### Task 4: Notebook Stub and Task Documentation

**Files:**
- Create: `notebooks/03_bq_pilot.ipynb`
- Modify: `docs/tasks/phase-1-pilot/02-bigquery-100rows.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

- [x] **Step 1: Add notebook smoke analysis cells**

Create a notebook that loads CSV files from `data/raw/pilot/`, prints `info()`, `describe()`, null counts, and edge-case subsets.

- [x] **Step 2: Update task status and decision log**

Mark the task as implemented with exact verification commands. Add a decision entry explaining the fixed pilot date, small row limits, decimal-as-string CSV policy, and local data ignore policy.

- [x] **Step 3: Run full verification**

Run:

```bash
PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/pytest -q
PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/ruff check src tests scripts
```

Expected: all tests and lint pass.
