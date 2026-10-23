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
