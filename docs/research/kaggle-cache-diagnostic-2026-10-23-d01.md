# One-off CPU mounted-cache diagnostic d01 — 2026-10-23

The user requested continuation after the replacement setup failure review.
Next work is diagnosis of mounted-cache verification slowness before any new
benchmark. This one-off diagnostic is outside product source, accepted bundle,
setup kit and campaign driver. It is not a verifier repair or benchmark attempt.
No native failed ID is reused and no replacement02 is prepared or authorized.

Two setup attempts have exhausted their setup budget in the unchanged accepted
verify_cache function, with no per-file output: original failed EN r03 and its
separately approved replacement01. Validation and finalVI completed the same
cache stage in702.389s and1,013.519s; replacement01 timed out after1,535.387s,
though runtime installation took only77.036s. No file/digest/I/O root cause is
yet established. Another headroom increase would not supply the missing evidence.

This measurement uses one private CPU notebook, internet/GPU/TPU disabled,
accepted setup dataset and cache-v5 output. Driver watchdog1,620s (27m), platform
cap1,800s (30m) to retain final logs/manifests. No exact pinned runtime install,
model/encoder loading, training, BigQuery, SQL repair, source adaptation,
weights copy/download or benchmark identity reservation. Input/archive/inventory/
pins/verifier fingerprints are checked before verification. No research settings,
accepted bytes, checks or benchmark caps change.

The observer calls the fingerprint-checked native verify_cache function with
'all'; it does not reimplement hashing or replace its result. It records native
per-file admission before path/size checks via a filtered trace callback and
wraps only Path.open calls made directly by that function. The reader returns
the same bytes from the same native2MiB requests. Native size/path/SHA256/
git-blob-SHA1 checks stay intact. Both the tracer and Path.open are restored
in finally; the observation lives in its own fresh worker process.

Journal events include file start/open/read-complete, cumulative byte counts,
read wall/thread CPU time, hash-and-loop wall time, and a10s heartbeat. Heartbeats
can identify an in-flight open/read when the main thread is blocked. Metrics
include observer overhead; hash-and-loop is not a pure cryptographic microbenchmark.
A file-read-complete event is explicitly hash-comparison-pending, never proof
that its digest passed. Only the unchanged native receipt after all files pass
establishes complete cache verification. A parent watchdog kills the full child
process group and retains summary/log/journal/manifest on timeout.

Default Kaggle CPU host/Python differs from pinned T4 inference runtime. CPU
success/slowness alone cannot reproduce, attribute or resolve the T4 failure.
The measurement may distinguish a particular file/open/read wait from hash/
loop work; its interpretation must retain host/cache variability and instrument
overhead. No claimed repair until relevant evidence is available.

Seven offline TEST-ONLY fixture probes pass: exact native receipt/byte counts/
four-file progress/both digest algorithms/restoration; native digest/size/path
failures with no success marker; heartbeat during slow synthetic reads and
unchanged2MiB requests; real process-group timeout retaining evidence; real
invalid-mount child admission failure with no receipt. These fixtures contain
small fabricated bytes, not real weights, model provenance or cache-v5 proof.
Notebook schema/source compilation/default-disabled-path probe and Ruff check/
format pass. No product code changed, so the13m full project suite is not rerun
for this one-off diagnostic; historical1,602-pass result is not relabeled fresh.

## Resume

Local source/deploy/single-request launcher/read-only poll/export live under
`.local/kaggle-cache-diagnostic-20261023-d01/` in the benchmark preparation
worktree. Use installed SDK Python for poll.py and terminal-only export_saved.py.
Never resubmit a possibly created ref after an uncertain API response. Preserve
all prior failed artifacts and current journal on timeout, without an automatic
retry or benchmark continuation. Fresh source/private/no-GPU/no-internet/cache
metadata and saved hashes must be checked before interpreting results.

[Machine checkpoint](../evidence/kaggle-cache-diagnostic-2026-10-23-d01.json)
and [source/probe manifest](../evidence/kaggle-cache-diagnostic-2026-10-23-d01/artifacts-manifest.json).

## Launch checkpoint

Preparation commit01e4bc6. One submission accepted as private version1,
kernel140391141:
https://www.kaggle.com/code/aohkvd/nl2sql-cache-diag-20261023-d01

