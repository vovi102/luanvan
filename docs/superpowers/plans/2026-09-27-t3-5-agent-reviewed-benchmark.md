# T3.5 Agent-Authored, Human-Reviewed Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the active T3.5 provenance path and publish a validated 120-case NL–GoogleSQL candidate pack that is ready for explicit user review without fabricating review or BigQuery evidence.

**Architecture:** Add a parallel `agent_authored_human_reviewed_v1` profile behind focused contract, validation, and artifact modules while leaving `three_pool_v1` behavior intact. Reuse the existing SQL safety and guarded BigQuery executor, then teach downstream test-set consumers to distinguish the two exact final schemas. Execution of this plan ends at `draft_ready`; genuine T3.5 finalization remains gated by the user's review and a separately authorized live BigQuery run.

**Tech Stack:** Python 3.11, dataclasses, CSV/JSON/JSONL, Click, SQLGlot, google-cloud-bigquery, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-27-t3-5-agent-reviewed-benchmark-design.md`

**Implementation status (2026-09-28):** Tasks 1–7 are committed and Task 8
published the hash-bound `draft_ready` evidence. The implementation deliberately
stops before human review, live BigQuery verification, and final publication;
those external gates remain listed in the handoff below.

## Global Constraints

- The active provenance profile is exactly `agent_authored_human_reviewed_v1`; `three_pool_v1` behavior and tests remain intact.
- Draft output contains exactly 120 stable IDs `t35-001` through `t35-120` with proposed difficulty counts `easy=36`, `medium=60`, `hard=24`.
- Final selection requires exactly 100 accepted IDs with `easy=30`, `medium=50`, `hard=20`, at least six categories, and all three entity kinds.
- The final artifact must say agent-authored and single-human-reviewed and must never claim independent authorship, inter-rater agreement, or Cohen's kappa.
- Test-set questions and variants are forbidden from training, prompt tuning, retrieval tuning, linker tuning, and hyperparameter tuning.
- Offline help, candidate validation, review validation, selection validation, and tests must not initialize credentials, a BigQuery client, or network access.
- Live verification requires `--allow-bigquery`, a project, and the fixed safety ceilings of 20 GiB per query and 64 GiB aggregate with query cache disabled.
- Final publication is atomic and immutable and requires current ready live evidence for all 100 selected cases.
- Generated candidate source is never edited by review commands; review events and final selection are separate human-owned inputs.
- No external review, BigQuery execution, or final scientific-readiness claim is performed as part of this implementation plan.

## Review Focus

- Mixed or missing provenance profiles must fail instead of falling back to three-pool semantics; Task 1 adds exact profile-confusion tests.
- A `REVISE` event followed by a high-scoring `ACCEPT` must bind the revised content, while skipped/duplicate rounds must fail; Task 3 adds state-machine tests.
- Leakage files use heterogeneous `nl` and `question` fields and may contain objects without either; Task 2 tests deterministic extraction and fail-closed decoding without treating unrelated objects as questions.
- Final JSONL and its manifest must avoid circular hashes while detecting any stale candidate, review, selection, catalog, or live-evidence digest; Task 4 adds tamper tests for every edge.
- Legacy B0/B1/B2/B4/B5 loaders must accept the new exact profile only when its provenance fields are complete and must reject mixed-profile snapshots; Task 6 adds end-to-end consumer tests.

---

### Task 1: Agent-reviewed contracts and strict codecs

**Files:**
- Create: `src/nl2sparql/dataset/testset/reviewed_contracts.py`
- Modify: `src/nl2sparql/dataset/testset/__init__.py`
- Test: `tests/unit/test_testset_reviewed_contracts.py`

**Interfaces:**
- Consumes: `_text`, `_identifier`, `_normalized_labels`, `_normalized_annotations`, `SelectionRecord`, and `TestSetError` from `contracts.py` without changing their historical behavior.
- Produces: `AGENT_REVIEWED_PROFILE`, `CandidateRecord`, `ReviewEvent`, `AcceptedCandidate`, `ReviewedTestSetPaths`, `load_candidates(path)`, `load_review_events(path)`, and `load_reviewed_selections(path)`.

- [ ] **Step 1: Write failing codec tests**

  Add tests named `test_candidate_record_requires_exact_agent_profile_and_fields`, `test_load_candidates_rejects_duplicate_json_keys_and_blank_lines`, `test_review_event_requires_valid_round_scores_and_revision_shape`, `test_reviewed_paths_separate_draft_and_final_roots`, and `test_profile_confusion_never_falls_back_to_three_pool`. Assert strict `schema_version="1.0.0"`, exact profile, `author_type="agent"`, pseudonymous reviewer IDs, explicit booleans, non-empty ordered output columns, and exact CSV headers.

- [ ] **Step 2: Run the contract tests and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_contracts.py`

  Expected: collection fails because `reviewed_contracts` does not exist.

