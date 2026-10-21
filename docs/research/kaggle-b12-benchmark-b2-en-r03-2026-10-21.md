# B2 English r03 — 2026-10-21

User explicitly requested next process. Existing B1 VI r03 completed and passed
full artifact/runtime review at `84b0f2a`. Submitted only next scheduled B2 EN
r03, full N=100, unchanged 5,400s native / 7,200s session caps. No full-campaign
budget inferred; this replicate does not replace previous runs.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261021-b2-en-r03

**Version 1 submitted at 23:26:48 Asia/Saigon; QUEUED at 23:27:06.**
Remote cells match submitted source; private/GPU/NvidiaTeslaT4 and accepted
dataset/cache metadata verified. Native inference, actual hardware/runtime and
saved completeness remain unverified. Queue/provisioning adds elapsed time
outside measured native/driver wall time.

Campaign `b12-envi-20261018-c01`, session `s11-b2-en-r03`, run
`b12-envi-20261018-c01-b2-en-r03`. Ten prior IDs match retained B1 VI r03
ledger: all r01/r02 runs, B1 EN r03, B1 VI r03. All prior reviews pass.
Ten complete, eleventh submitted, final B2 VI r03 unstarted. Keep all prior
replicates separate/immutable.

Fresh quota at 23:26:32: 20.353947222h available, 0h reserved, 30h total,
pay-to-scale off. Covers conservative four GPU-device-hour allowance for one
two-hour T4 ×2 session. All ten prior notebooks and private cache v5 COMPLETE;
exact ref absent before one push. Record final account quota delta separately
from invoice cost/general billing rules; running estimates can change.

Only operational settings differ from notebook 16: explicit opt-ins,
B2/EN/r03, session and ten prior IDs/review. Source defaults remain disabled.
Driver SHA remains
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`.
Immutable bundle/cache, full hashed lock/Python 3.11.15, model/encoder pins,
BF16/4-bit, seed 42, greedy, batch 1, 512 tokens, prompts/normalization,
retrieval and thresholds unchanged. B2 uses only accepted 7,208-row train
export SHA `b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`;
no development/benchmark/gold rows enter its matrix. No outcome-driven tuning.

Retain native unsafe/invalid/prose outputs, conservative aggregate review/live
flags and scientific blockers. No repair/retry, partial-run merge, canonical
adaptation, BigQuery, training, B3 or Phase 6–7 work. Each run/language keeps
N=100 separate; B0 stays English-only.

## Resume existing session

Read-only poll and bounded export helpers are under
`.local/kaggle-b12-benchmark-20261021-b2-en-r03/` in this worktree:

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261021-b2-en-r03/poll.py --status-only
```

After terminal status run `export_saved.py` there. Retain all original native
JSON/JSONL/log/Python/NPZ/lock campaign outputs including retrieval cache;
32 MiB per-file bounds, no model downloads or signed URL persistence. Review
omissions, then verify all manifest/report hashes, 100 genuine EN completions/
ordered IDs/questions/source authority, accepted 7,208-row cache identities/
matrix and all 500 selected training examples, unchanged settings, actual
hardware/software/runtime, scratch cleanup and exact eleven-attempt ledger.
Do not introduce a new language filter/family-diversity constraint absent from
the original retriever. No splicing/overwriting replicates; failed/timed-out
attempts must be retained first. No resubmission to resume monitoring.

Fresh checks: previous full result, notebook compilation/operational-only
changes, ten prior IDs, quota/cache/prior statuses, matching remote source
and private GPU metadata. No local inference/pytest suite reran; preparation
counts stay historical. T5.4 and separate BigQuery authorization pending.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b2-en-r03-2026-10-21.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b2-en-r03-2026-10-21/artifacts-manifest.json).
