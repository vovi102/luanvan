# T5.4-A NL2SQL Evaluation Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a canonical, hash-bound NL2SQL evaluation framework whose guarded
BigQuery execution is explicitly opt-in and whose reports and comparisons are fully
offline and deterministic.

**Architecture:** Baseline-specific adapters convert B0, B1/B2 and B4/B5 artifacts
into one immutable prediction contract. An injected executor produces sealed
execution evidence; pure SQL/result/statistics/failure modules then build reports
without network access. One explicit primary run supplies headline metrics, while
compatible replicate runs supply only reproducibility evidence.

**Tech Stack:** Python 3.11, frozen dataclasses, Click, SQLGlot BigQuery dialect,
google-cloud-bigquery, pytest and Ruff; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-t5-4-a-nl2sql-evaluation-design.md`

## Global Constraints

- Python remains `>=3.11,<3.12`; SQLGlot remains `>=30.17,<31` and
  google-cloud-bigquery remains `>=3.20,<4`.
- Live execution requires `--executor bigquery`, `--allow-bigquery`, explicit
  project/location, timeout, byte caps, pinned pricing policy and estimated USD cap.
- `report`, `compare`, `validate` and CLI help must not import or initialize a
  BigQuery client, credentials or network access.
- Gold execution failure invalidates the whole execution run; prediction failures
  remain false observations in the full `N` denominator.
- Exact/structural match are diagnostics; execution accuracy is the primary metric.
- SQL normalization uses SQLGlot's BigQuery dialect and never lowercases raw SQL or
  string literals.
- Unordered results use multisets that preserve duplicates; gold top-level
  `ORDER BY` selects sequence semantics.
- Inference and BigQuery evaluation costs remain separate; unmeasured local cost is
  null, never inferred USD 0.
- Every reported rate carries numerator, denominator, value and 95% CI. Bootstrap
  defaults are exactly 10,000 samples and seed 42.
- Failure classification is multi-label, includes `unclassified`, and never emits
  automatic `semantic_drift`.
- All artifacts are versioned, canonical UTF-8 JSON/JSONL, hash-bound and immutable.
- Tests and safe validation use synthetic fixtures and fake executors only. This
  plan performs no genuine baseline or live BigQuery run.

## Review Focus

- A native report and prediction file that are each valid but belong to different
  runs must be rejected by the owning adapter; Tasks 7-9 add cross-file identity
  mismatch tests.
- BigQuery's second dry-run may exceed the first estimate or pricing may require
  upward floor/rounding; Task 11 verifies the query is blocked before submission.
- The process may stop after BigQuery accepts a job but before final evidence is
  published; Task 11 verifies the hash-chained journal remains forensic-only and is
  never silently resumed or accepted by reporting.
- BigQuery rows may contain mapping-like Row objects, repeated nested structs,
  special floats and duplicate values; Task 4 pins schema-order and typed recursive
  normalization.
- Replicate input ordering must never change the primary run or headline metrics;
  Task 12 requires an explicit primary identity and rejects incompatible replicates.

---

## File map

Create the framework modules:

- `src/nl2sparql/evaluation/contracts.py` — all immutable public contracts and
  validation.
- `src/nl2sparql/evaluation/artifacts.py` — canonical codecs, strict loaders,
  immutable publication and hash-chained journals.
- `src/nl2sparql/evaluation/sql_semantics.py` — GoogleSQL analysis and signatures.
- `src/nl2sparql/evaluation/result_semantics.py` — typed result canonicalization,
  equality and answer overlap.
- `src/nl2sparql/evaluation/metrics.py` — ratios, latency summaries, bootstrap,
  reproducibility and paired deltas.
- `src/nl2sparql/evaluation/failures.py` — automated and manual failure tags.
- `src/nl2sparql/evaluation/adapters/common.py` — authoritative T3.5 and native
  artifact helpers.
- `src/nl2sparql/evaluation/adapters/b0.py` — B0 adapter.
- `src/nl2sparql/evaluation/adapters/b12.py` — B1/B2 adapter.
- `src/nl2sparql/evaluation/adapters/b45.py` — B4/B5 adapter.
- `src/nl2sparql/evaluation/executor.py` — executor/journal interfaces and scripted
  fake.
- `src/nl2sparql/evaluation/execution.py` — guarded orchestration and evidence
  derivation.
- `src/nl2sparql/evaluation/bigquery.py` — lazy live adapter.
- `src/nl2sparql/evaluation/reporting.py` — offline report and comparison builders.
- `src/nl2sparql/evaluation/cli.py` — Click commands and dependency injection.
- `scripts/19_nl2sql_evaluation.py` — numbered wrapper.

Modify:

- `src/nl2sparql/evaluation/__init__.py` — export the stable high-level interface.
- `docs/tasks/phase-5-baselines/04-evaluation-framework.md` — replace the legacy
  SPARQL/Fuseki task with T5.4-A/T5.4-B NL2SQL scope.
- `README.md` — add safe offline framework commands and live opt-in warning.

Create focused tests under `tests/unit/` named for each framework module plus one
`test_evaluation_pipeline.py` synthetic end-to-end test.

### Task 1: Immutable canonical contracts

**Files:**
- Create: `src/nl2sparql/evaluation/contracts.py`
- Test: `tests/unit/test_evaluation_contracts.py`

**Interfaces:**
- Consumes: no framework code.
- Produces: typed `EvaluationError`, frozen dataclasses `ArtifactRef`,
  `CostEvidence`, `PrivacyEvidence`, `PrivacyReview`,
  `InferenceEvidence`, `PredictionCase`, `RunProvenance`,
  `CanonicalPredictionRun`, `ResultField`, `QueryResultEvidence`,
  `DryRunEvidence`, `QueryExecution`, `ExecutionCaseEvidence`, `PricingPolicy`,
  `ExecutionPolicy`, `ExecutorProvenance`, `ExecutionEvidence`,
  `BootstrapPolicy`, `ConfidenceInterval`, `RatioMetric`, `DistributionMetric`,
  `AnswerScores`, `CaseEvaluation`, `Readiness`, `EvaluationReport`,
  `MetricDelta`, `ComparisonReport` and `ManualFailureReview`.
  `CanonicalArtifact` is the union of the five top-level
  prediction/execution/report/comparison/privacy types.

- [ ] **Step 1: Write failing invariant tests**

Add tests named:

```python
def test_prediction_run_requires_unique_complete_ordered_cases(): ...
def test_non_ok_prediction_cannot_carry_sql(): ...
def test_unmeasured_cost_requires_null_amount_and_observed_zero_is_explicit(): ...
def test_execution_evidence_derives_invalid_status_from_gold_failure(): ...
def test_bootstrap_defaults_are_10000_and_seed_42(): ...
def test_report_primary_run_is_explicit_and_replicates_are_distinct(): ...
```

Assert frozen mutation raises, digests are lowercase 64-hex, all floats are finite,
categories/tags/blockers are sorted unique tuples and enum-like literals reject
unknown values. `PrivacyReview` binds baseline ID, test-set hash, data-egress state,
optional provider and policy hash, reviewer ID, reviewed-at UTC and synthetic state.

- [ ] **Step 2: Run the contract tests and verify red**

Run: `pytest tests/unit/test_evaluation_contracts.py -v`

Expected: collection fails because `nl2sparql.evaluation.contracts` does not exist.

- [ ] **Step 3: Implement the immutable contracts**

Use `@dataclass(frozen=True)` and `Literal` aliases. Keep validation in
`__post_init__`; derived readiness/validity properties must not be caller-settable.
Represent exact money as `Decimal`, durations as finite non-negative `float`, bytes
and counts as non-negative `int`, and optional measurements as explicit status plus
nullable value.

- [ ] **Step 4: Run the contract tests and verify green**

Run: `pytest tests/unit/test_evaluation_contracts.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the contract surface**

