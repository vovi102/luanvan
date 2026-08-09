# T2-SQL-2 Label-Enriched Analytical Layer Design

## Context

T2-SQL-1 established a machine-readable schema contract but deliberately left
`entity_labels_v1` deferred. The current project has only the legacy
`nl2sparql_kg` dataset, whose 60-day default expiration and address-only
`labeled_addresses` table are unsuitable for a durable semantic interface. No
analytical routines currently exist.

The accepted dictionary contains 5,135 unique Ethereum addresses, 8,538 aliases
and explicit `operational|treasury|token` roles. Its raw SHA-256 is
`190f73a91b7affa8b8396cc189e4a6b332dc6f7f0109037a0d44edb14531c536` at design
time. Deployment must preserve that evidence and must not silently overwrite an
accepted label version.

## Goals

- Publish the accepted dictionary through a stable, durable BigQuery contract.
- Make deployment deterministic, idempotent, inspectable, and recoverable.
- Implement the six T2-SQL-1 canonical relations as views/TVFs.
- Add simple label-enriched transaction and token-transfer interfaces for
  NL2SQL generation.
- Validate metadata and dry-run safety before declaring objects usable.

## Non-goals

- Delete or migrate the legacy `nl2sparql_kg.labeled_addresses` table.
- Automatically garbage-collect previous label snapshots.
- Execute representative fact queries or claim latency/result correctness.
- Decode traces/log calldata or close CQ24's meta-transaction limitation.
- Materialize or duplicate the large public Ethereum fact tables.

## Approaches considered

### Replace one mutable label table

This is operationally small, but a failed or incorrect upload replaces the last
known-good state and makes audit/rollback harder.

### Append version columns to one table

History remains available, but every consumer must select the current version;
missing that predicate can duplicate labels and fact rows.

### Immutable snapshots behind a stable view — selected

Each dictionary digest maps to one immutable table. A stable view changes only
after the new snapshot passes validation. Same-digest deploys reuse the existing
snapshot, while rollback only repoints the view. This cleanly separates data
acceptance from consumer naming.

## Object model

All managed objects live in `nl2sparql-thesis.nl2sparql_analytics`, location
`US`. The durable contract requires no default table or partition expiration;
the current Sandbox exception is documented below.

| Object | Kind | Purpose |
|---|---|---|
| `entity_labels_snapshot_<sha12>` | table | immutable accepted dictionary rows |
| `entity_labels_v1` | view | stable label interface |
| `token_dimension` | view | explicit public token metadata projection |
| `transaction_facts` | TVF | bounded transaction/receipt facts |
| `block_facts` | TVF | bounded block facts |
| `contract_dimension` | TVF | latest contract deployment before end bound |
| `token_transfer_facts` | TVF | bounded precision-safe transfer facts |
| `labeled_transactions` | TVF | transaction facts with flat endpoint labels |
| `labeled_token_transfers` | TVF | transfer facts with endpoint and token labels |

The label table schema is explicit:

- required scalar: `address`, `chain_id`, `primary_label`, `owner`, `category`,
  `concept_class`, `address_role`, `confidence`, `verified_date`,
  `dictionary_sha256`;
- repeated string: `aliases`;
- repeated record `sources`: `name`, `url`, `revision`, `locator`,
  `retrieved_date`, `note`.

Rows use `address_lower` as `address`. The source artifact digest is repeated on
each row so an aggregate validation query can detect mixed or unexpected data.

## Routine semantics

### Bounds

TVFs use typed `DATE` parameters and half-open timestamp predicates. A shared
one-row bounds CTE rejects null, reversed, empty, or greater-than-31-day spans
with GoogleSQL `ERROR`. Each partitioned source used by a routine receives its
own direct predicate.

### Core facts and dimensions

`transaction_facts` and `block_facts` project the catalog-owned columns without
`SELECT *`. Native values remain exact `NUMERIC`. `contract_dimension` applies
the end bound and `ROW_NUMBER` to choose the newest row per normalized address.
`token_dimension` projects the maintained `amended_tokens` view.

