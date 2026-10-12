# Stage A v2 Account-Pair Evidence Design

**Status:** Approved in chat on 2026-10-12.

**Extends:**

- `docs/superpowers/specs/2026-10-09-stage-a-v2-25-intents-design.md`
- `docs/superpowers/specs/2026-10-10-stage-a-v2-batch-verification-design.md`
- `docs/superpowers/specs/2026-10-11-stage-a-v2-supported-intent-revision-design.md`

## Context

The revised Stage A v2 live acceptance attempt failed closed at record
`syn-v2-000436`, template `T_TX_BETWEEN_ACCOUNTS`. The generated pair
`0x8fca4ade3a517133ff23ca55cdaea29c78c990b8` and
`0x77021d475e36b3ab1921a0e3a8380f069d3263de` returned no rows in the
half-open window `[2026-06-15, 2026-06-16)`. No accepted artifact was written.

The existing generator selects `account` and `account_b` independently from
the `ethereum_address` pool. Each address has individual activity evidence,
but that evidence does not establish a transaction edge between the two
selected addresses. The acceptance failure therefore exposed a provenance
model defect, not an unsupported intent.

A bounded diagnostic was run only after confirming that project
`nl2sparql-thesis` had `billingEnabled=false` and no billing account. The
diagnostic used Standard SQL, disabled cache, and enforced a 1 GiB maximum
bytes billed cap. Its dry-run estimate was `215,950,984` bytes. The single
execution job was:

- job ID: `d7aa2151-18e4-4f3f-99c4-2c255bdbfe0e`;
- location: `US`;
- query SHA-256:
  `d85c553b8fef8621e68f847b31179b80e4b7bbab6397c7c8ed5a01b06569436d`;
- processed bytes: `190,675,508`;
- billed bytes: `190,840,832`;
- cache hit: `false`; and
- result: 1,000 transaction-bearing unordered pairs, from which the first 40
  pairs with globally distinct endpoints were selected deterministically.

This is sufficient to preserve `T_TX_BETWEEN_ACCOUNTS` without weakening any
validation gate or fabricating relationships.

## Decision

Add a relationship-level `account_pair` evidence pool and make
`T_TX_BETWEEN_ACCOUNTS` consume one complete entry atomically. An entry binds
both account endpoints, the exact date window, and the BigQuery evidence that
proved at least one transaction between those endpoints in that window.

The generator must never derive this template's two endpoints by independently
indexing `ethereum_address`. It must never take the endpoints from one pair and
the dates or evidence from another pair. The existing `ethereum_address` pool
continues to serve templates whose contract needs one independently verified
address.

The candidate is regenerated under the existing v2 candidate lifecycle and
paths. No v3 lifecycle is introduced. The failed live attempt is not retried.
A new live acceptance remains forbidden until the regenerated candidate has
passed local verification, a diagnostic-only check of all 170 logical
witnesses, and a fresh preflight that the user approves.

## Account-Pair Schema

`data/dataset/raw/stage-a-v2-evidence-pools.json` gains an `account_pair`
array containing exactly 40 entries. Every entry has exactly these top-level
fields:

```json
{
  "account": "0x...",
  "account_b": "0x...",
  "start_date": "2026-06-15",
  "end_date": "2026-06-16",
  "source": "BigQuery nl2sparql_analytics.transaction_facts",
  "evidence": {
    "project": "nl2sparql-thesis",
    "location": "US",
    "job_id": "d7aa2151-18e4-4f3f-99c4-2c255bdbfe0e",
    "query_sha256": "d85c553b8fef8621e68f847b31179b80e4b7bbab6397c7c8ed5a01b06569436d",
    "result_row": 1,
    "transaction_count": 24266,
    "first_seen_at": "2026-06-15T00:00:11+00:00",
    "last_seen_at": "2026-06-15T23:59:59+00:00",
    "total_bytes_processed": 190675508,
    "total_bytes_billed": 190840832,
    "cache_hit": false,
    "billing_enabled": false,
    "maximum_bytes_billed": 1073741824
  }
}
```

All 40 entries share the diagnostic job and exact half-open window but have a
distinct `result_row`, unordered endpoint pair, and positive
`transaction_count`. `first_seen_at` and `last_seen_at` must fall within the
entry's window. Both endpoint strings are lowercase 20-byte Ethereum addresses,
must differ within an entry, and must not occur in another selected entry. The
entry orders endpoints lexicographically, matching the diagnostic query's
`LEAST`/`GREATEST` projection.

Relationship provenance is valid only as a complete object. A string, partial
object, unknown field, empty job/query identifier, non-positive count, cache
hit, enabled billing flag, inconsistent byte metrics, invalid timestamp, or
window mismatch fails closed. The validator does not contact BigQuery to
reinterpret malformed provenance.

## Generation and Atomicity

For each of the 40 allocated `T_TX_BETWEEN_ACCOUNTS` records, generation takes
the canonical account-pair entry at the same index and copies all four bound
slot values:

- `account`;
- `account_b`;
- `start_date`; and
- `end_date`.

The template's `n` values remain deterministic and within the existing slot
range. Pair identity already makes all 40 rendered SQL strings unique, so `n`
does not need to manufacture uniqueness through independent pool cycling.

