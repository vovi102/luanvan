# T5.1 GoogleSQL Rule-Based Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic B0 baseline that maps natural-language Ethereum questions to validated GoogleSQL templates and evaluates local coverage, structural accuracy, and latency without claiming unavailable BigQuery execution evidence.

**Architecture:** A deep `BaselineB0` module compiles the accepted T3.1 templates, extracts typed slots through deterministic parsing plus T4.1-T4.3 evidence, fails closed on ambiguity, renders through the existing template validator, and validates the resulting GoogleSQL. Separate evaluation and workflow modules publish provenance-bound local artifacts while keeping network and BigQuery access outside prediction.

**Tech Stack:** Python 3.11, frozen dataclasses, regex/Unicode normalization, RapidFuzz-free token F1, SQLGlot BigQuery AST, Click, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-01-t5-1-google-sql-rule-baseline-design.md`

## Global Constraints

- `BaselineB0.predict(nl: str) -> str | None` is the compatibility interface.
- Prediction must not access the network, initialize BigQuery, or execute SQL.
- Only the 25 templates accepted by T3.1 and managed relations accepted by T3.5 may produce SQL.
- T4.1 evidence may break a structural tie but may not authorize unknown schema identities.
- Entity and concept slots must use supported T4.2/T4.3 evidence; ambiguity and coverage gaps fail closed.
- Every final SQL string must pass `render_template` and `validate_sql_text`.
- Synthetic fixtures never satisfy local or scientific readiness.
- Missing finalized T3.5 rows or BigQuery execution evidence must produce `not_ready` or structured `blocked`, never fabricated success.
- Production defaults use existing local cached indexes; `--help` and invalid-input paths remain encoder-free.

---

### Task 1: Immutable contracts and compiled template snapshot

**Files:**
- Create: `src/nl2sparql/models/__init__.py`
- Create: `src/nl2sparql/models/b0/__init__.py`
- Create: `src/nl2sparql/models/b0/contracts.py`
- Create: `src/nl2sparql/models/b0/templates.py`
- Test: `tests/unit/test_b0_contracts.py`
- Test: `tests/unit/test_b0_templates.py`

**Interfaces:**
- Consumes: `load_templates(path: Path)`, `validate_template_library(templates)`, and `PLACEHOLDER_RE` from `nl2sparql.dataset.templates.validate`.
- Produces: `B0Error`, `B0Policy`, `SlotValue`, `B0Prediction`, `CompiledTemplate`, and `compile_template_snapshot(path: Path, policy: B0Policy) -> tuple[CompiledTemplate, ...]`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_policy_is_bounded_and_fingerprinted() -> None:
    policy = B0Policy(structural_threshold=0.62, ambiguity_margin=0.03)
    assert len(policy.sha256) == 64
    with pytest.raises(B0Error, match="structural threshold"):
        B0Policy(structural_threshold=1.1, ambiguity_margin=0.03)


def test_prediction_requires_safe_immutable_values() -> None:
    prediction = B0Prediction(
        sql="SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
        template_id="T_LIST_KNOWN_EXCHANGES",
        match_mode="seed",
        score=1.0,
        slots=(SlotValue("n", "integer", 10, (5, 7)),),
        template_sha256="a" * 64,
        policy_sha256="b" * 64,
        catalog_sha256=None,
        entities_sha256=None,
        aliases_sha256=None,
        concepts_sha256=None,
        schema_elements=("entity_labels_v1.address",),
        cq_ids=("CQ07",),
        warnings=(),
    )
    assert prediction.slots[0].value == 10
```

- [ ] **Step 2: Run contract tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_contracts.py -q`

Expected: collection fails because `nl2sparql.models.b0` does not exist.

- [ ] **Step 3: Implement strict frozen contracts**

Implement exact validation in `contracts.py`:

```python
@dataclass(frozen=True)
class B0Policy:
    structural_threshold: float = 0.62
    ambiguity_margin: float = 0.03

    @property
    def sha256(self) -> str:
        body = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class SlotValue:
    name: str
    slot_type: str
    value: str | int
    span_offset: tuple[int, int]


