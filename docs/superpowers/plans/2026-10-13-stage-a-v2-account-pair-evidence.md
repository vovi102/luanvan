# Stage A v2 Account-Pair Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace independent address pairing with 40 relationship-proven account pairs, verify all 206 logical witnesses diagnostically without publishing acceptance, regenerate the candidate, and stop after a fresh preflight for user approval.

**Architecture:** A focused account-pair module validates and canonicalizes the relationship-level pool before Stage A v2 generation. The generator consumes each pair and its date window atomically, and the planner batches the 40 logical pair witnesses into four physical queries so the full 206-witness plan remains 126 queries. The provider workflow adds a billing-disabled guard and diagnostic-only report path around that verifier. Diagnostic evidence and acceptance evidence remain separate lifecycles; only the existing live command may publish accepted artifacts after a later approval.

**Tech Stack:** Python 3.11, frozen dataclasses, JSON/JSONL, Click, Google Cloud BigQuery, pytest, Ruff, Git.

**Spec:** `docs/superpowers/specs/2026-10-12-stage-a-v2-account-pair-evidence-design.md`

## Global Constraints

- Preserve all Stage A v1 files and historical evidence byte-for-byte.
- Preserve existing non-pair entries in `stage-a-v2-evidence-pools.json`.
- Require exactly 40 account-pair entries with 80 globally distinct endpoints, the half-open window `[2026-06-15, 2026-06-16)`, and complete relationship provenance.
- Keep exactly 1,000 records, 25 intents, seed 42, difficulty totals `350/450/200`, 206 logical witnesses, and 126 physical queries.
- Keep the per-query cap at 20 GiB and complete initial-preflight cap at 96 GiB.
- Before every query that executes rather than dry-runs, require `billingEnabled=false` and an empty billing account; never link or enable billing.
- Disable BigQuery cache, require Standard SQL, use `maximum_bytes_billed`, and never retry a quota or provider failure automatically.
- Diagnostic mode may execute read-only queries and write diagnostic evidence, but it must never invoke the accepted writer or create any accepted artifact.
- Candidate generation may write only the three `*-v2-candidate*` paths and remains `candidate` with `acceptance_eligible=false`.
- Do not run final live acceptance, merge, push, create a PR, audit 100 EN plus 100 VI, or build the 8,000-record corpus.
- Preserve the cleaned small-LLM-only scope from `main`; do not restore deleted
  hosted/remote-model code, dependencies, tasks, or backlog history.
- Use RED → GREEN → REFACTOR and small commits.

## Review Focus

- Pair entries whose fields are individually valid but whose endpoints/window come from different entries must fail atomicity tests in Task 2.
- Structurally plausible provenance with cache hits, enabled billing, inconsistent bytes, timestamps outside the window, or a non-positive transaction count must fail Task 1 validation.
- A diagnostic failure after some successful jobs must write only a truthful diagnostic failure report and must leave all accepted targets absent; Task 3 exercises this boundary.
- Billing state must be checked before BigQuery client construction for diagnostic and live execution, including malformed or unavailable `gcloud` output; Task 3 pins ordering and failure behavior.
- The new pool may reorder as a whole, but canonicalization must never separately sort endpoints, dates, or evidence; Tasks 1-2 test reordered entries with intentionally different windows.

---

### Task 0: Synchronize the Clean Small-LLM Baseline

**Files:**

