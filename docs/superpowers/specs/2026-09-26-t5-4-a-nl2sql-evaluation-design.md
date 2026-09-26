# T5.4-A NL2SQL Evaluation Framework Design

**Date:** 2026-09-26
**Status:** conversational design approved; written-spec review pending
**Scope:** implement the canonical, evidence-first NL2SQL evaluation framework used
by B0, B1/B2 and B4/B5, without running or claiming genuine baseline results.

## Intent

T5.4-A replaces the legacy SPARQL/Fuseki evaluation design with a GoogleSQL and
BigQuery framework. It standardizes six evaluation dimensions across baselines:
accuracy, latency, cost, privacy, reproducibility and failure modes. Exact and
structural SQL matches are diagnostic metrics. BigQuery execution accuracy is the
primary accuracy metric.

The framework separates costly, stateful execution from deterministic scientific
reporting:

1. `execute` validates and executes gold and predicted GoogleSQL under explicit
   BigQuery safety, byte, cost and timeout guards.
2. Execution produces immutable, hash-bound evidence.
3. `report` reads canonical prediction and execution evidence without credentials,
   network access or an executor.
4. `compare` computes paired deltas from reports that cover the same case IDs.

Tests use injected fake executors. T5.4-A must not contact BigQuery unless the user
invokes the live command with explicit opt-in and complete guard configuration.

## Completion boundary

T5.4-A has two deliberately separate completion states.

- **Implementation complete** means contracts, adapters, execution guards, result
  semantics, metrics, artifacts, CLI behavior, documentation and tests pass.
- **Scientific complete** requires finalized T3.5 evidence, genuine baseline runs,
  valid live BigQuery execution, complete reproducibility/privacy/cost evidence and
  no scientific blockers. T5.4-A does not by itself satisfy this state.

Synthetic or fake-executor fixtures must remain explicitly marked and must never be
presented as baseline results.

## In scope

- immutable canonical prediction, execution, report and comparison contracts;
- adapters for B0, B1/B2 and B4/B5 artifacts;
- GoogleSQL exact normalization and AST structural signatures;
- BigQuery result canonicalization and comparison;
- an injected executor seam with fake and guarded BigQuery adapters;
- execution accuracy and answer precision, recall and F1;
- inference and execution latency;
- inference and BigQuery evaluation cost kept separate;
- structured privacy and reproducibility evidence;
- multi-label failure classification;
- bootstrap confidence intervals and paired-bootstrap deltas;
- deterministic JSON artifacts and integrity validation;
- CLI commands for adaptation, execution, reporting, comparison and validation;
- migration of the T5.4 task from SPARQL/Fuseki to NL2SQL/BigQuery.

## Out of scope

- genuine full baseline runs or fabricated results;
- B0-B5 rankings or scientific conclusions;
- T5.4-B comparative synthesis;
- T5.5 pivot decisions;
- B3 fine-tuning;
- Phase 6 or Phase 7 implementation;
- SPARQL/Fuseki evaluation;
- automatic semantic-drift claims;
- automatic recovery or resumption of a partially executed BigQuery run;
- live BigQuery use without explicit operator opt-in.

## Architectural decision

Use a canonical hub-and-spoke architecture. Each baseline adapter validates its
native artifacts and converts them into one `CanonicalPredictionRun`. The execution,
metrics and reporting modules consume only canonical contracts; they do not import
baseline-specific models.

This is preferred to evaluator plugins because denominator, SQL semantics,
bootstrap and readiness rules must exist in one place. A fully event-sourced
evaluation platform is rejected as unnecessary for this task. Execution still uses
a small hash-chained journal so paid job evidence survives a process failure, but
the journal is not a general event platform.

## Module layout and interfaces

The implementation lives below `src/nl2sparql/evaluation/`:

- `contracts.py` owns immutable canonical dataclasses, enums, schema versions and
  validation. It has no file or network I/O and imports no baseline package.
- `adapters/b0.py`, `adapters/b12.py` and `adapters/b45.py` are the only modules
  that understand native baseline contracts and artifact layouts.
