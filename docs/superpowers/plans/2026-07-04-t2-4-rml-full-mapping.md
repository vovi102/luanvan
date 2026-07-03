# T2.4 RML Full Mapping Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the testable T2.4 RML full mapping scaffold without running the expensive full KG materialization.

**Architecture:** Add a full RML mapping beside the pilot mapping and a dedicated runner beside the pilot runner. Keep large-run risk behind CLI guardrails while proving behavior through small fixture CSVs and Morph-KGC materialization in unit tests.

**Tech Stack:** Python 3.11, Morph-KGC, RDFLib, pytest, project-local `uv`.

---

## Files

- Create `src/nl2sparql/kg/rml/full_mapping.ttl`: production RML TriplesMaps for transactions, blocks, token transfers, contracts, and prepared entity labels.
- Create `src/nl2sparql/kg/rml/run_morph_full.py`: full-run input validation, dictionary preparation, Morph-KGC config, materialization, output validation, and CLI.
- Create `tests/unit/test_rml_full.py`: focused T2.4 tests.
- Create fixture CSVs under `tests/fixtures/rml/full/`: `transactions.csv`, `blocks.csv`, `token_transfers.csv`, `contracts.csv`, and `entities.json`.
- Modify `docs/tasks/phase-2-kg/04-rml-full-mapping.md`: record scaffold status and verification evidence while leaving live acceptance unchecked.

## Task 1: Runner Skeleton and Input Validation

**Files:**
- Create: `src/nl2sparql/kg/rml/run_morph_full.py`
- Create: `tests/unit/test_rml_full.py`

- [ ] **Step 1: Write failing tests for path resolution and missing-file reporting**

```python
from pathlib import Path

import pytest

from nl2sparql.kg.rml.run_morph_full import (
    FullMaterializationError,
    required_full_input_paths,
    validate_required_files,
)


def test_required_full_input_paths_resolve_all_full_sources(tmp_path: Path) -> None:
    assert required_full_input_paths(tmp_path) == (
        tmp_path / "data/raw/full/transactions.csv",
        tmp_path / "data/raw/full/blocks.csv",
        tmp_path / "data/raw/full/token_transfers.csv",
        tmp_path / "data/raw/full/contracts.csv",
        tmp_path / "data/raw/full/entities.csv",
    )


def test_validate_required_files_lists_every_missing_full_path(tmp_path: Path) -> None:
    mapping = tmp_path / "full_mapping.ttl"
    inputs = required_full_input_paths(tmp_path)

    with pytest.raises(FullMaterializationError) as caught:
        validate_required_files(mapping, inputs)

    message = str(caught.value)
    assert str(mapping) in message
    for path in inputs:
        assert str(path) in message
```

- [ ] **Step 2: Run RED**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest tests/unit/test_rml_full.py -q
```

Expected: import fails because `run_morph_full.py` does not exist.

- [ ] **Step 3: Implement minimal runner skeleton**

```python
"""Run the T2.4 full Morph-KGC mapping scaffold."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "src/nl2sparql/kg/rml/full_mapping.ttl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/processed/full/output.nt"
DEFAULT_DICTIONARY_PATH = PROJECT_ROOT / "src/nl2sparql/linking/dictionary/entities.json"
DEFAULT_ENTITIES_CSV_PATH = PROJECT_ROOT / "data/raw/full/entities.csv"
MINIMUM_FULL_TRIPLES = 1_000


class FullMaterializationError(RuntimeError):
    """Report invalid full RML inputs or outputs."""


def required_full_input_paths(root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return the CSV paths required by T2.4 full materialization."""
    full_dir = root / "data/raw/full"
    return (
        full_dir / "transactions.csv",
        full_dir / "blocks.csv",
        full_dir / "token_transfers.csv",
        full_dir / "contracts.csv",
        full_dir / "entities.csv",
    )


def validate_required_files(mapping_path: Path, input_paths: Sequence[Path]) -> None:
    """Fail once with every missing mapping or input path."""
    missing = [path for path in (mapping_path, *input_paths) if not path.is_file()]
    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise FullMaterializationError(f"Missing RML full files:\n{rendered}")
