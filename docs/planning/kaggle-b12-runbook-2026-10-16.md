# Kaggle B1/B2 runner and bundle

Current benchmark preparation (2026-10-18): use **notebook 16**,
`notebooks/16_kaggle_b12_benchmark.ipynb`, and the
[campaign plan](kaggle-b12-benchmark-campaign-2026-10-18.md). It reuses the accepted
bundle and the exact successful smoke-v2 runtime procedure. Notebook 14 below is
the legacy preparation template and remains immutable inside that bundle.
Preparation is complete only after its offline checks; upload/execution still
requires separate authorization, fresh quota and approved caps. No scientific
completion is implied.

The runner supports the unchanged B1/B2 research definitions for **one explicit
language per config**, `en` or `vi`. English retains its finalized `nl` trusted
loader. Vietnamese goes through a typed paired-snapshot authority that checks
accepted source hashes, reconstructs all human acceptance events, validates the
complete final manifest and exact reused English live evidence, and retains the
original `PairedFinalCase` and source digests in native artifacts. No new BigQuery
execution is implied. The user bulk ACCEPT provenance (5/5/5/1) is preserved.

This bilingual bundle supersedes the English-only preparation bundle operationally;
its archive hash is recorded in
[the bilingual handoff](../research/b12-bilingual-consumer-2026-10-16.md).
The accepted release archive remains immutable. This runbook is itself bundled;
rebuilding after documentation changes yields a different archive SHA. For this
campaign consume the existing private archive with accepted SHA, not a fresh
build from current docs. Old archive/evidence and unsuccessful audits remain
historical records.

## Build and validate locally without models (development only)

From the repository worktree, use Python 3.11 with the project's dependencies:

```bash
PYTHONPATH=src python scripts/25_kaggle_b12.py bundle \
  --output .local/kaggle-b12-bilingual/release/input-bundle.tar.gz
PYTHONPATH=src python scripts/25_kaggle_b12.py unpack \
  --archive .local/kaggle-b12-bilingual/release/input-bundle.tar.gz \
  --sha256 <exact-archive-sha256-from-build> \
  --output /tmp/b12-input
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py preflight \
  --root /tmp/b12-input --level data
```

The archive SHA-256 is printed by `bundle`; record it independently and copy it
into the notebook. Archive timestamps, ownership and gzip header are fixed.
`configs/kaggle-b12-inputs.json` explicitly lists accepted data hashes and source
paths. Every packaged file has a size/digest/role in `kaggle-bundle.json`.
No model files, credentials, .git, caches, tests/fixtures or arbitrary repository
files are included. Build/extract refuse aliases, traversal and overwrites.
Do not put new files or configs inside the immutable extracted input tree.

B2 consumes only `data/dataset/processed/b2-training.jsonl`, 7,208 train records,
exact accepted SHA-256
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
The full 8,000-row canonical source and its companions are packaged solely for
existing adapter provenance verification. Its 792 development records never
enter retrieval or embeddings. English/VI gold files remain outside retrieval.

## External setup you perform

The numbered steps below describe the generic notebook-14 template. Current
campaign preparation uses notebook 16 with the existing dataset/cache; follow
its campaign plan rather than acquiring weights or uploading another bundle.

1. Prepare a **private** Kaggle dataset containing the archive and a private
   notebook based on `notebooks/14_kaggle_b12.ipynb`. This task does not upload.
2. Check your actual GPU quota/session limits and obtain the approved T4 hardware.
   No historical account quota/session/storage number is a current guarantee.
3. Provision Python 3.11 and the exact core dependency versions in `uv.lock`.
   Runtime preflight lists expected/installed versions without importing ML.
   The bundle includes the project lock, not wheels or an installed environment;
   the full hashed environment was genuinely installed with Python 3.11.15 in
   the cache/smoke sessions. Notebook 16 reuses those exact setup hashes.
