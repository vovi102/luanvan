# Bilingual training agent audit — 2026-10-15

Status: **audit complete, publication gate failed**. This is an agent review of
100 English and 100 Vietnamese rendered training questions, not human review,
independent review or a model-performance evaluation. No catalogue/SQL change,
provider call, canonical corpus publication, merge, push or PR occurred.

## Result

| Language | Faithful / 100 (minimum 95) | Natural / 100 (minimum 90) | Accept / reject | Gate |
| --- | --- | --- | --- | --- |
| English | 67 | 96 | 65 / 35 | Fail: faithfulness |
| Vietnamese | 73 | 93 | 70 / 30 | Fail: faithfulness |

An event is accepted only if both judgments are true. The publication contract
tests faithfulness and naturalness separately; accepted count is not substituted
for either threshold. All 200 decisions, including every rejection, are retained.

## Inputs and procedure

The user requested this audit after genuine Stage A v2 acceptance at `4e56d21`.
The [accepted source](stage-a-v2-final-live-acceptance-2026-10-15.md) is unchanged:
1,000 records, 25 intents, data SHA-256
`15b7cd6144301f040ecef54028929131afab76c45ccf3282011fd68f9ce62203`.
The reviewed catalogue SHA-256 is
`00d5dc083bd22aeeee4a8515c0cda0fb0f18cc972584f0e0f57681954cbf6cfe`.

1. CLI 20 `--mode audit-sample` validated the accepted source, catalogue,
   exclusion index, complete expansion, leakage and diversity gates. It expands
   8,000 rows in memory, but writes only the 200-row audit sample, not the
   canonical 8,000-row corpus or publication manifest.
2. Seed 42 selected exactly one sample for every combination of 25 intents and
   four styles in each language. A second CLI run to an ignored scratch path
   produced byte-identical sample output (`cmp` exit 0).
3. The agent read all 200 actual rendered questions and all 25 production SQL
   templates, cross-checking bound slots and the catalogue's half-open date
   contract. Each question received explicit faithful/natural judgments and a
   record-specific rationale; these are not scores inferred from a regex or
   from the automated renderer passing validation.
4. Every retained sample row was compared to the deterministic full expansion,
   including SQL, slots, anchors, expected columns and source/catalogue digests.
   Every audit event binds its exact expanded-record digest. Both languages'
   event logs passed structural/binding checks and then failed at their actual
   faithfulness threshold; the combined validator also fails closed.

Only the existing held-out exclusion **digest index** was consumed. No held-out
benchmark question text, predictions or evaluation results were used for this
review. Provider/model request count is zero. The same agent authored/revised
some catalogue entries earlier, so this is not an independent assessment.

## Rubric and interpretation

- Faithful requires the question to identify the SQL intent's material scope,
  direction, predicates, aggregation, units, thresholds and top-k selection.
  A question asking for arbitrary `n` matches is flagged when SQL instead
  selects the latest, largest-value, highest-gas or earliest `n`. Such a flag
  means under-specification of the paired training target, not that SQL returns
  rows outside the broad verbal request. Incidental dictionary presentation
  ordering and every projected output column need not be narrated.
- Addresses, hashes, class names, numbers, symbol filters and dates must remain
  literal. Ordinary date-range wording is interpreted using the catalogue's
  `[start_date, end_date)` convention. English “through end_date” is flagged
  because it affirmatively suggests inclusion of the final calendar date.
  The wording should state the exclusive boundary to remove that ambiguity.
- Transaction sender/recipient terminology alone is not a claim of successful
  funds movement. Explicit “transfers moved”, “total wei sent” or “chuyển ...
  wei” is flagged where SQL sums/filters transaction value without a receipt
  success predicate. Temporal funding association must not imply causality.
- Naturalness is judged within the declared style. Technical abbreviations,
  mathematical notation and familiar English domain loanwords are allowed in
  abbreviated Vietnamese. Singular/plural errors and heavily overloaded or
  malformed modifier chains are not accepted as natural.

