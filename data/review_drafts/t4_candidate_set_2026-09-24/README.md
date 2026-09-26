# T4 candidate set — reviewer handoff

**Status:** `DRAFT — agent-authored; not ground truth; not for training or publication`

This folder contains the complete candidate set for the three T4 components:

| Component | Candidate file | Required review count |
|---|---|---:|
| T4.1 Schema linker | `schema_link_candidates.jsonl` | 50 |
| T4.2 Entity linker | `entity_link_candidates.jsonl` | 100 |
| T4.3 Class resolver | `class_resolver_candidates.jsonl` | 50 |

## Review procedure

1. Open the relevant JSONL file and inspect each row against its question and
   target ID / field IDs.
2. Record `ACCEPT`, `REVISE`, or `REJECT` for the matching row in
   `review_decisions.csv`, with a short reason. For `REVISE`, state the exact
   replacement label or wording in the note.
3. Return the completed CSV to Codex. Only `ACCEPT` rows and corrected
   `REVISE` rows can be promoted to `data/eval/`; rejected rows remain as an
   audit trail in this draft folder.

The `manifest.json` binds this candidate set to the catalog and entity-dictionary
snapshots used to create it. Re-generate it with
`UV_CACHE_DIR=.uv-cache uv run python scripts/generate_t4_review_candidates.py`
after either source changes; do not copy it directly into `data/eval/`.

## Promotion record — 2026-09-26

Human review recorded 200 decisions: 162 `ACCEPT` and 38 corrected `REVISE`,
with no undecided or rejected rows. The reviewed results were promoted to the
three canonical files under `data/eval/`; this directory remains the immutable
agent-authored draft and audit trail.

| Component | Canonical rows | Ground-truth SHA-256 | Evaluation status |
|---|---:|---|---|
| Schema linker | 50 | `6bcbbee9cf5595b90d88ca04a84d2d28d0388c36076af2647911da5ec66a6213` | `ready` |
| Entity linker | 100 | `903fc702341c6aaf590fa6aba814794b16b4a1d2fbcd967a412e101db135e9ce` | `ready` |
| Class resolver | 50 | `0da3f12a33af155b92e42c6b36bc3ccad07fe42304636097a907e71538a30429` | `ready` |

The corresponding hash-bound reports are
`reports/schema_linker_evaluation.json`,
`reports/entity_linker_evaluation.json`, and
`reports/class_resolver_evaluation.json`.