- Merge from: `main` at or after `5ff21e1`
- Resolve: `docs/planning/prioritized-backlog-2026-09-21.md`
- Resolve: `docs/memory/05-DECISION_LOG.md`
- Preserve: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`

**Interfaces:**

- Consumes the cleaned B0–B3-only scope and dependency removals from `main`.
- Produces a feature branch based on the current clean governance structure,
  with Stage A implementation/history preserved through Git and the detailed
  T3.2 task record.
- Prevents Tasks 1–6 from reintroducing removed large-model/provider surfaces.

- [ ] **Step 1: Merge current `main` without publishing the branch**

Run `git merge --no-ff --no-commit main`. Do not merge the feature branch into
`main`, push, or create a PR.

Expected: conflicts only in governance files changed independently by the
Stage A evidence branch and the small-LLM cleanup.

- [ ] **Step 2: Resolve governance conflicts using the cleaned structure**

Keep `main`'s compact small-LLM-only backlog and its 2026-10-13 decision entry.
Do not restore deleted B4/B5, hosted-provider, or verbose active-backlog text.
Keep detailed prior Stage A operational evidence in
`docs/tasks/phase-3-dataset/02-synthetic-pipeline.md` and Git history. Task 5
will later add one concise account-pair decision and current P0 status.

Run `git diff --check` and scan for conflict markers.

Expected: no conflict markers or whitespace errors.

- [ ] **Step 3: Verify the synchronized baseline**

Run:

```bash
uv sync --frozen
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
```

Expected: the current reduced test suite and both Ruff checks pass. Record the
new baseline count; do not compare it with the pre-cleanup 1,646-test count.

- [ ] **Step 4: Commit the merge**

```bash
git add -A
git commit -m "merge: sync small-LLM scope into Stage A work"
```

Expected: the feature branch contains both histories and remains unpushed.

### Task 1: Relationship Evidence Contract and Captured Pool

**Files:**

- Create: `src/nl2sparql/dataset/stage_a/account_pairs.py`
- Modify: `src/nl2sparql/dataset/stage_a/__init__.py`
- Modify: `data/dataset/raw/stage-a-v2-evidence-pools.json`
- Create: `tests/unit/test_stage_a_account_pairs.py`
- Modify: `tests/unit/test_stage_a_v2_artifacts.py`

**Interfaces:**

- Produces frozen `AccountPairEvidence` and `AccountPair` dataclasses with
  `from_mapping(value: Mapping[str, Any]) -> Self` and
  `to_mapping() -> dict[str, Any]` methods.
- Produces `load_account_pairs(pools: Mapping[str, Any], *, expected_count: int = 40) -> tuple[AccountPair, ...]`.
- Produces `canonical_account_pair_mappings(pools: Mapping[str, Any]) -> list[dict[str, Any]]` for manifest hashing and generator input.
- Consumed by Task 2 generation and Task 3 provider gating.

- [ ] **Step 1: Write failing schema and provenance tests**

Add tests that load the committed pool and assert exactly 40 pairs, 80 globally distinct lowercase endpoints, lexicographic endpoint order, the exact half-open date window, positive transaction counts, timestamps within the window, cache disabled, billing disabled, a 1 GiB diagnostic cap, the captured job ID/query SHA, and unique positive result rows.

Parameterize failures for missing/extra fields, same endpoints, repeated endpoint across entries, invalid address/date/timestamp, timestamp outside the window, blank job/query/source, non-positive count, negative or contradictory bytes, billed bytes above the maximum, cache hit, enabled billing, wrong project/location, and duplicate result row.

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_account_pairs.py tests/unit/test_stage_a_v2_artifacts.py -q`

Expected: FAIL because `account_pairs.py` and the `account_pair` pool do not exist.

- [ ] **Step 3: Add the 40 captured entries**

Append only `account_pair` to the existing evidence-pool document. Use the exact 40 pairs returned by job `d7aa2151-18e4-4f3f-99c4-2c255bdbfe0e`, retaining each pair's result row, transaction count, first/last timestamp, query SHA, processed/billed bytes, cache flag, disabled-billing observation, and 1 GiB cap. Do not change existing keys or entries.

- [ ] **Step 4: Implement strict parsing and canonicalization**

Implement the Task 1 interfaces. Reject booleans where integers are required, unknown keys, non-UTC timestamps, non-canonical endpoint order, any repeated endpoint, cross-entry diagnostic metadata drift, and any value inconsistent with the fixed relation/window contract. Canonicalization sorts whole `AccountPair.to_mapping()` values by canonical JSON without decomposing an entry.

- [ ] **Step 5: Verify GREEN and immutable inputs**

Run: `uv run pytest tests/unit/test_stage_a_account_pairs.py tests/unit/test_stage_a_v2_artifacts.py -q`

Expected: PASS.

Recompute the three Stage A v1 hashes and compare them with:

- data: `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`;
- config: `781495b7a70614bd6b87861781a816946f2443ac1c66cab2bba16df58afbe713`; and
- stats: `bc93c7a9355a34e531b275181646db269968040d2484e8a2876a8329db8579db`.

Record the new evidence-pool SHA-256 from actual bytes.

