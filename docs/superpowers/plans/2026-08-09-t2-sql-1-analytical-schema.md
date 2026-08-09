# T2-SQL-1 Analytical Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and `superpowers:test-driven-development`.
> Complete each task test-first and checkpoint it separately.

**Goal:** Deliver a versioned, machine-readable GoogleSQL analytical schema
contract with fail-closed offline validation and optional read-only BigQuery
schema conformance.

**Architecture:** A committed JSON catalog describes physical sources,
canonical relations, join paths, semantic mappings, role policies, cost/date
guards, and CQ01-CQ30 coverage. A small Python module validates internal
references and live metadata; a CLI exposes offline and live read-only checks.
No BigQuery object is created in this task.

**Tech stack:** Python 3.11, standard-library `json`/`datetime`/`pathlib`,
`google-cloud-bigquery` 3.x, pytest 8, Ruff, GoogleSQL.

## Global constraints

- GoogleSQL only; fully qualified source names are catalog-owned.
- Fact windows are half-open and at most 31 days.
- Every joined partitioned fact has its own partition predicate.
- Default `maximum_bytes_billed` is 50 GiB and dry-run is mandatory.
- Address roles remain `operational|treasury|token` with distinct semantics.
- Raw token values are retained; invalid numeric conversion never becomes zero.
- Exactly CQ01-CQ30 must be represented with explicit support status.
- Offline tests and validation require no credentials or network.
- Live mode reads metadata only and skips the deferred managed label table.

## File structure

- Create `src/nl2sparql/sql/__init__.py`.
- Create `src/nl2sparql/sql/schema.py`.
- Create `src/nl2sparql/sql/catalog/ethereum_analytics.json`.
- Create `scripts/05_validate_sql_schema.py`.
- Create `tests/unit/test_sql_schema.py`.
- Modify `docs/tasks/phase-2-sql/01-analytical-schema.md` for closure evidence.
- Modify `docs/memory/05-DECISION_LOG.md` with the accepted contract decision.

---

### Task 1: Define catalog loader and fail-closed structural boundary

**Files:**
- Create: `tests/unit/test_sql_schema.py`
- Create: `src/nl2sparql/sql/__init__.py`
- Create: `src/nl2sparql/sql/schema.py`
- Create: `src/nl2sparql/sql/catalog/ethereum_analytics.json`

**Interfaces:**
- `CATALOG_PATH: Path`
- `SchemaCatalogError(ValueError)`
- `load_catalog(path: Path = CATALOG_PATH) -> dict[str, object]`
- `validate_catalog(catalog: Mapping[str, object]) -> CatalogSummary`

- [ ] **Step 1: Write failing loader and top-level contract tests**

Cover missing files, invalid JSON, wrong catalog version/dialect/location, a
non-positive byte cap, missing top-level sections, duplicate IDs, and the happy
path summary. Assert the committed catalog declares the six approved analytical
relations and five current public sources plus the deferred managed dimension.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest tests/unit/test_sql_schema.py -q
```

Expected: import/collection failure because `nl2sparql.sql.schema` does not
exist.

- [ ] **Step 3: Implement the minimum loader and top-level validators**

Use standard-library JSON parsing, convert parse/shape errors to
`SchemaCatalogError`, and return an immutable summary dataclass containing
source/relation/join/semantic/CQ counts.

- [ ] **Step 4: Add the minimum valid catalog skeleton and verify GREEN**

Populate top-level metadata, policies, and IDs first. Run the focused suite and
expect the initial tests to pass.

- [ ] **Step 5: Commit the structural boundary**

```bash
git add src/nl2sparql/sql tests/unit/test_sql_schema.py
git commit -m "feat(sql): establish analytical catalog boundary"
```

---

### Task 2: Encode sources, relations, joins, and semantic mappings

**Files:**
- Modify: `tests/unit/test_sql_schema.py`
- Modify: `src/nl2sparql/sql/schema.py`
- Modify: `src/nl2sparql/sql/catalog/ethereum_analytics.json`

**Interfaces:**
- `validate_date_window(start_date: date, end_date: date, *, max_days: int = 31) -> None`
- Catalog sections: `physical_sources`, `analytical_relations`, `join_paths`,
  `role_policies`, `semantic_mappings`.

- [ ] **Step 1: Write failing reference-integrity and date tests**

Assert failures for unknown source/column/relation/field/join/role/type,
partitioned facts without bounds, joins lacking fact-side date coverage,
non-half-open contracts, invalid or overlong date windows, and managed label
schemas missing provenance. Include one harmless extra metadata field case.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: new reference/date invariants fail against the skeleton.

- [ ] **Step 3: Implement minimal cross-reference and date validation**

Validate closed vocabularies, required keys, source field definitions, relation
field lineage, join conditions/cardinality/date coverage, semantic target
references, and role policies. Keep validation deterministic and side-effect
free.

- [ ] **Step 4: Fill the approved analytical catalog**

Encode live BigQuery types/modes, canonical relation fields, six named joins,
half-open predicates, token precision rules, and ontology concept/property
mappings. Store the planned label table as `deployment_status: deferred`.

- [ ] **Step 5: Run focused tests and verify GREEN**

```bash
uv run pytest tests/unit/test_sql_schema.py -q
```

- [ ] **Step 6: Commit source and semantic mappings**

```bash
git add src/nl2sparql/sql/schema.py \
  src/nl2sparql/sql/catalog/ethereum_analytics.json \
  tests/unit/test_sql_schema.py
