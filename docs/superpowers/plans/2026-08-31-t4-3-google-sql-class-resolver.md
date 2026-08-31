# T4.3 GoogleSQL Class Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic offline resolver that converts T4.2 entity evidence and optional T4.1 schema rankings into provenance-bound GoogleSQL constraint plans without rendering SQL.

**Architecture:** A deep `ClassResolver` module loads and validates one catalog snapshot plus one immutable entity corpus, then exposes only `resolve`. Focused contract, catalog-index, resolver, and evaluation files keep validation and policy local while a thin numbered workflow serializes canonical JSON.

**Tech Stack:** Python 3.11, frozen dataclasses, stdlib JSON/hashlib/regex, Click, pytest, Ruff, existing `EntityCorpus`, `EntityMatch`, `LinkResult`, and SQL catalog validator.

**Spec:** `docs/superpowers/specs/2026-08-31-t4-3-google-sql-class-resolver-design.md`

## Global Constraints

- The runtime dialect is GoogleSQL; no SPARQL fragment or executable SQL may appear in resolver output.
- All implementation and verification paths must run without network, model initialization, BigQuery credentials, or live queries.
- Inputs and outputs are immutable; valid ambiguity and coverage gaps are returned as data, while malformed or stale contracts fail closed with `ClassResolverError`.
- Catalog relations, fields, joins, roles, and coverage claims must come only from a snapshot accepted by `validate_catalog`.
- Scientific accuracy `>= 0.90` cannot be claimed without an independently reviewed, exactly 50-question annotation artifact.

---

### Task 1: Resolver Contracts and Validated Catalog Index

**Files:**
- Create: `src/nl2sparql/linking/resolver/contracts.py`
- Create: `src/nl2sparql/linking/resolver/catalog.py`
- Create: `src/nl2sparql/linking/resolver/__init__.py`
- Test: `tests/unit/test_class_resolver_contracts.py`
- Test: `tests/unit/test_class_resolver_catalog.py`

**Interfaces:**
- Consumes: `EntityCorpus` fingerprints and `validate_catalog(catalog) -> CatalogSummary`.
- Produces: `ClassResolverError`, `FieldCandidate`, `ResolvedEntity`, `ResolutionPlan`, `ResolverCatalog`, and `load_resolver_catalog(path: Path) -> ResolverCatalog`.

- [ ] **Step 1: Write failing immutable-contract tests**

```python
def test_resolved_entity_rejects_sql_text_and_invalid_operator_value_pair() -> None:
    with pytest.raises(ClassResolverError, match="operator"):
        ResolvedEntity(**{**valid_entity(), "operator": "equals", "values": ()})
    with pytest.raises(ClassResolverError, match="field"):
        FieldCandidate("transaction_facts", "to_address; DROP TABLE x")


def test_resolution_plan_is_deeply_immutable_and_status_is_coherent() -> None:
    entity = ResolvedEntity(**valid_entity())
    plan = ResolutionPlan(
        question_sha256="a" * 64,
        entities=(entity,),
        catalog_sha256="b" * 64,
        entities_sha256="c" * 64,
        aliases_sha256="d" * 64,
        concepts_sha256="e" * 64,
        status="resolved",
        warnings=(),
    )
    assert plan.entities == (entity,)
```

- [ ] **Step 2: Run the contract tests and confirm the red state**

Run: `uv run pytest tests/unit/test_class_resolver_contracts.py -q`

Expected: collection fails because `nl2sparql.linking.resolver` does not exist.

- [ ] **Step 3: Implement the frozen contracts and invariants**

```python
@dataclass(frozen=True)
class FieldCandidate:
    relation: str
    field: str


@dataclass(frozen=True)
class ResolvedEntity:
    span: str
    span_offset: tuple[int, int]
    target_id: str
    target_sha256: str
    resolution_kind: Literal["instance", "concept", "unresolved"]
    direction: Literal["from", "to", "token", "unspecified"]
    fields: tuple[FieldCandidate, ...]
    operator: Literal["in", "equals", "none"]
    values: tuple[str, ...]
    required_relation: str | None
    required_join: str | None
    required_role: str | None
    coverage_status: Literal["supported", "coverage_gap", "unresolved"]
    confidence: float
    explanation: str


@dataclass(frozen=True)
class ResolutionPlan:
    question_sha256: str
    entities: tuple[ResolvedEntity, ...]
    catalog_sha256: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str
    status: Literal["resolved", "partial", "unresolved"]
    warnings: tuple[str, ...]
```

