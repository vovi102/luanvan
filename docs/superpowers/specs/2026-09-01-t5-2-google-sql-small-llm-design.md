# T5.2 GoogleSQL Small-LLM Baselines Design

**Date:** 2026-09-01
**Status:** approved by the user on 2026-09-01
**Scope:** migrate B1/B2 from raw NL-to-SPARQL prompting to reproducible,
fail-closed NL-to-GoogleSQL baselines while keeping real Llama inference outside
the local GTX 1650 development gate.

## Context

Pivot #1 made read-only GoogleSQL over the managed BigQuery analytical catalog
the canonical target. The legacy T5.2 task still prompts with an RDF ontology,
extracts SPARQL, and assumes a Kaggle T4 runtime. It must be migrated before
implementation. B1 and B2 remain raw-model baselines: B1 receives only the
question and a compact catalog summary; B2 differs only by adding five training
examples selected by semantic similarity. Neither baseline may call T4.1-T4.3
linking modules or inject their evidence.

The local workstation has a GTX 1650 with 4 GiB VRAM, which is not an accepted
runtime for Llama 3 8B. T5.2 therefore separates locally verifiable baseline
behavior from the external Kaggle inference gate. Local work covers contracts,
catalog summarization, prompts, deterministic retrieval, output extraction,
GoogleSQL safety, artifact publication, CLI behavior, and tests through injected
adapters. It does not download, train, or report measurements from Llama 3 8B.

## Decision

Implement one deep `b12` module with two small public interfaces:

```python
BaselineB1.predict(question: str) -> str | None
BaselineB1.predict_detailed(question: str) -> SmallLLMPrediction

BaselineB2.predict(question: str) -> str | None
BaselineB2.predict_detailed(question: str) -> SmallLLMPrediction
```

`predict` returns one safe GoogleSQL query or `None`. `predict_detailed` always
returns a result that preserves raw generation, extraction status, timings,
token counts, selected example identities, generation configuration, and input
fingerprints. Invalid caller input and corrupt construction artifacts raise a
typed configuration error; an invalid or unsafe model response is a normal
failed prediction and never becomes executable SQL.

The constructor accepts a generation backend. B2 additionally accepts a
retriever built from an immutable training snapshot. These are real internal
seams because production uses Transformers/SentenceTransformers adapters while
tests use deterministic in-memory adapters. The external baseline interface
does not expose tokenizer tensors, device placement, quantization settings,
embedding arrays, prompt formatting, or SQL parser details.

## Module layout

`src/nl2sparql/models/b12/` owns the implementation:

- `contracts.py` defines immutable generation configuration, messages,
  completions, selected examples, predictions, statuses, and fingerprints.
- `catalog_summary.py` compiles and fingerprints a compact prompt summary from
  the accepted analytical catalog.
- `prompts.py` creates B1/B2 chat messages and enforces their only intended
  difference: the B2 examples block.
- `retrieval.py` loads and validates a training snapshot, embeds it once, and
  returns deterministic top-five examples without target leakage.
- `extraction.py` extracts exactly one candidate from raw output and applies the
  existing T3.5 GoogleSQL safety validator.
- `baseline.py` orchestrates prompt construction, generation, extraction,
  latency, and provenance for both baselines.
- `transformers_backend.py` contains lazy production loading for the pinned
  Llama model and is never imported by help, validation, or local fake tests.
- `evaluate.py` validates evaluation input and writes prediction/run evidence;
  aggregate six-dimensional scoring remains T5.4's responsibility.
- `__init__.py` exports only the stable baseline interfaces and result contracts.

The task-named files `src/nl2sparql/models/b1_zero_shot.py` and
`src/nl2sparql/models/b2_few_shot.py` are compatibility imports, not parallel
implementations.

## Catalog summary

The prompt context is generated from the exact bytes of
`src/nl2sparql/sql/catalog/ethereum_analytics.json`. The compiler validates the
catalog through the existing SQL schema contract, then emits a deterministic
summary containing:

- GoogleSQL dialect and half-open evaluation-window convention;
- each managed analytical relation and its parameters;
- relation fields with type and nullability;
- approved join relationships and essential value semantics;
- rules requiring bounded dates, explicit projections, managed relations, and
  read-only output.

