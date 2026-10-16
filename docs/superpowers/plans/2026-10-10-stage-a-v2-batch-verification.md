# Stage A v2 Batched Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove all 170 Stage A v2 logical witnesses below the unchanged 96 GiB aggregate cap by batching the 45 exact transaction-hash lookups into one physical BigQuery query.

**Architecture:** Add a provider-neutral logical-to-physical evidence graph and a Stage A v2 physical-query planner. The existing verifier dry-runs and executes physical queries, validates logical results, and propagates their provenance to records; v1 uses the unchanged one-query-per-group planner. The v2 CLI exposes a dry-run-only approval boundary before its live path can publish accepted artifacts.

**Tech Stack:** Python 3.11, frozen dataclasses, Click, Google Cloud BigQuery client, JSON/JSONL, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-10-stage-a-v2-batch-verification-design.md`

## Global Constraints

- Preserve Stage A v1 bytes, paths, behavior, historical evidence, and default one-query-per-group verification.
- Keep exactly 1,000 Stage A v2 records, 25 intents, 170 logical witnesses, seed 42, and difficulty totals `350/450/200`.
- Keep the per-physical-query cap at 20 GiB and aggregate physical-preflight cap at 96 GiB.
- Disable BigQuery query cache and require Standard SQL for every dry-run and execution.
- Require complete initial preflight before execution, then immediate re-dry-run of identical SQL before each physical execution.
- Do not create accepted artifacts unless every logical group has a non-empty proof, all evidence edges agree, and every execution has `cache_hit=false`.
- Do not run `--live`, audit bilingual samples, build the canonical 8,000-row corpus, or start B1/B2 without the separate approvals specified below.
- Never read, print, or commit credential material.

## Review Focus

- BigQuery may return batch rows in any order; Task 2 tests group-ID mapping rather than positional mapping.
- Missing, duplicate, unexpected, or wrong-hash batch rows must reject the whole run; Task 2 tests every case.
- Shared physical metrics must be counted once, not once per logical hash; Tasks 2 and 3 test 126-query accounting.
- Initial and immediate estimates may differ while SQL digest and group membership must match; Task 2 tests both facts.
- A preflight or partial live failure must leave every accepted output untouched; Task 4 tests atomic publication boundaries.

---

### Task 1: Physical Query Plan and Evidence Contracts

**Files:**

- Create: `src/nl2sparql/dataset/stage_a/planning.py`
- Modify: `src/nl2sparql/dataset/stage_a/evidence.py:15-65`
- Modify: `src/nl2sparql/dataset/stage_a/__init__.py:8-24`
- Create: `tests/unit/test_stage_a_witness_planning.py`

**Interfaces:**

- Consumes: `build_witness_groups(records) -> tuple[WitnessGroup, ...]` and the immutable `T_TX_BY_HASH` record slots/SQL contract.
- Produces: `WitnessQuery(query_id, query_sha256, proof_kind, template_id, group_ids, sql)`, `LogicalWitnessResult(group_id, witness_record_id, row_count, columns)`, `build_single_witness_queries(records) -> tuple[WitnessQuery, ...]`, and `build_stage_a_v2_witness_queries(records) -> tuple[WitnessQuery, ...]`.
- Changes `WitnessDryRun` and `WitnessExecution` to physical-query evidence containing query identity, covered group IDs, BigQuery job/location provenance, and physical metrics. `WitnessExecution.immediate_dry_run` stores the required second dry-run, while `WitnessExecution.logical_results` carries one result per covered logical group.

- [ ] **Step 1: Write failing planner tests**

Add tests with these core assertions:

```python
queries = build_stage_a_v2_witness_queries(records)
assert len(build_witness_groups(records)) == 170
assert len(queries) == 126
batch = next(query for query in queries if query.proof_kind == "tx_hash_batch")
assert len(batch.group_ids) == 45
assert batch.query_sha256 == hashlib.sha256(batch.sql.encode()).hexdigest()
assert batch.sql.count("transaction_facts") == 1
assert build_stage_a_v2_witness_queries(list(reversed(records))) == queries
```

Also assert the default planner returns 170 `single` queries in existing group order, batch SQL contains all 45 exact hashes once, and invalid/mixed/repeated batch inputs raise `WitnessEvidenceError`.

- [ ] **Step 2: Run planner tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_witness_planning.py -q`

Expected: FAIL because `planning.py`, `WitnessQuery`, and the new evidence fields do not exist.

- [ ] **Step 3: Implement deterministic planning and evidence dataclasses**

