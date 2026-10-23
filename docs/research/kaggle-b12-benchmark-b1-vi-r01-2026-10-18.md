# B1 Vietnamese r01 — 2026-10-18

After the full B1 EN r01 artifacts/runtime passed completeness review and were
committed at `3b93dd1`, the user said to continue. The next single scheduled
process is B1 VI r01, N=100, with the same 5,400s native / 7,200s session caps.
This continuation does not imply approval of the entire remaining campaign
budget. No settings were selected from English test accuracy or SQL validity.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261018-b1-vi-r01

**Version 1 COMPLETE; full B1 VI r01 independently verified on 2026-10-19, N=100.**
Submitted at 21:52:02 Asia/Saigon on 2026-10-18. Native inference finished at
22:38:23 that evening; platform COMPLETE was first checked after returning on
2026-10-19 at 19:03:27. The exact platform completion time was not observed.
Remote notebook cells match the submitted source; metadata confirms private,
GPU enabled, requested NvidiaTeslaT4. Cache v5 remains private COMPLETE.

Campaign `b12-envi-20261018-c01`, session `s02-b1-vi-r01`, native run
`b12-envi-20261018-c01-b1-vi-r01`. The exact previous attempted ID
`b12-envi-20261018-c01-b1-en-r01` is carried from its immutable ledger.
`PRIOR_COMPLETENESS_REVIEWED=True` reflects the completed runtime/artifact review.
Only operational notebook settings differ; driver SHA, immutable archive, cache
pins, full hashed lock/Python 3.11.15, model, encoder, original BF16/4-bit,
seed/greedy/batch/token cap, prompts/retrieval/normalization and thresholds remain
unchanged. All source preparation defaults remain disabled in notebook 16.

Fresh quota before launch at 21:51:20: 28.822119h available, 0h reserved,
30h total, pay-to-scale off. It covers the conservative 4 GPU-device-hours for
one two-hour T4 ×2 session. Record actual final account quota delta separately
from invoice cost or general billing rules. No parallel benchmark session runs;
EN v1 is already COMPLETE before this submission.

VI consumes the unchanged finalized typed paired snapshot: 100 original user
bulk ACCEPT events with scores 5/5/5/1 and exact reused English live evidence.
No new BigQuery execution is implied. Metrics retain N=100 VI separately from
EN. English B0 0/100 is not a Vietnamese control. No gold/benchmark or 792
development rows enter retrieval/embedding matrices; B2's train authority remains
the immutable 7,208-row export. B1 remains zero-shot.

The unchanged CLI25/CLI17 conservative review/live aggregate flags remain false,
as in the English process; no flags or native blockers are bypassed. Preserve
all outputs including invalid/unsafe SQL. No repair, accuracy-directed retry,
partial-run merging, threshold change or research-semantic change. Runtime
failure/timeout stops the process. Capture complete native outputs, hardware,
software/cache/data gates and the cumulative ledger before further work.

T5.4 adaptation/privacy/cost and separately authorized BigQuery execution remain
pending. No B3, constrained decoding, demo or Phase 6–7 implementation is included.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b1-vi-r01-2026-10-18.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b1-vi-r01-2026-10-18/artifacts-manifest.json).

## Monitoring stopped at user request

Historical checkpoint, superseded by the verified result below. The user asked
to stop checking and return later. **No Kaggle cancellation was
requested**; the existing private v1 session continues under its native/session
caps. No new remote check was made after that request. Last observed state was
RUNNING at **22:06:56 Asia/Saigon** (15:06:56 UTC), with 28.57429h account GPU
quota remaining. This is a last-known snapshot, not a current completion claim.

On return, inspect the **existing** notebook v1 and its saved outputs; resuming
monitoring does not require another upload or GPU session. Local monitoring and
bounded export helpers remain in
`.local/kaggle-b12-benchmark-20261018-b1-vi-r01/` in this worktree:

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261018-b1-vi-r01/poll.py --status-only
```

After terminal status and saved output availability, run `export_saved.py` from
that same helper directory with the Kaggle tool Python, then run its
`verify_saved.py` with `PYTHONPATH=src` and the project's shared `.venv/bin/python`.
The verifier uses the accepted release extracted under
`.local/benchmark-preparation/driver-accepted-input`. Check complete N=100 VI,
genuine markers, original question/paired lineage, exact reused English evidence,
all manifest/report hashes, runtime/hardware and the cumulative ledger. Preserve
invalid/unsafe SQL and all scientific blockers. No additional inference,
canonical adaptation, BigQuery or next process is part of resuming status checks.

## Verified result — 2026-10-19

Resumed read-only status checks on the existing private version 1; no upload,
replacement run or additional GPU session was started. Downloaded all 22 saved
campaign files (1,126,718 bytes), with no omissions or model payload downloads.
All 21 driver-manifest files match byte lengths and SHA-256; the report's
compact canonical JSON self-digest also passes. The retained repository manifest
covers the saved native manifest and all other evidence files.

All 100 genuine model completions and ordered case IDs pass completeness checks.
Each prediction matches the original Vietnamese question and its full typed
paired source. All 100 cases load as trusted, reviewed and live-verified; native
gold evidence mode remains `exact_reused_english_live_evidence`. No new Vietnamese
BigQuery execution is implied. Seed 42, greedy generation, batch 1, 512-token
cap, 4-bit settings, pinned model/encoder, input/cache hashes and unchanged driver
all pass verification. Actual runtime is Tesla T4 ×2, Python 3.11.15,
torch 2.5.1+cu124 / CUDA 12.4. Data/runtime/cache preflights pass, native exit is
0, and driver-owned scratch was removed. The cumulative ledger contains exactly
EN r01 followed by VI r01; this session contains only the VI run.

| Observation | Value |
|---|---:|
| Finalized Vietnamese denominator | 100 |
| Genuine generations | 100 |
| Extraction ok | 0 |
| Unsafe SQL | 100 |
| Generation P50 | 20.461s |
| Generation P95 | 30.376s |
| Native process wall time | 2,230.035s (37.17m) |
| Driver wall time, including setup/checks | 2,766.555s (46.11m) |

These are native extraction/runtime observations, not SQL execution accuracy.
P95 fails the unchanged B1 <5s gate. Native `scientific_ready=false` and blockers
remain `latency_gate_failed`, `live_evidence_missing`, and
`reviewed_test_set_missing`. As audited for EN, CLI25 omits the manual review/live
flags and CLI17's defaults keep aggregate gates conservative, even though the
trusted loader cases have those source authorities. No flags, native artifacts,
SQL, prompts, thresholds or research semantics were changed; no SQL repair or
retry occurred.

Account quota on return: 1.953218056h used, 28.046781944h remaining, 0h reserved.
Observed account delta from the pre-launch snapshot is 0.775337222h (46.520m).
This is an account quota observation across the interval, not invoice cost or a
universal hardware billing rule.

Campaign progress is **2/12 native processes complete**, with EN and VI each
N=100 and kept separate. Ten remain unstarted; the next planned session is
B2 EN r01, not launched by this status-check continuation. T5.4 adaptation,
privacy/cost evidence and separately authorized BigQuery work remain pending.
B0's existing result remains English-only. No full-campaign completion is claimed.

Fresh verification covered downloaded artifacts, lineage, model markers,
hardware/runtime, ledger and cleanup. No inference or pytest suite was rerun;
preparation test counts remain historical. See the machine checkpoint,
`verified-result.json`, `download-record.json`, verification source, and the full
`saved-v1/` outputs under the linked evidence directory.