- [ ] **Step 3: Implement immutable reviewed contracts**

  Define these exact public shapes:

  ```python
  AGENT_REVIEWED_PROFILE = "agent_authored_human_reviewed_v1"

  @dataclass(frozen=True)
  class CandidateRecord: ...

  @dataclass(frozen=True)
  class ReviewEvent: ...

  @dataclass(frozen=True)
  class AcceptedCandidate: ...

  @dataclass(frozen=True)
  class ReviewedTestSetPaths:
      @classmethod
      def from_roots(cls, draft_root: Path, final_root: Path) -> ReviewedTestSetPaths: ...

  def load_candidates(path: Path) -> tuple[CandidateRecord, ...]: ...
  def load_review_events(path: Path) -> tuple[ReviewEvent, ...]: ...
  def load_reviewed_selections(path: Path) -> tuple[SelectionRecord, ...]: ...
  ```

  `CandidateRecord` uses every field listed in the spec. `ReviewEvent` uses the append-only header including `review_round`, and permits blank revision fields only where the decision rules allow them. Parse JSON with duplicate-key detection and CSV with exact ordered headers.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_contracts.py tests/unit/test_testset_contracts.py`

  Expected: all tests pass; importing the modules does not import or initialize Google credentials.

- [ ] **Step 5: Commit the contract seam**

  ```bash
  git add src/nl2sparql/dataset/testset/reviewed_contracts.py \
    src/nl2sparql/dataset/testset/__init__.py \
    tests/unit/test_testset_reviewed_contracts.py
  git commit -m "feat(dataset): define agent-reviewed benchmark contracts"
  ```

### Task 2: Candidate quality, catalog, and leakage validation

**Files:**
- Create: `src/nl2sparql/dataset/testset/reviewed_validate.py`
- Test: `tests/unit/test_testset_reviewed_validate.py`
- Test fixture: `tests/fixtures/testset_reviewed/`

**Interfaces:**
- Consumes: `CandidateRecord`, `AGENT_REVIEWED_PROFILE`, `validate_sql_text`, and the canonical catalog at `src/nl2sparql/sql/catalog/ethereum_analytics.json`.
- Produces: `LeakageSource`, `CandidatePackReport`, `canonical_leakage_paths(repo_root)`, and `validate_candidate_pack(candidate_path, *, repo_root, catalog_path) -> CandidatePackReport`.

- [ ] **Step 1: Write failing candidate-validation tests**

  Cover exact count and ID sequence, duplicate normalized NL, 36/60/24 quotas, invalid SQL, output alias mismatch, unknown schema/CQ annotation, fewer than six categories, missing entity kinds, catalog hash mismatch, source commit format, and exact/normalized overlap with Stage A or T4 text. Add the Review Focus case: leakage JSON/JSONL/CSV rows may expose `nl` or `question`; valid unrelated objects are ignored, while malformed UTF-8/JSON/CSV fails with the path in the error.

- [ ] **Step 2: Run candidate-validation tests and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_validate.py`

  Expected: collection fails because `reviewed_validate` does not exist.

- [ ] **Step 3: Implement deterministic leakage discovery**

  ```python
  @dataclass(frozen=True)
  class LeakageSource:
      path: Path
      sha256: str
      question_count: int

  def canonical_leakage_paths(repo_root: Path) -> tuple[Path, ...]: ...
  ```

  Discover existing text-bearing `.json`, `.jsonl`, and `.csv` files below `data/dataset`, `data/eval`, and `data/review_drafts/t4_candidate_set_2026-09-24`, excluding the T3.5 draft and final roots. Sort resolved repository-relative paths and record every digest.

