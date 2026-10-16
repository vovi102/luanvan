# Offline Kaggle B1/B2 runner/bundle preparation — 2026-10-16

Implementation is prepared locally on `feat/kaggle-b12-bundle`, based on
`ededf48` (the locally finalized Vietnamese benchmark, following merged PR #27).
No subagents, model/encoder downloads, credential reads, GPU/model execution,
live BigQuery/network calls, Kaggle upload, push, merge or PR were performed.

## Deliverables and boundaries

- `scripts/25_kaggle_b12.py`: bundle, safe unpack, data/runtime preflight, command
  plan and explicitly opted-in future campaign execution.
- `src/nl2sparql/kaggle/`: standard-library orchestration around unchanged CLI17
  plus the existing data validators. No baseline/prompt/retrieval/linker, accepted
  data, research model/encoder identity or acceptance-threshold change.
- `configs/kaggle-b12-inputs.json`: explicit source paths and accepted-input hashes.
  The 180-file archive excludes .git, credentials, caches, tests/fixtures, model
  weights and arbitrary repository files. Python source package transport includes
  dormant modules; preparation/runner does not invoke remote provider paths.
- `configs/kaggle-b12-run.template.json`: fixed research settings with unknown
  model/encoder revisions, HF cache, campaign identity and wall-time cap left null.
  The tokenizer shares the existing model revision. No fake pins are supplied.
- `notebooks/14_kaggle_b12.ipynb`: private-input bootstrap, archive SHA check,
  safe fresh-workspace extraction, data/runtime preflight and optional campaign
  execution; `ALLOW_REAL_INFERENCE=False` by default. No install/download/login,
  credential or BigQuery cells. Notebook structure/code cells were checked;
  it was not executed as a Kaggle notebook or on GPU.
- [Runbook](../planning/kaggle-b12-runbook-2026-10-16.md): exact local commands,
  required external provisioning, non-test GPU smoke and native output handoff.

The runner plans three separate CLI17 processes for each B1/B2 configuration,
seed 42, greedy/batch-one/max_new_tokens 512/4-bit unchanged. Outputs are isolated
by campaign/baseline/replicate, never overwritten. Status, exact argv/config and
bundle hashes, hardware, Python/core versions/full installed inventory, native
predictions/log/report and stdout/stderr are retained. Nonzero exits, timeout or
interrupt stop further runs and preserve evidence. The wrapper does not rewrite
native scientific readiness, fabricate execution accuracy or combine partial runs.
Native process tests use explicitly synthetic temporary outputs, never published
or counted as scientific inference evidence.

## Actual input artifact

Archive (ignored local build output):
`.local/kaggle-b12/release/input-bundle.tar.gz`, **2,673,145 bytes**.

File SHA-256:
`4a49b57835e031986e3abcd274955df504ccf3b1811640fa8ef72ca854c70e4f`.

Content manifest digest:
`90b627f88da4db723f79c5fdde3fc4b0c88e90e4234e1d1bb5c24d285f69ef09`.

The sibling `input-bundle.sha256` and `kaggle-bundle.json` are supplied locally;
[archived manifest](../evidence/kaggle-b12-preparation-2026-10-16/bundle-manifest.json)
records every included path, role, size and hash. Archive bytes depend only on
these explicit inputs, with fixed tar ownership/mode/mtime and gzip metadata;
no absolute workspace path, Git working-tree state or current clock enters it.
The source/data content digest is authoritative; no uncommitted code is falsely
labeled as a published Git revision. Archive bytes are reproducible after commit.

The actual path is canonical T3.3 → unchanged 7,208-row train export → actual B2
preflight/retrieval boundary. Canonical's full 8,000 rows travel only as required
provenance input for the existing strict adapter. Its **792 development records
never enter retrieval/embeddings**. Exact accepted training fingerprint remains
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.

## Important consumer gap

**Execution currently supports English only.** CLI17's existing trusted loader
requires the English `nl`/reviewed T3.5 profile. Vietnamese final rows use typed
paired `question`/pair lineage. This task packages and validates all 100 reviewed
VI rows/review events/final manifest/reused live evidence but refuses language=vi
execution. No field rename or manual trusted flag is used to bypass this gap.
A dedicated typed VI consumer/evaluator is required before bilingual inference.
The baseline/prompt/retrieval/accuracy tests remain frozen after benchmark exposure.

## Fresh verification

- RED evidence retained: initially missing CLI/bundle feature; directory/cache
  aliases and malformed archive; absent timeout support; interruption incorrectly
  retained as started. Tests preceded their fixes. Earlier prototype passing
  logs are checkpoint evidence, not the final revision's complete verification.
  RED text logs trim trailing whitespace for Git; byte-exact captured originals
  are preserved in adjacent `.log.gz` files and bound by raw-content hashes.
- Final focused new + existing B1/B2 baseline/workflow/retrieval suite:
  **68 passed in 25.50s**.
- Two final builds are byte-identical (`cmp`); both guarded build commands exit 0.
- Guarded unpack: exit 0. Negative tests cover wrong archive SHA, traversal,
  malformed archives, unlisted files and input/output aliases; the extractor also
  enforces regular-file-only members, unique names and a total size cap.
- Guarded data preflight executed the CLI **inside the extracted bundle**, using
  only that bundle's source path. It returned `data_ready`: 7,208 train, 100 English,
  100 Vietnamese and exact accepted hash. Real B2 validation, finalized English
  loader, original paired review/manifest and exact evidence-reuse checks ran.
- Runtime template preflight: **blocked, exit 2**, as intended; its first missing
  operational field is the wall-time cap. The model/encoder revisions, campaign
  identity and HF cache are also null in the template. The 15 installed core
  dependency versions matched uv.lock via metadata only. No GPU/model/cache
  readiness is inferred from that match. Missing cache/shards are separately tested.
- Successful build/unpack/data and blocked runtime commands all observed zero
  network, credential, model/provider import and subprocess attempts under the
  [archived guard](../evidence/kaggle-b12-preparation-offline-runner-2026-10-16.txt).
  This is Python instrumentation, not an OS sandbox; SDK definitions may import.
- Ruff lint/format checks passed on all six new Python code/test files. Whole-diff
  whitespace, artifact hashes and training/VI locked hashes are checked at handoff.

Fresh full repository suite: **1,534 passed, 342 warnings in 619.26s**, exit 0,
using `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest -q`.
The prior 1,505-test result is historical and is not reused as a new result here.
Logs: `docs/evidence/kaggle-b12-preparation-2026-10-16/`;
[companion machine evidence](../evidence/kaggle-b12-preparation-2026-10-16.json).

## Still external or pending

The bundle contains no dependency wheels, model/encoder weights or chosen genuine
revisions. Python/Kaggle environment provisioning, account/quota, private dataset
upload, actual cache setup, T4 hardware/load/4-bit compatibility/non-test smoke,
OOM/latency and genuine native runs remain unverified external work. Structural
runtime preflight is not a model/hardware test or scientific acceptance.
Existing 4-bit/BF16 backend behavior remains unchanged.

Use the runbook and notebook, supply genuine pins/cache/campaign/wall-time cap,
validate runtime, perform non-test GPU smoke and only then authorize primary
English inference. Keep notebook URL/version and all native output directories.
Complete the typed VI consumer before bilingual inference. Genuine B1/B2 → T5.4
execution/comparison/privacy/reproducibility evidence → T5.5 decision on B3.
No Stage D noise, hosted baseline or research-model substitution is reopened.
