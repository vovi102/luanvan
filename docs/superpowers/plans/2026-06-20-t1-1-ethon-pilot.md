# T1.1 EthOn Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit the official EthOn ontology, inspect it reproducibly, and prove that its class, property, and subclass queries work against a local Fuseki `ethon-pilot` dataset.

**Architecture:** Keep the upstream Turtle file as the immutable source of truth. Put RDF parsing and deterministic inventory rendering in `ethon_pilot.py`, isolate Fuseki HTTP operations in `fuseki_pilot.py`, and keep the notebook as a thin executable walkthrough over those tested modules.

**Tech Stack:** Python 3.11, rdflib 7, urllib from the standard library, Apache Jena Fuseki in Docker, pytest, Ruff, Jupyter.

---

## File Structure

- Create `data/ontologies/EthOn.ttl`: complete upstream EthOn ontology.
- Create `data/ontologies/EthOn.sha256`: checksum plus upstream source URL.
- Create `src/nl2sparql/kg/ontology/__init__.py`: ontology package boundary.
- Create `src/nl2sparql/kg/ontology/ethon_pilot.py`: local parsing, inspection, query-file loading, and Markdown rendering.
- Create `src/nl2sparql/kg/ontology/fuseki_pilot.py`: authenticated, idempotent Fuseki pilot operations.
- Create `src/nl2sparql/kg/ontology/ethon-classes.md`: deterministic class inventory.
- Create `src/nl2sparql/kg/ontology/ethon-properties.md`: deterministic property inventory.
- Create `src/nl2sparql/kg/validation/ethon_smoke.sparql`: three standalone ontology queries.
- Create `notebooks/02_ethon_pilot.ipynb`: executable local and Fuseki verification walkthrough.
- Create `tests/unit/test_ethon_pilot.py`: ontology artifact and inventory tests.
- Create `tests/unit/test_fuseki_pilot.py`: HTTP behavior tests without Docker.
- Modify `docs/tasks/phase-1-pilot/01-load-ethon.md`: measured results and completion state.
- Modify `docs/memory/05-DECISION_LOG.md`: source, coverage, limitations, and T1.3 decision.

### Task 1: Commit and validate the upstream ontology

**Files:**
- Create: `data/ontologies/EthOn.ttl`
- Create: `data/ontologies/EthOn.sha256`
- Create: `tests/unit/test_ethon_pilot.py`

- [x] **Step 1: Write failing artifact tests**

Create `tests/unit/test_ethon_pilot.py` with:

```python
from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[2]
ETHON_PATH = ROOT / "data" / "ontologies" / "EthOn.ttl"
CHECKSUM_PATH = ROOT / "data" / "ontologies" / "EthOn.sha256"


def test_committed_ethon_parses_and_has_expected_scale() -> None:
    graph = Graph().parse(ETHON_PATH, format="turtle")

    assert len(graph) >= 1_000


def test_ethon_source_metadata_is_committed() -> None:
    metadata = CHECKSUM_PATH.read_text(encoding="utf-8")

    assert "sha256=" in metadata
    assert "https://raw.githubusercontent.com/ConsenSys/EthOn/" in metadata
```

- [x] **Step 2: Run the tests and confirm the missing-artifact failure**

Run:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py -v
```

Expected: FAIL because `data/ontologies/EthOn.ttl` does not exist.

- [x] **Step 3: Download the exact upstream file and record provenance**

Run:

```bash
mkdir -p data/ontologies
curl --fail --location \
  https://raw.githubusercontent.com/ConsenSys/EthOn/master/EthOn.ttl \
  --output data/ontologies/EthOn.ttl
