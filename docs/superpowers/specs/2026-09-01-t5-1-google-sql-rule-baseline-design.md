# T5.1 GoogleSQL Rule-Based Baseline Design

**Date:** 2026-09-01
**Status:** approved by the user on 2026-09-01
**Scope:** migrate B0 from SPARQL template filling to a deterministic,
provenance-bound GoogleSQL baseline over the accepted template library and
T4.1-T4.3 linking modules.

## Context

Pivot #1 made read-only GoogleSQL over the BigQuery analytical catalog the
canonical runtime. The legacy T5.1 task still asks B0 to emit SPARQL and assumes
that broad regular expressions can safely fill entity slots. That contract is
incompatible with the 25 accepted GoogleSQL templates, typed slot validation,
managed-relation allowlist, and fail-closed ambiguity behavior implemented by
T3.1 and T4.1-T4.3.

B0 remains the non-LLM lower bound. It must measure how far deterministic
template matching can go without silently turning uncertain language into an
executable query. Its implementation, structural evaluation, coverage, and warm
latency checks can run locally. Scientific execution accuracy still requires the
independently reviewed T3.5 benchmark, its live evidence, BigQuery credentials,
and an explicit cost budget.

## Decision

Implement a deep `BaselineB0` module whose compatibility operation is:

```python
BaselineB0.predict(nl: str) -> str | None
```

`predict` returns one validated GoogleSQL statement or `None` when no single
safe template and complete slot assignment can be established. It delegates to:

```python
BaselineB0.predict_detailed(nl: str) -> B0Prediction | None
```

The detailed result exists for evaluation and provenance. It includes the SQL,
template identity, match mode, score, typed slot values, linker fingerprints,
and deterministic warnings. Callers never supply regexes, scoring weights, slot
validators, SQL fragments, or catalog rules per call.

Construction accepts a validated template snapshot plus the existing schema
linker, entity linker, and class resolver. Dependencies are injected so tests
can use deterministic in-memory adapters and production can load the accepted
cached indexes. There is no separate generic plugin interface: the three
existing linker interfaces are the real seams that already vary between
production and test implementations.

## Module layout

`src/nl2sparql/models/b0/` owns the implementation:

- `contracts.py` defines immutable predictions, match metadata, policy, typed
  failures, and snapshot fingerprints.
- `templates.py` validates and compiles the T3.1 template snapshot into immutable
  patterns and structural anchors.
- `slots.py` extracts and assigns typed values without rendering SQL.
- `baseline.py` orchestrates matching, linker evidence, fail-closed selection,
  rendering, and final safety validation.
- `evaluate.py` validates local evaluation JSONL and computes deterministic
  coverage, structural correctness, exact-match accuracy, and latency evidence.
- `__init__.py` exports only the stable interface and result contracts.

`src/nl2sparql/models/b0_rule_based.py` remains a thin compatibility import for
the deliverable named by the task. Workflow and notebook code call the package
interface rather than private helpers.

## Template compilation and matching

At construction, B0 loads the exact bytes of `templates.json`, validates the
whole library with the existing T3.1 validator, and records its SHA-256. Each
`nl_seed` is compiled once. Literal text is Unicode-normalized, case-folded,
whitespace-tolerant, and regex-escaped; placeholders become named groups whose
patterns are selected only from the declared slot type. Templates are ordered
by descending literal specificity and then stable template ID.

Prediction uses two stages:

1. **Seed match.** A full seed-shaped match extracts candidate slots. Successful
   typed validation receives score `1.0`.
2. **Structural fallback.** If no seed match succeeds, normalize the question,
   mask recognized typed spans, and compare its remaining tokens with each
   template's literal anchors. Score is token F1, not raw substring or edit
   distance, so repeated question tokens and short templates are not
   over-rewarded. Candidates below policy threshold are rejected.

Structural candidates must still produce every declared slot through typed
extraction and linking. A top-score tie inside the configured ambiguity margin
returns `None` unless T4.1 evidence uniquely selects one candidate by overlap
with that template's declared `schema_elements`. A remaining tie fails closed;
template file order is never semantic authority.

