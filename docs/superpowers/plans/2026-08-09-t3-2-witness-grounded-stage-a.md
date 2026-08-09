# T3.2 Witness-Grounded Stage A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and live-verify 1,000 deterministic GoogleSQL Stage A records with bounded BigQuery witness execution.

**Architecture:** Candidate generation is network-free and uses the T3.1 typed renderer plus committed value pools. A separate verifier groups records only by safe `LIMIT` monotonicity, preflights the full witness workload, executes each witness once, and attaches explicit proof metadata before artifact writing.

**Tech Stack:** Python 3.11, JSON/JSONL, `google-cloud-bigquery` 3.x, Click 8, pytest 8, Ruff, GoogleSQL.

## Global Constraints

- Seed is exactly 42 and the target is exactly 1,000 records.
- Difficulty allocation is 350 easy, 450 medium, and 200 hard.
- No template exceeds 100 records and no entity value exceeds 50 records.
- Every SQL uses the T3.1 typed renderer and differs by real slot values.
- Witness caps are 20 GiB/query and 96 GiB total; query cache is disabled.
- Only `n` may be ignored when forming a monotonic witness group.

---

### Task 1: Deterministic candidate contract

**Files:**
- Rewrite: `tests/unit/test_synthetic_generate.py`
- Rewrite: `src/nl2sparql/dataset/generate.py`
- Create: `src/nl2sparql/dataset/stage_a/value_pools.json`

**Interfaces:**
- Consumes: `load_templates()` and `render_template(template, values)` from T3.1.
- Produces: `load_value_pools(path)`, `generate_stage_a_records(templates, pools, target_count=1000, seed=42)`, and `validate_stage_a_records(records, templates)`.

- [ ] Write failing tests requiring SQL-only fields, exact 350/450/200 counts,
  100-record template cap, 50-record entity cap, unique SQL/IDs/hashes, stable
  seed-42 output, typed entity extraction, and rejection of invalid targets.
- [ ] Run `uv run pytest tests/unit/test_synthetic_generate.py -q` and confirm
  failures reference the legacy `sparql` contract.
- [ ] Implement immutable allocation constants, pool loading/validation,
  slot-driven candidate generation, canonical SHA-256 helpers, and record
  validation. Do not add timestamps or live results during generation.
- [ ] Run the focused tests, Ruff, format, and `git diff --check`; commit the
  candidate boundary.

### Task 2: Witness planner and fake-client verifier

**Files:**
- Create: `src/nl2sparql/dataset/stage_a/verify.py`
- Create: `src/nl2sparql/dataset/stage_a/__init__.py`
- Create: `tests/unit/test_stage_a_verify.py`

**Interfaces:**
- Consumes: validated candidate records and the T3.1 template list.
- Produces: `build_witness_groups(records)`, `dry_run_witnesses(client, ...)`,
  `verify_stage_a(client, records, templates, verified_at, ...)`,
  `WitnessPreflight`, and `StageAVerificationReport`.

- [ ] Write fake-job tests proving singleton exact groups, `n`-only monotonic
  groups, smallest-limit witness selection, 20/96 GiB gates, complete preflight
  before execution, immediate re-dry-run, cache-off configs, exact schema,
  positive count semantics, and empty/schema/cache failure paths.
- [ ] Run the focused verifier tests and confirm RED on the missing module.
- [ ] Implement the planner, dataclasses, dry-run orchestration, execution
  checks, metrics, and proof propagation without mutating input candidates.
- [ ] Run both Stage A test files GREEN, Ruff, format, and whitespace checks;
  commit the live-verification boundary.

### Task 3: CLI, artifacts, and migrated documentation

**Files:**
- Create: `scripts/09_generate_stage_a.py`
- Rewrite: `notebooks/08_generate_synthetic.ipynb`
- Rewrite: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Mark superseded: `docs/superpowers/specs/2026-07-04-t3-2-synthetic-pipeline-scaffold-design.md`
- Mark superseded: `docs/superpowers/plans/2026-07-04-t3-2-synthetic-pipeline-scaffold.md`
- Extend: `tests/unit/test_synthetic_generate.py`

**Interfaces:**
- Default CLI writes deterministic unverified candidates without credentials.
- `--live` constructs BigQuery only after local validation and writes verified
  JSONL, generation config, and stats atomically after all witnesses pass.

- [ ] Write CLI tests for offline no-client behavior, explicit live mode,
  deterministic JSON/config/stats output, and no partial final artifact on a
  verifier failure.
- [ ] Implement the Click CLI and artifact writers using temporary sibling
  files followed by replacement only after validation.
- [ ] Migrate the notebook/task wording from SPARQL/Fuseki to GoogleSQL/BigQuery
  and mark the July scaffold documents superseded.
- [ ] Run focused tests and commit the runnable pipeline.

### Task 4: Live generation and closure

**Files:**
- Generate: `data/dataset/raw/synthetic-stage-a.jsonl`
- Generate: `data/dataset/raw/generation-config.json`
- Generate: `data/dataset/raw/stats.md`
- Modify: `docs/tasks/phase-3-dataset/01-query-templates.md`
- Modify: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

- [ ] Run offline generation twice and require identical candidate hashes.
- [ ] Run live preflight; if a pool member is empty, replace it only with a
  live-derived value and record the evidence rather than weakening policy.
- [ ] Execute all witness groups once and write the final 1,000 verified records.
- [ ] Validate exact counts, caps, unique SQL/hashes, 100% non-empty proofs,
  zero cache hits, artifact digest, and recorded cost/latency metrics.
- [ ] Run full pytest, Ruff, format, and `git diff --check`; close T3.1 and T3.2,
  commit with a clean worktree, compact, then migrate T3.3.