@dataclass(frozen=True)
class B0Prediction:
    sql: str
    template_id: str
    match_mode: Literal["seed", "structural"]
    score: float
    slots: tuple[SlotValue, ...]
    template_sha256: str
    policy_sha256: str
    catalog_sha256: str | None
    entities_sha256: str | None
    aliases_sha256: str | None
    concepts_sha256: str | None
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    warnings: tuple[str, ...]
```

Reject non-finite scores, noncanonical SHA-256 values, duplicate/unsorted warnings, duplicate slot names, invalid half-open spans, unknown match modes, and mutable collection inputs.

- [ ] **Step 4: Write failing template compilation tests**

```python
def test_compile_snapshot_validates_and_orders_by_specificity(tmp_path: Path) -> None:
    source = TEMPLATES_PATH.read_bytes()
    path = tmp_path / "templates.json"
    path.write_bytes(source)
    compiled = compile_template_snapshot(path, B0Policy())
    assert len(compiled) == 25
    assert all(row.template_sha256 == hashlib.sha256(source).hexdigest() for row in compiled)
    assert [row.template_id for row in compiled] == sorted(
        (row.template_id for row in compiled),
        key=lambda template_id: next(
            (-row.literal_token_count, row.template_id)
            for row in compiled
            if row.template_id == template_id
        ),
    )


def test_compiled_seed_escapes_regex_literals() -> None:
    row = next(
        value
        for value in compile_template_snapshot(TEMPLATES_PATH, B0Policy())
        if value.template_id == "T_COUNT_TX_IN_RANGE"
    )
    match = row.seed_pattern.fullmatch(
        "How many transactions happened between 2026-06-15 and 2026-06-16?"
    )
    assert match is not None
    assert match.groupdict() == {
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }
```

- [ ] **Step 5: Run template tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_templates.py -q`

Expected: fails because `compile_template_snapshot` is absent.

- [ ] **Step 6: Implement validated compilation**

`CompiledTemplate` stores the original template mapping behind an immutable copy, compiled regex, literal tokens, declared slot order, schema annotations, template snapshot digest, and literal specificity. Build patterns by splitting `nl_seed` with `PLACEHOLDER_RE`, applying `re.escape` to literals, translating literal whitespace to `r"\s+"`, and using named patterns for all supported slot types. Anchor with `\A` and `\Z`, compile case-insensitively, and sort with key `(-literal_token_count, template_id)`.

- [ ] **Step 7: Run focused tests and commit**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_contracts.py tests/unit/test_b0_templates.py -q`

Expected: PASS.

```bash
git add src/nl2sparql/models tests/unit/test_b0_contracts.py tests/unit/test_b0_templates.py
git commit -m "feat(baselines): compile typed B0 templates"
```

---

### Task 2: Typed slot extraction and linking evidence

**Files:**
- Create: `src/nl2sparql/models/b0/slots.py`
- Test: `tests/unit/test_b0_slots.py`

**Interfaces:**
- Consumes: `CompiledTemplate`, `SlotValue`, T4.2 `EntityMatch`, T4.3 `ResolutionPlan`, and T3.1 `render_template`-compatible Python values.
- Produces: `extract_seed_slots(template, question, groups, resolution_plan) -> tuple[SlotValue, ...] | None`, `extract_structural_slots(template, question, resolution_plan) -> tuple[SlotValue, ...] | None`, and `slot_mapping(values) -> dict[str, str | int]`.

- [ ] **Step 1: Write failing scalar and repeated-slot tests**

```python
def test_seed_slots_parse_dates_numbers_and_address(template_lookup) -> None:
    template = template_lookup("T_LIST_TX_FROM_ACCOUNT")
    question = (
        "List 10 transactions sent by "
        "0x0d0707963952f2fba59dd06f2b425ace40b492fe "
        "between 2026-06-15 and 2026-06-16."
    )
    groups = template.seed_pattern.fullmatch(question)
    assert groups is not None
    slots = extract_seed_slots(template, question, groups, None)
    assert slot_mapping(slots or ()) == {
        "n": 10,
        "account": "0x0d0707963952f2fba59dd06f2b425ace40b492fe",
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }


def test_structural_slots_assign_two_accounts_and_dates_in_source_order(template_lookup) -> None:
    template = template_lookup("T_TX_BETWEEN_ACCOUNTS")
    slots = extract_structural_slots(template, QUESTION_WITH_TWO_ACCOUNTS, None)
    assert [value.name for value in slots or ()] == [
        "n", "account", "account_b", "start_date", "end_date"
    ]
```

- [ ] **Step 2: Run scalar tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_slots.py -q`

Expected: fails because slot extraction is absent.

- [ ] **Step 3: Implement typed lexical scanners**

Use bounded compiled patterns for ISO dates, canonical addresses/hashes, unsigned numeric values, and symbols. Convert integer-like slots to `int`; preserve `decimal_wei` as a string. Validate each complete mapping by calling `render_template(template.raw, mapping)` so the existing min/max and 31-day date window contracts remain authoritative. Return `None` on missing, extra, overlapping, multiply assignable, or invalid values.

- [ ] **Step 4: Add failing entity and concept evidence tests**

```python
def test_owner_must_resolve_to_one_supported_address(template_lookup) -> None:
    template = template_lookup("T_LIST_TX_FROM_ACCOUNT")
    plan = resolved_instance_plan(addresses=(ADDRESS_A,))
    slots = extract_seed_slots(template, OWNER_QUESTION, owner_seed_match(template), plan)
    assert slot_mapping(slots or ())["account"] == ADDRESS_A


@pytest.mark.parametrize("plan", [partial_plan(), multi_address_plan(), coverage_gap_plan()])
def test_unsafe_resolution_rejects_candidate(template_lookup, plan) -> None:
    template = template_lookup("T_LARGE_TX_TO_CLASS")
    assert extract_structural_slots(template, CLASS_QUESTION, plan) is None
```

- [ ] **Step 5: Run evidence tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_slots.py -q`

Expected: new evidence cases fail.

- [ ] **Step 6: Bind scalar entity/concept slots to T4.3**

Map `ethereum_address` from source text first; otherwise require one source-overlapping `ResolvedEntity` with `resolution_kind="instance"`, `coverage_status="supported"`, operator `in`, and exactly one address. Map `concept_class` only from one source-overlapping `ResolvedEntity` with kind `concept`, status supported, operator equals, and one value. Require the aggregate plan status to be `resolved` and warnings empty for every linker-derived slot.

- [ ] **Step 7: Run focused tests and commit**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_slots.py -q`

Expected: PASS.

```bash
git add src/nl2sparql/models/b0/slots.py tests/unit/test_b0_slots.py
git commit -m "feat(baselines): extract safe B0 slots"
```

---

### Task 3: Baseline orchestration, structural selection, and SQL safety

**Files:**
- Create: `src/nl2sparql/models/b0/baseline.py`
- Create: `src/nl2sparql/models/b0_rule_based.py`
- Modify: `src/nl2sparql/models/b0/__init__.py`
- Modify: `src/nl2sparql/models/__init__.py`
- Test: `tests/unit/test_b0_rule_based.py`

**Interfaces:**
- Consumes: compiled templates, slot extractors, `SchemaLinker.link`, `EntityLinker.link`, `ClassResolver.resolve`, `render_template`, and `validate_sql_text`.
- Produces: `BaselineB0.__init__(templates_path, schema_linker, entity_linker, class_resolver, policy=B0Policy())`, `predict_detailed(nl: str) -> B0Prediction | None`, and `predict(nl: str) -> str | None`.

- [ ] **Step 1: Write failing exact prediction tests**

