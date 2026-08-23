# T4.2 GoogleSQL Entity Linker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an offline-testable, GoogleSQL-native entity linker with safe
content-addressed embeddings, a four-stage cascade, CLI/evaluation workflow, and
honest external scientific gates.

**Architecture:** A deep `nl2sparql.linking.entity` module owns deterministic
dictionary grouping, matching, cache validation, and evaluation behind
`EntityLinker.link(question)`. The encoder is injected; unit tests use a fake and
production commands explicitly load MiniLM.

**Tech Stack:** Python 3.11, dataclasses, NumPy, RapidFuzz, sentence-transformers,
filelock, pytest, Ruff, Jupyter JSON.

**Spec:** `docs/superpowers/specs/2026-08-23-t4-2-google-sql-entity-linker-design.md`

## Global Constraints

- Canonical runtime is GoogleSQL/BigQuery Plan B; no SPARQL/Fuseki output.
- Public interface is `EntityLinker.link(question: str) -> tuple[EntityMatch, ...]`.
- Production encoder is `sentence-transformers/all-MiniLM-L6-v2`; tests never load it.
- No pickle, implicit model download, implicit index rebuild, BigQuery call, or fabricated labels.
- Cache publication is content-addressed, fsynced, process-locked, and manifest-last.
- Scientific acceptance remains pending without exactly 100 independently reviewed rows.
- Every production behavior begins with a focused failing test.

---

### Task 1: Typed contracts and deterministic target documents

**Files:**
- Create: `src/nl2sparql/linking/entity/contracts.py`
- Create: `src/nl2sparql/linking/entity/documents.py`
- Create: `src/nl2sparql/linking/entity/__init__.py`
- Create: `tests/unit/test_entity_documents.py`

**Interfaces:**
- Consumes: `DictionaryArtifacts`, `validate_artifacts`, dictionary JSON files.
- Produces: `EntityTarget`, `EntityAlternative`, `EntityMatch`, `EntityCachePaths`,
  `build_entity_corpus(artifacts) -> EntityCorpus`.

- [x] **Step 1: Write failing corpus/contract tests**

```python
def test_build_entity_corpus_groups_owner_addresses_and_concepts(dictionary_artifacts):
    corpus = build_entity_corpus(dictionary_artifacts)
    owner = corpus.targets_by_id["owner:Binance"]
    assert owner.addresses == ("0x1111111111111111111111111111111111111111",)
    assert corpus.phrase_targets["binance"] == ("owner:Binance",)
    assert corpus.targets_by_id["concept:exchange"].target_kind == "concept"


def test_phrase_collision_is_preserved_as_ordered_ambiguity(dictionary_artifacts):
    corpus = build_entity_corpus(dictionary_artifacts)
    assert corpus.phrase_targets["swap"] == (
        "concept:dex",
        "owner:TrustSwap",
    )
```

- [x] **Step 2: Verify RED**

Run: `uv run pytest -q tests/unit/test_entity_documents.py`
Expected: collection fails because `nl2sparql.linking.entity` does not exist.

- [x] **Step 3: Implement validated immutable contracts and corpus builder**

Create frozen dataclasses with `__post_init__` validation, percent-encoded owner
IDs, SHA-256 document fingerprints, sorted addresses/categories/classes/roles,
phrase-to-ordered-target mappings, and address lookup. Call `validate_artifacts`
before reading derivations and reject missing alias targets or malformed text.

- [x] **Step 4: Verify GREEN and contract edge cases**

Run: `uv run pytest -q tests/unit/test_entity_documents.py tests/unit/test_entity_dictionary_schema.py`
Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add src/nl2sparql/linking/entity tests/unit/test_entity_documents.py
git commit -m "feat(linking): build canonical entity target corpus"
```

### Task 2: Safe content-addressed embedding index

**Files:**
- Create: `src/nl2sparql/linking/entity/index.py`
- Create: `tests/unit/test_entity_index.py`
- Modify: `src/nl2sparql/linking/entity/__init__.py`

**Interfaces:**
- Consumes: ordered `EntityCorpus.targets`, injected `Encoder`, dictionary hashes.
- Produces: `EntityIndex`, `EntityIndexMetadata`, `build_index(...)`, `load_index(...)`.

- [ ] **Step 1: Write failing build/load/tamper tests**

```python
def test_build_and_load_entity_index_uses_content_addressed_generation(tmp_path, corpus):
    paths = EntityCachePaths.from_directory(tmp_path)
    built = build_index(corpus, FakeEncoder(), paths, model_id="fake/model")
    assert built.metadata.matrices_file == f"entity-index-{built.metadata.matrices_sha256}.npz"
    loaded = load_index(paths, corpus, model_id="fake/model")
    np.testing.assert_array_equal(loaded.target_embeddings, built.target_embeddings)


