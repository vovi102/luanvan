# T2.1 Ontology Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate `v0.1.0` of the local EthOn-based Ethereum KG ontology extension.

**Architecture:** The authoritative artifact is a Turtle ontology file under `src/nl2sparql/kg/ontology/`. Unit tests parse it with `rdflib` and enforce class/property counts plus schema-linker metadata. Markdown docs capture version history, competency questions, memory updates, and task status.

**Tech Stack:** Python 3.11, `uv`, `pytest`, `rdflib`, Turtle/RDFS/OWL, Markdown.

---

## File Structure

- Create `tests/unit/test_ontology_extension.py`: structural tests for the ontology TTL and competency-question catalogue.
- Create `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`: local namespace ontology extension.
- Create `src/nl2sparql/kg/ontology/changelog.md`: ontology version history and manual Protégé validation status.
- Create `src/nl2sparql/kg/ontology/competency-questions.md`: 30+ questions with required ontology terms and SPARQL sketches.
- Modify `docs/memory/03-ONTOLOGY_REFERENCE.md`: replace placeholder status with finalized v0.1.0 reference.
- Modify `docs/memory/05-DECISION_LOG.md`: add a Phase 2 ontology namespace/scope decision.
- Modify `docs/tasks/phase-2-kg/01-ontology-extension.md`: tick acceptance criteria that can be verified locally and record evidence.

## Ontology Terms to Implement

Local namespace: `https://thesis.example.org/eth-kg/`

Classes:

- `:Account`, subclass of `ethon:Account`
- `:ExternallyOwnedAccount`, subclass of `:Account`
- `:IndividualAccount`, subclass of `:ExternallyOwnedAccount`
- `:ExchangeAccount`, subclass of `:ExternallyOwnedAccount`
- `:ValidatorAccount`, subclass of `:ExternallyOwnedAccount`
- `:MEVActorAccount`, subclass of `:ExternallyOwnedAccount`
- `:ContractAccount`, subclass of `:Account`
- `:MixerAccount`, subclass of `:ContractAccount`
- `:DEXProtocol`, subclass of `:ContractAccount`
- `:LendingProtocol`, subclass of `:ContractAccount`
- `:BridgeProtocol`, subclass of `:ContractAccount`
- `:NFTMarketplace`, subclass of `:ContractAccount`
- `:TokenContract`, subclass of `:ContractAccount`
- `:Transaction`, subclass of `ethon:Tx`
- `:Block`, subclass of `ethon:Block`
- `:TokenTransfer`, subclass of `ethon:LogEntry`
- `:ProtocolInteraction`, subclass of `ethon:LogEntry`

Properties:

- Identity: `:hasLabel`, `:hasAlias`, `:hasOwner`, `:hasCategory`, `:hasConfidenceScore`, `:hasSource`
- Transaction: `:hasFrom`, `:hasTo`, `:hasValue`, `:hasGasUsed`, `:hasGasPrice`, `:hasNonce`, `:hasInputData`, `:hasReceiptStatus`, `:includedInBlock`, `:hasTimestamp`, `:hasBlockNumber`
- Token: `:emittedInTransaction`, `:tokenTransferFrom`, `:tokenTransferTo`, `:transferredToken`, `:transferredAmount`, `:hasTokenSymbol`, `:hasTokenName`, `:hasDecimals`
- Block: `:hasMiner`, `:hasGasLimit`, `:hasTxCount`
- Meta-transaction: `:initiatedBy`, `:executedBy`

Each property must include `rdfs:label`, two-sentence `rdfs:comment`, `:synonyms` with at least three comma-separated terms, `:exampleUsage`, `rdfs:domain`, and `rdfs:range`.

### Task 1: Create failing ontology validation tests

