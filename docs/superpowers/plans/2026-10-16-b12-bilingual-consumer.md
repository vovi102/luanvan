# B1/B2 typed Vietnamese consumer implementation plan

> Native execution only, authorized by the user's pasted task; no subagents or repeated approval gates.

**Goal:** consume finalized VI through explicit typed provenance and isolate EN/VI runner outputs.
**Architecture:** preserve English loader; add paired snapshot authority, carry typed lineage through native outputs and validate it at canonical adaptation. One language per campaign config, three processes per baseline per language.
**Spec:** user's approved task and T3.5/T5.2/T5.4 contracts, unchanged research semantics.
**Tech stack:** Python 3.11, dataclasses, Click, pytest, existing paired validators.

## Constraints

Offline only; immutable accepted artifacts/review events; no downloads, credentials, GPU, BigQuery, actual evaluation, upload, push, merge or PR. B2 remains exact 7,208-row train export SHA b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835. Benchmark wording/SQL only validates plumbing/provenance; no accuracy tuning. Genuine readiness cannot originate from fixture backend/cache.

## Tasks

1. [x] Regression RED: finalized VI loader, explicit language planning, mixed language/snapshot rejection, native lineage round trip. Baseline focused tests first.
2. [x] Typed snapshot module: pinned files, reconstruct human acceptance and English semantics, exact manifest/reused evidence; EvaluationCase/Prediction/Run carry language and paired source binding. Keep English trust gate.
3. [x] CLI17 explicit language/root, safe outputs/defaults/protected sources; CLI25 language config and isolated run/cache paths. Bilingual bundle and disabled notebook. T5.4 B12 adapter verifies VI lineage against authority.
4. [x] Offline integration through actual loader/baseline/runner and finalized inputs, with synthetic backend/cache only at external seams. Negative provenance/source/language/output tests. No scientific acceptance from fixtures.
5. [x] Fresh focused/full tests, lint/format/current validators; deterministic double bundle build and extracted data preflight under offline guard. Preserve old evidence, document successor hash and pending external steps. Review diff and commit locally.

## Review focus

- Rehashed manifest or fabricated review/evidence must fail against accepted source pins.
- Same campaign across languages cannot overwrite outputs/cache.
- Model loads occur only after data/output/opt-in checks.
- Canonical adapter preserves language via exact snapshot/native-source artifacts and fingerprints.
- Publication cannot overwrite source evidence or a run from another language/identity.

## Progress

- Base main and remote main: 95f623e; new worktree feat/b12-bilingual-consumer. No AGENTS.md found in project or ancestor paths.
- User explicitly selects native execution and authorizes routine steps, overriding skill approval/delegation handoffs. Final review will be self-review.

- RED→GREEN: finalized VI, wrong language/snapshot, native/canonical lineage, explicit-language planning, report source binding and direct CLI output/run identity checks. Final focused 42 passed; latest strengthened rollback 1 passed.
- Boundary defect found by actual native/canonical round trip: complete prompt hashes legitimately vary per question. Bind their ordered list without changing prompts/research semantics.
- Bundle: two byte-identical builds; guarded extracted actual data preflight data_ready; runtime template blocked as intended. Accepted inputs all 24 hashes unchanged, data diff empty.
- Environment checkpoint: full suite without PYTHONPATH allowed subprocess to load main's editable package. Isolated help failure reproduced and passed with PYTHONPATH=src. Partial wrong-environment run retained and stopped, not treated as verification. Final full run uses PYTHONPATH=src.
- Final review: author self-review (user prohibits subagents). Checked typed source identity, immutable inputs, exact historical evidence mode, explicit language/denominator, output aliases/run isolation, unchanged B2/model/prompt, native/canonical provenance, disabled notebook and external runtime gates. No unresolved implementation finding; final full suite passed 1,564 tests, 342 warnings in 721.14s (exit 0).

- Completion verification: full suite 1,564 passed / 342 warnings / 721.14s; lint and format pass; current extracted production data preflight passes with 0 guarded accesses. Final code is reviewable; scientific evidence stays pending.
