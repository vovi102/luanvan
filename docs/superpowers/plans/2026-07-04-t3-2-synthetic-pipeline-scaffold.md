# T3.2 Synthetic Pipeline Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic offline Stage A generation scaffold.

**Architecture:** Render T3.1 templates with example fills first, then later replace verification mode with Fuseki execution when full KG is live.

**Tech Stack:** Python 3.11, JSONL, pytest, project-local `uv`.

---

## Tasks

- [ ] Write failing tests for generator load/render/write/stats behavior.
- [ ] Implement `src/nl2sparql/dataset/generate.py` and CLI.
- [ ] Add unexecuted notebook `notebooks/08_generate_synthetic.ipynb`.
- [ ] Update T3.2 task evidence.
- [ ] Run focused tests, full tests, and `git diff --check`.
