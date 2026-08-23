# T4.1 GoogleSQL Schema Linker Design

**Date:** 2026-08-15  
**Status:** approved under the user's standing self-approval delegation  
**Scope:** migrate T4.1 from ontology-property ranking to Plan B analytical
relation/field ranking without fabricating manual evaluation evidence.

## Context

T4.1 still describes EthOn properties, classes, and SPARQL prompt injection. Pivot
#1 made GoogleSQL over the accepted BigQuery analytical layer canonical. The
machine-readable catalog now contains six analytical relations, their fields,
lineage, semantic mappings, competency coverage, and safety contracts. The linker
must rank this catalog rather than revive the stopped Fuseki path.

The scientific purpose remains unchanged: quantify how much explicit schema
linking helps a small generator. In Plan B, ontology classes map to analytical
relations and ontology properties map to `relation.field` elements.

## Decision

Use hybrid lexical and sentence-embedding retrieval over deterministic catalog
documents. Lexical evidence protects exact blockchain/SQL role distinctions;
MiniLM handles natural paraphrases. Do not fine-tune an encoder in T4.1 and do not
silently fall back to fabricated embeddings when the production model is absent.

The public interface is typed:

```python
SchemaLinker.link(question: str, top_k: int | None = 10) -> LinkResult

LinkResult.relations: tuple[SchemaMatch, ...]
LinkResult.fields: tuple[SchemaMatch, ...]
```

`SchemaMatch` binds `element_id`, `kind`, total score, lexical score, semantic
score, and the document fingerprint. Relation and field rankings are separate so
downstream prompting cannot accidentally compare scores from different pools.
Scores are descending with stable element-ID tie-breaking.

## Catalog documents

The linker loads the validated catalog through `nl2sparql.sql.schema.load_catalog`
and builds one document per analytical relation plus one per analytical field.
Documents contain only committed catalog evidence:

- snake-case-split relation and field names;
- relation kind, parameters, primary key, and physical sources;
- field type, mode, lineage, and expression when present;
- semantic IDs whose targets reference the element;
- competency-question ID/status that references the element;
- a versioned, reviewed synonym lexicon for role and measure terms such as
  sender/from, recipient/to, value/amount, failed/status, gas/fee, token, block,
  contract, label, exchange, and protocol.

Document construction is deterministic. Empty relation/field collections,
unknown catalog references, duplicate IDs, or malformed synonym entries fail
before model initialization.

## Retrieval

The default encoder is
`sentence-transformers/all-MiniLM-L6-v2`. An `Encoder` protocol is injected into
the linker and index builder so unit tests use a deterministic fake without model
downloads, credentials, GPU, or network access.

Both document and question vectors are L2-normalized. Semantic score is cosine
similarity. Lexical score is a deterministic weighted overlap over normalized
tokens and reviewed synonyms; exact multi-token phrase matches receive the
highest lexical weight. The default total is:

```text
0.65 * semantic_score + 0.35 * lexical_score
```

Weights are immutable index metadata and validated to be finite, non-negative,
and sum to one. A caller may request `top_k` from 1 through the pool size; zero,
negative, boolean, oversized, empty, control-character, or non-string questions
fail closed. `top_k=None` explicitly ranks both complete pools for evaluation.

## Cache and lifecycle

Avoid pickle because it executes Python objects while loading. A cache consists
of:

- `schema-index.json`: schema version, model ID, document version, weights,
  catalog SHA-256, exact ordered current element/document metadata, dimensions,
  referenced generation filename, and payload SHA-256;
- `schema-index-<sha256>.npz`: immutable relation and field float32 matrix
  generation loaded with `allow_pickle=False`.

Publication writes and fsyncs a unique temporary matrix, moves it to its
content-addressed immutable generation under a process lock, fsyncs the directory,
then atomically switches/fsyncs the manifest last. Prior generations are retained,
so the old manifest remains readable after termination before the switch. Loading
requires the exact safe `schema-index-<digest>.npz` filename, rejects traversal,
symlink and hardlink aliases, and validates catalog hash, model ID, document
version, exact current ordered IDs/document hashes, dimensions, finite normalized
vectors, and the NPZ digest. Any mismatch raises `SchemaIndexError`; it never
recomputes implicitly.
The explicit build command owns model loading and cache replacement.