4. Obtain genuine local Hugging Face snapshots for the fixed model
   `meta-llama/Meta-Llama-3-8B-Instruct` and encoder
   `sentence-transformers/all-MiniLM-L6-v2`, with their actual lowercase 40-hex
   revisions. Do this separately under the applicable model license/access.
   Do not send tokens to chat or write them in notebook cells/outputs. Inference
   needs the local cache only; it does not log in or download anything.
5. In the notebook, set the archive path/SHA, campaign ID, revisions, HF cache
   root and explicit per-native-process `RUN_TIMEOUT_SECONDS`. Leave
   `ALLOW_REAL_INFERENCE=False` until a separately authorized genuine run.

Model and tokenizer use the same revision in the existing backend. No fake
revision is provided. The template keeps unknown values `null` and remains
blocked. HF layout must be `HF_HOME/hub/models--<owner>--<name>/snapshots/<revision>`;
local symlinks may only resolve within that HF cache. Preflight checks required
config/tokenizer/weight files and referenced weight shards, not model loading
or weight authenticity. Genuine load/hardware/OOM/latency evidence is external.
The unchanged backend's original 4-bit/BF16 behavior passed genuine T4 smoke
v2. Benchmark latency and complete 100-case processes remain unverified.

## Preflight, plan and authorized execution

Copy `configs/kaggle-b12-run.template.json` **outside** the input tree and fill
its unresolved operational fields and explicitly select `language=en` or
`language=vi`. Other research fields are fixed: three runs per baseline per language, seed 42, greedy, batch one, max_new_tokens 512, 4-bit.

```bash
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py preflight \
  --root /tmp/b12-input --level runtime \
  --config /path/to/run-config.json --output /path/to/b12-runs
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py plan \
  --root /tmp/b12-input --config /path/to/run-config.json --output /path/to/b12-runs
```

Data/runtime preflight and planning do not load an encoder/model, probe CUDA,
read credentials, call BigQuery or execute inference. `data_ready` only covers
inputs. Runtime `ready` covers structural prerequisites; it is not hardware,
model compatibility or scientific acceptance.

The historical prerequisite smoke used existing CLI17 `predict` on five
non-test training questions for B1/B2, with the same pinned configuration and
explicit real opt-in. For B2 pass the training record as target ID so its family
is excluded. Keep smoke outputs separate; do not change prompts/configuration
in response to held-out benchmark outcomes. Smoke v2 now satisfies compatibility
only; see the
[retained result](../research/kaggle-t4-smoke-2026-10-17.md). Do not repeat it
automatically or use it as benchmark acceptance.

Only in the separately authorized Kaggle execution, after successful smoke:

```bash
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py run \
  --root /tmp/b12-input --config /path/to/run-config.json --output /path/to/b12-runs \
  --real-inference
```

On Kaggle use the notebook's `/kaggle/working` paths rather than the local examples
above. The runner checks data, software/cache prerequisites and T4 before invoking
CLI17 with explicit `--language` and `--benchmark-root` in a separate process for each run. All HF loaders are forced
offline; no BigQuery execution is part of this runner. It plans
`<campaign>-b1-<language>-r01..03` and `<campaign>-b2-<language>-r01..03`.
Each config schedules six processes. A complete EN+VI protocol has twelve
processes: three compatible runs for each (baseline, language), never three total
shared across languages. Metrics keep N=100 separately for each snapshot; do not
pool the two snapshots into a 200-case result. B2 uses the same approved bilingual
train export in both languages; no language filtering or retrieval-policy change.
Caches are isolated at `<output>/<language>/cache/b2-few-shot.npz`; run folders
also include language. Native predictions/logs carry full paired source lineage
and per-case prompt hashes; reports bind the ordered prompt hash list. Choose
separate language configs (notebook `LANGUAGE`) and preserve each config. Use
`--baseline b1|b2 --replicate 1|2|3` to run an unstarted selection. Campaign outputs
are not overwritten: retain failed attempts, choose a new campaign for a genuine
retry and record its relationship to the old attempt in experiment notes.
Never combine partial attempts into one scientific run.