- `sql_semantics.py` owns BigQuery-dialect parsing, canonical exact forms,
  structural signatures, top-level order detection and structural facts.
- `result_semantics.py` owns typed BigQuery value normalization, row fingerprints,
  sequence/multiset comparison and per-case answer metrics.
- `executor.py` defines the injected `QueryExecutor` interface and test fake.
- `bigquery.py` implements the guarded production executor and lazily imports the
  Google Cloud client.
- `execution.py` orchestrates validation, preflight, execution, cancellation and
  evidence sealing.
- `metrics.py` derives aggregates, breakdowns, bootstrap intervals and paired
  bootstrap deltas.
- `failures.py` derives multi-label failure evidence.
- `artifacts.py` owns canonical JSON, self-hashes, cross-hashes, journals, atomic
  publication and strict loading.
- `reporting.py` constructs reports only from verified offline artifacts.
- `cli.py` is a thin Click interface over those deep modules.
- `__init__.py` exports only stable canonical types and high-level operations.

The public package surface is intentionally small:

```python
adapt_baseline_artifacts(...) -> CanonicalPredictionRun
execute_run(...) -> ExecutionEvidence
build_report(...) -> EvaluationReport
compare_reports(...) -> ComparisonReport
load_and_verify_artifact(...) -> CanonicalArtifact
```

The executor is a real seam because production supplies a BigQuery adapter and
tests supply an in-memory fake. Internal SQL, result and statistics helpers are not
exposed merely for tests; callers and tests use the same module interfaces.

## Canonical artifact envelope

Every standalone JSON artifact uses this logical envelope:

```json
{
  "artifact_type": "nl2sql_prediction_run",
  "schema_version": 1,
  "body": {},
  "artifact_sha256": "lowercase SHA-256"
}
```

`artifact_sha256` is the SHA-256 of the canonical JSON bytes for
`artifact_type`, `schema_version` and `body`; it does not include itself.
Serialization is UTF-8, key-sorted, compact, finite-only and newline-terminated.
Money and other exact decimals are canonical decimal strings. Artifact readers
accept an exact field set and known schema version, verify canonical bytes and use
constant-time digest comparison. Unknown versions and unknown fields fail closed.

Filesystem paths are not artifact identities. Source references contain a stable
role, media type, schema version when known and SHA-256. Arrays whose order has no
scientific meaning are sorted before serialization. The order of benchmark cases is
the authoritative T3.5 order and is preserved.

Adapter conversion adds no current timestamp. Given identical native files and
test-set bytes, it emits identical canonical bytes. Execution timestamps are facts
of the live run. Reporting does not add a current timestamp, so the same verified
inputs and policy always produce the same report bytes.

## Canonical prediction contract

`CanonicalPredictionRun` contains:

- baseline ID, run ID, seed and native generation timestamp;
- exact finalized test-set SHA-256 and case count;
- reviewed, live-verified and synthetic provenance markers;
- native source artifact references and hashes;
- model, configuration, catalog, prompt, training and provider fingerprints when
  applicable;
- adapter identity and adapter schema version;
- an ordered, complete tuple of prediction cases.

Each `PredictionCase` contains:

- case ID, question, gold SQL, difficulty and sorted unique categories from the
  authoritative test-set snapshot;
- a prediction status, predicted SQL when valid, raw-output SHA-256 and safe error
  code;
- inference latency, token observations and inference cost evidence;
- structured privacy evidence.

Prediction statuses are `ok`, `no_output`, `invalid_sql`, `unsafe_sql`,
`generation_error` and `timeout`. Only `ok` may carry predicted SQL. A native status
that cannot be represented is retained in adapter provenance but maps to the closest
canonical terminal status or causes adaptation to fail if doing so would be
ambiguous.

An adapter loads the finalized test set independently. It rejects duplicate,
missing or extra prediction case IDs and mismatched duplicated gold data; it never
silently intersects artifacts. The authoritative gold question, SQL, difficulty and
categories come from T3.5, not from a prediction artifact.

