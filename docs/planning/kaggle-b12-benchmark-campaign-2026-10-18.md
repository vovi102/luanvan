# B1/B2 EN/VI benchmark campaign — offline preparation, 2026-10-18

Preparation is authorized and local only. Execution is **not authorized by this
handoff**. No notebook/dataset upload, Kaggle session, model download/load,
GPU inference, training or BigQuery job is part of this change. Main base:
`ef3b66d` (PR #32). The old smoke worktree remains untouched.

## Deliverables and design

Use `notebooks/16_kaggle_b12_benchmark.ipynb`, with the operational source embedded
verbatim from `scripts/27_kaggle_b12_benchmark.py`. Notebook 14 remains unchanged:
it is one of the payload files in the accepted immutable bundle. Rebuilding that
bundle with a changed notebook would invalidate its accepted SHA. The runbook is also a bundled file; updating current documentation means a new
build from this checkout has a different SHA. Consume the existing accepted
private release archive, never substitute a new rebuild. No new runtime
module is injected into that archive. The separate driver imports its real CLI25
runner, which launches unchanged CLI17 `evaluate` in native processes. The review
configuration is `configs/kaggle-b12-benchmark-campaign.json`; it documents the
schedule/caps, does not execute anything and leaves campaign/quota unresolved.
The notebook's explicit settings are the execution controls.

Keep the eventual notebook **private**, as well as its saved outputs. Attach:

- Private dataset `aohkvd/nl2sql-setup-inputs`, archive `input-bundle.bundle`, SHA-256
  `2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de`.
- Private notebook output `aohkvd/nl2sql-environment-cache`, specifically **v5**.
  Confirm the version in the saved attachment UI; a slug alone is not a version pin.
  The driver discovers the actual mount using the single cache inventory and
  checks its accepted SHA `ae3b7dc2361f151bcc59d68f4b2ddcdef74b99a5fe8374b041190bded84d84f1`.

The driver authenticates four setup files using the exact smoke-v2 hashes before
running any setup script. It authenticates the archive before extracting 181
payload files plus `kaggle-bundle.json` (182 regular tar members), rejects unsafe
paths/duplicates/oversize members, and uses a fresh extraction. Actual bundle
verification and native data preflight follow in the pinned runtime. Inputs
are never modified. The cache stays under its actual `/kaggle/input` mount;
16.16 GB of weights are **not copied** into working storage.

Installation reuses smoke v2: isolated hashed bootstrap, managed Python 3.11.15,
`uv pip sync --require-hashes` with the complete existing 218-package lock. It
requires installation network access, but never downloads model/encoder payloads.
The runtime is installed separately from cache. Before inference, the setup
script streams verification of all pinned cache bytes, then real native data and
runtime checks run. Software/structural preflight is not scientific acceptance;
real CLI25 probes approved T4 hardware only after explicit inference opt-in.
No HF_TOKEN, secret access, credential discovery or login is needed.

## Fixed research and input contract

Model `meta-llama/Meta-Llama-3-8B-Instruct` revision
`8afb486c1db24fe5011ec46dfbe5b5dccdb575c2`; encoder
`sentence-transformers/all-MiniLM-L6-v2` revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Seed 42, greedy, batch 1,
max_new_tokens 512, original 4-bit/BF16 backend. Prompts, retrieval, normalization
and acceptance thresholds remain unchanged. In particular B1 P95 <5s and B2 P95
<8s remain acceptance gates; caps below do not replace those thresholds.

B2 consumes only `data/dataset/processed/b2-training.jsonl`, 7,208 train rows,
SHA-256 `b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
The packaged 8,000-row canonical corpus serves provenance verification only;
792 development rows, finalized benchmark/gold and review data never enter
retrieval/embedding matrices. Only the target question enters query embedding.
Stage A, canonical corpus, catalogue, finalized EN/VI, reviews and authority hashes
stay unchanged. VI retains 100 user bulk ACCEPT events, scores 5/5/5/1, and exact
reused English live evidence. This does not imply new Vietnamese BigQuery execution.

## Twelve full processes and session schedule

`C` below is one campaign identity chosen before execution. Run IDs follow the
existing runner contract. Each process consumes the complete finalized snapshot,
100 questions, with no limit/filter/retry. Metrics use N=100 for each language;
never pool EN/VI into N=200 or combine partial attempts.

| Session | Native run ID | Snapshot | Cases |
|---|---|---|---:|
| s01 | C-b1-en-r01 | finalized EN | 100 |
| s02 | C-b1-vi-r01 | finalized VI | 100 |
| s03 | C-b2-en-r01 | finalized EN | 100 |
| s04 | C-b2-vi-r01 | finalized VI | 100 |
| s05 | C-b1-en-r02 | finalized EN | 100 |
| s06 | C-b1-vi-r02 | finalized VI | 100 |
| s07 | C-b2-en-r02 | finalized EN | 100 |
| s08 | C-b2-vi-r02 | finalized VI | 100 |
| s09 | C-b1-en-r03 | finalized EN | 100 |
| s10 | C-b1-vi-r03 | finalized VI | 100 |
| s11 | C-b2-en-r03 | finalized EN | 100 |
| s12 | C-b2-vi-r03 | finalized VI | 100 |

There are six processes per language and three per (baseline, language), 1,200
predictions overall. Every process gets a fresh CLI17 interpreter/model lifetime.
Outputs: `/kaggle/working/b12-benchmark-C/runs/<run-id>/`; B2 cache:
`runs/<language>/cache/b2-few-shot.npz`, isolated by language and campaign. A fresh
Kaggle session can rebuild its cache deterministically from the same training
snapshot; restoring cache is not needed. Native output directories are never
reused, including failed/partial ones. Per-session driver evidence is under
`session-<SESSION_ID>/` and must also be fresh.

The first benchmark process is **full B1 EN r01**, not a smaller calibration set.
Before other sessions, review only runtime success and artifact completeness:
matching ordered 100 case IDs in predictions/log, language/run identity, baseline,
native runtime provenance, count and output hashes. Do not inspect accuracy for
configuration selection. Invalid/unsafe/empty/prose SQL stays in baseline outputs;
it does not trigger retry, repair, exclusion or early stopping. Runtime failures,
OOM, missing/corrupt artifacts and timeout stop the session; no later process is
started automatically. Complete artifacts may still fail latency/scientific gates.

## Caps, budget and uncertainty

Proposed one process per session, serial sessions on the same T4 ×2 hardware
class as smoke. Process cap: **5,400s (90m)** including native model/encoder setup
and all 100 generations. Setup plus cache verification: **1,620s (27m)** from
start of driver. Driver session cap: **7,200s (120m)**, including 120s reserved
for cleanup/evidence; worker watchdog is min(5,460s, remaining session budget).
Preflight inside the worker uses some watchdog time. This is an operational
wall-time policy, not an accuracy/latency threshold or guaranteed completion time.

Operational revision approved on 2026-10-22 after the B2 EN r03 setup timeout:
setup was originally 1,200s (20m), as retained in all earlier session sources.
The new allowance uses existing session headroom: 1,620s setup + 5,460s maximum
worker + 120s cleanup = 7,200s. It does not raise the native/session caps or
relax any hash/research gate. Per-stage start/finish/elapsed/remaining-budget
and completion/error/timeout outcomes are retained in `stage-timings.jsonl`,
including failed stages, without command or environment dumps. Keep old/new
driver hashes with their sessions; this revision has only been tested offline.
It does not authorize any new GPU session, retry/replacement or failed-process
continuation exception. Real mounted-cache completion remains unverified.

At the revised caps: 12 × 1.5h native = 18h; up to 5.4h setup, with 0.6h left
inside **24 GPU-session-hours** for worker overhead/cleanup. Propose **3h additional contingency**,
for **27 GPU-session-hours total**, requiring explicit approval. With two
provisioned T4s, the corresponding physical allocation could be as high as 54
GPU-device-hours including reserve. Verify Kaggle's actual quota charging unit
and hardware availability before authorization. If quota is charged per device,
27 session-hours would require 54 quota-hours and cannot be assumed to fit.

Historical quota after smoke was 29.76h remaining; it is not a current check or
budget approval. No quota was consumed or queried in this preparation turn.
Check remaining quota, refresh time, platform session limits, working disk and
billing multiplier before each future session. Do not start unless its full cap
fits within the approved remaining budget. Stop at the overall approved budget;
contingency is not permission for automatic reruns. Setup time consumes GPU quota
when the session already has a GPU attached. No parallel sessions are proposed.

Smoke v2 used five train questions, ten separate `predict` processes: B1 median
20.95s/max 28.47s, B2 median 20.01s/max 20.49s generation time. Multiplying those
medians by 100 gives an **illustrative scenario only** of 34.9m/33.3m generation
per process (~6.8h across 12). It excludes encoder construction, retrieval,
model startup, preflight and installation; it is neither forecast nor upper
bound. Benchmark prompts/output lengths and T4 contention can differ. Even
smoke maxima are not benchmark upper bounds. The 90m cap can fail; preserve that
negative runtime evidence and request a new operational decision without tuning
research settings from benchmark/gold results.

## Notebook use after a separate execution authorization

1. Review/upload only the private notebook 16 when authorized; attach the two
   existing private inputs and confirm cache v5. No dataset upload is necessary.
2. Choose one `CAMPAIGN_ID`, a fresh `SESSION_ID`, `BASELINE`, `LANGUAGE` and
   `REPLICATE`. s01 must be B1/en/1 with `PRIOR_ATTEMPTS=[]`.
3. To inspect inputs only, enable `ALLOW_PREPARATION`; leave installation and
   inference false. To perform full installed-runtime preflight/planning, also
   enable `ALLOW_ENV_INSTALL`, leaving `ALLOW_REAL_INFERENCE=False`.
4. Only with genuine execution authorization and fresh budget check, enable all
   three controls. Inference subprocesses use an allowlisted environment forced
   offline; inherited tokens are not forwarded. There is no HF/BigQuery login.
5. Save the entire campaign folder and Kaggle notebook URL, saved version,
   actual attachment versions, privacy settings and session quota deltas. Copy
   the full `attempted_run_ids` list from `campaign-ledger.json` into
   `PRIOR_ATTEMPTS` for the next session and set
   `PRIOR_COMPLETENESS_REVIEWED=True` only after a successful
   `complete_100_native_cases` receipt and runtime/artifact review. A failed or
   incomplete first process blocks continuation pending a new operational decision. Preserve
   source/settings hashes so twelve sessions can be audited as one protocol.

The ledger reserves each ID before attempting inference. Existing folders and
attempted IDs are refused. A fresh Kaggle session cannot inspect another
session's abandoned outputs: carrying the cumulative ledger and independently
archiving outputs are mandatory human campaign controls. A failed run is not
resumable; any replacement must be a new, separately approved full-process
identity and remain distinguishable from the original. Never concatenate partial
predictions or hide failed attempts to obtain three compatible replicates.

## Retention, failure and cleanup

Always retain native predictions, native-log, native-report, `run.json`, native
stdout/stderr, per-language caches and metadata; driver source/settings,
input provenance, cache verification log, data/runtime preflight, full 12-run
plan, ledger, worker.log, completeness receipt, summary and artifact hash manifest.
The summary always says scientific_ready=false. The CLI17 report's original
blockers/readiness are retained without rewriting them.

Commands stream to exclusive log files. Timeout/interrupt kills the entire
process group, including native grandchildren, before deleting installed runtime.
Runner errors retain its run.json/stdout/stderr and stop. Early driver errors
retain summary/logs and input provenance where available. `finally` cleanup only
removes the fresh `b12-scratch-*` child created by this driver; it never deletes
mounted inputs or campaign outputs. Removing a scratch symlink cannot delete its
target. Kaggle hard termination/disk failure can prevent final summaries/manifests;
this is why logs stream and each process has its own session. Native CLI17
publishes predictions atomically at process completion: a killed process may
retain logs but no per-case prediction file. Do not fabricate partial artifacts.
The revised driver also records the setup/worker/cleanup caps explicitly in
its summary and includes `stage-timings.jsonl` in the output manifest. An empty
timing file can indicate failure before the first subprocess (such as input
discovery); terminal summaries still carry the failing stage.

## Remaining scientific gates

This preparation and synthetic regression fixtures create no scientific readiness.
Genuine benchmark completion needs 12 compatible full native processes and all
real runtime/provenance/latency evidence. T5.4 still needs canonical adaptation,
privacy review, cost evidence, separately authorized/budgeted BigQuery predicted
and gold execution, reports and comparisons. Native extraction ok is not SQL
correctness. Existing B0 genuine 0/100 is **English only**, not a Vietnamese
control. Vietnamese B0 requires its own compatible genuine evidence if compared.
B3, constrained decoding, demo and Phase 6–7 tickets are outside this change.

Before real execution finalize: campaign/session IDs and output archival/ledger
owner; notebook privacy and immutable attachment versions; fresh quota/charging
units/platform limits/storage; approval of process/session caps and total GPU
budget; explicit installation/inference authorization. BigQuery project/location,
privacy/cost evidence, query/aggregate byte/USD caps and pricing policy belong to
a later independent T5.4 authorization, not this notebook.