Each run retains `run.json` (exact config, bundle hash, argv, hardware, Python,
core package checks, full installed inventory, start/finish and status), native
predictions/log/report and native stdout/stderr. A timeout/nonzero exit preserves
evidence and stops subsequent runs. Existing CLI17 publication/provenance and
scientific blockers remain authoritative; the wrapper does not upgrade readiness
or fabricate SQL execution accuracy, privacy/cost evidence or B3 decisions.

Keep the Kaggle notebook URL/version and full output directories for handoff.
Next evidence work is genuine B1/B2, then T5.4 comparison and T5.5 B3 decision;
typed VI execution plumbing is implemented; genuine bilingual scientific evidence remains pending.

## Native and T5.4 handoff

CLI17 defaults to English for compatibility; Vietnamese requires `--language vi`
and an explicit finalized VI `--test-set`. It retains the original IDs/question,
language/pair/English identity, gold SQL, review/candidate digests and source
fingerprints. The typed adapter rejects altered or missing source files, mismatched
language/snapshot/manifest/lineage/evidence. Outputs cannot alias any protected
benchmark source. VI default native outputs live under `data/eval/b12/vi/<baseline>/<run-id>/`;
explicit runner outputs remain per process as above. Existing outputs from another
run or language fail before model loading. Real inference still requires opt-in.

After genuine inference, CLI19 `adapt b12 --language vi --benchmark-root <input-root>`
consumes each native predictions/log/report triple with the matching VI test set.
It revalidates paired authority and exact per-case source lineage across files.
Canonical source references/fingerprints bind language and paired sources; exact
snapshot identity keeps EN/VI denominators and reproducibility separate. For EN,
use `--language en` (default). Prompt fingerprints hash complete messages including
each question: T5.4 binds their ordered list rather than requiring equal hashes
across different questions. No prompt text or research policy changed.

Inference alone does not measure predicted SQL execution accuracy. T5.4 genuine
execution, cost/privacy evidence, three compatible replicates per language, and
comparison remain external stages. Never infer new BigQuery results from VI's
reused historical gold evidence.

## Current benchmark controls — 2026-10-18

Notebook 16 defaults preparation, installation and inference to false. It discovers
actual mounts, authenticates setup/archive/cache inventory, retains mounted weights
in place, installs exact Python 3.11.15/full hashed lock only with opt-in, and runs
real bundle/data/cache/runtime gates. It selects one complete native process per
session through CLI25, preserving CLI17 and existing trust gates. The full plan
contains 12 processes: three for each B1/B2 × EN/VI, N=100 separately per language.

Proposed caps: 5,400s/process, 1,200s setup/cache, 7,200s/session. Twelve separate
sessions cap at 24 GPU-session-hours; propose 3h contingency (27h total). Charging
units for T4 ×2 and fresh quota must be checked before approval. Historical 29.76h
is not a current guarantee. See the campaign for the exact matrix, ledger/archival
requirements, first-full-process completeness review and timeout/cleanup behavior.
Failed attempts/unsafe SQL are retained; no accuracy tuning or partial-run merging.

T5.4 requires separate canonical adaptation, privacy/cost evidence and BigQuery
budget/authorization. B0's existing 0/100 is English evidence only. No B3,
constrained decoding or Phase 6–7 implementation is included.

## First authorized genuine process — 2026-10-18

B1 EN r01 v1 COMPLETE, N=100; native/runtime/artifact completeness independently
verified. See [result/audit](../research/kaggle-b12-benchmark-first-run-2026-10-18.md).
At that first EN checkpoint, exactly one process was authorized/executed; see
the subsequent VI result below for current campaign progress.
Carry the retained cumulative campaign ledger into any separately authorized
next session. Keep source defaults disabled. All 100 extraction failures and
original native scientific blockers are retained; no prompt/model/flag/threshold
change or automatic retry was made. T5.4 adaptation/privacy/cost and separately
budgeted BigQuery work remain pending.