The summary is size-bounded by deterministic character/token-estimate limits,
not by silently dropping arbitrary fields. Construction fails if the accepted
catalog cannot fit the documented budget. Its exact catalog SHA-256 and summary
SHA-256 are recorded in every prediction. The model receives no entity aliases,
schema-linker rankings, resolver plans, or live database values.

## Prompt and generation parity

B1 and B2 share one system message and one generation configuration. The system
message asks for one GoogleSQL query only, describes the managed catalog, and
forbids markdown, prose, mutation, wildcard projections, unmanaged relations,
and invented defaults. The user message carries the question.

B2 inserts exactly five retrieved `(question, sql)` examples before the target
question. The examples use stable delimiters and preserve their source SQL
verbatim after safety validation. Apart from this examples block and the
baseline identifier, the prompts and generation settings are identical.

The default production configuration pins:

- model ID `meta-llama/Meta-Llama-3-8B-Instruct`;
- revision supplied explicitly by the run environment and recorded in output;
- seed `42`, greedy decoding, `do_sample=False`, and `max_new_tokens=512`;
- batch size one and a 4-bit `BitsAndBytesConfig` for the Kaggle T4 adapter.

Temperature is omitted for greedy Transformers generation rather than passing a
misleading zero sampling temperature. Model and tokenizer load only when a real
inference command passes all local input preflight checks. T5.2 never trains or
modifies model weights.

## Few-shot retrieval

The B2 retriever reads the exact bytes of an accepted JSONL training artifact.
Every row must have a unique stable ID, non-empty question, one safe GoogleSQL
statement, and provenance marking it as training data rather than T3.5 test
data. Duplicate normalized questions, duplicate IDs, malformed SQL, synthetic
test fixtures presented as production, and train/test snapshot aliasing fail
closed.

The production adapter pins a SentenceTransformers model and revision. It
normalizes embeddings and ranks by cosine similarity. Ordering is deterministic:
descending finite score, then stable training ID. Retrieval always returns five
distinct examples; a smaller pool is invalid. Before ranking, it excludes rows
whose ID or Unicode-normalized question equals the target case. The prediction
records the training-file SHA-256, encoder identity/revision, selected IDs,
scores, and the selected-example content SHA-256. Embedding caches are keyed by
all of that source evidence and are rebuilt or blocked when stale.

This design intentionally uses nearest-neighbor top-five retrieval only. Diverse
retrieval and k-DPP are future ablations, not part of the B2 baseline.

## Generation adapter

The internal generation seam accepts immutable chat messages plus generation
configuration and returns an immutable completion containing raw text, input
and output token counts, model identity/revision, and backend-reported metadata.
The production Transformers adapter applies the tokenizer's chat template,
moves encoded inputs to the loaded model device, runs inference under inference
mode, and decodes only newly generated tokens.

Production construction validates that the completion identity matches the
pinned run configuration. It does not trust an adapter to relabel a different
model. Tests use a scripted adapter through the same seam, allowing every local
behavior to be exercised without network, GPU, Hugging Face authentication, or
fabricated benchmark claims.

## GoogleSQL extraction and safety

Extraction normalizes line endings and removes at most one complete outer
markdown fence. It then considers the remaining text as a whole candidate; it
does not search through prose for a convenient `SELECT` substring or truncate a
second statement. The candidate must pass the T3.5 SQLGlot BigQuery validator:
one read-only query, no comments or semicolons, explicit projections, and only
managed analytical relations. SQL is canonicalized only after validation.

Statuses distinguish at least `ok`, `empty`, `prose`, `invalid_sql`, and
`unsafe_sql`. Raw output is always retained. Any non-`ok` status yields `None`
from the compatibility `predict` method. This fail-closed rule prevents a model
explanation containing an embedded query from being treated as executable.

## Workflow and artifacts

Add numbered wrapper `scripts/17_small_llm_baselines.py` and a separately
importable workflow module. Commands are:

```text
validate     validate catalog, test/train snapshots, config, and output paths
predict      run one B1 or B2 prediction with an explicitly selected backend
evaluate     run one baseline over an accepted evaluation snapshot
```

`--help`, invalid questions, malformed JSONL, output alias checks, and missing
artifact reporting must not initialize Torch, Transformers, SentenceTransformers,
CUDA, or a network client. Real inference requires an explicit opt-in flag and
local model access; missing credentials, model snapshots, finalized T3.5 data,
or compatible hardware produce structured `blocked` output.

Default run artifacts are:

