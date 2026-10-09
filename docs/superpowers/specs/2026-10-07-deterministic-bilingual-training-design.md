# Deterministic Agent-Authored Bilingual Training Design

**Status:** Approved by the user on 2026-10-07.

**Supersedes:** The LLM-based English and Vietnamese training-text generation
parts of T3.3, the “Vietnamese Stage B and C” section of
`2026-10-04-bilingual-nl2sql-design.md`, and Tasks 2–3 plus the corresponding
CLI 20/21 generation steps in `2026-10-04-bilingual-nl2sql.md`.

All completed bilingual normalization, benchmark, linking, prompt, translation
baseline, evaluation, and offline workflow work remains valid.

## Decision

No remote or local language model generates training paraphrases.

The agent authors a finite, version-controlled bilingual template catalog. A
deterministic offline renderer binds those templates to the existing 1,000
validated Stage A records. Qwen, Gemini, OpenRouter, and any future solver model
are excluded from this producer boundary. The downstream NL2SQL experiment may
still use one pinned small Qwen model as the solver for B1/B2/B3-style
comparisons, but it must not be represented as a dataset author or reviewer.

This decision removes the Gemini Free Tier quota and availability bottleneck,
makes corpus construction reproducible without network access, and separates
the training-data author from the model being evaluated. It does not turn the
result into independently human-authored data: provenance must say exactly
`agent-authored`, `deterministically-expanded`, and, where applicable,
`agent-reviewed`.

## Context

The Gemini live T3.3 pilot completed 26 of 1,000 first-stage requests before
daily request limits and repeated service unavailability made the expected
completion time unsuitable for the thesis schedule. The checkpoint and outage
evidence remain preserved as historical pilot evidence, but those 26 outputs
are not canonical training records and must never be mixed with the new
artifact.

The repository has 25 accepted Stage A SQL intent templates and 1,000 accepted
Stage A records. Each record already binds immutable SQL, slots, schema facts,
entities, expected columns, and source hashes. These are sufficient inputs for
controlled surface realization without another generative model.

## Goals

1. Produce a balanced English–Vietnamese training corpus entirely offline.
2. Preserve Stage A SQL, slots, expected columns, schema annotations, entities,
   semantic anchors, and source hashes byte-for-byte.
3. Provide four useful surface styles in both languages: formal,
   conversational, abbreviated, and alternative wording.
4. Make every output reproducible from the catalog, Stage A snapshot, renderer
   version, and seed.
5. Keep the finalized English benchmark and Vietnamese review draft outside all
   authoring, selection, retrieval, training, and tuning inputs.
6. Retain the thesis ablation between Stage A-only training and augmented
   bilingual training.

## Non-goals

- Claiming that each expanded record was individually written or reviewed by a
  human.
- Claiming independent authorship, independent review, multiple reviewers, or
  inter-rater agreement.
- Using Gemini, OpenRouter, Qwen, machine translation, or another LLM as a
  fallback generator.
- Reusing the 26 Gemini pilot outputs in the canonical training corpus.
- Changing SQL, translating identifiers, or inventing facts not present in
  Stage A.
- Reading held-out benchmark surface text as a source for training templates.
- Using held-out benchmark results to revise the template catalog.

## Corpus Architecture

### Authored catalog

The catalog contains exactly one entry for each combination of:

- 25 Stage A `template_id` values;
- languages `en` and `vi`; and
- styles `formal`, `conversational`, `abbreviated`, and `alternative`.

The initial catalog therefore contains exactly 200 authored patterns. A pattern
is natural-language text with named placeholders whose set must exactly equal
the slots required by its Stage A intent. A catalog entry also records:

- stable catalog entry ID;
- Stage A `template_id`;
- language and style;
- protected placeholder list;
- author type `agent`;
- review type `agent-reviewed`;
- catalog schema version; and
- the entry content digest.

The catalog is reviewed as a finite source artifact. Expanded rows are not
misrepresented as separately authored or reviewed.

### Deterministic expansion