## Second genuine process verified — 2026-10-19

B1 VI r01 private v1 COMPLETE, N=100. All genuine completion markers,
source-bound Vietnamese questions/paired lineage, saved manifest/report hashes,
cache/data/runtime gates, T4 ×2 hardware and cumulative EN/VI ledger pass.
See [verified VI result](../research/kaggle-b12-benchmark-b1-vi-r01-2026-10-18.md).
VI: 100 unsafe_sql, 0 extraction ok, P95 30.376s; scientific gates remain
blocked. Native wall 37.17m, driver 46.11m. Outputs and negative observations
retained without repair/retry. Account quota remaining on return 28.046782h.
Campaign 2/12 native processes complete, N=100 separately per language.
Remaining ten unstarted; next planned B2 EN r01. Resuming monitoring launched
no new session and does not imply approval of the whole campaign budget.

## Third process submitted — 2026-10-19

After explicit continuation, next single B2 EN r01 private v1 submitted at
19:08:56 Asia/Saigon; platform RUNNING at 19:09:28. Same 90m/120m caps,
unchanged training-only retrieval/research settings, two prior IDs carried.
Fresh quota 28.046782h, no reserved quota, pay-to-scale disabled. Both prior
sessions and cache v5 COMPLETE. Remote source/private GPU metadata verified;
native inference and actual runtime/hardware remain unverified. Two processes
complete, this third pending, nine unstarted. See
[B2 EN checkpoint](../research/kaggle-b12-benchmark-b2-en-r01-2026-10-19.md).

## Third process verified — 2026-10-19

B2 EN r01 private v1 COMPLETE, N=100; all 25 saved artifacts retained, 24 native
manifest entries/report self-digest verified. All genuine completions and
7,208-row train-only retrieval matrix / 500 selected examples verified.
31 extraction ok, 60 prose, 8 unsafe_sql, 1 invalid_sql; P95 52.987s,
native wall 61.70m, driver 68.31m. Scientific gates remain blocked; no SQL
execution accuracy, BigQuery, repair/retry or research change claimed.
Quota remaining 26.902697h. Campaign 3/12 native processes complete, nine
unstarted; next B2 VI r01 not launched during this result check.
[Verified B2 EN result](../research/kaggle-b12-benchmark-b2-en-r01-2026-10-19.md).

## Fourth process submitted — 2026-10-19

Explicitly authorized B2 VI r01 private v1, N=100, submitted at 22:13:49
Asia/Saigon; QUEUED at 22:14:06. Same 90m/120m caps, unchanged research settings,
three prior IDs carried. Fresh quota 26.902697h, 0 reserved, pay-to-scale off;
private cache v5 and prior notebooks COMPLETE. Remote source/private GPU metadata
verified, actual hardware/inference still unverified. Three processes complete,
fourth submitted, eight unstarted. Queue time is not measured native wall time.
[B2 VI checkpoint](../research/kaggle-b12-benchmark-b2-vi-r01-2026-10-19.md).

## Fourth process verified — 2026-10-20

B2 VI r01 private v1 COMPLETE, full N=100. All 25 saved files retained, 24
native manifest hashes/report self-digest pass. Verified original VI questions,
paired lineage/reused English evidence, all genuine completions, 7,208-row
train-only cache and 500 selections, actual T4 ×2 runtime and four-attempt
ledger. 12 extraction ok, 88 prose; P95 73.590s. Native 62.47m, driver 66.49m.
Scientific blockers unchanged; no SQL execution accuracy, new BigQuery, retry
or research change claimed. Quota remaining 25.789862h. Campaign 4/12 complete,
all r01 combinations, eight unstarted; next B1 EN r02 not launched by this check.
[Verified B2 VI result](../research/kaggle-b12-benchmark-b2-vi-r01-2026-10-19.md).

