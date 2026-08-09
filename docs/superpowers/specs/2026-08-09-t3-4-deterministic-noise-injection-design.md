# T3.4 Deterministic GoogleSQL Noise Injection Design

## Context

T3.3 defines a final Stage C corpus of 3,000 natural English questions paired
with immutable GoogleSQL and provenance. Its live artifacts are currently
blocked by the missing `OPENROUTER_API_KEY`, but T3.4's transformation,
validation, publication, and audit machinery can be implemented and verified
offline now. The legacy T3.4 task is probabilistic, still calls the gold field
SPARQL, permits compound noise labels outside its own acceptance enum, and does
not guarantee an exact augmentation count.

## Goals and non-goals

T3.4 publishes exactly 3,150 rows: all 3,000 Stage C rows byte-semantically
unchanged plus exactly 150 noisy variants. It creates 38 typo, 38 abbreviation,
37 fragment, and 37 mixed-case variants using seed 42. Every selected Stage C
row contributes at most one variant. Re-running with identical source bytes and
configuration produces identical output bytes.

This task never changes SQL, Stage A hashes, generation metadata, slot values,
entity metadata, or Stage B/C text. It does not use an LLM, download an external
misspelling corpus, invent compound noise types, or claim that automated checks
replace the manual decipherability audit.

## Considered approaches

1. Deterministic candidate allocation is selected. Build a valid candidate for
   every eligible `(record, noise_type)`, shuffle stable record IDs with a
   stage-specific seed, then fill exact quotas without selecting a source twice.
   It gives exact counts, reproducibility, and auditable failure when a quota
   cannot be filled.
2. Independent Bernoulli sampling matches the old pseudocode but produces a
   variable count and type distribution, making artifacts and experiments hard
   to reproduce.
3. Generate several variants per record and filter globally provides more
   linguistic variety, but it expands manual-review scope and exceeds the 5%
   robustness augmentation required here.

## Module boundaries

`src/nl2sparql/dataset/noise/contracts.py` owns the four allowed noise types,
the immutable seed/quota contract, and typed validation errors.

`src/nl2sparql/dataset/noise/transforms.py` owns pure single-question
transformations. It derives protected anchors from `slot_values`, numeric/date
tokens, Ethereum addresses, token symbols, and pinned dictionary owner/primary
labels. Transformations may only edit unprotected text:

- typo performs one adjacent internal-letter swap in one word of at least five
  letters;
- abbreviation performs one case-insensitive longest-phrase replacement from
  the versioned local dictionary;
- fragment removes one request scaffold, auxiliary phrase, article, or final
  question mark;
- mixed case changes one unprotected alphabetic word's casing.

`src/nl2sparql/dataset/noise/pipeline.py` enumerates candidates, checks each
candidate against Stage C source data and entity anchors, performs exact quota
allocation, appends variants after originals in stable order, validates the
3,150-row artifact, and builds the run manifest.

`scripts/11_inject_noise.py` is the orchestration boundary. It accepts explicit
source/output/manifest paths for tests and defaults to the repository Stage C/D
paths. It validates all input before writing sibling temporary files and never
publishes a partial final artifact.

## Data contract

An original Stage C row is copied without adding noise fields. A noisy row keeps
every source field and replaces only `id` and `nl`, then adds:

```json
{
  "id": "<stage-c-id>-noise-typo",
  "noise_parent_id": "<stage-c-id>",
  "nl_original": "<exact source nl>",
  "nl": "<transformed question>",
  "noise_type": "typo",
  "noise_seed": 42,
  "noise_distance": 0.0182
}
```

`noise_type` is exactly one of `typo`, `abbrev`, `fragment`, or `mixed_case`.
The unchanged `parent_id` continues to identify the Stage A/Stage B parent;
`noise_parent_id` identifies the exact Stage C style row augmented by T3.4.

The abbreviation dictionary lives at
`src/nl2sparql/dataset/noise/abbreviations.json`. It contains structural query
language such as transaction/transactions, address, token transfer, between,
greater than, less than, average, maximum, and minimum. It intentionally omits
named entities and slot literals so abbreviation cannot bypass entity or fact
faithfulness checks.

## Deterministic selection

Input validation first reuses `validate_stage_c_records`, so the source must
contain exactly 3,000 normalized-unique Stage C rows with mean pairwise distance
above 0.30. Candidate order begins from source IDs sorted lexicographically.
Each noise type uses `random.Random("42:<noise_type>")` semantics implemented as
an integer derived from SHA-256, avoiding Python hash randomization. A candidate
is accepted only if its raw text changes, its protected anchors still validate,
its ID is unique, and the source has not already been used by another type.

Allocation order is `typo`, `abbrev`, `fragment`, `mixed_case`; the fixed quotas
are 38, 38, 37, and 37. Failure to fill any quota raises an error before output
publication. The final row order is all source rows in original order, followed
by noisy rows grouped in allocation order and then source ID order.

## Automated quality gates

The final validator proves:

- exactly 3,000 originals and 150 noisy rows, with exactly 3,150 unique IDs;
- exact noise distribution 38/38/37/37 and one variant per source;
- `nl_original` equals the source `nl`, while noisy `nl` differs in raw text;
- all fields other than the explicit T3.4 fields and `id`/`nl` equal the source;
- SQL and Stage A `record_sha256` remain unchanged;
- numeric, date, token, and entity anchors still pass the T3.3 validator;
- typo normalized edit distance is in `(0, 0.10]`, abbreviation in `(0, 0.35]`,
  fragment in `(0, 0.45]`, and mixed-case normalized distance is exactly zero;
- non-mixed-case noisy normalized questions do not collide with any other final
  normalized question; mixed-case variants must normalize to their original.

These gates make gross corruption unlikely but do not prove human
decipherability. The manifest deterministically samples 30 noisy IDs with seed
42 and records `manual_audit.completed=false` until a reviewer supplies the
30 decisions. Acceptance still requires at least 27/30 decipherable.

## Publication and manifest

`synthetic-stage-d.jsonl` and `noise-config.json` are written atomically only
after complete validation. The manifest records schema version, source Stage C
SHA-256, output SHA-256, seed, exact quotas/counts, abbreviation dictionary
SHA-256, raw/normalized uniqueness statistics, selected source IDs, 30 audit
IDs, and manual-audit status. It contains no API credentials or prompts.

The CLI supports `--mode generate` and `--mode validate-output`. Generate mode
requires the full Stage C artifact. Validate-output revalidates existing Stage C
and Stage D artifacts plus their manifest without regenerating them.

## Testing and completion boundary

Unit tests cover each pure transform, anchor protection, dictionary parsing,
deterministic allocation independent of input order, exact quotas/counts,
single-variant-per-source, SQL/provenance immutability, distance/collision
rejection, atomic failure, manifest hashes/audit IDs, and CLI failure without a
Stage C source. A generated 3,000-row fixture exercises the whole pipeline
without LLM or BigQuery access.

Implementation is complete when focused and full tests, Ruff, format, notebook
JSON, and whitespace checks pass. Dataset acceptance remains credential-gated
until T3.3 produces `synthetic-stage-c.jsonl`; at that point generate Stage D,
review the 30 manifest IDs, require at least 90% decipherable, then record the
artifact hashes and audit result in the task and decision log.
