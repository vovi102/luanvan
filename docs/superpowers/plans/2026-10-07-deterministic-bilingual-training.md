# Deterministic Bilingual Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blocked Gemini training-data path with an offline,
agent-authored, deterministic 200-pattern catalog that expands the accepted
1,000-record Stage A snapshot into a validated 8,000-record English–Vietnamese
training artifact.

**Architecture:** Strict catalog and expanded-record contracts form the producer
boundary. A pure renderer binds the four English and four Vietnamese patterns
for each Stage A intent, while assembly validates immutable semantics, diversity,
held-out exclusion indexes, group-aware splits, audit evidence, canonical hashes,
and recoverable atomic publication. CLI 20 builds locally and CLI 21 creates or
validates mechanical exclusion indexes and validates published artifacts; neither
imports provider, model, translation, or inference modules.

**Tech Stack:** Python 3.11, standard-library dataclasses/JSON/hashlib/string
formatting, Click, pytest, Ruff, and existing Stage A/template/normalization and
recoverable-publication utilities.

**Spec:** `docs/superpowers/specs/2026-10-07-deterministic-bilingual-training-design.md`

## Global Constraints

- The source is exactly 1,000 accepted records from the 25 pinned Stage A intent
  templates.
- The catalog has exactly 200 entries: 25 intents × `en|vi` × `formal|conversational|abbreviated|alternative`.
- The clean output has exactly 8,000 records: 4,000 per language and eight per
  semantic family.
- SQL, slots, expected columns, schema elements, entities, semantic anchors, and
  Stage A source hashes are immutable.
- `generation_model` and `provider` are null; `api_request_count` is `0`; and
  `recorded_cost_usd` is `0.00`.
- The producer must not import or initialize Gemini, OpenRouter, Qwen, a
  translator, sentence-transformers, or any other model/network client, and must
  not read provider-related environment variables or secrets.
- The 26-record Gemini pilot is historical evidence only and is never an input.
- Catalog authoring uses only Stage A intents, slot schemas, SQL semantics, and
  the production template catalog; held-out benchmark wording, review notes,
  predictions, and evaluation outputs are prohibited authoring inputs.
- English T3.5 and the Vietnamese candidate draft remain held out. Mechanical
  leakage validation consumes only a derived exclusion index containing digests
  and hashed high-order token n-grams, not raw benchmark wording.
- Splits are group-aware on `semantic_family_id`; all eight clean variants of a
  family remain in one split.
- Audit evidence is append-only and truthfully uses `reviewer_type=agent`; no
  independent or human review claim is permitted.
- Use TDD for every code behavior and make focused commits.

## Review Focus

- Patterns with escaped braces, repeated placeholders, missing placeholders, or
  Unicode-normalization surprises must fail before expansion; Task 1 tests this.
- Slot values containing braces or format syntax must render as literal values,
  and no unresolved placeholder may survive; Task 2 tests this.
- One altered SQL byte, slot value, entity, schema element, expected column, or
  source digest must block publication; Task 2 tests this.
- Input reordering, clock/environment variation, and reruns must not change
  artifact or manifest bytes; Tasks 2–4 test this.
- Empty/malformed exclusion or audit evidence, path aliasing, interrupted
  publication, and provider-related environment variables must fail closed
  without leaking secrets; Tasks 3–4 test this.

---

## File Structure

- `src/nl2sparql/dataset/bilingual/contracts.py`: strict catalog, expanded-row,
  exclusion-index, audit-event, configuration, and report contracts.
- `src/nl2sparql/dataset/bilingual/templates.json`: the finite 200-pattern source
  artifact with agent authorship/review metadata and content digests.
- `src/nl2sparql/dataset/bilingual/rendering.py`: catalog loading/validation,
  literal placeholder binding, stable expansion, protected-anchor checks, and
  per-family/language diversity metrics.
- `src/nl2sparql/dataset/bilingual/assembly.py`: Stage A validation, exclusion
  indexes, group-aware split assignment, stratified audit sampling, audit gates,
  manifest/hash validation, and recoverable atomic publication.
- `scripts/20_build_bilingual_training.py`: offline build/validate/audit-summary
  composition over explicit local paths.