Cost evidence uses `observed` or `unmeasured` measurement states. An observed cost
has a currency, exact amount and source. An unmeasured cost has `amount=null`. Zero
is accepted only when evidence explicitly measured zero; local cost is not inferred
to be USD 0.

Privacy evidence records whether documentation exists, whether data egress is
`none`, `provider` or `unknown`, the provider identity when applicable, and policy
or review hashes. Missing privacy evidence becomes `undocumented`; the adapter does
not invent a favorable local privacy rating.

## Baseline adapters

The B0 adapter reads the native prediction JSONL and self-hashed evaluation report,
then joins them to the authoritative T3.5 snapshot. Existing B0 aggregate exact and
structural rates are treated only as native operational evidence because their
historical denominator policy differs; T5.4 recomputes canonical metrics per case.

The B1/B2 adapter reads predictions, inference logs and the self-hashed native
report. It validates run, case, seed, input, model/config/catalog/training and
selected-example consistency across all files before conversion.

The B4/B5 adapter uses the existing native artifact loader so journal chains,
attempts, budgets, provider metadata, privacy fingerprints and report bindings are
validated before conversion. It retains authoritative inference charge evidence
without mixing it with BigQuery evaluation cost.

All adapters compute and retain the exact source-file hashes. They do not modify the
native baseline contracts or publication paths.

## SQL semantics

SQLGlot with `read="bigquery"` and `dialect="bigquery"` is the only parser and
renderer used by canonical SQL comparison.

Exact match compares canonical SQLGlot renderings after successful safety
validation. It removes formatting and keyword-case differences without lowercasing
raw SQL or changing string literals.

Structural signatures operate on the AST. They normalize aliases and formatting,
preserve node/operator/order structure and replace literal values with typed literal
placeholders. This makes structural match diagnostic: two queries can share a
structure while using a wrong filter value. Separate structural facts retain
literals for failure classification.

Top-level `ORDER BY` on the gold query determines result order semantics. An ordered
gold query uses sequence comparison. An unordered gold query uses multiset
comparison even if the prediction adds an order; the extra order remains available
to `wrong_order_or_limit` classification.

Parse or safety failure returns a typed diagnostic. It never falls back to regular
expressions or executes the query.

## BigQuery result semantics

Rows are normalized in BigQuery schema order, not mapping-key order. Column names
and schema hashes are retained as diagnostics, while execution equality requires
matching arity and normalized row values. A harmless output alias change alone does
not make otherwise equal results execution-incorrect.

Values use explicit type tags:

- NULL has a unique null tag;
- booleans remain distinct from integers;
- finite integer, NUMERIC, BIGNUMERIC and floating values use an exact canonical
  numeric representation without arbitrary rounding; negative zero normalizes to
  zero;
- floating NaN and infinities use explicit special tags;
- TIMESTAMP values normalize to UTC with a fixed ISO representation;
- DATE, TIME and timezone-free DATETIME retain distinct tags;
- bytes use canonical base64;
- strings are preserved verbatim;
- arrays preserve order;
- structs and JSON objects sort field names while recursively normalizing values.

Each normalized row becomes a SHA-256 digest. For ordered results, row digests stay
in sequence. For unordered results, row digests are sorted but not deduplicated, so
duplicate multiplicity is preserved. The result evidence records row count, arity,
schema fingerprint, order semantics, row digests and an aggregate result digest; it
does not need to publish raw result values.

Answer overlap always uses row multisets, even for ordered queries. Therefore an
ordered query can have answer F1 1 while execution accuracy is false because row
order differs.

## Execution evidence contract

`ExecutionEvidence` binds:

- execution ID;
- canonical prediction artifact SHA-256;
- test-set SHA-256;
- complete execution policy and policy hash;
- executor kind, project/location, client/library version and pricing assumptions;
- overall validity and derived blockers;
- one execution case per canonical case;
- aggregate BigQuery byte and cost evidence;
- terminal execution-journal hash.

