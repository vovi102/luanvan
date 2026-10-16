# Stage A v2 Supported-Intent Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unsupported mixer-to-DEX intent with a data-backed category-owner distribution intent, regenerate the deterministic Stage A v2 candidate, and promote it only after separately approved genuine BigQuery verification.

**Architecture:** Keep the existing Stage A v2 generator, logical-to-physical witness graph, 126-query batch planner, lifecycle writers, and evidence pool. Change only the retired template's production contract, its 34-record allocation key, and its eight bilingual catalog entries; then rebuild every candidate-bound digest from serialized bytes. Use the existing preflight/live CLI boundary so local work cannot create accepted artifacts and a live run cannot start until its fresh measured cost is explicitly approved.

**Tech Stack:** Python 3.11, JSON/JSONL, Click, Google Cloud BigQuery client, pytest, Ruff, Git.

**Spec:** `docs/superpowers/specs/2026-10-11-stage-a-v2-supported-intent-revision-design.md`

## Global Constraints

- Remove `T_MIXER_TO_DEX_LARGE_FLOW`; add `T_CATEGORY_OWNER_DISTRIBUTION` linked only to `CQ20`.
- The replacement is `transaction_aggregation`, `hard`, allocated exactly 34 records, and has only integer slot `n` in the inclusive range 1 through 100.
- Keep exactly 1,000 records, 25 intents, seed 42, and difficulty totals `350 easy / 450 medium / 200 hard`.
- Keep exactly 170 logical witness groups and 126 physical queries, derived from the generated plan rather than edited into metadata.
- Preserve `data/dataset/raw/stage-a-v2-evidence-pools.json` byte-for-byte, including 45 unique block numbers and 45 unique transaction hashes with exactly `{value, source, evidence}` per entry.
- Preserve all Stage A v1 artifacts byte-for-byte.
- Candidate regeneration may write only the three `*-v2-candidate*` paths and must retain lifecycle `candidate`, `acceptance_eligible=false`.
- Keep BigQuery caps at 20 GiB per physical query and 96 GiB for the complete initial preflight; disable query cache and require Standard SQL.
- Do not execute a paid live query until a fresh exact preflight has been reported and the user has explicitly approved that measured execution.
- Create accepted artifacts atomically only when 1,000/1,000 records have `non_empty=true`, the evidence graph is complete, cache hits are zero, and preflight/execution provenance is consistent.
- Do not start the bilingual audit, canonical 8,000-record build, or B1/B2 training in this plan. Vietnamese benchmark preparation must not be represented as human approval.
- Never read, print, or commit credential material.

## Review Focus

- A replacement accidentally linked to `CQ21` or `CQ30` would overstate supported semantics; Task 1 pins exact `cq_ids == ["CQ20"]` and absence of cross-category-owner language.
- Generic limit generation can drift when pool-backed slots are absent; Task 1 proves the 34 replacement records use exactly `n=1..34` and one limit-monotonic witness group.
- Bilingual text can retain mixer semantics or stale placeholders while still parsing; Task 2 asserts all eight exact IDs, `{n}` as the only placeholder, and no retired template reference.
- Regeneration can silently overwrite lifecycle or immutable inputs; Task 3 snapshots v1 and the evidence pool, checks candidate-only writes, and compares two independent builds byte-for-byte.
- A changed query estimate or empty live result can invalidate the earlier approval; Tasks 5-6 require fresh cap checks, a separate approval stop, immediate re-dry-runs, exact columns, non-empty rows, and atomic failure behavior.

---

### Task 1: Production Template and Deterministic Allocation Contract

**Files:**

- Modify: `tests/unit/test_query_templates.py`
- Modify: `tests/unit/test_stage_a_v2_artifacts.py`
- Modify: `tests/unit/test_stage_a_witness_planning.py`
- Modify: `src/nl2sparql/dataset/templates/templates.json`
- Modify: `src/nl2sparql/dataset/stage_a_v2.py`

**Interfaces:**