- `scripts/21_validate_bilingual_training.py`: offline exclusion-index creation
  and artifact/manifest validation over explicit local paths.
- `tests/unit/test_bilingual_contracts.py`: strict schema and catalog coverage.
- `tests/unit/test_bilingual_rendering.py`: rendering, immutability, diversity,
  order-independence, and exact count gates.
- `tests/unit/test_bilingual_assembly.py`: exclusion, split, audit, manifest,
  hash, and publication behavior.
- `tests/unit/test_bilingual_training_workflows.py`: CLI isolation and end-to-end
  deterministic workflow behavior.

### Task 1: Strict Contracts and the 200-Pattern Catalog

**Files:**
- Create: `src/nl2sparql/dataset/bilingual/__init__.py`
- Create: `src/nl2sparql/dataset/bilingual/contracts.py`
- Create: `src/nl2sparql/dataset/bilingual/templates.json`
- Create: `tests/unit/test_bilingual_contracts.py`

**Interfaces:**
- Consumes: the 25 production template definitions returned by
  `load_templates()`.
- Produces: `Language`, `Style`, `CatalogEntry`, `Catalog`,
  `ExpandedTrainingRecord`, `SplitConfig`, `ExclusionIndex`, `AuditEvent`,
  `AuditSummary`, and `load_catalog(path, templates) -> Catalog`.

- [ ] **Step 1: Write failing strict-contract and catalog-coverage tests**

  Add tests proving exact fields/types, frozen values, exact content digests,
  200 unique entry IDs, 25 intent IDs, all eight language/style combinations per
  intent, exact placeholder/schema equality, `author_type=agent`, and
  `review_type=agent-reviewed`. Include missing/extra/repeated placeholder,
  duplicate entry, unknown language/style, and digest-tamper failures.

- [ ] **Step 2: Run tests and verify RED**

  Run: `uv run pytest tests/unit/test_bilingual_contracts.py -q`

  Expected: FAIL because the bilingual contracts/catalog package does not exist.

- [ ] **Step 3: Implement strict contracts and catalog loader**

  Parse exact JSON field sets into frozen dataclasses. Extract placeholders with
  `string.Formatter`, reject positional/conversion/format-spec fields and repeated
  names, compare them with each production template's slot keys, and recompute
  each entry digest from canonical content excluding the digest field.

- [ ] **Step 4: Author and review all 200 patterns**

  Write four semantically faithful English and four natural Vietnamese patterns
  per production intent using only the approved authoring inputs. Keep SQL
  identifiers and protected slot values literal, and record finite-catalog
  provenance without claiming per-row human review.

- [ ] **Step 5: Run focused tests and lint**

  Run: `uv run pytest tests/unit/test_bilingual_contracts.py -q && uv run ruff check src/nl2sparql/dataset/bilingual/contracts.py tests/unit/test_bilingual_contracts.py`

  Expected: all tests pass and Ruff exits 0.

- [ ] **Step 6: Commit**

  ```bash
  git add src/nl2sparql/dataset/bilingual tests/unit/test_bilingual_contracts.py
  git commit -m "feat(dataset): add deterministic bilingual catalog"
  ```

### Task 2: Pure Renderer and Semantic Validation

**Files:**
- Create: `src/nl2sparql/dataset/bilingual/rendering.py`
- Create: `tests/unit/test_bilingual_rendering.py`

**Interfaces:**
- Consumes: `Catalog`, production template definitions, and accepted Stage A
  mappings.
- Produces: `render_pattern(entry, slot_values) -> str`,
  `expand_stage_a(records, catalog, templates) -> tuple[ExpandedTrainingRecord, ...]`,
  `validate_expansion(records, stage_a, templates) -> DiversityReport`, and
  `serialize_records(records) -> bytes`.

- [ ] **Step 1: Write failing literal-rendering tests**

  Test exact binding for dates, integers, hashes, token symbols, addresses,
  Vietnamese Unicode, and literal slot values containing braces. Reject missing,
  extra, duplicate, empty, or unresolved placeholders.

