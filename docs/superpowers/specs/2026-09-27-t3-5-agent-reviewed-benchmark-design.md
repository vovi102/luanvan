# T3.5 — Agent-authored, human-reviewed GoogleSQL benchmark

**Date:** 2026-09-27
**Status:** approved in conversation; implementation planning pending written-spec review
**Supersedes for active work:** the three-pool provenance requirements in
`2026-08-15-t3-5-google-sql-test-set-design.md`
**Canonical decision source:**
`docs/planning/prioritized-backlog-2026-09-21.md`

## Context

The original T3.5 workflow required three independent human pools, at least three
question authors, separate SQL writers, two reviewers on a 30-case subset, and a
Cohen's kappa threshold. Its tooling is implemented and remains a reproducible
historical artifact, but the required collaborators are unavailable on the active
critical path.

The canonical backlog therefore narrows the evidence claim. Codex drafts 120
English natural-language questions and their GoogleSQL gold queries. The user
reviews every candidate and explicitly accepts, revises, or rejects it, then
selects exactly 100 cases. The selected benchmark is verified live on BigQuery
before publication. Project documentation and downstream reports must describe
the result as **agent-authored, human-reviewed** and must not claim three-pool
collection, independent authorship, inter-rater review, or Cohen's kappa.

This migration changes provenance and review semantics, not the analytical
catalog, GoogleSQL safety policy, live-execution policy, or downstream rule that
the finalized test set is immutable and excluded from training and tuning.

## Goals

1. Produce a review-ready draft of exactly 120 distinct NL–GoogleSQL candidates
   against the managed Ethereum analytical catalog.
2. Give the user a deterministic local workflow to record `ACCEPT`, `REVISE`, or
   `REJECT` decisions without editing generated source files.
3. Require an explicit final selection of exactly 100 accepted cases with
   `easy=30`, `medium=50`, and `hard=20`.
4. Validate query safety, schema annotations, coverage, expected columns, and
   leakage constraints offline before any BigQuery call.
5. Require bounded live BigQuery evidence for all 100 selected queries before
   publishing `test-100.jsonl`.
6. Bind every published record to its draft, review, selection, SQL, live
   evidence, catalog, and source-code provenance with SHA-256 digests.
7. Preserve the limitations needed for honest thesis reporting and prevent the
   artifact from being presented as independently authored or independently
   reviewed.

## Non-goals

- The workflow does not simulate human reviewers, invent reviewer decisions, or
  auto-accept candidates.
- It does not claim independent test authorship, a three-pool protocol, reviewer
  agreement, Cohen's kappa, or a statistically representative population sample.
- It does not run baseline inference, train or fine-tune a model, or compare
  model performance. Those stages consume the finalized artifact later.
- It does not contact BigQuery during draft generation, review, offline
  validation, CLI help, or tests.
- It does not overwrite or reinterpret the historical three-pool artifacts.

## Chosen architecture

### Separate provenance profiles

The `src/nl2sparql/dataset/testset/` module gains an explicit provenance profile
instead of weakening the existing validator implicitly:

- `three_pool_v1` retains every historical three-pool invariant.
- `agent_authored_human_reviewed_v1` implements this design.

Every bundle, validation report, live-evidence artifact, and final record carries
the profile ID. Loading a file without a supported profile fails closed. A
three-pool bundle cannot be finalized through the agent-reviewed path and an
agent-reviewed bundle cannot be reported as three-pool evidence.

The public seam remains small:

```python
validate_candidate_pack(paths) -> CandidatePackReport
validate_review_bundle(paths) -> ReviewBundleReport
verify_sql(client, cases, policy=...) -> LiveEvidence
finalize_reviewed_bundle(bundle, evidence, output_path) -> FinalizationReport
```

Existing three-pool entry points remain available for reproducibility. The new
functions own profile-specific rules rather than adding conditional exceptions
throughout the old validator.

### Artifact layout

Draft and review material lives outside the canonical final path:

```text
data/review_drafts/t3_5_candidate_set_2026-09-27/
  candidates.jsonl
  review_events.csv
  final_selection.csv
  manifest.json
  REVIEW_GUIDE.md
  validation-report.json
```

Live and final artifacts are separate:

```text
data/dataset/test/
  live-evidence.json
  test-100.jsonl
  manifest.json
```

The draft directory is reviewable and may change through explicit revisions.
The finalized directory is immutable: publication refuses to overwrite an
existing artifact with different bytes.

## Candidate contract

`candidates.jsonl` contains exactly 120 canonical JSON objects sorted by stable
`question_id`. Each object contains:

- `schema_version` and `provenance_profile`;
- `question_id` and `author_type="agent"`;
- natural English `nl`;
- one read-only GoogleSQL `sql` statement;
- ordered `expected_columns` with explicit aliases;
- `expected_empty` and `ambiguity_flag` booleans;
- proposed `difficulty` in `easy`, `medium`, or `hard`;
- normalized `categories` and `entity_kinds`;
- explicit `schema_elements` and `cq_ids` from the canonical catalog;
- a short `rationale` explaining the intended operation and difficulty; and
- `generation_batch` plus source catalog and repository commit digests.

The candidate pack uses a 36/60/24 proposed difficulty distribution. This gives
the user six easy, ten medium, and four hard surplus candidates while preserving
the final 30/50/20 target. Proposed labels are advisory: only the user's reviewed
selection determines final difficulty.

Candidate IDs are content-independent stable sequence IDs (`t35-001` through
`t35-120`). SQL or wording revisions do not silently change identity; all content
changes are captured by hashes and review status.

## Candidate quality and coverage

Offline validation requires:

- exactly 120 unique IDs and normalized NL strings;
- one parseable GoogleSQL query per candidate;
- a single read-only statement, no comments, mutation, wildcard projection, or
  unmanaged relation/table function;
- explicit and unique output aliases matching `expected_columns`;
- catalog-valid schema and competency-question annotations;
- at least six categories and all three supported entity kinds;
- coverage of filters, aggregations, grouped comparison, top-k, time range,
  named-entity, address-only, class-level, and multi-relation questions;
- operation coverage derived from the parsed SQL AST plus at least 30 normalized
  SQL operation shapes (temporal/entity variants may intentionally share one
  shape);
- no exact or normalized-NL duplicate within the pack; and
- no exact or normalized-NL overlap with Stage A–D, T4 evaluation sets, or other
  finalized benchmark material discoverable in the repository.

The leakage scan is deterministic and reports every input path and digest. It is
an exact/normalized-text guard, not a semantic-independence claim. The manifest
states this limitation explicitly.

## Human review contract

`review_events.csv` is an append-only decision log with at least one row for
every candidate:

```text
question_id,review_round,reviewer_id,nl_quality,sql_faithfulness,difficulty,decision,revised_nl,revised_sql,notes
```

Rules:

- `reviewer_id` is a stable pseudonym and may not be an email address.
- One stable reviewer identity is used for the complete candidate pack, and
  `review_round` starts at 1 and increases contiguously per candidate.
- Scores are integers from 1 to 5.
- `decision` is `ACCEPT`, `REVISE`, or `REJECT`.
- `ACCEPT` requires both scores at least 4 and empty revision fields.
- `REVISE` requires at least one revised field. The revised candidate is
  revalidated and rehashed, and a later review round must explicitly `ACCEPT`
  the revised content; revision never implies acceptance.
- `REJECT` candidates cannot appear in final selection.
- Missing decisions block finalization; the system never fills defaults.

This is a single-reviewer workflow. The report records review completeness and
decision counts but does not calculate or display Cohen's kappa.

## Final-selection contract

`final_selection.csv` contains exactly 100 unique, accepted IDs:

```text
question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,selection_note
```

Validation requires exact difficulty counts of 30 easy, 50 medium, and 20 hard;
at least six categories; all three entity kinds; and catalog-valid annotations.
Every selected row binds to the post-review NL and SQL hashes. Selection is an
explicit user decision and is never performed automatically from scores.

## BigQuery verification

Only the explicit `verify-live` command may initialize BigQuery credentials or
submit jobs. It requires a reviewed and selected 100-case bundle plus the
existing live opt-in and cost controls.

The current safety behavior remains mandatory:

- complete dry-run preflight before any live execution;
- immediate second dry run before each query;
- query cache disabled;
- 20 GiB maximum per query and 64 GiB aggregate;
- bounded result previews;
- exact ordered expected-column validation;
- positive result size unless `expected_empty=true`; and
- job ID, processed bytes, billed bytes, latency, row count, SQL hash, location,
  project, timestamp, and policy provenance recorded for every case.

Any missing, stale, failed, or policy-violating query blocks the entire final
artifact. Partial live success is forensic evidence only.

## Final artifact and downstream boundary

`test-100.jsonl` preserves the SQL-native fields required by baseline and
evaluation code and adds explicit provenance:

- `source="agent"`;
- `review_provenance="single_human_reviewer"`;
- `provenance_profile="agent_authored_human_reviewed_v1"`;
- pseudonymous reviewer ID;
- candidate, accepted-content, selection, live-evidence, and catalog SHA-256
  values;
- `provenance_bundle_sha256`, computed from the ordered non-self-referential
  digests above; and
- `verified_executable=true` with the authoritative UTC verification time.

