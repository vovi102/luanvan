# T3.2 Witness-Grounded GoogleSQL Stage A Design

## Context

The pre-pivot T3.2 scaffold emits SPARQL records, uses 2024 windows, detects
entities as RDF IRIs, and labels unexecuted queries as verified. T3.1 now exposes
25 typed GoogleSQL templates over the accepted BigQuery analytical layer. Stage
A must migrate atomically and produce useful non-empty training targets without
turning 1,000 records into a multi-terabyte verification run.

Live T3.1 evidence also constrains the achievable distribution. A month-wide
probe found no exchange-to-DEX, mixer-to-DEX, or cross-exchange rows, and the
bridge-outflow template remained empty after a 52.64 GB scan. Only
`T_TOKEN_AFTER_NATIVE_FUNDING` and `T_REPEATED_PAIR_FLOW` currently have hard
examples. With a 10% per-template cap, 20% hard is therefore the maximum honest
non-empty share; the old approximate 25% target is infeasible until label
coverage improves.

## Considered approaches

1. Execute every generated SQL independently. This is the most literal reading
   of the old acceptance text, but repeated enriched token scans would consume
   multiple TiB and exceed the unbilled Sandbox monthly quota.
2. Keep offline rendering only. This is cheap and deterministic but provides no
   evidence that generated slot combinations return data.
3. Generate deterministic limit-monotonic groups and execute one live witness
   per group. This preserves a checkable proof of non-emptiness while sharing
   scans only where the SQL relationship is formally safe. This is selected.

## Candidate contract

The generator emits exactly 1,000 deterministic candidate records for seed 42.
Each record contains `id`, `template_id`, `category`, `difficulty`, typed
`slot_values`, `entities_used`, `sql`, `nl_seed`, `schema_elements`, `cq_ids`,
`template_sha256`, `record_sha256`, `generation_seed`, `witness_group_id`, and a
nullable `verification` object. IDs and record hashes exclude live metrics, so
candidate identity remains reproducible.

`entities_used` is derived from slot definitions, not RDF string prefixes. It
captures Ethereum addresses, transaction hashes, token symbols, owners,
categories, and concept classes. No entity value may appear in more than 50 of
the 1,000 records.

The accepted allocation is exact:

- easy: 350 records across six live templates;
- medium: 450 records across eight live templates;
- hard: 200 records across the two live hard templates;
- no template exceeds 100 records.

Nine sentinel or coverage-gap templates are excluded from Stage A until they
have a live non-empty witness. Their presence in T3.1 remains useful for query
shape/CQ coverage but they must not teach empty training targets.

## Value pools and rendering

A committed `value_pools.json` pins the June 2026 window and live-derived values
with acquisition notes. The address pool contains treasury addresses proven to
have both incoming and outgoing transactions on the example day. Token symbols
are checked by the verifier. The generator uses the T3.1 typed renderer, never
formats SQL directly.

For templates with `n`, records vary `n` from 1 upward. Entity-bearing templates
split records across enough pool values to satisfy the 5% entity cap. The count
template has no `n`, so it uses distinct half-open windows within the pinned
month. SQL uniqueness must come from typed slot values; comments or inert
predicates do not count as diversity.

## Live witness proof

Records are grouped by rendered semantics after removing only the `n` slot. The
group witness is the record with the smallest positive `n`. If that exact query
returns at least one row, every otherwise-identical query with a larger limit is
non-empty. This is recorded as `live_limit_monotonic`, with the exact witness ID
and metrics. Records without `n` form singleton groups and use `live_exact`.

The verifier first dry-runs every witness and rejects the entire run before any
execution if one query exceeds 20 GiB or all witnesses exceed 96 GiB. It then
re-dry-runs immediately before each execution, disables cache, verifies exact
result columns, and applies the non-empty predicate. For
`T_COUNT_TX_IN_RANGE`, a returned row is insufficient: `transaction_count` must
be positive. No propagated record claims an exact result count; it stores only
`non_empty=true`, the witness row count, proof mode, bytes, latency, and UTC
verification timestamp.

## Outputs

- `data/dataset/raw/synthetic-stage-a.jsonl`: 1,000 verified records.
- `data/dataset/raw/generation-config.json`: seed, allocation, input hashes,
  pools hash, budget, and artifact digest.
- `data/dataset/raw/stats.md`: distributions, entity maxima, witness counts,
  bytes, latency, and excluded templates.
- `notebooks/08_generate_synthetic.ipynb`: unexecuted GoogleSQL workflow.

## Failure handling and tests

Generation fails closed on invalid allocations, duplicate SQL/IDs/hashes,
template or entity caps, untyped pool values, and non-determinism. Verification
fails before execution on budget overflow and during execution on schema drift,
empty witnesses, invalid count values, cache hits, or an unsafe propagation
relationship.

Unit tests use fake BigQuery jobs to prove preflight ordering, caps, exact versus
monotonic modes, result checks, deterministic hashes, distributions, and artifact
round trips. Live completion requires the final 1,000-record artifact, 100%
non-empty proofs, zero cache hits, and full repository verification.

