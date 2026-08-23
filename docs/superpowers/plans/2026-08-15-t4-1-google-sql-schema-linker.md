# T4.1 GoogleSQL Schema Linker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed hybrid linker that ranks Plan B analytical relations and fields from natural-language Ethereum questions.

**Architecture:** A deep `linking/schema/` package separates catalog-document construction, safe index lifecycle, retrieval, and evaluation. A small `schema_linker.py` facade preserves the task-level import seam, while a numbered Click workflow owns explicit model loading and artifact publication.

**Tech Stack:** Python 3.11, dataclasses, NumPy, sentence-transformers MiniLM, JSON/NPZ, Click, pytest, Ruff.

## Global Constraints

- Canonical target is the committed GoogleSQL analytical catalog; no SPARQL/Fuseki runtime path.
- Production model ID is `sentence-transformers/all-MiniLM-L6-v2`.
- Default score is `0.65 * semantic_score + 0.35 * lexical_score`.
- Cache uses JSON plus NPZ loaded with `allow_pickle=False`; no pickle artifact.
- Cache identity binds catalog SHA-256, model ID, document version, weights, element order, matrix digest, and schema version.
- Offline unit tests inject a deterministic encoder and never download a model or initialize credentials.
- The 50-row manual ground truth, Recall@10 ≥0.80, and warm latency <100 ms remain pending unless real evidence exists.
- Public functions use Google-style docstrings and type hints; code comments are English.
- Scaffold/build commands never overwrite external ground-truth input or silently rebuild a stale cache.

---

## File map

- Create `src/nl2sparql/linking/schema/contracts.py`: domain types, validation, encoder protocol, cache paths, errors.
- Create `src/nl2sparql/linking/schema/documents.py`: deterministic Plan B relation/field documents and synonym loading.
- Create `src/nl2sparql/linking/schema/synonyms.json`: reviewed lexical aliases grouped by canonical tokens.
- Create `src/nl2sparql/linking/schema/index.py`: explicit index build, atomic two-file publication, strict loading.
- Create `src/nl2sparql/linking/schema/linker.py`: hybrid scoring and typed rankings.
- Create `src/nl2sparql/linking/schema/evaluate.py`: ground-truth validation, Recall/MRR/latency metrics, reports.
- Create `src/nl2sparql/linking/schema/__init__.py`: small public package surface.
- Create `src/nl2sparql/linking/schema_linker.py`: compatibility facade for T4.1 consumers.
- Modify `src/nl2sparql/linking/__init__.py`: export the stable linker types.
- Create `scripts/schema_linker_workflow.py` and `scripts/13_schema_linker.py`: build/query/evaluate CLI.
- Create `tests/unit/test_schema_documents.py`, `test_schema_index.py`, `test_schema_linker.py`, and `test_schema_linker_evaluate.py`.
- Create `notebooks/11_schema_linker_eval.ipynb`: thin production-API evaluation notebook.
- Modify `docs/tasks/phase-4-linking/01-schema-linker.md` and `docs/memory/05-DECISION_LOG.md` after evidence exists.

### Task 1: Typed contracts and deterministic catalog documents

**Files:**
- Create: `src/nl2sparql/linking/schema/contracts.py`
- Create: `src/nl2sparql/linking/schema/documents.py`
- Create: `src/nl2sparql/linking/schema/synonyms.json`
- Create: `src/nl2sparql/linking/schema/__init__.py`
- Test: `tests/unit/test_schema_documents.py`

**Interfaces:**
- Consumes: `load_catalog(path: Path) -> dict[str, object]` from `nl2sparql.sql.schema`.
- Produces: `SchemaElement(element_id, kind, document, document_sha256)`, `ScoreWeights`, `SchemaCachePaths.from_directory(path)`, `Encoder.encode(texts, normalize_embeddings=True)`, `build_schema_elements(catalog, synonyms) -> tuple[SchemaElement, ...]`, and `load_synonyms(path) -> dict[str, tuple[str, ...]]`.

- [x] **Step 1: Write failing contract/document tests**

  Cover the six accepted relation IDs, every `relation.field` ID, deterministic
  byte-identical documents, semantic mapping inclusion, `hasFrom`/sender and
  `hasTo`/recipient synonyms, malformed synonym JSON, duplicate element IDs, and
  `ScoreWeights` rejecting boolean/non-finite/negative/non-unit values.