For every accepted Stage A record, the renderer selects the four entries for
its `template_id` in each language and binds the record’s exact slot values.
There is no sampling and no model call. The canonical clean expansion contains:

- 4,000 English records;
- 4,000 Vietnamese records; and
- 8,000 records total, arranged in 1,000 semantic families with eight surface
  realizations per family.

Every expanded row records `language`, `style`, `semantic_family_id`, catalog
entry ID and digest, source record ID and digest, renderer version, rendered
text, immutable SQL and annotations, and the final record digest.

Rendering is stable under input order. Re-running with identical Stage A bytes,
catalog bytes, renderer version, and configuration must reproduce identical
records and manifests.

### Optional deterministic noise

Language-specific Stage D transforms remain allowed after clean expansion.
They are deterministic, separately labeled, and never replace the clean
record. Supported transformations are limited to the existing validated
English rules and reviewed Vietnamese rules such as diacritic removal, bounded
chat abbreviations, casing, punctuation, and spacing changes.

Addresses, hashes, token symbols, dates, numbers, thresholds, limits, entity
names, identifiers, and comparison semantics are protected spans. Any transform
that changes a protected span or creates an empty/colliding question is rejected.

The clean 8,000-record snapshot is the mandatory corpus. A noisy snapshot is a
separate derived artifact with its own configuration and manifest; it is not
required to claim deterministic bilingual generation complete.

## Validation Gates

Publication fails unless all of the following hold:

1. The Stage A input contains exactly 1,000 accepted records and uses only the
   25 pinned intent templates.
2. The catalog contains exactly 200 unique entries and exactly four styles for
   each `(template_id, language)` pair.
3. Each pattern’s placeholders exactly match the intent’s declared slot schema;
   no unresolved, extra, or duplicated placeholder remains after rendering.
4. The clean output contains exactly 8,000 records: 4,000 English and 4,000
   Vietnamese, with all eight variants present for every semantic family.
5. SQL bytes, slot values, expected columns, schema elements, entities, and all
   semantic anchors are unchanged from Stage A.
6. Record IDs and normalized questions are unique within the clean snapshot.
   Any permitted cross-language collision must still be rejected rather than
   silently deduplicated.
7. For each semantic family and language, mean pairwise normalized Levenshtein
   distance across the four clean styles is greater than `0.30`; the manifest
   reports the distribution and failing family IDs.
8. English and Vietnamese validation samples each contain 100 deterministic,
   stratified records covering all 25 intents and four styles. Agent audit must
   find at least 95/100 faithful and 90/100 natural in each language. Failures
   require catalog correction and a fresh artifact version, not waiver.
9. No normalized full-text match or configured high-order n-gram overlap exists
   with the immutable English benchmark or the Vietnamese review draft. The
   validator consumes only their exclusion digests/derived comparison index;
   the renderer and catalog authoring path do not consume benchmark text.
10. A second run from the same inputs has the same output and manifest hashes.

Agent audit decisions are append-only evidence with record ID, decision,
faithfulness, naturalness, notes, reviewer type `agent`, timestamp, and audit
schema version. They must never be labeled human or independent review.

## Leakage Boundary

Training templates are authored only from Stage A intent definitions, slot
schemas, SQL semantics, and the production catalog. The English T3.5 question
surface, Vietnamese candidate wording, review decisions, predictions, and
evaluation reports are prohibited inputs.

The Vietnamese benchmark was also agent-authored, so author independence cannot
be claimed. This limitation is disclosed in the thesis. Leakage risk is reduced
through separate artifact paths, immutable hashes, mechanical text/substring
overlap checks, group-aware splits, and the existing requirement for the user’s
100 explicit benchmark review decisions. The human benchmark review remains
mandatory and is not replaced by the training-catalog audit.

## Splitting and Assembly

Train/development splitting is group-aware on `semantic_family_id`; all language,
style, and noise variants of one Stage A record stay in one split. Assembly is
balanced by language, style, intent template, and semantic family. A single
style or language cannot be oversampled merely because it has more derived
noise variants.

