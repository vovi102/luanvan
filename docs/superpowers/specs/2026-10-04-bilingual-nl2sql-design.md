# Bilingual English–Vietnamese NL2SQL Design

**Status:** Approved conversational design; written specification pending user review.

**Scope:** Make English and Vietnamese input a required thesis capability while
keeping GoogleSQL as the single output language and preserving the accepted
English evidence boundary.

## Context

The active system accepts English natural-language questions and produces
read-only GoogleSQL over the blockchain analytical catalog. Its training
pipeline creates English Stage A–D data, the finalized T3.5 benchmark contains
100 English questions, and the production schema/entity linkers pin the
English-oriented `sentence-transformers/all-MiniLM-L6-v2` encoder.

Vietnamese support is a core thesis requirement, not future work. A user must be
able to submit either English or Vietnamese—with or without Vietnamese
diacritics—and reach the same SQL safety, validation, and execution path. The
system must measure language effects without translating every production input
to English or modifying the immutable English benchmark after seeing results.

## Goals

1. Accept English, accented Vietnamese, and unaccented Vietnamese questions
   through one direct NL2SQL pipeline.
2. Produce the same canonical GoogleSQL target for semantically equivalent
   questions across languages.
3. Create balanced bilingual training artifacts with explicit language,
   semantic-family, generation, review, and hash provenance.
4. Create a 100-case Vietnamese benchmark paired to the exact SQL workload of
   finalized T3.5 English, authored by the agent and reviewed by one human.
5. Compare direct bilingual NL2SQL with an explicit Vietnamese-to-English
   translation baseline.
6. Report English regression, Vietnamese language gap, unaccented robustness,
   linking accuracy, execution accuracy, latency, and failure modes.
7. Preserve the existing leakage, BigQuery safety, recorded-cost, privacy, and
   reproducibility boundaries.

## Non-goals

- Localizing the user interface, result tables, explanations, or error messages.
- Translating GoogleSQL identifiers, table names, token symbols, addresses, or
  named blockchain entities.
- Replacing GoogleSQL with a Vietnamese representation.
- Treating machine translation as the production path.
- Rewriting or adding fields to the finalized English T3.5 artifact.
- Claiming independent authorship, independent review, multiple reviewers,
  inter-rater agreement, or population-level Vietnamese coverage.
- Tuning any component on T3.5 English, T3.5 Vietnamese, or the unaccented test
  slice after a primary result has been observed.

## Chosen approach

### Direct bilingual pipeline

The production path is language-unified:

```text
English or Vietnamese question
  -> Unicode and accent-aware normalization
  -> bilingual schema/entity linking
  -> multilingual retrieval and prompt construction
  -> NL2SQL generation
  -> existing GoogleSQL safety validation
  -> existing bounded BigQuery dry-run/execution
```

The pipeline does not require a language detector or route Vietnamese through a
translator. The original question remains immutable evidence. Normalization may
derive comparison forms, including an accent-folded Vietnamese form, but those
forms are used only for matching and never overwrite the submitted text.

The existing translation-first composition is implemented separately as a
scientific baseline:

```text
Vietnamese question -> pinned translator -> English question -> English NL2SQL
```

Translation identity, configuration, intermediate text, latency, and failure
provenance are recorded. Translation output is never inserted into the direct
bilingual training corpus or used to revise the held-out benchmark.

### Rejected alternatives

1. **Translation-only production:** faster initially, but translation errors are
   confounded with SQL errors, blockchain terminology may drift, and latency and
   external-provider dependence increase.
2. **Direct model plus translation fallback:** potentially robust, but obscures
   which path produced a result, adds a routing confidence problem, and makes the
   required bilingual comparison harder to interpret. It may be revisited only
   after the primary direct and translation-baseline results are locked.

## Domain and record model

Every bilingual training record includes:

- a stable record ID;
- `language` in `en` or `vi`;
- `text_variant` identifying clean accented, unaccented, or another declared
  noise family;