```bash
git add src/nl2sparql/evaluation/contracts.py tests/unit/test_evaluation_contracts.py
git commit -m "feat(evaluation): add canonical contracts"
```

### Task 2: Canonical artifact codecs and immutable publication

**Files:**
- Create: `src/nl2sparql/evaluation/artifacts.py`
- Test: `tests/unit/test_evaluation_artifacts.py`

**Interfaces:**
- Consumes: all artifact body dataclasses from Task 1.
- Produces:
  `canonical_json(value: object) -> bytes`,
  `serialize_prediction_run(run: CanonicalPredictionRun) -> bytes`,
  `load_prediction_run(path: Path) -> CanonicalPredictionRun`,
  equivalent `serialize_*`/`load_*` functions for execution evidence, evaluation
  report, comparison report and privacy review,
  `load_and_verify_artifact(path: Path) -> CanonicalArtifact`,
  `publish_immutable(path: Path, payload: bytes, *, protected_paths: Sequence[Path] = ()) -> None`,
  and `HashChainJournal` with `append(record_type: str, body: Mapping[str, object])`
  and `seal(body: Mapping[str, object]) -> str`, plus
  `verify_sealed_journal(path: Path) -> str`.

- [ ] **Step 1: Write failing codec and publication tests**

Cover canonical key ordering/newline, Decimal strings, exact known fields, unknown
schema rejection, self-hash tampering, non-canonical input bytes, protected
symlink/hardlink aliases, byte-identical idempotence, different-content refusal,
record-chain tampering and unsealed-journal rejection. Round-trip a privacy review
and reject a review with a mismatched self-hash.

- [ ] **Step 2: Run the artifact tests and verify red**

Run: `pytest tests/unit/test_evaluation_artifacts.py -v`

Expected: import failure for artifact functions.

- [ ] **Step 3: Implement canonical envelopes and strict typed codecs**