- [ ] **Step 2: Run literal-rendering tests and verify RED**

  Run: `uv run pytest tests/unit/test_bilingual_rendering.py -q`

  Expected: FAIL because rendering functions do not exist.

- [ ] **Step 3: Implement minimal literal renderer**

  Use parsed named fields and direct string assembly rather than evaluating
  format expressions. Normalize only the derived comparison form; preserve the
  rendered UTF-8 question exactly.

- [ ] **Step 4: Write failing full-expansion and immutable-field tests**

  Pin stable IDs/digests, eight variants per family, exact 8,000/4,000/4,000
  counts, 1,000 families, exact language/style/intent distributions, stable
  output under reversed input/catalog order, unique IDs/questions, and unchanged
  SQL/slots/expected columns/schema/entities/source digest/semantic anchors.
  Mutate each immutable field separately and require failure.

- [ ] **Step 5: Write failing diversity tests**

  Assert per-family/language mean pairwise normalized Levenshtein distance is
  strictly greater than `0.30`, report min/mean/max/quantiles plus failing IDs,
  and reject one family at the exact boundary.

- [ ] **Step 6: Implement expansion and validation**

  Sort source records by ID and catalog entries by stable ID before expansion;
  derive expected columns from the hash-bound production template definition;
  validate all anchors with existing T3.3 anchor logic plus literal slot
  preservation; compute record digests from canonical exact fields.

- [ ] **Step 7: Run focused tests and lint**

  Run: `uv run pytest tests/unit/test_bilingual_rendering.py tests/unit/test_bilingual_contracts.py -q && uv run ruff check src/nl2sparql/dataset/bilingual tests/unit/test_bilingual_rendering.py`

  Expected: all tests pass and Ruff exits 0.

- [ ] **Step 8: Commit**

  ```bash
  git add src/nl2sparql/dataset/bilingual/rendering.py tests/unit/test_bilingual_rendering.py
  git commit -m "feat(dataset): render deterministic bilingual variants"
  ```

### Task 3: Leakage, Splits, Audit, Manifest, and Atomic Publication

**Files:**
- Create: `src/nl2sparql/dataset/bilingual/assembly.py`
- Create: `tests/unit/test_bilingual_assembly.py`

**Interfaces:**
- Consumes: expanded records, source/catalog/config bytes, a derived
  `ExclusionIndex`, and append-only `AuditEvent` rows.
- Produces: `build_exclusion_index(held_out_documents, *, ngram_size=12) -> ExclusionIndex`,
  `validate_no_leakage(records, index) -> LeakageReport`,
  `assign_group_splits(records, config) -> tuple[ExpandedTrainingRecord, ...]`,
  `select_audit_sample(records, language, seed=42) -> tuple[str, ...]`,
  `validate_audit(events, sample_ids) -> AuditSummary`,
  `build_manifest(...) -> dict[str, object]`, `validate_artifacts(...) -> ValidationReport`,
  and `publish_artifacts(...) -> None`.

- [ ] **Step 1: Write failing exclusion-index and leakage tests**

  Test that the index stores only normalized full-text digests and hashed
  12-token n-grams plus source file hashes/counts, never raw text. Reject exact
  normalized matches, any configured 12-gram hash match, malformed/empty indexes,
  benchmark IDs/review fields, and attempts to pass held-out raw paths to the
  renderer/build interface.

- [ ] **Step 2: Run leakage tests and verify RED**

  Run: `uv run pytest tests/unit/test_bilingual_assembly.py -q`

  Expected: FAIL because assembly functions do not exist.

- [ ] **Step 3: Implement mechanical exclusion and leakage reports**

  Keep raw held-out parsing in the index-builder seam only. Canonically sort and
  hash the derived index; validation receives the index object/bytes and cannot
  recover held-out wording.

- [ ] **Step 4: Write failing group-split and audit tests**

  Pin deterministic 90/10 train/dev assignment by SHA-256 of seed and family ID,
  no family crossing, and stable balanced counts. Require each 100-row language
  audit sample to cover all 25 intents × four styles exactly once. Validate
  append-only event sequencing, unique latest decision per sampled record,
  `reviewer_type=agent`, at least 95 faithful and 90 natural per language, and
  reject fabricated human/independent provenance or threshold failure.

