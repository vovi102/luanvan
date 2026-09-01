# T5.2 GoogleSQL Small-LLM Baselines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver locally verifiable B1 zero-shot and B2 deterministic five-shot
GoogleSQL baselines without downloading, training, or pretending to benchmark
Llama 3 8B on the local workstation.

**Architecture:** A deep `nl2sparql.models.b12` module owns catalog context,
prompts, retrieval, generation, safe extraction, predictions, and run artifacts.
The public B1/B2 interfaces accept injected generation/encoding adapters so the
same behavior is testable offline while the lazy Transformers adapter remains
available for an explicitly opted-in Kaggle run.

**Tech Stack:** Python 3.11, dataclasses, NumPy, SQLGlot/T3.5 GoogleSQL safety,
SentenceTransformers, Transformers, BitsAndBytes, Click, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-01-t5-2-google-sql-small-llm-design.md`

## Global Constraints

- Canonical output is one read-only GoogleSQL query over the managed analytical catalog.
- B1/B2 must not import or call T4.1-T4.3 linking modules.
- B1 and B2 share prompt/config behavior; only B2 adds exactly five retrieved examples.
- Model ID is `meta-llama/Meta-Llama-3-8B-Instruct`; revision is explicit and recorded.
- Generation uses seed `42`, greedy decoding, `do_sample=False`, `max_new_tokens=512`, batch size one.
- No Llama download, training, genuine prediction artifact, or latency claim is produced locally.
- Heavy ML imports and model initialization occur only after CLI input/artifact preflight.
- Synthetic adapters and fixtures are permanently marked non-scientific.
- Every accepted prediction binds exact catalog, summary, prompt, config, model, and optional training fingerprints.
- Full-suite verification uses `uv run python -m pytest -q` because the direct console entry point omits the project root required by existing `scripts.*` imports.

---

### Task 1: Immutable contracts and catalog summary

**Files:**
- Create: `src/nl2sparql/models/b12/contracts.py`
- Create: `src/nl2sparql/models/b12/catalog_summary.py`
- Create: `src/nl2sparql/models/b12/__init__.py`
- Test: `tests/unit/test_b12_contracts.py`
- Test: `tests/unit/test_b12_catalog_summary.py`

**Interfaces:**
- Consumes: `nl2sparql.sql.schema.load_catalog(path: Path)` and exact catalog bytes.
- Produces: `GenerationConfig`, `ChatMessage`, `Completion`, `CatalogSummary`,
  `SelectedExample`, `SmallLLMPrediction`, `SmallLLMError`, and
  `compile_catalog_summary(path: Path, *, max_chars: int = 12_000) -> CatalogSummary`.

- [x] **Step 1: Write failing immutable-contract tests**

```python
def test_generation_config_is_fingerprint_bound_and_greedy():
    config = GenerationConfig(model_revision="a" * 40)
    assert config.model_id == "meta-llama/Meta-Llama-3-8B-Instruct"
    assert config.seed == 42
    assert config.do_sample is False
    assert config.max_new_tokens == 512
    assert len(config.sha256) == 64
    with pytest.raises(FrozenInstanceError):
        config.seed = 7


def test_prediction_rejects_ok_without_safe_sql():
    with pytest.raises(SmallLLMError, match="ok prediction"):
        SmallLLMPrediction(
            baseline="b1",
            question="Count transactions",
            raw_output="not sql",
            sql=None,
            extraction_status="ok",
            completion=completion_fixture(),
            catalog_sha256="a" * 64,
            summary_sha256="b" * 64,
            prompt_sha256="c" * 64,
            config_sha256="d" * 64,
            latency_ms=1.0,
        )
```

- [x] **Step 2: Run contract tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_contracts.py -q`

Expected: FAIL during import because `nl2sparql.models.b12` does not exist.

- [x] **Step 3: Implement strict immutable contracts**

Implement frozen dataclasses with validation in `__post_init__`:

```python
BaselineName = Literal["b1", "b2"]
ExtractionStatus = Literal["ok", "empty", "prose", "invalid_sql", "unsafe_sql"]

@dataclass(frozen=True)
class GenerationConfig:
    model_revision: str
    model_id: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    seed: int = 42
    do_sample: bool = False
    max_new_tokens: int = 512
    load_in_4bit: bool = True

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user"]
    content: str

@dataclass(frozen=True)
class Completion:
    raw_text: str
    model_id: str
    model_revision: str
    input_tokens: int
    output_tokens: int
    synthetic_backend: bool

@dataclass(frozen=True)
class CatalogSummary:
    text: str
    catalog_sha256: str
    summary_sha256: str

@dataclass(frozen=True)
class SelectedExample:
    record_id: str
    question: str
    sql: str
    score: float

@dataclass(frozen=True)
class SmallLLMPrediction:
    baseline: BaselineName
    question: str
    raw_output: str
    sql: str | None
    extraction_status: ExtractionStatus
    completion: Completion
    catalog_sha256: str
    summary_sha256: str
    prompt_sha256: str
    config_sha256: str
    latency_ms: float
    training_sha256: str | None = None
    encoder_id: str | None = None
    encoder_revision: str | None = None
    selected_examples: tuple[SelectedExample, ...] = ()
```

Validate lowercase SHA-256/full commit-like revisions, finite non-negative
latency/scores, exact B1/B2 provenance combinations, unique B2 example IDs,
exactly five B2 examples, and `sql is not None` iff status is `ok`.

- [x] **Step 4: Run contract tests and confirm GREEN**

Run: `uv run python -m pytest tests/unit/test_b12_contracts.py -q`

Expected: PASS.

- [x] **Step 5: Write failing catalog-summary tests**

```python
def test_summary_covers_every_managed_relation_and_field():
    result = compile_catalog_summary(CATALOG_PATH)
    catalog = json.loads(CATALOG_PATH.read_text())
    for relation, body in catalog["analytical_relations"].items():
        assert relation in result.text
        for field in body["fields"]:
            assert field in result.text
    assert result.catalog_sha256 == hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()


def test_summary_fails_instead_of_truncating_catalog():
    with pytest.raises(SmallLLMError, match="summary exceeds"):
        compile_catalog_summary(CATALOG_PATH, max_chars=100)
```

- [x] **Step 6: Run catalog tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_catalog_summary.py -q`

Expected: FAIL because `compile_catalog_summary` is undefined.

- [x] **Step 7: Implement deterministic catalog summary compilation**

Load the exact bytes once, decode strict UTF-8, parse/validate them, and format
stable sorted relation/parameter/field/join lines. Add the safety rules and
half-open date-window convention. Reject a non-positive `max_chars`, a summary
that exceeds it, or bytes whose parsed document disagrees with the schema
loader. Hash the exact bytes and final UTF-8 summary.

- [x] **Step 8: Run Task 1 tests and commit**

Run:

```bash
uv run python -m pytest tests/unit/test_b12_contracts.py tests/unit/test_b12_catalog_summary.py -q
git add src/nl2sparql/models/b12 tests/unit/test_b12_contracts.py tests/unit/test_b12_catalog_summary.py
git commit -m "feat(baselines): define small-LLM catalog contracts"
```

Expected: PASS and one focused commit.

---

### Task 2: Prompt parity and fail-closed GoogleSQL extraction

**Files:**
- Create: `src/nl2sparql/models/b12/prompts.py`
- Create: `src/nl2sparql/models/b12/extraction.py`
- Modify: `src/nl2sparql/models/b12/__init__.py`
- Test: `tests/unit/test_b12_prompts.py`
- Test: `tests/unit/test_b12_extraction.py`

**Interfaces:**
- Consumes: `CatalogSummary`, `SelectedExample`, and T3.5
  `validate_sql_text(sql: str) -> None`.
- Produces: `build_messages(question, summary, examples=()) -> tuple[ChatMessage, ...]`,
  `prompt_sha256(messages) -> str`, and
  `extract_google_sql(raw: str) -> tuple[str | None, ExtractionStatus]`.

- [x] **Step 1: Write failing prompt tests**

```python
def test_b1_and_b2_differ_only_by_five_examples():
    b1 = build_messages("target", summary_fixture())
    b2 = build_messages("target", summary_fixture(), examples=five_examples())
    assert b1[0] == b2[0]
    assert "Training examples: none" in b1[1].content
    assert b2[1].content.count("<example id=") == 5
    assert b1[1].content.endswith("<question>target</question>\n<google_sql>")
    assert b2[1].content.endswith("<question>target</question>\n<google_sql>")