Use schema version 1 and artifact types
`nl2sql_prediction_run`, `nl2sql_execution_evidence`,
`nl2sql_evaluation_report`, `nl2sql_comparison_report` and
`nl2sql_privacy_review`. Hash the envelope without
`artifact_sha256`, compare digests with `hmac.compare_digest`, and reconstruct every
nested tuple/dataclass explicitly rather than accepting arbitrary dictionaries.

- [ ] **Step 4: Implement immutable atomic publication and generic journal chaining**

Write temporary regular files in the destination directory, flush/fsync, reject
aliases and publish with `os.replace`. Journal records include record type, body,
previous digest and current digest; only a verified terminal record is sealed.

- [ ] **Step 5: Run the artifact tests and verify green**

Run: `pytest tests/unit/test_evaluation_artifacts.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit artifact integrity support**

```bash
git add src/nl2sparql/evaluation/artifacts.py tests/unit/test_evaluation_artifacts.py
git commit -m "feat(evaluation): add immutable artifact codecs"
```

### Task 3: GoogleSQL exact and structural semantics

**Files:**
- Create: `src/nl2sparql/evaluation/sql_semantics.py`
- Test: `tests/unit/test_evaluation_sql_semantics.py`

**Interfaces:**
- Consumes: safe SQL strings.
- Produces frozen `SqlAnalysis` and `StructuralFacts`, plus
  `analyze_sql(sql: str) -> SqlAnalysis`,
  `exact_match(predicted_sql: str, gold_sql: str) -> bool` and
  `structural_match(predicted_sql: str, gold_sql: str) -> bool`.

- [ ] **Step 1: Write failing SQL semantics tests**

Assert formatting and keyword-case differences exact-match, string literals with
different case do not match, alias-only differences structural-match, typed literal
differences preserve the same structural signature but different filter facts,
managed CTEs are not relations, and only gold top-level `ORDER BY` selects sequence
semantics. Cover projection, join, aggregation, window, order, limit and offset
facts.

- [ ] **Step 2: Run the SQL tests and verify red**

Run: `pytest tests/unit/test_evaluation_sql_semantics.py -v`

Expected: import failure for `analyze_sql`.

- [ ] **Step 3: Implement SQLGlot BigQuery analysis**

Parse with `parse_one(sql, read="bigquery")`, render with
`.sql(dialect="bigquery", pretty=False)`, and derive deterministic AST payloads.
Replace literals only in structural signatures; retain literals in failure facts.
Raise a typed `EvaluationError` on parse or unsupported query shapes and never use a
regex fallback.

- [ ] **Step 4: Run the SQL tests and verify green**

Run: `pytest tests/unit/test_evaluation_sql_semantics.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit SQL semantics**

```bash
git add src/nl2sparql/evaluation/sql_semantics.py tests/unit/test_evaluation_sql_semantics.py
git commit -m "feat(evaluation): add GoogleSQL comparison semantics"
```

### Task 4: Typed BigQuery result semantics

**Files:**
- Create: `src/nl2sparql/evaluation/result_semantics.py`
- Test: `tests/unit/test_evaluation_result_semantics.py`

**Interfaces:**
- Consumes: Task 1 `ResultField` and raw rows in schema order.
- Produces
  `canonicalize_value(value: object, field: ResultField) -> object`,
  `canonicalize_result(rows: Iterable[object], schema: Sequence[ResultField], *, order_sensitive: bool) -> QueryResultEvidence`,
  `results_equal(gold: QueryResultEvidence, predicted: QueryResultEvidence) -> bool`
  and
  `answer_scores(gold: QueryResultEvidence, predicted: QueryResultEvidence) -> AnswerScores`.

- [ ] **Step 1: Write failing typed-value and row tests**

Cover NULL, bool versus integer, INT64/NUMERIC/BIGNUMERIC/FLOAT64 canonical numeric
equality, negative zero, NaN/infinities, UTC TIMESTAMP, DATE/TIME/DATETIME, bytes,
verbatim strings, arrays, repeated nested structs, JSON field ordering and
mapping-like BigQuery Row values read in schema order.

Add the Review Focus test showing duplicate unordered rows are retained while
ordered row reversal is unequal. Assert aliases do not affect value equality but
arity and tuple position do.

- [ ] **Step 2: Run result tests and verify red**

Run: `pytest tests/unit/test_evaluation_result_semantics.py -v`

Expected: import failure for result semantics.

- [ ] **Step 3: Implement recursive typed normalization and row hashing**

Produce type-tagged canonical JSON values, SHA-256 each row, preserve sequence for
ordered results and sort without deduplication for multisets. Use `Counter` minimum
multiplicity for answer overlap and implement the three explicit empty-result
conventions from the spec.

- [ ] **Step 4: Run result tests and verify green**