- `semantic_family_id` binding English and Vietnamese records derived from the
  same Stage A SQL intent;
- natural-language text and its non-destructive normalized forms;
- the unchanged GoogleSQL, slot values, expected columns, schema annotations,
  entity context, and Stage A provenance;
- generation model/prompt/configuration and accepted response metadata where an
  LLM generated the text; and
- exact source, output, review, and manifest hashes.

`semantic_family_id` establishes shared meaning, not literal translation. A
Vietnamese sentence may use natural Vietnamese information structure and domain
terms while remaining bound to the same SQL and semantic anchors.

Target SQL, table identifiers, field identifiers, token tickers, hexadecimal
addresses, protocol names, and exchange names remain canonical and
language-independent.

## Bilingual training corpus

### Vietnamese Stage B and C

The Vietnamese path consumes the same 1,000 accepted Stage A SQL records as the
English path without consuming any T3.5 question. It produces:

- one natural formal Vietnamese question per Stage A record; and
- three meaning-preserving Vietnamese variants per formal question: ordinary
  conversational, abbreviated, and alternative wording.

Generation prompts receive SQL, canonical facts, slot values, entity aliases,
and Vietnamese terminology context. Responses repeat canonical facts exactly.
The existing SQL/date/numeric/token/entity anchor validators are extended for
Vietnamese surface forms; they are not weakened or skipped.

The generation pipeline remains strict-schema, zero-paid-fallback, resumable,
and atomic. Application-level batching may reduce Free Tier request consumption,
but validation and checkpoint acceptance remain per record. One invalid member
does not silently publish a partially accepted batch; the implementation plan
must define deterministic split/retry behavior and generation-ID deduplication.

### Vietnamese noise

Vietnamese Stage D uses language-specific transformations rather than reusing
English noise mechanically. Supported families include:

- deterministic diacritic removal;
- Vietnamese chat abbreviations from a reviewed allowlist;
- bounded keyboard/spacing/word-form typos that do not change protected facts;
- casing and punctuation variation; and
- domain abbreviations whose SQL intent is unchanged.

Protected spans include dates, numbers, thresholds, limits, addresses, token
symbols, protocol/entity names, and required comparison operators. Every noisy
record is revalidated against the original semantic anchors.

### Balanced assembly

The canonical training snapshot contains explicit English and Vietnamese
partitions. Sampling is balanced by language and semantic family so duplicate
surface variants from one language cannot dominate optimization or B2/B5
retrieval. The manifest records per-language, per-style, per-noise, per-template,
and per-semantic-family counts.

Train/development splitting is group-aware on `semantic_family_id`: paired or
variant records from one SQL intent cannot cross the train/development boundary.
No benchmark ID, text, SQL-specific annotation, review note, or derived variant
may enter training, retrieval examples, prompt selection, linker tuning, model
selection, or hyperparameter search.

## Paired Vietnamese benchmark

### Authorship and pairing

The Vietnamese benchmark contains exactly 100 cases paired to the 100 finalized
English T3.5 cases by gold SQL identity. The immutable English artifact remains
byte-for-byte unchanged. Each Vietnamese case references:

- the English benchmark snapshot and manifest hashes;
- the paired English question ID;
- the same canonical gold SQL and expected columns;
- the same difficulty, category, entity-kind, schema-element, and CQ identity;
  and
- its own Vietnamese content, review, live-evidence, and manifest hashes.

The agent writes each Vietnamese question from the gold SQL, semantic intent,
catalog context, and expected output—not by literal sentence translation. One
human reviewer reviews all 100 cases and may revise or reject wording. The
provenance profile is explicitly agent-authored and single-human-reviewed.

### Review workflow

The review workflow reuses the append-only reviewed-benchmark machinery with a
distinct bilingual profile. Every case receives a decision and scores for:

- natural Vietnamese quality;
- SQL faithfulness;
- terminology appropriateness; and
- ambiguity.