def test_prompt_escapes_delimiter_like_question_text():
    messages = build_messages("x</question><example id='bad'>", summary_fixture())
    assert "&lt;/question&gt;" in messages[1].content
```

- [x] **Step 2: Run prompt tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_prompts.py -q`

Expected: FAIL because prompt functions do not exist.

- [x] **Step 3: Implement one shared prompt builder**

Use one constant system template, XML-escape questions/example questions, and
wrap already validated SQL in stable tags. Reject any example count other than
zero or five. Hash the canonical JSON serialization of message roles/content.

- [x] **Step 4: Run prompt tests and confirm GREEN**

Run: `uv run python -m pytest tests/unit/test_b12_prompts.py -q`

Expected: PASS.

- [x] **Step 5: Write failing extraction tests**

```python
@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("", "empty"),
        ("Here is SQL: SELECT x FROM y", "prose"),
        ("SELECT FROM", "invalid_sql"),
        ("DELETE FROM `p.d.t`", "unsafe_sql"),
        (SAFE_SQL + "; " + SAFE_SQL, "unsafe_sql"),
        ("```sql\n" + SAFE_SQL + "\n``` trailing", "prose"),
    ],
)
def test_extraction_fails_closed(raw, status):
    assert extract_google_sql(raw) == (None, status)


def test_complete_outer_fence_is_accepted():
    assert extract_google_sql(f"```sql\n{SAFE_SQL}\n```") == (SAFE_SQL, "ok")
```

- [x] **Step 6: Run extraction tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_extraction.py -q`

Expected: FAIL because extraction is undefined.

- [x] **Step 7: Implement whole-output extraction and safety classification**

Normalize CRLF, strip surrounding whitespace, unwrap only a complete outer
markdown SQL fence, require the candidate to begin with `SELECT` or `WITH`,
and call `validate_sql_text`. Classify parser failures as `invalid_sql` and
mutation/multiple statement/comment/wildcard/unmanaged-relation failures as
`unsafe_sql` without accepting substrings. Return stripped validated SQL.

- [x] **Step 8: Run Task 2 tests and commit**

Run:

```bash
uv run python -m pytest tests/unit/test_b12_prompts.py tests/unit/test_b12_extraction.py -q
git add src/nl2sparql/models/b12 tests/unit/test_b12_prompts.py tests/unit/test_b12_extraction.py
git commit -m "feat(baselines): build and parse GoogleSQL prompts"
```

Expected: PASS and one focused commit.

---

### Task 3: Provenance-bound deterministic five-shot retrieval

**Files:**
- Create: `src/nl2sparql/models/b12/retrieval.py`
- Modify: `src/nl2sparql/models/b12/__init__.py`
- Test: `tests/unit/test_b12_retrieval.py`

**Interfaces:**
- Consumes: accepted JSONL rows with `id`, `nl`, `sql`, `split="train"`, and
  `synthetic_fixture=false`; T3.5 SQL safety; an injected encoder satisfying
  `encode(texts: Sequence[str]) -> numpy.ndarray`.
- Produces: `FewShotRetriever.from_snapshot(path: Path, *, encoder: TextEncoder,
  encoder_id: str, encoder_revision: str, cache_path: Path | None = None) -> FewShotRetriever`,
  `.retrieve(question: str, *, target_id: str | None = None) -> tuple[SelectedExample, ...]`,
  plus read-only `training_sha256`, `encoder_id`, and `encoder_revision` properties.

- [x] **Step 1: Write failing snapshot/retrieval tests**

```python
def test_retrieval_is_score_then_id_deterministic(tmp_path):
    snapshot = write_training_rows(tmp_path, six_valid_rows())
    retriever = FewShotRetriever.from_snapshot(
        snapshot,
        encoder=TableEncoder(
            {
                "target": [1.0, 0.0],
                "question 1": [1.0, 0.0],
                "question 2": [1.0, 0.0],
                "question 3": [0.9, 0.1],
                "question 4": [0.8, 0.2],
                "question 5": [0.7, 0.3],
                "question 6": [0.0, 1.0],
            }
        ),
        encoder_id="sentence-transformers/all-MiniLM-L6-v2",
        encoder_revision="b" * 40,
    )
    selected = retriever.retrieve("target")
    assert [item.record_id for item in selected] == ["train-001", "train-002", "train-003", "train-004", "train-005"]