Run: `pytest tests/unit/test_evaluation_result_semantics.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit result semantics**

```bash
git add src/nl2sparql/evaluation/result_semantics.py tests/unit/test_evaluation_result_semantics.py
git commit -m "feat(evaluation): add BigQuery result semantics"
```

### Task 5: Metrics, bootstrap and reproducibility primitives

**Files:**
- Create: `src/nl2sparql/evaluation/metrics.py`
- Test: `tests/unit/test_evaluation_metrics.py`

**Interfaces:**
- Consumes: Task 1 metric contracts and per-case numeric observations.
- Produces
  `ratio_metric(scores: Sequence[float], policy: BootstrapPolicy) -> RatioMetric`,
  `distribution_metric(values: Sequence[float | None], expected_count: int, policy: BootstrapPolicy) -> DistributionMetric`,
  `reproducibility_metric(runs: Sequence[CanonicalPredictionRun], *, normalized_sql: bool, policy: BootstrapPolicy) -> RatioMetric`,
  and
  `paired_delta(left: Sequence[float], right: Sequence[float], policy: BootstrapPolicy) -> MetricDelta`.

- [ ] **Step 1: Write failing hand-calculated metric tests**

Assert a score vector `[1, 0, 1, 0]` has numerator 2, denominator 4 and value 0.5;
empty inputs fail; missing latency reports expected/observed/missing counts; P50/P95/
P99 follow the documented interpolated quantile; repeated calls with 10,000/42 are
identical; all-one input yields `[1, 1]`; paired delta uses `left - right` and shared
sample indices.

Add reproducibility tests with three runs: denominator must be
`N * 3`, failures are observable values, and incompatible run/test/config identities
are rejected.

- [ ] **Step 2: Run metric tests and verify red**

Run: `pytest tests/unit/test_evaluation_metrics.py -v`

Expected: import failure for metric functions.

- [ ] **Step 3: Implement pure seeded resampling and quantiles**

Use a local `random.Random(policy.seed)`, resample case indices with replacement and
compute percentile endpoints without NumPy or ambient RNG state. Reject non-finite
inputs and unequal paired lengths.

- [ ] **Step 4: Run metric tests and verify green**

Run: `pytest tests/unit/test_evaluation_metrics.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit metric primitives**

```bash
git add src/nl2sparql/evaluation/metrics.py tests/unit/test_evaluation_metrics.py
git commit -m "feat(evaluation): add deterministic evaluation statistics"
```

### Task 6: Multi-label failure classification

**Files:**
- Create: `src/nl2sparql/evaluation/failures.py`
- Test: `tests/unit/test_evaluation_failures.py`

**Interfaces:**
- Consumes: Task 1 prediction/execution contracts and Task 3 structural facts.
- Produces
  `classify_failure(*, prediction: PredictionCase, gold_execution: QueryExecution, predicted_execution: QueryExecution, execution_match: bool) -> tuple[str, ...]`
  and
  `load_manual_failure_reviews(path: Path) -> tuple[ManualFailureReview, ...]`.

- [ ] **Step 1: Write failing taxonomy tests**

Test every required tag, multi-tag structural cases, operational additions,
successful execution-equivalent alternatives with no tags, `answer_mismatch` plus
`unclassified` when no root cause exists, and strict manual sidecar identity/hash
validation. Assert no automated input can emit `semantic_drift`.

- [ ] **Step 2: Run failure tests and verify red**

Run: `pytest tests/unit/test_evaluation_failures.py -v`

Expected: import failure for `classify_failure`.

- [ ] **Step 3: Implement deterministic classification**

Map terminal statuses first, then compare relations, projections, filters, joins,
aggregation and order/limit facts. Sort and deduplicate tags. Apply manual semantic
drift only after validating its separate artifact and mark its source in the review
contract.

- [ ] **Step 4: Run failure tests and verify green**

Run: `pytest tests/unit/test_evaluation_failures.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit failure classification**

```bash
git add src/nl2sparql/evaluation/failures.py tests/unit/test_evaluation_failures.py
git commit -m "feat(evaluation): add failure taxonomy"
```

### Task 7: Authoritative test-set helpers and B0 adapter

**Files:**
- Create: `src/nl2sparql/evaluation/adapters/__init__.py`
- Create: `src/nl2sparql/evaluation/adapters/common.py`
- Create: `src/nl2sparql/evaluation/adapters/b0.py`
- Test: `tests/unit/test_evaluation_b0_adapter.py`

**Interfaces:**
- Consumes: Task 1 contracts, Task 2 strict JSON helpers, finalized T3.5 loader and
  native B0 predictions/report.
- Produces
  frozen
  `B0AdaptRequest(test_set_path, predictions_path, report_path, run_id, privacy_review_path=None, synthetic=False)`,
  `load_authoritative_test_set(path: Path, *, synthetic: bool) -> AuthoritativeCaseSet`
  and
  `adapt_b0(request: B0AdaptRequest) -> CanonicalPredictionRun`.

- [ ] **Step 1: Write failing B0 adaptation tests**

Build native artifacts with existing B0 publication helpers. Assert authoritative
gold metadata wins, unmatched cases map to `no_output`, local inference cost is
unmeasured, source hashes are retained and existing aggregate B0 rates are not
copied as canonical metrics.

Provide an optional canonical privacy-review artifact. Assert a matching review is
bound to the baseline/test-set identity and a missing review maps to undocumented
privacy rather than a favorable default.

Add Review Focus tests for valid-but-cross-run input hash mismatch, duplicate,
missing and extra prediction IDs, tampered report hash and B0 output alias safety.

- [ ] **Step 2: Run B0 adapter tests and verify red**

Run: `pytest tests/unit/test_evaluation_b0_adapter.py -v`

Expected: import failure for `adapt_b0`.

- [ ] **Step 3: Implement common authoritative loading and B0 conversion**

Read exact source bytes once, verify finalized provenance through existing loaders,
join by exact case ID while preserving T3.5 order, and create deterministic source
artifact references. Require explicit B0 `run_id` because the native report lacks
one; do not invent a generation timestamp or privacy claim. Validate an optional
`privacy_review_path` through Task 2 and require its baseline/test-set identity to
match.

- [ ] **Step 4: Run B0 adapter tests and verify green**

Run: `pytest tests/unit/test_evaluation_b0_adapter.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the B0 adapter**