sha256sum data/ontologies/EthOn.ttl
```

Create `data/ontologies/EthOn.sha256` with the actual command output in this format:

```text
source=https://raw.githubusercontent.com/ConsenSys/EthOn/master/EthOn.ttl
sha256=e73e19bf0d6bbb0e28b1497a73e4499ca78ee9c1e8c475fa31e7c821354ce71d
```

- [x] **Step 4: Re-run artifact tests**

Run the Step 2 command.

Expected: 2 tests PASS; parsed triple count is at least 1,000.

- [x] **Step 5: Commit the ontology source**

```bash
git add data/ontologies/EthOn.ttl data/ontologies/EthOn.sha256 tests/unit/test_ethon_pilot.py
git commit -m "feat(kg): commit official EthOn ontology"
```

### Task 2: Build deterministic ontology inspection helpers

**Files:**
- Create: `src/nl2sparql/kg/ontology/__init__.py`
- Create: `src/nl2sparql/kg/ontology/ethon_pilot.py`
- Modify: `tests/unit/test_ethon_pilot.py`

- [x] **Step 1: Add failing inspection and rendering tests**

Append to `tests/unit/test_ethon_pilot.py`:

```python
import hashlib

import pytest
from rdflib.namespace import OWL

from nl2sparql.kg.ontology.ethon_pilot import (
    inspect_ethon,
    load_ethon,
    render_class_inventory,
    render_property_inventory,
)


def test_inspect_ethon_finds_core_terms() -> None:
    inventory = inspect_ethon(load_ethon(ETHON_PATH))

    assert "http://ethon.consensys.net/Account" in inventory.classes
    assert "http://ethon.consensys.net/Block" in inventory.classes
    assert "http://ethon.consensys.net/Tx" in inventory.classes
    assert "http://ethon.consensys.net/from" in inventory.object_properties
    assert "http://ethon.consensys.net/txHash" in inventory.datatype_properties
    assert inventory.subclass_relations


def test_inventory_markdown_is_sorted_and_records_checksum() -> None:
    graph = load_ethon(ETHON_PATH)
    inventory = inspect_ethon(graph)
    checksum = hashlib.sha256(ETHON_PATH.read_bytes()).hexdigest()

    classes = render_class_inventory(inventory, checksum)
    properties = render_property_inventory(inventory, checksum)

    assert f"Source SHA-256: `{checksum}`" in classes
    assert classes.index("AccountConcept") < classes.index("BlockConcept")
    assert f"Source SHA-256: `{checksum}`" in properties
    assert "Object properties:" in properties
    assert "Datatype properties:" in properties


def test_load_ethon_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.ttl"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        load_ethon(empty)


def test_load_ethon_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="EthOn ontology not found"):
        load_ethon(tmp_path / "missing.ttl")
```

- [x] **Step 2: Run the focused tests and confirm import failure**

Run:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py -v
```

Expected: collection FAILS because `nl2sparql.kg.ontology.ethon_pilot` does not exist.

- [x] **Step 3: Implement the ontology helper**

Create `src/nl2sparql/kg/ontology/__init__.py` with a package docstring. Create
`src/nl2sparql/kg/ontology/ethon_pilot.py` with:

```python
"""Parse EthOn and produce deterministic ontology inventories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS


@dataclass(frozen=True)
class EthonInventory:
    """Sorted EthOn terms required by the pilot."""

    classes: tuple[str, ...]
    object_properties: tuple[str, ...]
    datatype_properties: tuple[str, ...]
    subclass_relations: tuple[tuple[str, str], ...]


def load_ethon(path: Path) -> Graph:
    """Load a non-empty local EthOn Turtle document."""
    if not path.exists():
        raise FileNotFoundError(f"EthOn ontology not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"EthOn ontology is empty: {path}")
    graph = Graph()
    graph.parse(path, format="turtle")
    if not graph:
        raise ValueError(f"EthOn ontology has no RDF statements: {path}")
    return graph


def inspect_ethon(graph: Graph) -> EthonInventory:
    """Return sorted class, property, and subclass inventories."""
    classes = _subjects(graph, RDF.type, OWL.Class)
    object_properties = _subjects(graph, RDF.type, OWL.ObjectProperty)
    datatype_properties = _subjects(graph, RDF.type, OWL.DatatypeProperty)
    subclass_relations = tuple(
        sorted(
            (str(child), str(parent))
            for child, parent in graph.subject_objects(RDFS.subClassOf)
            if isinstance(child, URIRef) and isinstance(parent, URIRef)
        )
    )
    if not classes:
        raise ValueError("EthOn ontology contains no OWL classes")
    if not object_properties and not datatype_properties:
        raise ValueError("EthOn ontology contains no RDF properties")
    return EthonInventory(classes, object_properties, datatype_properties, subclass_relations)


def render_class_inventory(inventory: EthonInventory, checksum: str) -> str:
    """Render the committed EthOn class inventory."""
    lines = [
        "# EthOn Classes",
        "",
        f"Source SHA-256: `{checksum}`",
        f"Total classes: {len(inventory.classes)}",
        "",
    ]
    lines.extend(f"- `{iri}` — {iri.rsplit('/', 1)[-1]}" for iri in inventory.classes)
    return "\n".join(lines) + "\n"


def render_property_inventory(inventory: EthonInventory, checksum: str) -> str:
    """Render object and datatype property inventories."""
    lines = [
        "# EthOn Properties",
        "",
        f"Source SHA-256: `{checksum}`",
        f"Object properties: {len(inventory.object_properties)}",
        f"Datatype properties: {len(inventory.datatype_properties)}",
        "",
        "## Object Properties",
        "",
    ]
    lines.extend(f"- `{iri}`" for iri in inventory.object_properties)
    lines.extend(["", "## Datatype Properties", ""])
    lines.extend(f"- `{iri}`" for iri in inventory.datatype_properties)
    return "\n".join(lines) + "\n"


def _subjects(graph: Graph, predicate: URIRef, obj: URIRef) -> tuple[str, ...]:
    return tuple(sorted(str(term) for term in graph.subjects(predicate, obj) if isinstance(term, URIRef)))
```

- [x] **Step 4: Run inspection tests and fix only contract mismatches**

Run the Step 2 command.

Expected: all tests in `test_ethon_pilot.py` PASS. If an upstream property is
declared under a more specific OWL/RDFS type, update the test to assert a core
property that is explicitly typed in `EthOn.ttl`; do not infer new triples.

- [x] **Step 5: Run Ruff and commit**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src/nl2sparql/kg/ontology tests/unit/test_ethon_pilot.py
git add src/nl2sparql/kg/ontology tests/unit/test_ethon_pilot.py
git commit -m "feat(kg): inspect EthOn ontology"
```

### Task 3: Store and validate the three smoke queries

**Files:**
- Create: `src/nl2sparql/kg/validation/ethon_smoke.sparql`
- Modify: `src/nl2sparql/kg/ontology/ethon_pilot.py`
- Modify: `tests/unit/test_ethon_pilot.py`

- [x] **Step 1: Add a failing query-file test**

Append to `tests/unit/test_ethon_pilot.py`:

```python
from rdflib.plugins.sparql import prepareQuery

from nl2sparql.kg.ontology.ethon_pilot import load_smoke_queries

QUERY_PATH = ROOT / "src" / "nl2sparql" / "kg" / "validation" / "ethon_smoke.sparql"


def test_ethon_smoke_file_contains_three_parseable_nonempty_queries() -> None:
    graph = load_ethon(ETHON_PATH)
    queries = load_smoke_queries(QUERY_PATH)

    assert len(queries) == 3
    for query in queries:
        prepareQuery(query)
        assert list(graph.query(query))
```

- [x] **Step 2: Run the focused test and confirm missing API/artifact failure**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py::test_ethon_smoke_file_contains_three_parseable_nonempty_queries -v
```

Expected: FAIL because `load_smoke_queries` or the query file is missing.