## Fifth process submitted — 2026-10-20

Explicitly authorized B1 EN r02 private v1, full N=100, submitted at 19:58:01
Asia/Saigon; RUNNING at 19:58:17. Scheduled replicate with unchanged research
settings, 90m native / 120m session caps and all four prior IDs carried.
Fresh quota 25.789862h, 0 reserved, pay-to-scale off; private cache v5 and all
prior notebooks COMPLETE. Remote source/private GPU metadata verified; actual
native hardware/runtime/completeness remain unverified. Four complete, fifth
running, seven unstarted. No replacement run or benchmark-directed tuning.
[B1 EN r02 checkpoint](../research/kaggle-b12-benchmark-b1-en-r02-2026-10-20.md).

## Fifth process verified — 2026-10-20

B1 EN r02 private v1 COMPLETE, full N=100; 22 saved files retained, 21 native
manifest hashes/report self-digest pass. All genuine completions, original
English source authority, zero-shot settings, actual T4 ×2 runtime and exact
five-attempt ledger verified. 99 unsafe_sql, 1 invalid_sql, 0 extraction ok;
P95 48.809s. Native 47.95m, driver 52.62m. Scientific blockers retained;
no SQL execution accuracy, repair/retry, adaptation, BigQuery or new session.
Quota remaining 24.906806h. Campaign 5/12 complete, seven unstarted; next B1 VI
r02 not launched by this check. r01/r02 remain separate immutable evidence.
[Verified B1 EN r02](../research/kaggle-b12-benchmark-b1-en-r02-2026-10-20.md).

## Sixth process submitted — 2026-10-20

Authorized B1 VI r02 private v1, full N=100, submitted at 21:03:51 Asia/Saigon;
QUEUED at 21:04:08. Scheduled replicate, unchanged settings/90m native/120m
session caps, five prior IDs carried. Fresh quota 24.906806h, 0 reserved,
pay-to-scale off; private cache v5 and all prior sessions COMPLETE. Remote
source/private GPU metadata match; actual native runtime/hardware unverified.
Five complete, sixth submitted, six unstarted. Keep r01/r02 separate with
original blockers and no automatic retry, SQL repair or BigQuery.
[B1 VI r02 checkpoint](../research/kaggle-b12-benchmark-b1-vi-r02-2026-10-20.md).

## Sixth process verified — 2026-10-20

B1 VI r02 private v1 COMPLETE, N=100. All 22 saved files/21 native manifest
hashes/report digest and 100 genuine completions/paired lineage pass. Zero-shot
settings, T4 ×2 runtime, cleanup and exact six-attempt ledger verified.
100 unsafe_sql, 0 extraction ok; P95 29.532s; native 35.86m, driver 44.37m.
Quota remaining 24.161284h. Native scientific blockers retained; no new BigQuery,
adaptation or repair. User explicitly authorized next B2 EN r02 after review;
fresh launch preflight remains required. Campaign 6/12 complete at this point.
[Verified B1 VI r02](../research/kaggle-b12-benchmark-b1-vi-r02-2026-10-20.md).

## Seventh process submitted — 2026-10-20

Authorized next B2 EN r02 private v1, N=100, submitted at 23:08:04 Asia/Saigon;
RUNNING at 23:08:19 after B1 VI r02 review passed. Same 90m/120m caps,
unchanged research settings, six prior attempted IDs carried. Fresh quota
24.161284h, 0 reserved, pay-to-scale off; prior sessions and cache v5 COMPLETE.
Remote source/private GPU metadata match; actual native runtime unverified.
Six complete, seventh running, five unstarted. No r01 replacement, new BigQuery
or adaptation/tuning.
[B2 EN r02 checkpoint](../research/kaggle-b12-benchmark-b2-en-r02-2026-10-20.md).
