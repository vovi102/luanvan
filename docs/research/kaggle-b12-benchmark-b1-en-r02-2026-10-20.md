# B1 English r02 — 2026-10-20

After verified B2 VI r01 results at `56db251`, the user explicitly said
“oke khởi chạy đi” for the next B1 EN r02 process. Submitted only this scheduled
replicate, full N=100, with unchanged 5,400s native / 7,200s session caps.
This is the preplanned r02 replicate, not a replacement or accuracy-directed
retry of r01. No whole-campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261020-b1-en-r02

**Version 1 COMPLETE; N=100 independently verified on 2026-10-20.**
Submitted at 19:58:01 Asia/Saigon; native process finished at 20:55:45.
Platform COMPLETE was checked at 21:01:30; exact platform completion time was
not observed.
Remote cells match the submitted source; metadata confirms private, GPU enabled,
NvidiaTeslaT4, accepted input dataset and cache source. The initial RUNNING checkpoint did not establish native inference completion;
the saved evidence now verifies actual runtime/hardware and all 100 completions.

Campaign `b12-envi-20261018-c01`, session `s05-b1-en-r02`, native run
`b12-envi-20261018-c01-b1-en-r02`. Prior ledger matches the retained B2 VI
ledger exactly: B1 EN r01, B1 VI r01, B2 EN r01, B2 VI r01. All four prior
runtime/artifact reviews pass. Campaign: five verified processes, seven unstarted.

Fresh quota at 19:57:48: 25.789861667h available, 0h reserved, 30h total,
pay-to-scale disabled. This exceeds the conservative four GPU-device-hour
allowance for one two-hour T4 ×2 session. All four prior notebooks and private
cache v5 were COMPLETE; exact requested kernel ref did not exist before push.
Exactly one version/session submitted. Record final observed quota separately
from invoice cost; live estimates can change.

Only operational notebook settings change: explicit opt-ins, B1/EN/r02, session
and prior attempted IDs/review. Prepared source defaults remain disabled.
Driver SHA stays
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`;
accepted immutable bundle/cache, full hashed lock/Python 3.11.15, pinned model
and encoder, BF16/4-bit, seed 42, greedy, batch 1, 512 tokens, prompts,
normalization and thresholds remain unchanged. B1 remains zero-shot; no
development/benchmark/gold rows enter retrieval. No settings were selected
from r01 outcomes.

Keep native invalid/unsafe SQL and conservative review/live flags/blockers.
No SQL repair, automatic replacement/retry, partial-run merge, canonical
adaptation, BigQuery, training, B3 or Phase 6–7 work is included. Each language
keeps N=100; no EN/VI pooling. B0 remains English-only.

## Resume existing session

Local read-only poll and bounded saved-output export helpers are in
`.local/kaggle-b12-benchmark-20261020-b1-en-r02/` in this worktree.

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261020-b1-en-r02/poll.py --status-only
```

After terminal status run `export_saved.py` there. It retains original native
JSON/JSONL/log/Python/NPZ/lock outputs under the campaign prefix, bounds files
at 32 MiB, excludes model downloads and never persists signed URLs. Review any
omission before claiming completeness. Verify all manifest/report hashes,
ordered 100 EN case IDs and questions, genuine completion markers, immutable
input/cache/settings, actual hardware/software/runtime, owned-scratch cleanup
and exact five-attempt ledger. Keep r01 and r02 separate; do not splice or
overwrite artifacts. Failure/timeout requires retaining evidence before any
next decision. No resubmission is needed to resume monitoring.

Fresh deployment checks: compiled notebook, operational-only cell changes,
four-attempt prior ledger, quota/cache/prior statuses, matching remote cells
and private GPU/source metadata. No local inference or pytest suite reran;
preparation-suite counts remain historical. T5.4 and separately authorized
BigQuery remain pending.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b1-en-r02-2026-10-20.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b1-en-r02-2026-10-20/artifacts-manifest.json).

## Verified result

Retained all 22 saved campaign files (435,126 bytes), with no omitted artifacts
or model payload downloads. All 21 native manifest entries match lengths and
SHA-256. Native report self-digest passes its compact canonical JSON format;
the repository manifest also covers the native manifest.

Verified all 100 genuine completions, ordered English case IDs and original
questions, trusted/reviewed/live source authorities, empty B1 selected examples,
unchanged seed 42/greedy/batch/token/4-bit settings and pinned model/encoder.
Actual hardware/runtime: Tesla T4 ×2, Python 3.11.15, torch 2.5.1+cu124 /
CUDA 12.4. Input/cache/data/runtime gates pass, native exit 0 and driver-owned
scratch removed. Exact ledger contains the four r01 runs then B1 EN r02; only
r02 is present in this session. Original r01 files remain separate and unchanged.

| Observation | Value |
|---|---:|
| English denominator / genuine generations | 100 / 100 |
| Extraction ok | 0 |
| Unsafe SQL | 99 |
| Invalid SQL | 1 |
| Generation P50 | 25.522s |
| Generation P95 | 48.809s |
| Native process wall | 2,876.815s (47.95m) |
| Driver wall including setup/checks | 3,157.134s (52.62m) |

These are extraction/runtime observations, not SQL execution accuracy. Native
scientific readiness remains false; unchanged blockers are `latency_gate_failed`,
`live_evidence_missing`, `reviewed_test_set_missing`. Trusted case authorities
pass, while unchanged CLI25/CLI17 aggregate review/live flags remain conservative
as recorded in the first B1 audit. No flags/gates, native report, SQL, prompts,
model or research settings were changed. No repair/retry, partial-run merge,
canonical adaptation, BigQuery, training or new inference was performed.

Account quota on return: 24.906805833h remaining, 0h reserved. Observed account
usage delta from pre-launch snapshot: 0.883055833h. This is account quota
observation across the interval, not invoice cost or a general billing rule.

Campaign **5/12 native processes verified complete**, seven unstarted. Next
planned B1 VI r02 was not launched by this result check. Keep each run and
language denominator N=100 separately; no EN/VI pooling or full-campaign
completion claim. B0 remains English-only; T5.4 and separately authorized
BigQuery remain pending. Fresh verification covered saved hashes, completion
markers, source authority, settings, runtime, cleanup and ledger. No local
inference or pytest suite reran. See `verified-result.json`, verification source,
download record and full `saved-v1/` evidence under the checkpoint directory.