```bash
git add src/nl2sparql/evaluation/adapters tests/unit/test_evaluation_b0_adapter.py
git commit -m "feat(evaluation): adapt B0 evidence"
```

### Task 8: B1/B2 adapter

**Files:**
- Create: `src/nl2sparql/evaluation/adapters/b12.py`
- Test: `tests/unit/test_evaluation_b12_adapter.py`

**Interfaces:**
- Consumes: Task 7 authoritative case set and native B12 prediction/log/report
  artifacts.
- Produces
  frozen
  `B12AdaptRequest(test_set_path, predictions_path, log_path, report_path, privacy_review_path=None, synthetic=False)`
  and
  `adapt_b12(request: B12AdaptRequest) -> CanonicalPredictionRun`.

- [ ] **Step 1: Write failing B12 adapter tests**

Generate native artifacts through `publish_evaluation_run`. Assert extraction
statuses, raw-output hash, latency/tokens, model/config/catalog/training/selected-
example provenance, synthetic marker and unmeasured inference cost map correctly.
Assert an optional canonical privacy review is identity-bound; absence remains
`undocumented`.

Add Review Focus cross-file tests for different run IDs, seeds, input hashes,
selected-example hashes, model revisions and case ordering; individually valid files
from different runs must fail.

- [ ] **Step 2: Run B12 adapter tests and verify red**

Run: `pytest tests/unit/test_evaluation_b12_adapter.py -v`

Expected: import failure for `adapt_b12`.

- [ ] **Step 3: Implement strict B1/B2 cross-artifact conversion**

Verify native report self-hash, exact case coverage and identity consistency before
constructing a run. Map native `empty`, `prose`, `invalid_sql` and `unsafe_sql`
statuses without treating them as absent records.

- [ ] **Step 4: Run B12 adapter tests and verify green**

Run: `pytest tests/unit/test_evaluation_b12_adapter.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the B12 adapter**

```bash
git add src/nl2sparql/evaluation/adapters/b12.py tests/unit/test_evaluation_b12_adapter.py
git commit -m "feat(evaluation): adapt B1 and B2 evidence"
```

### Task 9: B4/B5 adapter

**Files:**
- Create: `src/nl2sparql/evaluation/adapters/b45.py`
- Test: `tests/unit/test_evaluation_b45_adapter.py`

**Interfaces:**
- Consumes: Task 7 authoritative cases and existing
  `load_large_run_artifacts(report_path, request_log_path)`.
- Produces
  frozen
  `B45AdaptRequest(test_set_path, report_path, request_log_path, synthetic=False)`
  and
  `adapt_b45(request: B45AdaptRequest) -> CanonicalPredictionRun`.

- [ ] **Step 1: Write failing B45 adapter tests**

Use the existing B45 artifact builders. Assert completed/extraction/request/budget/
unresolved statuses, authoritative Decimal inference charges, provider/model/prompt/
privacy/attempt provenance and B5 training/retrieval hashes map without loss.

Add Review Focus tests for valid artifacts paired with another T3.5 snapshot,
tampered journal terminal, report/journal run mismatch, unresolved cost and missing
privacy review.

- [ ] **Step 2: Run B45 adapter tests and verify red**

Run: `pytest tests/unit/test_evaluation_b45_adapter.py -v`

Expected: import failure for `adapt_b45`.

- [ ] **Step 3: Implement conversion through the native verified loader**

Do not reimplement B45's hash-chain validator. Convert only the validated
`LargeEvaluationRun`, retain every source artifact hash and keep provider inference
charge separate from future BigQuery evaluation cost.

- [ ] **Step 4: Run B45 adapter tests and verify green**

Run: `pytest tests/unit/test_evaluation_b45_adapter.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the B45 adapter**

```bash
git add src/nl2sparql/evaluation/adapters/b45.py tests/unit/test_evaluation_b45_adapter.py
git commit -m "feat(evaluation): adapt B4 and B5 evidence"
```

