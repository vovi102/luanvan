# Bilingual catalogue correction and agent re-audit r1 — 2026-10-15

Status: wording correction and 200-row re-audit complete; both language audit
gates pass; **1,485 tests passed**, 342 upstream warnings in 510.32s. No canonical corpus publication,
BigQuery/provider calls, merge, push or PR.

The user explicitly approved correcting the [initial failed audit](bilingual-training-agent-audit-2026-10-15.md)
and auditing again. This is a bounded change to the existing catalogue and its
tests, not a new research contract or renderer. The same agent authored and
reviewed the revised wording; this is **not human or independent review**.

## Changes and preserved boundaries

- The 200 patterns now explicitly identify material latest/largest/highest-gas/
  earliest selection, half-open date endpoints, declared native transaction
  value, owner grouping, directed repeated-pair eligibility and minimum-ten
  successful positive native transaction units.
- Limits are independent clauses, so `n=1` does not produce “1 transfers”,
  “1 blocks” or similar plural errors. No renderer agreement logic was needed.
- Formal date windows are separate clauses. Conversational Vietnamese explicitly
  stops before the ending date; merely excluding one named calendar date is
  insufficient. Funding clauses separate receipt/positive-value requirements
  from token-sender and timestamp association, without causality claims.
- All 200 entry IDs, placeholder sets, languages/styles, author/review fields
  and catalogue schema version 1.0.0 remain. Only patterns and their content
  digests changed. **r1 is a content revision**, not a schema-version bump.
- No production Python, renderer, SQL, SQL catalogue, source slots/projections,
  Stage A accepted/candidate/V1 artifact, pool, exclusion index or benchmark
  surface was changed. No held-out question wording was consumed.

Catalogue SHA-256:

- Before: `00d5dc083bd22aeeee4a8515c0cda0fb0f18cc972584f0e0f57681954cbf6cfe`.
  Byte-exact archive: `tests/fixtures/dataset/bilingual-pre-audit-correction-catalog.json`.
- Active r1: `9a62ebb166b6e46da7d6970aeddf675ae05a58284242eea7f5625c8fcf88dbd7`.

The original failed sample, decisions, summary and validator evidence remain
unchanged. Historical wording can be replayed from the archived catalogue; old
decisions deliberately fail the new record-digest binding. No failure was
relabeled as a pass.

## Fresh re-audit

| Language | Faithful / 100 | Natural / 100 | Accepted / 100 | Original gates |
| --- | --- | --- | --- | --- |
| English | 100 | 100 | 100 | Pass (95 faithful, 90 natural) |
| Vietnamese | 100 | 100 | 100 | Pass (95 faithful, 90 natural) |

CLI 20 `audit-sample` passed accepted-source, complete 8,000-row in-memory
expansion, uniqueness, diversity and digest-only leakage checks before writing
only the 200 selected rows. No 8,000-row canonical JSONL/manifest was written.

The seed remains 42, with one row per 25 intents × four styles in each language.
Because selection hashes stable record IDs, the 200 selected IDs remain the
same across catalogue revisions; all 200 record digests and questions changed
from the initial audit. This is a controlled re-review, **not an independent
holdout or a newly sampled population estimate**. No seed or sampling rule was
changed to improve the score.

The agent read the rendered questions for both languages and the revised
material scopes, using the same rubric as the first audit. During drafting it
caught an ambiguous Vietnamese ending-date clause, an ambiguous sender-total
phrase and a broken English funding clause. Provisional samples stayed in
ignored scratch storage; they were not scored as final evidence. The last two
changes affected exactly two rendered sample rows; their final text was read
again and the other 198 reviewed rows were confirmed byte-identical.

Each final row received a new explicit rationale and an event bound to its exact
record digest. Separate revision-specific event logs preserve append-only
history within each bound snapshot; cross-version decisions are not silently
superseded or reused.

## Binding and verification

The [offline validator source](../evidence/bilingual-training-audit-r1-validator-2026-10-15.txt)
revalidates accepted Stage A evidence; every sample's SQL, slots, semantic
anchors, expected columns, entities, source/catalogue digests, rendered and
normalized questions, renderer/provenance fields and record hash; group split
assignment; and the complete audit event contract. It projects all 8,000 real
source/catalogue identities to reproduce seed-42 selection without another
expensive text expansion. This identity projection is used only for sample
membership, never as substitute live/semantic evidence. CLI 20 already checked
the full text expansion's mechanical gates.

Both audit summaries pass the unchanged 95/90 thresholds. Pairing the initial
audit decisions with r1 records is rejected at the record-digest check.
Canonical output and publication-manifest paths remain absent.

- [Sample](../evidence/bilingual-training-audit-r1-sample-2026-10-15.jsonl):
  `a767a2ea9a3e7cb5d556a482352a90223fb41fc331660b0e1d2abda872f3d55d`.
- [200 decisions](../evidence/bilingual-training-audit-r1-decisions-2026-10-15.jsonl):
  `3d10f0d0e1f3db9e46367e7b924cc8e1232ef33f29361bf26d463dad2a76df62`.
- [Summary](../evidence/bilingual-training-audit-r1-summary-2026-10-15.json):
  `ad2418b58cde4b35072a531fac41adbcbd21abca6c5ab38b29ebcd0d6a69dbe7`.

## Test-first implementation and review

The initial regression run observed 14 failures and one passing historical
replay test. A stronger date-stop regression then failed on the 22 ambiguous
Vietnamese conversational windows; a sender-total regression failed on the
largest-single-transaction reading. All are now green. A gas-ranking synonym
test was corrected to recognize Vietnamese “nhiều gas nhất”; the original
missing-ranking wording still fails. An obsolete exact-copy test now checks
rendered owner/account/distinct semantics instead of pinning rejected wording;
generic funding/SQL-scope guards remain.

Final focused run: **36 passed in 0.59s**. Full `.venv/bin/pytest -q` on the
frozen final catalogue: **1,485 passed, 342 upstream warnings in 510.32s**.
Ruff check/format and `git diff --check` pass. Two earlier in-progress runs were
stopped after authoring edits and are not completion evidence. No product or
test edits followed the frozen final suite launch.

Review follows the user's native/no-subagent constraint: local self-review,
not a fresh independent reviewer. No unresolved finding is claimed as waived;
the rubric, thresholds and actual row-specific decisions are retained. These
controlled-language scores do not establish population naturalness, human
authorship, inter-rater agreement, empirical difficulty or solver quality.

## Next boundary

The approved correction/re-audit does not itself authorize canonical corpus
publication. Next is an explicitly scoped offline build/validate/reproducibility
step using the r1 event log and the accepted Stage A source. The separate human
benchmark-review requirement remains unchanged.

## Subsequent approved step

After this handoff, the user approved the separate offline canonical build.
Its publication and fresh validation evidence are recorded in
[canonical build report](bilingual-training-canonical-build-2026-10-15.md).
The non-publication statements above describe this r1 audit's historical boundary.
