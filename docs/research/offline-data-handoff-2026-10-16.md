# Offline data handoff — 2026-10-16

Worktree: `.worktrees/t33-b2-offline`, branch `feat/t33-b2-offline`, base
`544fa82` (PR #26 merged). Main was clean before creating the isolated worktree;
existing worktrees were kept. No subagents, network/live query, credential read,
model/encoder download, GPU inference/training, genuine evaluation, Kaggle upload,
merge, push or PR was performed by this task.

## Delivered

1. Backlog and T3.3/T3.5/T5.2/T5.5 tickets now distinguish completed Stage A,
   canonical corpus and English finalization from pending Vietnamese human
   review and genuine Kaggle B1/B2. Original failed-audit evidence remains.
2. Training integration was committed at **`9adf02c` before opening Vietnamese
   benchmark content**. Canonical → lossless train export → B2 shared data
   preflight → encoder/cache boundary. [Integration report](b2-training-integration-2026-10-16.md)
   and [hash bindings](../evidence/b2-training-integration-2026-10-16.json).
3. [Vietnamese review pack](../../data/review_packs/t3_5_vi_2026-10-16/README.md):
   10 batches × 10, original question/SQL/metadata, stable IDs, per-line and source
   file hashes, completely blank decision/score fields. The source candidates,
   review events, guide and manifests remain byte-identical. No acceptance,
   scores or reviewer identity were invented. Training code/tests were unchanged
   after the review-pack boundary.

B2 consumes **7,208 train records / 901 families**, including 3,604 EN + 3,604 VI.
The 792 development records / 99 families never enter retrieval. Export digest:
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
Use that exact fingerprint with CLI17 and explicit
`--training data/dataset/processed/b2-training.jsonl`; it is distinct from the
8,000-row canonical hash. Canonical corpus/manifest/audit, accepted Stage A,
catalogue and exclusion index are unchanged. No `style` rename or added fixture
flag. Runtime pins the exact accepted publication and all seven immutable
sources; future publications require a deliberate evidence/binding update.

## Fresh checks

- Regression observed failing on the old fixture-field requirement, then passing.
- Focused tests: **42 passed in 99.42s** (new canonical integration + existing
  retrieval tests), including negative source/export/SQL/fixture/split/fingerprint
  cases and actual `FewShotRetriever.from_snapshot` loading via a temporary,
  explicitly test-only synthetic cache with no encoder. That cache was not
  published or counted as scientific evidence.
- Current canonical CLI21 `validate-artifact`: exit 0, 8,000 records, status valid.
  No historical absent-canonical audit validator rerun.
- Two guarded exports and guarded data preflight: exit 0; export and manifest
  byte-identical across builds. Successful guards observed zero network,
  credential, model/provider import and subprocess attempts. Python-level
  instrumentation permits SDK definitions; it is not an OS sandbox. Initial
  failed guard attempts are preserved separately and are not counted as passes.
- Ruff check + format check for all four changed Python code/test files and
  `git diff --check` passed before training lock.
- Vietnamese current `validate-draft`: exit 0, `paired_draft_valid`, 100 pairs,
  exact existing semantic snapshot binding. This validates no human decisions.
- Pack rebuilt without byte changes; independent integrity check confirms all
  100 unique IDs in source order, exact questions/SQL, blank worksheets, original
  source hashes and training-lock artifact hashes unchanged.

Fresh full repository suite: **1,505 passed, 342 warnings in 563.75s**, exit 0,
using `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest -q`.
The complete log is archived as `b2-training-2026-10-16/full-suite.log`. The earlier
**1,485 passed / 342 warnings** remains historical evidence at the prior revision;
it is not reused as a result for this task.

Logs: `docs/evidence/b2-training-2026-10-16/` and
`docs/evidence/vietnamese-review-pack-2026-10-16/`.

## User action and remaining gates

Open [batch 01](../../data/review_packs/t3_5_vi_2026-10-16/batch-01.md), provide a
decision and naturalness / SQL faithfulness / terminology / ambiguity scores
for each pair in its [blank worksheet](../../data/review_packs/t3_5_vi_2026-10-16/batch-01.csv)
or in chat. Keep IDs and candidate-line hashes. REVISE also needs your revised
question; skipped fields remain pending. Continue batches 02–10. Codex may append
only the explicit human decisions you provide, preserving the original candidate
snapshot. No need to review English candidates again.

After all 100 final ACCEPT events, run the existing review/finalization and exact
paired/live-evidence binding workflow; reuse English evidence only if its policy
permits the exact SQL/metadata binding. Genuine live work, if needed, belongs to
a separately authorized run. No Vietnamese final snapshot is claimed here.

Required order remains: data integration (done) + Vietnamese review/finalization
→ pinned genuine B1/B2 on Kaggle T4 → T5.4 comparison → T5.5 decision on B3.
B0's genuine 0/100 remains unchanged. Model/encoder revisions, genuine embeddings,
Kaggle runs, comparison and B3 decision are pending external evidence. No hosted
LLM baselines or Stage D noise generation are reopened.
