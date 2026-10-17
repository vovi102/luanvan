# Kaggle environment/cache handoff — 2026-10-17

Target supplied by the user:
https://www.kaggle.com/code/aohkvd/nl2sql-b1-b2-2026-09-22-r01

The user confirmed **Llama access has not yet been requested**. Do not substitute
another model or an unofficial mirror. Request access at the official
[model page](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct).
The user's notebook was not accessible through unauthenticated web inspection;
its contents, current runtime, privacy setting, quota and outputs are unverified.
No authenticated Kaggle/Hugging Face account access, upload or notebook execution happened here.

## What is ready locally

- [CPU setup notebook](../../notebooks/15_kaggle_environment_cache.ipynb): separate
  from inference notebook 14. All unpack/install/download/secret flags default
  False. It never invokes model/encoder load, GPU, inference, training or BigQuery.
- [Pinned file inventory](../../configs/kaggle-b12-model-pins.json): exact public
  repository revisions and per-file size plus LFS SHA-256 or Git blob SHA-1.
  Metadata was fetched anonymously with HTTP environment/auth lookup disabled.
- [Cache helper](../../scripts/26_kaggle_environment.py): explicit acquisition
  opt-in and offline byte verification; local 8B acquisition is refused before
  token reads/imports. Public encoder uses `token=False`, requests trust_env=False,
  and no login. Gated model accepts a token only through stdin on Kaggle after
  explicit user opt-in. Raw authenticated download errors are not printed.
- Runtime requirements exported **offline/frozen**, twice byte-identical, from
  the unchanged uv.lock, with exact versions, environment markers and hashes.
  The project itself is excluded; native code comes from the sealed input bundle.
  uv 0.11.14 bootstrap wheels have separate PyPI-published hashes. The notebook
  provisions Python **3.11.15** into `/kaggle/working/b12-runtime`; it does not
  replace the hosted notebook kernel or mutate the immutable input directory.
- Genuine public MiniLM cache: 11 files, **91,578,415 bytes**, downloaded and
  checked against source digests. No encoder was instantiated. Download guard
  observed **zero credential reads and zero model imports**. Hash verification
  also passed after extraction of the portable cache archive.

| Component | Exact revision | Selected files | Bytes | Current state |
|---|---|---:|---:|---|
| `meta-llama/Meta-Llama-3-8B-Instruct` | `8afb486c1db24fe5011ec46dfbe5b5dccdb575c2` | 13 | 16,069,769,266 | Metadata pinned; no weights downloaded; user access not requested |
| `sentence-transformers/all-MiniLM-L6-v2` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | 11 | 91,578,415 | Genuine cache bytes verified locally; no encoder load |

Only the Hugging Face Transformers safetensors variant is selected for Llama;
no duplicate `original/` weights. MiniLM excludes PyTorch/TF/ONNX/OpenVINO duplicate
formats and training scripts. All model/cache choices preserve baseline identity.

## Local delivery artifacts

Paths are relative to `.worktrees/b12-bilingual-consumer` (current branch is
`feat/kaggle-environment-cache`, based on `d7f7465`; the predecessor branch remains
at its original commit).

| Artifact | Path | SHA-256 |
|---|---|---|
| Setup kit | `.local/kaggle-environment-2026-10-17/release/setup-kit.tar.gz` | `95fd031a840e1dbe61d347ea09976d8fd0b42576dadbbc9f2a371cd1c06aeea5` |
| Portable public encoder cache | `.local/kaggle-environment-2026-10-17/release/encoder-cache.tar.gz` | `7b8173bbb7fa1af17fe07b42fb42c8d843559c349b773af14c7ae5ba719a0a0e` |
| Existing bilingual inference input | `.local/kaggle-b12-bilingual/release/input-bundle.tar.gz` | `2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de` |

Both new archives have two byte-identical builds with fixed archive metadata.
Their manifests, safe extraction and extracted encoder hash verification were
checked. Cache links are materialized as regular files in the portable archive;
it contains only the eleven pinned snapshot files plus its manifest, no tokens,
ambient caches, benchmarks or credentials. The setup archive is 51,289 bytes;
encoder archive is 83,467,922 bytes. These ignored local artifacts are not uploads.
The setup kit supplements the accepted inference bundle; **it does not replace
or rebuild that bundle**. Notebook 14, baseline code/config, accepted datasets,
review events, previous bundles/evidence and uv.lock remain unchanged.

## User-only access steps

The wizard skill supplies a local browser walkthrough. It has not been executed
end to end, does not collect tokens, and is ephemeral rather than committed:

```bash
cd /home/khoavd/WORKSPACE/LuanVan/.worktrees/b12-bilingual-consumer
bash .local/kaggle-environment-2026-10-17/setup-kaggle-access.sh
```

It opens the model request page, then the existing Kaggle notebook, and guides
Kaggle Secrets only after the user reports approval. Only non-secret access
status and the setup notebook URL are written to the ignored
`.local/kaggle-environment-2026-10-17/setup-public.env`. Script syntax passed
`bash -n`; shellcheck was unavailable. No token is requested in chat or locally.

The browser stages are:

1. Log into Hugging Face, review the actual access conditions and submit the model
   access request yourself. Approval timing is controlled by the publisher.
