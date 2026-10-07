# Bilingual evidence preflight — 2026-10-07

This record separates measurements made in the current offline run from future
live-work estimates. No environment file was loaded and no network client was
constructed while producing this draft.

## Measured current state

- Filesystem: 1007 GiB total, 95 GiB used, 862 GiB available (10% used).
- Vietnamese review draft: 100 candidates; approximately 104 KiB of candidate
  JSONL plus small manifest, validation, and review-guide files.
- External API calls: 0.
- Provider cost: USD 0.00.
- Sensitive data sent externally: none.
- Current operation: deterministic local authorship and validation from the
  accepted English T3.5 SQL, semantic metadata, and existing live evidence.

## Live-work authorization gates

No live generation or evaluation is authorized from this preflight. The exact
generation model/revision, request count, duration, and checkpoint size cannot
yet be stated because Tasks 2–3 and workflow CLIs 20–21 are not integrated from
the prerequisite branch. The only permitted future generation provider is the
Google Gemini Developer API under confirmed Free Tier, with a hard recorded cost
of USD 0.00, checkpoint/resume enabled, and no paid fallback.

Encoder selection likewise remains offline and development-only. Its exact
candidate model IDs/revisions, download sizes, latency estimate, and selected
revision must come from a complete candidate input table before execution; final
English, Vietnamese, and unaccented benchmarks are forbidden selection inputs.

The final benchmark/evaluation call count and duration are intentionally not
estimated from missing configurations. They must be recomputed after the user
has reviewed all 100 cases and after model, translator, encoder, dataset, prompt,
catalog, and execution revisions are pinned. Any BigQuery work must retain the
existing dry-run, byte cap, bounded execution, and evidence-reuse gates.

## Resume and privacy risks

- A quota or HTTP 429 response must preserve the checkpoint and stop; resumption
  is allowed only after reconfirming Free Tier availability.
- Prompts may contain benchmark/training questions, SQL, and public catalog
  metadata. Credentials and `.env` contents must never enter prompts or logs.
- Provider responses, temporary checkpoints, secrets, and ignored caches are not
  eligible for publication or commit.
- Until every unresolved field above is pinned and recorded, the safe decision
  is `BLOCKED_NO_LIVE_CALLS`.