**Files:**
- Create: `tests/unit/test_ontology_extension.py`
- Later create: `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = ROOT / "src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl"
ETHKG = Namespace("https://thesis.example.org/eth-kg/")


@pytest.fixture(scope="module")
def ontology_graph() -> Graph:
    graph = Graph()
    graph.parse(ONTOLOGY_PATH, format="turtle")
    return graph


def _local_terms(graph: Graph, rdf_type) -> set:
    return {
        subject
        for subject in graph.subjects(RDF.type, rdf_type)
        if str(subject).startswith(str(ETHKG))
    }


def _sentence_count(text: str) -> int:
    return len(re.findall(r"[.!?](?:\\s|$)", text))


def test_extension_turtle_exists_and_parses(ontology_graph: Graph) -> None:
    assert ONTOLOGY_PATH.exists()
    assert len(ontology_graph) > 0


def test_extension_declares_required_number_of_terms(ontology_graph: Graph) -> None:
    classes = _local_terms(ontology_graph, OWL.Class)
    object_properties = _local_terms(ontology_graph, OWL.ObjectProperty)
    datatype_properties = _local_terms(ontology_graph, OWL.DatatypeProperty)
    assert len(classes) >= 15
    assert len(object_properties | datatype_properties) >= 25


def test_all_local_properties_have_schema_linker_metadata(ontology_graph: Graph) -> None:
    properties = _local_terms(ontology_graph, OWL.ObjectProperty) | _local_terms(
        ontology_graph, OWL.DatatypeProperty
    )
    assert properties

    for prop in sorted(properties, key=str):
        labels = list(ontology_graph.objects(prop, RDFS.label))
        comments = list(ontology_graph.objects(prop, RDFS.comment))
        synonyms = list(ontology_graph.objects(prop, ETHKG.synonyms))
        examples = list(ontology_graph.objects(prop, ETHKG.exampleUsage))
        domains = list(ontology_graph.objects(prop, RDFS.domain))
        ranges = list(ontology_graph.objects(prop, RDFS.range))

        assert labels, f"{prop} missing rdfs:label"
        assert comments, f"{prop} missing rdfs:comment"
        assert synonyms, f"{prop} missing :synonyms"
        assert examples, f"{prop} missing :exampleUsage"
        assert domains, f"{prop} missing rdfs:domain"
        assert ranges, f"{prop} missing rdfs:range"

        comment_text = str(comments[0])
        assert _sentence_count(comment_text) >= 2, f"{prop} comment has fewer than 2 sentences"

        synonym_terms = [term.strip() for term in str(synonyms[0]).split(",") if term.strip()]
        assert len(synonym_terms) >= 3, f"{prop} has fewer than 3 synonyms"
        assert isinstance(examples[0], Literal)
        assert "?" in str(examples[0]), f"{prop} example does not look like a SPARQL fragment"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_ontology_extension.py -q
```

Expected: fail because `eth-kg-extension-v0.1.0.ttl` does not exist.

### Task 2: Implement ontology TTL

**Files:**
- Create: `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`
- Test: `tests/unit/test_ontology_extension.py`

- [ ] **Step 1: Add the ontology header, annotation properties, classes, and properties**

Use prefixes:

```turtle
@prefix : <https://thesis.example.org/eth-kg/> .
@prefix ethon: <http://ethon.consensys.net/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
```

Declare `:synonyms` and `:exampleUsage` as `owl:AnnotationProperty`. Declare all classes and all properties listed in "Ontology Terms to Implement". Use `owl:ObjectProperty` for entity-to-entity relationships and `owl:DatatypeProperty` for literal values.

- [ ] **Step 2: Run focused test to verify it passes**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_ontology_extension.py -q
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_ontology_extension.py src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl
git commit -m "feat: add Ethereum KG ontology extension"
```

### Task 3: Add competency-question tests and catalogue

**Files:**
- Modify: `tests/unit/test_ontology_extension.py`
- Create: `src/nl2sparql/kg/ontology/competency-questions.md`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_ontology_extension.py`:

```python
COMPETENCY_QUESTIONS_PATH = ROOT / "src/nl2sparql/kg/ontology/competency-questions.md"


def test_competency_questions_document_required_coverage() -> None:
    text = COMPETENCY_QUESTIONS_PATH.read_text(encoding="utf-8")
    question_lines = re.findall(r"^- \\[x\\] CQ\\d+:", text, flags=re.MULTILINE)
    covered_lines = re.findall(r"Coverage: covered", text)
    assert len(question_lines) >= 30
    assert len(covered_lines) >= 24
    assert "## Trivial questions" in text
    assert "## Medium questions" in text
    assert "## Hard questions" in text
    assert "Classes:" in text
    assert "Properties:" in text
    assert "SPARQL sketch:" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_ontology_extension.py::test_competency_questions_document_required_coverage -q
```

Expected: fail because `competency-questions.md` does not exist.

- [ ] **Step 3: Create the catalogue**

Create 30 checked questions: 10 trivial, 10 medium, 10 hard. For each item include:

```markdown
- [x] CQ01: Count all transactions in a time range.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`
  - Properties: `:hasTimestamp`
  - SPARQL sketch:
    ```sparql
    SELECT (COUNT(?tx) AS ?count) WHERE {
      ?tx a :Transaction ;
          :hasTimestamp ?ts .
      FILTER(?ts >= "2024-01-01T00:00:00Z"^^xsd:dateTime)
    }
    ```
```

- [ ] **Step 4: Run focused test to verify it passes**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_ontology_extension.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_ontology_extension.py src/nl2sparql/kg/ontology/competency-questions.md
git commit -m "docs: add ontology competency questions"
```

### Task 4: Add ontology changelog and memory updates

**Files:**
- Create: `src/nl2sparql/kg/ontology/changelog.md`
- Modify: `docs/memory/03-ONTOLOGY_REFERENCE.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

- [ ] **Step 1: Write changelog**

Create `src/nl2sparql/kg/ontology/changelog.md` with:

```markdown
# Ethereum KG Ontology Changelog

## v0.1.0 — 2026-06-27

- Added local namespace `https://thesis.example.org/eth-kg/`.
- Added EthOn-based account, DeFi protocol, transaction, block, and token transfer classes.
- Added schema-linker-ready property metadata using `rdfs:label`, `rdfs:comment`, `:synonyms`, and `:exampleUsage`.
- Added 30 competency questions with class/property coverage and SPARQL sketches.
- Automated validation: `rdflib` parse and metadata tests.
- Manual Protégé validation: pending external GUI check with FaCT++ or HermiT.
```

- [ ] **Step 2: Update ontology reference**

Replace placeholder status in `docs/memory/03-ONTOLOGY_REFERENCE.md` with `v0.1.0 finalized in T2.1`, document class/property groups, and update the changelog table with `0.1.0`.

- [ ] **Step 3: Update decision log**

Add a 2026-06-27 entry: "Chốt ontology extension v0.1.0 cho Ethereum KG". Record namespace, EthOn subclass strategy, property metadata contract, and consequence for Phase 4 schema linker.

- [ ] **Step 4: Run docs/test validation**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_ontology_extension.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/kg/ontology/changelog.md docs/memory/03-ONTOLOGY_REFERENCE.md docs/memory/05-DECISION_LOG.md
git commit -m "docs: record ontology extension v0.1.0"
```

### Task 5: Mark T2.1 task complete and run final verification

**Files:**
- Modify: `docs/tasks/phase-2-kg/01-ontology-extension.md`

- [ ] **Step 1: Update task status**

Change task status from `todo` to `done`. Tick acceptance criteria that were verified automatically. Add a verification section listing:

- focused ontology test command and result;
- full unit test command and result;
- Protégé validation status as `manual pending` if not run locally.

- [ ] **Step 2: Run full verification**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest -q
```

Expected: all tests pass.

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Commit**

```bash
git add docs/tasks/phase-2-kg/01-ontology-extension.md
git commit -m "docs: mark T2.1 ontology extension complete"
```

## Self-Review

- Spec coverage: plan covers ontology TTL, changelog, competency questions, ontology reference, decision log, task checklist, and automated validation.
- Placeholder scan: no `TBD`, `TODO`, `implement later`, or unbounded "add appropriate" instructions remain.
- Type consistency: namespace, class names, property names, and file paths match the approved design.
