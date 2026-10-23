# B2 English r03 — 2026-10-21

User explicitly requested next process. Existing B1 VI r03 completed and passed
full artifact/runtime review at `84b0f2a`. Submitted only next scheduled B2 EN
r03, full N=100, unchanged 5,400s native / 7,200s session caps. No full-campaign
budget inferred; this replicate does not replace previous runs.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-benchmark-20261021-b2-en-r03

**Version 1 ERROR; setup-timeout evidence verified on 2026-10-22.**
Submitted at 23:26:48 Asia/Saigon on 2026-10-21. ERROR observed at
19:18:04 on 2026-10-22; exact platform failure time was not observed.
Remote cells match submitted source; private/GPU/NvidiaTeslaT4 and accepted
dataset/cache metadata verified. Saved evidence establishes setup failed before native inference. Actual GPU
hardware/runtime and successful cache verification remain unverified. Queue/provisioning adds elapsed time
outside measured native/driver wall time.

Campaign `b12-envi-20261018-c01`, session `s11-b2-en-r03`, run
`b12-envi-20261018-c01-b2-en-r03`. Ten prior IDs match retained B1 VI r03
ledger: all r01/r02 runs, B1 EN r03, B1 VI r03. All prior reviews pass.
Ten native processes complete, this eleventh session failed during setup,
final B2 VI r03 unstarted. Keep all prior
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

## Failed setup audit — 2026-10-22

Retained all seven saved campaign files (11,712 bytes), no omissions/model
payload downloads. All six native manifest entries match size/SHA-256;
repository manifest covers the native manifest and failure audit. Driver summary
is `failed`, stage `verify_mounted_cache`, error type `TimeoutExpired`, wall
1,200.003s. Stage timeout was 615.233s: the cumulative 1,200s setup budget was
consumed across prior installation stages and mounted-cache verification.
The full locked environment installation completed; its log reports preparing
218 packages in 7m46s and installing them in 14.08s. Owned scratch was removed.

Cache verifier reads and hashes pinned mounted model/encoder bytes and only
prints a result after completing all files. Its retained log is empty, with no
cache mismatch error or successful receipt. The direct failure is setup-budget
exhaustion while verification was running. Underlying verification slowness is
undetermined: per-file timings were not emitted. Do not claim cache corruption,
a specific I/O/network bottleneck, OOM or a model/SQL defect from these artifacts.
The driver and submitted settings/pins are unchanged from reviewed successful
sessions; no fix or runtime change was attempted.

The driver invokes the native runner only after cache verification. That stage
was never reached: no `runs/`, native `run.json`, predictions, native log/report,
completeness receipt, data/runtime preflight or native campaign ledger exists
in this saved session. **Zero native cases generated; no B2 EN r03 result.**
This is not 0/100 accuracy or an additional completed replicate. Input provenance
was retained and binds the exact accepted bundle/cache inventory. Actual
hardware/runtime and cache integrity could not be independently established.

The last published native ledger remains the ten-ID B1 VI r03 ledger. A separate
`campaign-attempt-audit.json` records this failed setup/session/planned ID and
requires preserving its ID conservatively in any later continuation. This audit
is not a fabricated native ledger/completeness receipt. Never reuse or hide the
failed session/ID, splice outputs or label it complete.

Quota on return: 20.015843333h remaining, 0h reserved; observed account usage
delta from pre-launch snapshot 0.338103889h. Account quota observation is not
invoice cost or a general billing rule. Campaign: **10 complete native
processes, one setup failure, one unstarted slot**. Scientific readiness stays
false; no SQL execution accuracy, BigQuery, adaptation, training, retry or new
process is claimed.

## Concrete next-session proposal, awaiting decision

User requested continuing processes. The precommitted campaign states that
runtime failures/timeouts stop the session and no later process starts
automatically, and `PRIOR_COMPLETENESS_REVIEWED=True` requires a successful
100-native-case receipt. The failed EN session cannot satisfy that condition.
Therefore an explicit operational decision is pending before continuation;
source defaults/caps/flags have not been changed and nothing new was uploaded.

`proposed-next-session.json` prepares a single final B2 VI r03 session,
`s12-b2-vi-r03`, N=100, private/T4, all original caps/settings/driver retained,
all execution opt-ins false and prior completeness flag false. Proposed
exception: proceed to final VI after reviewing this failure, preserve EN r03
as failed setup, carry all eleven IDs conservatively, and do not retry EN.
If VI succeeds the campaign would have eleven complete native processes and
one failed setup slot, not twelve complete compatible replicates. Any EN
replacement would require a separately approved full-process identity and
protocol update; none is authorized or prepared here.

The user was asked to choose between unchanged final VI continuation with EN
failure retained, or stopping to address setup first. No answer is inferred
from elapsed time. Full failure evidence, read-only verification source/result,
account checkpoint and disabled proposal are retained under the linked evidence
directory. Fresh verification covered all original bytes, manifest, failure
stage/budget, absence of native outputs and cleanup. No local inference/pytest
suite reran. T5.4 and separate BigQuery authorization remain pending.

## User decision — address setup first

User selected “Dừng để xử lý lỗi setup trước”. The disabled final-VI proposal
above is not approved; B2 VI r03 remains unstarted. No new remote session or
runtime change has occurred. See the [offline comparative diagnosis and bounded
repair candidate](kaggle-b12-setup-diagnosis-2026-10-22.md), based on all eleven
saved sessions. Proposed setup allowance 27m plus unchanged 91m maximum worker
and 2m cleanup fits the original 120m session cap; the 90m native cap and all
hash/research gates remain intact. This design is pending approval, not a fix
or real validation claim. Original failed session/ID/evidence remains immutable.