- [ ] **Step 4: Implement pack validation**

  ```python
  @dataclass(frozen=True)
  class CandidatePackReport:
      status: str
      provenance_profile: str
      candidate_count: int
      difficulty_counts: tuple[tuple[str, int], ...]
      category_count: int
      entity_kind_count: int
      candidate_sha256: str
      catalog_sha256: str
      leakage_sources: tuple[LeakageSource, ...]
      source_commit: str

  def validate_candidate_pack(
      candidate_path: Path,
      *,
      repo_root: Path,
      catalog_path: Path,
  ) -> CandidatePackReport: ...
  ```

  Reuse `validate_sql_text`, use SQLGlot BigQuery AST projections to compare explicit output aliases to `expected_columns`, load the catalog's relation/field/CQ IDs, normalize question text with NFKC plus whitespace collapse, and return stable counts and input hashes.

- [ ] **Step 5: Run candidate-validation tests and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_validate.py tests/unit/test_testset_live.py`

  Expected: all tests pass with no cloud client calls.

- [ ] **Step 6: Commit candidate validation**

  ```bash
  git add src/nl2sparql/dataset/testset/reviewed_validate.py \
    tests/unit/test_testset_reviewed_validate.py tests/fixtures/testset_reviewed
  git commit -m "feat(dataset): validate T3.5 candidate quality and leakage"
  ```

### Task 3: Human review state and explicit final selection

**Files:**
- Modify: `src/nl2sparql/dataset/testset/reviewed_validate.py`
- Test: `tests/unit/test_testset_reviewed_review.py`

**Interfaces:**
- Consumes: reviewed contracts and `validate_candidate_pack` from Tasks 1–2.
- Produces: `ReviewedBundle`, `ReviewBundleReport`, `load_reviewed_bundle(paths)`, `resolve_review_state(bundle, *, repo_root, catalog_path)`, and `validate_reviewed_selection(bundle, *, repo_root, catalog_path) -> ReviewBundleReport`.

- [ ] **Step 1: Write failing review-state tests**

  Add tests for missing decisions, multiple reviewer IDs, non-contiguous or duplicate rounds, `ACCEPT` below score 4, `ACCEPT` carrying revision text, `REVISE` without changes, `REJECT` in selection, revisions that introduce unsafe SQL or leakage, and exact final quotas/coverage. Pin the Review Focus transition with `REVISE` round 1 followed by `ACCEPT` round 2 and assert that `AcceptedCandidate.nl`, `.sql`, and `.accepted_content_sha256` bind the revised content.

- [ ] **Step 2: Run review-state tests and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_review.py`

  Expected: imports or calls fail because the review bundle/state functions are absent.

- [ ] **Step 3: Implement the append-only state machine**

  ```python
  @dataclass(frozen=True)
  class ReviewedBundle:
      candidates: tuple[CandidateRecord, ...]
      events: tuple[ReviewEvent, ...]
      selections: tuple[SelectionRecord, ...]

  def load_reviewed_bundle(paths: ReviewedTestSetPaths) -> ReviewedBundle: ...
  def resolve_review_state(
      bundle: ReviewedBundle,
      *,
      repo_root: Path,
      catalog_path: Path,
  ) -> tuple[AcceptedCandidate, ...]: ...
  ```

  Apply events per candidate in ascending contiguous `review_round`. A revision mutates only the in-memory reviewed content, re-runs SQL and leakage validation, and remains pending until a later explicit acceptance.

- [ ] **Step 4: Implement final-selection validation**

  ```python
  @dataclass(frozen=True)
  class ReviewBundleReport:
      status: str
      provenance_profile: str
      candidate_count: int
      reviewed_count: int
      accepted_count: int
      revised_count: int
      rejected_count: int
      reviewer_id: str
      selected_count: int
      difficulty_counts: tuple[tuple[str, int], ...]
      accepted_content_sha256: str
      review_sha256: str
      selection_sha256: str

  def validate_reviewed_selection(
      bundle: ReviewedBundle,
      *,
      repo_root: Path,
      catalog_path: Path,
  ) -> ReviewBundleReport: ...
  ```

  Require exactly 100 accepted selected IDs, 30/50/20 final difficulty, six categories, all three entity kinds, catalog-valid annotations, and selection hashes bound to post-review content. Do not auto-select from scores.

