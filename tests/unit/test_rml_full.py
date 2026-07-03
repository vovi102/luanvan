"""Tests for the T2.4 full RML mapping scaffold."""

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from nl2sparql.kg.rml.run_morph_full import (
    FullMaterializationError,
    build_morph_config,
    main,
    materialize_full,
    parse_args,
    prepare_entities_csv,
    required_full_input_paths,
    validate_full_output,
    validate_required_files,
)

ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = ROOT / "src/nl2sparql/kg/rml/full_mapping.ttl"
FIXTURE_DIR = ROOT / "tests/fixtures/rml/full"
EX = Namespace("https://thesis.example.org/eth-kg/")


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


def _fixture_mapping(tmp_path: Path) -> Path:
    fixture_entities = tmp_path / "entities.csv"
    prepare_entities_csv(FIXTURE_DIR / "entities.json", fixture_entities)
    fixture_mapping = tmp_path / "full_mapping.ttl"
    mapping_text = MAPPING_PATH.read_text(encoding="utf-8")
    replacements = {
        "data/raw/full/transactions.csv": (FIXTURE_DIR / "transactions.csv").as_posix(),
        "data/raw/full/blocks.csv": (FIXTURE_DIR / "blocks.csv").as_posix(),
        "data/raw/full/token_transfers.csv": (
            FIXTURE_DIR / "token_transfers.csv"
        ).as_posix(),
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
    assert (
        EX["addr/0x2222222222222222222222222222222222222222"],
        RDF.type,
        EX.ContractAccount,
    ) in graph
    assert (
        EX["addr/0x1111111111111111111111111111111111111111"],
        RDF.type,
        EX.ExchangeAccount,
    ) in graph
    value = next(graph.objects(EX["tx/0xtx1"], EX.hasValue))
    assert value.datatype == XSD.decimal
    assert value.toPython() == Decimal("2000000000000000000")
    assert (EX["tx/0xtx1"], EX.includedInBlock, EX["block/19000000"]) in graph
    assert (
        EX["transfer/0xtx1-0"],
        EX.emittedInTransaction,
        EX["tx/0xtx1"],
    ) in graph
    assert URIRef(f"{EX}addr/") not in set(graph.all_nodes())


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
    output = tmp_path / "entities.csv"

    status = main(
        [
            "--root",
            str(tmp_path),
            "--dictionary",
            str(FIXTURE_DIR / "entities.json"),
            "--entities-csv",
            str(output),
        ]
    )

    assert status == 2
    assert not output.exists()
