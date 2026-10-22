# Private setup-only validation — 2026-10-22

After offline repair `78b6d26`, the user explicitly authorized real validation
then continuing execution. This authorizes one setup-only private session;
if its retained outputs pass validation, fresh quota/cache/duplicate checks
and final B2 VI r03. It does not authorize retrying/replacing B2 EN r03,
changing research settings, another validation attempt or any BigQuery work.

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-setup-validation-20261022-v02

Version 1 submitted at 20:58:15 Asia/Saigon, RUNNING at 21:00:26. Remote
cells/private GPU metadata match; server source confirms inference false.
Diagnostic campaign `b12-setup-20261022-v02`, session `validate-setup-v02` is
separate from the benchmark campaign. The unchanged worker returns after
data/runtime preflight while inference is false; no native campaign ledger,
predictions or completeness receipt should be created. It plans B1 EN r01
only to exercise the same installation/all-model-cache/runtime gates, not
to generate benchmark cases or reserve a benchmark identity.

Driver SHA `7f80915acfb47ce4e2741eb1f60f20487b121390d9cdd2ef43ffe8b1f4e7c5de`,
setup cap 27m and session cap 120m. Exact accepted archive/cache-v5/setup-kit
hashes and full locked Python 3.11.15 installation retained. Model inference
and downloads remain disabled/offline. Requested T4/private metadata is not
proof of actual GPU hardware: runtime preflight deliberately does not probe it.

Fresh quota at 20:58:04: 20.015843333h remaining, 0 reserved, 30h total,
pay-to-scale off; covers a conservative eight GPU-device-hour allowance for
one two-hour validation plus one two-hour final-VI session. Cache private v5
COMPLETE, ten successful notebooks COMPLETE, failed EN r03 still ERROR.
Exact diagnostic ref absent before the single push.

Read-only poll/export and offline verifier helpers are under
`.local/kaggle-b12-setup-validation-20261022-v02/` in this worktree. Poll with
installed Kaggle SDK Python, export only after terminal status, and run
`verify_saved.py` using project Python. Verify every native manifest entry,
source/hash/settings, all 24 pinned cache files, data and package preflight,
stage timing/budget, cleanup and zero inference/native identity reservation.
Actual cache completion, timings and artifact integrity remain pending until
that succeeds. Failed validation stops; no automatic retry or final VI launch.

If validation succeeds, the user-approved continuation exception must be
recorded with final VI: carry all eleven attempted IDs conservatively,
including the failed EN planned ID, keep all evidence and never claim a
successful EN r03 receipt. `PRIOR_COMPLETENESS_REVIEWED` will acknowledge
ten successful runtime reviews plus explicit review/authorization of the
failed setup, rather than fabricate a successful eleventh process. If VI
completes the campaign has eleven successful native processes and one failed
setup slot, not twelve successful compatible replicates.

[Machine checkpoint](../evidence/kaggle-b12-setup-validation-2026-10-22.json)
and [artifact manifest](../evidence/kaggle-b12-setup-validation-2026-10-22/artifacts-manifest.json).

## Monitoring stopped at user request

User asked to stop and will report completion before the next check. The poll
already in flight returned RUNNING at **21:06:09 Asia/Saigon** (14:06:09 UTC),
with 19.88460h account GPU quota remaining. No additional remote check was made
after the request; this is last-known state, not a current completion claim.
No cancellation was requested. The validation continues under its existing
caps; final B2 VI r03 has not been submitted.

On return use the existing local `poll.py --status-only` with installed Kaggle
SDK Python. After terminal status run `export_saved.py`; then run
`verify_saved.py` with project Python from this worktree. Verification source
and disabled/non-submitted final-session draft are retained in evidence as
`validation-verification-source.py` and `final-session-draft.json`. The actual
helper expects its original local directory layout under `.local/`.

If verified setup succeeds, the existing explicit authorization permits next
single B2 VI r03 after fresh launch preflight, without asking again. Preserve
failed B2 EN r03 and carry all eleven IDs conservatively, with the explicit
failure-continuation exception recorded. Do not resubmit validation or retry EN
to resume work. If validation fails, retain all evidence and stop for diagnosis.
