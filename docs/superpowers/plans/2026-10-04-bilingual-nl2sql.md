# Bilingual English–Vietnamese NL2SQL Implementation Plan

> **Amended 2026-10-07:** This plan is partially executed. Tasks 2–3 and the
> generation/assembly portions of Task 9 (CLI 20/21) are superseded by
> `docs/superpowers/specs/2026-10-07-deterministic-bilingual-training-design.md`
> and must not be resumed as Gemini generation work. A replacement implementation
> plan will be written after that specification is reviewed. Completed Tasks 1
> and 4–8 plus CLI 23/24 remain valid.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible direct NL2SQL pipeline that accepts English,
accented Vietnamese, and unaccented Vietnamese, plus a separately measured
translation-first baseline and paired bilingual thesis evaluation.

**Architecture:** Add immutable language-aware records and derived normalization
forms at the dataset boundary, then reuse them in generation, noise, retrieval,
linking, and evaluation. Keep one direct bilingual inference path to the existing
GoogleSQL safety/execution layer; isolate translation as a baseline whose
intermediate output and latency are evidence. Freeze all training, encoder,
catalog, benchmark, and configuration hashes before primary evaluation.

**Tech Stack:** Python 3.11, Pydantic 2, Click, NumPy, sentence-transformers,
Google Gemini Developer API under explicit Free Tier controls, sqlglot, pytest,
Ruff, and the repository's existing BigQuery safety/evaluation modules.

**Spec:** `docs/superpowers/specs/2026-10-04-bilingual-nl2sql-design.md`

## Global Constraints

- Input support for English, accented Vietnamese, and unaccented Vietnamese is
  required; GoogleSQL remains the only output language.
- The direct production path must not require language detection or translation.
- Original user text is immutable evidence; derived text is NFC-normalized and
  accent folding is used only for matching.
- The finalized English T3.5 benchmark and its SQL are immutable.
- The Vietnamese benchmark contains exactly 100 cases paired one-to-one with
  English T3.5 by SQL and semantic identity.
- Vietnamese benchmark provenance is `agent-authored` and
  `single-human-reviewed`; never claim independent or multi-reviewer evidence.
- The user reviews all 100 Vietnamese cases before finalization.
- Training and development artifacts must exclude English T3.5, Vietnamese T3.5,
  unaccented derivatives, review notes, and evaluation outputs.
- Model, encoder, translator, prompt, catalog, dataset, and configuration
  revisions are pinned and hash-bound before primary inference.
- Any Gemini generation uses confirmed Free Tier only, records USD `0.00`, has
  checkpoint/resume, and has no paid fallback.
- Existing SQL safety, dry-run, bounded execution, privacy, and artifact
  publication gates remain mandatory.
- Acceptance gates are: 100/100 Vietnamese cases reviewed and safe/live verified;
  English regression at most 2 percentage points; Vietnamese gap at most 10
  percentage points; unaccented drop at most 10 percentage points; confidence
  intervals and complete failure counts reported.
- A failed scientific gate remains a failed result; it must not trigger tuning on
  held-out test cases.
- Use TDD for code tasks and make one focused commit per task.

## Review Focus

- Unicode input containing decomposed Vietnamese marks, mixed normalization, or
  text already without accents must preserve the original and yield stable NFC
  and match forms; Task 1 tests this.
- Addresses, token symbols, numbers, dates, SQL identifiers, and entity names must
  survive Vietnamese generation and noise unchanged; Tasks 2 and 3 test this.
- One semantic family appearing in multiple language/style variants must never
  cross split boundaries or dominate balanced sampling; Task 3 tests this.
- A stale embedding cache built with another encoder, revision, catalog, or
  normalization version must be rejected even when dimensions match; Task 5
  tests this.
- Missing translations, predictions, executions, or language pairs must remain
  denominator failures and must not silently disappear from gap metrics; Tasks 7
  and 8 test this.

---

## File Structure

New focused modules:

- `src/nl2sparql/language/contracts.py`: language and text-variant enums plus
  immutable normalized-input records.
- `src/nl2sparql/language/normalization.py`: NFC, whitespace, casefold, and
  Vietnamese accent-fold derivations that never mutate original text.
- `src/nl2sparql/dataset/bilingual/contracts.py`: Vietnamese generation and
  balanced bilingual snapshot schemas.
- `src/nl2sparql/dataset/bilingual/generation.py`: prompt requests, response
  validation, checkpoint identity, and Vietnamese Stage B/C expansion.