2. Preserve the existing Kaggle notebook/version; use a **private CPU setup copy**
   with Internet on and Accelerator None. Import notebook 15 there. Attach private
   inputs containing the unpacked setup kit and the unchanged bilingual archive.
   Fill `KIT_ROOT` and `BUNDLE_ARCHIVE` from the actual mounted paths. Verify the
   archive SHA independently against this handoff. Do not guess a dataset slug.
3. Enable `ALLOW_INPUT_UNPACK` and `ALLOW_ENV_INSTALL` explicitly in that setup
   copy. Run the checks and environment cells. Save installation logs, Python
   version and notebook URL/version. Dependency installation on Kaggle has **not**
   been tested locally; failure stays blocked, with no silent version upgrades.
4. For public encoder, either enable cache download with `CACHE_COMPONENT="encoder"`
   or copy the verified portable `hf-home/` into `/kaggle/working/hf-home` after
   verifying/extracting its archive. Verify those bytes using the command below.
5. **After Hugging Face approval**, create a read token with access to that model.
   Enter it directly into Kaggle **Add-ons → Secrets**, label `HF_TOKEN`, granting
   only the private setup notebook access. Do not put it in cells, environment
   variables, local env files, screenshots or chat. Set `CACHE_COMPONENT="model"`
   (or `"all"`) and explicitly enable download + secret access in notebook 15.
   The runtime child receives it through stdin, never argv or logged output.
   No `hf auth login` or persistent token file is used.
6. Verify all pinned bytes and preserve the result. The notebook generates EN/VI
   config files outside immutable inputs with genuine revisions and HF_HOME.
   Campaign and wall-time cap intentionally remain null; filling them belongs to
   the next authorized smoke/run preparation. This does not grant inference opt-in.

Verify a mounted/copied encoder without loading it:

```bash
/kaggle/working/b12-runtime/bin/python <KIT_ROOT>/scripts/26_kaggle_environment.py verify-cache \
  --pins <KIT_ROOT>/configs/kaggle-b12-model-pins.json \
  --hf-home /kaggle/working/hf-home --component encoder
```

Replace `<KIT_ROOT>` with the actual setup dataset path. Once Llama is acquired,
use `--component all`. `cache_bytes_verified` only verifies file contents; it is
not a model-load, GPU/OOM, BF16/4-bit compatibility or scientific readiness result.

Keep all CLI17/CLI25 calls on the isolated Python 3.11 interpreter, even if the
host notebook kernel differs. For later native execution, use
`/kaggle/working/b12-runtime/bin/python .../scripts/25_kaggle_b12.py`, not an
unchecked kernel `sys.executable`. The original backend's BF16/4-bit behavior
remains unchanged and awaits genuine T4 smoke; do not change it in this setup.
No current GPU quota is claimed. Setup can run on CPU; genuine smoke/runs still
require the approved T4 and fresh actual quota/runtime checks.

## Evidence and remaining gate

[Machine evidence](../evidence/kaggle-environment-cache-2026-10-17.json) and
[logs/manifests](../evidence/kaggle-environment-cache-2026-10-17/).
Focused verification: **39 passed in 27.33s** (ten new setup tests plus existing
Kaggle tests). RED logs preserve the missing consumer/notebook and a stale embedded
source fingerprint before its correction. Tests cover explicit opt-in, missing/
wrong-size/same-size-tampered/escaping cache paths, local gated-model refusal,
synthetic byte fixtures retaining scientific_ready=False, and execution of all
notebook code cells under disabled flags with external operations forbidden.
The actual notebook was not executed on Kaggle or used for inference.

Fresh full suite: **1,574 passed, 342 warnings in 761.95s (12:41)**, exit 0,
using `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest -q`.
No historical test count is reused as a fresh result. All accepted input hashes and protected baseline
sources are checked unchanged at handoff.

The concrete external blockers are the user's pending model-access request,
private Kaggle setup/upload/session execution, actual dependency installation,
then full model-cache acquisition and byte verification. Next sequence remains:
environment/cache **actually verified on Kaggle** → non-test T4 GPU smoke → three
genuine processes per (baseline, language), twelve total → T5.4 → T5.5.

## Primary references checked for this setup

- [Hugging Face gated access](https://huggingface.co/docs/hub/models-gated)
- [Pinned model metadata](https://huggingface.co/api/models/meta-llama/Meta-Llama-3-8B-Instruct/revision/8afb486c1db24fe5011ec46dfbe5b5dccdb575c2?blobs=true)
- [Pinned encoder metadata](https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2/revision/1110a243fdf4706b3f48f1d95db1a4f5529b4d41?blobs=true)
- [HF Hub 0.36 acquisition source](https://github.com/huggingface/huggingface_hub/blob/v0.36.0/src/huggingface_hub/_snapshot_download.py)
- [Kaggle Secrets official CLI documentation](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md#using-secrets-in-kernels)
- [Kaggle notebook environment](https://www.kaggle.com/docs/notebooks)
- [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/)
- [uv 0.11.14 bootstrap metadata](https://pypi.org/pypi/uv/0.11.14/json)

Author self-review completed against setup scope, byte/source integrity, credential
boundaries, default-disabled notebook behavior and unchanged baseline sources.
No subagent/independent review is claimed.
