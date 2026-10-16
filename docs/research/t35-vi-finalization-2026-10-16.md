# Vietnamese T3.5 human review and offline finalization — 2026-10-16

Status: 100 Vietnamese paired cases finalized locally from the unchanged
2026-10-07 candidate snapshot after the user explicitly accepted all 100 cases
and confirmed shared scores **5 / 5 / 5 / 1** for naturalness / SQL faithfulness /
terminology / ambiguity. This closes the canonical Vietnamese review/data gate;
genuine B1/B2 model and Kaggle evidence is still pending.

## Human authorization and provenance

The user said “oke tôi duyệt hết các câu 3.5”, then requested all scores be 5.
The assistant explained that ambiguity uses the inverse scale and asked whether
the intended best scores were 5/5/5/1 for all 100. The user confirmed
“oke  đúng”. These explicit decisions authorize the 100 ACCEPT events recorded
in the original `review_events.jsonl`, all round 1 and `reviewer_role=user`.
No reviewer name, per-case rationale, independent audit or observed review time
is invented. Notes identify uniform bulk confirmation in chat, transcribed by
Codex. This is one human's approval, not independent authorship, multiple
reviewers, inter-rater agreement or 100 independently elicited score sets.

Candidate questions, SQL, IDs, metadata and original draft manifest/guide/report
remain byte-identical. Each final row binds its original candidate digest,
English semantic digest and the exact review event digest. No training, retrieval,
prompt, linker, encoder/model choice or accuracy test changed after benchmark
exposure. Earlier failed training audits and r1 evidence remain intact.

## Published local artifacts

- `data/review_drafts/t3_5_vi_candidate_set_2026-10-07/review_events.jsonl`:
  100 user ACCEPT events appended to the previously empty log.
- `data/dataset/test/test-100-vi.jsonl`: 100 finalized canonical Vietnamese rows.
- `data/dataset/test/manifest-vi.json`: exact paired output/English binding.
- `data/dataset/test/live-evidence-vi.json`: reused English execution evidence
  remapped to Vietnamese case IDs, not fresh query results.

Machine-readable file hashes, semantic manifest hashes, approval scope and logs:
[finalization evidence](../evidence/t35-vi-finalization-2026-10-16.json).
The manifest's `output_sha256` is a semantic digest of serialized case mappings;
it is distinct from the complete JSONL file hash recorded in the evidence.

## Workflow and verification

The unchanged `scripts/22_vietnamese_testset_workflow.py` was invoked with
explicit candidates and review-events paths for the 2026-10-07 draft. Existing
CLI defaults still point to the older 2026-10-04 draft; no default was changed.

1. `validate-draft`: `paired_draft_valid`, 100 pairs, existing source digests.
2. Before appending decisions, the real finalizer rejected zero events with
   `finalization requires 100 explicit ACCEPT decisions`.
3. `apply-review`: `finalized`, 100 rows; strict schema/round/score gates active.
4. `verify-live` **without `--allow-bigquery` or project**: `live_ready`, 100 rows.
   Existing reuse checks verify byte-identical SQL, policy, columns and row-count
   contracts against English evidence. Original job IDs, measurements and
   generated-at timestamp are retained. **Zero new BigQuery jobs.** Reused bytes
   and cost are historical measurements, not newly incurred query cost.
5. `validate-final`: `valid`, 100 rows.
6. Separate read-only verification reconstructed the final rows from candidate +
   user events, validated the paired manifest, recomputed reused evidence and
   checked all 23 protected source/training/code/evidence files unchanged.
7. Focused existing tests: **37 passed in 8.96s** using
   `tests/unit/test_testset_paired.py tests/unit/test_evaluation_bilingual.py`.
   No code/test change required; full repository suite was not rerun in this
   data-finalization task. Earlier 1,505-test evidence remains historical.

Both apply and verify ran under the archived
[offline runner](../evidence/t35-vi-finalization-offline-runner-2026-10-16.txt).
Successful runs observed zero network, credential, model/provider import,
subprocess and BigQuery client-construction attempts. SDK definitions may import;
this Python-level guard is not an OS sandbox. The runner's `apply` mode only
records the exact user-authorized payload if the log is empty, or resumes an
identical existing log; any different log fails closed. `verify` is read-only.

Reproduce the read-only check from this worktree root:

```bash
PYTHONPATH=src python docs/evidence/t35-vi-finalization-offline-runner-2026-10-16.txt verify
```

Original review-pack files, builder and evidence retain their pre-review
0-event snapshot. Their empty-log assertions are historical preparation checks,
not current finalization gates. No unaccented derivative was published here.
No download, GPU/model execution, live BigQuery call, upload, push, merge or PR.

## Next work

Stage A/T3.3, B2 train-only integration and English/Vietnamese finalization are
complete. Prepare the Kaggle runner/input bundle and pinned genuine model/encoder
environment, then obtain B1/B2 genuine runs, T5.4 comparison and T5.5 B3 decision.
No Stage D noise generation or hosted LLM baseline is reopened.
