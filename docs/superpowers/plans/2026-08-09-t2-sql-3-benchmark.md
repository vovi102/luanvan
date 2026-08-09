# T2-SQL-3 Live Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and `superpowers:test-driven-development`.

**Goal:** Gate Phase 3 on live, machine-asserted analytical correctness with
bounded scan cost and recorded BigQuery latency/job metrics.

**Architecture:** A committed six-case catalog produces one-row boolean
assertions. A side-effect-free preflight dry-runs every case and enforces
per-case/aggregate budgets. Execution rechecks each estimate, disables cache,
validates the result row and captures client/server metrics. A Click CLI exposes
dry-run-only and explicit execution modes.

**Tech stack:** Python 3.11, `google-cloud-bigquery` 3.x, GoogleSQL, pytest 8,
Click 8, Ruff, `time.perf_counter_ns`.

## Constraints

- Pinned half-open slice only: `[2026-05-31, 2026-07-01)`.
- Exactly six stable cases and one scalar `passed` row per case.
- Per-case cap 50 GiB; aggregate preflight cap 100 GiB.
- Dry-run immediately precedes every execution; query cache is disabled.
- No DDL/DML, table creation or large result materialization.
- One live repetition only; latency claims remain descriptive.

---

### Task 1: Encode benchmark cases and budgets

**Files:**
- Create `tests/unit/test_sql_benchmark.py`
- Create `src/nl2sparql/sql/benchmark.py`
- Modify `src/nl2sparql/sql/__init__.py`

- [ ] Write failing tests for exact case IDs, bounded dates, fully qualified
  managed objects, exact historical counts and token precision assertion.
- [ ] Confirm RED from absent module.
- [ ] Implement frozen case dataclass/catalog and static safety validation.
- [ ] Run focused tests GREEN and commit.

---

### Task 2: Implement dry-run and execution harness

**Files:**
- Modify `tests/unit/test_sql_benchmark.py`
- Modify `src/nl2sparql/sql/benchmark.py`

- [ ] Write fake-client tests for query configs/order, per-case overflow,
  aggregate overflow before execution, false/null/multi-row result and metric
  capture.
- [ ] Confirm RED before harness code.
- [ ] Implement preflight/result dataclasses, config builder, executor and JSON
  serialization boundary.
- [ ] Run focused tests GREEN and commit.

---

### Task 3: Add CLI and run live benchmark

**Files:**
- Create `scripts/07_benchmark_sql_layer.py`
- Modify `tests/unit/test_sql_benchmark.py`
- Create `docs/sql-benchmark.md`

- [ ] Write CLI tests proving default dry-run-only and explicit `--execute`.
- [ ] Implement deterministic JSON output and clear nonzero failures.
- [ ] Run all six live dry-runs; require per-case/aggregate budgets.
- [ ] Execute once with cache disabled; require 6/6 `passed=true`.
- [ ] Commit exact metrics and any latency-target miss without retrying it away.

---

### Task 4: Verify and close Phase 2 SQL

**Files:**
- Modify `docs/tasks/phase-2-sql/03-smoke-benchmark.md`
- Modify `docs/memory/05-DECISION_LOG.md`

- [ ] Run focused tests, full pytest, Ruff, format and `git diff --check`.
- [ ] Record commands/counts/bytes/timings and close every truthful acceptance
  item.
- [ ] Commit closure with a clean worktree.

## Completion checkpoint

After T2-SQL-3 passes, compact Phase 2 SQL as one logical checkpoint and migrate
Phase 3 task contracts from SPARQL to GoogleSQL before implementing templates.