Each execution case contains a gold `QueryExecution` and a prediction
`QueryExecution`. Prediction statuses that are not executable receive explicit
`skipped_no_output`, `skipped_invalid_sql`, `skipped_unsafe_sql`,
`skipped_generation_error` or `skipped_inference_timeout` outcomes rather than
disappearing. Inference timeout and BigQuery execution timeout remain distinct
facts even though both contribute a `timeout` failure tag.

Executable terminal outcomes are `completed`, `guard_blocked`, `timeout` and
`execution_error`. A query outcome contains query hash, dry-run estimate and guard
decision, job ID, timestamps, monotonic elapsed time, processed/billed bytes, cache
status, cancellation state, safe error code, cost evidence and result evidence when
completed.

Any gold dry-run, guard, timeout, execution or result-canonicalization failure marks
the whole execution evidence `invalid`. The failure remains recorded and no case is
removed. A prediction failure is a normal false result in the common denominator.

## BigQuery opt-in and guard policy

The live adapter is created only by `execute --executor bigquery` when all of the
following are supplied:

- `--allow-bigquery`;
- explicit project and location;
- a positive timeout;
- positive per-query and aggregate byte caps;
- a pinned pricing policy and positive maximum estimated USD cost.

Missing opt-in or guard configuration fails before credentials, a BigQuery client or
network access are initialized. `report`, `compare`, `validate` and CLI help do not
import the production adapter.

The immutable execution policy contains project, location, timeout,
`maximum_bytes_billed_per_query`, maximum estimated and billed aggregate bytes,
billing model, price-per-TiB, conservative per-query billing floor/rounding rules,
pricing source/version/hash, maximum estimated USD cost, and
`use_query_cache=false`. Estimated cost rounds upward under that pinned policy; a
pricing policy that cannot produce a conservative estimate is invalid for live
execution.

Execution is sequential and follows these steps:

1. verify prediction and test-set artifacts;
2. statically validate every gold and candidate prediction;
3. dry-run every gold query; any failure seals invalid evidence and prevents live
   execution;
4. dry-run executable predictions; prediction guard failures become false cases;
5. ensure the aggregate conservative estimate fits byte and cost caps;
6. repeat dry-run immediately before each submitted query;
7. submit gold then prediction for each case with cache disabled and server-side
   `maximum_bytes_billed`;
8. record terminal evidence before proceeding;
9. stop before the next submission if aggregate guards can no longer be honored;
10. seal the journal and publish final evidence last.

`job.result(timeout=...)` enforces the timeout. On timeout, the adapter requests
cancellation and records whether cancellation succeeded, failed or is unknown. It
collects job statistics when available. A submitted job with unresolved billing
evidence is never assigned zero cost.

## Cost semantics

Inference and BigQuery evaluation cost are separate report branches.

BigQuery job statistics provide observed processed and billed bytes but not always a
job-attributed invoice charge. Reports therefore distinguish:

- observed billed bytes;
- estimated on-demand USD cost derived from billed bytes and the pinned pricing
  policy;
- observed charge USD, which remains null unless direct billing evidence is
  available and attributable to the job.

Reservation or flat-rate billing is not relabeled as an observed on-demand charge.
If pricing permits a conservative estimate, it is labeled estimated. Otherwise USD
cost is unmeasured while observed byte evidence remains available.

A query skipped before submission has observed zero evaluation bytes. A timeout or
request error has zero only when job evidence establishes zero billed bytes. If any
submitted job has unresolved cost, the aggregate USD measurement is `partial` or
`unmeasured`; an observed subtotal is not reported as the full-run total.

## Metrics and denominator policy

Let `N` be the complete case count in the canonical T3.5 snapshot. Exact match,
structural match, execution accuracy and headline answer precision/recall/F1 all use
`N` cases. A missing, invalid, unsafe, timed-out, guard-blocked or execution-error
prediction is false and remains in the denominator.

If any gold execution fails, execution accuracy and answer metrics are invalid:
their denominator remains `N`, but numerator and value are null and invalid case IDs
are recorded. The framework never reports a partial successful-case accuracy.
Textual exact and structural diagnostics may still be emitted, accompanied by the
scientific blocker.