git commit -m "feat(sql): map Ethereum analytical schema"
```

---

### Task 3: Make competency coverage and schema drift executable

**Files:**
- Modify: `tests/unit/test_sql_schema.py`
- Modify: `src/nl2sparql/sql/schema.py`
- Modify: `src/nl2sparql/sql/catalog/ethereum_analytics.json`

**Interfaces:**
- `normalize_live_schema(table: object) -> dict[str, LiveField]`
- `validate_live_schemas(catalog: Mapping[str, object], schemas: Mapping[str, Mapping[str, LiveField]]) -> LiveSchemaSummary`
- Catalog section: `competency_questions`.

- [ ] **Step 1: Write failing CQ and drift tests**

Require exactly CQ01-CQ30, closed statuses, valid relation/join references, and
non-empty reasons for `coverage_gap`/`unsupported`. Assert the approved CQ24 and
CQ17 semantics. Fake live schemas must fail on missing/type/mode changes and
pass with additional upstream columns; deferred sources must be reported as
deferred rather than missing.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: CQ coverage and live-schema functions are absent/incomplete.

- [ ] **Step 3: Implement CQ and live metadata validation**

Keep BigQuery client objects behind a normalization boundary so all unit tests
remain offline. Return checked/skipped counts and actionable source/field error
messages.

- [ ] **Step 4: Encode CQ01-CQ30 mappings and verify GREEN**

Mark schema-supported questions precisely. Preserve explicit gaps for missing
operational mixer/NFT/MEV labels and unsupported meta-transaction semantics.

- [ ] **Step 5: Commit executable coverage**

```bash
git add src/nl2sparql/sql/schema.py \
  src/nl2sparql/sql/catalog/ethereum_analytics.json \
  tests/unit/test_sql_schema.py
git commit -m "feat(sql): validate competency and schema coverage"
```

---

### Task 4: Add CLI, live evidence, and close T2-SQL-1

**Files:**
- Create: `scripts/05_validate_sql_schema.py`
- Modify: `tests/unit/test_sql_schema.py`
- Modify: `docs/tasks/phase-2-sql/01-analytical-schema.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

**Interfaces:**
- CLI default: offline catalog validation.
- CLI `--live`: read-only `Client.get_table` checks for current public sources.
- CLI `--project`: billing/project context, defaulting from standard Google
  Cloud configuration.

- [ ] **Step 1: Write failing CLI tests**

Cover offline success, invalid catalog failure, live client injection, public
source checks, deferred managed source reporting, and nonzero exit on drift.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: CLI module/path does not exist.

- [ ] **Step 3: Implement the minimal offline/live CLI**

Do not query table data and do not create objects. Live mode calls metadata APIs
only and prints deterministic counts suitable for task evidence.

- [ ] **Step 4: Run focused and live checks**

```bash
uv run pytest tests/unit/test_sql_schema.py -q
uv run python scripts/05_validate_sql_schema.py
uv run python scripts/05_validate_sql_schema.py --live \
  --project nl2sparql-thesis
```

Run representative `bq query --dry_run --use_legacy_sql=false` statements for
transaction→block and transfer→contract/token join paths. Record estimated
bytes and require each estimate below 53,687,091,200 bytes.

- [ ] **Step 5: Run full verification**

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
git diff --check
```

- [ ] **Step 6: Close documentation and decision log**

Mark all acceptance items truthfully, record live schema/dry-run evidence, and
add a reverse-chronological decision entry for hybrid TVFs, half-open date
bounds, role separation, and explicit CQ limitations.

- [ ] **Step 7: Commit T2-SQL-1 closure**

```bash
git add scripts/05_validate_sql_schema.py tests/unit/test_sql_schema.py \
  docs/tasks/phase-2-sql/01-analytical-schema.md \
  docs/memory/05-DECISION_LOG.md
git commit -m "docs(sql): close analytical schema task"
```

---

## Completion checkpoint

T2-SQL-1 is complete only when all acceptance evidence is current, the
worktree is clean, and no remote object was mutated. Then summarize the task as
a logical compaction checkpoint and move directly to T2-SQL-2 design.