Validate bounded/control-free strings, lowercase SHA-256 digests, canonical
addresses, sorted unique tuples, finite confidence, allowed vocabularies, and
coherent operator/value/relation/join combinations in `__post_init__`.

- [ ] **Step 4: Run contract tests and confirm green**

Run: `uv run pytest tests/unit/test_class_resolver_contracts.py -q`

Expected: all contract tests pass.

- [ ] **Step 5: Write failing catalog-index tests**

```python
def test_catalog_index_exposes_only_validated_address_candidates(catalog_path: Path) -> None:
    index = load_resolver_catalog(catalog_path)
    assert index.fields_by_direction["from"] == (
        FieldCandidate("token_transfer_facts", "from_address"),
        FieldCandidate("transaction_facts", "from_address"),
    )
    assert index.entity_join == "fact_address_to_entity"
    assert index.concept_field == FieldCandidate("entity_labels_v1", "concept_class")


def test_catalog_index_rejects_tampered_join(catalog_path: Path) -> None:
    raw = json.loads(catalog_path.read_text())
    raw["join_paths"]["fact_address_to_entity"]["right_field"] = "owner"
    catalog_path.write_text(json.dumps(raw))
    with pytest.raises(ClassResolverError, match="entity lookup"):
        load_resolver_catalog(catalog_path)
```

- [ ] **Step 6: Implement exact-snapshot loading and catalog-derived lookup**

`load_resolver_catalog` must read bytes once, call `load_catalog(snapshot=raw)`,
call `validate_catalog`, hash `raw`, and derive immutable direction fields from
`fact_address_to_entity.left_relations`. It must verify the right relation/field,
allowed roles, `entity_labels_v1.concept_class`, and supported semantic mappings.

- [ ] **Step 7: Run Task 1 tests and commit**

Run: `uv run pytest tests/unit/test_class_resolver_contracts.py tests/unit/test_class_resolver_catalog.py -q`

Expected: all tests pass.

```bash
git add src/nl2sparql/linking/resolver tests/unit/test_class_resolver_contracts.py tests/unit/test_class_resolver_catalog.py
git commit -m "feat(linking): define resolver catalog contracts"
```

### Task 2: Deterministic Instance and Concept Resolution

**Files:**
- Create: `src/nl2sparql/linking/resolver/resolver.py`
- Modify: `src/nl2sparql/linking/resolver/__init__.py`
- Create: `src/nl2sparql/linking/class_resolver.py`
- Test: `tests/unit/test_class_resolver.py`

**Interfaces:**
- Consumes: `ResolverCatalog`, `EntityCorpus`, `EntityMatch`, and optional `LinkResult`.
- Produces: `ClassResolver(catalog_path: Path, corpus: EntityCorpus)` and `ClassResolver.resolve(question, matches, schema_links=None) -> ResolutionPlan`.

- [ ] **Step 1: Write failing tests for instance, address, and concept targets**

```python
def test_owner_resolves_to_canonical_address_membership(resolver, owner_match) -> None:
    result = resolver.resolve("transactions to Binance", (owner_match,))
    entity = result.entities[0]
    assert entity.resolution_kind == "instance"
    assert entity.direction == "to"
    assert entity.operator == "in"
    assert entity.values == owner_match.addresses
    assert entity.fields == (FieldCandidate("transaction_facts", "to_address"),)


def test_concept_resolves_through_catalog_label_join(resolver, concept_match) -> None:
    result = resolver.resolve("transactions to any exchange", (concept_match,))
    entity = result.entities[0]
    assert entity.resolution_kind == "concept"
    assert entity.operator == "equals"
    assert entity.values == ("ExchangeAccount",)
    assert entity.required_relation == "entity_labels_v1"
    assert entity.required_join == "fact_address_to_entity"
```

- [ ] **Step 2: Run the focused tests and confirm red**

Run: `uv run pytest tests/unit/test_class_resolver.py -k 'owner or concept' -q`

Expected: import or attribute failure for `ClassResolver`.

- [ ] **Step 3: Implement construction, input validation, and primary resolution**

The constructor strict-loads the resolver catalog once and indexes corpus targets
by ID. `resolve` must verify question length/content, exact span slices, source
ordering, non-overlap, target existence, and target fingerprint equality before
building any result. Owner/address targets use address membership; concept targets
use the catalog-backed concept-class constraint.

```python
class ClassResolver:
    def __init__(self, catalog_path: Path, corpus: EntityCorpus) -> None: ...

    def resolve(
        self,
        question: str,
        matches: Sequence[EntityMatch],
        schema_links: LinkResult | None = None,
    ) -> ResolutionPlan: ...
```

