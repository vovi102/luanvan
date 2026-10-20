# B1 English r02 — 2026-10-20

After verified B2 VI r01 results at `56db251`, the user explicitly said
“oke khởi chạy đi” for the next B1 EN r02 process. Submitted only this scheduled
replicate, full N=100, with unchanged 5,400s native / 7,200s session caps.
This is the preplanned r02 replicate, not a replacement or accuracy-directed
retry of r01. No whole-campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261020-b1-en-r02

**Version 1 submitted at 19:58:01 Asia/Saigon; RUNNING at 19:58:17.**
Remote cells match the submitted source; metadata confirms private, GPU enabled,
NvidiaTeslaT4, accepted input dataset and cache source. Platform RUNNING does
not establish native inference start or completion. Actual hardware/runtime and
native completeness remain unverified until saved evidence is available.

Campaign `b12-envi-20261018-c01`, session `s05-b1-en-r02`, native run
`b12-envi-20261018-c01-b1-en-r02`. Prior ledger matches the retained B2 VI
ledger exactly: B1 EN r01, B1 VI r01, B2 EN r01, B2 VI r01. All four prior
runtime/artifact reviews pass. Campaign: four verified processes, fifth
submitted/running, seven unstarted.

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
