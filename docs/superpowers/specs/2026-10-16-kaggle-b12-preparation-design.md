# Offline Kaggle B1/B2 preparation

Authorized scope: prepare a reviewable runner and deterministic input bundle,
native execution, without downloads, credentials, model/encoder/GPU execution,
BigQuery, upload, push, merge or PR. Continue the user's existing instruction to
present a short design and execute routine steps without repeated approvals.
Base: `ededf48`, containing the locally finalized Vietnamese benchmark.

Keep all accepted data, baseline/prompt/retrieval/linker code, model identities,
research contract, thresholds and existing accuracy tests unchanged. Reuse CLI17
for English inference. Its `nl` loader does not accept paired Vietnamese rows;
package/validate VI as immutable evidence but explicitly block VI execution.
A typed VI consumer is a separate task, not a field-rename workaround.

Deliver explicit file allowlist, SHA-256/size manifest, byte-reproducible tar.gz,
source-content fingerprint, local verification and data-only preflight through
actual B2/English/paired validators. The full canonical corpus is included only
as the B2 adapter's required provenance source; retrieval input is exclusively
the 7,208-row export. No secrets, .git, caches, fixtures, model files or arbitrary
repository glob enters the bundle. Reject symlinks, traversal and unexpected files.

The run-config template leaves unavailable model/encoder revisions, HF cache
location and campaign identity unresolved. Never invent pins or acceptance.
Runtime preflight checks exact dependency versions from uv.lock, Python 3.11,
pinned 40-hex revisions, local model/tokenizer/encoder snapshot files and safe
writable outputs before loading any ML stack. Actual run additionally requires
--real-inference and a T4 hardware check; all HF loaders stay offline/local-only.
Plan three compatible independent process runs per baseline, seed 42 and the
existing greedy/4-bit/batch-one configuration. Persist hardware, package versions,
exact config/bundle hashes, native stdout/stderr, status and native prediction/
log/report. Never overwrite run directories, fabricate execution accuracy or
upgrade native/scientific readiness. Preserve errors and stop on failure.

Provide a Kaggle notebook with real execution disabled by default, explicit
archive SHA check, safe unpack, data/runtime preflight and the run command.
User-side provisioning, dependencies/model snapshots and quota remain external.
No operational claim that GPU/model compatibility has been tested locally.