```python
def test_predict_returns_validated_google_sql(baseline: BaselineB0) -> None:
    sql = baseline.predict(
        "How many transactions happened between 2026-06-15 and 2026-06-16?"
    )
    assert sql == (
        "SELECT COUNT(*) AS transaction_count\n"
        "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
        "(DATE '2026-06-15', DATE '2026-06-16')"
    )
    validate_sql_text(sql)


def test_predict_detailed_records_template_and_snapshot(baseline: BaselineB0) -> None:
    result = baseline.predict_detailed(SEED_QUESTION)
    assert result is not None
    assert result.template_id == "T_COUNT_TX_IN_RANGE"
    assert result.match_mode == "seed"
    assert result.score == 1.0
```

- [ ] **Step 2: Run exact tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_rule_based.py -q`

Expected: fails because `BaselineB0` is absent.

- [ ] **Step 3: Implement exact orchestration**

Validate public NL as non-empty, control-free, token-bearing text of at most 2,000 characters. Compute entity/schema evidence lazily: seed candidates containing only directly parsed scalar slots do not invoke linkers. For each full seed match, extract slots, render, validate SQL, and create a prediction. Return one success; if multiple seed patterns succeed, retain only a unique most-specific pattern or return `None`.

- [ ] **Step 4: Write failing structural and tie tests**

```python
def test_structural_fallback_matches_unique_anchor_set(baseline: BaselineB0) -> None:
    result = baseline.predict_detailed(
        "Count transactions occurring from 2026-06-15 through 2026-06-16"
    )
    assert result is not None
    assert result.template_id == "T_COUNT_TX_IN_RANGE"
    assert result.match_mode == "structural"


def test_structural_tie_without_unique_schema_support_returns_none(tied_baseline) -> None:
    assert tied_baseline.predict_detailed(TIED_QUESTION) is None


def test_schema_overlap_breaks_only_one_structural_tie(schema_tied_baseline) -> None:
    result = schema_tied_baseline.predict_detailed(TIED_QUESTION)
    assert result is not None
    assert result.template_id == "T_LIST_TX_TO_ACCOUNT"
```

- [ ] **Step 5: Run structural tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_rule_based.py -q`

Expected: structural cases fail.

- [ ] **Step 6: Implement token F1 and fail-closed selection**

Normalize NFKC/casefold tokens. Mask spans found by typed scanners and T4.2 before scoring. Compute multiset precision/recall and harmonic F1 against each template's literal anchor tokens. Reject scores below `policy.structural_threshold`. Treat candidates whose score differs from the best by at most `ambiguity_margin` as tied. Break a tie only if one candidate has a strictly greater count of exact T4.1 `element_id` overlap with its declared schema elements; otherwise return `None`.

- [ ] **Step 7: Add safety and error behavior tests**

```python
@pytest.mark.parametrize("question", ["", "   ", "\x00", "x" * 2001])
def test_invalid_public_question_raises(question: str, baseline: BaselineB0) -> None:
    with pytest.raises(B0Error, match="question"):
        baseline.predict(question)


def test_partial_entity_plan_returns_none(partial_entity_baseline) -> None:
    assert partial_entity_baseline.predict(OWNER_QUESTION) is None


def test_renderer_or_sql_safety_failure_rejects_candidate(unsafe_template_baseline) -> None:
    assert unsafe_template_baseline.predict(SEED_QUESTION) is None
```

- [ ] **Step 8: Run focused tests and commit**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_contracts.py tests/unit/test_b0_templates.py tests/unit/test_b0_slots.py tests/unit/test_b0_rule_based.py -q`

Expected: PASS.

```bash
git add src/nl2sparql/models tests/unit/test_b0_rule_based.py
git commit -m "feat(baselines): predict GoogleSQL with B0"
```

---

### Task 4: Offline evaluation contracts and metrics

**Files:**
- Create: `src/nl2sparql/models/b0/evaluate.py`
- Modify: `src/nl2sparql/models/b0/__init__.py`
- Test: `tests/unit/test_b0_evaluate.py`

**Interfaces:**
- Consumes: finalized T3.5-style JSONL, `BaselineB0.predict_detailed`, `validate_sql_text`, and SQLGlot BigQuery parser.
- Produces: `B0EvaluationCase`, `B0CaseResult`, `B0EvaluationReport`, `load_b0_cases(path, *, synthetic=False)`, and `evaluate_b0(baseline, cases, *, clock=time.perf_counter_ns) -> tuple[tuple[B0CaseResult, ...], B0EvaluationReport]`.

- [ ] **Step 1: Write failing artifact validation tests**

```python
def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path, [valid_case("Q001"), valid_case("Q001")])
    with pytest.raises(B0EvaluationError, match="duplicate"):
        load_b0_cases(path, synthetic=True)


