# B2 EN r03 full replacement — 2026-10-23

The user explicitly approved preparing and executing one full 100-case B2 EN
r03 replacement under a new identity, preserving the failed setup attempt.
This supersedes the earlier no-EN-retry scope for this one process only.
Original eleven native successes and the failed setup remain retained unchanged.

Execution campaign `b12-envi-20261018-c01-replacement01`, native run
`b12-envi-20261018-c01-replacement01-b2-en-r03`, session
`s11-b2-en-r03-replacement01`. Parent campaign `b12-envi-20261018-c01`;
replacement_of `b12-envi-20261018-c01-b2-en-r03`.
The replacement marker precedes the native suffix so the accepted native
runner can generate the new ID without modifications. This supersedes only
the suffix placement in the initial proposal, not its full-process scope.

The operational driver, outside the immutable bundle, accepts an optional
`replacement_of` setting. It defaults to None; all three execution opt-ins
remain False in notebook16. Replacement requires B2 EN r03, distinct
`<parent>-replacement01` namespace, all twelve original attempted IDs without
duplicates/reuse, and explicit prior runtime/artifact review. These checks run
before preparation writes and again in the worker. The native ledger records
parent campaign, failed ID, twelve prior attempts and the new thirteenth ID
before invoking the unchanged native runner. The parent setup failure is not
represented as a successful native completeness receipt.

Only the new campaign identity and its output paths differ. Model/encoder
revisions, seed42/greedy/batch1/512 tokens, BF16/4-bit, original prompts,
normalization, retrieval, 7,208 accepted training rows, all 100 EN cases,
scientific thresholds and native review/live flags remain fixed. Setup27m,
native90m, worker91m, cleanup2m and platform session120m remain fixed.
No SQL repair, partial-run splice, new BigQuery, training, B3 or adaptation.

Offline verification checks the exact accepted archive and 181 payload files,
byte-identical accepted source/scripts/configs, data preflight, normalized
native argv and config (campaign_id only), notebook schema/default guards,
embedded source hash and twelve unchanged operational function ASTs. Nine
new operational test cases cover distinct identity/config/argv, invalid or
unreviewed replacement requests before writes, and retained worker lineage
before the native invocation. External inference/runtime boundaries are
stubbed only in that worker unit test; its files are test-only, not genuine
model provenance or campaign evidence.

A successful replacement would yield twelve genuine full native processes
across the parent and replacement namespaces, plus the original failed setup
(thirteen attempted IDs). Each language/run retains its own N=100; no pooling.
Native scientific readiness remains separately gated; this task does not
resolve original latency, aggregate live/review or T5.4 blockers.

## Resume this one session

Local deployment, single-push helper, read-only poll/export and terminal offline
verifier are in `.local/kaggle-b12-benchmark-20261023-b2-en-r03-replacement01/`.
Use installed Kaggle SDK Python for `poll.py --status-only` and, after terminal
state only, `export_saved.py`. Use project Python with `PYTHONPATH=src` for
`verify_saved.py`. Verify all saved manifest/report hashes, 100 genuine ordered
EN cases and source authority, 7,208×384 train-only cache and all500 selected
examples, actual hardware/runtime/caps/timings/cleanup and13-ID parent lineage.
Preserve failure and stop on any timeout; no automatic second replacement.
A prepared verifier is not a completed saved-artifact review.

Offline checks passed:28 focused tests in16.79s; full suite1,602 passed,342
warnings in758.87s; Ruff check/format, notebook schema/defaults/source hash,
accepted bundle/source/data/argv/config and retained lineage checks passed.
Original two new provenance tests failed before implementation; non-string
validation test also failed before its fix. No genuine inference ran locally.