- [ ] **Step 5: Run review-state tests and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_review.py tests/unit/test_testset_reviewed_validate.py`

  Expected: all tests pass.

- [ ] **Step 6: Commit human review semantics**

  ```bash
  git add src/nl2sparql/dataset/testset/reviewed_validate.py \
    tests/unit/test_testset_reviewed_review.py
  git commit -m "feat(dataset): enforce explicit T3.5 human review"
  ```

### Task 4: Hash-bound reviewed artifacts and finalization

**Files:**
- Create: `src/nl2sparql/dataset/testset/reviewed_artifacts.py`
- Test: `tests/unit/test_testset_reviewed_artifacts.py`

**Interfaces:**
- Consumes: `ReviewedBundle`, `ReviewBundleReport`, `resolve_review_state`, `validate_reviewed_selection`, existing `FinalCase`, `LiveEvidence`, `verify_sql`, and atomic/report helpers from `artifacts.py`.
- Produces: `ReviewedLiveEvidence`, `ReviewedFinalizationReport`, `write_review_scaffold`, `build_live_cases`, `write_reviewed_live_evidence`, `read_reviewed_live_evidence`, and `finalize_reviewed_bundle`.

- [ ] **Step 1: Write failing artifact tests**

  Test non-overwriting scaffold creation, profile-bound live evidence, exact selected IDs, stale SQL/live/catalog/review/selection digests, partial evidence, duplicate live IDs, atomic immutable publication, exact limitations array, and final rows retaining legacy SQL-native fields plus the new provenance fields. Pin the Review Focus rule: compute `provenance_bundle_sha256` only from ordered candidate/content/selection/live/catalog digests; manifest records final JSONL SHA and the same bundle hash; rows contain no manifest hash.

- [ ] **Step 2: Run artifact tests and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_artifacts.py`

  Expected: collection fails because `reviewed_artifacts` does not exist.

- [ ] **Step 3: Implement scaffold and live-case conversion**

  ```python
  def write_review_scaffold(paths: ReviewedTestSetPaths, *, force: bool = False) -> tuple[Path, ...]: ...
  def build_live_cases(
      bundle: ReviewedBundle,
      accepted: tuple[AcceptedCandidate, ...],
  ) -> tuple[FinalCase, ...]: ...
  ```

  The scaffold writes only `review_events.csv`, `final_selection.csv`, and `REVIEW_GUIDE.md`; it never creates decisions. Live cases use `source="agent"`, `pool_b_writer="agent"`, and exactly one accepted pseudonymous reviewer.

- [ ] **Step 4: Implement evidence envelope and immutable finalizer**

  ```python
  @dataclass(frozen=True)
  class ReviewedLiveEvidence:
      provenance_profile: str
      reviewed_bundle_sha256: str
      execution: LiveEvidence

  @dataclass(frozen=True)
  class ReviewedFinalizationReport:
      status: str
      record_count: int
      output_sha256: str
      manifest_sha256: str
      provenance_bundle_sha256: str

  def write_reviewed_live_evidence(evidence: ReviewedLiveEvidence, path: Path) -> None: ...
  def read_reviewed_live_evidence(path: Path) -> ReviewedLiveEvidence: ...
  def finalize_reviewed_bundle(
      bundle: ReviewedBundle,
      evidence: ReviewedLiveEvidence,
      *,
      output_path: Path,
      manifest_path: Path,
      repo_root: Path,
      catalog_path: Path,
  ) -> ReviewedFinalizationReport: ...
  ```

  Final rows preserve the historical fields expected by baseline consumers and add `provenance_profile`, `review_provenance`, `candidate_sha256`, `accepted_content_sha256`, `selection_sha256`, `live_evidence_sha256`, `catalog_sha256`, and `provenance_bundle_sha256`. Refuse byte-different overwrite of either final file.