Per-case answer conventions are:

- empty gold and empty prediction: precision, recall and F1 are 1;
- non-empty gold and empty/failed prediction: all are 0;
- empty gold and non-empty prediction: all are 0;
- otherwise precision and recall use multiset overlap and F1 is their harmonic
  mean.

Headline answer metrics are macro averages so each natural-language case has equal
weight. Their numerator is the sum of per-case scores and denominator is `N`.
Optional micro row totals are diagnostics, not headline metrics.

Every reported ratio contains numerator, denominator, value and a 95% confidence
interval. Failure-mode rates use `N`; because tags are multi-label, their rates need
not sum to one. Difficulty breakdowns use the full cases in that difficulty.
Category breakdowns use every case carrying that category and may overlap.

Latency is split into inference, predicted-query execution, gold-query execution
and total execution-run latency. Each distribution exposes expected, observed and
missing counts plus P50, P95 and P99 with bootstrap intervals. Skipped queries are
not assigned zero latency. Missing required latency evidence is visible and may
block scientific readiness.

Cost per 1,000 cases scales by `N`, not by successful queries. Coverage of observed
cost is reported alongside totals.

## Bootstrap and comparison

The default is 10,000 samples, seed 42 and a percentile 95% interval using the 2.5
and 97.5 percentiles. Resampling operates on case indices, never individual result
rows. Breakdown intervals resample only within their subgroup. Degenerate intervals
such as `[1, 1]` are valid.

The implementation uses a local seeded random generator and a documented pure
Python resampling/quantile policy under the supported Python 3.11 runtime so results
do not depend on ambient global RNG state.

Reproducibility accepts at least two comparable runs and reports raw-output/failure
observation agreement plus normalized-SQL/failure observation agreement. Scientific
readiness requires three genuine runs with the same baseline/config/test-set/model
identity and complete case IDs. For `k` runs, the denominator is
`N * k * (k - 1) / 2`.

Each evaluation report designates exactly one primary prediction/execution pair.
Headline accuracy, latency, cost, failure and breakdown metrics come only from that
primary run and therefore retain denominator `N`. Zero or more compatible replicate
pairs contribute only to the reproducibility dimension and its readiness checks;
their case outcomes are not pooled into the primary metrics. The primary run ID is
explicit, so input ordering cannot silently select it.

`ComparisonReport` requires the same test-set hash and identical case-ID set on both
sides. It records left and right report hashes, paired case-set hash, metric values,
`left - right` delta and paired-bootstrap interval. Each sample selects the same case
indices for both systems. A comparison may be generated diagnostically from blocked
reports, but inherits a scientific blocker and never declares a winner.

## Failure classification

Failure classification is multi-label and runs only on cases that are not successful
under the execution policy, including predictions that were never executable.
Automated tags are:

- `no_output`, `invalid_sql`, `unsafe_sql`, `execution_error`, `timeout`;
- `wrong_relation`, based on normalized relation multisets;
- `wrong_projection`, based on alias-insensitive projection expressions;
- `wrong_filter`, based on WHERE/HAVING/QUALIFY facts with literals preserved;
- `wrong_join`, based on join graph, type and predicates;
- `wrong_aggregation`, based on aggregates, DISTINCT, grouping and windows;
- `wrong_order_or_limit`, based on ordering, directions, null ordering, limits and
  offsets;
- `answer_mismatch`, when both queries execute but results differ;
- `unclassified`, when no root-cause operational or structural tag is supported.

Additional operational tags include `guard_blocked`, `generation_error` and
`cost_unresolved`. `answer_mismatch` describes the symptom. When it is the only
supported fact, the case also receives `unclassified`.

Execution-equivalent cases have no failure tags even if exact or structural match
is false. Automated classification never emits `semantic_drift`. That label is
accepted only from a hash-bound manual-review sidecar containing case ID, reviewer
ID, tags, note hash and review artifact hash; its source is recorded as
`manual_review`.

