# Kaggle B1/B2 runner and bundle

The runner supports the unchanged B1/B2 research definitions for **one explicit
language per config**, `en` or `vi`. English retains its finalized `nl` trusted
loader. Vietnamese goes through a typed paired-snapshot authority that checks
accepted source hashes, reconstructs all human acceptance events, validates the
complete final manifest and exact reused English live evidence, and retains the
original `PairedFinalCase` and source digests in native artifacts. No new BigQuery
execution is implied. The user bulk ACCEPT provenance (5/5/5/1) is preserved.

This bilingual bundle supersedes the English-only preparation bundle operationally;
its archive hash is recorded in
[the bilingual handoff](../research/b12-bilingual-consumer-2026-10-16.md).
The old archive/evidence and unsuccessful audits remain historical records.

## Build and validate locally without models

From the repository worktree, use Python 3.11 with the project's dependencies:

```bash
PYTHONPATH=src python scripts/25_kaggle_b12.py bundle \
  --output .local/kaggle-b12-bilingual/release/input-bundle.tar.gz
PYTHONPATH=src python scripts/25_kaggle_b12.py unpack \
  --archive .local/kaggle-b12-bilingual/release/input-bundle.tar.gz \
  --sha256 <exact-archive-sha256-from-build> \
  --output /tmp/b12-input
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py preflight \
  --root /tmp/b12-input --level data
```

The archive SHA-256 is printed by `bundle`; record it independently and copy it
into the notebook. Archive timestamps, ownership and gzip header are fixed.
`configs/kaggle-b12-inputs.json` explicitly lists accepted data hashes and source
paths. Every packaged file has a size/digest/role in `kaggle-bundle.json`.
No model files, credentials, .git, caches, tests/fixtures or arbitrary repository
files are included. Build/extract refuse aliases, traversal and overwrites.
Do not put new files or configs inside the immutable extracted input tree.

B2 consumes only `data/dataset/processed/b2-training.jsonl`, 7,208 train records,
exact accepted SHA-256
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
The full 8,000-row canonical source and its companions are packaged solely for
existing adapter provenance verification. Its 792 development records never
enter retrieval or embeddings. English/VI gold files remain outside retrieval.

## External setup you perform

1. Prepare a **private** Kaggle dataset containing the archive and a private
   notebook based on `notebooks/14_kaggle_b12.ipynb`. This task does not upload.
2. Check your actual GPU quota/session limits and obtain the approved T4 hardware.
   No historical account quota/session/storage number is a current guarantee.
3. Provision Python 3.11 and the exact core dependency versions in `uv.lock`.
   Runtime preflight lists expected/installed versions without importing ML.
   The bundle includes the project lock, not wheels or an installed environment;
   provisioning and dependency resolution have not been tested on Kaggle here.
4. Obtain genuine local Hugging Face snapshots for the fixed model
   `meta-llama/Meta-Llama-3-8B-Instruct` and encoder
   `sentence-transformers/all-MiniLM-L6-v2`, with their actual lowercase 40-hex
   revisions. Do this separately under the applicable model license/access.
   Do not send tokens to chat or write them in notebook cells/outputs. Inference
   needs the local cache only; it does not log in or download anything.
5. In the notebook, set the archive path/SHA, campaign ID, revisions, HF cache
   root and explicit per-native-process `RUN_TIMEOUT_SECONDS`. Leave
   `ALLOW_REAL_INFERENCE=False` until a separately authorized genuine run.

Model and tokenizer use the same revision in the existing backend. No fake
revision is provided. The template keeps unknown values `null` and remains
blocked. HF layout must be `HF_HOME/hub/models--<owner>--<name>/snapshots/<revision>`;
local symlinks may only resolve within that HF cache. Preflight checks required
config/tokenizer/weight files and referenced weight shards, not model loading
or weight authenticity. Genuine load/hardware/OOM/latency evidence is external.
The existing backend's 4-bit/BF16 behavior is unchanged and untested on T4 here.

## Preflight, plan and authorized execution

Copy `configs/kaggle-b12-run.template.json` **outside** the input tree and fill
its unresolved operational fields and explicitly select `language=en` or
`language=vi`. Other research fields are fixed: three runs per baseline per language, seed 42, greedy, batch one, max_new_tokens 512, 4-bit.

```bash
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py preflight \
  --root /tmp/b12-input --level runtime \
  --config /path/to/run-config.json --output /path/to/b12-runs
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py plan \
  --root /tmp/b12-input --config /path/to/run-config.json --output /path/to/b12-runs
```