### Task 10: Executor seam, scripted fake and guarded orchestration

**Files:**
- Create: `src/nl2sparql/evaluation/executor.py`
- Create: `src/nl2sparql/evaluation/execution.py`
- Test: `tests/unit/test_evaluation_execution.py`

**Interfaces:**
- Consumes: Task 1 execution contracts, Task 3 analysis and Task 4 results.
- Produces `QueryRequest`, protocol methods
  `QueryExecutor.dry_run(request: QueryRequest, policy: ExecutionPolicy) -> DryRunEvidence`
  and
  `QueryExecutor.execute(request: QueryRequest, policy: ExecutionPolicy, preflight: DryRunEvidence) -> QueryExecution`,
  `ExecutionJournal.append(record_type: str, body: Mapping[str, object]) -> None`,
  `ExecutionJournal.seal(body: Mapping[str, object]) -> str`,
  `ScriptedQueryExecutor`, `MemoryExecutionJournal`, and
  `execute_run(run: CanonicalPredictionRun, *, execution_id: str, policy: ExecutionPolicy, executor: QueryExecutor, journal: ExecutionJournal) -> ExecutionEvidence`.

- [ ] **Step 1: Write failing orchestration tests**

Assert all gold dry-runs precede live jobs, all prediction dry-runs precede live
jobs, each live query receives an immediate second preflight, execution is sequential
gold-then-prediction by case, non-executable predictions receive explicit skipped
outcomes, and journal append occurs before the next query.

Assert gold static/dry-run/live/result failure returns invalid evidence with null
execution metrics later, while prediction guard/timeout/error remains a terminal
false observation. Verify aggregate estimate guards and executor provenance binding.

- [ ] **Step 2: Run execution tests and verify red**

Run: `pytest tests/unit/test_evaluation_execution.py -v`

Expected: import failure for executor/orchestration modules.

- [ ] **Step 3: Implement the protocols and configurable fake**

The fake accepts per-query scripted dry-run and execution outcomes, records call
order, never imports Google Cloud and marks provenance `fake`. The memory journal
uses the same record shape as the durable journal.

- [ ] **Step 4: Implement `execute_run` with fail-closed guards**

Revalidate every SQL through the existing managed-relation safety validator and Task
3 analysis. Derive all status/validity fields; do not accept caller-provided ready
booleans. Keep every canonical case in output even when live submission stops.

- [ ] **Step 5: Run execution tests and verify green**