```

- [ ] **Step 4: Run GREEN**

Run the same focused pytest command.

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/kg/rml/run_morph_full.py tests/unit/test_rml_full.py
git commit -m "feat(kg): add full RML runner skeleton"
```

## Task 2: Dictionary Preparation and Morph-KGC Config

**Files:**
- Modify: `src/nl2sparql/kg/rml/run_morph_full.py`
- Modify: `tests/unit/test_rml_full.py`

- [ ] **Step 1: Write failing tests for entity CSV preparation and config generation**

```python
import csv
import json
from pathlib import Path

from nl2sparql.kg.rml.run_morph_full import (
    build_morph_config,
    prepare_entities_csv,
)


def test_prepare_entities_csv_flattens_dictionary_for_rml(tmp_path: Path) -> None:
    dictionary = tmp_path / "entities.json"
    output = tmp_path / "entities.csv"
    dictionary.write_text(
        json.dumps(
            [
                {
                    "address": "0xABCDEF0000000000000000000000000000000000",
                    "address_lower": "0xabcdef0000000000000000000000000000000000",
                    "primary_label": "Binance Hot Wallet",
                    "owner": "Binance",
                    "category": "exchange",
                    "concept_class": "ExchangeAccount",
                    "aliases": ["binance", "binance wallet"],
                }
            ]
        ),
        encoding="utf-8",
    )

    count = prepare_entities_csv(dictionary, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert count == 1
    assert rows == [
        {
            "address": "0xabcdef0000000000000000000000000000000000",
            "primary_label": "Binance Hot Wallet",
            "owner": "Binance",
            "category": "exchange",
            "concept_class": "ExchangeAccount",
            "aliases": "binance|binance wallet",
        }
    ]


def test_build_morph_config_uses_nt_output_and_process_count(tmp_path: Path) -> None:
    mapping = tmp_path / "full_mapping.ttl"

    config = build_morph_config(mapping, number_of_processes=2)

    assert "output_format: N-TRIPLES" in config
    assert "number_of_processes: 2" in config
    assert f"mappings: {mapping.resolve()}" in config
```

- [ ] **Step 2: Run RED**

Run:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest tests/unit/test_rml_full.py -q
```

Expected: fail because `prepare_entities_csv()` and `build_morph_config()` are missing.

- [ ] **Step 3: Implement dictionary preparation and config builder**

```python
import csv
import json
from typing import Any


ENTITY_CSV_FIELDS = (
    "address",
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "aliases",
)


def prepare_entities_csv(
    dictionary_path: Path = DEFAULT_DICTIONARY_PATH,
    output_path: Path = DEFAULT_ENTITIES_CSV_PATH,
) -> int:
    """Convert dictionary JSON to a flat CSV source for Morph-KGC."""
    entities: list[dict[str, Any]] = json.loads(dictionary_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENTITY_CSV_FIELDS)
        writer.writeheader()
        for entity in entities:
            aliases = entity.get("aliases") or []
            writer.writerow(
                {
                    "address": str(entity.get("address_lower") or entity["address"]).lower(),
                    "primary_label": entity.get("primary_label", ""),
                    "owner": entity.get("owner", ""),
                    "category": entity.get("category", ""),
                    "concept_class": entity.get("concept_class", "Account"),
                    "aliases": "|".join(str(alias) for alias in aliases),
                }
            )
    return len(entities)


def build_morph_config(
    mapping_path: Path,
    output_format: str = "N-TRIPLES",
    number_of_processes: int = 4,
) -> str:
    """Build the in-memory Morph-KGC configuration for the full mapping."""
    return (
        "[CONFIGURATION]\n"
        f"output_format: {output_format}\n"
        f"number_of_processes: {number_of_processes}\n\n"
        "[DataSource1]\n"
        f"mappings: {mapping_path.resolve()}\n"
    )