## Evaluation report

`EvaluationReport` contains:

- baseline identity, explicit primary run ID and all primary/replicate
  prediction/execution artifact hashes;
- test-set and case-set identities;
- expected and represented population counts;
- implementation and scientific readiness plus sorted blockers;
- six dimension sections;
- difficulty and category breakdowns;
- compact per-case metric/failure records;
- bootstrap policy;
- self-hash.

Per-case report rows include exact/structural booleans, execution outcome/match,
answer metrics, inference and execution latency, separate costs and failure tags.
They do not contain raw BigQuery results. These rows are the input for breakdowns
and paired comparison.

`implementation_status=ready` means the framework produced a complete,
integrity-valid derived artifact. It may be ready while
`scientific_status=blocked`, for example when a fake executor correctly demonstrates
the pipeline or a gold failure is correctly preserved. Scientific readiness is a
derived state; callers cannot set it directly.

Fatal contract/integrity errors produce no accepted report. Valid but insufficient
evidence produces a blocked report. Stable blocker codes include synthetic input,
fake executor, missing finalized test provenance, incomplete case coverage, gold
execution failure, unresolved submitted-job cost, incomplete reproducibility,
missing privacy evidence and missing genuine baseline runs.

## CLI

Add `scripts/19_nl2sql_evaluation.py` as a small wrapper over
`nl2sparql.evaluation.cli`.

Commands are:

```text
adapt b0|b12|b45   validate native artifacts and publish a canonical run
execute            create guarded execution journal and sealed evidence
report             build a deterministic offline evaluation report
compare            build deterministic paired deltas and intervals
validate           verify one artifact and all available bindings offline
```

`execute` requires canonical input plus explicit BigQuery project, location,
timeout, byte caps, pricing policy, cost cap and `--allow-bigquery`. `report` accepts
one required primary prediction/execution pair plus zero or more explicitly labeled
replicate pairs for reproducibility. `compare` accepts two evaluation reports.
`validate` performs no mutation.

Exit code 0 means the requested artifact operation completed, including successful
creation of a scientifically blocked diagnostic report. Exit code 1 means internal
or publication failure. Exit code 2 means invalid input, missing live opt-in or
preflight/guard rejection. CLI output is compact JSON; scientific detail resides in
the artifact.

## Artifact layout and publication

Default paths are:

```text
data/eval/framework/canonical/<baseline>/<run-id>/prediction-run.v1.json
data/eval/framework/execution/<baseline>/<run-id>/<execution-id>/execution-journal.v1.jsonl
data/eval/framework/execution/<baseline>/<run-id>/<execution-id>/execution-evidence.v1.json
reports/evaluation/<baseline>/<run-id>/evaluation-report.v1.json
reports/evaluation/comparisons/<left>__<right>/comparison-report.v1.json
```

The execution journal contains a header bound to prediction/policy/executor hashes,
hash-chained dry-run and terminal job records, and a terminal seal. Final execution
evidence binds the terminal journal hash and is published last. An unsealed journal
is forensic evidence only and is rejected by reporting. T5.4-A does not resume it
or automatically repeat submitted jobs.

Writers use a temporary regular file in the destination directory, flush and fsync,
then atomically replace. Inputs and outputs are checked for resolved-path,
symlink/hardlink and protected-input aliases. Published artifacts are immutable. An
existing byte-identical destination is idempotent success; different existing bytes
cause refusal. Multi-file publication writes the terminal report/evidence last and
restores prior accepted outputs on failure where replacement is part of the
operation.

## Testing strategy

Implementation follows test-driven development. All default tests are credential-
and network-free.

Contract tests cover exact field sets, enums, finite values, immutable tuples,
schema versions, hashes and cross-artifact identities. Adapter tests use native B0,
B12 and B45 fixtures and reject tampering, inconsistent provenance and case-set
differences.

