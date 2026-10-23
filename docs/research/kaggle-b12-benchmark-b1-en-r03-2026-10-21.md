# B1 English r03 — 2026-10-21

User saw completion notification and explicitly requested the next process.
B2 VI r02 finished and passed full artifact/runtime review at `b8147e6`.
Submitted only next scheduled B1 EN r03, N=100, unchanged 5,400s native /
7,200s session caps. No whole-campaign budget inferred; this planned replicate
does not replace previous runs.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261021-b1-en-r03

**Version 1 COMPLETE; N=100 independently verified on 2026-10-21.**
Submitted at 20:33:40 Asia/Saigon; native process finished at 21:28:26.
Platform COMPLETE checked at 22:14:32; exact platform completion time not observed.
Remote cells match submitted source; private/GPU/NvidiaTeslaT4 and accepted
dataset/cache metadata verified. Saved native inference, actual hardware/runtime and
completeness now pass the verification below. Queue/provisioning adds elapsed time outside
measured driver/native wall time.

Campaign `b12-envi-20261018-c01`, session `s09-b1-en-r03`, run
`b12-envi-20261018-c01-b1-en-r03`. Eight prior attempted IDs match retained
B2 VI r02 ledger exactly: all four r01 runs then all four r02 runs. All prior
reviews pass. Nine verified complete, three unstarted at this result review.

Fresh quota at 20:33:27: 21.979518611h available, 0h reserved, 30h total,
pay-to-scale off. Covers conservative four GPU-device-hour allowance for one
two-hour T4 ×2 session. All eight prior notebooks and private cache v5 COMPLETE;
exact ref absent before one push. Record final observed quota delta separately
from invoice cost or general billing rules.

Only operational settings differ from notebook 16: explicit opt-ins,
B1/EN/r03, session and eight prior IDs/review. Source defaults remain disabled.
Driver SHA remains
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`.
Immutable bundle/cache, full hashed lock/Python 3.11.15, model/encoder pins,
BF16/4-bit, seed 42, greedy, batch 1, 512 tokens, prompts/normalization and
thresholds unchanged. B1 remains zero-shot; no development/benchmark/gold rows
enter retrieval. No settings selected from earlier test outcomes.

Retain native unsafe/invalid SQL and conservative aggregate review/live flags
and scientific blockers. No repair/retry, partial-run merging, canonical
adaptation, BigQuery, training, B3 or Phase 6–7 work included. Each run/language
keeps N=100 separate; B0 remains English-only.

## Resume existing session

Read-only poll and bounded export helpers are under
`.local/kaggle-b12-benchmark-20261021-b1-en-r03/` in this worktree:

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261021-b1-en-r03/poll.py --status-only
```

After terminal status run `export_saved.py` there. It retains native
JSON/JSONL/log/Python/NPZ/lock campaign outputs, bounds files at 32 MiB,
excludes model payloads and persists no signed URLs. Review omissions, then
verify all manifest/report hashes, 100 genuine EN completions/ordered case
IDs/questions/source authority, zero-shot settings, input/cache gates, actual
hardware/software/runtime, scratch cleanup and exact nine-attempt ledger.
Keep r01/r02/r03 separate and immutable. Failed/timed-out attempts must be
archived before any next decision; no resubmission needed to resume monitoring.

Fresh checks: previous full result, notebook compilation/operational-only
changes, eight prior IDs, quota/cache/prior statuses, matching remote source
and private GPU metadata. No local inference/pytest suite reran; preparation
counts remain historical. T5.4 and separate BigQuery authorization pending.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b1-en-r03-2026-10-21.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b1-en-r03-2026-10-21/artifacts-manifest.json).

## Verified result

All 22 saved campaign files retained (435,615 bytes), no omissions/model
payload downloads. All 21 native manifest entries and report compact canonical
JSON self-digest pass; repository manifest covers full evidence. Verified
100 genuine EN completions, ordered IDs/questions/trusted reviewed-live source
authorities, empty B1 selected examples, unchanged seed/model/encoder/settings,
immutable input/cache/data/runtime gates, actual T4 ×2, Python 3.11.15,
torch 2.5.1+cu124 / CUDA 12.4, native exit 0 and scratch cleanup. Exact ledger
contains all r01/r02 runs followed by B1 EN r03; this session contains only r03.
Prior replicates stay separate and unchanged.

| Observation | Value |
|---|---:|
| EN denominator / genuine generations | 100 / 100 |
| Extraction ok | 0 |
| Unsafe SQL | 99 |
| Invalid SQL | 1 |
| Generation P50 | 23.260s |
| Generation P95 | 45.922s |
| Native wall | 2,608.453s (43.47m) |
| Driver wall including setup/checks | 2,844.414s (47.41m) |

These are extraction/runtime observations, not SQL execution accuracy. Native
scientific readiness remains false, with unchanged `latency_gate_failed`,
`live_evidence_missing`, `reviewed_test_set_missing`. Source authorities pass;
original CLI25/CLI17 aggregate review/live flags stay conservative as previously
audited. No SQL, report, flags/gates, settings, prompts or model changed.
No repair/retry, partial-run merge, canonical adaptation, BigQuery, training
or local inference ran.

Quota on return: 21.184038056h remaining, 0h reserved; observed account usage
delta 0.795480556h. This is quota observation across the interval, not invoice
cost or a general billing rule. Campaign 9/12 complete at review; three
unstarted. User authorized next B1 VI r03 after fresh quota/cache/duplicate
checks and carrying nine prior IDs. No whole-campaign budget inferred. Keep
each run/language N=100 separate; B0 remains English-only; T5.4 and separately
authorized BigQuery pending. No pytest suite/inference reran for verification.
Full saved outputs, verifier source/result and download record are retained
under the checkpoint directory.