- `data/eval/predictions/b1_test.jsonl` and `b2_test.jsonl`;
- `data/eval/logs/b1_run.jsonl` and `b2_run.jsonl`;
- `reports/b1_inference.json` and `b2_inference.json`.

Each output binds the baseline, case ID, raw and parsed output, extraction
status, prompt/config/catalog/training/model fingerprints, selected examples,
token counts, monotonic latency, run ID, seed, and UTC timestamp. Publication is
atomic, report-last, and refuses aliases with catalog, train/test inputs, model
configuration, locks, caches, predictions, or logs. A failed report write
cannot destroy an already accepted input or prior complete run.

No prediction or latency artifact produced by a fake adapter can be marked
scientifically ready. Fake runs carry an explicit synthetic backend marker.

## Evaluation boundary

T5.2's evaluator validates records, runs inference, and reports operational
counts needed by T5.4:

- total, generated, extraction-success, and extraction-failure counts;
- latency per case plus p50/p95 for the measured backend;
- input/output tokens and retrieval identities;
- deterministic repeated-run equality when matching run evidence is supplied;
- counts by difficulty, category, and extraction status.

It does not infer execution accuracy from text or AST similarity and does not
duplicate T5.4's six-dimensional aggregate framework. Gold SQL is validated and
carried forward for later comparison. Real B1/B2 readiness requires the
finalized independently reviewed T3.5 snapshot and genuine Llama completions.

## Testing

Implementation follows red-green-refactor and tests through the public baseline
interface wherever behavior is observable:

- catalog summary stability, completeness, size bounds, exact-byte fingerprint,
  and corrupt/stale catalog rejection;
- immutable contracts and strict question/config/model provenance validation;
- B1/B2 prompt parity and proof that only B2 contains exactly five examples;
- training JSONL validation, deterministic ranking/ties, normalized embeddings,
  leakage exclusion, insufficient pool, stale cache, and fingerprint binding;
- fenced valid SQL, empty output, prose, multiple statements, comments,
  mutation, wildcard, unmanaged relation, and malformed SQL extraction;
- raw-output retention, token/latency/model metadata, fake-backend marker, and
  `predict` fail-closed behavior;
- preflight ordering, lazy heavy imports, structured blocked states, protected
  paths, atomic publication, and report-last rollback;
- no imports or calls from B1/B2 to T4.1-T4.3 linking modules;
- focused tests, full `python -m pytest`, Ruff lint/format, CLI help, notebook or
  report-reader checks if added, and `git diff --check`.

The repository's direct `pytest` console entry point currently omits the project
root needed by existing `scripts.*` tests. The verified full-suite invocation is
`uv run python -m pytest -q`; changing global import configuration is outside
T5.2 unless implementation introduces a direct need.

## Alternatives rejected

1. **Run or train Llama 3 8B on the local GTX 1650:** the 4 GiB device is not the
   accepted Kaggle T4 environment and cannot support trustworthy latency/OOM
   evidence. T5.2 is inference-only; training belongs to Phase 6.
2. **Keep the legacy SPARQL prompt:** contradicts Pivot #1 and would make B1/B2
   incomparable with the GoogleSQL dataset, B0, and later evaluation.
3. **Inject schema/entity linker output:** may improve accuracy but destroys the
   raw-model control needed to quantify linking contribution.
4. **Use a tiny local model as the scientific substitute:** useful only as a
   development adapter and would not measure the specified Llama 3 8B baseline.
5. **Regex-search for SQL inside arbitrary prose:** increases apparent extraction
   rate by accepting outputs that violate the one-query-only prompt and can hide
   unsafe trailing content.
6. **Commit fake predictions for the missing test set:** would mix workflow
   fixtures with research evidence and could create false readiness.

## Acceptance boundary

T5.2 implementation is locally complete when the migrated task document, deep
B1/B2 module, catalog summary, deterministic retriever, extraction/safety path,
lazy production adapter, offline workflow, artifact contracts, focused tests,
full repository tests, Ruff, CLI checks, and whole-branch review pass.

Scientific acceptance remains pending until all of these external gates exist:

- a finalized independently reviewed T3.5 test set and accepted training pool;
- an accessible pinned Llama 3 8B model snapshot on Kaggle T4;
- B1 and B2 complete genuine prediction runs without OOM;
- measured B1 latency below 5 seconds/query and B2 below 8 seconds/query on T4.

Local fake-adapter results, CPU smoke tests, and AST/text metrics cannot close
those gates.