- [x] **Step 3: Add the query loader**

Add to `ethon_pilot.py`:

```python
QUERY_SEPARATOR = "# --- ETHON QUERY ---"


def load_smoke_queries(path: Path) -> tuple[str, ...]:
    """Load the three standalone EthOn smoke queries."""
    if not path.exists():
        raise FileNotFoundError(f"EthOn smoke query file not found: {path}")
    queries = tuple(part.strip() for part in path.read_text(encoding="utf-8").split(QUERY_SEPARATOR) if part.strip())
    if len(queries) != 3:
        raise ValueError(f"Expected 3 EthOn smoke queries, found {len(queries)}")
    return queries
```

- [x] **Step 4: Create the query artifact**

Create `src/nl2sparql/kg/validation/ethon_smoke.sparql` with exactly these three
segments, separated by `# --- ETHON QUERY ---`:

```sparql
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?class ?label WHERE {
  ?class a owl:Class .
  OPTIONAL { ?class rdfs:label ?label }
}
# --- ETHON QUERY ---
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?property ?domain ?range WHERE {
  ?property a owl:ObjectProperty .
  OPTIONAL { ?property rdfs:domain ?domain }
  OPTIONAL { ?property rdfs:range ?range }
}
# --- ETHON QUERY ---
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?subclass ?superclass WHERE {
  ?subclass rdfs:subClassOf ?superclass .
  ?subclass a owl:Class .
  ?superclass a owl:Class .
}
```

- [x] **Step 5: Run tests, Ruff, and commit**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py -v
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src/nl2sparql/kg/ontology tests/unit/test_ethon_pilot.py
git add src/nl2sparql/kg/ontology/ethon_pilot.py src/nl2sparql/kg/validation/ethon_smoke.sparql tests/unit/test_ethon_pilot.py
git commit -m "feat(kg): add EthOn smoke queries"
```

### Task 4: Implement a testable Fuseki pilot client

**Files:**
- Create: `src/nl2sparql/kg/ontology/fuseki_pilot.py`
- Create: `tests/unit/test_fuseki_pilot.py`

- [x] **Step 1: Write failing HTTP behavior tests**

Create `tests/unit/test_fuseki_pilot.py` with a `FakeTransport` that records method,
URL, headers, and body, then add these tests:

```python
from pathlib import Path

import pytest

from nl2sparql.kg.ontology.fuseki_pilot import FusekiError, FusekiPilotClient, HttpResponse


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse:
        self.calls.append((method, url, headers, body))
        return self.responses.pop(0)


def test_prepare_dataset_is_idempotent() -> None:
    transport = FakeTransport([HttpResponse(409, b"exists"), HttpResponse(200, b"cleared")])
    client = FusekiPilotClient("http://localhost:3030", "ethon-pilot", "admin", "secret", transport)

    client.prepare_dataset()

    assert transport.calls[0][0:2] == ("POST", "http://localhost:3030/$/datasets")
    assert b"dbName=ethon-pilot&dbType=mem" == transport.calls[0][3]
    assert transport.calls[1][1].endswith("/ethon-pilot/update")
    assert b"update=DROP+ALL" == transport.calls[1][3]


def test_upload_and_query_use_dataset_endpoints(tmp_path: Path) -> None:
    ontology = tmp_path / "EthOn.ttl"
    ontology.write_text("@prefix : <urn:test:> . :s :p :o .", encoding="utf-8")
    transport = FakeTransport([HttpResponse(200, b"uploaded"), HttpResponse(200, b'{"results":{"bindings":[{}]}}')])
    client = FusekiPilotClient("http://localhost:3030", "ethon-pilot", "admin", "secret", transport)

    client.upload_turtle(ontology)
    result = client.query("SELECT * WHERE { ?s ?p ?o }")

    assert transport.calls[0][1].endswith("/ethon-pilot/data")
    assert transport.calls[0][2]["Content-Type"] == "text/turtle"
    assert result["results"]["bindings"]