def test_load_rejects_stale_dictionary_hash(tmp_path, corpus, changed_corpus):
    paths = EntityCachePaths.from_directory(tmp_path)
    build_index(corpus, FakeEncoder(), paths, model_id="fake/model")
    with pytest.raises(EntityIndexError, match="dictionary"):
        load_index(paths, changed_corpus, model_id="fake/model")
```

Add tests for digest tamper, non-normalized vectors, traversal, symlink/hardlink,
future-generation output aliases, and failures immediately before/after the
manifest switch.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/unit/test_entity_index.py`
Expected: import fails because `index.py` is absent.

- [ ] **Step 3: Implement build/publication/load validation**

Encode ordered documents once, require finite L2-normalized float32 rows, write a
unique NPZ temporary, fsync, publish immutable generation under `FileLock`, fsync
the directory, and switch canonical JSON manifest last. Strict-load with
`allow_pickle=False` and exact current corpus/model/version binding.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest -q tests/unit/test_entity_index.py tests/unit/test_schema_index.py`
Expected: all entity and existing schema publication tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/linking/entity tests/unit/test_entity_index.py
git commit -m "feat(linking): add durable entity embedding index"
```

### Task 3: Four-stage linker cascade

**Files:**
- Create: `src/nl2sparql/linking/entity/linker.py`
- Create: `src/nl2sparql/linking/entity_linker.py`
- Create: `tests/unit/test_entity_linker.py`
- Modify: `src/nl2sparql/linking/entity/__init__.py`

**Interfaces:**
- Consumes: `EntityCorpus`, `EntityIndex`, injected `Encoder`.
- Produces: `EntityLinker.link(question) -> tuple[EntityMatch, ...]`.

- [ ] **Step 1: Write failing address/exact tests**

```python
def test_link_returns_original_span_and_all_owner_addresses(linker):
    result = linker.link("Transfers from  BINANCE, please")
    assert result[0].span == "BINANCE"
    assert result[0].span_offset == (16, 23)
    assert result[0].target_id == "owner:Binance"
    assert result[0].stage == "exact"


def test_unknown_valid_address_remains_queryable(linker):
    address = "0x1111111111111111111111111111111111111111"
    result = linker.link(f"payments to {address}")
    assert result[0].target_id == f"address:{address}"
    assert result[0].owner is None
```

- [ ] **Step 2: Verify address/exact RED, then implement GREEN**

Run RED: `uv run pytest -q tests/unit/test_entity_linker.py -k 'address or exact'`
Expected: `EntityLinker` import failure.

Implement mapped Unicode token offsets, address recognition, longest
non-overlapping phrase matches, collision ambiguity, immutable results, and input
guards. Re-run the same command; expected pass.

- [ ] **Step 3: Write failing fuzzy/embedding/ambiguity tests**

```python
def test_fuzzy_stage_recovers_unique_misspelling(linker):
    match = linker.link("show binnance withdrawals")[0]
    assert (match.target_id, match.stage) == ("owner:Binance", "fuzzy")


def test_embedding_near_tie_returns_ambiguous(corpus, index):
    linker = EntityLinker(corpus, index, NearTieEncoder())
    match = linker.link("privacy transfer service")[0]
    assert match.stage == "ambiguous"
    assert len(match.alternatives) == 2
```

- [ ] **Step 4: Verify fuzzy/embedding RED, then implement GREEN**

Use one-to-five uncovered token windows, RapidFuzz cutoff `0.85`, semantic cutoff
`0.75`, different-target margin `0.03`, one batch encode, deterministic proposals,
and no-result empty tuple semantics.

Run: `uv run pytest -q tests/unit/test_entity_linker.py`
Expected: all cascade tests pass.

- [ ] **Step 5: Run focused integration and commit**

```bash
uv run pytest -q tests/unit/test_entity_documents.py tests/unit/test_entity_index.py tests/unit/test_entity_linker.py
git add src/nl2sparql/linking/entity src/nl2sparql/linking/entity_linker.py tests/unit/test_entity_linker.py
git commit -m "feat(linking): implement cascading entity linker"
```

### Task 4: Scientific evaluation contracts and metrics

**Files:**
- Create: `src/nl2sparql/linking/entity/evaluate.py`
- Create: `tests/unit/test_entity_linker_evaluate.py`
- Modify: `src/nl2sparql/linking/entity/__init__.py`

**Interfaces:**
- Consumes: `EntityLinker`, 100-row JSONL, valid target IDs and original offsets.
- Produces: `GroundTruthCase`, `EntityEvaluationReport`, `load_ground_truth`,
  `evaluate_linker`.

- [ ] **Step 1: Write failing validation/metric tests**