Run: `uv run ruff format --check src/nl2sparql/dataset/stage_a/account_pairs.py tests/unit/test_stage_a_account_pairs.py tests/unit/test_stage_a_v2_artifacts.py && uv run ruff check src/nl2sparql/dataset/stage_a/account_pairs.py tests/unit/test_stage_a_account_pairs.py tests/unit/test_stage_a_v2_artifacts.py`

Expected: PASS.

- [ ] **Step 6: Commit the relationship evidence contract**

```bash
git add src/nl2sparql/dataset/stage_a/account_pairs.py src/nl2sparql/dataset/stage_a/__init__.py tests/unit/test_stage_a_account_pairs.py tests/unit/test_stage_a_v2_artifacts.py data/dataset/raw/stage-a-v2-evidence-pools.json
git commit -m "feat(dataset): add verified Stage A account pairs"
```

### Task 2: Atomic Pair Generation and Artifact Binding

**Files:**

- Modify: `src/nl2sparql/dataset/stage_a_v2.py`
- Modify: `src/nl2sparql/dataset/stage_a/v2_artifacts.py`
- Modify: `src/nl2sparql/dataset/stage_a/planning.py`
- Modify: `tests/unit/test_stage_a_v2.py`
- Modify: `tests/unit/test_stage_a_v2_artifacts.py`
- Modify: `tests/unit/test_stage_a_witness_planning.py`
- Modify: `tests/unit/test_stage_a_verify.py`
- Modify: `tests/unit/test_stage_a_v2_workflow.py`

**Interfaces:**

- Consumes Task 1 `load_account_pairs(...)` and `canonical_account_pair_mappings(...)`.
- Changes `_variant_fill(...)` so `T_TX_BETWEEN_ACCOUNTS` copies `account`, `account_b`, `start_date`, and `end_date` from one `AccountPair` at `index`.
- Changes `canonicalize_stage_a_v2_pools(...)` to canonicalize whole relationship entries atomically.
- Extends `has_evidence_backed_live_values(...)` to require the complete account-pair contract in addition to block/hash evidence.
- Extends the v2 planner with four deterministic `account_pair_batch` queries of 10 logical pair witnesses each, preserving 126 physical queries while raising truthful logical coverage to 206.
- Preserves record schema, witness planner signatures, and Stage A v1 behavior.

- [ ] **Step 1: Write failing atomicity and provenance tests**

Add `test_between_accounts_consumes_verified_pairs_atomically` and assert all 40 record slot dictionaries equal the four bound values from the corresponding canonical pair entry. Assert no generated pair equals the old independently combined failure pair unless that exact pair exists in `account_pair`.

Add reordered-pool fixtures with deliberately distinct date windows and prove reordering preserves whole pair/window units. Add cases where one endpoint, one date, or evidence is copied between entries and require generation/artifact validation to fail.

