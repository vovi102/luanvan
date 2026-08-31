# T4.2 GoogleSQL Entity Linker Design

**Date:** 2026-08-23
**Status:** approved under the user's standing self-approval delegation
**Scope:** migrate T4.2 from SPARQL-oriented entity resolution to a typed,
GoogleSQL-native linker over the accepted chain-aware dictionary.

## Context

Pivot #1 made read-only GoogleSQL over the BigQuery analytical catalog the
canonical runtime. The T4.2 task still describes SPARQL triple generation,
concept-class injection, and a pickle cache. The accepted dictionary now contains
5,135 chain-bound address records, 5,097 owner targets, 8,538 normalized aliases,
10 concepts, immutable source revisions, address roles, and confidence metadata.

T4.2 must identify entity evidence in a natural-language question without deciding
the final SQL predicate or join. T4.3 owns that later resolution. This keeps the
entity linker a deep module: callers learn one interface while exact phrase
matching, fuzzy recovery, embedding retrieval, address recognition, ambiguity,
cache validation, and provenance remain implementation details.

## Decision

Use a four-stage cascade over immutable target groups:

1. **Address/exact:** recognize a complete Ethereum address or a longest,
   boundary-aware dictionary/concept phrase.
2. **Fuzzy:** recover a misspelled phrase with RapidFuzz at a validated threshold.
3. **Embedding:** rank owner/concept documents with the existing production
   `sentence-transformers/all-MiniLM-L6-v2` encoder.
4. **Ambiguity:** return an explicit ambiguous match with alternatives when the
   winner is below the acceptance threshold or too close to the runner-up.

A question with no entity evidence returns an empty tuple. It does not fabricate
an `unknown` entity. A syntactically valid address is always queryable: a known
address is enriched from the dictionary, while an unknown address is returned as
an `address` target with no owner/category claims.

The public interface is:

```python
EntityLinker.link(question: str) -> tuple[EntityMatch, ...]
```

`EntityMatch` contains:

- original `span` and half-open `span_offset`;
- stable `target_id` and `target_kind` (`owner`, `concept`, or `address`);
- `owner`, `addresses`, `category`, and `concept_class` when supported;
- `stage` (`address`, `exact`, `fuzzy`, `embedding`, or `ambiguous`);
- finite `confidence` in `[0, 1]`;
- up to three typed alternatives for an ambiguous result;
- dictionary target fingerprint for downstream provenance.

Stable IDs are reversible and collision-free: `owner:<percent-encoded-owner>`,
`concept:<normalized-key>`, and `address:<lowercase-address>`.

Results are sorted by source offset, then longest span, then target ID. Spans do
not overlap. Exact/address matches dominate later stages. The interface exposes no
cache paths, NumPy arrays, encoder details, or SQL fragments.

## Canonical targets and documents

The loader calls the existing dictionary validator before deriving targets. It
then builds:

- one owner target per exact `owner`, grouping every address and primary label;
- one concept target per normalized concept key;
- address lookup entries for every `address_lower`;
- alias phrases from `aliases.json`, entity aliases, primary labels, owner names,
  concept keys, and concept aliases.

The accepted corpus contains real alias collisions, including token symbols shared
by different contracts and generic concept phrases that also name an owner. The
index therefore stores one phrase to an ordered set of targets. An exact collision
returns `ambiguous` with alternatives instead of relying on input order. Duplicate
definitions of the same phrase/target collapse deterministically. A target
referenced by `aliases.json` but absent from owner groups fails construction.
Empty, control-character, tokenless, oversized, or non-normalized phrases fail
closed.

Owner documents contain the owner, sorted primary labels, sorted aliases, sorted
categories, concept classes, and address roles. Concept documents contain the key,
description, aliases, ontology class local name, total instance count, and at most
the first 50 sorted instance owners. This deterministic bound prevents a broad
concept such as `token_contract` from creating a document larger than the encoder
can use. Documents and target metadata carry SHA-256 fingerprints.

Normalization uses Unicode NFKC plus case folding and collapsed whitespace. The
question tokenizer retains an original-character offset map so returned spans are
always slices of the caller's original string, including case and punctuation.

## Retrieval behavior

### Address and exact stage

Complete `0x` plus 40-hex addresses are recognized case-insensitively with token
boundaries. Exact aliases are matched as normalized token sequences. Longest
non-overlapping phrases win; equal unambiguous spans tie-break by stable target
ID. Equal spans with multiple semantic targets produce one `ambiguous` result.

Address results do not suppress a distinct named entity elsewhere in the question.
An exact name suppresses fuzzy/embedding proposals that overlap the same span.

### Fuzzy stage

Fuzzy matching considers uncovered one-to-five-token windows containing at least
one alphabetic character. Stopword-only windows are discarded. RapidFuzz compares
each window to the canonical alias vocabulary. The default acceptance threshold is
`0.85`; the score is normalized to `[0, 1]`. A winner is accepted only when it is
unique at that score and is at least `0.03` above a different-target runner-up.
Otherwise it becomes `ambiguous` with up to three alternatives.