```python
def test_documents_keep_directional_role_terms(catalog, synonyms):
    elements = {row.element_id: row for row in build_schema_elements(catalog, synonyms)}
    assert "sender" in elements["transaction_facts.from_address"].document
    assert "recipient" in elements["transaction_facts.to_address"].document
    assert elements["transaction_facts.from_address"].kind == "field"
```

- [x] **Step 2: Run the document test and verify RED**

  Run `UV_CACHE_DIR=.uv-cache uv run pytest -q tests/unit/test_schema_documents.py`.
  Expected: collection fails because `nl2sparql.linking.schema` does not exist.

- [x] **Step 3: Implement strict types, synonyms, and document builder**

  Validate non-empty/control-free IDs and documents in frozen dataclasses. Parse
  the synonym file as `dict[str, list[str]]`, normalize with Unicode NFKC and
  case-folding, reject duplicate aliases across incompatible canonical groups,
  and return sorted tuples. Traverse `analytical_relations`, `semantic_mappings`,
  and `competency_questions`; resolve semantic IDs to targeted relation/field
  documents and reject unknown targets before producing sorted elements.

- [x] **Step 4: Run focused tests, Ruff, and format**

  Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest -q tests/unit/test_schema_documents.py
UV_CACHE_DIR=.uv-cache uv run ruff check src/nl2sparql/linking/schema tests/unit/test_schema_documents.py
UV_CACHE_DIR=.uv-cache uv run ruff format --check src/nl2sparql/linking/schema tests/unit/test_schema_documents.py
```

  Expected: all commands exit zero without model/network access.

- [x] **Step 5: Commit the document seam**

  Stage the four package files and document tests, then commit
  `feat(linking): build Plan B schema documents`.

### Task 2: Safe, fingerprinted index lifecycle

**Files:**
- Create: `src/nl2sparql/linking/schema/index.py`
- Test: `tests/unit/test_schema_index.py`

**Interfaces:**
- Consumes: `SchemaElement`, `SchemaCachePaths`, `ScoreWeights`, and injected `Encoder` from Task 1.
- Produces: `SchemaIndex(metadata, relation_embeddings, field_embeddings)`, `build_index(elements, encoder, model_id, catalog_bytes, paths, weights) -> SchemaIndex`, and mandatory-current-document `load_index(paths, expected_catalog_sha256, expected_model_id, expected_document_version, expected_elements) -> SchemaIndex`.

- [x] **Step 1: Write failing index tests with a deterministic encoder**

```python
class FakeEncoder:
    def encode(self, texts, *, normalize_embeddings=True):
        rows = np.asarray([[len(text), text.count("address"), 1.0] for text in texts])
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)
```

  Test deterministic element ordering, float32 normalized matrices, JSON/NPZ
  creation, JSON payload hash, NPZ hash, stale catalog/model/document rejection,
  truncated/tampered NPZ rejection, non-finite/wrong-shaped encoder output,
  unique temporary siblings, and lock-protected atomic replacement. Assert that
  a failed rebuild leaves the previously accepted pair readable.

- [x] **Step 2: Run the index test and verify RED**

  Run `UV_CACHE_DIR=.uv-cache uv run pytest -q tests/unit/test_schema_index.py`.
  Expected: import failure for the absent `index` module.

- [x] **Step 3: Implement build/publication/load validation**

  Encode relation and field document lists separately, require one 2-D finite
  unit-normalized vector per element with a shared positive dimension, and cast
  to float32. Write compressed NPZ to a unique sibling, flush/fsync, compute its
  SHA-256, then write canonical JSON manifest to another sibling. Under a lock,
  publish an immutable content-addressed NPZ generation first and switch the
  manifest pointer last. Retain prior generations. Loader reads the manifest under
  the same lock, rejects unsafe referenced names/aliases, verifies its self-hash
  and exact current ordered document fingerprints, verifies NPZ bytes, loads with
  `allow_pickle=False`, and validates shapes/order/norms.

- [x] **Step 4: Run focused index gates**

  Run the index test, document test, Ruff, format, and `git diff --check` for the
  new package. Expected: every gate exits zero.

- [x] **Step 5: Commit index lifecycle**

  Commit `feat(linking): add fingerprinted schema index` with the module and its
  tests only.

### Task 3: Hybrid relation/field retrieval

**Files:**
- Create: `src/nl2sparql/linking/schema/linker.py`
- Create: `src/nl2sparql/linking/schema_linker.py`
- Modify: `src/nl2sparql/linking/schema/__init__.py`
- Modify: `src/nl2sparql/linking/__init__.py`
- Test: `tests/unit/test_schema_linker.py`

**Interfaces:**
- Consumes: validated `SchemaIndex`, `Encoder`, synonyms, and `ScoreWeights`.
- Produces: `SchemaMatch`, `LinkResult`, `SchemaLinker(index, encoder, synonyms)`, and `SchemaLinker.link(question: str, top_k: int = 10) -> LinkResult`.

- [x] **Step 1: Write failing retrieval tests**

  Use a hand-sized fake index and encoder to prove exact output types, descending
  scores, stable ID tie-breaks, relation/field pool separation, top-k bounds,
  empty/control/non-string rejection, directional sender/recipient ranking,
  amount/value synonyms, ambiguous gas fields, and no mutation of cached arrays.

```python
def test_directional_terms_rank_correct_address_fields(linker):
    sent = linker.link("transactions sent by an exchange", top_k=3)
    received = linker.link("transactions received by an exchange", top_k=3)
    assert sent.fields[0].element_id == "transaction_facts.from_address"
    assert received.fields[0].element_id == "transaction_facts.to_address"
