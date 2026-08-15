# T3.5 — GoogleSQL three-pool test-set workflow

**Date:** 2026-08-15
**Status:** approved design; implementation may proceed offline
**Scope:** migrate the independent test-set contract from Plan A SPARQL/Fuseki to
Plan B GoogleSQL/BigQuery, and build the reproducible tooling around the human
collection gates.

## Context and non-goals

The original T3.5 task describes `(NL, SPARQL)` pairs, Fuseki execution, and a
single Pool C reviewer. The project pivoted to Plan B, where the canonical target
is read-only GoogleSQL over the analytical catalog. The revised workflow keeps
the three independent pools but makes every executable and audit field SQL-native.

This task does not invent Pool A questions, impersonate collaborators, fabricate
reviews, or claim BigQuery execution without credentials and accepted human
submissions. The implementation must make those missing gates explicit and leave
the final artifact absent until its evidence is complete.

## Goals and acceptance mapping

The offline implementation will provide:

1. Strict schemas and CSV readers for Pool A questions, Pool B SQL gold, Pool C
   review decisions, and a lead-owned final selection.
2. Validation for duplicate IDs, empty/unsafe text, author coverage, Pool B
   one-to-one joins, SQL read-only safety, accepted review decisions, difficulty
   quotas, category coverage, and the required 30-case double-review subset.
3. A dependency-free Cohen's kappa calculation over the designated subset. The
   tool fails closed for missing raters, missing labels, or a degenerate sample;
   it never substitutes percent agreement for kappa.
4. A deterministic finalizer that consumes an explicit `final_selection.csv`.
   Human selection is an input, not an algorithmic side effect. It emits exactly
   100 JSONL records only when all offline gates and live evidence pass.
5. A BigQuery adapter that performs a complete dry-run preflight before any
   execution, disables query cache, applies the existing 20 GiB per-query and
   64 GiB aggregate policy, rejects mutation/multi-statement SQL, checks expected
   columns and the non-empty/explicit-empty policy, and records bytes, latency,
   job ID, and evidence hashes.
6. A CLI and scaffold documents that collaborators can use without Python
   knowledge. Missing credentials or source files produce a structured blocked
   report and a nonzero exit, never a partial final artifact.

The human/live acceptance gates remain pending until evidence exists:

- at least three pseudonymous Pool A authors, each contributing at least 20
  questions;
- at least 100 accepted final records with 30/50/20 easy/medium/hard quotas;
- 100% BigQuery verification (non-empty or explicitly expected empty);
- Pool C reject rate below 30%; and
- Cohen's kappa at least 0.7 on the 30-row double-reviewed subset.

## Chosen architecture

### Deep module and interface

The seam is `src/nl2sparql/dataset/testset/`. Its public interface is deliberately
small:

```python
validate_bundle(paths: TestSetPaths) -> BundleReport
verify_sql(client, cases, policy=...) -> LiveEvidence
finalize_bundle(bundle, evidence, selection_path) -> FinalizationReport
```

`contracts.py` owns typed record shapes and the `TestSetPaths` manifest. The
implementation behind the interface owns CSV decoding, canonicalization,
cross-file joins, review aggregation, quota checks, kappa, SQL safety, and
deterministic JSONL serialization. Callers do not duplicate row-level rules.

The BigQuery client is an adapter passed into `verify_sql`; offline tests use a
fake adapter and do not initialize credentials. The adapter uses GoogleSQL
`QueryJobConfig(dry_run=True, use_query_cache=False, maximum_bytes_billed=...)`
for preflight, repeats the dry run immediately before each execution, and
collects only bounded result previews.

### File contracts

All CSVs are UTF-8 with a header and stable `question_id` values. Person
identifiers are pseudonyms and must not be email addresses or free-form names.

`raw_pool_a.csv`:

```text
question_id,author_id,nl,persona,source_batch
```

Pool A authors receive only the brief and a small entity-name list; the validator
does not require or trust their optional difficulty/category hints.

`sql_pool_b.csv`:

```text
question_id,writer_id,sql,expected_empty,ambiguity_flag,notes
```

Each question has exactly one canonical Pool B row after ambiguity resolution.
`expected_empty` is explicit rather than inferred from a zero result.

`review_pool_c.csv`:

```text
question_id,reviewer_id,nl_quality,faithfulness,difficulty,decision,notes
```

