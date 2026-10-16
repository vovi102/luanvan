# Kaggle B1/B2 Preparation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans, native only; no subagents.

**Goal:** Produce an offline-verifiable Kaggle runner and deterministic input bundle.
**Architecture:** An explicit manifest packages unchanged CLI17/source/accepted inputs;
new orchestration validates data and runs CLI17 in isolated processes only after
runtime preflight and explicit opt-in. Vietnamese is packaged/validated, not
silently converted to CLI17's English schema.
**Tech Stack:** Python 3.11 standard library, existing validators/CLI17, pytest.
**Spec:** `docs/superpowers/specs/2026-10-16-kaggle-b12-preparation-design.md`.

## Global Constraints

No baseline, prompt, retrieval, linker, accepted data, model identity or threshold
changes. No downloads, credentials, ML/GPU execution, network/BigQuery, upload,
merge/push/PR. Exact B2 export hash `b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
Preserve native outputs; no invented model pins/scientific readiness.

## Review Focus

- Tampered/missing/extra input or alias must fail before ML imports (Task 1).
- Missing/placeholder pins or incomplete local snapshots remain blocked (Task 2).
- Output path alias/overwrite must fail before loading models (Task 2).
- VI input must not be relabeled as English or passed to unsupported loader (Task 2).
- Failed process retains native error/status and prevents later runs (Task 2).

### Task 1 — deterministic bundle and data boundary

Files: `src/nl2sparql/kaggle/{__init__,bundle}.py`,
`configs/kaggle-b12-inputs.json`, `tests/unit/test_kaggle_b12.py`.
Interfaces: `build_bundle(root, output)`, `verify_bundle(root)`, `preflight_data(root)`.
- [x] RED: CLI entry/bundle construction absent; assert archive reproducibility,
  explicit manifest inputs and exclusions, safe extraction and tamper rejection.
- [x] GREEN: implement allowlisted archive/manifest and existing-validator preflight.
- [x] Verify actual extracted corpus + English/VI lineage under offline guards.

### Task 2 — fail-closed runner and notebook

Files: `src/nl2sparql/kaggle/{runner,workflow}.py`, `scripts/25_kaggle_b12.py`,
`configs/kaggle-b12-run.template.json`, `notebooks/14_kaggle_b12.ipynb`.
Interfaces: `plan_runs(root, config, output)`, `preflight_runtime(root, config, output)`,
`run_campaign(root, config, output, real_inference, baseline, replicate)`.
- [x] RED: tests missing opt-in/pins, exact commands, VI refusal, no input writes,
  bad paths, incomplete cache and subprocess failure retention before implementation.
- [x] GREEN: orchestration delegates to unchanged CLI17; hardware probing is lazy,
  offline environment is explicit and each process/run has its own preserved output.
- [x] Validate notebook structure and compile code cells; execute its data-only path.

### Task 3 — verification, evidence and handoff

- [x] Run focused/new tests and unchanged B1/B2 tests; lint and full suite once stable.
- [x] Build twice, compare archive bytes, extract and run guarded data preflight;
  preserve blocked runtime result from unresolved external pins as blocked, not pass.
- [x] Update active task/backlog and stale Kaggle Stage D references, document VI
  execution gap, external steps and actual checks; commit locally.

## Native ledger

- Base worktree clean at `ededf48`. Existing worktrees kept.
- Ruling: use CLI17 English path unchanged; VI execution is unsupported until a
  dedicated typed consumer exists. Cost: no bilingual inference-ready claim here.
- Ruling: null external pins are honest preparation inputs, not fabricated revisions.

- Native self-review added tests before fixes for directory/cache aliases,
  malformed archives, timeout and interrupt evidence; all passing in focused suite.
- Final focused suite: 68 passed in 25.50s; fresh full suite 1,534 passed / 342 warnings in 619.26s, exit 0.
- Ruling: output wall-time cap is an explicit operational field (null until supplied),
  not a changed generation/accuracy threshold. Interrupted attempts remain interrupted.
- Actual guarded extracted-bundle preflight: data_ready, 7208 train / 100 EN / 100 VI,
  zero observed network/credential/model-provider/subprocess attempts.
- Runtime template preflight: blocked, as expected; no genuine pins/cache fabricated.

- Final native whole-branch self-review: source/data boundaries, fixed research
  config, aliases, offline child environment, native output/status preservation,
  VI refusal and external readiness limits checked. No independent reviewer was
  dispatched because the user requires native execution without subagents.
- Byte-identical final archive SHA-256:
  `4a49b57835e031986e3abcd274955df504ccf3b1811640fa8ef72ca854c70e4f`.
