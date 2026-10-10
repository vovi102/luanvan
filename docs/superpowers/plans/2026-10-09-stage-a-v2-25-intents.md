# Stage A v2 25-Intent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an immutable, deterministic Stage A v2 candidate covering all 25
production intents, enforce genuine live acceptance, and connect only accepted
v2 evidence to the bilingual training pipeline.

**Architecture:** A v2 generator and artifact contract live beside unchanged v1
code and files. The existing witness engine gains an explicit validator seam;
v2 manifests distinguish candidate from accepted state. Bilingual audit/build
commands validate the accepted manifest and artifact digest before publication.

**Tech Stack:** Python 3.11, JSON/JSONL, Click, pytest, Ruff, existing Stage A
witness and deterministic bilingual modules.

**Spec:** `docs/superpowers/specs/2026-10-09-stage-a-v2-25-intents-design.md`

## Global Constraints

- Preserve all Stage A v1 artifact/evidence bytes and paths.
- V2 has exactly 1,000 rows, 25 intents, difficulty totals `350/450/200`, seed
  42, template cap 10%, entity cap 5%, and unique IDs/SQL/hashes.
- Never claim acceptance without a passing genuine live witness report.
- Do not read credentials or initialize any provider/model during offline work.
- Do not read raw held-out wording outside exclusion-index creation, and never
  alter Vietnamese benchmark review decisions.
- Keep deterministic producer provenance and zero model/provider/API/cost fields.
- Use TDD and commit each milestone separately.

## Review Focus

- V1 default commands and hashes must remain unchanged.
- Candidate provenance must never be accepted through a missing, mismatched, or
  hand-edited manifest.
- Reordered templates/inputs must not change candidate bytes.
- Address-bearing allocations and slot variation must satisfy uniqueness and
  entity caps without fake SQL diversity.
- Offline commands must not import or instantiate BigQuery/model/provider code.

---

### Task 1: V2 Generator and Candidate Artifact

**Files:**
- Create: `src/nl2sparql/dataset/stage_a_v2.py`
- Create: `src/nl2sparql/dataset/stage_a/v2_artifacts.py`
- Create: `tests/unit/test_stage_a_v2.py`
- Create: `tests/unit/test_stage_a_v2_artifacts.py`
- Create: `data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl`
- Create: `data/dataset/raw/generation-config-v2-candidate.json`
- Create: `data/dataset/raw/stats-v2-candidate.md`

**Interfaces:**
- Produces `generate_stage_a_v2_records(...)`,
  `validate_stage_a_v2_records(...)`, and v2 candidate manifest serialization.
- Consumed by Task 2 live verification and Task 3 source acceptance.

- [ ] Write tests for exact 25-intent allocation, old scientific distribution,
  uniqueness/caps, immutable template semantics, deterministic bytes, separate
  paths, candidate lifecycle, and v1 byte preservation; run and observe RED.
- [ ] Implement the minimal v2 generator and candidate artifact contracts; run
  focused pytest and Ruff to GREEN.
- [ ] Generate and validate the candidate twice at separate paths; record
  byte-identical hashes without calling it accepted.
- [ ] Commit as `feat(dataset): add Stage A v2 candidate`.

### Task 2: Live Acceptance and Offline CLI Isolation

**Files:**
- Modify: `src/nl2sparql/dataset/stage_a/verify.py`
- Create: `scripts/09_generate_stage_a_v2.py`
- Modify: `tests/unit/test_stage_a_verify.py`
- Create: `tests/unit/test_stage_a_v2_workflow.py`

**Interfaces:**
- Consumes Task 1's validator and candidate records.
- Produces an accepted v2 artifact/manifest only from a passing live report.

- [ ] Write tests proving the validator seam preserves v1 behavior, v2 live
  reports require all 25 intents, candidate manifests cannot be promoted, and
  offline CLI help/build never initializes BigQuery; run and observe RED.
- [ ] Implement the verifier seam and v2 CLI with separate candidate/accepted
  targets and fail-closed live publication; run focused pytest/Ruff to GREEN.
- [ ] Run the offline candidate workflow. Do not run live BigQuery without
  explicit credentials/quota/cost authority; record that external gate.
- [ ] Commit as `feat(dataset): gate Stage A v2 acceptance`.

### Task 3: Accepted-Source Bilingual Gate

**Files:**
- Modify: `scripts/20_build_bilingual_training.py`
- Modify: `scripts/21_validate_bilingual_training.py`
- Modify: `src/nl2sparql/dataset/bilingual/assembly.py`
- Modify: `tests/unit/test_bilingual_training_workflows.py`
- Modify: `tests/unit/test_bilingual_assembly.py`

**Interfaces:**
- Consumes Task 2's accepted v2 manifest and artifact digest.
- Produces audit samples/events and canonical bilingual outputs only after the
  accepted-source check.

- [ ] Write tests for missing/candidate/mismatched Stage A manifests, strict
  post-split audit digest binding, and accepted v2 success; run and observe RED.
- [ ] Implement the accepted-source and audit gates; keep validate-only useful
  for candidate diagnostics; run focused pytest/Ruff to GREEN.
- [ ] If live acceptance exists, perform the truthful 100+100 audit, build twice,
  compare bytes, and validate all outputs. Otherwise stop publication at the
  explicit external gate and do not fabricate audit decisions.
- [ ] Commit as `feat(dataset): require accepted Stage A v2 evidence`.

### Task 4: Governance, Verification, and Handoff

**Files:**
- Modify: `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`
- Modify: `docs/tasks/phase-3-dataset/03-paraphrasing.md`
- Modify: `docs/memory/01-ARCHITECTURE.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/planning/prioritized-backlog-2026-09-21.md`

**Interfaces:**
- Consumes exact Task 1–3 outputs and evidence.
- Produces truthful status, hashes, rulings, verification, review, and PR handoff.

- [ ] Record v2 supersession without changing v1 history; distinguish candidate,
  accepted, and canonical states and keep Vietnamese review pending.
- [ ] Run artifact validators, JSON checks, secret scan, full pytest, Ruff
  format/check, and `git diff --check`; commit evidence.
- [ ] Run a fresh-context whole-branch review and one RED→GREEN fix pass for
  Critical/Important findings.
- [ ] Push `feat/stage-a-v2-25-intents` and create a PR to `main` if tooling and
  permissions allow; report the external live gate precisely.