def test_scientific_rows_require_live_verification(tmp_path: Path) -> None:
    row = valid_case("Q001") | {"verified_executable": False}
    path = write_jsonl(tmp_path, [row])
    with pytest.raises(B0EvaluationError, match="verified"):
        load_b0_cases(path, synthetic=False)
```

- [ ] **Step 2: Run artifact tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_evaluate.py -q`

Expected: fails because evaluator contracts are absent.

- [ ] **Step 3: Implement strict JSONL loading**

Read UTF-8 bytes, reject duplicate JSON keys, blank lines, unknown/missing fields, duplicate IDs, controls, unsafe gold SQL, invalid difficulty, malformed evidence SHA, and scientific rows without `verified_executable=true`. Retain an input SHA-256 and `synthetic` flag in the immutable case collection.

- [ ] **Step 4: Write failing metric tests**

```python
def test_metrics_separate_coverage_from_matched_accuracy(fake_baseline) -> None:
    results, report = evaluate_b0(fake_baseline, THREE_CASES, clock=step_clock())
    assert len(results) == 3
    assert report.coverage == pytest.approx(2 / 3)
    assert report.exact_match_accuracy == pytest.approx(1 / 2)
    assert report.structural_accuracy == pytest.approx(1.0)
    assert report.execution_accuracy is None
    assert report.scientific_status == "not_ready"


def test_synthetic_report_never_becomes_ready(perfect_baseline) -> None:
    _, report = evaluate_b0(perfect_baseline, SYNTHETIC_CASES, clock=step_clock())
    assert report.local_status == "not_ready"
    assert report.scientific_status == "not_ready"
```

- [ ] **Step 5: Run metric tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_evaluate.py -q`

Expected: metric cases fail.

- [ ] **Step 6: Implement canonical comparison and latency evidence**

Canonicalize SQL with `sqlglot.parse_one(sql, read="bigquery").sql(dialect="bigquery", pretty=False)`. Exact match compares normalized whitespace; structural match compares canonical AST SQL. Measure only `predict_detailed` with monotonic nanoseconds after one untimed warm-up per distinct question. Compute nearest-rank p50/p95 over nonnegative finite millisecond samples. Set local ready only for nonsynthetic reviewed data meeting coverage `>=0.40`, structural accuracy `>=0.60`, and p95 `<100.0`; keep scientific status not ready while execution accuracy is absent.

- [ ] **Step 7: Run focused tests and commit**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_evaluate.py -q`

Expected: PASS.

```bash
git add src/nl2sparql/models/b0/evaluate.py src/nl2sparql/models/b0/__init__.py tests/unit/test_b0_evaluate.py
git commit -m "feat(baselines): evaluate B0 offline"
```

---

### Task 5: Offline workflow, atomic artifacts, and numbered CLI

**Files:**
- Create: `scripts/b0_rule_baseline_workflow.py`
- Create: `scripts/16_b0_rule_baseline.py`
- Test: `tests/unit/test_b0_workflow.py`
- Test: `tests/unit/test_b0_artifacts.py`

**Interfaces:**
- Consumes: production cached schema/entity indexes, dictionary artifacts, catalog, `BaselineB0`, and evaluator contracts.
- Produces: Click commands `predict` and `evaluate`, canonical JSON stdout, atomic prediction JSONL/report publication, structured exit codes `0=success`, `1=failed`, and `2=blocked`.

- [ ] **Step 1: Write failing offline CLI tests**

