# First genuine B1 EN benchmark — 2026-10-18

The user explicitly authorized private upload and **only the first full B1 EN
r01 process**, N=100, after a fresh quota check. Native cap 5,400s; platform session
cap 7,200s. This does not authorize the remaining eleven processes, the proposed
27-hour campaign budget, automatic replacement runs, BigQuery, training, B3 or
changes to research semantics.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261018-b1-en-r01

**Version 1 COMPLETE; full B1 EN r01 verified, N=100.** All 100 native
completions are genuine, all 100 prediction/log IDs match the finalized English
snapshot, and all retained output hashes pass. This is one native process out
of twelve; scientific campaign completion remains blocked.

Campaign `b12-envi-20261018-c01`, session `s01-b1-en-r01`, native run
`b12-envi-20261018-c01-b1-en-r01`. Source is preparation commit `8194926`;
only notebook settings change to explicit opt-in and this one process. The
committed preparation notebook still defaults all three opt-ins to false.
Remote notebook cells match the submitted source. Server metadata confirms
private, GPU enabled and requested `NvidiaTeslaT4`.

Fresh quota at 06:27:28 UTC (13:27:28 Asia/Saigon): 29.76275h available,
0h reserved, 30h weekly total, pay-to-scale disabled; refresh 2026-10-24 00:00
as returned by the API. This is sufficient even under the conservative 4
GPU-device-hour allowance for one two-hour T4 ×2 session. Actual quota debit
will be measured after completion, not inferred as a billing rule from hardware.

Cache latest remains private v5 COMPLETE and smoke private v2 COMPLETE. Actual
session-output paths contain all 24 pinned cache files; the small cache inventory
was downloaded and its SHA verified. No model payload was downloaded locally.
Setup dataset contains all seven expected paths and the accepted archive size.
Submission requested `aohkvd/nl2sql-environment-cache/5`; the server's returned
metadata normalizes it to the slug without a version suffix. The driver requires
the exact accepted inventory hash and hashes all mounted cache bytes before
inference, independently of that normalized label.

Kaggle's generic file-list API exposed wrapper names/sizes rather than actual
saved snapshot paths. Preflight therefore used the actual session-output API and
inventory bytes. A numeric `version_label` read returned 404; reading the current
version returned the exact submitted cells. Live-log API currently returns 400;
RUNNING status alone is not used to claim a runtime stage. These read-only API
checks did not submit additional versions or sessions.

The immutable accepted archive, fixed model/encoder revisions, full hashed lock,
Python 3.11.15, original 4-bit/BF16, seed/greedy/token cap, prompts/retrieval and
trust gates remain unchanged. No benchmark-driven tuning, SQL repair/retry or
partial-run merging. Invalid SQL is retained. Runtime failure/timeout stops this
process and requires preserving evidence before any next operational decision.

## Verified result

Exactly one native process completed. Downloaded all 22 saved campaign files
(434,659 bytes), with no omitted campaign artifacts or model payload downloads.
All 21 files covered by the driver's manifest match byte lengths and SHA-256;
the manifest itself is covered by the repository artifact manifest. Native
report self-digest also passes its publisher's compact canonical JSON format.
A first local verifier used the bundle's pretty-JSON format and failed that
self-digest assertion; the corrected independent check passes without changing
any native artifact. Its failed checkpoint is retained separately.

Actual hardware/runtime: Tesla T4 ×2, capability 7.5, Python 3.11.15,
torch 2.5.1+cu124 / CUDA 12.4, unchanged BF16/4-bit backend. All 24 pinned mounted
cache files passed verification; native data/runtime preflights pass. Native
run.json says completed_native_inference with exit 0. No runtime failure/OOM
was observed. Driver completed and removed only owned scratch; mounted inputs
and outputs were preserved. The cumulative ledger contains only
`b12-envi-20261018-c01-b1-en-r01`.

| Observation | Value |
|---|---:|
| Finalized English denominator | 100 |
| Genuine generations | 100 |
| Extraction ok | 0 |
| Unsafe SQL | 99 |
| Invalid SQL | 1 |
| Generation P50 | 25.457s |
| Generation P95 | 49.107s |
| Native process wall time | 2,819.781s (47.00m) |
| Driver wall time, including setup/checks | 3,366.645s (56.11m) |

No SQL was repaired, retried or removed. These are extraction/runtime observations,
not a new SQL execution-accuracy result. P95 fails unchanged B1 <5s acceptance.
The initial 40–60m smoke-based estimate was uncertain: the saved driver took 56.1m,
while submission at 13:29 to observed platform COMPLETE at 14:34 took about 65m,
including platform provisioning/saving. Do not use the smoke median or this one
process as an upper bound for other benchmark runs.

Settled account quota at 14:36:37: used 1.177880833h, remaining 28.822119167h,
reserved 0h. The observed account delta from the pre-launch snapshot is
0.940630556h (56.438m). Live quota estimates were revised on completion; retain
the full status history rather than treating a running estimate as final usage.
This is quota observation, not invoice cost, a universal per-device billing rule,
or authorization of the remaining campaign budget.

## Native review/live flags remain conservative

Native report scientific_ready=false and blockers remain exactly:
`latency_gate_failed`, `live_evidence_missing`, `reviewed_test_set_missing`.
Read-only audit verifies that all 100 loader cases are trusted, reviewed and
live-verified, with exact English snapshot hash
`5d342a5c063ea2d4b5fb7cd62ab15fabb82d2164e5eca5cb248843797989ff0d`.
CLI25 omits manual `--reviewed` / `--live-verified`; CLI17 passes their default
False into evaluate_baseline, which retains those aggregate blockers. There is
no `trusted_test_set_provenance_missing` blocker. No flag, source, report,
threshold or research semantics was changed to bypass a gate. Keep this audit
with the native outputs for later T5.4 authority/adaptation review.

Fresh checks in this execution stage are the actual saved artifact hashes,
report self-digest, 100 genuine completion markers and ordered source-bound
IDs, actual hardware/software, cache/data/runtime gates, single-process ledger,
and owned-scratch cleanup. No pytest suite, model inference or genuine evaluation
was rerun to verify downloaded files. Preparation-suite counts remain historical.

## Handoff and stopping point

First-process runtime/artifact completeness review passes. The remaining eleven
processes have not started and remain outside the original first-process-only
authorization. No replacement version/session or automatic retry was submitted.
Do not select settings from these benchmark outcomes. Preserve the negative
observations, native blockers, original research contract and ledger.

T5.4 canonical adaptation/privacy/cost evidence and separately budgeted BigQuery
execution/comparison remain pending; no BigQuery job or canonical adaptation ran.
B0 0/100 is English-only. No Vietnamese comparison, B3, constrained decoding,
demo or Phase 6–7 change is claimed.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-first-run-2026-10-18.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-first-run-2026-10-18/artifacts-manifest.json).