- [ ] **Step 5: Run artifact tests and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_artifacts.py tests/unit/test_testset_artifacts.py tests/unit/test_testset_live.py`

  Expected: all tests pass and historical finalization output remains unchanged.

- [ ] **Step 6: Commit reviewed artifact publication**

  ```bash
  git add src/nl2sparql/dataset/testset/reviewed_artifacts.py \
    tests/unit/test_testset_reviewed_artifacts.py
  git commit -m "feat(dataset): publish hash-bound reviewed benchmarks"
  ```

### Task 5: Offline-first CLI and guarded live path

**Files:**
- Modify: `scripts/test_set_workflow.py`
- Modify: `scripts/12_test_set_workflow.py`
- Test: `tests/unit/test_testset_reviewed_cli.py`

**Interfaces:**
- Consumes: all reviewed profile functions from Tasks 1–4 and the existing injected `verify_sql` adapter.
- Produces: a `reviewed` Click subgroup with `scaffold`, `validate-candidates`, `validate-review`, `verify-live`, and `finalize` commands; existing top-level three-pool commands remain compatible.

- [ ] **Step 1: Write failing CLI tests**

  Assert help lists the reviewed subgroup; `scaffold` creates headers only; `validate-candidates` can reach `draft_ready`; `validate-review` returns structured blocked status on empty decisions; and `finalize` fails without evidence. Patch both credential discovery and `bigquery.Client` to raise if any offline command touches them. Assert `verify-live` refuses to create a client without `--allow-bigquery`, `--project`, and a review-ready bundle.

- [ ] **Step 2: Run CLI tests and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_cli.py`

  Expected: the `reviewed` command group is absent.

- [ ] **Step 3: Implement reviewed offline commands**

  Add explicit `--draft-root` and `--final-root` options. `validate-candidates` writes a canonical validation report and candidate manifest containing profile, candidate/catalog/leakage digests, source commit, limitations, and `draft_ready`; `--check-only` performs the same validation without writing either file. `validate-review` never mutates candidate source.

- [ ] **Step 4: Implement reviewed live and finalize commands**

  `reviewed verify-live` requires `--allow-bigquery`, `--project`, uses location `US`, and instantiates the client only after candidate/review/selection validation passes. Use `SqlPolicy(per_query_bytes=20 * 2**30, total_bytes=64 * 2**30, location="US")`. Persist failures as `blocked` for credential/API availability and `failed` for deterministic validation/policy errors.

- [ ] **Step 5: Run CLI tests and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_testset_reviewed_cli.py tests/unit/test_testset_artifacts.py tests/unit/test_testset_live.py`

  Expected: all tests pass; offline credential/client sentinels remain untouched.

- [ ] **Step 6: Commit CLI orchestration**

  ```bash
  git add scripts/test_set_workflow.py scripts/12_test_set_workflow.py \
    tests/unit/test_testset_reviewed_cli.py
  git commit -m "feat(dataset): orchestrate reviewed T3.5 workflow"
  ```

### Task 6: Downstream baseline and evaluation compatibility

**Files:**
- Modify: `src/nl2sparql/models/b0/evaluate.py`
- Modify: `src/nl2sparql/evaluation/adapters/common.py`
- Test: `tests/unit/test_b0_evaluate.py`
- Test: `tests/unit/test_evaluation_b0_adapter.py`
- Test: `tests/unit/test_evaluation_b12_adapter.py`
- Test: `tests/unit/test_evaluation_b45_adapter.py`
- Test: `tests/unit/test_b12_workflow.py`
- Test: `tests/unit/test_b45_workflow.py`

**Interfaces:**
- Consumes: finalized row schemas for historical three-pool and `agent_authored_human_reviewed_v1` profiles.
- Produces: `load_b0_cases` and `load_authoritative_test_set` that accept either exact homogeneous schema and preserve trusted/reviewed/live flags without inflating provenance claims; `AuthoritativeCaseSet.provenance_profile: str` exposes the selected profile downstream.

- [ ] **Step 1: Write failing consumer tests**

  Add one valid 100-row agent-reviewed fixture builder and cases for missing profile fields, wrong `source`, wrong `pool_b_writer`, zero/multiple reviewers, wrong review provenance, malformed digests, and a snapshot mixing legacy and reviewed rows. Assert the reviewed profile is trusted only when live evidence fields are valid, while legacy three-pool identity-disjoint checks remain unchanged. Add workflow cases proving the reviewed final snapshot cannot be the same file, symlink, or hard link as training input for B2/B5.

- [ ] **Step 2: Run consumer tests and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_b0_evaluate.py tests/unit/test_evaluation_b0_adapter.py tests/unit/test_evaluation_b12_adapter.py tests/unit/test_evaluation_b45_adapter.py tests/unit/test_b12_workflow.py tests/unit/test_b45_workflow.py`

  Expected: new rows fail the legacy exact-field check.

