# T2.3 BigQuery Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe, reproducible full BigQuery extraction scaffold for one month of Ethereum data, with dry-run cost checks before any real export.

**Architecture:** Add a `full_extract` module next to the existing `pilot_extract` module. Keep pure helpers testable without network access: dictionary address loading, date range computation, SQL generation, cost estimation, output schema validation, CSV writing, and manifest writing. The CLI script will instantiate the real BigQuery client only at the boundary and will require `--force` for live extraction.

**Tech Stack:** Python 3.11, Click, google-cloud-bigquery, pandas, pytest, project-local `uv`.

---

### Task 1: Full extraction pure helpers

**Files:**
- Create: `src/nl2sparql/kg/extraction/full_extract.py`
- Test: `tests/unit/test_full_extract.py`

- [ ] **Step 1: Write failing tests for address loading and date range**

```python
from datetime import date
import json
from pathlib import Path

from nl2sparql.kg.extraction.full_extract import (
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
```

- [ ] **Step 2: Run RED**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest tests/unit/test_full_extract.py -q
```

Expected: fail because `nl2sparql.kg.extraction.full_extract` does not exist.

- [ ] **Step 3: Implement minimal helper code**

Add `DEFAULT_DICTIONARY_PATH`, `DEFAULT_OUTPUT_DIR`, `compute_full_extract_date_range()`, and `load_dictionary_addresses()`.

- [ ] **Step 4: Run GREEN**

Run the same focused pytest command. Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/kg/extraction/full_extract.py tests/unit/test_full_extract.py
git commit -m "feat(kg): add full extraction helpers"
```

### Task 2: SQL generation and cost guard

**Files:**
- Modify: `src/nl2sparql/kg/extraction/full_extract.py`
- Modify: `tests/unit/test_full_extract.py`
- Create: `src/nl2sparql/kg/extraction/full_extract.sql`

- [ ] **Step 1: Write failing tests for query shape and cost guard**

```python
from datetime import date

import pytest

from nl2sparql.kg.extraction.full_extract import (
    MAX_BYTES_BILLED,
    assert_within_cost_guard,
    build_full_extract_queries,
)


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
```

- [ ] **Step 2: Run RED**

Expected: fail because functions/constants are missing.

- [ ] **Step 3: Implement SQL builder and guard**

Add:
- `MAX_BYTES_BILLED = 100 * 10**9`
- `USD_PER_TIB = 5.0`
- `estimate_bigquery_cost_usd(bytes_processed: int) -> float`
- `assert_within_cost_guard(bytes_processed: int, maximum_bytes_billed: int = MAX_BYTES_BILLED) -> None`
- `build_full_extract_queries(start_date, end_date, labeled_table) -> dict[str, str]`

The SQL must use the dictionary temp table for tier-1 address matches and deterministic 1% tier-2 background sample.

- [ ] **Step 4: Add static SQL reference file**

Write `src/nl2sparql/kg/extraction/full_extract.sql` documenting the generated query strategy with `@start_date`, `@end_date`, and a labeled-address table placeholder.

- [ ] **Step 5: Run GREEN**

Run focused pytest. Expected: all full extraction tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/nl2sparql/kg/extraction/full_extract.py src/nl2sparql/kg/extraction/full_extract.sql tests/unit/test_full_extract.py
git commit -m "feat(kg): add guarded full extraction SQL"
```

### Task 3: Manifest and local CSV validation

**Files:**
- Modify: `src/nl2sparql/kg/extraction/full_extract.py`
- Modify: `tests/unit/test_full_extract.py`

- [ ] **Step 1: Write failing tests for manifest and CSV read check**

```python
import json
from datetime import date
from pathlib import Path

import pandas as pd

from nl2sparql.kg.extraction.full_extract import (
    validate_csv_outputs,
    write_manifest,
)


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
        tmp_path / "token_transfers.csv", index=False
    )
    pd.DataFrame({"address": ["0xabc"]}).to_csv(tmp_path / "contracts.csv", index=False)

    rows = validate_csv_outputs(tmp_path)

    assert rows == {
        "transactions.csv": 1,
        "blocks.csv": 1,
        "token_transfers.csv": 1,
        "contracts.csv": 1,
    }
```

- [ ] **Step 2: Run RED**

Expected: fail because manifest and validation helpers are missing.

- [ ] **Step 3: Implement helpers**

Implement `write_manifest()` and `validate_csv_outputs()`. Manifest must include extraction date, mode, data period, rows, bytes processed, bytes billed, total bytes billed, estimated cost, dictionary path/count when available, and source table names.

- [ ] **Step 4: Run GREEN**

Run focused pytest. Expected: all full extraction tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/kg/extraction/full_extract.py tests/unit/test_full_extract.py
git commit -m "feat(kg): add full extraction manifest checks"
```

### Task 4: CLI boundary and dry-run path

**Files:**
- Create: `scripts/04_bigquery_full_extract.py`
- Modify: `src/nl2sparql/kg/extraction/full_extract.py`
- Modify: `tests/unit/test_full_extract.py`

- [ ] **Step 1: Write failing tests for dry-run orchestration with fake client**

```python
from datetime import date
from pathlib import Path

from nl2sparql.kg.extraction.full_extract import run_full_extract_dry_run


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
```

- [ ] **Step 2: Run RED**

Expected: fail because dry-run orchestration is missing.

- [ ] **Step 3: Implement dry-run orchestration**

Implement `run_full_extract_dry_run()`. It should build queries, run BigQuery dry runs using `bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, maximum_bytes_billed=MAX_BYTES_BILLED)`, enforce the cost guard per query and in total, then write `manifest.json`.

- [ ] **Step 4: Add CLI script**

Create `scripts/04_bigquery_full_extract.py` with options:
- `--output-dir`
- `--dictionary-path`
- `--start-date`
- `--end-date`
- `--labeled-table`
- `--dry-run`
- `--force`

Behavior:
- without `--dry-run` and without `--force`, raise a ClickException explaining that live extraction needs `--force`;
- with `--dry-run`, run only estimates and manifest writing;
- live extraction can remain guarded with a clear ClickException if temp-table/export settings are not configured in this task.

- [ ] **Step 5: Run GREEN**

Run focused pytest. Expected: all full extraction tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/04_bigquery_full_extract.py src/nl2sparql/kg/extraction/full_extract.py tests/unit/test_full_extract.py
git commit -m "feat(kg): add full extraction dry-run CLI"
```

### Task 5: Task documentation and final verification

**Files:**
- Modify: `docs/tasks/phase-2-kg/03-bigquery-extraction.md`

- [ ] **Step 1: Update task evidence**

Mark implemented local automation criteria as checked only where proven:
- SQL/script scaffold exists.
- Dry-run cost guard exists.
- Manifest schema exists.
- Pandas output validation helper exists.

Leave unchecked:
- real CSV total size ≤ 5GB;
- real BigQuery cost < $5;
- real schema matches pilot CSV;
- real coverage ≥80%;
- real pandas read of full generated CSVs.

- [ ] **Step 2: Run focused verification**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest tests/unit/test_full_extract.py -q
```

- [ ] **Step 3: Run full test suite**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest -q
```

- [ ] **Step 4: Run whitespace check**

```bash
git diff --check
```

- [ ] **Step 5: Commit docs**

```bash
git add docs/tasks/phase-2-kg/03-bigquery-extraction.md
git commit -m "docs(kg): record T2.3 extraction scaffold status"
```

