# B1 English r03 — 2026-10-21

User saw completion notification and explicitly requested the next process.
B2 VI r02 finished and passed full artifact/runtime review at `b8147e6`.
Submitted only next scheduled B1 EN r03, N=100, unchanged 5,400s native /
7,200s session caps. No whole-campaign budget inferred; this planned replicate
does not replace previous runs.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261021-b1-en-r03

**Version 1 submitted at 20:33:40 Asia/Saigon; QUEUED at 20:33:58.**
Remote cells match submitted source; private/GPU/NvidiaTeslaT4 and accepted
dataset/cache metadata verified. Native inference, actual hardware/runtime and
completeness remain unverified. Queue/provisioning adds elapsed time outside
measured driver/native wall time.

Campaign `b12-envi-20261018-c01`, session `s09-b1-en-r03`, run
`b12-envi-20261018-c01-b1-en-r03`. Eight prior attempted IDs match retained
B2 VI r02 ledger exactly: all four r01 runs then all four r02 runs. All prior
reviews pass. Eight verified complete, ninth submitted, three unstarted.

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