Canonicalization sorts complete pair entries as indivisible values. It may not
sort endpoint arrays separately or reconstruct pairs after sorting. Record
`entities_used`, witness identity, SQL rendering, hashes, and the candidate
manifest must all derive from the same atomic slot assignment. The candidate
manifest binds the new complete value-pool digest.

Candidate generation for this revision requires the evidence-backed v2 pool.
A pool without `account_pair`, with fewer or more than 40 entries, or with an
invalid entry cannot generate or validate the revised Stage A v2 candidate.
This stricter rule applies to Stage A v2 only and does not change Stage A v1.

## Diagnostic-Only Witness Verification

Before the new acceptance preflight, the workflow must execute all 170 logical
witness obligations in a diagnostic-only mode. This mode uses the same
126-physical-query plan, exact-column validation, non-empty checks, cache
prohibition, initial complete preflight, immediate re-dry-runs, and 20 GiB per
query and 96 GiB aggregate caps as acceptance.

Diagnostic execution differs from acceptance only at publication:

- it never calls the accepted artifact writer;
- it never creates, replaces, or partially writes any accepted v2 path;
- it emits a canonically serialized evidence report with a fixed schema,
  containing all dry-run and execution job metadata, processed/billed bytes,
  cache status, logical coverage, and the first failed gate if any; and
- it is explicitly labeled diagnostic evidence, not acceptance evidence.

Before any diagnostic execution, the workflow checks billing state read-only.
It proceeds only when `billingEnabled=false` and no billing account is linked.
Every query uses Standard SQL, cache disabled, and
`maximum_bytes_billed=21,474,836,480`. The initial aggregate preflight must not
exceed `103,079,215,104` bytes. Provider quota failure is terminal for the run;
there is no automatic retry. A failed or incomplete diagnostic produces no
accepted artifact and does not authorize acceptance.

The diagnostic report must distinguish dry-run estimates from actual processed
and billed bytes. It records physical jobs once even when one job proves
multiple logical witnesses. Success requires all 170 logical witnesses to have
valid, non-empty evidence. Any other empty template is reported by record,
template, slots, query ID, and job metadata, then the workflow stops without
lowering a gate.

## Candidate Regeneration and Preflight

After the pair schema and generator pass their RED-to-GREEN tests:

1. regenerate the three existing `*-v2-candidate*` artifacts from the genuine
   evidence pool;
2. build twice into separate temporary directories and require byte-identical
   data, config, and stats;
3. validate exactly 1,000 records, 25 intents, difficulty totals `350/450/200`,
   170 logical witnesses, and 126 physical queries;
4. run the complete diagnostic-only witness verification;
5. run the full repository test, lint, format, JSON, immutable-artifact, and
   whitespace checks; and
6. run a fresh dry-run-only acceptance preflight and report exact counts,
   total bytes, maximum query, caps, and gross reference-price estimate while
   stating that billing is not linked.

Preflight writes no accepted or candidate artifact. After reporting the fresh
preflight, the workflow stops for explicit user approval. It does not run the
acceptance command in the same approval.

## Failure Handling

Every new boundary fails closed:

- missing, empty, malformed, duplicated, or independently assembled pair data;
- pair/window provenance that does not bind both endpoints;
- invalid address, date, job, query, row, count, timestamp, byte, cache, or
  billing fields;
- candidate records that do not match their bound account-pair entry;
- empty, malformed, or unexpected diagnostic results;
- per-query or aggregate cap overflow;
- free-quota/provider failure;
- changed SQL digest or logical membership between dry-run and execution; or
- any attempt to publish accepted artifacts from diagnostic evidence.

Failure must leave these paths absent:

- `data/dataset/raw/synthetic-stage-a-v2.jsonl`;
- `data/dataset/raw/generation-config-v2.json`; and
- `data/dataset/raw/stats-v2.md`.

It must also preserve Stage A v1 and every unrelated evidence pool entry.

## Testing

Implementation follows RED, GREEN, REFACTOR. Tests must prove:

- one complete pair entry supplies both endpoints and both date bounds;
- reversing or reordering pool input cannot mix pair members or windows;
- the old independent-address behavior fails the new regression test;
- missing, extra, malformed, inconsistent, or relationship-free provenance
  fails closed;
- empty, malformed, duplicate, reordered-column, and unexpected diagnostic
  results fail closed;
- diagnostic failure cannot write any accepted artifact, including partial
  output from an earlier physical job;
- the 40 generated records bind the 40 verified entries and remain unique;
- all 170 logical witnesses and 126 physical queries are derived from the
  regenerated candidate;
- candidate double-builds are byte-identical;
- Stage A v1 and non-pair evidence remain unchanged; and
- acceptance publication still requires a newly executed passing live report,
  never the diagnostic report.

## Documentation and Commit Boundaries

The implementation uses small commits for the pair contract/tests, atomic
generation, diagnostic-only workflow, regenerated candidate, diagnostic
evidence, local verification, and final preflight evidence. The progress ledger,
task record, backlog, and decision log report measured facts and preserve both
failed acceptance attempts as historical evidence.

No commit merges to `main`, pushes a branch, creates a pull request, performs
the final acceptance run, starts the 100-English plus 100-Vietnamese audit, or
builds the 8,000-record corpus.