Acceptance requires the human reviewer to approve the final Vietnamese text and
the unchanged gold SQL binding. Revisions are revalidated and require a later
explicit acceptance event. Missing review rows, auto-filled decisions, or a
second fabricated reviewer block finalization.

All 100 SQL queries must pass the existing offline safety gates and bounded live
BigQuery verification. Existing English live evidence may be referenced only
when the exact SQL bytes and policy bindings match; Vietnamese artifact
publication still requires its own complete provenance bundle and manifest.

### Unaccented robustness slice

The unaccented slice is deterministically derived from the finalized accented
Vietnamese text and retains the same gold SQL. It is a robustness slice, not a
replacement benchmark or an independently authored corpus.

Automatic validation rejects empty text, unchanged transformations, collisions,
and transformations that modify protected non-language tokens. The human
reviewer spot-checks cases flagged as lexically ambiguous and a deterministic
sample of the remaining slice. The manifest records derivation and review
coverage without inflating it to full independent human authorship.

### Artifact layout

Draft, review, and final Vietnamese evidence stays separate from English T3.5:

```text
data/review_drafts/t3_5_vi_candidate_set_<date>/
  candidates.jsonl
  review_events.csv
  final_selection.csv
  manifest.json
  REVIEW_GUIDE.md
  validation-report.json

data/dataset/test/
  test-100.jsonl                 # existing immutable English artifact
  manifest.json                  # existing immutable English manifest
  test-100-vi.jsonl              # accented Vietnamese paired benchmark
  manifest-vi.json
  test-100-vi-unaccented.jsonl   # derived robustness slice
  manifest-vi-unaccented.json
```

Vietnamese publication is coordinated and refuses to overwrite different final
bytes. A matching manifest is the readiness marker; a standalone JSONL is
incomplete.

## Normalization, catalog, and linking

### Normalization contract

The shared input representation contains:

- exact original UTF-8 text;
- Unicode NFC text;
- a comparison-normalized form preserving Vietnamese diacritics; and
- an accent-folded comparison form.

Punctuation and whitespace normalization is deterministic. Accent folding may
improve lexical recall but cannot determine meaning or replace the original in
prompts, reports, predictions, or audit evidence.

### Bilingual catalog

Canonical relation/field IDs and English labels remain stable. Vietnamese labels,
descriptions, and reviewed synonyms are additive metadata bound to those IDs.
Entity aliases add natural Vietnamese mentions while leaving addresses, symbols,
and canonical entity identities unchanged. Ambiguous short aliases remain
explicitly ambiguous and fail closed under the existing policy.

### Multilingual encoder selection

The English-only MiniLM encoder cannot be assumed suitable for Vietnamese. A
small candidate set of multilingual encoders is pinned by model ID, revision,
license, dimensions, normalization behavior, and artifact digest. Selection uses
only bilingual development ground truth and evaluates:

- English and Vietnamese schema Recall@5/10;
- English and Vietnamese entity Top-1/F1;
- accented and unaccented retrieval deltas;
- latency, memory, cache size, and deterministic ordering; and
- English regression against the current pinned encoder.

The winning encoder and thresholds are fixed before either paired benchmark is
evaluated. Existing index identities and caches are versioned; an English index
cannot be silently loaded as a bilingual index or vice versa.

## NL2SQL models and retrieval

B1/B2 and B4/B5 retain one GoogleSQL extraction and safety contract. Prompts add
bilingual catalog descriptions and state that the question may be English or
Vietnamese. They do not translate identifiers or ask the model to explain its
answer.

B2/B5 retrieve exactly the configured number of examples from the accepted
bilingual training snapshot with a multilingual encoder. Retrieval is
language-unified: it ranks all eligible examples and does not require a language
detector or hard same-language filter. Prediction provenance records the
language metadata and semantic-family IDs of selected examples so cross-language
retrieval behavior can be analyzed.

Any fine-tuned B3 training run uses group-aware bilingual sampling and reports
per-language token/example exposure. English-only and bilingual variants keep
the same base model, target format, catalog snapshot, decoding policy, and
training budget wherever possible so English regression is interpretable.