- Consumes: the existing template-library schema, `render_template(...)`, `generate_stage_a_v2_records(...)`, `build_witness_groups(...)`, and `build_stage_a_v2_witness_queries(...)`.
- Produces: production template `T_CATEGORY_OWNER_DISTRIBUTION`, allocation `V2_TEMPLATE_ALLOCATION["T_CATEGORY_OWNER_DISTRIBUTION"] == 34`, and 34 generated records whose only varying slot is `n`.
- Preserves: all other template definitions, allocation counts/order, record schema, witness identity rules, and planner interfaces.

- [ ] **Step 1: Write failing template-contract tests**

Update `EXPECTED_IDS` in `test_query_templates.py` and add `test_category_owner_distribution_has_exact_supported_contract`. Assert the retired ID is absent and the replacement has exactly:

```python
assert replacement["name"] == "Category owner distribution"
assert replacement["category"] == "transaction_aggregation"
assert replacement["difficulty"] == "hard"
assert replacement["slots"] == {"n": {"type": "integer", "min": 1, "max": 100}}
assert replacement["cq_ids"] == ["CQ20"]
assert replacement["expected_columns"] == [
    "category",
    "owner_count",
    "account_count",
    "accounts_per_owner",
    "owner_rank",
]
assert replacement["schema_elements"] == [
    "entity_labels_v1.category",
    "entity_labels_v1.owner",
    "entity_labels_v1.address",
]
assert replacement["validation"]["expect_non_empty"] is True
assert "CQ21" not in replacement["cq_ids"]
assert "CQ30" not in replacement["cq_ids"]
```

Also assert rendered SQL equals the exact GoogleSQL in the approved spec and its scope note says it summarizes the accepted label dictionary without claiming one owner spans categories.

- [ ] **Step 2: Write failing generation and witness tests**

In `test_stage_a_v2_artifacts.py`, add `test_replacement_uses_34_monotonic_limits_without_changing_population` with these assertions:

```python
replacement = [r for r in records if r["template_id"] == "T_CATEGORY_OWNER_DISTRIBUTION"]
assert len(replacement) == 34
assert [r["slot_values"] for r in replacement] == [{"n": n} for n in range(1, 35)]
assert len({r["witness_group_id"] for r in replacement}) == 1
assert Counter(r["difficulty"] for r in records) == {"easy": 350, "medium": 450, "hard": 200}
assert len(records) == 1000
assert len({r["template_id"] for r in records}) == 25
```

In `test_stage_a_witness_planning.py`, assert the replacement group's witness is its `n=1` record, all 34 group members are retained, the complete plan still derives 170 logical groups and 126 physical queries, and reversing records leaves the physical plan unchanged.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `uv run pytest tests/unit/test_query_templates.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py -q`

Expected: FAIL because the production library and allocation still reference `T_MIXER_TO_DEX_LARGE_FLOW`.

- [ ] **Step 4: Replace the production template and allocation key**

In `templates.json`, replace the retired object with the exact contract and SQL from the spec. Set `example_fill` to `{"n": 10}` and use an `nl_seed` asking for the top `{n}` accepted label categories ranked by distinct owners, including account count and accounts per owner.

In `stage_a_v2.py`, replace only the old allocation key with `"T_CATEGORY_OWNER_DISTRIBUTION": 34`. Do not add template-specific generation logic: the existing generic limit logic must yield `n=1..34` because this template has no pool-backed slots.

- [ ] **Step 5: Run focused tests and Ruff**

Run: `uv run pytest tests/unit/test_query_templates.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py -q`

Expected: PASS with 25 templates, 1,000 records, `350/450/200`, 170 logical groups, and 126 physical queries.

Run: `uv run ruff format --check src/nl2sparql/dataset/stage_a_v2.py tests/unit/test_query_templates.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py && uv run ruff check src/nl2sparql/dataset/stage_a_v2.py tests/unit/test_query_templates.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py`

Expected: PASS.

- [ ] **Step 6: Commit the supported template contract**

```bash
git add src/nl2sparql/dataset/templates/templates.json src/nl2sparql/dataset/stage_a_v2.py tests/unit/test_query_templates.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py
git commit -m "feat(dataset): replace unsupported Stage A v2 intent"
```

### Task 2: Eight-Pattern Bilingual Catalog Migration

**Files:**

- Modify: `tests/unit/test_bilingual_contracts.py`
- Modify: `src/nl2sparql/dataset/bilingual/templates.json`