def test_http_failure_hides_password() -> None:
    transport = FakeTransport([HttpResponse(500, b"server error")])
    client = FusekiPilotClient("http://localhost:3030", "ethon-pilot", "admin", "secret", transport)

    with pytest.raises(FusekiError) as error:
        client.prepare_dataset()

    assert "secret" not in str(error.value)
    assert "500" in str(error.value)
```

- [x] **Step 2: Run tests and confirm import failure**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_fuseki_pilot.py -v
```

Expected: collection FAILS because `fuseki_pilot.py` does not exist.

- [x] **Step 3: Implement the client contracts**

Create `fuseki_pilot.py` with:

```python
"""Minimal authenticated Fuseki operations for the EthOn pilot."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class HttpTransport(Protocol):
    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse: ...


class UrllibTransport:
    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return HttpResponse(response.status, response.read())
        except HTTPError as error:
            return HttpResponse(error.code, error.read())


class FusekiError(RuntimeError):
    """Raised when a Fuseki pilot operation fails."""


class FusekiPilotClient:
    def __init__(self, base_url: str, dataset: str, username: str, password: str, transport: HttpTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset = dataset
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}
        self.transport = transport or UrllibTransport()

    def prepare_dataset(self) -> None:
        created = self._form("POST", f"{self.base_url}/$/datasets", {"dbName": self.dataset, "dbType": "mem"})
        if created.status not in {200, 201, 409}:
            self._raise("create dataset", created)
        cleared = self._form("POST", f"{self.base_url}/{self.dataset}/update", {"update": "DROP ALL"})
        if cleared.status not in {200, 204}:
            self._raise("clear dataset", cleared)

    def upload_turtle(self, path: Path) -> None:
        response = self.transport.request("POST", f"{self.base_url}/{self.dataset}/data", {**self.headers, "Content-Type": "text/turtle"}, path.read_bytes())
        if response.status not in {200, 201, 204}:
            self._raise("upload Turtle", response)

    def query(self, sparql: str) -> dict[str, Any]:
        response = self._form("POST", f"{self.base_url}/{self.dataset}/query", {"query": sparql}, accept="application/sparql-results+json")
        if response.status != 200:
            self._raise("query dataset", response)
        return json.loads(response.body)

    def _form(self, method: str, url: str, fields: dict[str, str], accept: str | None = None) -> HttpResponse:
        headers = {**self.headers, "Content-Type": "application/x-www-form-urlencoded"}
        if accept:
            headers["Accept"] = accept
        return self.transport.request(method, url, headers, urlencode(fields).encode())

    @staticmethod
    def _raise(operation: str, response: HttpResponse) -> None:
        body = response.body.decode("utf-8", errors="replace")[:500]
        raise FusekiError(f"Fuseki {operation} failed with HTTP {response.status}: {body}")
```

- [x] **Step 4: Run client tests and Ruff**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_fuseki_pilot.py -v
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src/nl2sparql/kg/ontology/fuseki_pilot.py tests/unit/test_fuseki_pilot.py
```

Expected: all client tests PASS and Ruff reports no errors. Apply formatting-only
line wraps where Ruff requires them without changing the tested behavior.

- [x] **Step 5: Commit the Fuseki client**

```bash
git add src/nl2sparql/kg/ontology/fuseki_pilot.py tests/unit/test_fuseki_pilot.py
git commit -m "feat(kg): add Fuseki EthOn pilot client"
```

### Task 5: Generate inventories and build the executable notebook

**Files:**
- Create: `src/nl2sparql/kg/ontology/ethon-classes.md`
- Create: `src/nl2sparql/kg/ontology/ethon-properties.md`
- Create: `notebooks/02_ethon_pilot.ipynb`
- Modify: `tests/unit/test_ethon_pilot.py`

- [x] **Step 1: Add failing committed-inventory tests**

Append to `tests/unit/test_ethon_pilot.py`:

```python
CLASS_DOC = ROOT / "src" / "nl2sparql" / "kg" / "ontology" / "ethon-classes.md"
PROPERTY_DOC = ROOT / "src" / "nl2sparql" / "kg" / "ontology" / "ethon-properties.md"