The final manifest includes a machine-readable limitations array containing at
least `agent_authored`, `single_human_reviewer`, `no_independent_authorship`,
`no_inter_rater_agreement`, and `no_kappa_claim`. It records the final JSONL
SHA-256 and the same provenance-bundle digest. Final rows do not contain the
manifest hash, avoiding a circular digest dependency.

Once finalized, the 100 questions and their variants are forbidden inputs to:

- Stage B/C paraphrasing;
- Stage D noise injection;
- prompt, retrieval, schema-linker, or hyperparameter tuning;
- model training or fine-tuning; and
- manual error-driven system changes before the primary evaluation is locked.

Downstream evaluation requires the sibling manifest, validates its final-row
bindings, and records both the snapshot and manifest SHA-256 values. The
manifest is published last and acts as the readiness marker; a JSONL without a
valid matching manifest is incomplete and rejected.

## CLI behavior

`scripts/12_test_set_workflow.py` gains profile-specific commands or explicit
profile arguments for:

- validating the checked-in candidate pack;
- validating human decisions and revisions;
- validating the final selection;
- performing guarded live verification; and
- finalizing the reviewed benchmark.

Help, generation, review validation, selection validation, and all tests are
offline. Live access remains opt-in and cannot be selected through a default.
Every failure produces `blocked` or `failed` status with a nonzero exit code; no
command publishes a plausible partial final artifact.

## Readiness states

- `draft_ready`: 120 candidates pass offline quality, coverage, and leakage
  checks and are ready for user review.
- `review_ready`: every candidate has a valid user decision, all revisions have
  explicit acceptance, and the selected 100 pass final quotas.
- `live_ready`: all selected SQL queries have current bounded BigQuery evidence.
- `finalized`: immutable `test-100.jsonl` and manifest are published and their
  hashes verify.

Only `finalized` unlocks genuine B0–B5 accuracy evaluation. None of these states
upgrades the provenance to independently authored or independently reviewed.

## Compatibility and migration

The August three-pool design, schemas, tests, and CLI behavior remain supported
under `three_pool_v1`. Existing files are not rewritten. Documentation marks
that path as historical/optional and makes the September canonical backlog the
active T3.5 acceptance source.

Downstream consumers must accept the new explicit provenance fields without
discarding them. Any consumer that requires independent authorship must reject
this benchmark rather than silently treating it as three-pool evidence.

## Testing strategy

Tests are written before implementation and cover:

1. strict parsing and deterministic serialization of all new artifacts;
2. exact 120-candidate and 36/60/24 draft quotas;
3. SQL safety, explicit columns, annotation validation, coverage, and leakage;
4. review completeness, score rules, revision/acceptance transitions, and
   rejection handling;
5. exact 100-case 30/50/20 final selection;
6. profile confusion and attempts to use one provenance path as another;
7. stale hashes and immutable-publication behavior;
8. offline commands never initializing credentials or network clients;
9. fake-client live verification failure modes and evidence binding; and
10. an end-to-end synthetic fixture that reaches tooling readiness but is never
    reported as genuine human review or real BigQuery evidence.

Repository completion gates are the focused T3.5 tests, full `pytest`, Ruff lint,
Ruff format check, notebook JSON validation, `git diff --check`, and a review of
the generated candidate manifest. Genuine T3.5 completion additionally requires
the user's recorded review and the explicit live BigQuery run.

## Risks and mitigations

- **Agent phrasing bias:** require persona and operation diversity, report
  category distribution, and disclose authorship.
- **Gold SQL defects:** require user faithfulness review, AST/catalog validation,
  and live result verification; none alone is treated as sufficient.
- **Test leakage:** keep review drafts separate, scan repository datasets, bind
  the finalized hash, and prohibit all tuning use.
- **Review fatigue:** provide 120 bounded candidates, concise rationales, stable
  IDs, and resumable decisions without auto-acceptance.
- **Provenance inflation:** encode profile and limitations in every layer and
  reject cross-profile finalization.
- **Unexpected BigQuery cost:** preserve complete dry-run and byte-cap guards;
  live execution remains a separate explicit user-authorized stage.

## Acceptance criteria

- A deterministic, hash-bound 120-candidate draft passes offline validation.
- The user can review, revise, reject, and select candidates without editing the
  generated candidate source.
- Final selection cannot pass unless it contains 100 accepted cases with exact
  30/50/20 difficulty quotas and required coverage.
- No offline operation accesses credentials, BigQuery, or another network API.
- Final publication requires complete current live evidence for all 100 cases.
- Final artifacts and reports identify the benchmark as agent-authored and
  single-human-reviewed and explicitly prohibit three-pool/kappa claims.
- Historical `three_pool_v1` behavior remains reproducible and its tests pass.
- The finalized snapshot is hash-bound and excluded from every training and
  tuning path.