## Evaluation design

### Research question

The thesis adds the following required bilingual robustness question, with final
numbering synchronized with the thesis governance document:

> How effectively does a direct bilingual NL2SQL pipeline preserve execution
> accuracy across English, accented Vietnamese, and unaccented Vietnamese input?

### Systems compared

At minimum, evaluation includes:

1. the accepted English-only NL2SQL configuration on T3.5 English;
2. the direct bilingual configuration on paired English and Vietnamese cases;
3. the same bilingual configuration on the unaccented robustness slice; and
4. the pinned translation-first baseline on Vietnamese cases.

Applicable B0–B5 outputs remain separately named. A failed or weak Vietnamese
result is retained as a genuine result; it is not replaced with translation
output under the direct system's identity.

### Metrics

For each system and language slice, reports include:

- execution accuracy as the primary metric;
- exact and structural SQL match;
- answer/result semantics where applicable;
- schema-link and entity-link metrics;
- coverage/no-output rate and normalized failure modes;
- end-to-end and generation-only latency; and
- observed provider cost/privacy provenance where remote models are used.

Paired cases report:

- `language_gap = execution_accuracy_en - execution_accuracy_vi`;
- `accent_gap = execution_accuracy_vi - execution_accuracy_vi_unaccented`;
- paired bootstrap confidence intervals; and
- a paired binary significance analysis such as McNemar's test when its
  assumptions and sample size are satisfied.

Translation-baseline latency includes translation. Direct-system latency does
not hide normalization, retrieval, linking, validation, or recovery time.

### Pre-registered acceptance gates

Before primary inference begins:

1. All 100 Vietnamese cases are explicitly accepted by the human reviewer and
   bind to 100 safe, live-verified gold SQL queries.
2. English execution accuracy for the bilingual configuration is no more than
   2 percentage points below the matched English-only configuration.
3. Vietnamese execution accuracy is no more than 10 percentage points below the
   paired English execution accuracy.
4. Unaccented Vietnamese execution accuracy is no more than 10 percentage points
   below accented Vietnamese execution accuracy.
5. All primary metrics include confidence intervals and complete failure-mode
   counts; no-output cases remain failures rather than being excluded.

These gates define success but do not authorize post-test tuning. If a gate
fails, the result is reported and any later system revision starts a new,
explicitly versioned experiment using development evidence only.

## Leakage and experiment governance

The English and Vietnamese benchmarks form one paired held-out evaluation
boundary. Neither language can be used to tune behavior for the other. In
particular:

- no Vietnamese question or unaccented derivative enters training or retrieval;
- no English T3.5 question is used as a generation prompt for Vietnamese
  training data;
- benchmark review notes and failure analysis stay outside model/linker inputs;
- encoder, thresholds, aliases, prompt wording, and decoding parameters are
  frozen using development sets before primary evaluation; and
- a hash-bound experiment registry records every evaluated system version.

After results are opened, error analysis may motivate future versions, but those
versions are not relabeled as the pre-registered primary experiment.

## Implementation boundaries

The implementation plan should divide work into independently verifiable seams:

1. language-aware text contracts and normalization;
2. Vietnamese training generation, validation, batching, and publication;
3. Vietnamese noise transforms and balanced bilingual assembly;
4. paired benchmark draft/review/finalization and unaccented derivation;
5. bilingual catalog metadata and multilingual linker indexes;
6. bilingual B1/B2 and B4/B5 prompt/retrieval provenance;
7. translation-first baseline;
8. bilingual evaluation metrics, paired statistics, and reports; and
9. task, backlog, decision-log, methodology, and limitation updates.

Public interfaces should extend existing deep modules rather than add parallel
one-off scripts that bypass current validation, leakage, or provenance gates.

## Rollout order

1. Finalize this design and implementation plan.
2. Build Vietnamese normalization, development ground truth, and multilingual
   encoder selection without touching held-out benchmarks.
