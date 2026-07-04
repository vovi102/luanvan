# T2.5 SHACL Validation Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local SHACL validation scaffold that can validate fixture RDF graphs and later run against the full KG artifact.

**Architecture:** Add ontology-aligned SHACL Core shapes under `kg/validation`, a small Python runner around `pyshacl.validate`, and fixture-based unit tests. Keep full KG validation out of tests and document it as pending live evidence.

**Tech Stack:** Python 3.11, RDFLib, pySHACL, pytest, project-local `uv`.

---

## Task 1: SHACL Shapes Static Contract

**Files:**
- Create: `src/nl2sparql/kg/validation/shapes.ttl`
- Create: `tests/unit/test_shacl_validation.py`

- [ ] Write failing tests that parse `shapes.ttl`, assert at least six `sh:NodeShape` resources, and assert key predicates `:hasFrom`, `:hasTo`, `:hasValue`, `:emittedInTransaction`, `:transferredAmount`, `:hasLabel`, and `:hasOwner`.
- [ ] Run `uv run pytest tests/unit/test_shacl_validation.py -q`; expect fail because `shapes.ttl` does not exist.
- [ ] Add SHACL Core shapes for Transaction, Block, Account, ExchangeAccount, TokenTransfer, and TokenContract.
- [ ] Run focused tests; expect pass.
- [ ] Commit with `feat(kg): add SHACL shape scaffold`.

## Task 2: Local Runner and Conforming Fixture

**Files:**
- Create: `src/nl2sparql/kg/validation/run_shacl.py`
- Create: `tests/fixtures/shacl/conforming.ttl`
- Modify: `tests/unit/test_shacl_validation.py`

- [ ] Write failing tests for `parse_rdf_graph()` and `run_shacl_validation()` using `conforming.ttl`.
- [ ] Run focused tests; expect import/function failure.
- [ ] Implement `ShaclValidationResult`, `parse_rdf_graph()`, and `run_shacl_validation()` with report serialization.
- [ ] Run focused tests; expect pass.
- [ ] Commit with `feat(kg): add local SHACL validation runner`.

## Task 3: Violation Summary and CLI Guardrails

**Files:**
- Create: `tests/fixtures/shacl/violating.ttl`
- Modify: `src/nl2sparql/kg/validation/run_shacl.py`
- Modify: `tests/unit/test_shacl_validation.py`

- [ ] Write failing tests for non-conforming validation, grouped violation summary, markdown summary writing, CLI return code `1`, and `--allow-nonconform` return code `0`.
- [ ] Run focused tests; expect missing summary/CLI failures.
- [ ] Implement `ViolationSummary`, `summarize_validation_report()`, `write_violations_summary()`, `parse_args()`, and `main()`.
- [ ] Run focused tests and CLI help smoke.
- [ ] Commit with `feat(kg): summarize SHACL validation reports`.

## Task 4: Documentation Evidence and Final Verification

**Files:**
- Modify: `docs/tasks/phase-2-kg/05-shacl-validation.md`

- [ ] Update T2.5 status to `scaffold done; full KG validation pending`.
- [ ] Add local automation scaffold checkboxes and evidence commands.
- [ ] Keep full acceptance criteria unchecked.
- [ ] Run `uv run pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Commit with `docs(kg): record T2.5 SHACL scaffold evidence`.
