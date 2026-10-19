# B2 English r01 — 2026-10-19

After the verified B1 VI r01 result at `7dcbeb6`, the user said
“OKe tiếp tục triển khai đi”. The next single scheduled process B2 EN r01,
N=100, was submitted under the unchanged 5,400s native / 7,200s session caps.
No authorization of the whole remaining campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261019-b2-en-r01

**Version 1 submitted at 19:08:56 Asia/Saigon; RUNNING at 19:09:28.**
These are platform status observations, not proof that native inference has
started or finished. Actual runtime, hardware and output completeness remain
unverified until saved evidence is available. Remote cells match the submitted
source; server metadata confirms private, GPU enabled, NvidiaTeslaT4, and the
accepted input/cache sources.

Campaign `b12-envi-20261018-c01`, session `s03-b2-en-r01`, native run
`b12-envi-20261018-c01-b2-en-r01`. The prior ledger carries exactly B1 EN r01
then B1 VI r01; both completed runtime/artifact reviews. Two of twelve native
processes are verified complete; this third process is pending verification.

Fresh quota at 19:08:43: 28.046781944h available, 0h reserved, 30h total,
pay-to-scale disabled. It covers the conservative 4 GPU-device-hour allowance
for this single two-hour T4 ×2 session. Both previous sessions and the private
cache v5 were COMPLETE; no matching B2 EN notebook existed before submission.
Record the observed account quota delta after completion separately from cost
or any general billing rule. Do not infer final usage from live estimates.

Only operational settings differ from the prepared notebook: explicit opt-ins,
B2 / EN / r01, this session ID, and the two prior attempted IDs with completed
review. The immutable bundle, unchanged driver SHA
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`,
full hashed lock/Python 3.11.15, model/encoder revisions, BF16/4-bit,
seed 42, greedy generation, batch 1, 512-token limit, original prompts,
normalization, retrieval and acceptance thresholds remain unchanged. Committed
notebook 16 retains its disabled defaults.

B2 retrieval uses only the immutable 7,208-row training export, SHA
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
No 792 development rows, benchmark questions or gold SQL enter the retrieval
matrix. Do not select settings from the B1 benchmark outcomes. Preserve native
unsafe/invalid SQL, conservative review/live flags and scientific blockers.
No repair, retry, partial-run merge, canonical adaptation, BigQuery, training,
B3 or Phase 6–7 work is included. EN N=100 stays separate from VI; B0 remains
English-only.

## Resume existing session

Read-only poll and bounded saved-output export helpers are in
`.local/kaggle-b12-benchmark-20261019-b2-en-r01/` in this worktree.
Use the installed Kaggle SDK Python; authentication stays internal:

```bash
/home/khoavd/.local/share/uv/tools/kaggle/bin/python \
  .local/kaggle-b12-benchmark-20261019-b2-en-r01/poll.py --status-only
```

After terminal status, run `export_saved.py` from that directory. It retains
JSON/JSONL/log/Python and NPZ artifacts under the campaign output prefix, with
32 MiB per-file bounds and no signed URL persistence or model downloads. B2
retrieval cache must be retained and checked alongside every native manifest
entry; review any omitted artifact before claiming completeness. Verify the
native report self-digest, ordered 100 EN case IDs, genuine completion markers,
train-only retrieval authority, actual hardware/software, immutable inputs,
cache gates, owned-scratch cleanup and cumulative three-attempt ledger. No
replacement upload is needed to resume monitoring. Runtime failure or timeout
requires retaining evidence before any next operational decision.

Fresh deployment checks covered quota, prior/cache status, submitted cell
compilation, matching remote source and private GPU/source metadata. No inference
or pytest suite was rerun locally. Preparation test counts remain historical.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-b2-en-r01-2026-10-19.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-b2-en-r01-2026-10-19/artifacts-manifest.json).
