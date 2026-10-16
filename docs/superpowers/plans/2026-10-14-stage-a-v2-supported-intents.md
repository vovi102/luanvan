# Supported Stage A v2 intents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the approved keep-one/replace-three coverage proposal without weakening acceptance.

**Architecture:** Preserve the historical default SQL catalogue byte-for-byte. Add an explicitly selected 1.1.0 training catalogue containing unchanged CQ01–CQ30 and new CQ31–CQ34; template validation uses this revision. Replace three templates in their allocation positions and correct funding semantics, then regenerate only v2 candidate artifacts.

**Tech Stack:** Python, pytest, GoogleSQL, bilingual JSON catalogues.

**Spec:** `docs/research/stage-a-v2-hard-intent-coverage-audit-2026-10-14.md` (user approved 2026-10-14).

## Global Constraints

- 1,000 records, 25 intents, seed 42, difficulty 350/450/200; derive 206 logical groups and 126 physical queries.
- Preserve v1 bytes, historical catalogue, benchmark wording/gold, prior evidence and model results.
- No merge, push, PR, canonical bilingual publication or accepted v2 artifacts.
- No retries or query cache; executions require billing disabled/unlinked, bounded preflights; final acceptance requires separate approval.
- Replacements use only start_date/end_date/n; funding keeps six projected columns and duration 60.

## Review Focus

- Historical consumers must keep their catalogue hash, rather than silently adopt new CQs.
- Unknown catalogue versions and wrong exact CQ sets must fail closed.
- Funding language must permit equal timestamps without implying causation or within-block ordering.
- Concentration patterns must include successful positive values and minimum ten transactions.
- Token diversity must count contracts and recipients, not sum heterogeneous quantities.

### Task 1: Versioned CQ extension and four template contracts

**Files:** schema.py, SQL catalogue revision, templates.json, stage_a_v2.py, tests/unit/test_stage_a_v2_supported_intents.py, tests/unit/test_query_templates.py.

**Interfaces:** Consumes approved audit SQL prototypes; produces TRAINING_CATALOG_PATH (Path), version-aware validate_catalog(), unchanged template record fields, new allocation IDs.

- [x] Write regression tests for historical SHA, exact CQ31–34 additions, reject version/set mismatches, exact prototype SQL, funding predicates and mappings.
- [x] Run `.venv/bin/pytest tests/unit/test_stage_a_v2_supported_intents.py -q`; Expected: FAIL for absent revision/replacements.
- [x] Add version-specific exact CQ guards, a separate training catalogue, explicit template-validator selection and approved SQL replacements.
- [x] Run `.venv/bin/pytest tests/unit/test_stage_a_v2_supported_intents.py tests/unit/test_query_templates.py tests/unit/test_sql_schema.py -q`; Expected: PASS.
- [x] Commit `feat(dataset): version supported hard-intent CQ contracts`.

### Task 2: Bilingual migration and reproducible candidate

**Files:** bilingual/templates.json, bilingual tests, candidate artifacts and artifact hash tests.

**Interfaces:** Consumes Task 1 template IDs/slots; produces 200 reviewed patterns and regenerated v2 candidate bytes.

- [x] Add tests for eight patterns per new intent, funding timestamp wording and concentration minimum ten; run targeted tests; Expected: FAIL before migration.
- [x] Replace 24 retired patterns, correct eight funding patterns, refresh content hashes using the existing digest function; regenerate candidate twice and compare bytes.
- [x] Run targeted bilingual/v2 tests; Expected: PASS, 1,000 records, 133 changed records, unchanged evidence pools and historical files.
- [x] Run `.venv/bin/pytest -q`; Expected: PASS.
- [x] Commit `feat(dataset): migrate bilingual supported intents and candidate`.

### Task 3: Bounded diagnostic and handoff

**Files:** new diagnostic evidence, provenance/status documentation.

**Interfaces:** Consumes Task 2 candidate; produces independently validated diagnostic and fresh dry-run preflight, never accepted files.

- [x] Inspect diagnostic controls; run only after billing disabled/unlinked and caps confirmed. Expected: retries/cache disabled.
- [x] Execute one bounded diagnostic and validate it locally. Expected: 206 logical witnesses, 126 physical executions, all non-empty; retain evidence and stop provider work on failure.
- [x] Conditional success branch not run: diagnostic failed at an unchanged intent, so provider work stopped as required. Initial preflight is not acceptance approval.
- [x] Review implementation and report remaining final-live approval gate.

**Execution outcome:** Tasks 1–2 verified, 1,442 tests pass. Task 3 took the specified failure branch: all four revised intents have non-empty production witnesses, but unchanged `T_LARGE_TX_TO_CLASS` / `syn-v2-000759` returned zero rows. Failed report validated offline; no retry, further provider work, accepted publication or final preflight. See the implementation provenance document for exact metrics and proposed next scope.

**Final review:** Fresh reviewer identified two Important evidence-validation
defects; both fixed with RED/GREEN regressions. Final full suite: 1,462 passed.
No second reviewer or provider execution. See
`docs/superpowers/reviews/2026-10-14-stage-a-v2-supported-intents.md`.
