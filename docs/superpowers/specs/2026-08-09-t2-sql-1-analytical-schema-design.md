# T2-SQL-1 Analytical Schema Design

## Context

Pivot #1 replaces the full Fuseki KG execution target with GoogleSQL over the
BigQuery public Ethereum dataset. The downstream dataset, linker, baseline,
evaluation, and demo phases need a stable semantic interface rather than raw
table knowledge embedded independently in every prompt or query.

The live public schema is usable but not sufficient by itself. Transactions,
blocks, token transfers, and contracts have different time and join fields;
token values are strings; token metadata lives in `amended_tokens`; and the
legacy project label table is an expiring address-only extraction filter from
before the accepted dictionary remediation.

## Goals

- Define one versioned, machine-readable GoogleSQL catalog.
- Map ontology-era semantic concepts and CQ01-CQ30 to physical BigQuery data.
- Define canonical analytical relations, keys, joins, types, and address roles.
- Make date pruning, dry runs, and maximum-bytes limits part of the contract.
- Detect upstream schema drift without rejecting harmless added columns.
- Preserve known semantic limitations explicitly instead of fabricating data.

## Non-goals

- Create or replace BigQuery tables, views, or routines.
- Upload the remediated entity dictionary.
- Benchmark query latency or execute billable representative workloads.
- Migrate the Phase 3 SPARQL template library.
- Add traces/log decoding for meta-transactions.

## Approaches considered

### Direct public-table prompts

This is the smallest setup, but every generated query must rediscover raw join
keys and safety predicates. It increases query complexity and makes unbounded
scans or semantically invalid role joins too easy.

### Materialized full monthly snapshot

A denormalized snapshot gives simple and stable SQL, but duplicates large
public tables, needs a refresh lifecycle, and introduces storage and mutation
before the semantic contract has been validated.

### Hybrid logical analytical layer — selected

Keep public BigQuery tables as facts, add a small managed entity-label
dimension, and expose date-bounded TVFs in T2-SQL-2. T2-SQL-1 records the layer
as a catalog and validates it without remote mutation. Parameterless dimensions
may use logical views; date-bounded facts use TVFs because logical views cannot
accept query parameters.

## Architecture

The design has four boundaries:

1. **Physical sources.** Five current public sources plus the planned managed
   `entity_labels_v1` dimension. Each source declares table kind, location,
   required columns/types, keys, partition metadata, and deployment state.
2. **Analytical relations.** Stable output fields for transaction, block, token
   transfer, contract, token, and entity-label semantics. Relations declare
   date parameters and precision rules independently of future SQL DDL text.
3. **Semantic graph.** Named join paths, role policies, ontology concept/property
   mappings, and CQ01-CQ30 support status.
4. **Validation boundary.** Offline structure/reference validation plus optional
   read-only BigQuery metadata conformance. T2-SQL-2 consumes the validated
   catalog when it builds labels and routines.

## Physical source contract

All live sources and the planned managed dimension are in location `US`.

| Source ID | BigQuery object | Kind | Time contract |
|---|---|---|---|
| `transactions` | `bigquery-public-data.crypto_ethereum.transactions` | partitioned table | `block_timestamp` |
| `blocks` | `bigquery-public-data.crypto_ethereum.blocks` | partitioned table | `timestamp` |
| `token_transfers` | `bigquery-public-data.crypto_ethereum.token_transfers` | partitioned table | `block_timestamp` |
| `contracts` | `bigquery-public-data.crypto_ethereum.contracts` | partitioned table | `block_timestamp` |
| `amended_tokens` | `bigquery-public-data.crypto_ethereum.amended_tokens` | logical view | parameterless small dimension |
| `entity_labels_v1` | configurable project dataset table | managed table | versioned dictionary snapshot |

`entity_labels_v1` is one row per lowercase Ethereum address. It retains
`chain_id`, `primary_label`, `owner`, `category`, `concept_class`,
`address_role`, aliases, confidence, verification date, and nested immutable
source provenance. The table also records the dictionary artifact digest.

## Analytical relation contract

### `transaction_facts(start_date, end_date)`

The relation exposes transaction and receipt identity, timestamp, sender,
nullable recipient, native value in wei, gas fields, receipt success, input,
transaction type, and block identity. Contract creation remains represented by
a null recipient plus `receipt_contract_address`.

### `block_facts(start_date, end_date)`

The relation exposes block identity, timestamp, beneficiary address, gas usage,
transaction count, and base fee. The source field is named `miner`, but the
semantic label is `beneficiary_address`; it is not sufficient evidence for
validator identity after proof-of-stake.

### `token_transfer_facts(start_date, end_date)`

