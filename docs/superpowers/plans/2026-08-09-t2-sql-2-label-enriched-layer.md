# T2-SQL-2 Label-Enriched Analytical Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and `superpowers:test-driven-development`.
> Complete each task test-first and checkpoint it separately.

**Goal:** Deploy a durable, versioned entity-label dimension and canonical
GoogleSQL views/TVFs with safe plan/apply behavior and reproducible validation.

**Architecture:** A deterministic local builder converts the accepted dictionary
to explicit BigQuery rows and a digest-addressed immutable snapshot. A stable
view publishes only validated snapshots. Catalog-owned SQL renders core and
label-enriched routines. A plan-first deployer orchestrates mutations behind a
small client boundary that unit tests can fake.

**Tech stack:** Python 3.11, `google-cloud-bigquery` 3.x, GoogleSQL, pytest 8,
Ruff, standard-library `hashlib`/`json`/`dataclasses`.

## Global constraints

- Plan-only is the default; only `--apply` mutates BigQuery.
- Managed objects stay in `US` and durable dataset defaults never expire them.
- Snapshot identity comes from raw `entities.json` SHA-256 and is immutable.
- Stable view changes only after full snapshot validation.
- No deploy or rollback path deletes an old snapshot.
- Every fact TVF enforces half-open bounds of at most 31 days.
- Token values preserve raw precision and invalid casts remain observable.
- Label enrichment uses unique-address `LEFT JOIN`s and explicit flat fields.
- T2-SQL-2 executes only small label checks; fact queries are dry-run only.

## File structure

- Create `src/nl2sparql/sql/label_layer.py`.
- Modify `src/nl2sparql/sql/__init__.py` for public deployment interfaces.
- Create `scripts/06_deploy_sql_label_layer.py`.
- Create `tests/unit/test_sql_label_layer.py`.
- Modify `src/nl2sparql/sql/catalog/ethereum_analytics.json` after live deploy.
- Modify `tests/unit/test_sql_schema.py` for the live label source.
- Modify `docs/tasks/phase-2-sql/02-label-enriched-layer.md` for evidence.
- Modify `docs/memory/05-DECISION_LOG.md` with lifecycle/routine decisions.

---

### Task 1: Build deterministic label snapshots

**Files:**
- Create `tests/unit/test_sql_label_layer.py`
- Create `src/nl2sparql/sql/label_layer.py`
- Modify `src/nl2sparql/sql/__init__.py`

**Interfaces:**
- `LabelLayerError(ValueError)`
- `LabelSnapshot` frozen dataclass
- `LABEL_TABLE_SCHEMA`
- `build_label_snapshot(entities_path: Path = ENTITIES_PATH) -> LabelSnapshot`

- [ ] Write failing tests for raw-file digest naming, deterministic row mapping,
  explicit nested schema, role counts, lowercase unique addresses, and invalid
  artifact rejection.
- [ ] Run the focused test and confirm RED from the absent module.
- [ ] Implement the smallest builder, reusing dictionary validators rather than
  weakening their accepted contract.
- [ ] Confirm the committed artifact yields 5,135 rows, expected role counts and
  snapshot `entity_labels_snapshot_190f73a91b7a`.
- [ ] Run focused tests to GREEN and commit the snapshot boundary.

---

### Task 2: Render core and label-enriched GoogleSQL

**Files:**
- Modify `tests/unit/test_sql_label_layer.py`
- Modify `src/nl2sparql/sql/label_layer.py`

**Interfaces:**
- `SqlObject` frozen dataclass with name, kind, dependencies and DDL
- `render_label_layer_ddl(project: str, dataset: str, snapshot_table: str) -> tuple[SqlObject, ...]`
- `render_stable_label_view(...) -> str`
- `render_rollback_ddl(...) -> str`

- [ ] Write failing tests for the exact object set/order, fully qualified names,
  explicit projections, date guards, per-source partition filters, latest
  contract deduplication, `SAFE_CAST`, fungible normalization and flat
  `LEFT JOIN` label fields.
- [ ] Confirm RED before adding renderers.
- [ ] Implement minimal deterministic DDL renderers with no `SELECT *`.
- [ ] Assert identifiers reject unsafe project/dataset/table values.
- [ ] Run focused tests to GREEN and commit routine rendering.

---

### Task 3: Implement plan-first deployment and rollback

**Files:**
- Modify `tests/unit/test_sql_label_layer.py`
- Modify `src/nl2sparql/sql/label_layer.py`
- Create `scripts/06_deploy_sql_label_layer.py`

**Interfaces:**
- `DeploymentPlan` and `DeploymentResult` frozen dataclasses
- `build_deployment_plan(...) -> DeploymentPlan`
- `apply_deployment(plan, client) -> DeploymentResult`
- `validate_deployed_snapshot(snapshot, client, ...) -> None`
- CLI flags `--project`, `--dataset`, `--location`, `--apply`, `--rollback-to`

- [ ] Write failing fake-client tests proving default plan-only has no remote
  calls, apply operation order, dataset policy checks, `WRITE_EMPTY`, same-digest
  idempotency, aggregate mismatch failure before view swap, and rollback only
  repoints after validation.
- [ ] Write failing CLI tests for deterministic plan output and explicit apply.
- [ ] Confirm RED before deployment implementation.
- [ ] Implement a narrow BigQuery boundary, explicit load schema and capped
  validation query.
- [ ] Implement the CLI without importing credentials/network in plan-only mode.
- [ ] Run focused tests to GREEN and commit deploy orchestration.

---

### Task 4: Deploy live, validate, and close T2-SQL-2

**Files:**
- Modify `src/nl2sparql/sql/catalog/ethereum_analytics.json`
- Modify `tests/unit/test_sql_schema.py`
- Modify `docs/tasks/phase-2-sql/02-label-enriched-layer.md`
- Modify `docs/memory/05-DECISION_LOG.md`

- [ ] Run the complete offline focused suite and plan output.
- [ ] Apply to `nl2sparql-thesis.nl2sparql_analytics` and record the accepted
  snapshot/object metadata.
- [ ] Run the small snapshot aggregate validation and metadata readback.
- [ ] Dry-run representative calls to each fact/enriched TVF; record bytes and
  require each below 53,687,091,200.
- [ ] Only after live success, update catalog `entity_labels_v1` to the managed
  logical view and update deferred/live schema tests test-first.
- [ ] Run `scripts/05_validate_sql_schema.py --live --project
  nl2sparql-thesis` and require all six sources to pass.
- [ ] Run full pytest, Ruff, format and `git diff --check`.
- [ ] Close task evidence and decision log truthfully; commit closure.

## Completion checkpoint

T2-SQL-2 is complete only when remote objects and the committed catalog agree,
all validation evidence is current, the worktree is clean, and rollback remains
available through an older accepted snapshot. Then issue a logical compaction
checkpoint and continue directly to T2-SQL-3 live correctness/cost/latency
benchmarking.
