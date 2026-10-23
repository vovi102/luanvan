# B2 English r02 — 2026-10-20

The user explicitly requested checking B1 VI r02 results and launching the next
process. B1 VI r02 finished and passed full runtime/artifact review at `2a24069`.
Submitted only the next scheduled B2 EN r02, N=100, unchanged 5,400s native /
7,200s session caps. No full-campaign budget is inferred.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261020-b2-en-r02

**Version 1 COMPLETE; N=100 independently verified on 2026-10-21.**
Submitted at 23:08:04 Asia/Saigon on 2026-10-20; native process finished at
00:15:40 on 2026-10-21. Platform COMPLETE was checked at 19:08:14 that day;
exact platform completion time was not observed.
Remote cells match submitted source; metadata confirms private, GPU enabled,
NvidiaTeslaT4 and accepted dataset/cache sources. The original RUNNING status did not verify inference; saved artifact/runtime
completeness now passes the checks below.

Campaign `b12-envi-20261018-c01`, session `s07-b2-en-r02`, run
`b12-envi-20261018-c01-b2-en-r02`. Prior ledger exactly matches the retained
B1 VI r02 ledger: all four r01 runs, B1 EN r02, B1 VI r02. All six prior
reviews pass; seven processes verified complete, five unstarted at this review.
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

## Verified result — 2026-10-21

Retained all 25 saved campaign files (11,384,126 bytes), no omissions/model
payload downloads. All 24 native manifest entries (including NPZ, metadata and
empty lock) and report compact canonical JSON self-digest pass; repository
manifest covers full retained evidence including native manifest.

Verified all 100 genuine EN completions, ordered IDs/original questions and
trusted/reviewed/live case authorities; unchanged model/encoder/settings,
T4 ×2, Python 3.11.15, torch 2.5.1+cu124 / CUDA 12.4, input/cache/data/runtime
gates, native exit 0 and scratch cleanup pass. Exact ledger contains all four
r01 runs, B1 EN r02, B1 VI r02, then B2 EN r02. Only this run occurs in this
session; original r01 remains separate. Offline cache load verifies the
7,208 × 384 training matrix and full identities/digests without encoding.
All 500 selected examples match the accepted training question/SQL/language/
family lineage; five distinct training record IDs per case, no new family
constraint imposed. No development/benchmark rows enter the matrix.

| Observation | Value |
|---|---:|
| EN denominator / genuine generations | 100 / 100 |
| Extraction ok | 31 |
| Prose | 60 |
| Unsafe SQL | 8 |
| Invalid SQL | 1 |
| Generation P50 | 32.443s |
| Generation P95 | 51.300s |
| Native wall | 3,550.515s (59.18m) |
| Driver wall including setup/checks | 3,823.914s (63.73m) |

These are extraction/runtime observations, not SQL execution accuracy. Native
scientific readiness remains false with original `latency_gate_failed`,
`live_evidence_missing`, `reviewed_test_set_missing` blockers. Source authorities
pass; unchanged CLI25/CLI17 aggregate review/live flags remain conservative,
as previously audited. No flags, thresholds, SQL, reports, settings, model or
research semantics changed. No repair/retry, partial-run merge, canonical
adaptation, BigQuery, training or local inference ran.

Account quota on return: 23.094585833h remaining, 0h reserved; observed account
usage delta from pre-launch snapshot 1.066697778h. This is quota observation
across the interval, not invoice cost or a universal billing rule.

Campaign 7/12 complete at review, five unstarted. User explicitly authorized
next B2 VI r02; proceed only after fresh quota/cache/duplicate checks, carrying
all seven attempted IDs. No whole-campaign budget inferred. Each run/language
keeps N=100 separate; B0 remains English-only. T5.4 and separately authorized
BigQuery remain pending. Fresh verification covered saved bytes, lineage,
retrieval/cache/runtime and ledger; no local inference or pytest suite reran.
Full native evidence, verification source/result and download record are retained
under the linked checkpoint directory.
