"""Tests for the T2.4 full RML mapping scaffold."""

import csv
import json
from pathlib import Path

import pytest

from nl2sparql.kg.rml.run_morph_full import (
    FullMaterializationError,
    build_morph_config,
    prepare_entities_csv,
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