**Interfaces:**

- Consumes: the replacement template's sole `{n}` slot and `catalog_entry_digest(entry) -> str` from `nl2sparql.dataset.bilingual.contracts`.
- Produces: exactly four English and four Vietnamese `T_CATEGORY_OWNER_DISTRIBUTION` entries, one for each existing style, with recomputed content digests.
- Preserves: catalog schema version, author/review metadata, 200 total catalog entries, two languages, four styles, and all unrelated entries byte-for-byte.

- [ ] **Step 1: Replace stale expected-copy tests with exact replacement copy**

Change the eight mixer assertions in `test_bilingual_contracts.py` to the following approved intent copy:

```text
en/formal: List the top {n} label categories ranked by distinct owner count, including account count and accounts per owner.
en/conversational: Which {n} label categories have the most distinct owners, and how many accounts and accounts per owner does each have?
en/abbreviated: Top {n} label categories by owners, with accounts and accounts/owner.
en/alternative: Rank {n} categories in the accepted label dictionary by unique owners and return each category's account total and accounts-per-owner ratio.
vi/formal: Liệt kê {n} danh mục nhãn đứng đầu theo số chủ sở hữu riêng biệt, kèm số tài khoản và số tài khoản trên mỗi chủ sở hữu.
vi/conversational: {n} danh mục nhãn nào có nhiều chủ sở hữu riêng biệt nhất, và mỗi danh mục có bao nhiêu tài khoản cùng tỷ lệ tài khoản trên chủ sở hữu?
vi/abbreviated: Top {n} danh mục nhãn theo số chủ sở hữu, kèm số tài khoản và tài khoản/chủ sở hữu.
vi/alternative: Xếp hạng {n} danh mục trong từ điển nhãn đã chấp nhận theo số chủ sở hữu duy nhất, đồng thời trả về tổng tài khoản và tỷ lệ tài khoản trên mỗi chủ sở hữu.
```

Add assertions that each entry has `placeholders == ("n",)`, all eight normalized patterns are unique, no catalog entry references the retired ID, and none of the replacement patterns claim a cross-category owner.

- [ ] **Step 2: Run the bilingual contract test and verify RED**

Run: `uv run pytest tests/unit/test_bilingual_contracts.py -q`

Expected: FAIL because the catalog still contains eight mixer entries and old placeholders.

- [ ] **Step 3: Replace only the eight bilingual catalog entries**

Retain the existing entry order and style/language matrix. Change each ID, `template_id`, pattern, and placeholders to the values above. Recompute each `content_sha256` with `catalog_entry_digest` over the entry body; do not hand-copy stale digests or change `author_type`, `review_type`, or `catalog_schema_version`.

- [ ] **Step 4: Run bilingual and downstream catalog tests**

Run: `uv run pytest tests/unit/test_bilingual_contracts.py tests/unit/test_bilingual_rendering.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py -q`

Expected: PASS with exactly 200 entries and exact references to the 25 production templates.

Run: `uv run ruff format --check tests/unit/test_bilingual_contracts.py && uv run ruff check tests/unit/test_bilingual_contracts.py`

Expected: PASS.

- [ ] **Step 5: Commit the catalog migration**

```bash
git add src/nl2sparql/dataset/bilingual/templates.json tests/unit/test_bilingual_contracts.py
git commit -m "feat(dataset): migrate category distribution prompts"
```

### Task 3: Regenerated Candidate and Immutable-Input Proofs

**Files:**

- Modify: `tests/unit/test_stage_a_v2_artifacts.py`
- Modify: `data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl`
- Modify: `data/dataset/raw/generation-config-v2-candidate.json`
- Modify: `data/dataset/raw/stats-v2-candidate.md`

**Interfaces:**

- Consumes: updated production templates/allocation and default offline value pools through `scripts/09_generate_stage_a_v2.py`.
- Produces: regenerated candidate data, manifest, and stats whose hashes are calculated from actual bytes.
- Preserves: evidence-pool SHA-256 `1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8` and the three immutable v1 hashes listed in Step 1.

- [ ] **Step 1: Strengthen immutable and lifecycle assertions**

Extend `test_candidate_writer_is_deterministic_and_preserves_v1_bytes` or add a focused regression asserting:

```python
assert _sha256(V1_ARTIFACT) == "a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709"
assert _sha256(V1_CONFIG) == "781495b7a70614bd6b87861781a816946f2443ac1c66cab2bba16df58afbe713"
assert _sha256(V1_STATS) == "bc93c7a9355a34e531b275181646db269968040d2484e8a2876a8329db8579db"
assert _sha256(Path("data/dataset/raw/stage-a-v2-evidence-pools.json")) == "1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8"
```

Also assert the default candidate manifest remains `candidate`, `acceptance_eligible=false`, `verification_mode="offline_candidates"`, and none of the three accepted default paths exists after an offline build.

- [ ] **Step 2: Run the lifecycle tests before regeneration**

Run: `uv run pytest tests/unit/test_stage_a_v2_artifacts.py -q`

Expected: PASS for the code-level lifecycle, immutable-hash, and accepted-path guards.

- [ ] **Step 3: Build two isolated candidates and compare exact bytes**

Run:

```bash
candidate_tmp_a="$(mktemp -d)"
candidate_tmp_b="$(mktemp -d)"
uv run python scripts/09_generate_stage_a_v2.py --output "$candidate_tmp_a/data.jsonl" --config "$candidate_tmp_a/config.json" --stats "$candidate_tmp_a/stats.md"
uv run python scripts/09_generate_stage_a_v2.py --output "$candidate_tmp_b/data.jsonl" --config "$candidate_tmp_b/config.json" --stats "$candidate_tmp_b/stats.md"
cmp -s "$candidate_tmp_a/data.jsonl" "$candidate_tmp_b/data.jsonl"
cmp -s "$candidate_tmp_a/config.json" "$candidate_tmp_b/config.json"
cmp -s "$candidate_tmp_a/stats.md" "$candidate_tmp_b/stats.md"
```

Require each command to return exit code 0. Neither generation invocation may pass `--preflight` or `--live`.

Expected: two byte-identical builds, each reporting 1,000 records, 25 intents, lifecycle `candidate`, and `acceptance_eligible=false`.

- [ ] **Step 4: Regenerate the committed candidate paths**

Run: `uv run python scripts/09_generate_stage_a_v2.py`

Expected: only the three v2 candidate artifacts are rewritten. Parse the JSON/JSONL and report their actual SHA-256 values, record count, 25-intent coverage, `350/450/200` totals, and lifecycle. Confirm the retired ID occurs zero times and the replacement occurs 34 times.

- [ ] **Step 5: Verify hashes and immutable inputs after regeneration**

Run: `uv run pytest tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_stage_a_witness_planning.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py -q`

Expected: PASS; accepted v2 outputs remain absent, the evidence-pool hash is unchanged, and all v1 hashes equal Step 1.

Run: `git diff --check`

Expected: PASS.

- [ ] **Step 6: Commit truthful candidate bytes**

```bash
git add tests/unit/test_stage_a_v2_artifacts.py data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl data/dataset/raw/generation-config-v2-candidate.json data/dataset/raw/stats-v2-candidate.md
git commit -m "data(dataset): regenerate supported Stage A v2 candidate"
```

### Task 4: Provider-Free Gate and Full Local Verification

**Files:**

- Modify if required by changed fixtures: `tests/unit/test_stage_a_v2_workflow.py`
- Modify if required by changed fixtures: `tests/unit/test_stage_a_verify.py`
- Modify if required by changed fixtures: `tests/unit/test_bilingual_assembly.py`
- Modify if required by changed fixtures: `tests/unit/test_bilingual_training_workflows.py`

**Interfaces:**

- Consumes: regenerated candidate records, existing fake BigQuery clients, existing 20/96 GiB caps, and atomic accepted writer.
- Produces: local evidence that the new SQL preserves preflight/live fail-closed behavior without contacting BigQuery.
- Preserves: lazy Google imports, 126 physical dry-runs, cache prohibition, immediate re-dry-run checks, and candidate/accepted source gates.

- [ ] **Step 1: Add replacement-specific fake-provider regressions**