These are conservative agent judgments for exact NL–SQL training pairs. The
stratified sample is not a random population estimate and the scores do not
establish user-language representativeness, inter-rater agreement or model
accuracy. Findings should be resolved through clearer catalogue wording, not
by claiming the broad questions identify a unique top-k target after the fact.

## Main findings

1. **Top-k criterion omitted.**
   `syn-v2-000047__en__conversational` asks for outgoing transfers without
   “latest”, whereas SQL orders timestamp descending.
   `syn-v2-000153__vi__alternative` states a minimum wei value but omits
   largest-value selection. `syn-v2-000791__vi__alternative` has the same
   omission for CQ35 despite its otherwise correct neutral native-value scope.
   Funding formal/conversational/alternative styles omit earliest-event
   selection, while the abbreviated styles explicitly say “First”/“đầu tiên”.
2. **Date endpoint ambiguity/conflict.**
   `syn-v2-000238__en__alternative` says “through 2026-06-16”; the underlying
   block TVF excludes timestamps at and after that date. Similar English
   alternative patterns repeat the problem across intents.
3. **Declared native value versus actual movement.**
   `syn-v2-000136__en__conversational` says “transfers moved”; its SQL has no
   success predicate. `syn-v2-000157__vi__conversational` and top-sender
   value wording similarly overstate the underlying transaction-value metric.
   Use neutral “native transaction value” wording rather than changing SQL.
4. **Grouping/eligibility under-specified.**
   `syn-v2-000482__en__abbreviated` says labeled senders, not grouped owners.
   Repeated-pair variants omit direction and/or `transaction_count > 1`.
   `syn-v2-000927__vi__abbreviated` says “≥10 native thành công” without the
   transaction count unit required by the concentration intent.
5. **Surface quality.**
   English has “1 transfers” and “1 blocks”. Vietnamese funding patterns have
   overloaded modifier chains; the CQ35 formal threshold clause is awkward.
   These naturalness issues are retained even though both languages exceed
   the naturalness minimum.

The exact affected IDs and judgments are in the decision log, not only these
examples. Accepted Stage A SQL and its live witness proof remain valid; this
audit does not justify rerunning BigQuery, weakening gates or changing SQL to
fit the wording.

## Evidence and verification

- [Sample, 200 rows](../evidence/bilingual-training-audit-sample-2026-10-15.jsonl),
  SHA-256 `de01254165eca7a361f3c4e6b092189b4dc39f72bfc610577ddd0d32f60fe1b9`.
- [Append-only initial decisions, 200 events](../evidence/bilingual-training-audit-decisions-2026-10-15.jsonl),
  SHA-256 `3aea05fc16e2d8c552a16ff4092a9b178a91efff6db347397ccd87a21a97795d`.
- [Machine-readable summary](../evidence/bilingual-training-audit-summary-2026-10-15.json),
  SHA-256 `ebc56909ca56714ee9ef4fdd0104110006961c4d2f478a4fab677c87b359cb1d`.
- [Offline binding/gate validator source](../evidence/bilingual-training-audit-validator-2026-10-15.txt).
  Its successful process exit means the failed audit was reproduced and
  validated as failed, **not** that publication gates passed.

The validator checks each language separately and preserves the exact errors:
“audit requires at least 95 faithful records, received 67” and
“audit requires at least 95 faithful records, received 73”. Automated quality
checks passing before sampling do not override these manual judgments.

Focused audit regression tests: **14 passed, 28 deselected in 80.92s**, using
`pytest tests/unit/test_bilingual_assembly.py tests/unit/test_bilingual_training_workflows.py -k audit -q`.
`git diff --check` passed. Production source, tests, accepted/candidate/V1
artifacts, catalogue and exclusion index are unchanged; no full-suite rerun was
needed for this evidence/documentation-only change.

## Next step — requires a correction task

Revise only the bilingual catalogue wording and any minimal renderer agreement
handling needed for bound `n=1`, with regression tests. Preserve the frozen
sample and decisions above. Create a new bound catalogue/artifact version and
fresh deterministic sample/audit; do not relabel this failed evidence as pass.
Only then consider canonical build/publication after every original gate passes.
This audit request did not authorize implementing those corrections.