### Embedding stage

Embedding retrieval runs only when no exact/fuzzy target was accepted for a
candidate window. Candidate windows are encoded in one batch. Their normalized
vectors are multiplied by the immutable target matrix. The default acceptance
threshold is `0.75`, with the same `0.03` different-target margin. Programming
errors are not reclassified as missing-model failures.

Embedding is an injected internal seam: deterministic fake encoders cover unit
tests, while production commands explicitly load MiniLM. Importing the module or
running `--help` never downloads or initializes a model.

## Cache and publication

Pickle is rejected. The entity index uses:

- `entity-index.json`: canonical manifest with schema/document versions, model ID,
  SHA-256 of `entities.json`, `aliases.json`, and `concepts.json`, exact ordered
  target metadata/document fingerprints, dimension, thresholds, referenced matrix
  generation filename, and matrix SHA-256;
- `entity-index-<sha256>.npz`: immutable float32 target matrix loaded with
  `allow_pickle=False`;
- `entity-index.lock`: process lock sidecar.

Publication follows the T4.1 manifest-last protocol: write and fsync a unique
temporary NPZ, move it to its content-addressed generation, fsync the directory,
then atomically switch and fsync the manifest. Prior generations remain readable
after interruption. Loading rejects path traversal, a mismatched generation name,
symlinks, hardlink aliases, stale dictionary/model/document metadata, non-finite or
non-normalized vectors, and digest/shape mismatches. Loading never rebuilds.

Exact and fuzzy indexes are deterministically reconstructed from the hash-bound
target metadata. Only embedding matrices are persisted.

## CLI, evaluation, and artifacts

`scripts/14_entity_linker.py` exposes:

- `build-index`: validate dictionary, load encoder, build and publish explicitly;
- `query`: strict-load the current index and print typed matches;
- `evaluate`: require an explicit independently reviewed 100-row ground truth,
  warm the encoder, and publish aggregate accuracy/latency/provenance.

The scientific ground truth path is
`data/eval/entity_link_groundtruth.jsonl`. Each row has a unique ID/question and
one or more gold mentions with original span offsets and a stable target ID. It
must contain exactly 100 rows and at least one named-entity mention per row.
Dictionary targets and offsets are validated before evaluation. The report emits
named-entity top-1 accuracy, mention precision/recall/F1, per-stage counts, p50/p95
warm latency, model/dictionary/index hashes, and full lowercase git SHA.

The implementation acceptance gates are offline and may be completed locally.
Scientific Top-1 accuracy `>=0.85` and warm latency `<200 ms` remain unchecked
until the independent 100-row artifact exists and a real evaluation passes.
`notebooks/12_entity_linker_eval.ipynb` imports production functions rather than
duplicating retrieval logic.

## Errors and safety

- Invalid questions, dictionaries, targets, thresholds, or cache data raise typed
  entity-linker domain errors with actionable messages.
- Missing model files/packages/network raise a dedicated unavailable error only at
  explicit production initialization seams.
- Question text is not persisted in the index or aggregate report.
- Evaluation/report outputs may not overwrite dictionary, index, or ground-truth
  paths, including relative/absolute, symlink, hardlink, or future-generation
  aliases.
- No local command invents manual labels, downloads a model implicitly, queries
  BigQuery, or claims the scientific gate from synthetic fixtures.

## Testing

Test-first coverage crosses the public module interface and publication seam:

- dictionary grouping, collision rejection, deterministic documents/fingerprints;
- Unicode/case/whitespace normalization with exact original offsets;
- known and unknown addresses, exact aliases, longest non-overlap;
- fuzzy misspelling, ambiguity margin, embedding fallback, stable ordering;
- invalid input and fake-encoder shape/normalization/error taxonomy;
- stale/tampered/path-aliased NPZ and interrupted manifest-last publication;
- 100-row ground-truth validation and metric math;
- CLI group/subcommand help without model initialization;
- notebook JSON and repository Ruff/pytest/format/diff gates.

## Alternatives rejected

1. **Scan every entity record per query:** avoids a build artifact but repeats
   owner data, weakens locality, and makes the `<200 ms` target unpredictable.
2. **Embedding-only retrieval:** smaller implementation, but unsafe for exact
   addresses, short symbols, directional names, and deterministic ambiguity.
3. **Persist a pickle/trie object:** convenient but unsafe and coupled to Python
   object layout. Deterministic reconstruction plus NPZ is portable and auditable.
4. **Generate SQL filters inside T4.2:** makes the module shallow by leaking catalog
   join decisions into entity recognition. T4.3 owns SQL-native resolution.

## External gates

Implementation, real index build, and warm-query smoke can run locally. Closing
T4.2 scientifically still requires an independently reviewed 100-question entity
ground-truth artifact. T3.5 collaborators may produce compatible questions, but
the linker evaluation labels and acceptance claim must be reviewed independently.