def test_committed_inventories_match_the_ontology() -> None:
    graph = load_ethon(ETHON_PATH)
    inventory = inspect_ethon(graph)
    checksum = hashlib.sha256(ETHON_PATH.read_bytes()).hexdigest()

    assert CLASS_DOC.read_text(encoding="utf-8") == render_class_inventory(inventory, checksum)
    assert PROPERTY_DOC.read_text(encoding="utf-8") == render_property_inventory(inventory, checksum)
```

- [x] **Step 2: Run the focused test and confirm missing-file failure**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py::test_committed_inventories_match_the_ontology -v
```

Expected: FAIL because `ethon-classes.md` does not exist.

- [x] **Step 3: Generate the exact committed inventories**

Run:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run python -c 'from hashlib import sha256; from pathlib import Path; from nl2sparql.kg.ontology.ethon_pilot import inspect_ethon, load_ethon, render_class_inventory, render_property_inventory; p=Path("data/ontologies/EthOn.ttl"); i=inspect_ethon(load_ethon(p)); h=sha256(p.read_bytes()).hexdigest(); Path("src/nl2sparql/kg/ontology/ethon-classes.md").write_text(render_class_inventory(i,h),encoding="utf-8"); Path("src/nl2sparql/kg/ontology/ethon-properties.md").write_text(render_property_inventory(i,h),encoding="utf-8")'
```

- [x] **Step 4: Create the notebook as a thin client**

Create `notebooks/02_ethon_pilot.ipynb` with executable Python cells equivalent to:

```python
import hashlib
import os
from pathlib import Path

from nl2sparql.kg.ontology.ethon_pilot import inspect_ethon, load_ethon, load_smoke_queries
from nl2sparql.kg.ontology.fuseki_pilot import FusekiPilotClient

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path.cwd().parent
ETHON_PATH = ROOT / "data" / "ontologies" / "EthOn.ttl"
QUERY_PATH = ROOT / "src" / "nl2sparql" / "kg" / "validation" / "ethon_smoke.sparql"
graph = load_ethon(ETHON_PATH)
inventory = inspect_ethon(graph)
checksum = hashlib.sha256(ETHON_PATH.read_bytes()).hexdigest()
print({"triples": len(graph), "classes": len(inventory.classes), "object_properties": len(inventory.object_properties), "datatype_properties": len(inventory.datatype_properties), "sha256": checksum})
```

```python
client = FusekiPilotClient(
    os.getenv("FUSEKI_URL", "http://localhost:3030"),
    "ethon-pilot",
    os.getenv("FUSEKI_ADMIN_USER", "admin"),
    os.getenv("FUSEKI_ADMIN_PASSWORD", "admin"),
)
client.prepare_dataset()
client.upload_turtle(ETHON_PATH)
```

```python
results = []
for index, query in enumerate(load_smoke_queries(QUERY_PATH), start=1):
    bindings = client.query(query)["results"]["bindings"]
    assert bindings, f"EthOn smoke query {index} returned no rows"
    results.append({"query": index, "rows": len(bindings)})
results
```

Include Markdown cells documenting the committed source, dataset name, and the
fact that no reasoning/inference is enabled. Do not save the password or an
Authorization header in cell output.

- [x] **Step 5: Run inventory tests and commit**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py -v
git add src/nl2sparql/kg/ontology/ethon-classes.md src/nl2sparql/kg/ontology/ethon-properties.md notebooks/02_ethon_pilot.ipynb tests/unit/test_ethon_pilot.py
git commit -m "docs(kg): add EthOn pilot inventory notebook"
```

