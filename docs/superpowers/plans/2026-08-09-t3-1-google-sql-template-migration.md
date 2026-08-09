# T3.1 GoogleSQL Template Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and `superpowers:test-driven-development`.

**Goal:** Replace the superseded SPARQL scaffold with 25 bounded, catalog-linked
GoogleSQL templates validated offline and live.

**Architecture:** JSON remains the versioned library. A Python validation/render
boundary loads the analytical catalog, enforces template/slot/schema/CQ safety,
and orchestrates opt-in dry-run/execution through a Click CLI. Existing IDs and
distribution remain stable while executable fields migrate atomically.

**Tech stack:** Python 3.11, JSON, `google-cloud-bigquery` 3.x, Click 8, pytest 8,
Ruff, GoogleSQL.

---

### Task 1: Define contract-v2 tests and validator boundary

**Files:**
- Rewrite `tests/unit/test_query_templates.py`
- Create `src/nl2sparql/dataset/templates/validate.py`
- Modify `src/nl2sparql/dataset/templates/__init__.py`

- [x] Write failing tests for exact IDs/distribution, v2 required fields,
  legacy-field absence, slots/placeholders, safe/bounded SQL, schema/CQ refs.
- [x] Confirm RED against legacy JSON/module.
- [x] Implement loader, dataclasses, offline validator and typed renderer.
- [x] Keep errors actionable and network-free.
- [x] Run focused tests GREEN and commit.

---

### Task 2: Migrate all 25 templates

**Files:**
- Rewrite `src/nl2sparql/dataset/templates/templates.json`
- Rewrite `src/nl2sparql/dataset/templates/README.md`
- Rewrite `notebooks/07_template_validate.ipynb`

- [x] Add/extend failing semantic tests for relation coverage, role policies,
  CQ24 exclusion and example-fill precision.
- [x] Replace every SPARQL query with canonical managed GoogleSQL.
- [x] Preserve IDs/categories/difficulties, expected aliases and meaningful NL
  seeds where semantics remain valid.
- [x] Update README/notebook to the Plan B workflow.
- [x] Run focused tests GREEN and commit.

---

### Task 3: Add live validation CLI

**Files:**
- Modify `src/nl2sparql/dataset/templates/validate.py`
- Create `scripts/08_validate_sql_templates.py`
- Extend `tests/unit/test_query_templates.py`

- [x] Write fake-client tests for 25-case preflight, accepted 20/64 GiB caps, explicit
  execution, result columns, non-empty policy and metrics.
- [x] Confirm RED before client orchestration.
- [x] Implement offline/default, `--live` dry-run and `--execute` modes.
- [x] Run focused tests GREEN and commit.

---

### Task 4: Run live evidence and close T3.1

**Files:**
- Modify `docs/tasks/phase-3-dataset/01-query-templates.md`
- Modify `docs/memory/05-DECISION_LOG.md`

- [x] Dry-run all 25 examples and require cost gates.
- [x] Execute all examples once; fix semantic/result failures test-first.
- [x] Record zero-row allowed cases, bytes and latency without hiding misses.
- [x] Run full pytest, Ruff, format and `git diff --check` after the coupled
  T3.2 consumer migration (336 passed).
- [x] Commit closure with a clean worktree, then compact and migrate T3.2.