Implement the interfaces above. Canonicalize only the v2 physical plan by group ID; validate group IDs and transaction hashes as lowercase hexadecimal before embedding literals. Compute `query_id` from proof kind, template ID, ordered group IDs, and SQL digest. Render the batch result schema as `witness_group_id` followed by the unchanged `T_TX_BY_HASH` columns.

- [ ] **Step 4: Run focused tests and Ruff**

Run: `uv run pytest tests/unit/test_stage_a_witness_planning.py tests/unit/test_stage_a_verify.py -q`

Expected: PASS after updating existing test constructors only as required by the typed evidence contract.

Run: `uv run ruff check src/nl2sparql/dataset/stage_a tests/unit/test_stage_a_witness_planning.py tests/unit/test_stage_a_verify.py`

Expected: PASS.

- [ ] **Step 5: Commit the planning seam**

```bash
git add src/nl2sparql/dataset/stage_a tests/unit/test_stage_a_witness_planning.py tests/unit/test_stage_a_verify.py
git commit -m "feat(dataset): plan batched Stage A witnesses"
```

### Task 2: Physical Preflight, Batch Execution, and Logical Proofs

**Files:**

- Modify: `src/nl2sparql/dataset/stage_a/verify.py:43-286`
- Modify: `tests/unit/test_stage_a_verify.py`

**Interfaces:**

- Consumes: `WitnessQuery`, `LogicalWitnessResult`, and a planner callable `Callable[[Sequence[Mapping[str, Any]]], tuple[WitnessQuery, ...]]` from Task 1.
- Produces: `dry_run_witnesses(..., query_planner=build_single_witness_queries) -> WitnessPreflight` and `verify_stage_a(..., query_planner=build_single_witness_queries) -> StageAVerificationReport`.
- `WitnessPreflight.witnesses` and `StageAVerificationReport.witnesses` contain physical evidence. Record propagation resolves each logical group through `WitnessExecution.logical_results`.

- [ ] **Step 1: Write failing preflight/accounting tests**

Add fake-job provenance and assert:

```python
preflight = dry_run_witnesses(client, records, query_planner=build_stage_a_v2_witness_queries)
assert len(preflight.witnesses) == 126
assert len(client.calls) == 126
assert preflight.total_estimated_bytes == sum(item.estimated_bytes for item in preflight.witnesses)
assert all(item.job_id and item.location == "US" for item in preflight.witnesses)
```

Use estimates where 170 logical scans exceed 96 GiB but 126 physical scans pass, and assert the unchanged default planner still performs 170 dry-runs and rejects the larger sum.

- [ ] **Step 2: Run preflight tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_verify.py -q -k 'preflight or budget'`

Expected: FAIL because the verifier still accepts groups rather than physical queries.

- [ ] **Step 3: Implement physical dry-run and cap enforcement**

Replace group-level submission with physical-query submission. Record `job_id`, location, query ID, SQL digest, proof kind, group IDs, and estimated bytes. Enforce 20 GiB per physical query and 96 GiB over unique physical queries before any execution.

- [ ] **Step 4: Write failing live batch-result tests**

Add tests asserting exactly one batch immediate dry-run and one batch execution, followed by 45 logical results. Parameterize malformed results:

```python
@pytest.mark.parametrize("failure", ["missing", "duplicate", "unexpected", "wrong_hash", "schema", "cache"])
def test_tx_hash_batch_fails_closed(failure): ...
```

Also assert shuffled valid rows pass, all 1,000 records receive `non_empty=true`, hash records remain `mode="live_exact"`, physical provenance is propagated, and initial/immediate estimates may differ without allowing query ID, SQL digest, or membership drift.

- [ ] **Step 5: Run live tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_verify.py -q -k 'batch or verification or cache'`

Expected: FAIL because the verifier cannot execute or split a batch result.

- [ ] **Step 6: Implement single and batch result validation**

Dispatch by `WitnessQuery.proof_kind`. Keep current schema/non-empty/count checks for `single`. For `tx_hash_batch`, require schema `("witness_group_id", *expected_columns)`, map rows by group ID, enforce exact membership/cardinality/hash equality, and emit one `LogicalWitnessResult` per group. Propagate physical query ID, SQL digest, job ID, and location into every verified record without multiplying physical totals.

- [ ] **Step 7: Run verifier regression tests**

Run: `uv run pytest tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_witness_planning.py tests/unit/test_stage_a_artifacts.py -q`

Expected: PASS, including unchanged v1 order, caps, and result semantics.

Run: `uv run ruff format --check src/nl2sparql/dataset/stage_a tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_witness_planning.py && uv run ruff check src/nl2sparql/dataset/stage_a tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_witness_planning.py`

Expected: PASS.

- [ ] **Step 8: Commit physical verification**