The load-time criterion `<1s` measures validated cache loading after Python
startup and excludes loading model weights. The query latency criterion `<100ms`
is warm-model p50 over the 50-case evaluation file after one warm-up query.

## CLI and notebook

`scripts/13_schema_linker.py` exposes:

- `build-index`: validate catalog, load the named encoder, build and atomically
  publish the cache;
- `query`: load a validated cache/model and print ranked relations and fields;
- `evaluate`: load an explicit ground-truth JSONL, warm the model, and emit
  configurable relation Recall@K, fixed field Recall@5/Recall@10, full-field-pool
  MRR, latency distribution, input digests, model ID, and git SHA.

Missing model files/network or missing ground truth produce a structured
`blocked` report and nonzero exit. Only explicit encoder dependency failures are
classified through wrapped causes; programming errors remain `failed`, as do
invalid catalog/cache/ground truth. No command invents labels or marks a run ready
without evidence.

`notebooks/11_schema_linker_eval.ipynb` imports production functions, displays
the report, and does not contain a second implementation.

## Evaluation contract

`data/eval/schema_link_groundtruth.jsonl` contains exactly 50 independently
reviewed rows:

```json
{"id":"SL-001","nl":"transactions sent by an exchange","gold_relations":["transaction_facts"],"gold_fields":["transaction_facts.from_address"]}
```

IDs and normalized questions are unique. Gold elements must exist in the current
catalog; every row has at least one gold field, and at least one relation is
derived from those fields or explicitly annotated. Relation Recall@K is
configurable and micro-averaged; field recall is always emitted at both 5 and 10,
with field Recall@10 ≥0.80 as the acceptance gate. MRR uses the first relevant
rank from the complete field pool, not a top-10 truncation. The report also records
warm p50/p95 latency.

The committed Stage A/template provenance may be used for unit fixtures and
diagnostics, but it is not called manual ground truth and cannot close the
50-question scientific acceptance gate.

## Error handling and privacy

- Catalog and index errors use domain exceptions with actionable messages.
- Model initialization happens only in build/query/evaluate paths, never on
  module import or catalog-document tests.
- The linker accepts one bounded question and stores no question text in the
  cache. Evaluation reports contain aggregate metrics and input hashes, not
  participant identity.
- Cache/report publication is deterministic or provenance-stamped as
  appropriate and never overwrites catalog or ground-truth inputs.

## Tests and acceptance evidence

Test-first coverage includes document construction, Plan B relation/field IDs,
synonyms and role ambiguity, deterministic ranking/ties, invalid input, weight
validation, stale catalog/model/cache detection, NPZ tampering, atomic build,
evaluation metric math, ground-truth validation, and CLI help without model
initialization. A fake encoder makes all unit tests credential-free.

Repository gates remain full pytest, Ruff check, Ruff format check, notebook JSON
validation, and `git diff --check`. Implementation boxes may be completed from
offline evidence. Recall, latency, and manual-annotation boxes remain pending
until the real encoder and reviewed 50-row file produce a passing report.

## Alternatives rejected

1. **Embedding-only label retrieval:** simplest migration, but weak on
   directional and role-sensitive fields and offers no deterministic exact-term
   safety net.
2. **Ontology/SPARQL compatibility layer:** contradicts the accepted Plan B
   runtime and would rank elements the generator cannot emit.
3. **Fine-tuned bi-encoder:** could improve recall but needs labels and GPU before
   the baseline exists; defer until an evaluated failure justifies it.
4. **Pickled cache:** convenient but unsafe to load and unnecessarily couples
   artifacts to Python class layout.

## External gates

Implementation can proceed offline. Closing T4.1 scientifically still requires
the independently reviewed 50-question ground truth and a real MiniLM run that
meets Recall@10 and latency thresholds. Missing either is recorded as a blocker
while later independent implementation work continues.
