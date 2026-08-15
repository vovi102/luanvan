# T3.5 GoogleSQL Test-Set Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a credential-free, fail-closed three-pool workflow that can validate and later finalize 100 independent GoogleSQL test cases without fabricating human or BigQuery evidence.

**Architecture:** A deep `src/nl2sparql/dataset/testset/` module owns typed CSV contracts, bundle validation, review statistics, SQL safety, live evidence, and deterministic finalization. A Click CLI exposes scaffold, validate, verify-live, and finalize modes; the BigQuery client is injected as an adapter and never created in offline mode.

**Tech Stack:** Python 3.11, dataclasses, csv/json/hashlib, Click, google-cloud-bigquery, pytest, Ruff.

## Global Constraints

- Canonical target is read-only GoogleSQL; no new SPARQL/Fuseki fields or execution claims.
- Final difficulty counts are exactly `easy=30`, `medium=50`, `hard=20`.
- BigQuery policy is 20 GiB per query and 64 GiB aggregate, with cache disabled and complete dry-run preflight.
- Human identifiers are pseudonyms; no emails or free-form names are accepted.
- Offline commands must not instantiate a BigQuery client or require credentials.
- Finalization requires explicit `final_selection.csv` and matching live evidence; missing external inputs produce `blocked`, not fake data.
- Tests are written before implementation, and every public function has Google-style docstrings and type hints.
- Do not overwrite non-empty collaborator files without an explicit `--force` flag.

## File Map

- Create `src/nl2sparql/dataset/testset/contracts.py`: typed records, paths, policies, and domain errors.
- Create `src/nl2sparql/dataset/testset/validate.py`: CSV decoding, cross-file validation, review aggregation, kappa, and quota reports.
- Create `src/nl2sparql/dataset/testset/live.py`: read-only SQL checks and injected BigQuery execution adapter.
- Create `src/nl2sparql/dataset/testset/artifacts.py`: scaffold, evidence/report serialization, deterministic final JSONL, and atomic publication.
- Create `src/nl2sparql/dataset/testset/__init__.py`: the small public interface exported by the package.
- Create `scripts/test_set_workflow.py` and `scripts/12_test_set_workflow.py`: Click orchestration and numbered entry point with credential-free offline modes.
- Create `scripts/__init__.py`: mark CLI helpers as an importable repository package for tests.
- Create `tests/unit/test_testset_contracts.py`, `test_testset_validate.py`, `test_testset_live.py`, and `test_testset_artifacts.py`.
- Create `data/dataset/test/PROCESS.md`, `CONSENT.md`, and CSV header templates through the scaffold command; keep real submissions out of the repository until consent permits publication.
- Modify `docs/tasks/phase-3-dataset/05-test-set-3pool.md`, `docs/memory/05-DECISION_LOG.md`, and the task status only after implementation evidence exists.

### Task 1: Typed contracts and safe CSV loading

**Files:**
- Create: `src/nl2sparql/dataset/testset/contracts.py`
- Create: `src/nl2sparql/dataset/testset/__init__.py`
- Test: `tests/unit/test_testset_contracts.py`

**Interfaces:**
- `TestSetPaths.from_root(root: Path) -> TestSetPaths` returns the five input/output paths.
- `load_csv(path: Path, required_columns: tuple[str, ...]) -> list[dict[str, str]]` reads UTF-8 headers and rejects missing/extra/duplicate headers.
- Dataclasses `PoolARecord`, `PoolBRecord`, `ReviewRecord`, `SelectionRecord`, and `FinalCase` expose typed fields matching the spec.
- `TestSetError` is the common domain exception used by later modules.

- [x] **Step 1: Write failing contract tests**

  Test valid headers, missing headers, duplicate headers, empty required values,
  unsafe person identifiers, boolean parsing, and `TestSetPaths.from_root`.