Add tests that missing, empty, malformed, or 39-entry `account_pair` pools fail closed; candidate/live manifests bind the complete new pool digest; and accepted paths remain absent on every failure.
Assert the offline CLI without an explicit evidence-backed pool now fails before
writing, while the same CLI with `--value-pools
data/dataset/raw/stage-a-v2-evidence-pools.json` remains provider-free.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_v2.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py -q`

Expected: FAIL because the generator still combines independent `ethereum_address` entries and live-pool validation ignores `account_pair`.

- [ ] **Step 3: Implement atomic generation and binding**

Use the Task 1 parser before generation. For `T_TX_BETWEEN_ACCOUNTS`, select one canonical pair by record index, copy its four slot fields together, and set `n` deterministically within the template range. Leave the generic pool loop unchanged for every other template. Ensure `entities_used`, witness IDs, rendered SQL, record hashes, and manifest pool hashes all derive from the atomic slots. Render the 40 resulting witness groups as four stable 10-pair batch queries whose result rows include `witness_group_id`; reject missing, duplicate, unexpected, or column-drifted logical results.

- [ ] **Step 4: Verify GREEN and unchanged plan shape**

Run: `uv run pytest tests/unit/test_stage_a_v2.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py tests/unit/test_stage_a_verify.py -q`

Expected: PASS with 40 relationship-backed records, 206 logical witnesses, and 126 physical queries.

Run: `uv run ruff format --check src/nl2sparql/dataset/stage_a_v2.py src/nl2sparql/dataset/stage_a/v2_artifacts.py tests/unit/test_stage_a_v2.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py && uv run ruff check src/nl2sparql/dataset/stage_a_v2.py src/nl2sparql/dataset/stage_a/v2_artifacts.py tests/unit/test_stage_a_v2.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py`

Expected: PASS.

- [ ] **Step 5: Commit atomic generation**

```bash
git add src/nl2sparql/dataset/stage_a_v2.py src/nl2sparql/dataset/stage_a/v2_artifacts.py tests/unit/test_stage_a_v2.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py tests/unit/test_stage_a_verify.py
git commit -m "fix(dataset): generate account pairs atomically"
```

### Task 3: Billing-Disabled Diagnostic Workflow

**Files:**

- Create: `src/nl2sparql/dataset/stage_a/diagnostics.py`
- Modify: `src/nl2sparql/dataset/stage_a/verify.py`
- Modify: `src/nl2sparql/dataset/stage_a/__init__.py`
- Modify: `scripts/09_generate_stage_a_v2.py`
- Create: `tests/unit/test_stage_a_diagnostics.py`
- Modify: `tests/unit/test_stage_a_verify.py`
- Modify: `tests/unit/test_stage_a_v2_workflow.py`

**Interfaces:**

- Produces `ProjectBillingState(project_id: str, billing_enabled: bool, billing_account_name: str)` and `require_unbilled_project(project: str, *, runner: Callable[..., CompletedProcess[str]] = subprocess.run) -> ProjectBillingState`.
- Produces `DiagnosticRecorder` with canonical event methods for initial dry-runs, immediate dry-runs, executions, logical results, and terminal failure.
- Extends `verify_stage_a(..., diagnostic_recorder: DiagnosticRecorder | None = None)` without changing default behavior or report types.
- Produces `serialize_diagnostic_report(...) -> bytes` and
  `validate_diagnostic_report(report: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None`.
- Produces `_run_diagnostic(...)` in the CLI and adds mutually exclusive
  `--diagnostic`, `--diagnostic-report`, and provider-free
  `--validate-diagnostic-report`, with a default report under `docs/evidence/`.

- [ ] **Step 1: Write failing billing guard tests**

Test exact `gcloud billing projects describe PROJECT --format=json(...)` invocation through an injected runner. Require `billingEnabled=false` and an empty billing account. Parameterize enabled billing, non-empty account, malformed JSON, wrong project, missing `gcloud`, and nonzero exit. Assert every failure happens before BigQuery client construction for both diagnostic and live modes.

- [ ] **Step 2: Write failing diagnostic lifecycle tests**

Using fake BigQuery jobs, assert diagnostic success records 206 logical witnesses over 126 physical jobs, exact dry-run/execution metrics, zero cache hits, and mode `diagnostic`. Assert empty, malformed, unexpected, duplicate, schema-drift, cache-hit, quota, and provider failures produce a canonical failure report naming the first failed gate.

For every outcome, monkeypatch accepted and candidate writers to raise if called and assert the three accepted targets remain absent. Assert `--diagnostic`, `--preflight`, and `--live` are mutually exclusive before billing/provider use.
Assert `--validate-diagnostic-report` rejects missing/tampered physical edges,
logical coverage, candidate digests, byte totals, or cache state without
importing Google modules.

- [ ] **Step 3: Run diagnostic tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_diagnostics.py tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py -q`

Expected: FAIL because the billing guard, recorder, and diagnostic mode do not exist.

- [ ] **Step 4: Implement billing guard and recorder**

Keep `gcloud` output capture private and serialize only the normalized project, boolean state, and empty billing-account assertion. Record physical metrics once. Make recorder callbacks observational: they must not alter planner order, validation, caps, or acceptance report construction. On failure, atomically write the diagnostic report through a temporary sibling and `Path.replace`; never call an artifact writer.

- [ ] **Step 5: Implement diagnostic and live billing ordering**

In `_run_diagnostic(...)` and `_run_live(...)`, call `require_unbilled_project(...)` before importing/constructing the BigQuery client. Diagnostic uses the existing v2 planner and verifier, writes only its report, and returns a summary. Live retains its accepted-writer behavior but is now additionally blocked when billing is linked. Preflight remains dry-run-only and does not claim zero quota use.

- [ ] **Step 6: Verify GREEN and v1 compatibility**

Run: `uv run pytest tests/unit/test_stage_a_diagnostics.py tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_artifacts.py -q`

Expected: PASS.

Run: `uv run ruff format --check src/nl2sparql/dataset/stage_a/diagnostics.py src/nl2sparql/dataset/stage_a/verify.py scripts/09_generate_stage_a_v2.py tests/unit/test_stage_a_diagnostics.py tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py && uv run ruff check src/nl2sparql/dataset/stage_a/diagnostics.py src/nl2sparql/dataset/stage_a/verify.py scripts/09_generate_stage_a_v2.py tests/unit/test_stage_a_diagnostics.py tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py`

Expected: PASS.

- [ ] **Step 7: Commit diagnostic isolation**

```bash
git add src/nl2sparql/dataset/stage_a/diagnostics.py src/nl2sparql/dataset/stage_a/verify.py src/nl2sparql/dataset/stage_a/__init__.py scripts/09_generate_stage_a_v2.py tests/unit/test_stage_a_diagnostics.py tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_v2_workflow.py
git commit -m "feat(dataset): add unbilled Stage A diagnostics"
```

### Task 4: Regenerated Candidate and Determinism Proof

**Files:**

- Modify: `data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl`
- Modify: `data/dataset/raw/generation-config-v2-candidate.json`
- Modify: `data/dataset/raw/stats-v2-candidate.md`
- Modify: `tests/unit/test_stage_a_v2_artifacts.py`

**Interfaces:**

- Consumes Tasks 1-2 relationship pool and generator.
- Produces regenerated candidate bytes and actual SHA-256 values.
- Preserves all accepted paths as absent and all Stage A v1 hashes.

- [ ] **Step 1: Update deterministic artifact expectations only after code is GREEN**

Add assertions for candidate lifecycle, exact pair binding, old failing pair absence unless evidenced, 1,000 records, 25 intents, `350/450/200`, 206/126 plan shape, and accepted-path absence. Do not hard-code new hashes until produced from actual serialized bytes.

- [ ] **Step 2: Build twice in isolated temporary directories**

Run the offline CLI twice with `--value-pools data/dataset/raw/stage-a-v2-evidence-pools.json` and separate `--output`, `--config`, and `--stats` paths. Require `cmp -s` success for all three files. Neither command may pass `--preflight`, `--diagnostic`, or `--live`.

Expected: byte-identical candidate builds with 1,000 records, 25 intents, lifecycle `candidate`, and `acceptance_eligible=false`.

- [ ] **Step 3: Regenerate committed candidate paths**

Run the offline CLI with the genuine evidence pool and default candidate output paths. Parse all outputs, calculate actual SHA-256 values, and add those exact values to the artifact test.

- [ ] **Step 4: Verify candidate and immutable artifacts**

Run: `uv run pytest tests/unit/test_stage_a_v2.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py -q`

Expected: PASS.

Recheck Stage A v1 hashes, the new evidence-pool hash, JSON/JSONL parsing, and accepted-path absence. Run `git diff --check` and require PASS.

- [ ] **Step 5: Commit regenerated candidate**

```bash
git add tests/unit/test_stage_a_v2_artifacts.py data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl data/dataset/raw/generation-config-v2-candidate.json data/dataset/raw/stats-v2-candidate.md
git commit -m "data(dataset): regenerate pair-backed Stage A v2 candidate"
```

### Task 5: Full Local Verification and 206-Witness Diagnostic

**Files:**

- Create from measured output: `docs/evidence/stage-a-v2-account-pair-diagnostic.json`
- Modify: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/planning/prioritized-backlog-2026-09-21.md`

**Interfaces:**

- Consumes Tasks 1-4 plus the current billing-disabled project and free quota.
- Produces a diagnostic-only report for all 206 logical witnesses, or truthful failure evidence.
- Does not produce or authorize accepted artifacts.

- [ ] **Step 1: Run complete local verification before provider use**

Run:

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
git diff --check
```

Expected: full suite and checks pass. Recheck immutable v1 hashes, candidate hashes, evidence-pool hash, and accepted-path absence.

- [ ] **Step 2: Reconfirm billing-disabled state and execute diagnostic once**

Run the CLI with `--diagnostic`, the genuine evidence pool, and the default diagnostic report path. The command must internally confirm unlinked billing before client creation, complete the initial 126-query preflight below 96 GiB, use immediate dry-runs and cache-disabled executions capped at 20 GiB each, and never retry.

Expected success: 206/206 non-empty logical witnesses, 126 physical executions, zero cache hits, and exact processed/billed metadata. On quota, provider, empty, malformed, or cap failure: stop this plan's provider work, verify accepted paths remain absent, record the failure truthfully, and do not weaken validation.

- [ ] **Step 3: Validate diagnostic evidence and artifact isolation**

Run:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --validate-diagnostic-report docs/evidence/stage-a-v2-account-pair-diagnostic.json \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Expected: validation passes, physical bytes are counted once, every logical
group is covered exactly once, and query IDs/digests/membership agree across
initial dry-run, immediate dry-run, and execution evidence. Recompute all
artifact hashes and require only the diagnostic report and later documentation
to differ from Step 1.

- [ ] **Step 4: Record measured diagnostic outcome**

Record complete billing/job/count/byte/cache facts, every logical-witness
outcome, candidate hashes, and the statement that diagnostic evidence is not
acceptance evidence in the task document and diagnostic artifact. Add one
concise reverse-chronological decision-log entry for pair-level provenance and
the diagnostic/acceptance boundary. Update only the compact T3.3/P0 status and
next action in the backlog; do not restore removed history or out-of-scope model
paths. Preserve the two earlier failed live attempts in the task record and Git
history.

- [ ] **Step 5: Commit diagnostic evidence**

```bash
git add docs/evidence/stage-a-v2-account-pair-diagnostic.json docs/tasks/phase-3-dataset/02-synthetic-pipeline.md docs/memory/05-DECISION_LOG.md docs/planning/prioritized-backlog-2026-09-21.md
git commit -m "docs(evidence): record pair-backed Stage A diagnostics"
```

### Task 6: Final Verification, Fresh Preflight, and Approval Stop

**Files:**

- Modify after measurement: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify after measurement: `docs/memory/05-DECISION_LOG.md`
- Modify after measurement: `docs/planning/prioritized-backlog-2026-09-21.md`

**Interfaces:**

- Consumes the green local suite, regenerated candidate, and successful Task 5 diagnostic.
- Produces a fresh dry-run-only 206/126 acceptance estimate and final handoff.
- Does not run final live acceptance.

- [ ] **Step 1: Run final repository verification**

Run `uv run pytest -q`, `uv run ruff format --check .`, `uv run ruff check .`, JSON/JSONL parsing, hash checks, and `git diff --check`. Require every accepted path to remain absent.

- [ ] **Step 2: Run the fresh preflight only**

Run:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --preflight \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Expected: 206 logical witnesses, 126 physical queries, total estimate no more than `103,079,215,104` bytes, and maximum query no more than `21,474,836,480` bytes. Preflight performs no execution and writes no artifact.

- [ ] **Step 3: Compute and document the cost boundary**

Record exact total bytes/GiB, maximum query ID/template/bytes, both caps, per-template totals, and gross estimated cost using the current official BigQuery on-demand reference rate. State the source/rate date, that billing is not linked, and that free-tier/quota and billed bytes determine actual charge.

- [ ] **Step 4: Prove preflight was read-only**

Recompute candidate, v1, evidence-pool, diagnostic-report, and accepted-path state. Require no change from before preflight.

- [ ] **Step 5: Commit truthful preflight evidence**

```bash
git add docs/tasks/phase-3-dataset/02-synthetic-pipeline.md docs/memory/05-DECISION_LOG.md docs/planning/prioritized-backlog-2026-09-21.md
git commit -m "docs(evidence): record pair-backed Stage A preflight"
```

Keep detailed measurements in the T3.2 task record. In the cleaned backlog,
update only the current Stage A/T3.3 status and next action. In the decision
log, amend the single account-pair decision only when the measured preflight
changes its consequences; do not add a second operational-history entry.

- [ ] **Step 6: STOP for explicit acceptance approval**

Report logical/physical counts, total estimate, maximum query, caps, diagnostic processed/billed totals, candidate hashes, billing-disabled state, and accepted-path absence. Do not run `--live` until the user separately approves the exact current preflight.