Ensure fake live results for `T_CATEGORY_OWNER_DISTRIBUTION` use exactly `category`, `owner_count`, `account_count`, `accounts_per_owner`, and `owner_rank`. Add or adapt tests proving an empty result or a missing/reordered/unexpected column rejects the live report and leaves all accepted targets absent. Keep tests proving cap overflow, cache hit, SQL-digest drift, and missing evidence edges fail closed.

- [ ] **Step 2: Run focused workflow tests against the new contract**

Run: `uv run pytest tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_v2_artifacts.py -q`

Expected: PASS without provider access. If a stale mixer fixture fails, continue to Step 3; if production validation fails, diagnose it without weakening a gate.

- [ ] **Step 3: Update only stale fixtures; do not weaken production gates**

Replace retired template IDs/columns in fake reports. Do not change validation thresholds, cap constants, cache policy, evidence completeness, or accepted-writer logic unless a failing test demonstrates an actual contract mismatch introduced by Task 1.

- [ ] **Step 4: Run the complete local verification suite**

Run: `uv run pytest -q`

Expected: PASS.

Run: `uv run ruff format --check . && uv run ruff check .`

Expected: PASS.

Run: `git diff --check`

Expected: PASS.

Recheck the v1 and evidence-pool hashes from Task 3 and verify the three accepted v2 paths are still absent.

- [ ] **Step 5: Commit fixture-only changes if Step 3 required them**

```bash
git add tests/unit/test_stage_a_v2_workflow.py tests/unit/test_stage_a_verify.py tests/unit/test_stage_a_v2_artifacts.py tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py
git commit -m "test(dataset): cover supported Stage A v2 verification"
```

Skip this commit if no files changed.

### Task 5: Fresh BigQuery Preflight and Mandatory Cost-Approval Stop

**Files:**

- Modify after measurement: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify after measurement: `docs/memory/05-DECISION_LOG.md`
- Modify after measurement: `docs/planning/prioritized-backlog-2026-09-21.md`

**Interfaces:**

- Consumes: existing Application Default Credentials without reading or printing credential contents, genuine evidence pool, regenerated records in memory, and `_run_preflight(...)`.
- Produces: a fresh read-only BigQuery estimate with exact logical/physical counts, caps, maximum query, per-template totals, and estimated gross on-demand cost when a reference rate is available.
- Does not produce: accepted artifacts or authority to execute live queries.

- [ ] **Step 1: Confirm the preflight command cannot overwrite artifacts**

Record current hashes/existence for v1, all three candidate files, the evidence pool, and all three accepted paths. Confirm repository tests from Task 4 are green and the worktree has no unexplained changes.

- [ ] **Step 2: Run the genuine dry-run-only command**

Run:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --preflight \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Expected: JSON reports `logical_witness_count == 170`, `physical_query_count == 126`, per-query cap `21,474,836,480`, aggregate cap `103,079,215,104`, an exact total estimate below the aggregate cap, and a maximum query below the per-query cap. If credentials, quota, dataset permission, or either cap fails, stop immediately and report the blocker; do not run live.

- [ ] **Step 3: Prove preflight was read-only and report its cost boundary**

Recompute Step 1 hashes/existence and require no artifact changes. Report:

- exact estimated bytes and GiB;
- 170 logical witness groups and 126 physical queries;
- 20 GiB per-query and 96 GiB aggregate caps;
- maximum query ID/template/bytes;
- per-template query counts/bytes; and
- gross estimated cost using `estimated_bytes / 2**40 * reference_USD_per_TiB`, clearly identifying the rate and noting that free tier and billed bytes can change actual charge.

- [ ] **Step 4: Record the measured preflight as preflight-only evidence**

Update the three status documents with the new candidate hashes and exact dry-run measurements. State explicitly that no query executed, no accepted artifact exists, and the old failed run is not acceptance evidence.

- [ ] **Step 5: Commit the preflight record**

```bash
git add docs/tasks/phase-3-dataset/02-synthetic-pipeline.md docs/memory/05-DECISION_LOG.md docs/planning/prioritized-backlog-2026-09-21.md
git commit -m "docs(evidence): record revised Stage A v2 preflight"
```

- [ ] **Step 6: STOP for explicit live-cost approval**

Do not continue to Task 6 in the same approval. Present the measured estimate and wait for the user to approve that exact live execution. A previous approval for the superseded SQL plan does not authorize the revised plan.