```

- [ ] **Step 4: Run GREEN**

Run focused pytest again.

Expected: all current tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/kg/rml/run_morph_full.py tests/unit/test_rml_full.py
git commit -m "feat(kg): prepare full RML entity source"
```

## Task 3: Full Mapping File and Static Validation

**Files:**
- Create: `src/nl2sparql/kg/rml/full_mapping.ttl`
- Modify: `tests/unit/test_rml_full.py`

- [ ] **Step 1: Write failing static mapping test**

```python
from rdflib import Graph

ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = ROOT / "src/nl2sparql/kg/rml/full_mapping.ttl"


def test_full_mapping_parses_and_declares_expected_sources() -> None:
    graph = Graph().parse(MAPPING_PATH, format="turtle")
    text = MAPPING_PATH.read_text(encoding="utf-8")

    assert len(graph) > 0
    assert text.count("a rr:TriplesMap") == 5
    assert 'rml:source "data/raw/full/transactions.csv"' in text
    assert 'rml:source "data/raw/full/blocks.csv"' in text
    assert 'rml:source "data/raw/full/token_transfers.csv"' in text
    assert 'rml:source "data/raw/full/contracts.csv"' in text
    assert 'rml:source "data/raw/full/entities.csv"' in text
    for predicate in (
        ":hasFrom",
        ":hasTo",
        ":includedInBlock",
        ":emittedInTransaction",
        ":tokenTransferFrom",
        ":tokenTransferTo",
        ":transferredToken",
        ":hasLabel",
        ":hasAlias",
    ):
        assert predicate in text
```

- [ ] **Step 2: Run RED**

Run focused pytest.

Expected: fail because `full_mapping.ttl` does not exist.

- [ ] **Step 3: Add production full mapping**

Create `src/nl2sparql/kg/rml/full_mapping.ttl` with five TriplesMaps. Use:

```turtle
@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix rml: <http://semweb.mmlab.be/ns/rml#> .
@prefix ql: <http://semweb.mmlab.be/ns/ql#> .
@prefix : <https://thesis.example.org/eth-kg/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<#TransactionMap> a rr:TriplesMap ;
    rml:logicalSource [
        rml:source "data/raw/full/transactions.csv" ;
        rml:referenceFormulation ql:CSV
    ] ;
    rr:subjectMap [
        rr:template "https://thesis.example.org/eth-kg/tx/{hash}" ;
        rr:class :Transaction
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasFrom ;
        rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/addr/{from_address}" ; rr:termType rr:IRI ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasTo ;
        rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/addr/{to_address}" ; rr:termType rr:IRI ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasValue ;
        rr:objectMap [ rml:reference "value" ; rr:datatype xsd:decimal ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasGasUsed ;
        rr:objectMap [ rml:reference "gas" ; rr:datatype xsd:integer ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasGasPrice ;
        rr:objectMap [ rml:reference "gas_price" ; rr:datatype xsd:decimal ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasReceiptStatus ;
        rr:objectMap [ rml:reference "receipt_status" ; rr:datatype xsd:boolean ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasBlockNumber ;
        rr:objectMap [ rml:reference "block_number" ; rr:datatype xsd:integer ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :hasTimestamp ;
        rr:objectMap [ rml:reference "block_timestamp" ; rr:datatype xsd:dateTime ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate :includedInBlock ;
        rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/block/{block_number}" ; rr:termType rr:IRI ]
    ] .
```

Then add analogous `BlockMap`, `TokenTransferMap`, `ContractMap`, and `AccountLabelMap` using the ontology predicates in the spec.

- [ ] **Step 4: Run GREEN**

Run focused pytest.