- [x] **Step 2: Run the focused tests and verify RED**

  Run `uv run pytest -q tests/unit/test_testset_contracts.py`.
  Expected: import/constructor failures because the new package does not exist.

- [x] **Step 3: Implement the minimal typed contracts and loader**

  Use `csv.DictReader`, reject control characters and identifiers containing
  `@`, and preserve source row numbers in error messages. Do not load any cloud
  library from `contracts.py`.

- [x] **Step 4: Run the focused tests and verify GREEN**

  Run the same command; all contract tests must pass and offline import must not
  touch Google credentials.

- [x] **Step 5: Commit the contract seam**

  Run `git add src/nl2sparql/dataset/testset tests/unit/test_testset_contracts.py`
  and commit `feat(dataset): define three-pool test-set contracts`.

### Task 2: Bundle validation, review metrics, and deterministic selection checks

**Files:**
- Create: `src/nl2sparql/dataset/testset/validate.py`
- Test: `tests/unit/test_testset_validate.py`

**Interfaces:**
- `load_bundle(paths: TestSetPaths) -> Bundle` loads Pool A/B/C and selection rows.
- `validate_bundle(bundle: Bundle) -> BundleReport` returns counts, author coverage, category/difficulty evidence, reject rate, and kappa.
- `cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float` computes the standard nominal statistic and raises `TestSetError` for unequal/degenerate inputs.
- `validate_selection(bundle: Bundle) -> tuple[SelectionRecord, ...]` requires exactly 100 unique accepted IDs and exact 30/50/20 difficulty counts.

- [x] **Step 1: Write failing validation tests**

  Add fixtures for a valid small bundle, duplicate NL/IDs, Pool A author under-
  coverage, Pool B join mismatch, unsafe SQL, missing/extra reviewers, kappa
  below 0.7, reject rate at/above 30%, six-category/three-entity coverage, and
  exact selection quota failures. Include the known kappa vector whose result is
  1.0 and a disagreement vector whose result is below the threshold.

- [x] **Step 2: Run focused tests and verify RED**

  Run `uv run pytest -q tests/unit/test_testset_validate.py`; expected failure is
  missing `load_bundle`, `cohen_kappa`, and `validate_bundle`.

- [x] **Step 3: Implement validation behind the module interface**

  Normalize NL with Unicode NFKC and whitespace collapse, join by exact IDs,
  require three authors with 20 rows each, require one canonical Pool B row per
  question, calculate Pool C reject rate and two-rater kappa on a deterministic
  30-ID subset, and reject any final row not explicitly accepted.

- [x] **Step 4: Run focused tests and verify GREEN**

  Run `uv run pytest -q tests/unit/test_testset_validate.py`; no cloud client may
  be imported or instantiated by these tests.

- [x] **Step 5: Commit validation and metrics**

  Commit `feat(dataset): validate three-pool review evidence` after staging the
  validator and tests.

### Task 3: Read-only SQL and BigQuery evidence adapter

**Files:**
- Create: `src/nl2sparql/dataset/testset/live.py`
- Test: `tests/unit/test_testset_live.py`

**Interfaces:**
- `SqlPolicy(per_query_bytes=20*2**30, total_bytes=64*2**30, location="US")` stores immutable caps.
- `validate_sql_text(sql: str) -> None` rejects empty, comments, multi-statement, mutation, wildcard projection, and unmanaged objects.
- `verify_sql(client: Any, cases: Sequence[FinalCase], policy: SqlPolicy) -> LiveEvidence` performs complete preflight, immediate re-dry-run, bounded execution, result-column/non-empty checks, and returns hash-bound evidence.

- [x] **Step 1: Write failing live-adapter tests**

  Fake jobs must prove mutation/comment/wildcard rejection, per-query and total
  budget rejection, `use_query_cache=False`, missing expected columns, empty
  result policy, stale SQL hash detection, and successful evidence collection.

- [x] **Step 2: Run focused tests and verify RED**

  Run `uv run pytest -q tests/unit/test_testset_live.py`; expected failure is the
  absent adapter module.