- [ ] **Step 4: Add red tests for stale evidence and invalid spans**

```python
@pytest.mark.parametrize("mutation", ["unknown_target", "stale_digest", "bad_slice", "overlap"])
def test_resolver_rejects_untrusted_match_evidence(resolver, mutation, match_factory) -> None:
    with pytest.raises(ClassResolverError):
        resolver.resolve(*match_factory(mutation))
```

- [ ] **Step 5: Implement fail-closed evidence checks and plan provenance**

Hash the UTF-8 question, copy catalog/dictionary fingerprints into the plan, and
derive aggregate status from entity statuses. Never include the question text in
`ResolutionPlan`.

- [ ] **Step 6: Run Task 2 tests and commit**

Run: `uv run pytest tests/unit/test_class_resolver.py tests/unit/test_class_resolver_contracts.py tests/unit/test_class_resolver_catalog.py -q`

Expected: all tests pass.

```bash
git add src/nl2sparql/linking/resolver src/nl2sparql/linking/class_resolver.py tests/unit/test_class_resolver.py
git commit -m "feat(linking): resolve typed entity constraints"
```

### Task 3: Ambiguity, Direction, Schema Narrowing, and Coverage

**Files:**
- Modify: `src/nl2sparql/linking/resolver/resolver.py`
- Modify: `tests/unit/test_class_resolver.py`

**Interfaces:**
- Consumes: the Task 2 `ClassResolver.resolve` interface and T4.1 `SchemaMatch.element_id` values formatted as `relation` or `relation.field`.
- Produces: deterministic concept-trigger selection, direction candidates, schema narrowing, coverage gaps, and conflict warnings through the existing `ResolutionPlan` types.

- [ ] **Step 1: Write failing table-driven language-policy tests**

```python
@pytest.mark.parametrize(
    ("question", "expected_direction"),
    [
        ("transactions from Binance", "from"),
        ("transactions sent by Binance", "from"),
        ("transactions to Binance", "to"),
        ("funds received by Binance", "to"),
        ("show Binance activity", "unspecified"),
    ],
)
def test_direction_is_inferred_from_bounded_context(
    resolver, owner_match_at_span, question, expected_direction
) -> None:
    match = owner_match_at_span(question, "Binance")
    assert resolver.resolve(question, (match,)).entities[0].direction == expected_direction
```

Also add cases for `any`, `all`, `every`, `major`, generic plural, conflicting
cues, two same-direction mentions, no-address owner, and ambiguity with zero,
one, or two concept alternatives.

- [ ] **Step 2: Run language-policy tests and confirm red**

Run: `uv run pytest tests/unit/test_class_resolver.py -k 'direction or ambiguous or trigger' -q`

Expected: failures show missing ambiguity and context rules.

- [ ] **Step 3: Implement bounded cue and ambiguity policy**

Normalize only for comparison while retaining original offsets. Inspect a fixed
token window around each span. Select a concept alternative only for a class
trigger plus exactly one corpus-backed concept alternative; otherwise emit an
`unresolved` entity with operator `none`, empty values/fields, and explanation.

- [ ] **Step 4: Write failing schema and coverage tests**

```python
def test_schema_links_narrow_but_never_expand_catalog_fields(resolver, owner_match) -> None:
    links = LinkResult(
        relations=(schema_match("transaction_facts", "relation"),),
        fields=(schema_match("transaction_facts.to_address", "field"),),
    )
    entity = resolver.resolve("to Binance", (owner_match,), links).entities[0]
    assert entity.fields == (FieldCandidate("transaction_facts", "to_address"),)


def test_empty_concept_coverage_is_explicit(resolver, mixer_match) -> None:
    entity = resolver.resolve("to any mixer", (mixer_match,)).entities[0]
    assert entity.coverage_status == "coverage_gap"
    assert "coverage" in entity.explanation
```

- [ ] **Step 5: Implement schema intersection, role, and coverage derivation**

Parse schema IDs only after validating their `kind`; intersect them with the
catalog-derived direction candidates. If the intersection is empty, retain
catalog candidates and add an evidence warning rather than inventing a field.
Coverage derives by indexing corpus owner targets whose `concept_classes` contain
the hydrated concept class and whose `address_roles` satisfy the catalog role
policy. It must not parse the concept document or assume that a concept target
contains addresses. Matching catalog competency coverage can downgrade the result.
Role values must be copied from catalog policies only.

- [ ] **Step 6: Run Task 3 tests and commit**

