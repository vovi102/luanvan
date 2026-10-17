# Typed Vietnamese B1/B2 consumer and bilingual runner — 2026-10-16

Implementation is offline on `feat/b12-bilingual-consumer`, in
`.worktrees/b12-bilingual-consumer`, based on main `95f623e`. Read-only remote
inspection confirmed the same main commit before editing. Existing worktrees
were preserved. Native execution only; no subagents, push, merge or PR.

## Typed boundary

`src/nl2sparql/models/b12/paired_snapshot.py` authenticates eleven accepted
source files by exact SHA-256: EN/VI snapshots, final manifests, live evidence,
English candidates/review/selection, Vietnamese candidates and the original
100-event user review log. Changing this publication requires an explicit
binding update with new evidence, not a caller flag or a rehashed manifest.

The loader retains the English B0 finalized loader and reads typed English
pairing semantics from the final selection and genuine evidence. It rebuilds
Vietnamese finalization using the existing strict `PairedCandidate`,
`PairedReviewDecision` and `finalize_paired_cases` contracts, compares complete
final rows and the rebuilt manifest, and recomputes **exact reused English live
evidence**. It rechecks source bytes after validation. No BigQuery client/job is
created. The original user bulk ACCEPT events and scores 5/5/5/1, review digests,
English job IDs, timestamps and historical measurements remain unchanged.
There is no claim of independently elicited per-case scores or new execution.

`load_evaluation_cases(..., language="vi", source_root=...)` returns existing
EvaluationCase values with a typed `PairedCaseSource`: the complete original
`PairedFinalCase`, sorted (relative source path, exact digest) bindings, and
`evidence_mode=exact_reused_english_live_evidence`. IDs, original question,
language, pair/English identity, SQL, normalization and source/review digests
are preserved. This is a validated adapter, not a `question` → `nl` rewrite or
a synthetic-trust override. English keeps the existing finalized `nl` path.
Wrong language/snapshot/hash/lineage and absent or modified evidence fail closed.
Manual cases/flags cannot acquire loader trust; synthetic backend completions
remain scientific blockers. Evaluator rejects mixed language/snapshot inputs
before prediction and keeps the full N=100 separately for each language.

## CLI and output flow

- CLI17 `evaluate --language en|vi --benchmark-root <root>` retains explicit
  `--real-inference`. Source and output validation occur before backend loading.
  Original question only enters prediction; gold is retained for later evaluation,
  never supplied as retrieval/training/prompt examples.
- Native predictions/logs retain language and full per-case typed paired source;
  the report binds source digests, historical evidence mode, snapshot, language
  and ordered prompt hashes. VI defaults use
  `data/eval/b12/vi/<baseline>/<run-id>/`. Existing output from a different run,
  baseline or language is refused; protected source files cannot be outputs.
- CLI25 run config chooses exactly one `language`, `en` or `vi`. Existing template
  defaults explicitly to EN; select VI in its own config. Research model, encoder,
  generation settings, prompt policy and retrieval definition are unchanged.
- Each config plans **six native processes**, three B1 and three B2. Complete
  EN+VI protocol is **twelve processes**, three per (baseline, language). Run IDs
  include campaign, baseline, language and replicate. Language caches use
  `<output>/<language>/cache/b2-few-shot.npz`; native run outputs remain separate.
  Do not pool EN/VI metrics, partial attempts or incompatible replicates.
- Notebook `LANGUAGE` selects the config; EN/VI config filenames are separate.
  `ALLOW_REAL_INFERENCE=False` remains default. Notebook cells were checked as
  code/JSON, never executed as a notebook or on GPU.
- CLI19 `adapt b12 --language vi --benchmark-root <root>` revalidates VI authority,
  original native metadata, cross-file source lineage, report evidence mode and
  source bindings. Canonical refs/fingerprints bind language and paired sources;
  native artifact refs retain the complete source-path mapping. Canonical snapshot
  hashes keep language-specific denominators/reproducibility separate. Existing
  English legacy artifacts remain readable.

The real native-to-canonical round trip exposed an existing adapter defect:
`prompt_sha256` hashes complete messages including the question, while the old
adapter required equality across questions. The fix binds the ordered list of
per-case prompt digests across predictions/log/report and computes its run digest.
The prompt text, baseline behavior and acceptance thresholds did not change.

## B2 and leakage

Both languages consume exactly `data/dataset/processed/b2-training.jsonl`, the
unchanged 7,208 original train rows (901 families; 3,604 EN + 3,604 VI), SHA-256
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.
The same strict accepted canonical-source verification remains in place.
Canonical 8,000-row data travels only for provenance. The 792 development rows,
benchmark/gold and review files do not enter the retrieval corpus or training
embedding matrix. At inference only the target question supplies the transient
retrieval query vector; gold SQL never enters that query. No language
filter, retriever/linker/prompt/accuracy tuning, model change, threshold change,
Stage D, review reopening or hosted baseline was introduced.

## Successor bundle

Local archive (ignored build output):
`.local/kaggle-b12-bilingual/release/input-bundle.tar.gz`, **2,678,997 bytes**,
181 files. File SHA-256:
`2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de`.
Content manifest digest:
`4c10b260b7e1b119b9b6a13b43b9c00c3a4ec84402648b03eac92253840682bc`.