```bash
git add src/nl2sparql/dataset/stage_a/verify.py tests/unit/test_stage_a_verify.py
git commit -m "feat(dataset): verify transaction hashes in one batch"
```

### Task 3: Accepted Evidence Graph and Genuine Value Pool

**Files:**

- Create: `data/dataset/raw/stage-a-v2-evidence-pools.json`
- Modify: `src/nl2sparql/dataset/stage_a/v2_artifacts.py:44-515`
- Modify: `tests/unit/test_stage_a_v2_artifacts.py`
- Modify: `tests/unit/test_bilingual_assembly.py`
- Modify: `tests/unit/test_bilingual_training_workflows.py`

**Interfaces:**

- Consumes: physical `WitnessPreflight`, physical `WitnessExecution`, and their `LogicalWitnessResult` edges from Task 2.
- Produces: accepted manifest fields `witness_count`, `physical_query_count`, `preflight_evidence`, `execution_evidence`, and physical totals; record verification fields include `physical_query_id`, `query_sha256`, `job_id`, and `location`.
- Preserves: candidate manifest schema and all Stage A v1 files.

- [ ] **Step 1: Add the genuine evidence pool and hash test**

Add the already acquired pool exactly as captured and assert:

```python
assert hashlib.sha256(path.read_bytes()).hexdigest() == "1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8"
assert has_evidence_backed_live_values(load_value_pools(path)) is True
assert all(set(entry) == {"value", "source", "evidence"} for entry in block_and_hash_entries)
```

- [ ] **Step 2: Write failing evidence-graph tests**

Update the fake live report to model 170 logical groups over 126 physical queries. Assert the accepted manifest has `witness_count == 170`, `physical_query_count == 126`, one batch node with 45 group IDs, and physical bytes counted once. Parameterize tampering with duplicate physical IDs, missing logical edges, changed SQL digests, mismatched job IDs, repeated accounting, cache hits, and incomplete initial/immediate evidence.

- [ ] **Step 3: Run artifact tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py -q`

Expected: FAIL because the current manifest assumes one execution per logical group and has no evidence graph.

- [ ] **Step 4: Implement graph validation and serialization**

Validate exact typed report objects, unique physical nodes, complete initial-preflight/immediate-preflight/execution links, exactly-once logical coverage, record-to-execution equality, zero cache hits, and one verification timestamp. Serialize deterministic evidence arrays without raw BigQuery rows; compute processed, billed, latency, and cache totals once per physical execution.

- [ ] **Step 5: Update downstream accepted-source fixtures**

Update only fixtures that construct accepted manifests/reports. Keep downstream source validation strict and ensure candidate manifests or digest mismatches remain rejected.

- [ ] **Step 6: Run artifact and downstream tests**

Run: `uv run pytest tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py -q`

Expected: PASS.

Run: `uv run ruff format --check src/nl2sparql/dataset/stage_a/v2_artifacts.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py && uv run ruff check src/nl2sparql/dataset/stage_a/v2_artifacts.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py`

Expected: PASS.

- [ ] **Step 7: Commit artifact evidence**

```bash
git add data/dataset/raw/stage-a-v2-evidence-pools.json src/nl2sparql/dataset/stage_a/v2_artifacts.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py
git commit -m "feat(dataset): bind Stage A v2 physical evidence"
```

### Task 4: Dry-run CLI and Fail-closed Publication Boundary

**Files:**

- Modify: `scripts/09_generate_stage_a_v2.py:35-127`
- Modify: `tests/unit/test_stage_a_v2_workflow.py`

**Interfaces:**

- Consumes: `build_stage_a_v2_witness_queries`, `dry_run_witnesses`, and `verify_stage_a` from Tasks 1-2.
- Produces: mutually exclusive `--preflight` and `--live` modes. Preflight prints `mode`, `logical_witness_count`, `physical_query_count`, totals, caps, maximum query, and per-template totals, and writes no artifacts.
- Live mode always repeats preflight through `verify_stage_a`; it never consumes a saved preflight as authority.

- [ ] **Step 1: Write failing CLI-mode tests**

Assert offline mode still blocks Google imports. With injected fake clients, assert `--preflight` requires evidence-backed pools, performs only 126 dry-runs, emits deterministic JSON, and leaves candidate/accepted targets absent. Assert `--preflight --live` is rejected before credentials and a preflight cap failure never calls execution or artifact writers.

- [ ] **Step 2: Run workflow tests and verify RED**

Run: `uv run pytest tests/unit/test_stage_a_v2_workflow.py -q`

Expected: FAIL because `--preflight` and v2 planner injection do not exist.

- [ ] **Step 3: Implement lazy preflight and live planner selection**

Keep all Google imports inside preflight/live helpers. Add the mutually exclusive CLI flags, route both provider modes through `build_stage_a_v2_witness_queries`, and keep candidate mode byte-for-byte unchanged. Catch BigQuery/auth/verifier errors as `StageAV2WorkflowError` without writing accepted outputs.

- [ ] **Step 4: Run focused workflow verification**

Run: `uv run pytest tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_v2_artifacts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the approval boundary**