### Task 6: Verify with Fuseki and close T1.1 documentation

**Files:**
- Modify: `docs/tasks/phase-1-pilot/01-load-ethon.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/superpowers/plans/2026-06-20-t1-1-ethon-pilot.md`

- [x] **Step 1: Start Fuseki and confirm container health**

```bash
docker compose -f infrastructure/docker/docker-compose.fuseki.yml up -d
docker compose -f infrastructure/docker/docker-compose.fuseki.yml ps
```

Expected: `nl2sparql-fuseki` is running and becomes healthy on port 3030.

- [x] **Step 2: Execute the notebook against real Fuseki**

```bash
JUPYTER_CONFIG_DIR=/tmp/t1-1-jupyter-config \
JUPYTER_DATA_DIR=/tmp/t1-1-jupyter-data \
JUPYTER_RUNTIME_DIR=/tmp/t1-1-jupyter-runtime \
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
uv run jupyter nbconvert --to notebook --execute notebooks/02_ethon_pilot.ipynb \
  --output /tmp/t1-1-ethon-pilot-verified.ipynb \
  --ExecutePreprocessor.timeout=120
```

Expected: execution succeeds; ontology triple count is at least 1,000 and all
three query result counts are greater than zero.

- [x] **Step 3: Query the real dataset count independently**

```bash
curl --fail --user admin:admin \
  --data-urlencode 'query=SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }' \
  -H 'Accept: application/sparql-results+json' \
  http://localhost:3030/ethon-pilot/query
```

Expected: HTTP 200 and the JSON binding contains a count of at least 1,000.

- [x] **Step 4: Record measured results and decision**

Change the task status to ``done — 2026-06-20`` and add the actual triple, class,
object-property, datatype-property, and subclass-relation counts printed by the
notebook. Add a reverse-chronological decision-log entry with:

```markdown
### 2026-06-20 — Commit EthOn 0.2 làm ontology nền cho pilot

- **Context:** T1.1 cần ontology tái lập để kiểm chứng Fuseki và làm namespace nền cho RML pilot T1.3.
- **Options considered:** Tải động mỗi lần; commit skeleton tối thiểu; commit toàn bộ ontology chính thức.
- **Decision:** Commit toàn bộ `EthOn.ttl`, giữ nguyên namespace `http://ethon.consensys.net/`, và chạy truy vấn không inference.
- **Rationale:** File nhỏ, loại bỏ phụ thuộc mạng, đồng thời giữ đầy đủ Account, Block, Tx và các property cốt lõi.
- **Consequences:** T1.3 có thể tham chiếu trực tiếp EthOn; DEX, lending, mixer, token standards và dữ liệu hậu PoS vẫn cần extension ở Phase 2.
- **Revisit:** T2.1 khi thiết kế ontology extension.
- **Linked:** `docs/tasks/phase-1-pilot/01-load-ethon.md`, `data/ontologies/EthOn.ttl`.
```

Also replace the plan checkboxes completed during execution from `[ ]` to `[x]`.

- [x] **Step 5: Run fresh final verification**

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest -q
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src tests scripts
git diff --check
git status --short
```

Expected: all tests pass, Ruff reports no errors, `git diff --check` is empty,
and status lists only the intended T1.1 documentation changes.

- [x] **Step 6: Commit task completion**

```bash
git add docs/tasks/phase-1-pilot/01-load-ethon.md docs/memory/05-DECISION_LOG.md docs/superpowers/plans/2026-06-20-t1-1-ethon-pilot.md
git commit -m "docs(kg): complete EthOn pilot"
```

- [x] **Step 7: Verify the final branch state**

```bash
git status --short --branch
git log --oneline --decorate -6
```

Expected: branch `feat/t1-1-ethon-pilot` is clean and contains the design,
ontology, implementation, notebook, verification documentation, and completion commits.