Expected: static mapping tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/kg/rml/full_mapping.ttl tests/unit/test_rml_full.py
git commit -m "feat(kg): add full RML mapping scaffold"
```

## Task 4: Fixture Materialization and Output Validation

**Files:**
- Create fixtures under `tests/fixtures/rml/full/`
- Modify: `src/nl2sparql/kg/rml/run_morph_full.py`
- Modify: `tests/unit/test_rml_full.py`

- [ ] **Step 1: Add fixture CSV and dictionary files**

Create:

- `tests/fixtures/rml/full/transactions.csv`
- `tests/fixtures/rml/full/blocks.csv`
- `tests/fixtures/rml/full/token_transfers.csv`
- `tests/fixtures/rml/full/contracts.csv`
- `tests/fixtures/rml/full/entities.json`

Use two transactions, one block, one token transfer, one contract, and two labeled entities. Include one transaction with empty `to_address`.

- [ ] **Step 2: Write failing materialization test**

```python
from decimal import Decimal
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from nl2sparql.kg.rml.run_morph_full import materialize_full, validate_full_output

EX = Namespace("https://thesis.example.org/eth-kg/")
FIXTURE_DIR = ROOT / "tests/fixtures/rml/full"


def _fixture_mapping(tmp_path: Path) -> Path:
    fixture_entities = tmp_path / "entities.csv"
    prepare_entities_csv(FIXTURE_DIR / "entities.json", fixture_entities)
    fixture_mapping = tmp_path / "full_mapping.ttl"
    mapping_text = MAPPING_PATH.read_text(encoding="utf-8")
    replacements = {
        "data/raw/full/transactions.csv": (FIXTURE_DIR / "transactions.csv").as_posix(),
        "data/raw/full/blocks.csv": (FIXTURE_DIR / "blocks.csv").as_posix(),
        "data/raw/full/token_transfers.csv": (FIXTURE_DIR / "token_transfers.csv").as_posix(),
        "data/raw/full/contracts.csv": (FIXTURE_DIR / "contracts.csv").as_posix(),
        "data/raw/full/entities.csv": fixture_entities.as_posix(),
    }
    for old, new in replacements.items():
        mapping_text = mapping_text.replace(old, new)
    fixture_mapping.write_text(mapping_text, encoding="utf-8")
    return fixture_mapping


def test_materialize_full_fixture_emits_core_kg_shapes(tmp_path: Path) -> None:
    output = tmp_path / "output.nt"

    graph = materialize_full(_fixture_mapping(tmp_path), output, minimum_triples=35)

    assert output.is_file()
    assert len(graph) >= 35
    assert validate_full_output(output, minimum_triples=35) == len(graph)
    assert (EX["tx/0xtx1"], RDF.type, EX.Transaction) in graph
    assert (EX["block/19000000"], RDF.type, EX.Block) in graph
    assert (EX["transfer/0xtx1-0"], RDF.type, EX.TokenTransfer) in graph
    assert (EX["addr/0x2222222222222222222222222222222222222222"], RDF.type, EX.ContractAccount) in graph
    assert (EX["addr/0x1111111111111111111111111111111111111111"], RDF.type, EX.ExchangeAccount) in graph
    value = next(graph.objects(EX["tx/0xtx1"], EX.hasValue))
    assert value.datatype == XSD.decimal
    assert value.toPython() == Decimal("2000000000000000000")
    assert (EX["tx/0xtx1"], EX.includedInBlock, EX["block/19000000"]) in graph
    assert (EX["transfer/0xtx1-0"], EX.emittedInTransaction, EX["tx/0xtx1"]) in graph
    assert URIRef(f"{EX}addr/") not in set(graph.all_nodes())