- [ ] **Step 3: Implement exact schema dispatch**

  Dispatch the whole snapshot by row field set and `provenance_profile`; reject mixed snapshots. For reviewed rows require `source == pool_b_writer == "agent"`, one non-empty pseudonymous reviewer, `review_provenance == "single_human_reviewer"`, all seven lower-case SHA-256 fields, and valid live execution evidence. Do not run three-pool role-disjoint checks on this explicitly different profile.

- [ ] **Step 4: Preserve truthful downstream flags**

  Extend `AuthoritativeCaseSet` with required `provenance_profile: str`; legacy rows yield `three_pool_v1` and reviewed rows yield `agent_authored_human_reviewed_v1`. `reviewed=True` means a recorded human review exists, not independent review. Keep `synthetic=False` and `live_verified=True` behavior hash-bound and unchanged for baseline readiness calculations.

- [ ] **Step 5: Run consumer tests and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_b0_evaluate.py tests/unit/test_evaluation_*adapter.py tests/unit/test_b12_evaluate.py tests/unit/test_b45_evaluate.py tests/unit/test_b12_workflow.py tests/unit/test_b45_workflow.py`

  Expected: both provenance profiles pass their own valid fixtures and reject cross-profile confusion.

- [ ] **Step 6: Commit consumer compatibility**

  ```bash
  git add src/nl2sparql/models/b0/evaluate.py \
    src/nl2sparql/evaluation/adapters/common.py \
    tests/unit/test_b0_evaluate.py tests/unit/test_evaluation_b0_adapter.py \
    tests/unit/test_evaluation_b12_adapter.py tests/unit/test_evaluation_b45_adapter.py \
    tests/unit/test_b12_workflow.py tests/unit/test_b45_workflow.py
  git commit -m "feat(evaluation): accept reviewed T3.5 provenance"
  ```

### Task 7: Author and validate the 120-candidate pack

**Files:**
- Create: `data/review_drafts/t3_5_candidate_set_2026-09-27/candidates.jsonl`
- Create: `data/review_drafts/t3_5_candidate_set_2026-09-27/review_events.csv`
- Create: `data/review_drafts/t3_5_candidate_set_2026-09-27/final_selection.csv`
- Create: `data/review_drafts/t3_5_candidate_set_2026-09-27/REVIEW_GUIDE.md`
- Test: `tests/unit/test_t35_candidate_pack.py`

**Interfaces:**
- Consumes: canonical SQL catalog/dictionary, candidate validator, and review scaffold from Tasks 1–5.
- Produces: a checked-in `draft_ready` source pack; review and selection files contain headers only and make no human-evidence claim.

- [ ] **Step 1: Write the failing repository-artifact test**

  `test_repository_t35_candidate_pack_is_draft_ready` loads the canonical draft path, asserts IDs `t35-001..t35-120`, exact 36/60/24 quotas, full catalog/SQL/leakage validation, empty review/selection bodies, and the absence of finalized `data/dataset/test/test-100.jsonl`.

- [ ] **Step 2: Run the artifact test and verify RED**

  Run: `.venv/bin/pytest -q tests/unit/test_t35_candidate_pack.py`

  Expected: FAIL because the candidate pack does not exist.

- [ ] **Step 3: Create review-owned scaffold files**

  Run the reviewed scaffold command for the canonical draft root. Confirm it creates only CSV headers and the guide and labels Codex as author, the user as reviewer, and live verification as pending.

- [ ] **Step 4: Author 36 easy candidates**

  Add distinct single-relation filters, lookups, counts, and bounded time-range questions using stable IDs. Every query must use only managed relations/functions, explicit aliases, the catalog's June 2026 window, and a non-empty-policy judgment that the user can review.

- [ ] **Step 5: Author 60 medium candidates**

  Add grouped aggregations, comparisons, top-k, entity/concept filters, token metadata, and two-relation questions with diverse wording and explicit output order.

- [ ] **Step 6: Author 24 hard candidates**

  Add multi-relation CTEs, temporal comparisons, nested aggregation, conditional metrics, and class-level analysis without mutation, wildcard projection, unsupported tables, or unbounded date scans.

- [ ] **Step 7: Run offline artifact validation and verify GREEN**

  Run: `.venv/bin/pytest -q tests/unit/test_t35_candidate_pack.py`

  Run: `.venv/bin/python scripts/12_test_set_workflow.py reviewed validate-candidates --check-only --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27`

  Expected: test passes and CLI reports `draft_ready`; no credentials or network are accessed.

- [ ] **Step 8: Commit candidate source and review handoff**

  ```bash
  git add data/review_drafts/t3_5_candidate_set_2026-09-27 \
    tests/unit/test_t35_candidate_pack.py
  git commit -m "data(dataset): add T3.5 candidate review pack"
  ```

### Task 8: Publish draft evidence, migrate docs, and verify the branch

**Files:**
- Create: `data/review_drafts/t3_5_candidate_set_2026-09-27/manifest.json`
- Create: `data/review_drafts/t3_5_candidate_set_2026-09-27/validation-report.json`
- Modify: `docs/tasks/phase-3-dataset/05-test-set-3pool.md`
- Modify: `docs/planning/prioritized-backlog-2026-09-21.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/superpowers/plans/2026-09-27-t3-5-agent-reviewed-benchmark.md`

**Interfaces:**
- Consumes: the clean candidate-source commit from Task 7 and reviewed CLI.
- Produces: hash-bound `draft_ready` evidence and an accurate handoff that leaves human review, BigQuery live verification, and final 100-case publication pending.

- [ ] **Step 1: Generate candidate manifest from a clean commit**

  Run the canonical `reviewed validate-candidates` command after Task 7 is committed. Confirm the manifest pins the candidate, catalog, leakage corpus, repository commit, and limitations digests and contains no review/live claim.

- [ ] **Step 2: Migrate task and backlog status**

  Rename the active T3.5 heading/content to agent-authored, human-reviewed while retaining the August three-pool path as historical. Mark tooling and 120-candidate draft complete only with evidence; leave user review, 100-case selection, live verification, and finalization unchecked. Update the stale backlog line that still names T5.4-A as the next task.

- [ ] **Step 3: Record the provenance decision**

  Add a decision-log entry with the superseded requirement, chosen profile, scientific limitations, training-leakage prohibition, artifact paths, and required next human action.

- [ ] **Step 4: Run focused verification**

  Run:

  ```bash
  .venv/bin/pytest -q tests/unit/test_testset_reviewed_*.py tests/unit/test_t35_candidate_pack.py
  .venv/bin/python scripts/12_test_set_workflow.py reviewed validate-candidates \
    --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27
  .venv/bin/python scripts/12_test_set_workflow.py reviewed validate-review \
    --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27
  ```

  Expected: candidate validation is `draft_ready`; review validation exits nonzero with a structured blocked reason naming missing human decisions.

- [ ] **Step 5: Run repository completion gates**

  Run:

  ```bash
  .venv/bin/pytest -q
  uv run ruff check .
  uv run ruff format --check .
  uv run python -m json.tool notebooks/10_noise_injection.ipynb >/dev/null
  git diff --check
  ```

  Expected: 0 failures, lint/format/notebook/diff checks pass, and no live client is created.

- [ ] **Step 6: Self-audit the published draft**

  Verify there are exactly 120 JSONL rows, no filled review/selection rows, no `test-100.jsonl`, no credential or PII material, no three-pool/kappa claim, no normalized leakage collision, and no untracked generated evidence.

- [ ] **Step 7: Commit documentation and draft evidence**

  ```bash
  git add data/review_drafts/t3_5_candidate_set_2026-09-27 \
    docs/tasks/phase-3-dataset/05-test-set-3pool.md \
    docs/planning/prioritized-backlog-2026-09-21.md \
    docs/memory/05-DECISION_LOG.md \
    docs/superpowers/plans/2026-09-27-t3-5-agent-reviewed-benchmark.md
  git commit -m "docs(dataset): publish T3.5 draft-ready evidence"
  ```

## External handoff after implementation

1. The user fills `review_events.csv` for all 120 candidates, including explicit follow-up acceptance for every revision.
2. The user fills `final_selection.csv` with exactly 100 accepted IDs and 30/50/20 difficulty.
3. Codex runs offline review validation and resolves any deterministic errors with the user; it does not alter human decisions.
4. The user explicitly authorizes the guarded BigQuery command after reviewing dry-run policy and credentials.
5. Only complete current live evidence permits `reviewed finalize` to publish `test-100.jsonl` and unlock genuine B0–B5 evaluation.