SQL tests cover literal-case preservation, keyword/format normalization, aliases,
CTEs, relations, projections, filters, joins, grouping, windows, order and limits.
Result tests cover NULL, numeric types, negative zero, special floats, timestamps,
dates/times, bytes, strings, arrays, structs/JSON, column order, duplicate rows,
sequence and multiset semantics.

Executor contract tests run through the fake adapter and cover full preflight,
immediate second dry-run, per-query/aggregate guards, cache disabling, timeout and
cancellation, prediction failures, gold invalidation and unresolved billing. The
BigQuery adapter uses fake client/job objects to assert configuration and provenance;
CI never contacts Google Cloud.

Metrics tests use hand-computed cases for denominator policies, empty answers,
macro metrics, overlapping categories, missing latency/cost, reproducibility,
deterministic confidence intervals and paired deltas. Failure tests cover multi-tag
classification, `unclassified`, execution-equivalent alternatives and the manual-
only semantic-drift rule.

Artifact tests cover canonical bytes, self/cross-hash tampering, journal chains,
unsealed journals, atomic rollback, symlink/hardlink aliases and idempotent
publication. CLI tests verify root/subcommand help, JSON errors and exit codes;
`execute` without opt-in must fail before client creation, and `report`/`compare`
must never initialize credentials.

One synthetic integration pipeline covers native fixture -> adapter -> canonical
run -> fake execution -> sealed evidence -> report -> paired comparison. Every
fixture carries synthetic/fake blockers and can never be scientific-ready.

## Documentation migration

Rewrite `docs/tasks/phase-5-baselines/04-evaluation-framework.md` to remove
SPARQL/Fuseki execution, lowercasing, set-based duplicate loss, successful-only
denominators, local USD-zero claims, 1,000-sample defaults, placeholder baseline
numbers and claims that T5.4-A performs T5.4-B synthesis. Document the canonical
commands, artifact schemas, execution opt-in and separate implementation/scientific
completion definitions.

README or task command references added by implementation must use the numbered
wrapper and safe offline examples. No documentation may contain fabricated baseline
metrics.

## Acceptance criteria

Implementation is complete only when all of the following are demonstrated:

1. B0, B12 and B45 native fixtures adapt to the same immutable schema, while
   missing/extra/duplicate/tampered evidence fails closed.
2. Exact normalization preserves literal contents and structural signatures use the
   SQLGlot BigQuery AST.
3. Result comparison passes sequence, multiset-with-duplicates and typed nested
   BigQuery value tests.
4. Live adapter construction requires explicit opt-in, dry-run, byte/cost caps and
   timeout before credential or network access.
5. Gold failure invalidates a run; every prediction failure remains in the full
   denominator.
6. Every reported ratio, including exact, structural, execution, macro answer,
   reproducibility, failure and breakdown rates, exposes numerator, denominator,
   value and deterministic 95% CI; reported latency percentiles also expose their
   bootstrap intervals.
7. Paired bootstrap uses identical case indices, 10,000 samples and seed 42 by
   default and reports `left - right` deltas.
8. Latency, inference cost and BigQuery evaluation cost remain separate and expose
   observation coverage; unmeasured local cost is null, not zero.
9. Failure classification is multi-label, contains `unclassified` and never emits
   automatic semantic drift.
10. Reports and comparisons are byte-deterministic for identical verified inputs,
    versioned and hash-bound.
11. Report and comparison commands operate offline, and all unit/integration tests
    use fake executors without credentials or network.
12. Synthetic integration artifacts are implementation-ready but scientific-
    blocked; no genuine baseline result is generated or claimed.
13. The legacy T5.4 task is migrated to NL2SQL/BigQuery and clearly assigns genuine
    runs, synthesis and conclusions to T5.4-B.
14. Focused tests, full pytest, Ruff check, Ruff format check, CLI help and safe
    offline validation pass before completion is claimed.

## Deferred scientific work

After this framework is implementation-complete, T5.4-B may ingest finalized T3.5
and genuine B0-B5 runs, execute them under an approved live policy, generate paired
comparisons and conduct manually reviewed failure analysis. Until those gates pass,
all reports remain scientifically blocked regardless of local framework quality.