- `src/nl2sparql/dataset/bilingual/assembly.py`: semantic-family grouping,
  leakage checks, balancing, manifests, and immutable publication.
- `src/nl2sparql/dataset/testset/paired.py`: English/Vietnamese pairing,
  review/finalization, unaccented derivation, and hash validation.
- `src/nl2sparql/linking/bilingual_aliases.json`: reviewed Vietnamese schema and
  entity terminology without changing canonical SQL identifiers.
- `src/nl2sparql/linking/encoder_selection.py`: development-only multilingual
  encoder comparison and frozen selection evidence.
- `src/nl2sparql/baselines/translation.py`: pinned translator interface and
  translation-first evidence wrapper.
- `src/nl2sparql/evaluation/bilingual.py`: paired language/accent statistics,
  McNemar counts, and pre-registered gate evaluation.
- `scripts/20_generate_vietnamese_training.py` through
  `scripts/24_bilingual_evaluation.py`: thin, offline-first workflow entry points.

Existing modules are extended rather than bypassed: paraphrase and noise
validation, schema/entity document builders and indexes, B1/B2/B4/B5 shared
prompts and retrieval, canonical evaluation contracts/artifacts, SQL safety, and
test-set live verification.

### Task 1: Immutable Language and Normalization Contracts

**Files:**
- Create: `src/nl2sparql/language/__init__.py`
- Create: `src/nl2sparql/language/contracts.py`
- Create: `src/nl2sparql/language/normalization.py`
- Test: `tests/unit/test_language_normalization.py`

**Interfaces:**
- Consumes: raw question `str`.
- Produces: `Language = Literal["en", "vi"]`,
  `TextVariant = Literal["canonical", "unaccented"]`, and
  `normalize_input(text: str, *, language: Language) -> NormalizedInput` where
  `NormalizedInput` exposes immutable `original`, `nfc`, `match`,
  `accent_folded`, `language`, and `normalization_version` fields.

- [ ] **Step 1: Write failing normalization contract tests**

  Add tests named
  `test_normalize_input_preserves_original_and_composes_vietnamese`,
  `test_normalize_input_folds_accents_only_in_derived_form`,
  `test_normalize_input_leaves_addresses_symbols_dates_and_numbers_intact`,
  `test_normalize_input_is_idempotent_for_unaccented_vietnamese`, and
  `test_normalize_input_rejects_empty_control_or_unknown_language`. Assert that
  composed/decomposed equivalents share derived forms while `original` retains
  exact submitted bytes.

- [ ] **Step 2: Verify the tests fail for the missing package**

  Run: `uv run pytest tests/unit/test_language_normalization.py -q`

  Expected: FAIL during import of `nl2sparql.language`.

- [ ] **Step 3: Implement the minimal contracts and pure normalization**

  Use Unicode NFC for `nfc`, whitespace collapse plus `casefold()` for `match`,
  and NFD combining-mark removal followed by NFC for `accent_folded`. Validate
  one printable line and never infer the language.

- [ ] **Step 4: Run focused tests and lint**

  Run: `uv run pytest tests/unit/test_language_normalization.py -q && uv run ruff check src/nl2sparql/language tests/unit/test_language_normalization.py`

  Expected: all tests pass and Ruff exits 0.

- [ ] **Step 5: Commit**

  ```bash
  git add src/nl2sparql/language tests/unit/test_language_normalization.py
  git commit -m "feat(language): add immutable bilingual normalization"
  ```

### Task 2: Vietnamese Training Generation Contracts and Resume Safety

**Files:**
- Create: `src/nl2sparql/dataset/bilingual/__init__.py`
- Create: `src/nl2sparql/dataset/bilingual/contracts.py`
- Create: `src/nl2sparql/dataset/bilingual/generation.py`
- Create: `tests/unit/test_bilingual_generation.py`
- Modify: `src/nl2sparql/dataset/paraphrase/gemini.py`
- Modify: `src/nl2sparql/dataset/paraphrase/runner.py`
- Modify: `tests/unit/test_paraphrase_runner.py`

**Interfaces:**
- Consumes: validated English Stage A records and existing `GeminiClient`.
- Produces: `BilingualTrainingRecord`, `VietnamesePromptRequest`,
  `build_vietnamese_request(record, *, style) -> VietnamesePromptRequest`, and
  `run_vietnamese_generation(records, client, checkpoint_path, *, concurrency,
  cost_cap_usd) -> VietnameseGenerationReport`.

