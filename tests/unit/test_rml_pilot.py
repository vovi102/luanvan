"""Tests for the T1.3 RML pilot."""

from pathlib import Path

import pytest

from nl2sparql.kg.rml.run_morph_pilot import (
    PilotMaterializationError,
    build_morph_config,
    required_input_paths,
    validate_required_files,
)


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