- [x] **Step 3: Implement policy and injected adapter**

  Reuse the managed catalog prefix and existing GoogleSQL budget conventions.
  Call `client.query` with dry-run config for every case before execution, sum
  estimates before executing anything, and reject any cache hit or billed bytes
  over the caps. Record query SHA-256, job ID, result count, columns, bytes, and
  UTC timestamp.

- [x] **Step 4: Run focused tests and verify GREEN**

  Run the focused live suite; verify no test accesses the network or credentials.

- [x] **Step 5: Commit the live adapter**

  Commit `feat(dataset): add bounded GoogleSQL test-set verification`.

### Task 4: Artifacts, CLI, and scaffold documents

**Files:**
- Create: `src/nl2sparql/dataset/testset/artifacts.py`
- Create: `scripts/12_test_set_workflow.py`
- Create: `tests/unit/test_testset_artifacts.py`
- Create/emit: `data/dataset/test/PROCESS.md`, `CONSENT.md`, CSV headers

**Interfaces:**
- `write_scaffold(root: Path, force: bool = False) -> ScaffoldReport` creates only absent/empty files.
- `write_report(report: BundleReport | LiveEvidence, path: Path) -> None` writes canonical JSON with SHA metadata.
- `finalize_bundle(bundle: Bundle, evidence: LiveEvidence, selection_path: Path, output_path: Path) -> FinalizationReport` validates every precondition and atomically writes exactly 100 JSONL rows.

- [x] **Step 1: Write failing artifact/CLI tests**

  Test scaffold idempotence and `--force`, canonical report hashes, blocked
  finalize with missing evidence, deterministic final output across runs, and
  Click `scaffold`/`validate` operation without credentials.

- [x] **Step 2: Run focused tests and verify RED**

  Run `uv run pytest -q tests/unit/test_testset_artifacts.py`; expected failure is
  missing artifact functions and CLI module.

- [x] **Step 3: Implement atomic artifacts and CLI modes**

  Use unique temporary files plus `os.replace`, include git SHA/input hashes in
  reports, return nonzero Click errors for blocked/failed validation, and make
  `verify-live` the only mode allowed to create live evidence.

- [x] **Step 4: Run focused tests and verify GREEN**

  Run `uv run pytest -q tests/unit/test_testset_*.py` and `uv run python scripts/12_test_set_workflow.py --help`.

- [x] **Step 5: Commit the tooling checkpoint**

  Commit `feat(dataset): add three-pool test-set workflow CLI`.

### Task 5: Migrate task evidence and run repository verification

**Files:**
- Modify: `docs/tasks/phase-3-dataset/05-test-set-3pool.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/superpowers/specs/2026-08-15-t3-5-google-sql-test-set-design.md`
- Modify: `docs/superpowers/plans/2026-08-15-t3-5-google-sql-test-set.md`

- [x] **Step 1: Rewrite T3.5 contract and record blockers**

  Replace SPARQL/Fuseki wording with GoogleSQL/BigQuery fields, mark offline
  implementation checks complete only when evidenced, leave human/live boxes
  unchecked, and record the credential/collaborator blocker in the decision log.

- [x] **Step 2: Run all verification gates**

  Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run python -m json.tool notebooks/10_noise_injection.ipynb >/dev/null`,
  and `git diff --check`. Expected: all tests pass and every command exits 0.

- [x] **Step 3: Review the complete checkpoint**

  Inspect `git diff --stat`, run the CLI offline validation against the scaffold,
  confirm no generated personal data or large raw artifact was added, and verify
  all pending external acceptance boxes remain explicit.

- [x] **Step 4: Commit documentation and verification evidence**

  Commit `docs(dataset): migrate T3.5 to GoogleSQL test-set contract` after all
  checks pass. If Git metadata remains read-only, preserve the complete diff and
  report that commit/push is externally blocked.