```python
def test_help_does_not_initialize_encoder(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_production_baseline", forbidden)
    result = CliRunner().invoke(workflow.create_cli(), ["--help"])
    assert result.exit_code == 0
    assert "predict" in result.output
    assert "evaluate" in result.output


def test_missing_test_set_is_structured_blocked(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        workflow.create_cli(), ["evaluate", "--test-set", str(tmp_path / "missing.jsonl")]
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["cause"] == "external_evidence_unavailable"
```

- [ ] **Step 2: Run CLI tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_workflow.py -q`

Expected: fails because workflow is absent.

- [ ] **Step 3: Implement lazy local production construction**

Reuse the accepted builders/loaders from `schema_linker_workflow.py`, `entity_linker_workflow.py`, and `class_resolver_workflow.py` without importing Click command callbacks. Move only generally reusable local-loading helpers into the owning linking packages if direct imports would create a script-to-script dependency. Instantiate encoders inside command callbacks with local-files-only behavior and classify absent cache/model/evidence as blocked.

- [ ] **Step 4: Write failing publication tests**

```python
def test_evaluate_publishes_canonical_predictions_and_report(tmp_path: Path, fake_factory) -> None:
    result = CliRunner().invoke(
        create_cli(baseline_factory=fake_factory),
        [
            "evaluate", "--test-set", str(SYNTHETIC_INPUT), "--synthetic",
            "--predictions", str(tmp_path / "predictions.jsonl"),
            "--report", str(tmp_path / "report.json"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "not_ready"


def test_output_may_not_alias_input(tmp_path: Path, fake_factory) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_bytes(SYNTHETIC_INPUT.read_bytes())
    result = CliRunner().invoke(
        create_cli(baseline_factory=fake_factory),
        ["evaluate", "--test-set", str(path), "--synthetic", "--report", str(path)],
    )
    assert result.exit_code == 1
    assert path.read_bytes() == SYNTHETIC_INPUT.read_bytes()
```

- [ ] **Step 5: Run artifact tests and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_artifacts.py tests/unit/test_b0_workflow.py -q`

Expected: publication cases fail.

- [ ] **Step 6: Implement canonical atomic publication**

Serialize sorted-key compact JSON with one trailing newline. Write both artifacts to unique files in their destination directories, flush and fsync files, replace predictions first and report last, fsync directories, reject symlinks/hardlinks/nonregular outputs, and restore the previously accepted predictions file if report publication fails. Include Git SHA/dirty state plus template, policy, catalog, dictionary, and input fingerprints in the report.

- [ ] **Step 7: Run workflow tests and commit**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_artifacts.py tests/unit/test_b0_workflow.py -q`

Expected: PASS.

```bash
git add scripts/16_b0_rule_baseline.py scripts/b0_rule_baseline_workflow.py tests/unit/test_b0_artifacts.py tests/unit/test_b0_workflow.py
git commit -m "feat(baselines): add B0 offline workflow"
```

---

### Task 6: Migrate task documentation and add reproducible notebook

**Files:**
- Modify: `docs/tasks/phase-5-baselines/01-b0-rule-based.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Create: `notebooks/13_b0_eval.ipynb`
- Test: `tests/unit/test_b0_notebook.py`

**Interfaces:**
- Consumes: final module/workflow paths and measured focused verification output.
- Produces: SQL-native T5.1 task state, architecture decision entry, and a valid notebook that reads the published report without implementing prediction logic.

- [ ] **Step 1: Write failing notebook contract test**

```python
def test_b0_notebook_is_valid_and_uses_workflow_artifact() -> None:
    notebook = json.loads(Path("notebooks/13_b0_eval.ipynb").read_text())
    assert notebook["nbformat"] == 4
    source = "\n".join(
        line
        for cell in notebook["cells"]
        for line in cell.get("source", [])
    )
    assert "reports/b0_evaluation.json" in source
    assert "BaselineB0(" not in source
    assert "BigQuery" not in source
```

- [ ] **Step 2: Run notebook test and confirm RED**

Run: `/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_notebook.py -q`

Expected: fails because the notebook is absent.

- [ ] **Step 3: Create the report-reader notebook**

Create a deterministic nbformat 4 notebook with markdown explaining local versus scientific readiness and code cells that load `reports/b0_evaluation.json`, display aggregate metrics, and plot counts only when the report exists. Use no embedded output, execution count, credential access, or duplicated B0 logic.

- [ ] **Step 4: Rewrite T5.1 as GoogleSQL and record the decision**

Replace SPARQL terminology, obsolete pseudo-code, and unconditional execution claims. Document exact module/CLI/artifact paths, local acceptance gates, external T3.5/BigQuery blockers, and checked evidence. Add a decision-log entry that B0 is a fail-closed template selector, not a second SQL generator.

- [ ] **Step 5: Run documentation checks and commit**

Run:

```bash
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest tests/unit/test_b0_notebook.py -q
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m json.tool notebooks/13_b0_eval.ipynb >/dev/null
rg -n "SPARQL|Fuseki|NL2SPARQL" docs/tasks/phase-5-baselines/01-b0-rule-based.md
```

Expected: tests and JSON pass; the terminology scan has no matches.

```bash
git add docs/tasks/phase-5-baselines/01-b0-rule-based.md docs/memory/05-DECISION_LOG.md notebooks/13_b0_eval.ipynb tests/unit/test_b0_notebook.py
git commit -m "docs(baselines): migrate T5.1 to GoogleSQL"
```

---

### Task 7: Local acceptance evidence and final review

**Files:**
- Modify: `docs/tasks/phase-5-baselines/01-b0-rule-based.md`
- Modify: any T5.1 file implicated by verification or review findings.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: reviewed, clean, locally complete T5.1 branch whose external scientific gates remain explicit.

- [ ] **Step 1: Run focused T5.1 verification**

Run:

```bash
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest \
  tests/unit/test_b0_contracts.py \
  tests/unit/test_b0_templates.py \
  tests/unit/test_b0_slots.py \
  tests/unit/test_b0_rule_based.py \
  tests/unit/test_b0_evaluate.py \
  tests/unit/test_b0_artifacts.py \
  tests/unit/test_b0_workflow.py \
  tests/unit/test_b0_notebook.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run repository verification**

Run:

```bash
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m pytest -q
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/ruff check .
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/ruff format --check .
PYTHONPATH=src /home/khoavd/WORKSPACE/LuanVan/.venv/bin/python scripts/16_b0_rule_baseline.py --help
/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python -m json.tool notebooks/13_b0_eval.ipynb >/dev/null
git diff --check origin/main...HEAD
```

Expected: pytest, Ruff, CLI help, notebook validation, and diff checks pass.

- [ ] **Step 3: Request whole-branch review**

Review `origin/main...HEAD` along both axes:

- Standards: repository conventions, fail-closed behavior, deterministic artifacts, offline help, immutable provenance, and test quality.
- Spec: every requirement in `docs/superpowers/specs/2026-09-01-t5-1-google-sql-rule-baseline-design.md`, with special attention to ambiguous structural matches, scalar entity resolution, synthetic readiness, and publication rollback.

Expected: no Critical or Important findings before completion.

- [ ] **Step 4: Apply review fixes test-first and rerun verification**

For every valid finding, add a focused failing regression test, observe RED, implement the smallest fix, observe GREEN, then rerun Step 1 and Step 2. Do not weaken contracts or tests to clear a finding.

- [ ] **Step 5: Record exact local evidence and commit**

Update the task with exact focused/full test counts, warning count, Ruff results, CLI result, branch SHA, and explicit pending external gates. Do not claim coverage, structural accuracy, latency, or execution accuracy unless a qualifying reviewed artifact was actually evaluated.

```bash
git add docs/tasks/phase-5-baselines/01-b0-rule-based.md
git commit -m "docs(baselines): complete T5.1 local checkpoint"
git status --short
```

Expected: final commit succeeds and the worktree is clean.
