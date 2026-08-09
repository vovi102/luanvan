"""Tests for the T2.4 full RML mapping scaffold."""

import csv
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from nl2sparql.kg.rml import run_morph_full
from nl2sparql.kg.rml.run_morph_full import (
    FullMaterializationError,
    build_morph_config,
    main,
    materialize_full,
    materialize_full_chunked,
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


def test_materialize_full_chunked_limits_sources_and_appends_output(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for filename in ("transactions.csv", "blocks.csv", "token_transfers.csv", "contracts.csv"):
        shutil.copyfile(FIXTURE_DIR / filename, input_dir / filename)
    prepare_entities_csv(FIXTURE_DIR / "entities.json", input_dir / "entities.csv")
    output = tmp_path / "chunked-output.nt"

    triple_count = materialize_full_chunked(
        mapping_path=MAPPING_PATH,
        input_dir=input_dir,
        output_path=output,
        work_dir=tmp_path / "chunks",
        chunk_rows=1,
        minimum_triples=35,
        number_of_processes=1,
    )
    graph = Graph().parse(output, format="nt")

    assert output.is_file()
    assert triple_count == len(graph)
    assert (EX["tx/0xtx1"], RDF.type, EX.Transaction) in graph
    assert (EX["transfer/0xtx1-0"], RDF.type, EX.TokenTransfer) in graph
    assert (
        EX["addr/0x1111111111111111111111111111111111111111"],
        RDF.type,
        EX.ExchangeAccount,
    ) in graph
    assert URIRef(f"{EX}addr/") not in set(graph.all_nodes())


def test_materialize_full_chunked_resumes_completed_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for filename in ("transactions.csv", "blocks.csv", "token_transfers.csv", "contracts.csv"):
        shutil.copyfile(FIXTURE_DIR / filename, input_dir / filename)
    prepare_entities_csv(FIXTURE_DIR / "entities.json", input_dir / "entities.csv")
    output = tmp_path / "chunked-output.nt"
    work_dir = tmp_path / "chunks"
    expected_triples = materialize_full_chunked(
        mapping_path=MAPPING_PATH,
        input_dir=input_dir,
        output_path=output,
        work_dir=work_dir,
        chunk_rows=1,
        minimum_triples=35,
        number_of_processes=1,
    )
    output.unlink()

    def fail_if_materialized(*args: object, **kwargs: object) -> int:
        raise AssertionError("completed chunks must not be materialized again")

    monkeypatch.setattr(run_morph_full, "_materialize_mapping_to_nt", fail_if_materialized)

    resumed_triples = materialize_full_chunked(
        mapping_path=MAPPING_PATH,
        input_dir=input_dir,
        output_path=output,
        work_dir=work_dir,
        chunk_rows=1,
        minimum_triples=35,
        number_of_processes=1,
        resume=True,
    )

    assert resumed_triples == expected_triples
    assert len(Graph().parse(output, format="nt")) == expected_triples


def test_materialize_full_chunked_rejects_incompatible_resume(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for filename in ("transactions.csv", "blocks.csv", "token_transfers.csv", "contracts.csv"):
        shutil.copyfile(FIXTURE_DIR / filename, input_dir / filename)
    prepare_entities_csv(FIXTURE_DIR / "entities.json", input_dir / "entities.csv")
    output = tmp_path / "chunked-output.nt"
    work_dir = tmp_path / "chunks"
    materialize_full_chunked(
        mapping_path=MAPPING_PATH,
        input_dir=input_dir,
        output_path=output,
        work_dir=work_dir,
        chunk_rows=1,
        minimum_triples=35,
        number_of_processes=1,
    )

    with pytest.raises(FullMaterializationError, match="does not match"):
        materialize_full_chunked(
            mapping_path=MAPPING_PATH,
            input_dir=input_dir,
            output_path=output,
            work_dir=work_dir,
            chunk_rows=2,
            minimum_triples=1,
            number_of_processes=1,
            resume=True,
        )


def test_materialize_full_chunked_rebuilds_uncommitted_chunk(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for filename in ("transactions.csv", "blocks.csv", "token_transfers.csv", "contracts.csv"):
        shutil.copyfile(FIXTURE_DIR / filename, input_dir / filename)
    prepare_entities_csv(FIXTURE_DIR / "entities.json", input_dir / "entities.csv")
    output = tmp_path / "chunked-output.nt"
    work_dir = tmp_path / "chunks"
    expected_triples = materialize_full_chunked(
        mapping_path=MAPPING_PATH,
        input_dir=input_dir,
        output_path=output,
        work_dir=work_dir,
        chunk_rows=1,
        minimum_triples=35,
        number_of_processes=1,
    )
    first_chunk = work_dir / "chunk-00000"
    (first_chunk / "complete.json").unlink()
    (first_chunk / "output.nt").write_text(
        "<https://example.org/s> <https://example.org/p> <https://example.org/o> .\n",
        encoding="utf-8",
    )

    resumed_triples = materialize_full_chunked(
        mapping_path=MAPPING_PATH,
        input_dir=input_dir,
        output_path=output,
        work_dir=work_dir,
        chunk_rows=1,
        minimum_triples=35,
        number_of_processes=1,
        resume=True,
    )

    assert resumed_triples == expected_triples
    assert len(Graph().parse(output, format="nt")) == expected_triples


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