The default policy is immutable and fingerprinted. It contains only the
structural threshold and ambiguity margin. Test fixtures can provide a different
validated policy explicitly; reports record the effective values.

## Typed slot extraction

Slot extraction is candidate-specific and returns Python values accepted by the
existing T3.1 `render_template` function:

- `date` accepts strict ISO `YYYY-MM-DD` values and preserves source order;
- `ethereum_address` and `transaction_hash` accept canonical hexadecimal forms;
- `integer`, `block_number`, `duration_minutes`, and `decimal_wei` use bounded
  numeric parsing and template metadata;
- `token_symbol` accepts a bounded alphanumeric symbol and uses entity evidence
  when the symbol identifies a known token;
- `concept_class` is filled only from a T4.3 concept resolution with supported
  coverage and a resolved plan;
- future accepted `entity_owner` and `entity_category` slots must resolve through
  the same T4.2/T4.3 evidence rather than accepting arbitrary captured text.

Repeated slot types are assigned by named seed groups when available. In the
structural fallback, values are assigned in source order only when that order is
unambiguous for the template. For example, two dates map to `start_date` then
`end_date`, and two account mentions map to `account` then `account_b`. Missing,
extra, overlapping, out-of-range, or multiply assignable values reject the
candidate. Defaults are not invented by B0.

An owner mention may satisfy an `ethereum_address` slot only when T4.2 resolves
one target and T4.3 returns one supported instance constraint. Multiple verified
addresses are ambiguous for a scalar template slot and reject the candidate.
Raw addresses remain valid through T4.2's self-authenticating address evidence.

## Linker use and provenance

T4.1 ranks schema relations and fields for the whole question. Its evidence is
used only to break an otherwise unresolved structural template tie; it cannot
authorize a template or catalog element absent from the validated library.

T4.2 recognizes entity spans. T4.3 converts those matches into catalog-backed
instance or concept constraints. B0 consumes only resolved, supported
constraints. Partial/unresolved plans, ambiguity warnings, coverage gaps, stale
fingerprints, and direction conflicts cannot be rendered as successful
predictions.

`B0Prediction` records the template snapshot digest, policy digest, catalog and
dictionary fingerprints exposed by resolution evidence, and the chosen
template's schema/CQ annotations. Prediction artifacts therefore identify the
exact local semantics that produced them without persisting model embeddings.

## Rendering and SQL safety

B0 never formats captured text directly into SQL. The final complete slot map is
passed to T3.1 `render_template`, which applies type checks, escaping, numeric
bounds, and date-window validation. The rendered statement then passes the T3.5
SQLGlot BigQuery safety validator, which requires one read-only query, explicit
projections, and managed analytical relations only.

Any template-validation, linker, resolver, rendering, or SQL-safety failure is
converted into a deterministic rejected candidate. Invalid public input or a
corrupt construction artifact raises `B0Error`; ordinary lack of coverage,
ambiguity, or incomplete slots returns `None`.

## Offline workflow and artifacts

Add numbered wrapper `scripts/16_b0_rule_baseline.py` and implementation workflow
`scripts/b0_rule_baseline_workflow.py` with commands:

```text
predict    emit one canonical JSON prediction or an explicit unmatched result
evaluate   validate reviewed local JSONL, write predictions, and publish a report
```

`--help` and input validation do not initialize encoders or access the network.
Production prediction/evaluation may load only the already accepted local
schema/entity index snapshots. Missing models, indexes, T3.5 data, or other
external evidence produce machine-readable `blocked` output rather than a false
passing report. Report and prediction publication is atomic and refuses aliases
to protected inputs.

Default outputs are:

- `data/eval/predictions/b0_test.jsonl` for per-case predictions;
- `reports/b0_evaluation.json` for aggregate evidence;
- `notebooks/13_b0_eval.ipynb` as a lightweight reproducible reader of the
  report, not an alternative implementation.