Scores are integers 1–5, difficulty is one of `easy`, `medium`, `hard`, and
decision is `ACCEPT`, `REVISE`, or `REJECT`. The designated kappa subset must
have exactly two distinct reviewers per question; all remaining final candidates
must have at least one independent review.

`final_selection.csv`:

```text
question_id,final_difficulty,categories,entity_kinds,selection_note
```

The lead researcher supplies exactly 100 unique accepted IDs and the final
difficulty labels. Categories and entity kinds are pipe-separated stable labels.
The finalizer checks, but does not rewrite, this human decision.

`test-100.jsonl` records contain only pseudonymous provenance and SQL-native
fields: `id`, `source`, `nl`, `sql`, `difficulty`, `categories`,
`schema_elements`, `cq_ids`, `expected_result_size`, `ambiguity_flag`,
`pool_b_writer`, `pool_c_reviewers`, `verified_executable`, `verified_at`, and
`evidence_sha256`. No SPARQL or Fuseki field is emitted.

### CLI modes and publication

`scripts/12_test_set_workflow.py` exposes:

- `scaffold`: create headers, briefs, `PROCESS.md`, and `CONSENT.md`; refuses to
  overwrite non-empty files unless `--force` is explicit;
- `validate`: run all credential-free bundle, schema, review, coverage, kappa,
  and quota checks and emit a JSON/Markdown report;
- `verify-live`: require an accepted Pool B bundle, run complete dry-run gates,
  execute bounded read-only SQL, and write evidence atomically;
- `finalize`: require valid bundle, passing kappa/quota/review gates, live
  evidence hashes, and explicit final selection before publishing `test-100`.

Every generated report includes the git commit, schema version, input SHA-256
digests, UTC timestamp, policy caps, and a `status` of `ready`, `blocked`, or
`failed`. Publication is staged and replaced only after validation; an incomplete
run cannot leave a plausible final artifact.

## Validation details

- Canonical NL is Unicode-normalized, trimmed, and rejected if empty or contains
  control characters. Duplicate canonical NL is rejected within the final set.
- SQL must be a single read-only `SELECT`/`WITH` statement, use the managed
  analytical catalog, project explicit columns, and contain no comments or
  mutation keywords that could hide a second statement. The live adapter remains
  the authority for BigQuery parsing.
- Final difficulty counts are exactly `easy=30`, `medium=50`, `hard=20`.
- The final set must cover at least six categories and three entity kinds as
  recorded in the selected rows.
- Review acceptance is computed from review rows; a `REVISE` or `REJECT` cannot
  silently become accepted.
- Kappa uses the standard observed-agreement/chance-agreement formula on the
  two-reviewer subset and fails closed when the denominator is zero.
- Live evidence binds `question_id`, SQL SHA-256, row policy, bytes processed,
  bytes billed, cache-hit status, and job ID. A later SQL edit invalidates the
  evidence and blocks finalization.

## Testing strategy

Tests are written first at the module interface. Offline tests cover valid
fixtures and each failure mode: malformed headers, duplicate IDs, author
coverage, unsafe SQL, mismatched joins, missing/double reviews, kappa below
threshold, quota mismatch, deterministic output, stale evidence, and blocked
credentials. Fake BigQuery jobs cover dry-run budget rejection, re-preflight,
column/result-policy checks, cache rejection, and evidence hashing. A CLI test
proves scaffold/validate are credential-free and finalize is fail-closed.

The full repository gate remains `uv run pytest -q`, followed by Ruff,
format-check, notebook JSON validation, and `git diff --check`.

## Alternatives rejected

- Keeping SPARQL/Fuseki would contradict the approved Plan B architecture and
  make downstream linking/evaluation contracts inconsistent.
- A docs-only form would leave quality gates unenforced and allow silent schema
  drift.
- Automatic top-score selection would erase the human review decision and make
  the benchmark less auditable.
- A web survey platform is deferred; it adds infrastructure and PII risk without
  improving the local, reproducible validation seam.

## Blockers and handoff

The committed scaffold and validators are the offline checkpoint. Human
recruitment, consent, question writing, independent SQL gold authoring, review,
and BigQuery credentials are external gates. `PROCESS.md` explains the handoff;
`CONSENT.md` keeps publication consent separate from benchmark records.