```

- [ ] **Step 3: Run RED**

Run focused pytest.

Expected: fail because `materialize_full()` and `validate_full_output()` are missing.

- [ ] **Step 4: Implement materialization and validation**

Add imports:

```python
import morph_kgc
from rdflib import Graph
```

Add functions:

```python
def materialize_full(
    mapping_path: Path,
    output_path: Path,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
) -> Graph:
    """Materialize, serialize, reparse, and validate the full mapping."""
    graph = morph_kgc.materialize(build_morph_config(mapping_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_path, format="nt")
    validate_full_output(output_path, minimum_triples=minimum_triples)
    return Graph().parse(output_path, format="nt")


def validate_full_output(
    output_path: Path,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
) -> int:
    """Parse an existing full output artifact and validate triple count."""
    if not output_path.is_file():
        raise FullMaterializationError(f"Missing full RML output: {output_path}")
    graph = Graph().parse(output_path, format="nt")
    if len(graph) < minimum_triples:
        raise FullMaterializationError(
            f"Morph-KGC produced {len(graph)} triples; minimum is {minimum_triples}"
        )
    return len(graph)
```

- [ ] **Step 5: Run GREEN**

Run focused pytest.

Expected: all T2.4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/nl2sparql/kg/rml/run_morph_full.py tests/unit/test_rml_full.py tests/fixtures/rml/full
git commit -m "test(kg): verify full RML fixture materialization"
```

## Task 5: CLI Guardrails and Documentation Evidence

**Files:**
- Modify: `src/nl2sparql/kg/rml/run_morph_full.py`
- Modify: `tests/unit/test_rml_full.py`
- Modify: `docs/tasks/phase-2-kg/04-rml-full-mapping.md`

- [ ] **Step 1: Write failing CLI guardrail tests**

```python
from nl2sparql.kg.rml.run_morph_full import main, parse_args


def test_parse_args_defaults_to_guarded_full_run() -> None:
    args = parse_args([])

    assert args.force is False
    assert args.fixture_mode is False
    assert args.prepare_only is False


def test_main_prepare_only_writes_entities_csv(tmp_path: Path) -> None:
    output = tmp_path / "entities.csv"

    status = main(
        [
            "--prepare-only",
            "--dictionary",
            str(FIXTURE_DIR / "entities.json"),
            "--entities-csv",
            str(output),
        ]
    )

    assert status == 0
    assert output.is_file()


def test_main_refuses_live_materialization_without_force(tmp_path: Path) -> None:
    status = main(["--root", str(tmp_path)])

    assert status == 2
```

- [ ] **Step 2: Run RED**

Run focused pytest.

Expected: fail because CLI functions are missing.

- [ ] **Step 3: Implement CLI**

Add argparse parser and `main()`:

```python
import argparse


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the full RML runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY_PATH)
    parser.add_argument("--entities-csv", type=Path, default=DEFAULT_ENTITIES_CSV_PATH)
    parser.add_argument("--minimum-triples", type=int, default=MINIMUM_FULL_TRIPLES)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run preparation or guarded full materialization."""
    args = parse_args(argv)
    count = prepare_entities_csv(args.dictionary.resolve(), args.entities_csv.resolve())
    if args.prepare_only:
        print(f"Prepared {count} entity rows: {args.entities_csv.resolve()}")
        return 0
    if not args.force and not args.fixture_mode:
        print("Refusing full materialization without --force or --fixture-mode.")
        return 2
    inputs = required_full_input_paths(args.root.resolve())
    validate_required_files(args.mapping.resolve(), inputs)
    graph = materialize_full(
        args.mapping.resolve(),
        args.output.resolve(),
        minimum_triples=args.minimum_triples,
    )
    print(f"Morph-KGC full triples: {len(graph)}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run GREEN**

Run focused pytest and CLI help:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest tests/unit/test_rml_full.py -q

UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run python src/nl2sparql/kg/rml/run_morph_full.py --help
```

Expected: pytest passes and help exits `0`.

- [ ] **Step 5: Update task documentation**

Update `docs/tasks/phase-2-kg/04-rml-full-mapping.md`:

- Keep live acceptance criteria unchecked.
- Set `## Trạng thái` to `scaffold done; live materialization pending`.
- Add evidence commands for focused tests, full tests, and CLI help.
- State that full Morph-KGC, TDB2 load, triple count, and query benchmark are not yet claimed.

- [ ] **Step 6: Run final verification**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run pytest -q

git diff --check
```

Expected: all tests pass and diff check exits `0`.

- [ ] **Step 7: Commit**

```bash
git add src/nl2sparql/kg/rml/run_morph_full.py tests/unit/test_rml_full.py docs/tasks/phase-2-kg/04-rml-full-mapping.md
git commit -m "feat(kg): guard full RML scaffold execution"
```