```

- [x] **Step 2: Run retrieval tests and verify RED**

  Run `UV_CACHE_DIR=.uv-cache uv run pytest -q tests/unit/test_schema_linker.py`.
  Expected: missing linker API.

- [x] **Step 3: Implement lexical and semantic fusion**

  Normalize the question once, expand reviewed synonym groups without substring
  matching, and compute bounded lexical overlap for every document. Encode one
  question vector, validate dimension/norm, multiply against relation and field
  matrices, combine with manifest weights, and use `(-score, element_id)` as the
  stable ordering key. Return immutable tuples and expose only stable symbols
  through both package and facade.

- [x] **Step 4: Run focused retrieval gates**

  Run document/index/linker tests plus Ruff and format checks. Expected: all pass
  using only fake encoders.

- [x] **Step 5: Commit retrieval API**

  Commit `feat(linking): rank analytical schema elements`.

### Task 4: Ground-truth evaluation, CLI, and notebook

**Files:**
- Create: `src/nl2sparql/linking/schema/evaluate.py`
- Create: `scripts/schema_linker_workflow.py`
- Create: `scripts/13_schema_linker.py`
- Create: `tests/unit/test_schema_linker_evaluate.py`
- Create: `notebooks/11_schema_linker_eval.ipynb`

**Interfaces:**
- Consumes: `SchemaLinker`, catalog elements, explicit ground-truth JSONL, cache paths, and an encoder factory.
- Produces: `GroundTruthCase`, `EvaluationReport`, `load_ground_truth(path, valid_elements, expected_count=50)`, `evaluate_linker(linker, cases, relation_k=5)` with fixed field Recall@5/@10 and full-pool MRR, and Click commands `build-index`, `query`, `evaluate`.

- [x] **Step 1: Write failing evaluator and CLI tests**

  Test exact 50 rows, unique IDs/NL, unknown/empty gold fields, relation/field
  consistency, known Recall@K/MRR vectors, warm-up exclusion, p50/p95 calculation,
  report provenance, CLI help without model initialization, missing ground truth
  returning structured `blocked`, invalid cache returning `failed`, and encoder
  factory invoked only by model-requiring commands.

- [x] **Step 2: Run evaluator tests and verify RED**

  Run `UV_CACHE_DIR=.uv-cache uv run pytest -q tests/unit/test_schema_linker_evaluate.py`.
  Expected: missing evaluator and CLI modules.

- [x] **Step 3: Implement validation, metrics, reports, and commands**

  Parse JSONL with line-aware errors and exact keys. Compute micro recall from
  set intersections, reciprocal rank from the first relevant field, and latency
  percentiles from per-case `perf_counter` measurements after one warm-up. Emit
  canonical atomic JSON reports containing schema version, status, UTC, git SHA,
  catalog/cache/ground-truth digests, model ID, weights, metrics, and report hash.
  `build-index` is the only cache writer. Catch missing file/model/network as
  `blocked`; contract/index/evaluation failures as `failed`; always exit nonzero
  on either status.

- [x] **Step 4: Create and validate the thin notebook**

  Add environment/version, artifact-status, metric table, top-error inspection,
  and manual-gate Markdown cells. Code cells import the production evaluator and
  do not build a second linker. Validate JSON with
  `UV_CACHE_DIR=.uv-cache uv run python -m json.tool notebooks/11_schema_linker_eval.ipynb`.

- [x] **Step 5: Run focused workflow gates**

  Run all four `test_schema_*.py` modules, CLI `--help`, Ruff, format, notebook
  JSON validation, and `git diff --check`. Confirm no model download occurs.

- [x] **Step 6: Commit evaluation workflow**

  Commit `feat(linking): evaluate Plan B schema linker`.

### Task 5: Optional real-model evidence, task migration, and repository verification

**Files:**
- Create when evidence exists: `src/nl2sparql/linking/cache/schema-index.json`
- Create when evidence exists: `src/nl2sparql/linking/cache/schema-index-<sha256>.npz`
- Modify: `docs/tasks/phase-4-linking/01-schema-linker.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/superpowers/specs/2026-08-15-t4-1-google-sql-schema-linker-design.md` only if implementation reveals a contradiction.
- Modify: this plan to mark evidenced steps.

**Interfaces:**
- Consumes: completed CLI and, when available, cached MiniLM plus independently reviewed `data/eval/schema_link_groundtruth.jsonl`.
- Produces: honest implementation status, optional real index/evaluation report, and repository-wide verification evidence.

- [x] **Step 1: Attempt explicit real index build without weakening behavior**

  Run `build-index` with the production model ID. If the model is unavailable,
  preserve the structured blocked report and do not commit fake vectors. If it
  succeeds, run a second load and measure validated cache load time.

- [x] **Step 2: Run real evaluation only with accepted ground truth**

  If and only if the exact reviewed 50-row file exists, run `evaluate`, inspect
  Recall@10 and warm p50/p95, and commit the hash-bound report. Otherwise leave
  the scientific recall/latency boxes unchecked and record the external gate.

- [x] **Step 3: Migrate the T4.1 task and decision log**

  Replace ontology-property/Fuseki acceptance with the Plan B relation/field
  contract, list implementation artifacts and verification counts, mark only
  evidenced implementation boxes complete, and record manual/model blockers
  without calling template-derived fixtures independent annotation.

- [x] **Step 4: Run fresh repository verification**

  Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest -q
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run ruff format --check .
UV_CACHE_DIR=.uv-cache uv run python -m json.tool notebooks/11_schema_linker_eval.ipynb
git diff --check
git status --short --branch
```

  Read every exit code and test count before updating evidence.