```bash
git add scripts/09_generate_stage_a_v2.py tests/unit/test_stage_a_v2_workflow.py
git commit -m "feat(dataset): add Stage A v2 preflight mode"
```

### Task 5: Repository Verification and Exact BigQuery Preflight

**Files:**

- Modify after measured evidence: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify after measured evidence: `docs/memory/05-DECISION_LOG.md`
- Modify after measured evidence: `docs/planning/prioritized-backlog-2026-09-21.md`

**Interfaces:**

- Consumes: implementation from Tasks 1-4 and the genuine evidence pool.
- Produces: verified implementation plus a measured, read-only BigQuery preflight report. It does not produce accepted artifacts before the explicit live approval gate.

- [ ] **Step 1: Run complete local verification**

Run:

```bash
uv run pytest
uv run ruff format --check .
uv run ruff check .
git diff --check
```

Expected: all tests pass (baseline was 1,613), Ruff passes, and no whitespace errors.

- [ ] **Step 2: Verify immutable artifacts and the pool**

Assert the immutable hashes remain exactly:

- v1 data: `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`;
- v1 config: `781495b7a70614bd6b87861781a816946f2443ac1c66cab2bba16df58afbe713`;
- v1 stats: `bc93c7a9355a34e531b275181646db269968040d2484e8a2876a8329db8579db`;
- v2 candidate data: `4746f68642913e0c40a0d19817cf0e4bf556f46d3ba1777a611f903e062e6561`;
- v2 candidate config: `fd5bdd9797e0e6af0ee184e9dcc4cc787a7526e3f3d05d0bdf73f8955c814a4d`;
- v2 candidate stats: `3b0f445fd12da9712f71e05a9075fd165ed32fd4cd658e1953abaa3c95e23a55`; and
- evidence pool: `1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8`.

Also assert no accepted v2 default output exists yet.

- [ ] **Step 3: Run the exact dry-run-only CLI**

Run:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --preflight \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Expected: 170 logical witnesses, 126 physical queries, every query at or below 20 GiB, aggregate at or below 96 GiB, no executions, and no accepted outputs. Record the actual bytes and current price-based estimate if determinable.

- [ ] **Step 4: Stop for explicit live-cost approval**

Report the exact preflight, caps, expected physical job count, and cost estimate. Do not run `--live` until the user explicitly approves this measured run.

- [ ] **Step 5: Commit truthful preflight documentation**

After the preflight report is available, update the three status documents with measured values and the still-pending live gate.

```bash
git add docs/tasks/phase-3-dataset/02-synthetic-pipeline.md docs/memory/05-DECISION_LOG.md docs/planning/prioritized-backlog-2026-09-21.md
git commit -m "docs(evidence): record batched Stage A v2 preflight"
```

### Task 6: Conditional Live Acceptance After Separate Approval

**Files:**

- Create only on complete success: `data/dataset/raw/synthetic-stage-a-v2.jsonl`
- Create only on complete success: `data/dataset/raw/generation-config-v2.json`
- Create only on complete success: `data/dataset/raw/stats-v2.md`
- Modify after complete success: the three status documents from Task 5

**Interfaces:**

- Consumes: the exact preflight approved in Task 5 and genuine BigQuery analytical objects.
- Produces: accepted v2 artifacts only if the repeated preflight and all physical executions pass.

- [ ] **Step 1: Run live only after explicit approval**

Run:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --live \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Expected: no cap failure, no empty logical proof, no schema mismatch, no cache hit, and three accepted outputs written atomically.

- [ ] **Step 2: Validate accepted artifacts**

Assert 1,000 records, 25 intents, `350/450/200`, 170 logical witnesses, 126 physical queries, 100% `non_empty=true`, complete evidence graph, zero cache hits, lifecycle `accepted`, exact pool/template/artifact hashes, and unchanged Stage A v1 bytes.

- [ ] **Step 3: Re-run full repository verification**

Run `uv run pytest`, `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check` again after artifact creation.

Expected: all pass.

- [ ] **Step 4: Record and commit live acceptance**

Update documentation with actual processed/billed bytes, job evidence, accepted hashes, and the next bilingual-audit gate. Commit accepted artifacts and truthful documentation. Do not start the audit or canonical build in this plan.