Data/runtime preflight and planning do not load an encoder/model, probe CUDA,
read credentials, call BigQuery or execute inference. `data_ready` only covers
inputs. Runtime `ready` covers structural prerequisites; it is not hardware,
model compatibility or scientific acceptance.

Before primary evaluation, perform the existing CLI17 `predict` smoke on five
non-test training questions for B1/B2, with the same pinned configuration and
explicit real opt-in. For B2 pass the training record as target ID so its family
is excluded. Keep smoke outputs separate; do not change prompts/configuration
in response to held-out benchmark outcomes. This offline task does not run smoke.

Only in the separately authorized Kaggle execution, after successful smoke:

```bash
PYTHONPATH=/tmp/b12-input/src python /tmp/b12-input/scripts/25_kaggle_b12.py run \
  --root /tmp/b12-input --config /path/to/run-config.json --output /path/to/b12-runs \
  --real-inference
```

On Kaggle use the notebook's `/kaggle/working` paths rather than the local examples
above. The runner checks data, software/cache prerequisites and T4 before invoking
CLI17 with explicit `--language` and `--benchmark-root` in a separate process for each run. All HF loaders are forced
offline; no BigQuery execution is part of this runner. It plans
`<campaign>-b1-<language>-r01..03` and `<campaign>-b2-<language>-r01..03`.
Each config schedules six processes. A complete EN+VI protocol has twelve
processes: three compatible runs for each (baseline, language), never three total
shared across languages. Metrics keep N=100 separately for each snapshot; do not
pool the two snapshots into a 200-case result. B2 uses the same approved bilingual
train export in both languages; no language filtering or retrieval-policy change.
Caches are isolated at `<output>/<language>/cache/b2-few-shot.npz`; run folders
also include language. Native predictions/logs carry full paired source lineage
and per-case prompt hashes; reports bind the ordered prompt hash list. Choose
separate language configs (notebook `LANGUAGE`) and preserve each config. Use
`--baseline b1|b2 --replicate 1|2|3` to run an unstarted selection. Campaign outputs
are not overwritten: retain failed attempts, choose a new campaign for a genuine
retry and record its relationship to the old attempt in experiment notes.
Never combine partial attempts into one scientific run.

Each run retains `run.json` (exact config, bundle hash, argv, hardware, Python,
core package checks, full installed inventory, start/finish and status), native
predictions/log/report and native stdout/stderr. A timeout/nonzero exit preserves
evidence and stops subsequent runs. Existing CLI17 publication/provenance and
scientific blockers remain authoritative; the wrapper does not upgrade readiness
or fabricate SQL execution accuracy, privacy/cost evidence or B3 decisions.

Keep the Kaggle notebook URL/version and full output directories for handoff.
Next evidence work is genuine B1/B2, then T5.4 comparison and T5.5 B3 decision;
typed VI execution plumbing is implemented; genuine bilingual scientific evidence remains pending.

## Native and T5.4 handoff

CLI17 defaults to English for compatibility; Vietnamese requires `--language vi`
and an explicit finalized VI `--test-set`. It retains the original IDs/question,
language/pair/English identity, gold SQL, review/candidate digests and source
fingerprints. The typed adapter rejects altered or missing source files, mismatched
language/snapshot/manifest/lineage/evidence. Outputs cannot alias any protected
benchmark source. VI default native outputs live under `data/eval/b12/vi/<baseline>/<run-id>/`;
explicit runner outputs remain per process as above. Existing outputs from another
run or language fail before model loading. Real inference still requires opt-in.

After genuine inference, CLI19 `adapt b12 --language vi --benchmark-root <input-root>`
consumes each native predictions/log/report triple with the matching VI test set.
It revalidates paired authority and exact per-case source lineage across files.
Canonical source references/fingerprints bind language and paired sources; exact
snapshot identity keeps EN/VI denominators and reproducibility separate. For EN,
use `--language en` (default). Prompt fingerprints hash complete messages including
each question: T5.4 binds their ordered list rather than requiring equal hashes
across different questions. No prompt text or research policy changed.

Inference alone does not measure predicted SQL execution accuracy. T5.4 genuine
execution, cost/privacy evidence, three compatible replicates per language, and
comparison remain external stages. Never infer new BigQuery results from VI's
reused historical gold evidence.