- [ ] **Step 1: Write failing strict-record and prompt tests**

  Assert exact fields `language`, `text_variant`, `semantic_family_id`,
  `source_record_sha256`, `sql`, `slot_values`, `entities_used`, `question`,
  `generation_id`, and provenance. Test `language == "vi"`, immutable SQL and
  anchors, Vietnamese-only instruction text, stable prompt hashes, and rejection
  of extra/missing fields or altered protected facts.

- [ ] **Step 2: Run contract tests and observe failure**

  Run: `uv run pytest tests/unit/test_bilingual_generation.py -q`

  Expected: FAIL because bilingual generation contracts do not exist.

- [ ] **Step 3: Implement contracts and deterministic request builders**

  Generate formal, casual, alternative, abbreviated, and unaccented-robust
  Vietnamese variants from SQL/semantic facts, never from held-out English test
  questions. Keep model IDs and all generation controls explicit in the request
  fingerprint.

- [ ] **Step 4: Write failing checkpoint and cost-deduplication tests**

  Cover interrupted batches, corrupt trailing JSONL, duplicate generation IDs,
  retry after 429, split batches, atomic checkpoint append, resume without repeat
  requests, and `recorded_cost_usd == 0.0` under Free Tier.

- [ ] **Step 5: Extend the shared Gemini runner and implement generation**

  Reuse transport/retry behavior from T3.3. Key completed work by generation ID
  and prompt hash; reject non-zero cost evidence or any provider/model mismatch.

- [ ] **Step 6: Run focused regression tests**

  Run: `uv run pytest tests/unit/test_bilingual_generation.py tests/unit/test_paraphrase_runner.py -q`

  Expected: all tests pass with no T3.3 resume regression.

- [ ] **Step 7: Commit**

  ```bash
  git add src/nl2sparql/dataset/bilingual src/nl2sparql/dataset/paraphrase/gemini.py src/nl2sparql/dataset/paraphrase/runner.py tests/unit/test_bilingual_generation.py tests/unit/test_paraphrase_runner.py
  git commit -m "feat(dataset): add resumable Vietnamese generation"
  ```

### Task 3: Vietnamese Noise and Balanced Bilingual Assembly

**Files:**
- Create: `src/nl2sparql/dataset/bilingual/assembly.py`
- Create: `src/nl2sparql/dataset/noise/abbreviations_vi.json`
- Create: `tests/unit/test_bilingual_assembly.py`
- Modify: `src/nl2sparql/dataset/noise/contracts.py`
- Modify: `src/nl2sparql/dataset/noise/transforms.py`
- Modify: `src/nl2sparql/dataset/noise/pipeline.py`
- Modify: `tests/unit/test_noise_transforms.py`
- Modify: `tests/unit/test_noise_pipeline.py`

**Interfaces:**
- Consumes: accepted English Stage A–D and validated Vietnamese variants.
- Produces: `inject_language_noise(record, *, seed) -> BilingualTrainingRecord`,
  `assemble_bilingual_snapshot(records, config) -> BilingualSnapshot`, and
  `publish_bilingual_snapshot(snapshot, output_path, manifest_path) -> None`.

- [ ] **Step 1: Write failing Vietnamese noise tests**

  Pin deterministic accent removal, Vietnamese abbreviation, fragment, typo, and
  mixed-case candidates. Assert exactly one declared operation per record and no
  mutation of protected addresses, token symbols, numbers, dates, identifiers,
  or reviewed entity names.

- [ ] **Step 2: Run noise tests and observe failure**

  Run: `uv run pytest tests/unit/test_noise_transforms.py tests/unit/test_noise_pipeline.py -q`

  Expected: FAIL for unsupported Vietnamese transforms/configuration.

- [ ] **Step 3: Add language-aware noise dictionaries and transforms**

  Preserve the existing English quotas and behavior. Require a language-specific
  dictionary and include its digest in output manifests.

- [ ] **Step 4: Write failing assembly, leakage, and balance tests**

  Test that semantic families cannot cross declared splits; final benchmark SQL,
  questions, derivatives, and IDs are rejected; duplicate normalized questions
  are rejected; language/style/noise counts meet the pinned configuration; and
  sampling is stable for seed 42 regardless of input order.

- [ ] **Step 5: Implement group-aware balanced assembly and publication**

  The manifest records source hashes, family counts, language/style/noise counts,
  configuration hash, exclusion-set hash, output hash, and provenance.

