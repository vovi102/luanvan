# T3.3 GoogleSQL Paraphrasing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce faithful Stage B and diverse Stage C English questions from the 1,000 verified GoogleSQL records through a bounded, resumable two-model pipeline.

**Architecture:** Pure prompt/contracts/quality modules validate data without network access. An injected async completion client handles OpenRouter calls, while a runner owns retries, checkpoints, actual-cost accounting, and stable ordering; artifact publication is a separate atomic boundary.

**Tech Stack:** Python 3.11, Pydantic 2, `openai` 1.x `AsyncOpenAI`, asyncio, Click 8, JSONL/CSV, pytest 8, Ruff.

## Global Constraints

- Source artifact SHA-256 is `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`.
- Stage B model is `openai/gpt-4.1-mini`; Stage C model is `google/gemini-2.5-flash`.
- Stage B count is 1,000; Stage C count is exactly 3,000.
- Total actual API cost cannot exceed $30; missing `usage.cost` fails closed.
- Default concurrency is 10 and retry attempts are capped at 3.
- Every final question passes fact-anchor validation; Stage C mean normalized edit distance exceeds 0.30.

---

### Task 1: Prompt, response, and quality contracts

**Files:**
- Create: `src/nl2sparql/dataset/paraphrase/contracts.py`
- Create: `src/nl2sparql/dataset/paraphrase/prompts.py`
- Create: `src/nl2sparql/dataset/paraphrase/quality.py`
- Create: `src/nl2sparql/dataset/paraphrase/__init__.py`
- Create: `tests/unit/test_paraphrase_contracts.py`

**Interfaces:**
- Produces `StageBResponse`, `StageCResponse`, `build_preserved_facts(record)`,
  `build_stage_b_request(record, entity_index)`, `build_stage_c_request(record)`,
  `validate_question_anchors(question, record, entity_index)`, and
  `normalized_levenshtein(left, right)`.

- [x] Write failing tests for strict response fields, canonical fact order,
  SQL-specific prompts, prompt SHA-256, entity aliases, numeric/date/token
  anchors, duplicate variants, code fences, and known edit-distance values.
- [x] Confirm RED on the missing paraphrase package.
- [x] Implement Pydantic schemas, immutable prompt dataclasses, dictionary-aware
  context, anchor normalization, and dynamic-programming Levenshtein distance.
- [x] Run focused tests, Ruff, format, and whitespace checks.

### Task 2: Resumable bounded runner

**Files:**
- Create: `src/nl2sparql/dataset/paraphrase/runner.py`
- Create: `tests/unit/test_paraphrase_runner.py`

**Interfaces:**
- Consumes an async `CompletionClient.complete(request) -> CompletionResult`.
- Produces `run_stage_b(...)`, `run_stage_c(...)`, `load_checkpoint(path)`,
  `CostLedger`, `StageRunReport`, and canonical checkpoint rows.

- [x] Write async fake-client tests for stable output ordering, resume skips,
  checkpoint conflicts, 429/5xx retry with injected sleeper, non-retryable
  schema failures, three-attempt limit, actual token/cost capture, missing-cost
  rejection, and $30 reservation/actual gates.
- [x] Confirm RED before runner implementation.
- [x] Implement bounded asyncio scheduling, retry classification, append-only
  canonical checkpoints, prompt/source/model keys, and cost ledger.
- [x] Run contract/runner tests GREEN.

### Task 3: OpenRouter adapter and atomic artifacts

**Files:**
- Create: `src/nl2sparql/dataset/paraphrase/openrouter.py`
- Create: `src/nl2sparql/dataset/paraphrase/artifacts.py`
- Create: `scripts/10_paraphrase_stage_a.py`
- Create: `tests/unit/test_paraphrase_artifacts.py`

**Interfaces:**
- `OpenRouterClient.from_env()` constructs `AsyncOpenAI` only in live mode.
- CLI modes: `--validate-only`, `--stage-b`, `--stage-c`, and `--all`.
- Artifact writer emits Stage B/C JSONL, cost CSV, config JSON, and quality stats
  only after full validation.

- [x] Write fake-SDK tests for strict `response_format`, pinned models,
  `require_parameters`, usage cost extraction, and credential failure without
  leaking key material.
- [x] Write CLI/artifact tests for validate-only no-client behavior, exact
  1,000/3,000 schemas, normalized uniqueness/distance gates, atomic failure,
  and deterministic audit sample IDs.
- [x] Implement the adapter, artifact builders/writers, and Click CLI.
- [x] Run focused tests.

### Task 4: Documentation, live run, and closure

**Files:**
- Rewrite: `docs/tasks/phase-3-dataset/03-paraphrasing.md`
- Create: `notebooks/09_paraphrase.ipynb`
- Generate: `data/dataset/raw/synthetic-stage-b.jsonl`
- Generate: `data/dataset/raw/synthetic-stage-c.jsonl`
- Generate: `data/dataset/raw/cost_log.csv`
- Generate: `data/dataset/raw/paraphrase-config.json`
- Modify: `docs/memory/05-DECISION_LOG.md`

- [x] Migrate all active wording/schema examples from SPARQL to GoogleSQL and
  document the two-model, structured-output, resume, and cost contracts.
- [x] Run validate-only against the accepted Stage A artifact and record source
  hash/count/caps.
- [x] If `OPENROUTER_API_KEY` is present, run Stage B then Stage C with resume;
  otherwise record the external credential gate without weakening acceptance.
- [ ] Validate output counts, actual cost, anchors, unique normalized text, mean
  edit distance, and deterministic manual sample manifests.
- [x] Run full pytest, Ruff, format, and diff checks; because live artifacts do
  not exist, record the 50/100 manual audits as credential-gated and
  commit completed evidence or an honest credential-gated implementation
  checkpoint with a clean worktree.