Run: `uv run pytest tests/unit/test_class_resolver.py -q`

Expected: at least 20 focused cases pass.

```bash
git add src/nl2sparql/linking/resolver/resolver.py tests/unit/test_class_resolver.py
git commit -m "feat(linking): enforce resolver ambiguity policy"
```

### Task 4: Offline 50-Question Evaluation Contracts

**Files:**
- Create: `src/nl2sparql/linking/resolver/evaluate.py`
- Modify: `src/nl2sparql/linking/resolver/__init__.py`
- Create: `tests/unit/test_class_resolver_evaluate.py`

**Interfaces:**
- Consumes: a resolver satisfying `resolve(question, matches, schema_links=None) -> ResolutionPlan` and JSONL cases containing reviewed match payloads plus expected kinds/directions/status.
- Produces: `load_ground_truth(path, corpus) -> ResolverGroundTruth`, `evaluate_resolver(resolver, dataset, provenance) -> ResolverEvaluationReport`.

- [ ] **Step 1: Write failing dataset-contract tests**

```python
def test_ground_truth_requires_exactly_fifty_unique_questions(tmp_path, corpus) -> None:
    with pytest.raises(ResolverEvaluationError, match="exactly 50"):
        load_ground_truth(write_rows(tmp_path, rows(49)), corpus)


def test_ground_truth_rejects_invalid_expected_vocabulary(tmp_path, corpus) -> None:
    bad = rows(50)
    bad[-1]["expected"][0]["direction"] = "sideways"
    with pytest.raises(ResolverEvaluationError, match=r"line 50.*direction"):
        load_ground_truth(write_rows(tmp_path, bad), corpus)
```

- [ ] **Step 2: Run evaluator tests and confirm red**

Run: `uv run pytest tests/unit/test_class_resolver_evaluate.py -q`

Expected: collection fails because evaluation contracts do not exist.

- [ ] **Step 3: Implement strict JSONL loading**

Require exactly 50 unique IDs/questions, valid original offsets, corpus-backed
target IDs and fingerprints, one expected row per supplied match, and the exact
resolution/direction/coverage vocabularies. Preserve the SHA-256 of accepted file
bytes and return immutable typed cases.

- [ ] **Step 4: Write failing hand-derived metric tests**

```python
def test_evaluator_reports_hand_derived_metrics(dataset, fake_resolver) -> None:
    report = evaluate_resolver(fake_resolver, dataset, provenance())
    assert report.resolution_kind_accuracy == pytest.approx(48 / 50)
    assert report.direction_accuracy == pytest.approx(45 / 50)
    assert report.fully_resolved_plan_accuracy == pytest.approx(44 / 50)
    assert report.coverage_gap_count == 3
```

- [ ] **Step 5: Implement deterministic evaluation and provenance**

Compute exact micro accuracies with explicit denominators, plan-level exact match,
coverage-gap counts, dataset/catalog/dictionary hashes, and full lowercase git
SHA plus dirty flag. Reject empty denominators, resolver provenance mismatch, and
non-finite metric values.

- [ ] **Step 6: Run Task 4 tests and commit**

Run: `uv run pytest tests/unit/test_class_resolver_evaluate.py -q`

Expected: all evaluator tests pass; synthetic metrics are labeled test evidence.

```bash
git add src/nl2sparql/linking/resolver/evaluate.py src/nl2sparql/linking/resolver/__init__.py tests/unit/test_class_resolver_evaluate.py
git commit -m "feat(linking): evaluate resolver plans offline"
```

### Task 5: Numbered Offline Workflow and Canonical Serialization

**Files:**
- Create: `scripts/15_class_resolver.py`
- Create: `scripts/class_resolver_workflow.py`
- Create: `tests/unit/test_class_resolver_workflow.py`

**Interfaces:**
- Consumes: committed dictionary/catalog paths, JSON payloads convertible to typed `EntityMatch` values, and Task 4 evaluation functions.
- Produces: `resolve` and `evaluate` Click subcommands with canonical JSON stdout or atomic report publication.

- [ ] **Step 1: Write failing help and offline resolve tests**

```python
def test_help_does_not_initialize_models_or_external_clients(monkeypatch) -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "resolve" in result.output
    assert "evaluate" in result.output


def test_resolve_emits_canonical_plan_json(tmp_path, valid_payload) -> None:
    result = CliRunner().invoke(cli, ["resolve", "--input", str(valid_payload)])
    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "resolved"
    assert result.output == canonical_json(json.loads(result.output)).decode()
```

