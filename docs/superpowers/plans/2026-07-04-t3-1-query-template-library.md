# T3.1 Query Template Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline-validated SPARQL template library for Phase 3 dataset generation.

**Architecture:** Store templates as versioned JSON data, document the schema beside the artifact, and validate structure/distribution with unit tests. Keep Fuseki execution as a later evidence step because full KG live loading is still pending.

**Tech Stack:** Python 3.11, JSON, pytest, nbformat-compatible notebook JSON.

---

## Task 1: Offline Template Contract Tests

**Files:**
- Create: `tests/unit/test_query_templates.py`

- [ ] Add tests for template count, unique IDs, required fields, difficulty/category distribution, slot placeholder consistency, expected SELECT columns, README existence, and unexecuted validation notebook.
- [ ] Run focused tests and confirm RED because template artifacts do not exist.

## Task 2: Template Library Artifact

**Files:**
- Create: `src/nl2sparql/dataset/templates/templates.json`
- Create: `src/nl2sparql/dataset/templates/README.md`
- Create: `src/nl2sparql/dataset/templates/__init__.py`

- [ ] Add at least 25 templates covering easy/medium/hard and at least 6 categories.
- [ ] Document format, slot types, and validation workflow.
- [ ] Run focused tests and confirm GREEN.
- [ ] Commit with `feat(dataset): add query template library`.

## Task 3: Validation Notebook and Task Evidence

**Files:**
- Create: `notebooks/07_template_validate.ipynb`
- Modify: `docs/tasks/phase-3-dataset/01-query-templates.md`

- [ ] Add an unexecuted notebook that loads templates, fills `example_fill`, and sketches Fuseki execution.
- [ ] Update T3.1 status to `scaffold done; Fuseki execution pending`.
- [ ] Run focused tests, full pytest, and `git diff --check`.
- [ ] Commit with `docs(dataset): record T3.1 template scaffold evidence`.
