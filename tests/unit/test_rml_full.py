"""Tests for the T2.4 full RML mapping scaffold."""

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
