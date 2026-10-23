# CPU notebook admission repair and requested cache retry — 2026-10-23

The user explicitly requested API rechecks or a retry after CPU diagnostic d01
returned ERROR without runtime output. API recheck still showed ERROR, blank
failure_message, zero output files and the persisted log array `[]`. No cache
measurements could be recovered. The source remained private/GPU-off/internet-off.

## Controlled failure exposes the notebook defect

A single private no-input CPU control d02 was submitted with a300s cap, no
GPU/TPU/internet, no cache/model/network/install/benchmark calls. Its exact cell
was exercised locally using a temporary TEST-ONLY output path before submitting.
It prints a start marker, writes started.json, three heartbeat records and a
complete.json marker in3seconds. Notebook format/source validation passed.

API reported d02 ERROR. Unlike d01, it exposed a full Papermill traceback:
`ValueError: No kernel name found in notebook and no override provided.`
This happens during nb_kernel_name, before cell execution. No start marker or
output files exist. The notebook generator omitted metadata.kernelspec.
The same missing field is present in d01; the previously working benchmark16
already declares the python3 kernelspec. This was an avoidable diagnostic
notebook preparation error. Nbformat schema validation and direct execution
of its cell did not catch this Papermill consumer requirement.

The original d01 log remains empty, so the exact d01 platform exception is not
claimed to be directly observed. Its source defect is established separately.
These CPU controls do not reclassify or explain the earlier T4 cache timeouts.

## Real consumer reproduction and metadata-only repair

An isolated temporary uv environment with papermill2.6.0 reproduced the exact
ValueError against the original notebook. No project dependency/lock/SDK or
Kaggle runtime package was installed/changed. Adding only
metadata.kernelspec={display_name:"Python 3",language:"python",name:"python3"}
lets that same Papermill function select python3. The source cells, IDs, code,
GPU/internet/input settings and300s cap remain identical. The fixed no-input
control uses a fresh external ref d03; the failed d02 remains preserved.

Private control d02 v1 kernel140397194:
https://www.kaggle.com/code/aohkvd/nl2sql-cpu-smoke-20261023-d02

Fixed private control d03 v1 kernel140397704:
https://www.kaggle.com/code/aohkvd/nl2sql-cpu-smoke-20261023-d03

D03 COMPLETE observed at20:29:08 Asia/Saigon on2026-10-23. API metadata/source/
kernelspec and no-input/private/GPU-off/internet-off guards match. All3 genuine
saved files (531bytes) downloaded and hashes retained, no omissions. Start/end
log markers and heartbeat steps0/1/2 pass. Actual control Python3.13.15, host
log reaches CPU_SMOKE_COMPLETE around18.146s from worker log origin. The older
cpu-smoke-d02 output subdirectory is intentional: preserving the exact same
cells makes this a metadata-only repair, with a separate fresh Kaggle workspace.

This establishes that CPU notebook execution and saved output persistence work
with the kernelspec repair. It is not model inference, cache verification,
a T4 timing comparison or proof that the original cache slowness is fixed.
The frozen-debugger and old conversion-library syntax warnings did not prevent
completion; they are not the admission failure being repaired.

## One requested CPU cache diagnostic retry

After d03 saved-result verification, a fresh private CPU cache diagnostic d04
was submitted under the user's retry request. Its notebook differs from d01
only by the python3 kernelspec metadata. Every cell and observer-driver byte
remains unchanged; original full-byte/path/size/hash guards, accepted pins,
cache-v5 inventory and setup fingerprints remain fixed. Native notebook/driver
sources used for benchmarking are untouched. No T4/EN retry is launched.

Private d04 v1 kernel140398078:
https://www.kaggle.com/code/aohkvd/nl2sql-cache-diag-20261023-d04

RUNNING observed at20:30:56 Asia/Saigon on2026-10-23. Remote source, kernelspec,
private/GPU-off/TPU-off/internet-off and setup/cache source metadata verified.
Fresh quota/state gates passed: earlier benchmark failures remain ERROR,
finalVI/cache COMPLETE, d01 ERROR and fixed d03 COMPLETE. CPU execution requests
no GPU, pay-to-scale remains off, GPU reserved hours0. Parent verification
watchdog1,620s/27m, platform cap1,800s/30m;10s heartbeats and all original checks
remain. The historical cache-diagnostic-d01 output prefix is intentional,
allowing exact cells to be preserved under a fresh independent workspace.

Per-file/cache measurements remain pending. CPU/Python3.13 control and default
diagnostic runtime differ from pinned T4/Python3.11.15 inference runtime; a CPU
cache pass would not by itself establish a T4 repair. Neither CPU controls nor
d04 reserve a native benchmark ID. The original13 attempted benchmark IDs,
11successful native runs and2setup failures remain intact. No new BigQuery,
training, inference, research setting/cap change or SQL repair occurred.

Local artifacts/helpers are in `.local/kaggle-cpu-smoke-20261023-d02/`, d03 and
`.local/kaggle-cache-diagnostic-20261023-d04/`. Use installed SDK Python to poll
this existing d04 ref, then export_saved.py only after terminal state. Use project
Python for verify_saved.py; it expects the preserved cache-diagnostic-d01 saved
subdirectory. Prepared verifier is not a completed review. Monitoring stops at
this launch checkpoint; no further retry or benchmark launch is automatic.

[Failed control evidence](../evidence/kaggle-cpu-smoke-2026-10-23-d02.json),
[verified repaired control](../evidence/kaggle-cpu-smoke-2026-10-23-d03.json),
[CPU cache retry checkpoint](../evidence/kaggle-cache-diagnostic-2026-10-23-d04.json).

Final handoff poll at20:33:52 Asia/Saigon still RUNNING; remote v1 source/
python3 kernelspec/private CPU/no-internet checks pass. No terminal cache
receipt or per-file artifact review claimed.
