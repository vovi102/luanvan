# T2-SQL-3 Live Benchmark Design

## Context

T2-SQL-1 proved the analytical schema against source metadata and T2-SQL-2
deployed its label dimension and routines. Dry runs prove parse/type/cost
feasibility, but they do not prove live result cardinality, label-join behavior,
token precision invariants, or observed latency. Phase 3 must not generate SQL
against an interface that has only been structurally validated.

## Goals

- Execute a small representative workload with machine-checkable correctness.
- Detect fact loss or multiplication introduced by views and label joins.
- Validate contract/end-bound/token precision invariants on live rows.
- Record reproducible bytes and job timing without relying on query cache.
- Bound both each query and the full benchmark before execution begins.

## Non-goals

- Benchmark all CQ01-CQ30 or establish statistically stable latency percentiles.
- Compare model inference latency; this task measures only SQL execution.
- Materialize results or mutate routines/datasets.
- Turn missing dictionary coverage into successful semantic claims.
- Estimate dollar cost from a time-varying price; bytes are the stable metric.

## Approaches considered

### Parse-only dry runs

Lowest risk, but repeats T2-SQL-2 evidence and cannot detect row multiplication
or wrong results.

### Repeated performance benchmark

Three or more cache-disabled repetitions would support medians but multiplies
public-data scan budget without changing the Phase 3 readiness decision.

### One bounded correctness run with full job metrics — selected

Six cases cover the critical contracts once. Every case is dry-run first; the
whole workload must fit a 100 GiB estimate before any result execution. This is
enough to gate Phase 3 while treating latency as descriptive evidence.

## Workload

The label case proves exactly 5,135 unique addresses, role counts 14/5,091/30
and one accepted digest. Transaction/block cases compare routine counts with
the committed full-extraction evidence. Contract dimension proves a unique
address output and no row at/after the end bound.

The labeled transaction case requires both total rows and distinct transaction
hashes to remain 4,431,329. The labeled token-transfer case requires total and
distinct `(transaction_hash, log_index)` events to remain 4,001,230. It also
counts violations where a non-null normalized amount lacks a valid cast, ERC-20
status, non-ERC-721 status, or decimals in 0–38; violations must equal zero.

Each query returns one scalar result row containing `passed`. Additional scalar
diagnostics are serialized into the report.

## Harness

`BenchmarkCase` owns a stable ID, description, difficulty and GoogleSQL text.
`dry_run_benchmark` validates the full workload before execution and returns
estimated bytes. `execute_benchmark` refuses to start unless all estimates fit
the per-case and total caps, then dry-runs each case again immediately before
its live job.

All `QueryJobConfig` objects use GoogleSQL, disabled cache and the 50 GiB maximum
billed limit. Execution records wall-clock milliseconds plus server job
timestamps, processed/billed bytes, slot milliseconds, cache hit and diagnostic
row values. A false or null `passed` raises a benchmark error and preserves
already collected evidence in CLI output/error context.

## CLI and report

The CLI requires a project and defaults to dry-run-only. `--execute` performs
the preflight and live run, printing deterministic JSON suitable for committing
as a Markdown table. Credentials/client construction is allowed in both modes
because BigQuery dry-run is a remote read-only validation, but no result query
runs without `--execute`.

The report records environment/date/window, query IDs, assertion diagnostics,
dry-run/processed/billed bytes, wall/server latency, slot milliseconds and cache
status. Latency ≤30 seconds is an operational target; any miss is reported, not
silently retried or hidden.

## Testing and completion

Unit tests fake dry-run and result jobs to verify operation ordering, configs,
budget refusal before execution, exact one-row/boolean handling, metrics and
CLI modes. Live execution follows only after offline tests and a full dry-run
pass. Task closure requires 6/6 correctness assertions, byte budgets, committed
report, full suite, Ruff, formatting and whitespace checks.