Two builds are byte-identical, checked with `cmp`. Independent guarded unpack
and data preflight used only the extracted bundle's source path. The allowlist
adds the typed snapshot module; all accepted-input hashes are unchanged. Fixed
archive metadata excludes workspace paths, clock and Git state; source bytes
are reproducible after commit. [Manifest](../evidence/b12-bilingual-consumer-2026-10-16/bundle-manifest.json).

This supersedes the English-only archive SHA-256
`4a49b57835e031986e3abcd274955df504ccf3b1811640fa8ef72ca854c70e4f`
for future execution. The previous archive/evidence and failed audits are
preserved; they were not relabeled or overwritten.

## Fresh verification

- Clean baseline focused suite: **44 passed in 28.43s**.
- Initial regression: **7 failed**, loader lacked language support and runner
  rejected VI. Intermediate round trip: **1 failed, 55 passed**, exposing the
  per-case prompt fingerprint defect above. Both RED logs are retained.
- Additional RED: report source binding absent (**1 failed**); other-baseline
  overwrite and late run-ID validation (**2 failed**). Fixes preceded final checks.
- Final focused source/native/canonical regressions: **42 passed in 12.96s**.
- Full final suite: **1,564 passed, 342 warnings in 721.14s (12:01)**, exit 0,
  using `PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest -q`.
  Includes the guarded actual bilingual runner integration. Interrupted development
  checkpoints were superseded and are not counted as passing verification.
- Ruff lint and format: pass for **13** Python files in the touched modules/tests (including two unchanged Kaggle module files).
- CLI17 evaluate and CLI19 adapt-b12 help: exit 0; new language options present.
- Guarded build ×2/unpack: exit 0; identical archive bytes.
- Guarded extracted data preflight: `data_ready`, 7,208 train / 100 EN / 100 VI,
  exact accepted training hash. Actual production B2, English and typed VI loaders
  run, including human finalization and exact reused evidence reconstruction.
- Guarded runtime template: `blocked`, exit 2 as intended; unresolved timeout,
  revisions, campaign/cache fields remain null. Package versions matched lock
  via metadata only; no model/GPU compatibility or current quota is inferred.
- Guarded commands observed zero network, credential, ML/provider import and
  subprocess attempts, using the unchanged archived preparation guard. This is
  Python instrumentation, not an OS sandbox; SDK definitions may import.
- Offline integration uses actual CLI25 planning/data preflight/run orchestration
  and CLI17 evaluation/publication, with finalized artifacts and train export.
  Only hardware/runtime and native process/model/query-vector external seams are
  synthetic. Test-only caches/outputs are temporary. No real encoder/model loads,
  network or credential access; synthetic backend blockers remain in all outputs.

[Machine evidence](../evidence/b12-bilingual-consumer-2026-10-16.json) and
[logs](../evidence/b12-bilingual-consumer-2026-10-16/).
Historical 1,534-test merge evidence is not presented as a new result.

## Remaining external work, in order

1. Prepare the Kaggle Python 3.11 / exact locked environment and genuine local
   Llama 3 8B Instruct + MiniLM snapshots. Record real immutable revisions, model
   license/access, actual GPU quota and storage/session limits. No credentials
   belong in chat, notebook outputs or the input bundle.
2. Privately upload the successor archive and disabled notebook when separately
   authorized. Verify the archive SHA; use a fresh extraction and external outputs.
3. Create EN and VI configs with explicit language, campaign identity, genuine
   revisions, HF cache and positive wall-time cap. Run data/runtime preflight.
   Structural runtime readiness does not prove hardware/4-bit/BF16 compatibility.
4. Obtain non-test T4 GPU smoke with the fixed model/config: five training-only
   questions per baseline, with B2 target IDs for family exclusion. Preserve load,
   OOM, memory/latency/environment evidence. Do not tune against benchmark outcomes.
5. After successful smoke and explicit real opt-in, obtain three complete genuine
   native processes for each (baseline, language), twelve total. Preserve native
   outputs, run.json/stdout/stderr and notebook URL/version; never overwrite failed
   attempts or merge partial runs into a successful run.
6. Adapt each language against its exact snapshot for T5.4; separately authorize
   any predicted-query execution and provide privacy, cost and compatible-run
   evidence. Produce language-specific B0/B1/B2 comparisons, then T5.5 B3 decision.

No genuine B1/B2 inference, evaluation metrics, new BigQuery execution or bilingual
scientific completion is claimed. Human/external runtime, smoke, genuine runs and
T5.4/T5.5 evidence remain pending. Final code review is an author self-review,
consistent with the user's prohibition on subagents; independent review is still
appropriate before a future PR/merge.

Development environment checkpoint: running pytest without `PYTHONPATH=src`
allowed its help-test subprocess to resolve the shared virtualenv's editable
package in main rather than this worktree (`validate_run_id` ImportError). The
isolated test passed with the correct source path; the partial full run was
stopped and preserved, not counted as a full verification. The final command is
`PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest -q`.
Raw failed/checkpoint logs are preserved as deterministic `.log.gz` files with
raw-byte hashes in machine evidence. Readable RED logs trim trailing whitespace
only. The strengthened rollback check passed **1 test in 1.31s** using an older
valid output timestamp so a missing rollback would change bytes and fail.