- [ ] **Step 6: Run focused tests and existing English regressions**

  Run: `uv run pytest tests/unit/test_bilingual_assembly.py tests/unit/test_noise_artifacts.py tests/unit/test_noise_pipeline.py tests/unit/test_noise_transforms.py -q`

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/nl2sparql/dataset/bilingual/assembly.py src/nl2sparql/dataset/noise tests/unit/test_bilingual_assembly.py tests/unit/test_noise_artifacts.py tests/unit/test_noise_pipeline.py tests/unit/test_noise_transforms.py
  git commit -m "feat(dataset): assemble balanced bilingual training data"
  ```

### Task 4: Paired Vietnamese Benchmark and Human Review Workflow

**Files:**
- Create: `src/nl2sparql/dataset/testset/paired.py`
- Create: `tests/unit/test_testset_paired.py`
- Create: `scripts/22_vietnamese_testset_workflow.py`
- Modify: `src/nl2sparql/dataset/testset/reviewed_contracts.py`
- Modify: `src/nl2sparql/dataset/testset/reviewed_validate.py`
- Modify: `src/nl2sparql/dataset/testset/live.py`

**Interfaces:**
- Consumes: immutable `data/dataset/test/test-100.jsonl`, its manifest/live
  evidence, an agent-authored Vietnamese draft, and user review decisions.
- Produces: `PairedCandidate`, `PairedReviewDecision`,
  `validate_pairing(english, vietnamese) -> PairingReport`,
  `derive_unaccented_cases(cases) -> tuple[FinalCase, ...]`, and immutable paired
  benchmark/manifest/live-evidence artifacts.

- [ ] **Step 1: Write failing exact-pairing and provenance tests**

  Assert exactly 100 unique pair IDs; identical normalized SQL, expected columns,
  difficulty, categories, entity/schema annotations, and CQ IDs within each pair;
  exact profile `agent-authored` plus `single-human-reviewed`; and rejection of
  `human-review-01`, independent-review, agreement, or second-reviewer claims.

- [ ] **Step 2: Run paired test-set tests and observe failure**

  Run: `uv run pytest tests/unit/test_testset_paired.py -q`

  Expected: FAIL because paired workflow contracts do not exist.

- [ ] **Step 3: Implement draft/review/finalization contracts**

  Finalization requires 100 explicit user accept decisions, zero unresolved or
  rejected rows, valid hashes, and safe SQL. Derive unaccented text only after
  acceptance and preserve the accented parent ID/hash.

- [ ] **Step 4: Add live-evidence reuse and verification rules**

  Reuse English evidence only when SQL bytes, policy, and expected result contract
  match exactly; otherwise require bounded live verification. Bind accented and
  unaccented manifests to their parent benchmark hashes.

- [ ] **Step 5: Implement the offline-first CLI**

  Commands: `draft`, `validate-draft`, `apply-review`, `derive-unaccented`,
  `verify-live`, and `validate-final`. Only `verify-live` may initialize BigQuery.

- [ ] **Step 6: Run paired and existing T3.5 regression tests**

  Run: `uv run pytest tests/unit/test_testset_paired.py tests/unit/test_testset_reviewed_contracts.py tests/unit/test_testset_reviewed_validate.py tests/unit/test_testset_live.py -q`

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/nl2sparql/dataset/testset scripts/22_vietnamese_testset_workflow.py tests/unit/test_testset_paired.py tests/unit/test_testset_reviewed_contracts.py tests/unit/test_testset_reviewed_validate.py tests/unit/test_testset_live.py
  git commit -m "feat(testset): add paired Vietnamese review workflow"
  ```

### Task 5: Bilingual Catalog, Linkers, and Encoder Selection

**Files:**
- Create: `src/nl2sparql/linking/bilingual_aliases.json`
- Create: `src/nl2sparql/linking/encoder_selection.py`
- Create: `tests/unit/test_encoder_selection.py`
- Modify: `src/nl2sparql/linking/schema/documents.py`
- Modify: `src/nl2sparql/linking/schema/index.py`
- Modify: `src/nl2sparql/linking/entity/documents.py`
- Modify: `src/nl2sparql/linking/entity/index.py`
- Modify: `src/nl2sparql/linking/resolver/catalog.py`
- Modify: `tests/unit/test_schema_documents.py`
- Modify: `tests/unit/test_schema_index.py`
- Modify: `tests/unit/test_entity_documents.py`
- Modify: `tests/unit/test_entity_index.py`

**Interfaces:**
- Consumes: reviewed bilingual development ground truth only.
- Produces: language-tagged schema/entity documents,
  `evaluate_encoder_candidate(candidate, development_sets) -> EncoderScore`, and
  `select_encoder(candidates, *, english_regression_limit=0.02) -> EncoderSelection`.