- [ ] **Step 5: Implement splits, sampling, and audit gates**

  Preserve eight-record families and count by split/language/style/intent/family.
  Bind audit events to record digests and make replacement/revision an explicit
  later event rather than an overwrite.

- [ ] **Step 6: Write failing manifest/hash/publication tests**

  Pin null provider/model, zero calls/cost, honest provenance, all required
  counts/hashes/diversity/audit/exclusion fields, deterministic manifest bytes,
  tamper detection, output/manifest/audit path non-aliasing, concurrent lock,
  rollback after second replace failure, and recovery after an interruption.

- [ ] **Step 7: Implement manifest validation and recoverable publication**

  Reuse the established lock/journal/backup pattern from noise artifacts, extend
  it to output/manifest/audit evidence as one transaction, and fsync staged files
  and the containing directory before declaring publication complete.

- [ ] **Step 8: Run focused tests and lint**

  Run: `uv run pytest tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_rendering.py -q && uv run ruff check src/nl2sparql/dataset/bilingual tests/unit/test_bilingual_assembly.py`

  Expected: all tests pass and Ruff exits 0.

- [ ] **Step 9: Commit**

  ```bash
  git add src/nl2sparql/dataset/bilingual/assembly.py tests/unit/test_bilingual_assembly.py
  git commit -m "feat(dataset): assemble and audit bilingual training"
  ```

### Task 4: Offline CLI 20/21 and Canonical Artifact

**Files:**
- Create: `scripts/20_build_bilingual_training.py`
- Create: `scripts/21_validate_bilingual_training.py`
- Create: `tests/unit/test_bilingual_training_workflows.py`
- Create when policy permits: `data/dataset/processed/bilingual-training.jsonl`
- Create when policy permits: `data/dataset/processed/bilingual-training-manifest.json`
- Create: `data/dataset/processed/bilingual-training-audit.jsonl`
- Create: `data/dataset/processed/bilingual-training-exclusion-index.json`

**Interfaces:**
- Consumes: Tasks 1–3 through explicit local file paths.
- Produces: CLI 20 modes `build|validate-only|audit-sample`; CLI 21 modes
  `index-exclusions|validate-catalog|validate-artifact`; deterministic JSON
  summaries and non-zero exits for every failed gate.

- [ ] **Step 1: Write failing CLI isolation tests**

  Import both scripts under blockers for network/model/provider modules. Set
  sentinel provider secrets and replace environment access with a guard; assert
  help, validation, indexing, and build never read those names, initialize a
  model, access network, or emit the sentinel. Test input/output alias rejection.

- [ ] **Step 2: Run CLI tests and verify RED**

  Run: `uv run pytest tests/unit/test_bilingual_training_workflows.py -q`

  Expected: FAIL because CLI 20/21 do not exist.

- [ ] **Step 3: Implement thin CLI composition**

  Keep Click wrappers limited to local parsing, pure module calls, canonical
  summaries, and generic secret-safe failures. `index-exclusions` is the only
  mode allowed to parse raw held-out question files; it emits only irreversible
  hashes and aggregate counts.

- [ ] **Step 4: Add failing end-to-end reproducibility test**

  Build twice from the same fixture with reversed source order and differing
  output paths; assert identical output/manifest/audit hashes and exact counts,
  then validate the published pair. Assert `api_request_count=0`, cost `0.00`,
  and null provider/model.

- [ ] **Step 5: Implement end-to-end build and validation**

  Require a passing catalog, expansion, leakage report, audit thresholds, and
  artifact validation before the publication transaction begins.

- [ ] **Step 6: Run focused workflow tests and CLI help**

  Run: `uv run pytest tests/unit/test_bilingual_training_workflows.py tests/unit/test_bilingual_*.py -q && uv run python scripts/20_build_bilingual_training.py --help && uv run python scripts/21_validate_bilingual_training.py --help`

  Expected: all tests pass; both help commands exit 0 without credentials.

