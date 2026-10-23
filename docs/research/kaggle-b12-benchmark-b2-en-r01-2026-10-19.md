# B2 English r01 — 2026-10-19

After the verified B1 VI r01 result at `7dcbeb6`, the user said
“OKe tiếp tục triển khai đi”. The next single scheduled process B2 EN r01,
N=100, was submitted under the unchanged 5,400s native / 7,200s session caps.
No authorization of the whole remaining campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261019-b2-en-r01

**Version 1 COMPLETE; N=100 independently verified on 2026-10-19.**
Submitted at 19:08:56 Asia/Saigon; native inference finished at 20:43:25.
Platform COMPLETE was checked at 21:12:55; the exact platform completion time
was not observed. Remote cells match the submitted source; server metadata
confirms private, GPU enabled, NvidiaTeslaT4, and accepted input/cache sources.

Campaign `b12-envi-20261018-c01`, session `s03-b2-en-r01`, native run
`b12-envi-20261018-c01-b2-en-r01`. The prior ledger carries exactly B1 EN r01
then B1 VI r01; both completed runtime/artifact reviews. Three of twelve native
processes are verified complete; nine remain unstarted.

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

## Verified result

All 25 saved campaign files retained (11,383,637 bytes), including the NPZ
retrieval cache, metadata and original empty lock. The initial bounded export
omitted the lock extension; its original zero-byte contents were subsequently
fetched and verified. No saved campaign artifact remains omitted. All 24 native
manifest entries match length and SHA-256; the report compact canonical JSON
self-digest passes. The repository manifest also covers the native manifest.

Verified 100 genuine completions, ordered English case IDs and original
questions, unchanged seed/model/settings, T4 ×2 hardware, Python 3.11.15,
torch 2.5.1+cu124 / CUDA 12.4, immutable input/cache/data/runtime gates and
owned-scratch cleanup. Native exit is 0. The ledger contains B1 EN r01,
B1 VI r01, then B2 EN r01; this session has only the B2 EN run.

The original cache loads offline with no encoder or inference: matrix
7,208 × 384, all record identities and training/cache hashes match the accepted
training snapshot. All 500 selected examples (five distinct record IDs per
question) match training question/SQL, English language, semantic-family lineage
and pinned encoder. No development/benchmark rows enter this training matrix.
A first local audit incorrectly required five distinct semantic families;
source review confirmed the original retriever requires five eligible records,
with no family-diversity constraint. The audit was corrected to distinct record
IDs; native artifacts and research behavior were unchanged. This correction is
retained in `verifier-correction.json`.

| Observation | Value |
|---|---:|
| English denominator / genuine generations | 100 / 100 |
| Extraction ok | 31 |
| Prose | 60 |
| Unsafe SQL | 8 |
| Invalid SQL | 1 |
| Generation P50 | 33.696s |
| Generation P95 | 52.987s |
| Native process wall | 3,702.281s (61.70m) |
| Driver wall including setup/checks | 4,098.889s (68.31m) |

Extraction success is not SQL execution accuracy. No BigQuery jobs, canonical
adaptation, SQL repair, retries or partial-run merges occurred. Native
`scientific_ready=false`; blockers remain `latency_gate_failed`,
`live_evidence_missing`, `reviewed_test_set_missing`. Trusted source cases pass
review/live lineage checks, while original CLI25/CLI17 aggregate flags remain
conservative, as documented in the B1 audit. No flags or gates were bypassed.

Account quota on return: 26.902696667h remaining, 0h reserved; observed account
usage delta from the pre-launch snapshot 1.144085278h. This is quota observation
across the interval, not invoice cost or a universal billing rule.

Campaign **3/12 native processes complete**, nine unstarted. EN and VI remain
separate N=100 denominators. The next scheduled process B2 VI r01 was not
launched by this result check. T5.4 and separately authorized BigQuery work remain
pending; B0 remains English-only. Fresh checks covered saved artifact integrity,
retrieval authority and runtime/completeness. No local inference or pytest suite
was rerun. See `verified-result.json`, `verification-source.py`, the download
record and full `saved-v1/` evidence under the linked checkpoint directory.