- [ ] **Step 1: Write failing bilingual alias/document tests**

  Assert canonical identifiers remain English SQL identifiers; Vietnamese aliases
  are NFC-normalized, language-tagged, unique per target, hash-bound, and
  retrievable for accented/unaccented queries without overwriting original text.

- [ ] **Step 2: Run document/index tests and observe failure**

  Run: `uv run pytest tests/unit/test_schema_documents.py tests/unit/test_entity_documents.py tests/unit/test_schema_index.py tests/unit/test_entity_index.py -q`

  Expected: FAIL because bilingual aliases and identity fields are unsupported.

- [ ] **Step 3: Extend documents and cache identity**

  Include alias-catalog hash, normalization version, encoder ID, pinned revision,
  and corpus hash in cache identity. Reject stale caches even if matrix dimensions
  and record IDs happen to match.

- [ ] **Step 4: Write failing development-only selection tests**

  Test deterministic ranking by Vietnamese metric, then English metric, latency,
  model ID; reject any final benchmark path/hash; and reject candidates exceeding
  the 2-point English regression limit.

- [ ] **Step 5: Implement selection evidence and report serialization**

  Evidence includes candidate revisions, development hashes, per-language
  precision/recall/MRR, latency, selection rule, winner, and report hash.

- [ ] **Step 6: Run all linker tests**

  Run: `uv run pytest tests/unit/test_encoder_selection.py tests/unit/test_schema_*.py tests/unit/test_entity_*.py tests/unit/test_class_resolver_*.py -q`

  Expected: all tests pass, including English regression fixtures.

- [ ] **Step 7: Commit**

  ```bash
  git add src/nl2sparql/linking tests/unit/test_encoder_selection.py tests/unit/test_schema_*.py tests/unit/test_entity_*.py tests/unit/test_class_resolver_*.py
  git commit -m "feat(linking): add bilingual aliases and encoder selection"
  ```

### Task 6: Direct Bilingual B1/B2/B4/B5 Prompting and Retrieval

**Files:**
- Modify: `src/nl2sparql/models/b12/contracts.py`
- Modify: `src/nl2sparql/models/b12/prompts.py`
- Modify: `src/nl2sparql/models/b12/retrieval.py`
- Modify: `src/nl2sparql/models/b12/baseline.py`
- Modify: `src/nl2sparql/models/b45/baseline.py`
- Modify: `tests/unit/test_b12_prompts.py`
- Modify: `tests/unit/test_b12_retrieval.py`
- Modify: `tests/unit/test_b12_baseline.py`
- Modify: `tests/unit/test_b45_baseline.py`

**Interfaces:**
- Consumes: normalized raw question, bilingual catalog summary, accepted balanced
  bilingual snapshot, and pinned multilingual encoder.
- Produces: unchanged baseline public `predict(question: str)` interfaces plus
  prompt/retrieval evidence containing input-normalization, catalog, training,
  encoder, and selected-example hashes.

- [ ] **Step 1: Write failing bilingual prompt and escaping tests**

  Assert the shared system prompt explicitly accepts English/Vietnamese but emits
  GoogleSQL only; accented/decomposed/unaccented questions are escaped safely;
  addresses and symbols remain literal; and no translator or language detector is
  called by B1/B2/B4/B5.

- [ ] **Step 2: Run prompt/baseline tests and observe failure**

  Run: `uv run pytest tests/unit/test_b12_prompts.py tests/unit/test_b12_baseline.py tests/unit/test_b45_baseline.py -q`

  Expected: FAIL on the new bilingual prompt/evidence assertions.

- [ ] **Step 3: Extend prompt construction and provenance**

  Keep zero-shot/five-shot cardinality and SQL extraction unchanged. Make prompt
  hashes include the bilingual catalog and normalization version.

- [ ] **Step 4: Write failing semantic-family retrieval tests**

  Require exactly five deterministic examples, exclude target IDs and semantic
  families, support both language variants, reject test-set IDs/hashes, and bind
  cache metadata to the accepted bilingual training hash.

- [ ] **Step 5: Extend retrieval without changing public prediction signatures**

  Support the versioned bilingual snapshot while retaining compatibility with the
  existing English snapshot for English-only baselines.