The manifest includes counts by split, language, style, intent, and noise
family; all source/catalog/configuration hashes; renderer and validator
versions; audit summary and evidence hash; exclusion-set hashes; and final
artifact hashes.

## Provenance and Cost

The manifest records:

- `producer_type: deterministic_template_renderer`;
- `author_type: agent`;
- `review_type: agent-reviewed`;
- `generation_model: null`;
- `provider: null`;
- `api_request_count: 0`;
- `recorded_cost_usd: 0.00`; and
- a note that recorded cost is non-authoritative operational evidence, not a
  provider billing statement.

No API key is read by the offline builder. A test runs the workflow with network
access disabled and provider-related environment variables removed.

## Artifact and Module Boundaries

The implementation should replace the blocked generation contracts rather than
extend the Gemini runner:

```text
src/nl2sparql/dataset/bilingual/
  contracts.py       # strict catalog and expanded-record schemas
  templates.json     # 200 agent-authored bilingual patterns
  rendering.py       # pure slot binding and protected-span checks
  assembly.py        # balance, split, leakage, audit, manifest, publication

scripts/
  20_build_bilingual_training.py
  21_validate_bilingual_training.py
```

Existing normalization, language-aware noise, retrieval, prompts, paired
benchmark, translation baseline, and bilingual evaluation modules are reused.
The old Gemini paraphrase modules remain only for historical T3.3 evidence and
are not imported by the new builder.

## Migration and Preservation

1. Preserve the Gemini live worktree, its 26-record checkpoint, request journal,
   and outage evidence without committing secrets or temporary checkpoint data.
2. Mark the Gemini T3.3 attempt as an incomplete historical pilot, not a
   completed dataset task.
3. Do not cherry-pick the pilot outputs into the bilingual training branch.
4. Replace only the blocked generation/assembly tasks and CLI 20/21 steps in the
   existing plan. Completed Tasks 1 and 4–8 plus CLI 23/24 stay intact.
5. Update backlog/evidence only after the deterministic artifact passes every
   gate; never record completion based on code or templates alone.

## Testing Strategy

Implementation follows TDD and covers:

- exact catalog cardinality and coverage;
- placeholder/schema mismatch and Unicode edge cases;
- immutable SQL, slots, anchors, identifiers, and protected spans;
- stable expansion regardless of input order;
- exact per-language/style/family counts;
- normalized duplicate and benchmark-overlap rejection;
- group-aware split isolation and balanced assembly;
- Levenshtein diversity calculation and threshold failures;
- honest audit provenance and threshold enforcement;
- manifest/file hash verification and atomic publication;
- a second-build byte-for-byte reproducibility check; and
- offline execution with zero network/model/provider use.

The focused tests are followed by the repository’s full pytest suite, Ruff, and
all artifact validators relevant to Stage A, bilingual training, benchmark
exclusion, retrieval snapshots, and manifests.

## Thesis Interpretation

This corpus supports a controlled augmentation experiment, not a claim that an
LLM independently paraphrased real user language. The thesis compares:

- Stage A-only training;
- deterministic agent-authored bilingual augmentation; and
- retrieval/model configurations over the same frozen data boundary.

Any improvement can be attributed to the augmentation strategy under the pinned
experiment, while limitations include template regularity, shared agent
authorship, finite intent coverage, and absence of population-representative
Vietnamese language data. The paired held-out benchmark, the user’s explicit
review, and execution-based SQL evaluation remain the primary validity checks.

## Acceptance Criteria

This design is implemented only when:

- all 200 catalog entries exist and pass full catalog review;
- the canonical clean artifact contains exactly 8,000 valid records;
- all automated validation, diversity, leakage, reproducibility, test, and lint
  gates pass;
- both 100-record agent audits meet the stated thresholds;
- manifests report zero requests, `$0.00`, null model/provider, and honest
  agent/deterministic provenance;
- the Gemini pilot remains excluded and preserved as incomplete evidence; and
- artifact paths, counts, hashes, audit results, and ablation configuration are
  documented before downstream training begins.