`token_transfer_facts` retains `value_raw`, uses `SAFE_CAST(... AS
BIGNUMERIC)` for numeric inspection, exposes cast validity and ERC flags, and
normalizes only fungible values with usable decimals. Invalid or NFT-like
values remain null rather than becoming zero.

### Label enrichment

Both enriched TVFs `LEFT JOIN` the stable label view by normalized address.
Because the accepted snapshot enforces one address per row, enrichment cannot
multiply facts. Transaction outputs use `from_*` and `to_*` label columns;
transfer outputs additionally use `token_*`. Each prefix includes primary
label, owner, category, concept class, address role, and confidence.

Aliases and provenance remain queryable through `entity_labels_v1` but are not
copied into every fact row. Flat scalar fields are preferred over nested label
structs because they simplify schema linking, result serialization and
constrained NL2SQL generation.

## Deployment workflow

The deploy command is plan-only by default. It validates the committed
dictionary and catalog, computes digest/name/counts, renders all SQL, and prints
the intended object order without creating anything. `--apply` enables remote
mutation.

Apply proceeds as follows:

1. Preflight local artifacts and DDL.
2. Create the durable dataset, read it back from the server, and verify location
   and expiration policy; request-side values are not trusted as final state.
3. Load the immutable snapshot with `WRITE_EMPTY`, or validate and reuse the
   same-digest table.
4. Run a small capped aggregate query for total rows, distinct addresses, role
   counts and digest.
5. Create/replace `entity_labels_v1` to select explicit columns from the
   accepted snapshot.
6. Create/replace the parameterless token view and core TVFs.
7. Create/replace enriched TVFs after their dependencies exist.
8. Read back metadata and dry-run representative routine calls under the 50 GiB
   cap.

Any pre-swap failure leaves consumers on their prior label version. A later
routine failure does not invalidate the stable label contract and leaves prior
routine definitions available until individually replaced. No deploy path
deletes tables. Explicit rollback names an accepted snapshot, validates it, and
repoints only the stable view.

## Validation and failure behavior

Local validation rejects malformed dictionary rows, duplicate addresses,
unknown roles, invalid provenance, digest/name mismatch, and catalog
incompatibility. DDL tests assert explicit projection, qualified identifiers,
parameter/date guards, safe casts, and left-join role fields.

Remote validation rejects a wrong dataset location, unexpected expiration,
existing incompatible snapshot schema, count/role/digest mismatch, missing
objects, unexpected routine types, or dry runs above the catalog cap. Metadata
and snapshot validation may execute; large public data queries remain dry-run
only.

## Deployment constraint discovered during live apply

Readback on 2026-08-09 showed that the project has `billingEnabled=false`.
BigQuery Sandbox therefore overrides the requested no-expiration dataset policy
with a 60-day `5,184,000,000 ms` default. The snapshot and logical views expire
on 2026-10-08. This is a platform constraint: an unbilled project cannot request
a longer lifetime.

The implementation preserves the durable contract as its default and fails
closed on any server-applied TTL. An operator must pass
`--allow-sandbox-expiration` to accept exactly the known 60-day policy. In that
mode the deployer reports the dataset default and snapshot expiry explicitly;
other TTL values remain errors. Same-digest redeployment is idempotent while the
snapshot exists. Billing must be enabled or the layer redeployed before expiry.
The deployer never claims an expiring object is durable.

The constraint and removal semantics follow the official BigQuery
[dataset creation](https://cloud.google.com/bigquery/docs/datasets) and
[expiration update](https://cloud.google.com/bigquery/docs/updating-datasets)
documentation.

After all remote validation succeeds, the T2-SQL-1 catalog changes the managed
source from a deferred table to the live `entity_labels_v1` logical view. The
existing live-schema validator then checks all six physical sources.

## Testing strategy

Tests are written first and use fake clients/jobs for all mutation workflows.
They cover deterministic transformation, explicit schema, DDL contracts,
plan-only behavior, operation order, idempotent reuse, failure before view swap,
rollback rendering, and remote summary mismatches. Live deployment follows only
after the offline suite passes. Completion requires focused tests, the full
suite, Ruff, formatting, whitespace checks, live metadata verification, and
documented dry-run bytes.