def test_retrieval_excludes_same_id_and_normalized_question(tmp_path):
    retriever = retriever_fixture(tmp_path)
    selected = retriever.retrieve("Ｓａｍｅ question", target_id="train-001")
    assert len(selected) == 5
    assert all(item.record_id != "train-001" for item in selected)
    assert all(normalize(item.question) != normalize("Same question") for item in selected)
```

Also test invalid JSON/UTF-8, duplicate IDs/questions, unsafe SQL, non-train split,
synthetic production rows, fewer than six usable rows, wrong/NaN/zero embeddings,
stale cache metadata, and exact-byte training SHA-256.

- [x] **Step 2: Run retrieval tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_retrieval.py -q`

Expected: FAIL because the retriever does not exist.

- [x] **Step 3: Implement validated snapshot loading and ranking**

Define the internal encoder protocol and immutable training record. Read exact
bytes once, decode strict UTF-8, require one JSON object per non-empty line,
normalize questions with NFKC/casefold/whitespace collapse, and validate SQL.
Encode all questions once, require a finite 2-D matrix with one non-zero row per
record, L2-normalize it, then rank query dot products by `(-score, record_id)`.
Exclude matching target IDs/questions before selecting exactly five.

- [x] **Step 4: Implement optional atomic embedding cache**

Store `.npz` vectors plus canonical JSON metadata containing training SHA-256,
encoder ID/revision, row IDs, shape, dtype, and matrix SHA-256. Refuse aliases
between snapshot/cache/lock, lock publication, validate every metadata field and
matrix digest on read, rebuild a stale cache only when the encoder is available,
and return structured `SmallLLMError` otherwise.

- [x] **Step 5: Run retrieval tests and confirm GREEN**

Run: `uv run python -m pytest tests/unit/test_b12_retrieval.py -q`

Expected: PASS.

- [x] **Step 6: Commit retrieval**

```bash
git add src/nl2sparql/models/b12 tests/unit/test_b12_retrieval.py
git commit -m "feat(baselines): retrieve deterministic B2 examples"
```

---

### Task 4: Deep B1/B2 prediction module and lazy Transformers adapter

**Files:**
- Create: `src/nl2sparql/models/b12/backend.py`
- Create: `src/nl2sparql/models/b12/baseline.py`
- Create: `src/nl2sparql/models/b12/transformers_backend.py`
- Create: `src/nl2sparql/models/b1_zero_shot.py`
- Create: `src/nl2sparql/models/b2_few_shot.py`
- Modify: `src/nl2sparql/models/b12/__init__.py`
- Test: `tests/unit/test_b12_baseline.py`
- Test: `tests/unit/test_b12_transformers_backend.py`

**Interfaces:**
- Consumes: `GenerationBackend.generate(messages, config) -> Completion`,
  catalog summary, prompt builder, extractor, and optional `FewShotRetriever`.
- Produces: `BaselineB1`, `BaselineB2`, their `predict`/`predict_detailed`
  operations, and lazy `TransformersBackend`.

- [x] **Step 1: Write failing public-interface tests with a scripted backend**

```python
def test_b1_returns_safe_sql_and_full_provenance():
    baseline = BaselineB1(summary_fixture(), GenerationConfig("a" * 40), ScriptedBackend(SAFE_SQL))
    result = baseline.predict_detailed("Count transactions")
    assert result.baseline == "b1"
    assert result.sql == SAFE_SQL
    assert result.extraction_status == "ok"
    assert result.selected_examples == ()
    assert result.completion.synthetic_backend is True


def test_b2_uses_exactly_retrieved_examples():
    baseline = BaselineB2(summary_fixture(), GenerationConfig("a" * 40), ScriptedBackend(SAFE_SQL), retriever_fixture())
    result = baseline.predict_detailed("Count transactions", target_id="test-001")
    assert result.baseline == "b2"
    assert len(result.selected_examples) == 5
    assert result.training_sha256 == retriever_fixture().training_sha256
```

Also test invalid question before backend/retriever calls, backend exceptions,
model identity mismatch, raw-output retention for every extraction status,
monotonic finite latency, and compatibility `predict` returning `None` on fail.

