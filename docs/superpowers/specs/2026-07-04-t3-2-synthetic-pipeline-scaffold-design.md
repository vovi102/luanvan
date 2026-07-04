# T3.2 Synthetic Pipeline Scaffold Design

## Goal

Build an offline, reproducible scaffold for Stage A synthetic dataset generation. The scaffold renders T3.1 templates into `(SPARQL, nl_seed)` records using deterministic slot fills, writes JSONL and stats artifacts, and leaves Fuseki execution/non-empty verification pending until the full KG is loaded.

## Scope

Included:

- Add `src/nl2sparql/dataset/generate.py` with template loading, rendering, deterministic record generation, JSONL writing, stats writing, and CLI.
- Add unit tests for reproducibility, record schema, uniqueness, template caps, and stats.
- Add an unexecuted notebook `notebooks/08_generate_synthetic.ipynb`.
- Update T3.2 task evidence as scaffold done.

Excluded:

- Executing generated SPARQL against Fuseki.
- Rejecting empty query results.
- Producing the final 1000 live-verified records.

## Record Contract

Each scaffold record includes `id`, `template_id`, `difficulty`, `slot_values`, `entities_used`, `sparql`, `nl_seed`, `result_preview`, `result_count`, `execution_time_ms`, `verified_at`, and `verification_mode`.

`verification_mode` is `offline_render_only` for scaffold records.