- [ ] **Step 6: Run complete small/large baseline unit suites**

  Run: `uv run pytest tests/unit/test_b12_*.py tests/unit/test_b45_*.py -q`

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/nl2sparql/models/b12 src/nl2sparql/models/b45 tests/unit/test_b12_*.py tests/unit/test_b45_*.py
  git commit -m "feat(models): support direct bilingual NL2SQL prompts"
  ```

### Task 7: Translation-First Scientific Baseline

**Files:**
- Create: `src/nl2sparql/baselines/__init__.py`
- Create: `src/nl2sparql/baselines/translation.py`
- Create: `tests/unit/test_translation_baseline.py`
- Modify: `src/nl2sparql/evaluation/contracts.py`
- Modify: `src/nl2sparql/evaluation/artifacts.py`

**Interfaces:**
- Consumes: Vietnamese question, pinned `Translator` protocol implementation, and
  accepted English NL2SQL predictor.
- Produces: `TranslationEvidence` and
  `TranslationFirstBaseline.predict_detailed(question, *, request_id) -> TranslationPrediction`.

- [ ] **Step 1: Write failing translation evidence tests**

  Pin translator/model revision, request ID, original/translated text hashes,
  translation latency, downstream latency, total latency, status, cost/privacy,
  and configuration hash. Test that a missing/failed translation produces a
  denominator failure and never calls downstream inference.

- [ ] **Step 2: Run the focused test and observe failure**

  Run: `uv run pytest tests/unit/test_translation_baseline.py -q`

  Expected: FAIL because the baseline and evidence types do not exist.

- [ ] **Step 3: Implement the isolated composition wrapper**

  Do not import it from the direct production baselines. Validate translated text
  with the same input contract and retain intermediate text as hash-bound evidence.

- [ ] **Step 4: Add artifact round-trip and no-network offline tests**

  Assert canonical serialization round-trips, tampering is rejected, and artifact
  validation never constructs a translator or model backend.

- [ ] **Step 5: Run focused and canonical artifact tests**

  Run: `uv run pytest tests/unit/test_translation_baseline.py tests/unit/test_evaluation_contracts.py tests/unit/test_evaluation_artifacts.py -q`

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/nl2sparql/baselines src/nl2sparql/evaluation/contracts.py src/nl2sparql/evaluation/artifacts.py tests/unit/test_translation_baseline.py tests/unit/test_evaluation_contracts.py tests/unit/test_evaluation_artifacts.py
  git commit -m "feat(baselines): add translation-first comparison path"
  ```

### Task 8: Paired Bilingual Metrics and Pre-registered Gates

**Files:**
- Create: `src/nl2sparql/evaluation/bilingual.py`
- Create: `tests/unit/test_evaluation_bilingual.py`
- Modify: `src/nl2sparql/evaluation/contracts.py`
- Modify: `src/nl2sparql/evaluation/metrics.py`
- Modify: `src/nl2sparql/evaluation/reporting.py`
- Modify: `src/nl2sparql/evaluation/artifacts.py`

**Interfaces:**
- Consumes: compatible English, accented Vietnamese, unaccented Vietnamese, and
  translation-baseline canonical reports sharing exactly 100 pair IDs.
- Produces: `BilingualEvaluationReport`,
  `compare_language_pairs(...) -> BilingualEvaluationReport`, and
  `evaluate_bilingual_gates(report, policy) -> GateDecision`.

- [ ] **Step 1: Write failing paired metric tests**

  Assert `language_gap = en - vi`, `accent_gap = vi - vi_unaccented`, deterministic
  paired-bootstrap intervals, McNemar discordant counts/exact p-value, complete
  failure-mode counts, and latency that includes translation for the baseline.

- [ ] **Step 2: Run metric tests and observe failure**

  Run: `uv run pytest tests/unit/test_evaluation_bilingual.py -q`

  Expected: FAIL because bilingual report types/functions do not exist.

- [ ] **Step 3: Implement paired statistics and strict compatibility checks**

  Reject reordered, duplicate, missing, or mismatched pair IDs and incompatible
  gold SQL/test hashes. Count missing outputs/executions as zero-success cases.

- [ ] **Step 4: Write failing acceptance-gate tests**

  Pin inclusive thresholds: English regression `<= 0.02`, language gap `<= 0.10`,
  accent gap `<= 0.10`, review/live count exactly 100, all intervals present, and
  no missing failure counts. Assert boundary values pass and values one unit above
  the representable tolerance fail.

- [ ] **Step 5: Implement gate decisions and canonical serialization**

  Store every observed value, threshold, pass/fail result, frozen input hash, and
  overall result. Never mutate or filter reports based on the decision.