- [x] **Step 2: Run baseline tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_baseline.py -q`

Expected: FAIL because the baseline interfaces do not exist.

- [x] **Step 3: Implement backend protocol and baseline orchestration**

```python
class GenerationBackend(Protocol):
    def generate(
        self,
        messages: tuple[ChatMessage, ...],
        config: GenerationConfig,
    ) -> Completion:
        raise NotImplementedError

class BaselineB1:
    def predict(self, question: str) -> str | None:
        raise NotImplementedError

    def predict_detailed(self, question: str) -> SmallLLMPrediction:
        raise NotImplementedError

class BaselineB2:
    def predict(self, question: str, *, target_id: str | None = None) -> str | None:
        raise NotImplementedError

    def predict_detailed(
        self,
        question: str,
        *,
        target_id: str | None = None,
    ) -> SmallLLMPrediction:
        raise NotImplementedError
```

Validate question text before retrieving/generating. Measure only the generation
call with `time.perf_counter_ns`, validate completion model/revision against the
config, extract SQL, and construct the immutable prediction. Convert backend
runtime failures into a typed inference error without manufacturing a completion.

- [x] **Step 4: Run baseline tests and confirm GREEN**

Run: `uv run python -m pytest tests/unit/test_b12_baseline.py -q`

Expected: PASS.

- [x] **Step 5: Write failing lazy-adapter tests**

```python
def test_import_does_not_import_heavy_ml_modules():
    code = "import sys; import nl2sparql.models.b12.transformers_backend; print(int('torch' in sys.modules))"
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "0"


def test_adapter_uses_chat_template_and_decodes_only_new_tokens(monkeypatch):
    adapter = TransformersBackend.from_loaded(fake_model, fake_tokenizer)
    completion = adapter.generate(messages_fixture(), GenerationConfig("a" * 40))
    assert completion.raw_text == SAFE_SQL
    assert completion.input_tokens == 17
    assert completion.output_tokens == 11
    assert completion.synthetic_backend is False
```

- [x] **Step 6: Implement lazy production adapter**

Import Torch/Transformers/BitsAndBytes inside `load`, construct
`BitsAndBytesConfig(load_in_4bit=True)`, pin model/tokenizer `revision`, reject
remote code, set seed 42, apply chat template, run batch-one inference under
`torch.inference_mode()`, omit temperature for greedy generation, and decode
only tokens after input length. `from_loaded` exists only for adapter contract
tests and validates the supplied model/tokenizer surface.

- [x] **Step 7: Run Task 4 tests and commit**

Run:

```bash
uv run python -m pytest tests/unit/test_b12_baseline.py tests/unit/test_b12_transformers_backend.py -q
git add src/nl2sparql/models/b12 src/nl2sparql/models/b1_zero_shot.py src/nl2sparql/models/b2_few_shot.py tests/unit/test_b12_baseline.py tests/unit/test_b12_transformers_backend.py
git commit -m "feat(baselines): predict GoogleSQL with B1 and B2"
```

Expected: PASS and one focused commit.

---

### Task 5: Offline evaluator, atomic artifacts, and numbered CLI

**Files:**
- Create: `src/nl2sparql/models/b12/evaluate.py`
- Create: `scripts/small_llm_baselines_workflow.py`
- Create: `scripts/17_small_llm_baselines.py`
- Modify: `scripts/__init__.py`
- Test: `tests/unit/test_b12_evaluate.py`
- Test: `tests/unit/test_b12_workflow.py`
- Test: `tests/unit/test_b12_artifacts.py`

**Interfaces:**
- Consumes: B1/B2 public interfaces and accepted T3.5-style JSONL records.
- Produces: `evaluate_baseline(cases: Sequence[EvaluationCase], baseline:
  BaselineB1 | BaselineB2, *, run_id: str, reviewed: bool = False,
  live_verified: bool = False) -> EvaluationRun`,
  `validate`, `predict`, and `evaluate` CLI commands plus canonical JSONL/JSON artifacts.

- [x] **Step 1: Write failing evaluator tests**

```python
def test_evaluator_preserves_case_order_and_operational_counts():
    run = evaluate_baseline(cases_fixture(), baseline_fixture(), run_id="run-001")
    assert [row.case_id for row in run.predictions] == ["test-001", "test-002"]
    assert run.metrics.total == 2
    assert run.metrics.generated == 2
    assert run.metrics.extraction_ok == 1
    assert run.metrics.p50_latency_ms is not None
    assert run.scientific_ready is False