No fabricated benchmark rows are committed. Unit fixtures exercise the full
local workflow but are clearly synthetic and cannot satisfy scientific gates.

## Evaluation contract

The evaluator consumes finalized T3.5-style records with stable ID, NL question,
gold GoogleSQL, and live-evidence fields. It refuses duplicate IDs, unverified
scientific rows, unsafe gold SQL, or malformed provenance. A separate explicitly
synthetic mode is allowed for tests and never reports scientific readiness.

Metrics are:

- `coverage`: non-`None` predictions divided by all accepted cases;
- `exact_match_accuracy`: canonical SQL equality over matched cases;
- `structural_accuracy`: SQLGlot AST equivalence after BigQuery parsing over
  matched cases;
- warm `p50` and `p95` prediction latency measured with a monotonic clock;
- counts by match mode, template, difficulty, and rejection reason.

Execution accuracy is not inferred from SQL text. When valid BigQuery execution
evidence for both gold and prediction is unavailable, the report sets execution
accuracy to `null` and scientific status to `not_ready`. A future evaluation
adapter may compare result semantics under the Phase 5 evaluation framework;
T5.1 does not duplicate BigQuery execution logic.

Local implementation readiness requires all of the following on an explicitly
reviewed local artifact: coverage at least `0.40`, structural accuracy at least
`0.60` among matched cases, and warm p95 below `100 ms`. Scientific readiness
additionally requires execution accuracy at least `0.60` on the finalized T3.5
benchmark. Synthetic fixtures never set either readiness flag.

## Testing

Test-first coverage crosses the public baseline interface:

- compilation of all accepted slot types, escaped literals, Unicode/case/space
  normalization, and stable specificity ordering;
- exact seed matches for representative easy, medium, and hard templates;
- structural fallback scoring, schema-evidence tie breaking, threshold rejection,
  and unresolved ties;
- named groups, repeated dates/accounts, bounds, malformed hashes/addresses,
  scalar owner resolution, concept coverage, and incomplete slot rejection;
- partial or stale T4.2/T4.3 evidence and invalid T4.1 identities fail closed;
- rendering escapes text and rejects unsafe, multi-statement, mutation, wildcard,
  and unmanaged-relation SQL;
- immutable predictions, stable fingerprints, deterministic warnings, and the
  compatibility `predict` result;
- evaluation arithmetic, SQL canonicalization, duplicate/malformed JSONL,
  synthetic versus scientific readiness, latency quantiles, atomic publication,
  and protected-path behavior;
- CLI help and unmatched behavior remain offline;
- full pytest, Ruff lint/format, notebook JSON, and `git diff --check` pass.

## Alternatives rejected

1. **Regex-only filling from arbitrary text:** small implementation, but broad
   entity patterns bypass T4.2/T4.3 provenance and can inject the wrong scalar
   into an otherwise valid SQL template.
2. **Always select the highest fuzzy score:** improves apparent coverage by
   converting close ties into guesses. That contaminates the lower-bound result
   and conflicts with the project's fail-closed ambiguity policy.
3. **Let B0 construct SQL directly from resolver fields:** duplicates catalog
   joins and quoting already encoded by T3.1 templates. It also turns B0 into a
   second query generator instead of a template baseline.
4. **Run BigQuery inside `predict`:** couples inference latency to network and
   billing, makes the interface shallow, and prevents credential-free tests.
5. **Claim execution accuracy from AST equality:** structurally similar SQL can
   return different results, while equivalent results can come from different
   ASTs. The two metrics remain separate.

## Acceptance boundary

T5.1 implementation is locally complete when the migrated task, B0 module,
offline workflow, prediction/report contracts, notebook, focused tests, full
repository tests, Ruff, and diff checks pass. Coverage, structural accuracy, and
latency gates may be closed only against an explicitly reviewed local artifact.
Execution accuracy `>= 0.60` and final scientific readiness remain pending until
the finalized T3.5 benchmark and valid BigQuery result evidence are available.