- [ ] **Step 6: Run all evaluation tests**

  Run: `uv run pytest tests/unit/test_evaluation_*.py -q`

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/nl2sparql/evaluation tests/unit/test_evaluation_*.py
  git commit -m "feat(evaluation): add paired bilingual metrics and gates"
  ```

### Task 9: Offline-first Workflow CLIs and Integration Tests

**Files:**
- Create: `scripts/20_generate_vietnamese_training.py`
- Create: `scripts/21_build_bilingual_snapshot.py`
- Create: `scripts/23_select_multilingual_encoder.py`
- Create: `scripts/24_bilingual_evaluation.py`
- Create: `tests/unit/test_bilingual_workflows.py`

**Interfaces:**
- Consumes: interfaces from Tasks 1–8.
- Produces: validate/generate/finalize commands with JSON summaries and non-zero
  exits on contract, hash, quota, leakage, or acceptance failures.

- [ ] **Step 1: Write failing CLI isolation tests**

  Assert every CLI offers `validate-only`; offline validation does not initialize
  Gemini, BigQuery, translators, sentence-transformers, or inference backends;
  secret values never appear in stdout/stderr/manifests; and output paths cannot
  alias protected inputs or temporary checkpoints.

- [ ] **Step 2: Run workflow tests and observe failure**

  Run: `uv run pytest tests/unit/test_bilingual_workflows.py -q`

  Expected: FAIL because the entry points do not exist.

- [ ] **Step 3: Implement thin CLI composition**

  `20` generates/resumes Vietnamese records with explicit concurrency and zero
  cost cap; `21` validates/builds the balanced snapshot; `23` evaluates/freezes
  encoder selection; `24` validates/builds bilingual reports and gates.

- [ ] **Step 4: Add synthetic end-to-end fixture tests**

  Exercise a tiny English/Vietnamese family through normalization, assembly,
  retrieval, canonical predictions, paired evaluation, and gate serialization.
  Mark all fixture output as synthetic/non-genuine.

- [ ] **Step 5: Run workflow and full offline tests**

  Run: `uv run pytest tests/unit/test_bilingual_workflows.py -q && uv run pytest -q`

  Expected: workflow tests and the full suite pass.

- [ ] **Step 6: Run repository formatting/lint gates**

  Run: `uv run ruff format --check . && uv run ruff check . && git diff --check`

  Expected: all commands exit 0.

- [ ] **Step 7: Commit**

  ```bash
  git add scripts/20_generate_vietnamese_training.py scripts/21_build_bilingual_snapshot.py scripts/23_select_multilingual_encoder.py scripts/24_bilingual_evaluation.py tests/unit/test_bilingual_workflows.py
  git commit -m "feat(workflows): add bilingual dataset and evaluation CLIs"
  ```

### Task 10: Produce, Review, Freeze, and Report Genuine Evidence

**Files:**
- Create when validated: `data/dataset/raw/vietnamese-training.jsonl`
- Create when validated: `data/dataset/raw/vietnamese-training-manifest.json`
- Create when validated: `data/dataset/processed/bilingual-training.jsonl`
- Create when validated: `data/dataset/processed/bilingual-training-manifest.json`
- Create for review: `data/review_drafts/t3_5_vi_candidate_set_<date>/...`
- Create after review: `data/dataset/test/test-100-vi.jsonl`
- Create after review: `data/dataset/test/test-100-vi-unaccented.jsonl`
- Create after review: paired manifests and live evidence beside those files
- Create: `data/eval/bilingual/<run-id>/...`
- Modify: `docs/planning/prioritized-backlog-2026-09-21.md`
- Modify: relevant `docs/tasks/phase-3-dataset/*.md`
- Modify: relevant `docs/tasks/phase-4-linking/*.md`
- Modify: relevant `docs/tasks/phase-5-baselines/*.md`
- Modify: `docs/memory/01-ARCHITECTURE.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

**Interfaces:**
- Consumes: accepted T3.3/T3.4 English artifacts, Tasks 1–9, confirmed external
  credentials/quota, and the user's 100 review decisions.
- Produces: genuine hash-bound training, benchmark, run, report, audit, and thesis
  evidence; no source interface is introduced here.

- [ ] **Step 1: Run all offline preflights and record resource estimates**

  Report disk space, expected artifact size, API calls, duration, quota/resume
  risk, exact models/providers, privacy, and cost caps before any network call.
  Load `.env` only inside subprocesses and never print it.

- [ ] **Step 2: Generate and validate Vietnamese training evidence**

  Run `scripts/20_generate_vietnamese_training.py` at conservative concurrency.
  Monitor checkpoints; on 429 preserve state and resume only within Free Tier.
  Require complete records, unique normalized variants, immutable anchors/SQL,
  correct Gemini provenance, valid hashes, no duplicate requests, and USD `0.00`.

- [ ] **Step 3: Build and freeze the balanced bilingual snapshot**

  This step is blocked until accepted English Stage D exists. Validate family
  isolation, exclusion hashes, exact balance, manifest, and output digest before
  allowing retrieval/index construction.

- [ ] **Step 4: Select and freeze the multilingual encoder on development data**

  Publish the complete candidate table, English regression evidence, chosen model
  and revision, latency, development hashes, and selection-report digest. Do not
  read either final benchmark during selection.

- [ ] **Step 5: Author exactly 100 paired Vietnamese candidates**

  Derive wording from gold SQL and semantic annotations, not English surface text.
  Validate exact pairing/safety and publish a review guide plus empty decision
  sheet under `data/review_drafts/`; label authorship honestly as agent-authored.

- [ ] **Step 6: Pause for the user's review of all 100 cases**

  Do not synthesize decisions or finalize early. Apply requested revisions,
  preserve review events, and require 100 explicit accept decisions from the one
  human reviewer.

- [ ] **Step 7: Finalize accented/unaccented benchmarks and live evidence**

  Derive unaccented text from accepted Vietnamese; review flagged ambiguities;
  validate 100/100 pairs, manifests, SQL safety, reusable or fresh bounded live
  evidence, hashes, and no training/cache overlap.

- [ ] **Step 8: Freeze systems and run primary bilingual evaluation once**

  Run English-only, direct bilingual, and translation-first configurations on the
  declared paired slices. Store every prediction/execution, missing case, latency,
  failure class, cost/privacy record, fingerprint, and journal hash.

- [ ] **Step 9: Evaluate gates and document results without post-test tuning**

  Publish paired confidence intervals, McNemar analysis where valid, English
  regression, language/accent gaps, linking metrics, latency, failures, and each
  pre-registered pass/fail outcome. If a gate fails, report it as failed.

- [ ] **Step 10: Run final repository and evidence verification**

  Run: `uv run pytest -q && uv run ruff format --check . && uv run ruff check . && git diff --check`

  Also run every new CLI in `validate-only`/`validate-final` mode, repository
  secret scanning, notebook JSON validation if notebooks changed, manifest/hash
  verification, and an explicit benchmark-to-training/cache leakage audit.

- [ ] **Step 11: Update task, backlog, architecture, decision, and thesis evidence**

  Record genuine counts/hashes/models/revisions/costs/gates/limitations. State
  agent authorship and single-human review; never claim `human-review-01` or
  independent review.

- [ ] **Step 12: Commit evidence and documentation allowed by repository policy**

  Do not add `.env`, credentials, temporary checkpoints, provider response dumps,
  ignored caches, or policy-excluded artifacts.

  ```bash
  git add <only policy-allowed validated artifacts and documentation>
  git commit -m "docs(evidence): record bilingual NL2SQL evaluation"
  ```

### Task 11: Whole-branch Review and PR Handoff

**Files:**
- Review all changes since commit `41494bf`.
- Modify only files required by verified review findings.

**Interfaces:**
- Consumes: completed Tasks 1–10 and their fresh verification evidence.
- Produces: reviewed branch ready for a PR; no merge authorization.

- [ ] **Step 1: Run a standards and spec review against the approved design**

  Check every acceptance criterion, leakage boundary, Free Tier/cost statement,
  provenance claim, public interface, and repository convention. Record concrete
  findings by severity and file/line.

- [ ] **Step 2: Fix verified findings test-first**

  For each code defect, add or tighten a failing regression test, observe failure,
  make the smallest fix, and rerun the focused suite. Do not change frozen
  scientific evidence to improve a metric.

- [ ] **Step 3: Re-run final verification from a clean status**

  Run: `uv run pytest -q && uv run ruff format --check . && uv run ruff check . && git diff --check`

  Revalidate every published manifest/hash and confirm `git status --ignored`
  contains no staged secret, `.env`, checkpoint, or excluded artifact.

- [ ] **Step 4: Commit review fixes and open a PR**

  Push the feature branch and create a PR summarizing implementation, genuine
  evidence, gate results, limitations, tests, and artifact policy. Do not merge
  without an explicit user request.
