"""Tests for the T1.3 RML pilot."""

from decimal import Decimal
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from nl2sparql.kg.rml.run_morph_pilot import (
    PilotMaterializationError,
    build_morph_config,
    materialize_pilot,
    required_input_paths,
    validate_required_files,
)

ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = ROOT / "src/nl2sparql/kg/rml/pilot_mapping.ttl"
FIXTURE_DIR = ROOT / "tests/fixtures/rml"
EX = Namespace("https://thesis.example.org/eth-kg/")


def test_required_input_paths_resolve_both_pilot_sources(tmp_path: Path) -> None:
    assert required_input_paths(tmp_path) == (
        tmp_path / "data/raw/pilot/transactions_pilot.csv",
        tmp_path / "data/raw/pilot/blocks_pilot.csv",
    )


def test_validate_required_files_lists_every_missing_path(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.ttl"
    transactions, blocks = required_input_paths(tmp_path)

    with pytest.raises(PilotMaterializationError) as caught:
        validate_required_files(mapping, (transactions, blocks))

    message = str(caught.value)
    assert str(mapping) in message
    assert str(transactions) in message
    assert str(blocks) in message


def test_build_morph_config_uses_absolute_mapping_path(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.ttl"

    config = build_morph_config(mapping)

    assert config == f"[DataSource1]\nmappings: {mapping.resolve()}\n"


def test_production_mapping_parses_and_declares_both_sources() -> None:
    graph = Graph().parse(MAPPING_PATH, format="turtle")
    text = MAPPING_PATH.read_text(encoding="utf-8")

    assert len(graph) > 0
    assert text.count("a rr:TriplesMap") == 2
    assert 'rml:source "data/raw/pilot/transactions_pilot.csv"' in text
    assert 'rml:source "data/raw/pilot/blocks_pilot.csv"' in text
    assert 'rr:template "https://thesis.example.org/eth-kg/addr/{to_address}"' in text


def _fixture_mapping(tmp_path: Path) -> Path:
    fixture_mapping = tmp_path / "fixture_mapping.ttl"
    mapping_text = MAPPING_PATH.read_text(encoding="utf-8")
    mapping_text = mapping_text.replace(
        "data/raw/pilot/transactions_pilot.csv",
        (FIXTURE_DIR / "transactions.csv").as_posix(),
    ).replace(
        "data/raw/pilot/blocks_pilot.csv",
        (FIXTURE_DIR / "blocks.csv").as_posix(),
    )
    fixture_mapping.write_text(mapping_text, encoding="utf-8")
    return fixture_mapping


def test_morph_materializes_typed_fixture_and_omits_empty_recipient(tmp_path: Path) -> None:
    output = tmp_path / "output.ttl"

    graph = materialize_pilot(_fixture_mapping(tmp_path), output, minimum_triples=20)

    assert len(graph) == 20
    assert output.is_file()
    assert (EX["tx/0xtx1"], RDF.type, EX.Transaction) in graph
    value = next(graph.objects(EX["tx/0xtx1"], EX.hasValue))
    assert value.datatype == XSD.decimal
    assert value.toPython() == Decimal("2000000000000000000")
    assert (EX["tx/0xtx2"], EX.hasToAddress, None) not in graph
    assert URIRef(f"{EX}addr/") not in set(graph.all_nodes())


def test_materialize_rejects_graph_below_minimum(tmp_path: Path) -> None:
    with pytest.raises(PilotMaterializationError, match="20 triples; minimum is 21"):
        materialize_pilot(
            _fixture_mapping(tmp_path),
            tmp_path / "small.ttl",
            minimum_triples=21,
        )
