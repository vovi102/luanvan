# Stage A v2 CQ35 correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved BridgeProtocol/1 ETH correction and exact CQ35 mapping, then verify the new candidate without publishing acceptance.

**Architecture:** Add a separately selected training catalogue 1.2.0; preserve historical 1.0.0 and 1.1.0 bytes. Change only the large-native-to-class template's example/CQ/validation metadata and neutralize its bilingual value wording. Archive pre-CQ35 template inputs so immutable failed diagnostics remain reproducible.

**Tech Stack:** Python, pytest, JSON, GoogleSQL, BigQuery bounded witness diagnostics.

**Spec:** `docs/research/stage-a-v2-large-class-coverage-audit-2026-10-14.md` and linked CQ audit; user approved implementation 2026-10-15.

## Global Constraints

- Keep SQL, six output columns, inclusive NUMERIC 1 ETH threshold and window `[2026-06-15, 2026-06-16)`; BridgeProtocol fill, 41 medium records, n=1..41.
- 1,000 records, 25 intents, seed 42, difficulty 350/450/200; derive 206 logical / 126 physical queries.
- CQ35 describes recipient label class and native transaction value, not successful fund movement, deposit/outflow or CQ26 coverage.
- Preserve all other 24 templates, catalogue 1.0.0/1.1.0, V1, evidence pools, previous reports and benchmark/model results.
- No accepted V2 or canonical bilingual publication, merge, push or PR. Final `--live` requires separate fresh-preflight approval.
- Billing disabled/unlinked; cache and request/job/result retries disabled. 20 GiB/query, 96 GiB aggregate diagnostic caps; stop provider work on first failure, no retry.

## Review Focus

- Wrong catalogue version/CQ count must fail closed; old source fingerprints remain reproducible.
- CQ35 language must not infer receipt success or decoded bridge operation.
- Existing failed diagnostic must be checked against its old inputs, not regenerated CQ35 records.
- Parameter correction must change exactly the 41 allocation positions, not unrelated templates.
- Successful diagnostic is not accepted publication; no provider repeat after failure.

### Task 1: Local versioned correction and deterministic regeneration

**Files:** sql/schema.py, new catalogue ethereum_analytics_stage_a_v2_1_2.json, templates/templates.json, bilingual/templates.json, tests/unit/test_stage_a_v2_cq35.py, tests/fixtures/dataset/stage-a-v2-pre-cq35-templates.json, diagnostic/artifact regression tests and candidate artifacts.

**Interfaces:** Consumes approved audit prototype and unchanged input pools; produces TRAINING_CATALOG_PATH selecting 1.2.0, exact CQ01–CQ35, the same record/slot/projection contract, new candidate hashes and preserved historical diagnostic reconstruction.

- [x] Write tests for exact version guards, old catalogue hashes, production query equality to audited Bridge witness, CQ35 mapping, neutral bilingual rendering and changed-record positions. Archive historical templates as test inputs, not an active library.
- [x] Run `.venv/bin/pytest tests/unit/test_stage_a_v2_cq35.py -q`; Expected: FAIL before 1.2.0/Bridge correction.
- [x] Add catalogue 1.2.0 with unchanged CQ01–CQ34 and explicit CQ35; select it without overwriting 1.1.0. Correct one template's fill/CQ/validation note and bilingual value wording; update partial-diagnostic tests to use immutable historical inputs.
- [x] Regenerate candidate twice with existing evidence pools; compare bytes and measure hashes. Expected: exactly 41 changed records (759..799), unchanged 206/126 topology, no accepted files; update measured hash tests only.
- [x] Run focused CQ35/catalogue/template/diagnostic/artifact/bilingual tests, Ruff/diff checks, then `.venv/bin/pytest -q`; Expected: PASS.
- [x] Commit `feat(dataset): bind large native class intent to CQ35`.

### Task 2: Bounded diagnostic, provenance and review handoff

**Files:** new dated diagnostic/preflight evidence, implementation/status docs.

**Interfaces:** Consumes Task 1 exact candidate and template/catalogue hashes; produces a validated diagnostic and, only on success, fresh dry-run approval evidence.

- [x] Run a one-shot diagnostic with an injected no-retry client, internal complete initial plus immediate preflights, disabled cache and verified unlinked/disabled billing. Expected: 126 executions / 206 logical results pass, or retain first failure and stop.
- [x] Validate report offline with `scripts/09_generate_stage_a_v2.py --validate-diagnostic-report` and exact current pools. Expected: report validates; status is explicitly reported, never inferred from validation exit code.
- [x] Only if passed, run fresh dry-run preflight; record candidate/catalogue fingerprints, actual bytes/caps and approval-only status. Expected: no accepted artifacts.
- [x] Update provenance/phase task status and commit; run offline report validation as Task 2 completion check.
- [x] Fresh whole-branch read-only review under requesting-code-review; any Important/Critical fix uses TDD and one full-suite fix pass, no second reviewer. Keep branch/worktree and request final-live approval only if ready.