Run: `pytest tests/unit/test_evaluation_execution.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit execution core**

```bash
git add src/nl2sparql/evaluation/executor.py src/nl2sparql/evaluation/execution.py tests/unit/test_evaluation_execution.py
git commit -m "feat(evaluation): orchestrate guarded query execution"
```

### Task 11: Lazy BigQuery adapter and durable execution journal

**Files:**
- Create: `src/nl2sparql/evaluation/bigquery.py`
- Modify: `src/nl2sparql/evaluation/artifacts.py`
- Test: `tests/unit/test_evaluation_bigquery.py`
- Test: `tests/unit/test_evaluation_execution_journal.py`

**Interfaces:**
- Consumes: Task 10 executor/journal protocols and Task 2 hash chaining.
- Produces
  `create_bigquery_executor(policy: ExecutionPolicy, *, allow_bigquery: bool, client_factory: Callable[[], object] | None = None) -> QueryExecutor`,
  `BigQueryExecutor`, and
  `FileExecutionJournal.create(path: Path, *, header: Mapping[str, object], protected_paths: Sequence[Path]) -> FileExecutionJournal`.

- [ ] **Step 1: Write failing lazy-import and job-config tests**

Monkeypatch the client factory and assert missing opt-in or incomplete policy raises
before it is called. With fake client/job objects, assert BigQuery dialect,
`use_legacy_sql=False`, `use_query_cache=False`, `dry_run` mode,
`maximum_bytes_billed`, location, timeout, job ID, cache status and bytes are
captured.

- [ ] **Step 2: Write failing pricing-drift, timeout and journal tests**

Add the Review Focus tests: conservative floor/rounding is upward; a larger immediate
dry-run blocks before live submit; timeout requests cancellation and never invents
zero billing; process interruption after a submitted record leaves an unsealed
journal that strict loaders reject and never resume. Test terminal journal/evidence
cross-hash and tamper detection.

- [ ] **Step 3: Run BigQuery/journal tests and verify red**

Run:
`pytest tests/unit/test_evaluation_bigquery.py tests/unit/test_evaluation_execution_journal.py -v`

Expected: import failure for live adapter and file journal.

- [ ] **Step 4: Implement lazy BigQuery construction and adapter methods**

Import `google.cloud.bigquery` inside the factory/adapter construction path only.
Convert schema recursively to `ResultField`; canonicalize rows through Task 4.
Use `job.result(timeout=...)`, request cancellation on timeout and read statistics
when available. Label billed-byte-derived USD as estimated, not observed charge.

- [ ] **Step 5: Implement append/fsync journal and final evidence binding**

Lock the destination, append one canonical hash-chained JSONL record at a time,
flush/fsync before returning, and seal with a terminal record. Do not add a resume
entry point. Publish execution evidence only after terminal verification.

- [ ] **Step 6: Run BigQuery/journal tests and verify green**

Run:
`pytest tests/unit/test_evaluation_bigquery.py tests/unit/test_evaluation_execution_journal.py -v`

Expected: all tests pass with no network or credentials.

- [ ] **Step 7: Commit live adapter and durable evidence**

```bash
git add src/nl2sparql/evaluation/bigquery.py src/nl2sparql/evaluation/artifacts.py tests/unit/test_evaluation_bigquery.py tests/unit/test_evaluation_execution_journal.py
git commit -m "feat(evaluation): add guarded BigQuery evidence adapter"
```

### Task 12: Offline report and paired comparison builders

**Files:**
- Create: `src/nl2sparql/evaluation/reporting.py`
- Test: `tests/unit/test_evaluation_reporting.py`

**Interfaces:**
- Consumes: verified primary prediction/execution pair, zero or more verified
  replicate pairs, Tasks 3-6 semantics, and Task 2 hashes.
- Produces
  `build_report(*, primary_run: CanonicalPredictionRun, primary_evidence: ExecutionEvidence, replicate_pairs: Sequence[tuple[CanonicalPredictionRun, ExecutionEvidence]] = (), bootstrap_policy: BootstrapPolicy = BootstrapPolicy(), manual_reviews: Sequence[ManualFailureReview] = ()) -> EvaluationReport`
  and
  `compare_reports(left: EvaluationReport, right: EvaluationReport, *, bootstrap_policy: BootstrapPolicy = BootstrapPolicy()) -> ComparisonReport`.

- [ ] **Step 1: Write failing primary metric and denominator tests**

Use four synthetic cases to assert exact/structural/execution and macro answer
numerators, full `N` denominators, CI fields, latency missing counts, separate costs,
privacy evidence, multi-label failure rates and overlapping difficulty/category
breakdowns. Assert any gold failure makes execution/answer numerator and value null
without dropping IDs.

- [ ] **Step 2: Write failing readiness, replicate and comparison tests**

Add the Review Focus test proving replicate ordering cannot select/change the
explicit primary or its headline metrics. Reject mismatched baseline, test hash,
config/model identity, case IDs and execution bindings. Assert two runs compute but
scientific readiness still requires three genuine runs. Assert fake/synthetic/
missing privacy/unresolved cost blockers are sorted and derived.

For comparison, require identical test/case identities, use per-case paired samples,
report `left - right`, inherit blockers and never emit winner/ranking fields. Pin
paired deltas for exact, structural, execution, answer precision/recall/F1 and every
latency/cost measure with complete comparable per-case observations; incomplete
latency/cost measures remain explicitly unavailable rather than dropping cases.

- [ ] **Step 3: Run reporting tests and verify red**

Run: `pytest tests/unit/test_evaluation_reporting.py -v`

Expected: import failure for report builders.

- [ ] **Step 4: Implement deterministic primary report derivation**

Compute SQL and result comparisons from evidence only. Never call an executor or
read current time. Build compact per-case records first, then derive every aggregate,
breakdown, failure rate, reproducibility result and readiness state from them.

- [ ] **Step 5: Implement paired report comparison**

Verify input report hashes/identity, align by exact case ID and call Task 5 paired
delta for each supported case-level metric. Diagnostic blocked comparisons remain
valid artifacts but cannot be scientific-ready.

- [ ] **Step 6: Run reporting tests and verify green**

Run: `pytest tests/unit/test_evaluation_reporting.py -v`

Expected: all tests pass.

- [ ] **Step 7: Commit reporting and comparison**

```bash
git add src/nl2sparql/evaluation/reporting.py tests/unit/test_evaluation_reporting.py
git commit -m "feat(evaluation): build deterministic evaluation reports"
```

### Task 13: Public exports, CLI and synthetic end-to-end pipeline

**Files:**
- Create: `src/nl2sparql/evaluation/cli.py`
- Modify: `src/nl2sparql/evaluation/__init__.py`
- Create: `scripts/19_nl2sql_evaluation.py`
- Test: `tests/unit/test_evaluation_cli.py`
- Test: `tests/unit/test_evaluation_pipeline.py`

**Interfaces:**
- Consumes: all high-level interfaces from Tasks 2 and 7-12.
- Produces
  `create_cli(*, bigquery_executor_factory: Callable[..., QueryExecutor] = create_bigquery_executor) -> click.Group`
  and public
  `adapt_baseline_artifacts(request: B0AdaptRequest | B12AdaptRequest | B45AdaptRequest) -> CanonicalPredictionRun`,
  plus exports `execute_run`, `build_report`, `compare_reports` and
  `load_and_verify_artifact`.

- [ ] **Step 1: Write failing CLI help and safe-default tests**

Use `CliRunner` to test root and `adapt b0|b12|b45`, `execute`, `report`, `compare`,
`validate` help. Assert help and offline commands do not call the injected BigQuery
factory. Assert `execute` missing `--allow-bigquery`, project, location, timeout,
caps or pricing exits 2 before factory access and emits stable JSON.

- [ ] **Step 2: Write the failing synthetic pipeline test**

Run native fixture -> adapter -> serialize/load canonical run -> scripted fake
execution with memory/file journal -> serialize/load evidence -> offline report ->
second synthetic report -> paired comparison. Assert repeated report/comparison
bytes are identical and all artifacts are implementation-ready but carry synthetic/
fake scientific blockers.

- [ ] **Step 3: Run CLI/pipeline tests and verify red**

Run:
`pytest tests/unit/test_evaluation_cli.py tests/unit/test_evaluation_pipeline.py -v`

Expected: import failure for CLI/public facade.

- [ ] **Step 4: Implement thin commands and numbered wrapper**

Commands load and verify all inputs before mutation, protect input paths, publish
reports/evidence last and emit compact JSON status. `report` takes one explicit
primary pair and repeated explicit replicate pairs. B0/B12 adaptation accepts an
optional `--privacy-review` canonical artifact, and `report` accepts an optional
hash-bound `--manual-failure-reviews` sidecar. Keep live imports behind the injected
factory.

- [ ] **Step 5: Export only the stable facade and run tests**

Run:
`pytest tests/unit/test_evaluation_cli.py tests/unit/test_evaluation_pipeline.py -v`

Expected: all tests pass with no network or credentials.

- [ ] **Step 6: Verify CLI help and offline validation manually**

Run:

```bash
python scripts/19_nl2sql_evaluation.py --help
python scripts/19_nl2sql_evaluation.py execute --help
python scripts/19_nl2sql_evaluation.py report --help
```

Expected: exit 0 and no credential/client initialization.

- [ ] **Step 7: Commit CLI and integrated offline workflow**

```bash
git add src/nl2sparql/evaluation/cli.py src/nl2sparql/evaluation/__init__.py scripts/19_nl2sql_evaluation.py tests/unit/test_evaluation_cli.py tests/unit/test_evaluation_pipeline.py
git commit -m "feat(evaluation): add offline-first evaluation CLI"
```

### Task 14: Migrate T5.4 documentation and run completion gates

**Files:**
- Modify: `docs/tasks/phase-5-baselines/04-evaluation-framework.md`
- Modify: `README.md`
- Test: all evaluation tests and repository quality gates.

**Interfaces:**
- Consumes: implemented CLI and the approved design/spec terminology.
- Produces: canonical NL2SQL T5.4-A task documentation, safe commands and final
  implementation verification evidence; no scientific results.

- [ ] **Step 1: Write the documentation assertions before editing docs**

Create `tests/unit/test_evaluation_docs.py` to assert the T5.4 task names GoogleSQL,
BigQuery, explicit opt-in, 10,000/42 bootstrap, full-denominator failures,
implementation versus scientific completion and T5.4-B ownership. Assert it does
not prescribe SPARQL/Fuseki execution, local USD 0 or placeholder result tables.

- [ ] **Step 2: Run documentation tests and verify red**

Run: `pytest tests/unit/test_evaluation_docs.py -v`

Expected: FAIL because the legacy task still requires SPARQL/Fuseki.

- [ ] **Step 3: Rewrite the task and add README safe commands**

Replace the legacy body rather than layering corrections onto it. Include artifact
roles, command examples, no-network defaults, explicit live warning, denominator/
cost/privacy/readiness policy, acceptance criteria and the T5.4-A/T5.4-B boundary.
Do not include baseline values or conclusions.

- [ ] **Step 4: Run focused evaluation tests**

Run: `pytest tests/unit/test_evaluation_*.py -v`

Expected: all focused tests pass.

- [ ] **Step 5: Run the full repository test suite**

Run: `pytest`

Expected: all tests pass with no live network or credentials.

- [ ] **Step 6: Run lint, format and whitespace gates**

Run:

```bash
ruff check .
ruff format --check .
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 7: Run CLI and safe offline validation gates**

Run root/subcommand help plus the synthetic pipeline test. Do not invoke
`--allow-bigquery` and do not create a genuine evaluation artifact.

Expected: help exits 0; synthetic pipeline passes and remains scientific-blocked.

- [ ] **Step 8: Commit documentation and final verification changes**

```bash
git add docs/tasks/phase-5-baselines/04-evaluation-framework.md README.md tests/unit/test_evaluation_docs.py
git commit -m "docs(evaluation): migrate T5.4 to NL2SQL"
```

After this commit, report **implementation complete** only if every gate above has
fresh passing output. Report **scientific complete: no** with blockers for finalized
T3.5, genuine baseline runs and live execution evidence as applicable.