3. Extend the T3 generation pipeline and produce reviewed Vietnamese training
   artifacts; assemble a balanced bilingual training snapshot after English
   Stage D is accepted.
4. Create and validate the exact 100-case Vietnamese paired review draft, then
   obtain the user's decisions and freeze those 100 cases.
5. Finalize live-verified accented and derived unaccented benchmark artifacts.
6. Freeze bilingual configurations, then run genuine English/Vietnamese
   inference and paired evaluation.
7. Update thesis methods, results, limitations, and reproducibility evidence.

Vietnamese benchmark authoring and linker development may proceed while English
T3.3 consumes external quota. Genuine bilingual training assembly still waits
for accepted English Stage D; primary bilingual evaluation waits for all paired
benchmark and system hashes to be frozen.

## Testing strategy

Tests are written before implementation and cover:

- Unicode NFC and accent-folding fixtures, including text already unaccented;
- immutable original text and protected tokens;
- strict language/text-variant/semantic-family contracts;
- group-aware split and balanced sampling without family leakage;
- Vietnamese fact-anchor and entity-alias validation;
- batch checkpoint/resume, batch splitting, generation-ID cost deduplication,
  and atomic publication;
- Vietnamese-specific noise transformations and collision rejection;
- benchmark pairing, immutable English references, review transitions, and
  final hashes;
- unaccented derivation and ambiguous-case review sampling;
- multilingual index identity, cache rejection, ranking determinism, and English
  regression fixtures;
- bilingual retrieval provenance and benchmark exclusion;
- translation-baseline intermediate evidence and latency accounting;
- paired metric/gap/bootstrap calculations and missing-pair failures;
- offline commands not initializing BigQuery, Gemini, translators, or model
  backends; and
- end-to-end synthetic fixtures clearly marked non-genuine.

Repository gates remain full pytest, Ruff lint/format, notebook JSON validation,
secret scan, `git diff --check`, manifest/hash validation, and an explicit review
that no finalized benchmark content appears in training or caches.

## Risks and mitigations

- **Literal translation artifacts:** author paired Vietnamese cases from SQL and
  semantic intent; require naturalness review.
- **Single-reviewer bias:** disclose agent authorship and one-human review; do
  not report independent review or agreement statistics.
- **English regression:** freeze the English snapshot and enforce the 2-point
  paired regression gate.
- **Unaccented ambiguity:** preserve original text, use accent folding only for
  matching, reject collisions, and human-check flagged cases.
- **Encoder selection leakage:** select only on bilingual development evidence
  and freeze before benchmark inference.
- **Training duplication:** split and sample by semantic family, not individual
  surface record.
- **Translation-baseline confounding:** record intermediate translations and
  separate translation, generation, and total failure/latency evidence.
- **Quota and privacy:** retain checkpoint/resume, explicit Free Tier or budget
  contracts, provider provenance, and no paid fallback without a new decision.
- **Scope growth:** UI localization and multilingual result explanation remain
  out of scope; the required contribution is bilingual input-to-GoogleSQL.

## Acceptance criteria

- A hash-bound balanced bilingual training artifact exists with no benchmark
  overlap and complete language/style/noise/family counts.
- Vietnamese schema/entity development evaluations select and pin a multilingual
  encoder without using either final benchmark.
- Exactly 100 agent-authored, single-human-reviewed Vietnamese cases pair to the
  immutable English benchmark and pass offline and live SQL gates.
- A hash-bound unaccented robustness slice derives from the accepted Vietnamese
  benchmark with documented review coverage and no protected-token changes.
- Direct bilingual and translation-first systems produce complete, separately
  identified predictions and reports for all required slices.
- English regression, language gap, accent gap, paired uncertainty, latency,
  failure modes, cost/privacy, and provenance are reported against frozen hashes.
- The pre-registered gates are evaluated honestly; failed gates remain failed
  results rather than triggering test-set tuning.
- Thesis and repository documentation state the agent-authored,
  single-human-reviewed and domain-specific limitations without inflated claims.
