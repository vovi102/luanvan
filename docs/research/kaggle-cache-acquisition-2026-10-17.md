# Kaggle environment and model-cache acquisition — 2026-10-17

Private notebook: https://www.kaggle.com/code/aohkvd/nl2sql-environment-cache

The verified notebook version is **5**; select it through Kaggle's Versions list.

**Result:** Kaggle reports `COMPLETE`. The private saved output exposes all
**24 pinned cache files, 16,161,347,681 bytes**. Every file passed its expected
SHA-256 or Git blob SHA-1 twice on Kaggle, including after materializing snapshot
symlinks as regular files. Metadata-only streamed GET response headers for all
24 saved files independently match their pinned lengths. No response bodies for
model weights were read or saved locally. Only small JSON evidence and logs were
downloaded. No model/encoder was instantiated; no inference, training, GPU probe
or BigQuery job ran. Cache availability does not establish GPU compatibility.

| Component | Revision | Files | Payload bytes |
|---|---|---:|---:|
| `meta-llama/Meta-Llama-3-8B-Instruct` | `8afb486c1db24fe5011ec46dfbe5b5dccdb575c2` | 13 | 16,069,769,266 |
| `sentence-transformers/all-MiniLM-L6-v2` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | 11 | 91,578,415 |

## Environment and operational history

The user confirmed Hugging Face approval and created Kaggle secret `HF_TOKEN`.
The existing CLI login was used internally, without manually opening credentials.
Private input dataset `aohkvd/nl2sql-setup-inputs` contains seven allowlisted setup
files, including `input-bundle.bundle`: this is the accepted tar.gz archive with
only its filename changed, preserving SHA-256
`2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de`.
A download round trip verified all seven uploaded files byte for byte.

- Version 1 genuinely installed Python **3.11.15** and the full **218-package**
  pinned environment, then verified the public encoder. Its execution log is
  preserved; completion of that version's output saving was not established.
- Version 2, launched through the API, failed the early secret preflight. The
  [upstream secret-attachment limitation](https://github.com/Kaggle/kaggle-cli/issues/582)
  prevents treating an API push as proof that a saved run can use the UI secret.
- Version 3, launched by the user through the UI, successfully accessed the secret
  and installed the full environment, but stopped before model acquisition: only
  **20,897,562,624 bytes** were initially free, insufficient for full dependencies
  plus the model/cache and download margin.
- Version 4 was a **Quick Save**, without execution, of the space-safe source.
  It selects the unchanged lock's dependency closure for `huggingface-hub` and
  `click`: 15 requirements including a Windows-only marker, 14 applicable Linux
  packages. The subset SHA-256 is
  `9e619d93825589352748ab8379be6b5e28476b08392eccc8fd4ecf46a6018aa0`.
  A genuine local isolated hashed install occupied about 20.4 MiB of packages.
  Three synthetic checks verified shared-blob materialization, same-size
  corruption rejection, and rejection of an escaping snapshot symlink.
- Version 5 was launched by the user with **Save & Run All** and the secret
  attached. It used CPU and Internet, downloaded the original pinned files,
  verified them, replaced cache symlinks with hardlinks without duplicating
  payloads, removed redundant blob names, re-verified all hashes, and removed
  temporary installation directories. It saved regular cache snapshot files
  directly, avoiding a second 16 GB archive. Only read-only API operations were
  used after the user's launch; no further notebook push occurred.

The full research environment installation is verified separately; **it is not
retained in version 5's cache output**. Python/torch/GPU/model-load compatibility
has not been checked. The original notebook 15 and its original setup archive
remain historical preparation artifacts; use the executed version 5 source for
this 20 GB cache-acquisition workflow. Do not rerun the full-install-plus-archive
workflow on a 20 GB working disk.

## Reuse and next stage

Attach the **private output of version 5** as input to the next notebook. Inspect
its actual mounted path; do not guess a `/kaggle/input` slug. Use the mounted
`hf-home/` directly as a read-only offline cache and provision the full pinned
Python 3.11.15 runtime separately in `/kaggle/working`. Copying 16 GB of weights
back beside the full runtime recreates the disk problem.

The saved EN/VI configs retain the exact model/encoder revisions. Their
`campaign_id` and `run_timeout_seconds` intentionally remain null. Update the
runtime's cache location from the actual mount outside immutable inputs; do not
change baseline prompts, retrieval corpus, quantization or accepted evidence.
The next stage is an explicitly authorized, non-test T4 smoke with fresh GPU
quota/runtime checks. Genuine B1/B2 runs, T5.4 and T5.5 remain unexecuted.

## Evidence

[Machine checkpoint](../evidence/kaggle-cache-acquisition-2026-10-17.json),
[artifact manifest](../evidence/kaggle-cache-acquisition-2026-10-17/artifacts-manifest.json),
[executed version 5 source](../evidence/kaggle-cache-acquisition-2026-10-17/executed-v5.ipynb),
[saved output accessibility](../evidence/kaggle-cache-acquisition-2026-10-17/saved-output-accessibility.json),
[downloaded cache inventory](../evidence/kaggle-cache-acquisition-2026-10-17/b12-cache-inventory.json).
The folder also retains earlier failures and the successful worker log; no token
values, signed download URLs or weights are included. No historical full-suite
count is presented as a fresh test run. Research sources, accepted data and the
original bilingual bundle were not changed.