def test_fake_backend_can_never_be_scientifically_ready():
    run = evaluate_baseline(reviewed_cases_fixture(), synthetic_baseline_fixture(), run_id="run-001")
    assert run.scientific_ready is False
    assert "synthetic_backend" in run.blockers
```

Also test duplicate/malformed case IDs, unsafe gold SQL, difficulty/category
breakdowns, status counts, token sums, quantiles, deterministic repeated-run
comparison, and B2 passing target IDs into leakage exclusion.

- [x] **Step 2: Run evaluator tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_evaluate.py -q`

Expected: FAIL because evaluator contracts are missing.

- [x] **Step 3: Implement evaluation records and arithmetic**

Use frozen case/prediction/metrics/run dataclasses. Require unique stable IDs,
non-empty NL, safe gold SQL, normalized non-empty categories, and documented
difficulty. Preserve input order, compute p50/p95 with deterministic linear
interpolation, group counts by difficulty/category/status, and keep scientific
readiness false unless the backend is genuine and all external evidence flags
are explicitly valid. Do not compute execution accuracy.

- [x] **Step 4: Run evaluator tests and confirm GREEN**

Run: `uv run python -m pytest tests/unit/test_b12_evaluate.py -q`

Expected: PASS.

- [x] **Step 5: Write failing workflow/preflight/artifact tests**

```python
def test_help_does_not_import_ml_stack(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules
    assert "sentence_transformers" not in sys.modules


def test_invalid_question_precedes_model_loading(monkeypatch, runner):
    monkeypatch.setattr(workflow, "load_real_backend", fail_if_called)
    result = runner.invoke(cli, ["predict", "--baseline", "b1", "--question", "\x00"])
    assert result.exit_code != 0


def test_output_cannot_alias_any_protected_input(tmp_path, runner):
    result = invoke_evaluate(output=train_snapshot, train_snapshot=train_snapshot)
    assert result.exit_code != 0
    assert train_snapshot.read_bytes() == original_bytes
```

Cover missing catalog/test/train/model snapshots as structured `blocked`, B2
preflight before encoder loading, explicit `--real-inference` opt-in, exact
model revision, atomic temp/replace publication, prediction-first/report-last,
rollback, output-output aliases, symlink/hardlink aliases, locks/caches, and fake
adapter artifacts marked synthetic.

- [x] **Step 6: Run workflow tests and confirm RED**

Run: `uv run python -m pytest tests/unit/test_b12_workflow.py tests/unit/test_b12_artifacts.py -q`

Expected: FAIL because the workflow and CLI do not exist.

- [x] **Step 7: Implement lazy workflow and artifact publication**

Keep Click argument parsing and preflight in `small_llm_baselines_workflow.py`.
Only `load_real_backend` imports the Transformers adapter; only B2 real setup
imports SentenceTransformers. Serialize dataclasses to canonical newline-ended
JSON, fsync temp files, atomically replace targets, publish predictions/logs
before the final report, and restore prior complete outputs if final publication
fails. Emit one canonical structured status object on blocked/failed paths.

- [x] **Step 8: Add executable numbered wrapper**

`scripts/17_small_llm_baselines.py` imports `cli` from the workflow module and
calls it under `if __name__ == "__main__"`. Verify `--help` without model access:

```bash
uv run python scripts/17_small_llm_baselines.py --help
uv run python scripts/17_small_llm_baselines.py validate --help
uv run python scripts/17_small_llm_baselines.py predict --help
uv run python scripts/17_small_llm_baselines.py evaluate --help
```

- [x] **Step 9: Run Task 5 tests and commit**

Run:

```bash
uv run python -m pytest tests/unit/test_b12_evaluate.py tests/unit/test_b12_workflow.py tests/unit/test_b12_artifacts.py -q
git add src/nl2sparql/models/b12 scripts/17_small_llm_baselines.py scripts/small_llm_baselines_workflow.py scripts/__init__.py tests/unit/test_b12_evaluate.py tests/unit/test_b12_workflow.py tests/unit/test_b12_artifacts.py
git commit -m "feat(baselines): add B1 B2 offline workflow"
```

Expected: PASS and one focused commit.

---

### Task 6: Migrate task documentation and close local verification

