# Stage A v2 Batched Transaction-Hash Verification Design

**Status:** Approved in chat on 2026-10-10; written specification pending user review.

**Extends:**

- `docs/superpowers/specs/2026-08-09-t3-2-witness-grounded-stage-a-design.md`
- `docs/superpowers/specs/2026-10-09-stage-a-v2-25-intents-design.md`

## Context

Stage A v2 now has a genuine BigQuery-derived value pool containing 45 unique
block numbers and 45 unique transaction hashes from the half-open window
`[2026-06-15, 2026-06-16)`. The analytical layer was redeployed successfully,
but an exact dry-run of the 170 logical witness groups estimated
`119,135,658,992` bytes (`110.953729 GiB`). This exceeds the immutable 96 GiB
aggregate acceptance cap by `14.953729 GiB`, so the live workflow correctly
stopped before execution.

The main avoidable duplication is `T_TX_BY_HASH`: 45 singleton logical
witnesses each scan the same daily transaction partition. Together they account
for `18,239,157,000` estimated bytes (`16.986539 GiB`), although all 45 hashes
can be checked in one bounded scan. Replacing those 45 physical scans with one
batch scan is expected to reduce the aggregate estimate to approximately
`94.344669 GiB`. That estimate is planning evidence only; a fresh BigQuery
preflight remains the acceptance authority.

## Decision

Preserve all 170 logical witness obligations, but allow the Stage A v2 verifier
to satisfy the 45 `T_TX_BY_HASH` singleton obligations with one physical
BigQuery query. The batch query must return the original template columns plus
an internal logical-group identifier, and the verifier must prove that every
requested group has exactly one matching row with the requested transaction
hash.

All other templates keep the existing one-physical-query-per-group behavior.
Stage A v1 keeps the existing verifier plan unchanged. The per-query 20 GiB cap,
aggregate 96 GiB cap, cache prohibition, immediate re-dry-run, exact-column
checks, and all non-empty requirements remain unchanged.

## Goals

1. Keep 170 logical witness groups and prove every one of the 1,000 records.
2. Reduce duplicated BigQuery scans without raising either byte cap.
3. Bind initial preflight, immediate preflight, execution, and propagated record
   evidence to the exact physical SQL and logical groups they cover.
4. Expose a dry-run-only Stage A v2 CLI mode so cost approval occurs before any
   live witness execution.
5. Preserve Stage A v1 bytes, behavior, paths, and historical evidence.

## Non-goals

- Raising the 20 GiB per-query or 96 GiB aggregate cap.
- Treating the value-pool acquisition query as proof of the generated SQL.
- Batching templates other than `T_TX_BY_HASH` in this change.
- Reusing query cache, materializing a new Ethereum fact table, or weakening
  exact result validation.
- Starting bilingual audit, canonical corpus publication, or B1/B2 training.

## Logical Witnesses and Physical Queries

A logical witness remains the existing `WitnessGroup`: one exact record or one
limit-monotonic group. A physical query is the SQL job used to prove one or more
logical witnesses.

The default physical planner maps each logical witness to its current SQL. The
Stage A v2 planner replaces all `T_TX_BY_HASH` physical queries with one batch
query and leaves every other mapping unchanged. For the current candidate this
means 170 logical witnesses and 126 physical queries.

Each physical query has:

- a deterministic physical query ID;
- the SHA-256 digest of its exact GoogleSQL text;
- an ordered, non-empty set of covered logical group IDs;
- a proof kind: `single` or `tx_hash_batch`;
- the exact SQL sent to BigQuery.

The planner fails closed if a proposed hash batch contains another template,
repeated group IDs, repeated hashes, inconsistent date bounds, a non-singleton
logical group, or fewer than two members. SQL and identifiers are deterministic
under input reordering.

## Batch Query Semantics

The query builds a typed in-query relation of requested
`(witness_group_id, transaction_hash)` pairs, scans the existing bounded
`transaction_facts(start_date, end_date)` table function once, and joins on the
transaction hash. It returns:

1. the internal `witness_group_id`; then
2. exactly the original `T_TX_BY_HASH` expected columns in their original order.

The verifier rejects the whole run unless:

- the returned schema is exactly the internal ID followed by the template
  schema;
- every requested group ID appears exactly once;
- no unrequested group ID appears;
- every returned transaction hash equals the value requested for that group;
- every requested group therefore has one non-empty exact proof; and
- the physical job reports `cache_hit=false`.

The internal group column is verification metadata only. It is not added to the
generated record SQL or training target.

