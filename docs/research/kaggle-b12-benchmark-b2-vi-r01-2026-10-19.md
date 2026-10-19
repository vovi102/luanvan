# B2 Vietnamese r01 — 2026-10-19

The user explicitly said “oke khởi chạy đi” after discussing B2 VI r01.
Submitted only this next scheduled process, full N=100, under unchanged
5,400s native / 7,200s session caps. No whole-campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261019-b2-vi-r01

**Version 1 submitted at 22:13:49 Asia/Saigon; QUEUED at 22:14:06.**
Submission succeeded without source errors. Remote cells match the submitted
source, with private/GPU/NvidiaTeslaT4 and accepted dataset/cache sources
verified. QUEUED does not establish actual inference start, runtime or hardware.
Queue/provisioning time is additional to measured native/driver time.

Campaign `b12-envi-20261018-c01`, session `s04-b2-vi-r01`, run
`b12-envi-20261018-c01-b2-vi-r01`. The cumulative prior ledger exactly matches
the retained B2 EN ledger: B1 EN r01, B1 VI r01, B2 EN r01. All three prior
runtime/artifact reviews pass; B2 EN evidence is committed at `ebec1d7`.
Three of twelve native processes are verified complete; this fourth is submitted
and eight remain unstarted.

Fresh quota at 22:13:41: 26.902696667h remaining, 0h reserved, 30h total,
pay-to-scale disabled. This exceeds the conservative four GPU-device-hour
allowance for one two-hour T4 ×2 session. All three prior notebooks and private
cache v5 were COMPLETE. Fuzzy kernel search returned the completed B2 EN
notebook; an exact-ref comparison confirmed the requested VI notebook did not
exist. The initial broad duplicate guard stopped before any submission and was
corrected to compare exact refs. Exactly one push was made; no retry/version
replacement was submitted. Record settled quota separately from invoice cost.

Only operational settings differ from prepared notebook 16: explicit opt-ins,
B2/VI/r01, this session ID, and all three prior attempted IDs with review true.
Source defaults remain disabled. Driver SHA remains
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`;
immutable bundle/cache, full hashed lock/Python 3.11.15, model/encoder revisions,
BF16/4-bit, seed 42, greedy, batch 1, 512 tokens, prompts, normalization,
retrieval and scientific thresholds remain unchanged.

B2 retrieval uses only the accepted 7,208-row training snapshot, SHA
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
No development/benchmark/gold rows enter its matrix. VI consumes the finalized
typed paired 100-case snapshot with original bulk ACCEPT 5/5/5/1 reviews and
exact reused English live evidence. No new Vietnamese BigQuery execution is
implied. EN/VI N=100 remain separate; B0 remains English-only.

Preserve all native invalid/unsafe SQL and conservative aggregate review/live
flags. No SQL repair, automatic retries, partial-run merge, prompt/model tuning,
canonical adaptation, BigQuery, training, B3 or Phase 6–7 work is included.

## Resume this existing session

Local read-only poll and bounded export helpers are under
`.local/kaggle-b12-benchmark-20261019-b2-vi-r01/` in this worktree.

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261019-b2-vi-r01/poll.py --status-only
```

After terminal status run `export_saved.py` there; it allows native
JSON/JSONL/log/Python/NPZ/lock files, bounds each file at 32 MiB, excludes model
downloads and never persists signed URLs. Check any omission before claiming
completeness. Verify every saved manifest hash and report self-digest, genuine
100-case VI completions, original questions and full paired lineage, exact reused
English evidence, train-only retrieval/cache and selected example authority,
hardware/runtime/software gates, owned-scratch cleanup and four-attempt ledger.
If failed/timed out retain evidence before any next decision; do not resubmit
to resume monitoring. T5.4 and separate BigQuery authorization remain pending.

Fresh deployment checks: notebook compilation, unchanged non-setting cells,
ledger, fresh quota/cache/prior status, matching remote cells and private GPU
metadata. Actual inference/hardware remain unverified; no local inference or
pytest suite was rerun. Preparation test counts remain historical.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b2-vi-r01-2026-10-19.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b2-vi-r01-2026-10-19/artifacts-manifest.json).