- [ ] **Step 7: Build exclusion index and audit samples without exposing wording**

  Run CLI 21 `index-exclusions` against immutable English T3.5 and the Vietnamese
  review draft, printing only hashes/counts. Run CLI 20 `audit-sample` and review
  all 100 English plus 100 Vietnamese rows, appending truthful agent decisions.
  If either language misses 95 faithful or 90 natural, fix catalog entries and
  restart the affected TDD/catalog build cycle; never waive the gate.

- [ ] **Step 8: Build and validate the canonical clean artifact twice**

  Run CLI 20 `build`, CLI 21 `validate-artifact`, and a second build to separate
  temporary paths. Compare output and manifest hashes before retaining only
  repository-policy-allowed canonical artifacts.

- [ ] **Step 9: Run focused tests and lint**

  Run: `uv run pytest tests/unit/test_bilingual_*.py -q && uv run ruff check src/nl2sparql/dataset/bilingual scripts/20_build_bilingual_training.py scripts/21_validate_bilingual_training.py tests/unit/test_bilingual_*.py`

  Expected: all tests pass and Ruff exits 0.

- [ ] **Step 10: Commit**

  ```bash
  git add src/nl2sparql/dataset/bilingual scripts/20_build_bilingual_training.py scripts/21_validate_bilingual_training.py tests/unit/test_bilingual_*.py data/dataset/processed/bilingual-training-*.json*
  git commit -m "feat(workflows): publish offline bilingual training data"
  ```

### Task 5: Evidence, Governance, and Final Verification

**Files:**
- Modify: `.superpowers/sdd/2026-10-04-bilingual-nl2sql/progress.md`
- Create: `.superpowers/sdd/2026-10-07-deterministic-bilingual-training/progress.md`
- Modify: `docs/tasks/phase-3-dataset/03-paraphrasing.md`
- Modify: `docs/tasks/phase-3-dataset/04-noise-injection.md`
- Modify: `docs/planning/prioritized-backlog-2026-09-21.md`
- Modify: `docs/memory/01-ARCHITECTURE.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

**Interfaces:**
- Consumes: validated Task 4 artifacts and verification output.
- Produces: truthful counts, hashes, diversity/audit results, zero-call/cost
  evidence, supersession records, limitations, and branch handoff.

- [ ] **Step 1: Update task/backlog/decision/architecture evidence**

  Mark the Gemini producer as an incomplete historical pilot superseded by the
  deterministic path. Record exact artifact paths/counts/hashes/audit results,
  shared-agent-authorship limitation, and the still-pending human review of the
  100 Vietnamese benchmark candidates. Do not mark benchmark finalization done.

- [ ] **Step 2: Update both progress ledgers**

  Preserve completed Tasks 1 and 4–8 plus CLI 23/24, mark old Tasks 2–3 and old
  CLI 20/21 as superseded, and record each replacement task's commits, tests, and
  rulings in the new plan workspace ledger.

- [ ] **Step 3: Run artifact validators and secret/policy checks**

  Run Stage A validation, catalog/artifact/leakage validation, retrieval snapshot
  regressions, manifest/hash validation, a repository secret-pattern scan, JSON
  parsing for changed JSON artifacts, `git diff --check`, and inspect
  `git status --ignored` before staging.

- [ ] **Step 4: Run full verification**

  Run: `uv run pytest -q && uv run ruff format --check . && uv run ruff check . && git diff --check`

  Expected: full pytest and every Ruff/diff gate exit 0. Report any pre-existing
  dependency warning separately rather than suppressing it.

- [ ] **Step 5: Commit evidence and final verified adjustments**

  ```bash
  git add docs .superpowers/sdd/2026-10-04-bilingual-nl2sql/progress.md
  git commit -m "docs(evidence): record deterministic bilingual training"
  ```

- [ ] **Step 6: Perform whole-branch fresh-context review and fix findings TDD-first**

  Review from merge-base with `main` through final HEAD against this plan and both
  approved bilingual specs. Critical/Important findings require one RED→GREEN fix
  pass and a fresh full suite; Minor findings are ledgered for user disposition.

- [ ] **Step 7: Push and create a PR when remote permissions permit**

  Push `design/bilingual-nl2sql`, create a PR into `main`, and leave it unmerged.
  Report the PR URL or the exact external permission/tooling blocker.