## Preflight, Execution, and Caps

Dry-run accounting operates on physical queries, not logical groups. Every
physical query is dry-run once during the complete preflight. The verifier
rejects before execution when any physical query exceeds 20 GiB or the sum of
all unique physical-query estimates exceeds 96 GiB.

After approval, live verification repeats the complete preflight, then for each
physical query:

1. immediately dry-runs the identical SQL again;
2. verifies the SQL digest and logical membership match the approved plan;
3. enforces the 20 GiB cap again;
4. executes with Standard SQL, cache disabled, and
   `maximum_bytes_billed=20 GiB`; and
5. validates the result according to its proof kind.

The initial and immediate estimates may differ because BigQuery metadata can
change. Consistency means they refer to identical SQL bytes, physical query ID,
and logical membership; both estimates must independently pass their guards.
No execution begins unless the complete initial preflight passes.

## Evidence Graph and Artifact Accounting

Provider-neutral evidence retains one logical proof per witness group while
allowing multiple logical proofs to reference one physical job. Each dry-run and
execution edge records the physical query ID, SQL digest, covered group IDs,
BigQuery job ID, location, byte metrics, cache status where applicable, and
timestamps or latency metrics already available from the job.

Each accepted record keeps its existing logical witness ID and witness record
ID and additionally references the physical query ID and SQL digest that proved
it. The 45 hash records remain `live_exact`; sharing a scan does not turn them
into limit-monotonic proofs.

`generation-config-v2.json` includes the complete physical-query evidence graph
without raw result rows. Its summary reports:

- `witness_count=170` for logical obligations;
- `physical_query_count=126` for the expected current plan;
- initial preflight bytes summed once per physical query;
- processed and billed bytes summed once per physical execution; and
- zero cache hits.

Artifact validation rejects missing or duplicate physical query IDs, unknown or
multiply-proven logical groups, mismatched SQL digests, incomplete batch
membership, repeated accounting, cache hits, and any logical group not connected
to both preflight and execution evidence.

## CLI and Approval Boundary

`scripts/09_generate_stage_a_v2.py` gains a dry-run-only preflight mode for
evidence-backed pools. It creates the v2 records and physical plan, contacts
BigQuery only for dry-runs, prints deterministic JSON containing logical count,
physical count, byte estimates, caps, and per-template totals, and writes no
accepted artifacts.

The existing `--live` mode repeats preflight before execution. It never treats a
previous local report as authority and writes accepted artifacts only after all
physical jobs and all 170 logical proofs pass. Offline candidate mode remains
provider-isolated.

## Evidence Pool

The implementation branch will add
`data/dataset/raw/stage-a-v2-evidence-pools.json`, SHA-256
`1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8`.
It contains exactly 45 unique block entries and 45 unique transaction-hash
entries. Every entry has exactly `value`, `source`, and `evidence`; the evidence
references BigQuery acquisition job
`6c4439f8-ce2b-475d-949f-8b9381f11a05`, its row, location `US`, and the pinned
window. Existing address and token entries remain unchanged.

## Failure Handling

Planning, preflight, execution, result validation, graph validation, and artifact
publication all fail closed. A failure produces no accepted replacement and
does not modify Stage A v1 or the v2 candidate. Specifically, the workflow stops
on:

- batch planner ambiguity or non-determinism;
- per-query or aggregate cap overflow;
- preflight/execution SQL or membership mismatch;
- missing, duplicate, unexpected, or wrong-hash batch rows;
- schema drift, empty results, invalid count witnesses, or cache hits;
- incomplete logical-to-physical evidence edges; or
- any Stage A v2 generation or artifact validation failure.

## Testing and Verification

Implementation follows RED, GREEN, REFACTOR. Unit tests use fake BigQuery jobs
to prove deterministic planning, one batch dry-run and execution, exact group
coverage, cap accounting without multiplication, immediate re-dry-run ordering,
job/query provenance, strict batch-result validation, v1 compatibility, and
artifact graph rejection cases.

Workflow tests prove that offline commands remain provider-isolated, preflight
never executes or writes accepted outputs, and live publication remains
fail-closed. Repository verification includes focused tests, all 1,613+ tests,
Ruff format/check, JSON validation, artifact hashes, v1 byte preservation, and
`git diff --check`.

After implementation, the operator runs the new exact preflight with the genuine
pool and reports the measured estimate. Live execution still requires a separate
approval after that report. Acceptance, bilingual audit, deterministic 8,000-row
publication, and training remain later gates.
