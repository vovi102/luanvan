# Shared execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement inline task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Triển khai exact-SQL shared campaign và isolated prediction failures với reporting không đếm lặp physical jobs.

**Architecture:** New campaign contracts/codecs bind physical queries và logical refs. New orchestration giữ double preflight/global accounting; report adapter đọc campaign trực tiếp. Legacy artifacts/mode giữ nguyên.

**Tech Stack:** Python 3.11, dataclasses, SQLGlot, existing canonical codecs/hash-chain journal, pytest/ruff; no new dependencies.

**Spec:** docs/superpowers/specs/2026-10-24-shared-execution-design.md

## Global Constraints

- Không live/inference, paid spend 0 USD; live cần quota/reservation và final approval riêng.
- Giữ exact SQL/source evidence/N=100 và EN/VI riêng; không sửa benchmark để pass.
- Test-first; fake output không thành scientific evidence. Không commit/push.

## Review Focus

- Same SQL gold+prediction: một job, gold failure phải dừng toàn cohort.
- Same SQL ordered/unordered consumers: preserve row order và duplicate semantics.
- Invalid prediction vs auth/quota/network failure: chỉ validation failure được tiếp tục.
- Immediate estimate tăng/unknown billing: không oversubmit sau halt hoặc release sai bytes.
- Forged mapping/journal/outcome/job-ID hoặc reuse ngoài campaign: reject trước reporting.

### Task 1: Contracts, codec và campaign journal

Files: contracts.py, artifacts.py, new shared_execution.py, tests/unit/test_shared_execution.py.
Interfaces: SharedExecutionEvidence physical outcomes + logical run/case refs;
serialize/load via existing canonical envelope; verify_shared_execution_journal.
- [x] RED tests: tampering/round-trip, duplicate/foreign refs, exact-SQL planning, same SQL used in multiple roles.
- [x] GREEN minimal typed contracts, codec and plan validation; preserve legacy schemas.
- [x] Verify focused artifact/contract tests.

### Task 2: Guarded shared execution

Files: shared_execution.py, executor.py, bigquery.py; tests/unit/test_shared_execution.py and test_evaluation_bigquery.py.
Interfaces: execute_shared_campaign(runs, campaign_id, source_context_sha256, policy, executor, journal).
- [x] RED tests: one physical submission across runs/roles, blocked/compile-error prediction does not poison budgets, gold failure stops, infrastructure failures stop, immediate re-preflight, unresolved/cancel handling.
- [x] GREEN minimal campaign executor with initial/immediate preflight and unique physical accounting.
- [x] Verify journal binds inputs/requests/preflights/submissions/outcomes and seal.

### Task 3: Reports, CLI và pinned offline preparation

Files: reporting.py, result_semantics.py, cli.py, shared_execution.py; focused reporting/CLI tests and docs/config.
Interfaces: build_report accepts shared artifact with real campaign hash; shared plan/execute CLI uses explicit config and offline opt-in guards.
- [x] RED tests: full N failures, gold-null report, physical latency/cost not repeated, ordered/unordered consumers, primary/replicate binding, offline help/validate and fail-closed live config.
- [x] GREEN report shared views, measurement scope, safe CLI and local campaign scope from 12 privacy-bound runs.
- [x] Focused suite, ruff and full pytest; fresh review; fix any material findings via RED→GREEN.
- [x] Update decision/backlog and save implementation evidence; keep live disabled until actual quota/final approval.

## Execution and rulings

User already authorized both behaviors; execute inline without another plan approval question.
Source context manifest must be pinned/verified for one campaign; no cross-campaign cache.
Keep legacy execute_run behavior for historical protocol; new shared mode is the authorized path.
