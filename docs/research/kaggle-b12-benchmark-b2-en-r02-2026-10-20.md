# B2 English r02 — 2026-10-20

The user explicitly requested checking B1 VI r02 results and launching the next
process. B1 VI r02 finished and passed full runtime/artifact review at `2a24069`.
Submitted only the next scheduled B2 EN r02, N=100, unchanged 5,400s native /
7,200s session caps. No full-campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261020-b2-en-r02

**Version 1 submitted at 23:08:04 Asia/Saigon; RUNNING at 23:08:19.**
Remote cells match submitted source; metadata confirms private, GPU enabled,
NvidiaTeslaT4 and accepted dataset/cache sources. Platform status alone does
not verify native inference, actual hardware/runtime or saved completeness.

Campaign `b12-envi-20261018-c01`, session `s07-b2-en-r02`, run
`b12-envi-20261018-c01-b2-en-r02`. Prior ledger exactly matches the retained
B1 VI r02 ledger: all four r01 runs, B1 EN r02, B1 VI r02. All six prior
reviews pass; six processes verified complete, seventh running, five unstarted.
This scheduled replicate does not replace or overwrite r01.

Fresh quota at 23:07:55: 24.161283611h remaining, 0h reserved, 30h total,
pay-to-scale disabled. It covers the conservative four GPU-device-hour allowance
for one two-hour T4 ×2 session. All six prior notebooks and private cache v5
were COMPLETE; exact requested ref absent before the single push. Record final
account quota delta separately from invoice cost/general billing assumptions.

Only operational settings change from prepared notebook 16: explicit opt-ins,
B2/EN/r02, session and six prior IDs/review. Source defaults remain disabled.
Driver SHA remains
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`.
Immutable bundle/cache, full hashed lock/Python 3.11.15, model/encoder revisions,
BF16/4-bit, seed 42, greedy, batch 1, 512 tokens, prompts, normalization,
retrieval and thresholds unchanged. No settings selected from preceding test
outcomes. B2 uses only the 7,208-row accepted training export with SHA
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`;
development/benchmark/gold rows do not enter retrieval matrices.

Preserve native unsafe/invalid/prose outputs and conservative review/live flags
and blockers. No repair, replacement retry, partial-run merge, canonical
adaptation, BigQuery, training, B3 or Phase 6–7 work is included. Keep each run
and language N=100 separate; B0 remains English-only.

## Resume existing session

Local read-only polling and bounded export helpers are under
`.local/kaggle-b12-benchmark-20261020-b2-en-r02/` in this worktree:

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261020-b2-en-r02/poll.py --status-only
```

After terminal status run `export_saved.py` there. Retain original
JSON/JSONL/log/Python/NPZ/lock campaign outputs, including training cache; export
bounds files at 32 MiB, excludes model downloads and persists no signed URLs.
Review omissions, then verify all manifest/report hashes, ordered 100 EN case
IDs/questions, genuine model markers, source authority, accepted 7,208-row
cache identities/matrix and all 500 selected examples, unchanged settings,
actual hardware/software/runtime, scratch cleanup and seven-attempt ledger.
Keep r01/r02 separate; do not resubmit to resume monitoring. Failure/timeout
requires retaining evidence before the next decision.

Fresh checks covered the previous process's full result, notebook compilation,
operational-only changes, six prior IDs, fresh quota/cache/prior statuses,
matching remote cells and private GPU metadata. No local inference or pytest
suite reran; preparation counts remain historical. T5.4 and separately
authorized BigQuery remain pending.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b2-en-r02-2026-10-20.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b2-en-r02-2026-10-20/artifacts-manifest.json).