### Task 6: Approved Live Acceptance and Final Evidence Audit

**Files:**

- Create only on complete success: `data/dataset/raw/synthetic-stage-a-v2.jsonl`
- Create only on complete success: `data/dataset/raw/generation-config-v2.json`
- Create only on complete success: `data/dataset/raw/stats-v2.md`
- Modify after success or failure: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify after success or failure: `docs/memory/05-DECISION_LOG.md`
- Modify after success or failure: `docs/planning/prioritized-backlog-2026-09-21.md`

**Interfaces:**

- Consumes: explicit approval for the exact Task 5 estimate and the existing live verifier, which repeats full preflight and immediate per-query dry-runs.
- Produces on success: atomically published accepted Stage A v2 data, manifest, and stats with complete genuine evidence.
- Produces on failure: no accepted outputs; only a truthful operational record of the failed attempt.

- [ ] **Step 1: Reconfirm the approval matches the current plan**

Require unchanged candidate/template/evidence-pool hashes since Task 5. If inputs changed or repeated preflight exceeds either cap, stop and obtain a new estimate approval.

- [ ] **Step 2: Execute the approved live command once**

Run:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --live \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Expected on success: complete initial preflight, consistent immediate dry-runs, cache-disabled execution, 170 logical proofs over 126 physical queries, and atomic creation of all three accepted paths. On any empty result, schema mismatch, cache hit, cap overflow, provenance drift, or provider error, stop; verify all accepted paths remain absent and do not retry without a new diagnosis/approval.

- [ ] **Step 3: Audit accepted artifact invariants from bytes**

Parse the accepted JSONL and manifest and assert:

```python
assert len(records) == 1000
assert len({record["id"] for record in records}) == 1000
assert len({record["sql"] for record in records}) == 1000
assert len({record["template_id"] for record in records}) == 25
assert Counter(record["difficulty"] for record in records) == {
    "easy": 350,
    "medium": 450,
    "hard": 200,
}
assert all(record["verification"]["non_empty"] is True for record in records)
assert all(record["verification"]["cache_hit"] is False for record in records)
assert manifest["lifecycle_state"] == "accepted"
assert manifest["acceptance_eligible"] is True
assert manifest["verified_record_count"] == 1000
assert manifest["witness_count"] == 170
assert manifest["physical_query_count"] == 126
assert manifest["cache_hit_count"] == 0
```

Validate every record hash, artifact hash, template-library hash, pool hash, initial/immediate/execution edge, job/location field, SQL digest, and aggregate metric. Report SHA-256 for the accepted data, manifest, and stats from their actual bytes. Recheck all v1 hashes and the evidence-pool hash.

- [ ] **Step 4: Run final repository verification**

Run: `uv run pytest -q`

Expected: PASS.

Run: `uv run ruff format --check . && uv run ruff check .`

Expected: PASS.

Run: `git diff --check`

Expected: PASS.

- [ ] **Step 5: Record the truthful live outcome**

On success, update the three status documents with actual accepted hashes, record/intent/difficulty counts, logical/physical counts, processed and billed bytes, cache-hit count, and lifecycle `accepted`. On failure, record the exact failed gate and actual jobs/bytes while stating that accepted outputs remain absent. Never describe a failed run as acceptance evidence.

- [ ] **Step 6: Commit the live outcome**

Success path:

```bash
git add data/dataset/raw/synthetic-stage-a-v2.jsonl data/dataset/raw/generation-config-v2.json data/dataset/raw/stats-v2.md docs/tasks/phase-3-dataset/02-synthetic-pipeline.md docs/memory/05-DECISION_LOG.md docs/planning/prioritized-backlog-2026-09-21.md
git commit -m "data(dataset): accept Stage A v2 with live evidence"
```

Failure path: commit only truthful documentation/evidence files that changed; do not add accepted outputs.

- [ ] **Step 7: Stop at the post-acceptance boundary**

If and only if Task 6 succeeded, propose a separate execution plan for the manual audit of 100 English plus 100 Vietnamese records. Only after documented human audit approval may a later plan build the canonical 8,000-record corpus twice and compare bytes. Keep B1/B2 training blocked until both gates complete.