**Files:**
- Modify: `docs/tasks/phase-5-baselines/02-b1-b2-small-llm.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/superpowers/plans/2026-09-01-t5-2-google-sql-small-llm.md`
- Test: `tests/unit/test_b12_artifacts.py`

**Interfaces:**
- Consumes: all implemented B1/B2 interfaces and fresh verification evidence.
- Produces: migrated GoogleSQL task status that separates local implementation
  completion from Kaggle/T3.5 scientific gates.

- [x] **Step 1: Review the legacy task against the documentation contract**

```python
def test_t5_2_task_is_google_sql_and_keeps_external_gates_open():
    text = TASK_PATH.read_text()
    assert "GoogleSQL" in text
    assert "không train" in text
    assert "implementation locally complete" in text
    assert "B1 latency <5s/query" in text
    assert "B2 latency <8s/query" in text
    assert "SPARQL extraction" not in text
```

- [x] **Step 2: Confirm the legacy task violates the approved GoogleSQL contract**

The review confirmed the legacy task described SPARQL baselines and conflated
local implementation with external scientific acceptance. A source-text test
was intentionally omitted because prose wording is not a runtime contract.

- [x] **Step 3: Rewrite T5.2 and add the architecture decision**

Document the GoogleSQL interfaces, catalog summary, raw-baseline no-linker
constraint, B2 top-five retrieval, lazy real backend, local commands, artifact
schema, synthetic-evidence exclusion, and exact external blockers. Add a dated
decision-log entry explaining why local implementation and Kaggle scientific
acceptance are separate.

- [x] **Step 4: Run focused tests and static checks**

```bash
uv run python -m pytest tests/unit/test_b12_contracts.py tests/unit/test_b12_catalog_summary.py tests/unit/test_b12_prompts.py tests/unit/test_b12_extraction.py tests/unit/test_b12_retrieval.py tests/unit/test_b12_baseline.py tests/unit/test_b12_transformers_backend.py tests/unit/test_b12_evaluate.py tests/unit/test_b12_workflow.py tests/unit/test_b12_artifacts.py -q
uv run ruff check src/nl2sparql/models/b12 src/nl2sparql/models/b1_zero_shot.py src/nl2sparql/models/b2_few_shot.py scripts/17_small_llm_baselines.py scripts/small_llm_baselines_workflow.py tests/unit/test_b12_*.py
uv run ruff format --check src/nl2sparql/models/b12 src/nl2sparql/models/b1_zero_shot.py src/nl2sparql/models/b2_few_shot.py scripts/17_small_llm_baselines.py scripts/small_llm_baselines_workflow.py tests/unit/test_b12_*.py
git diff --check
```

Expected: all pass.

- [x] **Step 5: Run full repository verification**

```bash
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/17_small_llm_baselines.py --help
git status --short
```

Expected: all tests/checks pass; status lists only intended T5.2 changes.

- [x] **Step 6: Commit documentation and plan evidence**

```bash
git add docs/tasks/phase-5-baselines/02-b1-b2-small-llm.md docs/memory/05-DECISION_LOG.md docs/superpowers/plans/2026-09-01-t5-2-google-sql-small-llm.md tests/unit/test_b12_artifacts.py
git commit -m "docs(baselines): migrate T5.2 to GoogleSQL"
```

- [x] **Step 7: Request whole-branch standards and spec review**

Review from merge-base `548e61e5afc7d922d468db5619fb18d873248660` along both axes:

- Standards: repository conventions, fail-closed safety, artifact integrity,
  lazy dependencies, test quality, and focused-module design.
- Spec: every requirement in the approved T5.2 design and migrated task,
  especially no local training/download, no linker use, no fake readiness, and
  external Kaggle gates remaining open.

- [x] **Step 8: Apply accepted review fixes test-first and re-verify**

For each Critical/Important finding, reproduce with a failing test, implement
one root-cause fix, rerun its focused suite, then rerun Step 5. Record final
review/verification evidence in the task document and commit the fix wave with a
focused message.

- [ ] **Step 9: Finish branch without claiming external acceptance**

Use `superpowers:verification-before-completion`, then
`superpowers:finishing-a-development-branch`. Push the branch only after fresh
tests and review pass. Report the PR URL and list T3.5/Kaggle latency/OOM gates
as pending rather than marking scientific T5.2 complete.
