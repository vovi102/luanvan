# Stage A v2 supported-intent revision — 2026-10-14

Implements the user-approved [coverage proposal](stage-a-v2-hard-intent-coverage-audit-2026-10-14.md)
and [native plan](../superpowers/plans/2026-10-14-stage-a-v2-supported-intents.md).
This is a training-population/CQ-coverage revision, not benchmark or model evaluation.

## Contract and provenance

The historical default `src/nl2sparql/sql/catalog/ethereum_analytics.json`
remains version 1.0.0 with exact CQ01–CQ30 and SHA-256
`db8393aa7258d1331387eff9825e22ca729daf93234419f00d7dd538196cb3dd`.
Benchmark/model consumers and their existing hashes are unchanged.

Training template validation explicitly selects
`src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json`, version 1.1.0
with exact CQ01–CQ34, SHA-256
`2c800d4c1af74f24aed73bcb7881f1cd514ab068fecdb301d6c478fd3ce34fa0`.
The first 30 definitions are structurally identical to the historical catalogue.
Both versions retain exact-ID guards; a mismatched version/set or unknown
version is rejected. CQ31–CQ34 are GoogleSQL extensions only.

| Intent | CQ | Records | Scope |
|---|---|---:|---|
| `T_TOKEN_AFTER_NATIVE_FUNDING` | CQ31 | 33 | Successful positive native treasury funding, followed by token transfer from funded address at/after timestamp and strictly before duration bound |
| `T_OWNER_NET_NATIVE_FLOW` | CQ32 | 34 | Incoming/outgoing/net external native wei on labeled treasury addresses, rank absolute net; not owner balance change |
| `T_TREASURY_NATIVE_COUNTERPARTY_CONCENTRATION` | CQ33 | 33 | Recipient count-share HHI over successful positive native transfers; minimum 10 transactions per owner; no AML/actor inference |
| `T_TREASURY_TOKEN_COUNTERPARTY_DIVERSITY` | CQ34 | 33 | Distinct recipient/contract counts and transfer-event counts; no sum of heterogeneous token amounts |

The three retired templates no longer claim CQ13/CQ22/CQ26 coverage. Funding
no longer claims the opposite-direction historical CQ29. Hard is a
compositional SQL rubric, not measured B1/B2/B3 empirical difficulty.

All other template objects are structurally unchanged. Raw template-library
SHA-256: `11a03a487e53248fe9549504e8f5054b4760b3d074343a5d4c59291782c0a8b9`.
Eight bilingual patterns per template remain (25 × 2 × 4 = 200); exactly
24 retired patterns were replaced and eight funding patterns corrected.
Bilingual catalogue SHA-256:
`305f98ab651b0651b02aaecf2bf2a6460fe8e42e6f903e83de872f379d29b10e`.

## Candidate regeneration

Two regeneration runs produced identical bytes. Exactly 133 of 1,000 records
changed, at the existing allocation positions. Seed 42, 25 intents and
difficulty 350/450/200 remain. Actual planner output is 206 logical witness
groups / 126 physical queries, not a forced manifest count.

- Candidate JSONL: `c20be57c884baf0c8b4dac3d6f7f81031becc7df030842963413d29c6dfc7c59`.
- Candidate manifest: `8b14614b447301b0a49a99bd01c8dc7e8c23b4710b6595386624636d0357d40d`.
- Candidate stats: `c64bb37333bb1590dd4e01e8446a062885b590ad6095326d80a567a0a9a53187`.
- Unchanged evidence pools: `a6b827732320c18a274323fe4f5a5d60ea07d380065c6c1c4707b905a081fbca`.

V1 data/config/stats bytes, historical evidence, benchmark wording/gold and
model results are unchanged. Current bilingual patterns cannot be paired with
historical V1 funding SQL: the SQL-drift guard deliberately rejects that mix.
Unit tests use the existing synthetic accepted-v2 fixture; no fabricated live
evidence is published. Canonical 8,000 bilingual records are not published.

## Verification and execution boundary

Local verification: 1,442 tests passed (342 upstream warnings), Ruff and
`git diff --check` passed, offline template and bilingual catalogue validation
passed. The bounded diagnostic stopped at a separate unchanged intent. Initial
dry-run (126 physical queries) estimated 81,554,265,475 bytes (~75.953 GiB)
under the 96 GiB aggregate cap. Maximum query is funding:
15,091,902,950 bytes under the 20 GiB per-query cap. Cache and SDK query/job/
result retries are disabled in the one-shot diagnostic client wrapper;
these settings are not claimed as defaults of the production SDK client.
Billing is checked disabled and unlinked before provider work.

## Diagnostic result: four revised intents pass; acceptance remains blocked

The [diagnostic report](../evidence/stage-a-v2-supported-intents-diagnostic.json)
has status `failed` and validates offline against the exact new candidate.
SHA-256: `64a824e73b13505fadc2788d01f4fd121545ea081a38ca92ede98171eb0d04ce`.
All four revised production intents executed with one non-empty witness each:

- CQ31 funding: job `cc00b130-4385-4a8b-995f-b7aba93e4557`.
- CQ32 net flow: job `713a9d6f-f9c1-48b5-a22b-a28f2096f9d8`.
- CQ33 concentration: job `89218485-7384-4af8-8f88-4a87a710f0ff`.
- CQ34 diversity: job `ffe7c005-d2c6-4082-9c27-997ca683b791`.

Execution then stopped on physical query 94, witness `syn-v2-000759` of
unchanged medium intent `T_LARGE_TX_TO_CLASS`. Its exact parameters are
`concept_class=DEXProtocol`, `value_wei=1000000000000000000` (1 ETH),
`n=1`, window `[2026-06-15, 2026-06-16)`. SQL executed successfully but
returned zero rows, so the non-empty gate correctly rejected it.
This does not establish absence for every class/window/threshold.

The report records 93 successful physical executions / 164 logical results,
not complete 126/206 acceptance. Successful-query totals are 77,942,707,806
processed / 78,341,210,112 billed bytes, zero cache hits. The recorder excludes
the rejected empty execution from those totals; its separate
[last-job metadata](../evidence/stage-a-v2-supported-intents-last-job.json)
(SHA-256 `ea87dcd478736c2fda80eb189de708eb91946bda9dcbad2fca6e9363cee3fc47`)
preserves job `fb114172-bdb9-4521-8407-9448604c4ef3`, no SQL errors,
389,805,715 processed / 390,070,272 billed bytes, no cache hit.
Actual 94-execution totals including the empty job are therefore
78,332,513,521 processed / 78,731,280,384 billed bytes. No execution was retried.

The [initial preflight](../evidence/stage-a-v2-supported-intents-initial-preflight.json)
is explicitly pre-diagnostic, not a final acceptance preflight. No provider
work continued after failure and no post-diagnostic preflight was run.
All three accepted-v2 paths remain absent. Final `--live` is not ready for approval.

Next proposed scope is a bounded coverage audit for `T_LARGE_TX_TO_CLASS`
(class/window/threshold and existing CQ21/CQ25 mapping), followed by a
separately justified evidence-pool or contract correction. The approved scope
required the other 21 templates to remain unchanged; that next correction is
not silently included in this implementation.