```python
def test_ground_truth_requires_exactly_one_hundred_rows(tmp_path, corpus):
    path = write_cases(tmp_path / "gt.jsonl", valid_cases(99))
    with pytest.raises(EntityEvaluationError, match="exactly 100"):
        load_ground_truth(path, corpus)


def test_evaluator_computes_top1_and_mention_metrics(fake_linker, cases):
    report = evaluate_linker(fake_linker, cases, model_id="fake/model")
    assert report.named_entity_top1_accuracy == pytest.approx(0.5)
    assert report.mention_f1 == pytest.approx(2 / 3)
    assert report.warm_latency_p50_ms >= 0
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/unit/test_entity_linker_evaluate.py`
Expected: import failure because evaluator is absent.

- [ ] **Step 3: Implement strict loader and aggregate evaluator**

Validate unique IDs/questions, exact question slices at offsets, stable target IDs,
named-entity presence, and exactly 100 rows. Warm once, then compute named top-1,
mention precision/recall/F1, stage counts, p50/p95, hashes, and readiness without
persisting question text.

- [ ] **Step 4: Verify GREEN and commit**

```bash
uv run pytest -q tests/unit/test_entity_linker_evaluate.py
git add src/nl2sparql/linking/entity tests/unit/test_entity_linker_evaluate.py
git commit -m "feat(linking): evaluate entity linker evidence"
```

### Task 5: Production workflow, CLI, and notebook

**Files:**
- Create: `scripts/entity_linker_workflow.py`
- Create: `scripts/14_entity_linker.py`
- Create: `notebooks/12_entity_linker_eval.ipynb`
- Create: `tests/unit/test_entity_linker_workflow.py`

**Interfaces:**
- Consumes: public entity module and explicit filesystem/model arguments.
- Produces: `build-index`, `query`, `evaluate` CLI commands and JSON reports.

- [ ] **Step 1: Write failing offline help/error taxonomy tests**

```python
@pytest.mark.parametrize("args", [["--help"], ["build-index", "--help"], ["query", "--help"], ["evaluate", "--help"]])
def test_cli_help_does_not_load_model(monkeypatch, args):
    monkeypatch.setattr(workflow, "load_encoder", fail_if_called)
    assert workflow.main(args) == 0


def test_evaluate_missing_ground_truth_is_blocked(tmp_path, capsys):
    code = workflow.main(["evaluate", "--ground-truth", str(tmp_path / "missing.jsonl")])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/unit/test_entity_linker_workflow.py`
Expected: workflow import failure.

- [ ] **Step 3: Implement commands and thin numbered wrapper**

Use Click lazy command callbacks, explicit model initialization, strict cache load,
structured `ready`/`blocked`/`failed` output, atomic report publication, path
identity checks covering future generation names, and cause-aware unavailable
taxonomy. Build the notebook as valid JSON that calls production functions only.

- [ ] **Step 4: Verify GREEN and commit**

```bash
uv run pytest -q tests/unit/test_entity_linker_workflow.py
uv run python scripts/14_entity_linker.py --help
uv run python -m json.tool notebooks/12_entity_linker_eval.ipynb
git add scripts notebooks/12_entity_linker_eval.ipynb tests/unit/test_entity_linker_workflow.py
git commit -m "feat(linking): add entity linker workflow"
```

### Task 6: Production index, task migration, and final gates

**Files:**
- Modify: `docs/tasks/phase-4-linking/02-entity-linker.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Create: `src/nl2sparql/linking/cache/entity-index.json`
- Create: `src/nl2sparql/linking/cache/entity-index-<sha256>.npz`
- Create: `src/nl2sparql/linking/cache/entity-index.lock`

**Interfaces:**
- Consumes: real accepted dictionary and cached MiniLM model.
- Produces: strict-loadable production index and honest implementation evidence.

- [ ] **Step 1: Build and strict-load the real index**

Run `uv run python scripts/14_entity_linker.py build-index --local-files-only`, then
run representative exact, fuzzy, concept, and address queries. Record target count,
dimension, hashes, and warm smoke latency. Do not run or fabricate the absent
100-row evaluation.

- [ ] **Step 2: Migrate task and decision documentation**

Rewrite T4.2 to GoogleSQL terminology, check only implementation acceptance, record
commands/hashes/counts, and leave manual Top-1/latency boxes pending. Add a dated
decision-log entry for the recognition/resolution seam and safe cache.

- [ ] **Step 3: Run final focused and repository gates**

```bash
uv run pytest -q tests/unit/test_entity_documents.py tests/unit/test_entity_index.py tests/unit/test_entity_linker.py tests/unit/test_entity_linker_evaluate.py tests/unit/test_entity_linker_workflow.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m json.tool notebooks/12_entity_linker_eval.ipynb
git diff --check
```

- [ ] **Step 4: Final self-review, commit, and push**

Inspect every diff against the spec, verify no credential/model cache leakage, then:

```bash
git add docs src/nl2sparql/linking/cache
git commit -m "docs(linking): complete T4.2 implementation checkpoint"
git push -u origin feat/t4-2-google-sql-entity-linker
```
