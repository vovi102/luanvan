# First genuine B1 EN benchmark — 2026-10-18

The user explicitly authorized private upload and **only the first full B1 EN
r01 process**, N=100, after a fresh quota check. Native cap 5,400s; platform session
cap 7,200s. This does not authorize the remaining eleven processes, the proposed
27-hour campaign budget, automatic replacement runs, BigQuery, training, B3 or
changes to research semantics.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261018-b1-en-r01

**Submitted version 1; latest checkpoint RUNNING.** This is not evidence of
completed inference, actual hardware, full artifacts or scientific acceptance.

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

After saved output becomes available, verify driver/native logs and hashes,
actual hardware/runtime, cache/data/runtime preflights, run.json status, ordered
100 prediction/log IDs and the completeness receipt. Do not choose configuration
based on test accuracy. T5.4 canonical adaptation/privacy/cost evidence and
separate BigQuery authorization remain pending; B0 0/100 is English-only.

[Machine checkpoint](../evidence/kaggle-b12-benchmark-first-run-2026-10-18.json)
and [artifact manifest](../evidence/kaggle-b12-benchmark-first-run-2026-10-18/artifacts-manifest.json).