Submitted at19:39:00 Asia/Saigon on2026-10-23. Platform RUNNING
observed at19:39:07 that day. Remote cells exactly match the prepared source;
private/GPU-off/TPU-off/internet-off, setup dataset and cache source metadata
verified. API may normalize the cache reference to its slug; exact v5 inventory
and pinned file checks remain mandatory inside the diagnostic.

Fresh state check: original EN failure and replacement01 ERROR, finalVI and
private cache-v5 COMPLETE, exact diagnostic ref absent before the one push.
GPU quota17.996651111h remaining, zero reserved, pay-to-scale off; this notebook
requests no GPU. Account observation is not invoice cost. No benchmark session
or new native ID was created. Both setup failures and11 native successes remain
unchanged. The CPU diagnostic is not a thirteenth/fourteenth benchmark result.

Actual per-file observations/cache receipt remain pending. A terminal-only
offline verifier is prepared but has not been run against absent results.
After terminal state export original outputs and run verify_saved.py with
project Python; it checks hashes, settings/source identity, monotonic heartbeat/
byte progress, per-file ordering, all24 native receipt files/bytes on success,
and absence of model/benchmark artifacts. A timeout retains its last observed
file/phase rather than a fabricated successful cache receipt.

Monitoring stops after this launch checkpoint, following the user's preference
to return after a completion notice. Poll this existing ref only on return;
never rerun the launcher. This launch does not establish root cause, a cache
repair, T4 equivalence, or readiness for another B2 EN benchmark attempt.

## Terminal API check — 2026-10-23

**ERROR with no saved diagnostic output or execution-log events.** Status
observed at20:16:33 Asia/Saigon on2026-10-23. Exact failure time and
actual runtime start are not established. The private version1 source still
matches the accepted submission; GPU/TPU/internet remain off and dataset/cache
source metadata matches. Source metadata RUNNING at launch was platform state,
not proof that notebook cells or the diagnostic worker began execution.

The full output listing is empty, with no next page. This is not an export
prefix/filter omission. Terminal export downloaded0files,0bytes, no omissions.
The SDK persisted-log endpoint returns the2-byte JSON array `[]` (zero log
events). The stream endpoint returned zero events without exception. Platform
failure_message is empty. There is no diagnostic-summary.json, worker.log,
cache-progress.jsonl, native-cache-receipt.json or saved hash manifest to audit.
The prepared terminal artifact verifier cannot run without those files; no
successful verification or cache receipt is fabricated.

The source-view cell execution counters are null with empty output arrays.
Those belong to the source API and are not proof that runtime never started.
Its last_run_time metadata predates this new submission, so it is not used
as an execution/failure clock. Default CPU Python/version and actual worker
state remain unknown. No evidence currently identifies a file/hash/read stall,
notebook exception, dependency error, startup/staging error, platform timeout,
or output persistence failure. All remain unproven; no speculative fix or cap/
pin/runtime/network change was made in this review.

Therefore the CPU diagnostic produced **no usable per-file measurement**.
It is not another established cache timeout and does not resolve the T4 setup
failure. The2earlier benchmark setup failures and11native successes (13retained
benchmark IDs) remain unchanged. This is1failed diagnostic session, not a new
benchmark replicate/failure. No inference or benchmark was requested by this
session, and no new session or automatic retry was submitted during this check.

API observations/source metadata/download history and empty persisted log are
retained with hashes. They are platform evidence only, not runtime artifacts.
No product code changed or model/tests/install ran in this review. Investigate
why Kaggle supplies no execution log/output before considering a fresh diagnostic
submission. Monitoring stops after this terminal checkpoint. Underlying cache
slowness/root cause remains unresolved; earlier local fixture probes are still
only test evidence, not proof that this remote diagnostic executed.

## Later user-requested API retry and source defect diagnosis

A fresh no-input CPU control exposed a Papermill missing-kernelspec error via
API logs. The same missing metadata is present in this d01 source, though its
own log still returns `[]`. An actual Papermill reproduction and metadata-only
fix passed locally, then a fixed CPU control completed with3saved artifacts.
A fresh d04 cache diagnostic was requested and launched with the same cells/
observer and added python3 kernelspec. D01 remains immutable historical evidence;
its exact platform exception is not invented from the control. See the
[repair/control/retry handoff](kaggle-cpu-admission-repair-and-cache-retry-2026-10-23.md).
