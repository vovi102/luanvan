# Kaggle T4 smoke — 2026-10-17

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-t4-smoke-20261017-r01

**Result (2026-10-18): version 2 is `COMPLETE`; compatibility smoke passed.**
All ten unchanged CLI17 processes completed with genuine production-backend
markers, on **Tesla T4 ×2**, compute capability 7.5, Python 3.11.15,
torch 2.5.1+cu124 and CUDA 12.4. Model and encoder loaded successfully with
the original 4-bit/BF16 settings. No OOM was observed. The driver completed in
818.93 seconds under its unchanged 2,700-second session cap.

| Non-test observation | B1 | B2 |
|---|---:|---:|
| Genuine native processes completed | 5 | 5 |
| Generation median, seconds | 20.95 | 20.01 |
| Generation maximum, seconds | 28.47 | 20.49 |
| Extraction status | 5 `unsafe_sql` | 5 `ok` |

These are five fixed training questions, not a benchmark or an accuracy
estimate. `ok` means native extraction/safety passed, not semantic correctness.
Both smoke generation medians exceed the existing B1 <5s and B2 <8s targets;
those acceptance gates remain open. Genuine EN/VI benchmark campaigns, execution
accuracy and scientific completion remain unperformed. Prompts, retrieval,
model settings and thresholds were not adjusted in response to these outputs.

The post-run quota snapshot reports 0.24h GPU used and 29.76h remaining;
recheck it before any further campaign. Only 47 small JSON/log/source files were
downloaded. The embedding NPZ and its lock were omitted; no weights were
downloaded locally. All 38 downloaded files named by the worker artifact
manifest match its sizes/SHA-256; that manifest, driver evidence and submitted
sources are covered by the repository artifact manifest.

Version 1 failed at `input_discovery`, before installation or model loading.
The notebook incorrectly expected 181 tar members; the immutable accepted
archive has 181 payload files plus `kaggle-bundle.json`, totaling **182**.
Its SHA-256 remains unchanged. Version 2 changes only that expected count. Its actual Kaggle log subsequently
reached `install_bootstrap`, `create_python311`, then `install_locked_environment`,
confirming the original archive guard is passed remotely as well.
The original submitted source and genuine failure logs remain preserved.

A local regression executed the exact archive-extraction block from version 1
against the accepted archive and reproduced the genuine error. The exact
corrected block then extracted all 182 files; native CLI25 data preflight passed
for EN/VI with 7,208 accepted training records. No model libraries, inference,
network or credentials were needed for this regression. Duplicate, traversal,
member-type, size and archive-hash guards remain unchanged.

The notebook mounts `aohkvd/nl2sql-setup-inputs` and the private output of
`aohkvd/nl2sql-environment-cache`. Cache version 5 was checked as `COMPLETE`
immediately before submission. It discovers the actual mounted path, verifies
all pinned cache bytes, and uses the cache in place under `/kaggle/input`.
It installs the unchanged full hashed lock in a separate Python 3.11.15 runtime
under `/kaggle/working`. HF credentials are neither requested nor needed.

The probe selects five questions from the accepted 7,208-row training export in
fixed file order: EN/VI/EN/VI/EN, distinct semantic families. Selection occurs
before generation; benchmark questions and gold do not guide it. Each question
runs through unchanged CLI17 `predict` for B1 and B2, with the training ID passed
to B2 for family exclusion. There are ten planned native processes, at most
300 seconds each and 1,800 seconds for the smoke loop. The first runtime failure
stops the probe. Invalid SQL extraction remains an observed diagnostic.

Model revision, encoder revision, seed, greedy generation, 512-token cap,
batch one, 4-bit quantization and the backend's BF16 behavior remain unchanged.
Actual hardware, dependency inventory, native stdout/stderr and per-case timing
are retained if execution reaches those stages. Temporary installed environments
and extracted inputs are removed in the driver's final cleanup; mounted inputs
are never modified. No benchmark evaluation, BigQuery job or training is included.

Local validation compiled both notebook cells and the worker, executed the
default-disabled notebook without installations or inference, and verified five
fixed cases against the exact accepted training hash. This validates preparation,
not T4 compatibility. The submitted source has the explicit smoke opt-in enabled;
the preserved preparation source defaults to disabled.

[Machine checkpoint](../evidence/kaggle-t4-smoke-2026-10-17.json),
[artifact manifest](../evidence/kaggle-t4-smoke-2026-10-17/artifacts-manifest.json),
[submitted version 2](../evidence/kaggle-t4-smoke-2026-10-17/submitted-v2.ipynb),
[failed version 1](../evidence/kaggle-t4-smoke-2026-10-17/submitted-v1.ipynb).
[Saved smoke summary](../evidence/kaggle-t4-smoke-2026-10-17/saved-v2/b12-smoke-results/smoke-summary.json),
[actual hardware](../evidence/kaggle-t4-smoke-2026-10-17/saved-v2/b12-smoke-results/hardware.json).
Next, plan the genuine EN/VI campaign with explicit process/session caps and
fresh quota. Preserve the negative observations and unchanged research settings;
keep three processes per (baseline, language), N=100 per language, and no pooling.
No new BigQuery execution is authorized or implied by this smoke.