The composite event key is `(transaction_hash, log_index)`. The relation keeps
raw string value, safe `BIGNUMERIC` projection, cast-valid flag, token standard
flags, symbol/name/decimals, and normalized fungible amount. Normalization is
valid only when value casts, decimals are within the supported range, and the
contract is ERC-20 rather than ERC-721. Invalid values remain observable and
never become zero.

### Parameterless dimensions

`contract_dimension(end_date)` limits contract deployments to those created
before the analytical end bound. `token_dimension` uses the maintained public
`amended_tokens` view. `entity_labels_v1` is a versioned managed dimension
created by T2-SQL-2.

## Time, cost, and dialect contract

- Dialect is GoogleSQL only.
- Date intervals are half-open: `[start_date, end_date)`.
- Bounds are typed `DATE`; timestamp predicates compare the partition column
  against `TIMESTAMP(start_date)` and `TIMESTAMP(end_date)`.
- The maximum permitted window is 31 days.
- The pinned evaluation window is `[2026-05-31, 2026-07-01)`.
- Every fact source participating in a join receives its own qualifying time
  predicate.
- Every execution path must dry-run first and apply a default 50 GiB
  `maximum_bytes_billed` cap.
- Fully qualified source objects come from the catalog, not model output.

## Join contract

- `transaction_to_block`: match both number and hash; filter both sources.
- `transaction_to_contract`: match normalized recipient and contract address;
  deduplicate redeployments by latest block before the requested end bound.
- `transfer_to_transaction`: match transaction hash and block identity; filter
  both sources.
- `transfer_to_contract`: normalized token address to contract address;
  contract creation must be before `end_date`.
- `transfer_to_token`: normalized token address to amended token address.
- `fact_address_to_entity`: lowercase fact address to the unique label address.

Join metadata declares cardinality and nullability. Optional dimensions use
left joins so missing labels or metadata do not delete fact rows.

## Role semantics

- `operational`: eligible for protocol execution and protocol endpoint filters.
- `treasury`: eligible for owner attribution and explicitly described exchange
  treasury/custody flows, never substituted for a protocol operational address.
- `token`: eligible as a token contract or transfer asset, never substituted for
  a protocol endpoint.

Queries involving both an exchange and a protocol use distinct role predicates
on each side. The result language must not generalize one known treasury address
to all activity of its owner.

## Competency coverage

Every CQ receives a support status and mapping:

- `supported` when the current source and label contract prove the semantics;
- `coverage_gap` when the schema supports the query shape but accepted labels do
  not currently provide enough operational endpoints;
- `unsupported` when the substrate cannot prove the requested semantics.

CQ24 is unsupported because transaction sender is not a reliable
meta-transaction initiator/executor pair. CQ17 is mapped to block beneficiary,
not validator identity. Questions involving mixers, NFT marketplaces, or MEV
actors remain coverage gaps when the role-aware dictionary lacks suitable
operational rows. Confidence questions use categorical confidence, not a
fabricated numeric score.

## Validation and error handling

Catalog validation fails on:

- unknown dialect, location, source kind, BigQuery type, role, or CQ status;
- duplicate IDs or missing CQ01-CQ30 entries;
- fields, joins, semantic mappings, or CQs referencing unknown objects;
- a partitioned fact without half-open parameter/date metadata;
- missing source keys or invalid join conditions;
- an invalid evaluation window or a cap other than a positive integer;
- a managed entity schema missing chain, role, or provenance fields.

Live validation compares required field names, types, and modes. Missing fields
or incompatible types fail; additional upstream fields are ignored. Planned
managed objects are explicitly deferred until T2-SQL-2 instead of falsely
reported as live.

## Testing strategy

Tests are written before implementation and run offline by default:

- catalog shape and exact CQ coverage;
- reference integrity across sources, relations, joins, semantics, and CQs;
- date-window boundary cases and maximum span;
- role and precision invariants;
- live-schema drift using fake metadata for missing, changed, and extra fields;
- CLI success/failure behavior without credentials.

After offline tests pass, a read-only live run validates the five public source
schemas. Representative SQL is dry-run for transaction/block and token transfer
join paths and must remain below the 50 GiB cap. Full pytest, Ruff, and whitespace
checks close the task.

## Acceptance criteria

- The committed catalog completely describes the approved contract.
- CQ01-CQ30 are each explicitly supported, gap-marked, or unsupported.
- Offline and live schema validation pass with documented evidence.
- Representative dry runs validate and remain within the per-query cost cap.
- No remote data object is created or modified by T2-SQL-1.
- Task status and decision log record the contract and its limitations.
