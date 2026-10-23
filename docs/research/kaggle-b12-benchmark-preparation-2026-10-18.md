# Private bilingual benchmark preparation — 2026-10-18

Prepared locally on `feat/b12-benchmark-preparation`, worktree
`/home/khoavd/WORKSPACE/LuanVan/.worktrees/b12-benchmark-preparation`, from fetched
`origin/main` at `ef3b66d` (PR #32). Main checkout and the old
`.worktrees/b12-bilingual-consumer` / `feat/kaggle-t4-smoke` worktree were preserved.
No subagents, push, PR or merge. No Kaggle API operation, upload/new session,
GPU/model/encoder inference, model download, training, BigQuery or genuine
benchmark evaluation occurred. Existing CLI authentication was not opened/read.

Use [notebook 16](../../notebooks/16_kaggle_b12_benchmark.ipynb), the
[operational driver](../../scripts/27_kaggle_b12_benchmark.py), the
[review config](../../configs/kaggle-b12-benchmark-campaign.json) and the
[campaign/run instructions](../planning/kaggle-b12-benchmark-campaign-2026-10-18.md).
Three opt-ins default false: preparation, environment installation and real
inference. The complete operational source is embedded and SHA-bound, so the
future private notebook needs no new dataset upload. It uses the existing private
setup dataset and read-only cache-v5 output, with mount discovery and hash gates.
Notebook 14, runner, CLI17/CLI25 and research modules remain unchanged.

The campaign has 12 full 100-case native processes: B1/B2 × EN/VI × r01–r03.
Each language retains its own N=100, outputs and retrieval cache; there is no
pooling or partial-run stitching. Select one process/session with a cumulative
attempt ledger and fresh session identity. First process is full B1 EN r01;
review runtime/artifact completeness only before the rest. No baseline SQL repair,
retry or accuracy-guided selection is implemented. Runtime errors/timeouts stop;
invalid/unsafe SQL remains in predictions.

Proposed caps: 90m native process, 20m setup/cache, 120m session. Twelve sessions
cap at 24 GPU-session-hours, plus proposed 3h contingency = 27h. With T4 ×2 the
physical provisioned budget can be 54 GPU-device-hours including reserve. Quota
charging units/current remaining balance are unresolved; historical 29.76h is
not a fresh quota reading. Smoke medians are illustrative generation scenarios,
not upper bounds or budget guarantees. Explicit approval is still needed for
actual upload/execution and the operational budget.

## Fresh offline verification

- `pytest -q tests/unit/test_kaggle_benchmark_preparation.py`: **16 passed in
  17.13s**. Executes default notebook cells with network/process/ML/file-access
  guards; real CPU subprocess timeout kills descendants and preserves log bytes;
  real process-error logs survive; owned-scratch cleanup preserves external
  symlink targets and mount files; prior IDs/session folders refuse overwrite.
  Native planning covers all twelve combinations and language-specific cache.
  Completeness fixtures reject missing/duplicate/mixed/corrupt/synthetic outputs,
  but accept 100 unsafe results without accuracy filtering. Handwritten shapes
  are TEST-ONLY; their receipts always say scientific_ready=false.
- Notebook passes nbformat validation; all three code cells compile, embedded
  source matches the reviewed script, outputs/execution counts are empty.
  Driver `--help`, Ruff lint and format checks pass.
- Exact accepted **release archive**, unchanged SHA
  `2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de`, extracted
  using both native CLI25 and the new notebook driver. Native bundle verification:
  181 payload files + manifest = 182; content SHA
  `4c10b260b7e1b119b9b6a13b43b9c00c3a4ec84402648b03eac92253840682bc`.
  Actual extracted CLI25 data preflight passes: 7,208 train, 100 EN, 100 VI,
  accepted training digest, typed VI authority and scientific_ready=false.
- Actual extracted CLI25 plans 6 EN + 6 VI; the review schedule matches all 12
  native identities with language isolation. Guarded unpack/preflight/plan report
  **zero network, credential, ML/provider-import and subprocess attempts**.
  The guard is Python instrumentation, not an OS sandbox. No cache weights were
  read/downloaded locally or model/encoder instantiated to establish these checks.
- Full repository suite: **1,590 passed, 342 warnings in 702.88s (11:42)**,
  exit 0, using `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python
  -m pytest -q`. No historical test/smoke count is presented as fresh evidence.
- Compared all 181 release payload hashes with this checkout: 180 unchanged;
  only the updated runbook differs. All research code/data/config remains exact.
  `git diff --check` passes.

[Machine evidence](../evidence/kaggle-b12-benchmark-preparation-2026-10-18.json)
and [log hash manifest](../evidence/kaggle-b12-benchmark-preparation-2026-10-18/artifacts-manifest.json).

## Preserved development checkpoints

The initial default-notebook/new-driver tests failed as intended before the new
implementation (five failures). Additional RED exposed that the completeness
check did not reject a report from another baseline (one failed, five passed);
adding baseline binding fixed it. The final 16-test regression result above is
fresh, not historical smoke/full-suite evidence.

The runbook is itself a bundle payload. Updating it changes a rebuild's archive
SHA; a current-source rebuild is **not** the accepted release archive. An early
unpack correctly rejected that rebuilt hash, and subsequent preflight failed
because extraction never happened. Logs are retained as unsuccessful checkpoints.
The transport unit fixture authenticates its own rebuilt bytes and cannot grant
release/scientific readiness. Acceptance checks above use the actual immutable
release archive from the preserved old worktree; it was only read, never changed.
A diagnostic plan-log parser also failed on interleaved stdout/stderr; final
planning uses separate streams and passes. These are not passing verification.
One full-suite development run was interrupted before completion after the
fixture assumption changed; it is preserved and not counted as a full pass.

Author self-review followed the user's prohibition on subagents. The main
operational limitations remain explicit: carry the cumulative ledger across
sessions, archive all prior outputs, pin the cache attachment version in UI,
and expect a platform hard kill to prevent cleanup/final manifests. Logs stream
while commands execute; CLI17's atomic publication can leave no predictions if
killed before completion. Do not invent or concatenate partial predictions.

## Before authorization and scientific completion

Choose campaign/session IDs and the archival/ledger owner, confirm private
notebook/input/output settings and actual cache-v5 attachment, check fresh quota,
charging units, GPU/session/disk limits, approve caps/total budget and explicitly
authorize installation/inference. Switches remain false in committed source.
No new Kaggle session or upload has occurred.

Genuine twelve-process runs and benchmark latency acceptance remain pending.
T5.4 still needs canonical adaptation, privacy/cost evidence and separately
approved BigQuery project/location/pricing/query/aggregate/USD budget and genuine
execution/comparison evidence. VI retains 100 bulk ACCEPT reviews (5/5/5/1) and
exact reused English live evidence, never implied new BigQuery execution. Existing
B0 0/100 is English only and cannot be used as a Vietnamese control. No B3,
constrained decoding, demo or Phase 6–7 implementation was added.
