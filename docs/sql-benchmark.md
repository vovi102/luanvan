# T2-SQL-3 — Live GoogleSQL benchmark

Date: 2026-08-09

Project/location: `nl2sparql-thesis`, `US`

Window: `[2026-05-31, 2026-07-01)`

Execution policy: GoogleSQL, `use_query_cache=false`, dry-run immediately before
every live case, `maximum_bytes_billed=53,687,091,200`, aggregate preflight cap
`107,374,182,400` bytes.

## Oracle correction

The first execution stopped at `transaction_count`: the routine returned
65,621,456 while the initial assertion expected 4,431,329. Root-cause tracing
showed that the older count came from T2.3's KG extraction query, which retains
all dictionary-linked transactions plus a deterministic 1% background sample.
It is not the full public-table population.

An independent bounded raw-source query then established the full-window
oracles:

- transactions: 65,621,456;
- blocks: 222,310;
- token transfers: 125,320,919.

That query dry-ran at 1,529,317,480 bytes and executed at 1,529,872,384 billed
bytes. The benchmark assertions and tests were corrected before the accepted
run. Filtered KG counts remain valid only as Plan A extraction evidence.

## Accepted preflight

| Case | Estimated bytes |
|---|---:|
| `label_contract` | 600,969 |
| `transaction_count` | 524,971,648 |
| `block_count` | 1,778,480 |
| `contract_dimension_contract` | 12,996,876,032 |
| `labeled_transaction_cardinality` | 10,758,892,464 |
| `labeled_token_transfer_contract` | 41,882,654,765 |
| **Total** | **66,165,774,358** |

Every case is below 50 GiB and the full workload is below 100 GiB.

## Accepted live run

| Case | Processed bytes | Billed bytes | Server ms | Wall ms | Slot ms | Cache | Result |
|---|---:|---:|---:|---:|---:|---|---|
| `label_contract` | 600,969 | 10,485,760 | 239 | 1,727.45 | 20 | false | Pass |
| `transaction_count` | 524,971,648 | 525,336,576 | 370 | 1,577.08 | 7,011 | false | Pass |
| `block_count` | 1,778,480 | 10,485,760 | 377 | 1,810.56 | 191 | false | Pass |
| `contract_dimension_contract` | 12,996,876,032 | 12,997,099,520 | 7,590 | 9,505.68 | 1,434,537 | false | Pass |
| `labeled_transaction_cardinality` | 10,758,892,464 | 10,759,438,336 | 3,441 | 5,340.92 | 301,108 | false | Pass |
| `labeled_token_transfer_contract` | 41,882,654,765 | 41,883,271,168 | 41,155 | 45,793.73 | 2,716,932 | false | Pass, latency target miss |
| **Total** | **66,165,774,358** | **66,186,117,120** | **53,172** | **65,755.41** | **4,459,799** | — | **6/6 pass** |

## Correctness diagnostics

- `entity_labels_v1`: 5,135 rows and unique addresses; operational/token/
  treasury roles 14/5,091/30; one accepted dictionary digest.
- `transaction_facts`: 65,621,456 rows, equal to the independent raw oracle.
- `block_facts`: 222,310 rows, equal to the independent raw oracle.
- `contract_dimension`: 101,019,765 rows and unique addresses; zero deployments
  at or after the exclusive end bound.
- `labeled_transactions`: 65,621,456 rows and distinct transaction hashes, so
  label enrichment neither drops nor multiplies facts.
- `labeled_token_transfers`: 125,320,919 rows and distinct event keys; zero
  normalized-value violations.

## Latency interpretation

Five cases met the descriptive 30-second operational target. The full-month
token-transfer stress case missed it at 45.79 seconds wall time. It combines a
125.3M-row label join, exact distinct event count and precision audit, so the
result is an upper-bound validation workload rather than a typical interactive
query.

This miss does not invalidate the 6/6 correctness or byte-budget gates, but it
does constrain downstream design: generated token-transfer queries should use
the narrowest justified date window, always dry-run, and retain execution
latency/bytes in evaluation logs. T2-SQL-3 does not hide the miss through a
cache-enabled or repeated run and does not materialize a new fact snapshot from
one stress measurement.

## Commands

```bash
uv run python scripts/07_benchmark_sql_layer.py \
  --project nl2sparql-thesis

uv run python scripts/07_benchmark_sql_layer.py \
  --project nl2sparql-thesis --execute
```