- [ ] **Step 5: Request focused code review and fix all Critical/Important findings**

  Review the complete diff against the approved design and task acceptance.
  Re-run affected focused tests after each correction and repeat review until
  merge-ready.

  The earlier approval was superseded by the final whole-branch review of
  `90bca619445c15aee9a7782ab50fcb3c361012e2`, which found 9 Important and 4
  Minor issues. The remediation below is complete, but controller scoped
  re-review remains pending before push.

- [x] **Step 6: Commit and push the T4.1 checkpoint**

  Commit `docs(linking): complete T4.1 implementation checkpoint`, push
  `wip/continuous-backlog`, and verify the remote branch SHA with `git ls-remote`.

### Final review remediation (2026-08-15)

- [x] Bind every load to current ordered element IDs/document hashes and pass
  fresh elements through both query/evaluate.
- [x] Reject normalized-key/phrase synonym collisions and tokenless phrases
  before encoder initialization.
- [x] Emit fixed field Recall@5/@10 and compute MRR over the complete field pool;
  correct first-extra-row line context and evaluator docstrings.
- [x] Publish content-addressed matrix generations with manifest switch-last,
  deterministic crash tests, retained prior generations, and safe no-alias load.
- [x] Split explicit model dependency blockers from programming failures; rebuild
  and strict-load the real MiniLM schema-v2 artifact.
- [ ] Independent 50-row ground truth, scientific Recall, and warm latency report
  remain external and were not generated by this remediation.
