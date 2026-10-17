# Kaggle T4 smoke — 2026-10-17

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-b12-t4-smoke-20261017-r01

Version 1 was submitted through the authenticated Kaggle CLI with an explicit
2,700-second session cap and T4 accelerator. At the latest saved API checkpoint,
Kaggle reports `QUEUED`; no actual hardware, model load, inference or latency
result is established. A requested accelerator is not proof of allocated hardware.
Do not submit another run merely because this one is queued.

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
[submitted source](../evidence/kaggle-t4-smoke-2026-10-17/submitted-v1.ipynb).
Continue by inspecting this same notebook's status and logs. Preserve genuine
failures; do not change dtype, prompt, model or quantization silently. Genuine
B1/B2 benchmark runs remain gated on the smoke outcome and current quota.