- [ ] **Step 2: Run workflow tests and confirm red**

Run: `uv run pytest tests/unit/test_class_resolver_workflow.py -q`

Expected: imports fail because the numbered workflow does not exist.

- [ ] **Step 3: Implement lazy offline commands**

Build the corpus only inside command callbacks, strict-load one catalog snapshot,
parse duplicate-key-rejecting JSON, construct typed matches, call production
resolver/evaluator functions, and serialize dataclasses with sorted compact JSON.
Map missing external evidence to a distinct blocked exit status; programming and
contract errors remain failed. `resolve` writes stdout only. `evaluate --report`
uses unique temporary files, fsync, atomic replace, and rejects aliases with
catalog, dictionary, input, or ground-truth paths.

- [ ] **Step 4: Add red tests for malformed payloads and unsafe reports**

Cover duplicate JSON keys, invalid spans, missing ground truth, report/input
aliases through relative/absolute/symlink/hardlink paths, failed publication
rollback, and canonical provenance fields.

- [ ] **Step 5: Implement the failure and publication contracts**

Keep filesystem mutation limited to the explicit report destination. Do not
create a report or lock when deterministic validation fails.

- [ ] **Step 6: Run Task 5 tests and commit**

Run: `uv run pytest tests/unit/test_class_resolver_workflow.py -q`

Expected: all workflow tests pass without network or credentials.

```bash
git add scripts/15_class_resolver.py scripts/class_resolver_workflow.py tests/unit/test_class_resolver_workflow.py
git commit -m "feat(linking): add class resolver workflow"
```

### Task 6: Migrate T4.3 Documentation and Verify the Branch

**Files:**
- Rewrite: `docs/tasks/phase-4-linking/03-class-resolver.md`
- Create: `src/nl2sparql/linking/RESOLVER_RULES.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `src/nl2sparql/linking/__init__.py`
- Test: `tests/unit/test_class_resolver_artifacts.py`

**Interfaces:**
- Consumes: all production contracts and verification evidence from Tasks 1-5.
- Produces: stable package exports, migrated task status, resolver rule reference, decision record, and artifact checks preventing SPARQL regression.

- [ ] **Step 1: Write failing artifact and export tests**

```python
def test_t43_docs_are_google_sql_native() -> None:
    task = TASK_PATH.read_text()
    rules = RULES_PATH.read_text()
    forbidden = ("triple_pattern", "BIND(", "SPARQL fragment")
    assert not any(term in task for term in forbidden)
    assert "coverage_gap" in task
    assert "fact_address_to_entity" in rules


def test_stable_linking_facade_exports_resolver_contracts() -> None:
    from nl2sparql.linking import ClassResolver, ResolutionPlan
    assert ClassResolver is not None
    assert ResolutionPlan is not None
```

- [ ] **Step 2: Run artifact tests and confirm red**

Run: `uv run pytest tests/unit/test_class_resolver_artifacts.py -q`

Expected: legacy SPARQL terms and missing exports fail.

- [ ] **Step 3: Rewrite the task and rule reference**

Document the typed interface, rule priority, catalog field mapping, ambiguity,
role semantics, coverage gaps, local evidence, and pending independent 50-row
gate. Mark implementation criteria only after their commands pass.

- [ ] **Step 4: Add the decision-log entry and stable exports**

Record why typed constraint planning was chosen over SQL/SPARQL rendering and
LLM classification. Export `ClassResolver`, `ClassResolverError`,
`FieldCandidate`, `ResolvedEntity`, and `ResolutionPlan` from the stable linking
facade without importing CLI code.

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
uv run pytest tests/unit/test_class_resolver_contracts.py tests/unit/test_class_resolver_catalog.py tests/unit/test_class_resolver.py tests/unit/test_class_resolver_evaluate.py tests/unit/test_class_resolver_workflow.py tests/unit/test_class_resolver_artifacts.py -q
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Expected: focused and full tests pass; Ruff and diff checks exit zero.

- [ ] **Step 6: Record exact evidence and commit the checkpoint**

Update the T4.3 task with actual test counts and explicitly state that the missing
independently reviewed 50-row artifact leaves the scientific gate pending.

```bash
git add docs/tasks/phase-4-linking/03-class-resolver.md src/nl2sparql/linking/RESOLVER_RULES.md docs/memory/05-DECISION_LOG.md src/nl2sparql/linking/__init__.py tests/unit/test_class_resolver_artifacts.py
git commit -m "docs(linking): complete T4.3 implementation checkpoint"
```
