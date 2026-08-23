"""Tests for Plan B schema-linker contracts and catalog documents."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from nl2sparql.linking.schema import (
    SchemaCachePaths,
    SchemaDocumentError,
    SchemaElement,
    SchemaLinkerError,
    ScoreWeights,
    build_schema_elements,
    load_synonyms,
)
from nl2sparql.sql.schema import load_catalog


def test_build_schema_elements_covers_plan_b_relations_and_fields() -> None:
    catalog = load_catalog()
    synonyms = load_synonyms()

    rows = build_schema_elements(catalog, synonyms)
    by_id = {row.element_id: row for row in rows}

    assert len(rows) == 68
    assert {row.element_id for row in rows if row.kind == "relation"} == {
        "block_facts",
        "contract_dimension",
        "entity_labels_v1",
        "token_dimension",
        "token_transfer_facts",
        "transaction_facts",
    }
    assert by_id["transaction_facts.from_address"].kind == "field"
    assert "sender" in by_id["transaction_facts.from_address"].document
    assert "recipient" in by_id["transaction_facts.to_address"].document


def test_schema_documents_are_deterministic_and_include_catalog_semantics() -> None:
    catalog = load_catalog()
    synonyms = load_synonyms()

    first = build_schema_elements(catalog, synonyms)
    second = build_schema_elements(copy.deepcopy(catalog), dict(reversed(synonyms.items())))
    by_id = {row.element_id: row for row in first}

    assert first == second
    assert ":hasFrom" in by_id["transaction_facts.from_address"].document
    assert "CQ04" in by_id["transaction_facts.from_address"].document
    assert "STRING REQUIRED" in by_id["transaction_facts.from_address"].document
    assert len(by_id["transaction_facts.from_address"].document_sha256) == 64


@pytest.mark.parametrize(
    "payload",
    (
        [],
        {"from": []},
        {"from": ["sender", "sender"]},
        {"from": ["sender"], "to": ["sender"]},
        {"from": ["bad\u0001alias"]},
    ),
)
def test_load_synonyms_rejects_malformed_or_conflicting_groups(
    tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "synonyms.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SchemaDocumentError):
        load_synonyms(path)


@pytest.mark.parametrize(
    "payload",
    (
        {"From": ["sender"], "from": ["originating"]},
        {"from": ["sender"], "ｆｒｏｍ": ["originating"]},
        {"!!!": ["sender"]},
        {"from": ["!!!"]},
        {"from": ["sender"], "sender": ["originating"]},
    ),
)
def test_load_synonyms_rejects_normalized_key_collisions_and_tokenless_phrases(
    tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "synonyms.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SchemaDocumentError, match="normalized|token"):
        load_synonyms(path)


def test_build_schema_elements_wraps_invalid_catalog_references() -> None:
    catalog = copy.deepcopy(load_catalog())
    catalog["semantic_mappings"][0]["targets"] = [{"relation": "missing_relation"}]

    with pytest.raises(SchemaDocumentError, match="catalog"):
        build_schema_elements(catalog, load_synonyms())


@pytest.mark.parametrize(
    ("semantic", "lexical"),
    (
        (True, 0.0),
        (math.nan, 0.0),
        (0.8, -0.2),
        (0.6, 0.3),
    ),
)
def test_score_weights_reject_invalid_values(semantic: float, lexical: float) -> None:
    with pytest.raises(SchemaLinkerError, match="weights"):
        ScoreWeights(semantic=semantic, lexical=lexical)


def test_schema_contracts_validate_elements_and_derive_cache_paths(tmp_path: Path) -> None:
    with pytest.raises(SchemaLinkerError, match="element"):
        SchemaElement("bad\u0001id", "field", "valid document", "0" * 64)
    with pytest.raises(SchemaLinkerError, match="kind"):
        SchemaElement("valid.id", "property", "valid document", "0" * 64)

    paths = SchemaCachePaths.from_directory(tmp_path)

    assert paths.manifest == tmp_path / "schema-index.json"
    assert paths.matrices == tmp_path / "schema-index.npz"
    assert paths.lock == tmp_path / "schema-index.lock"
    assert paths.matrix_generation("a" * 64) == tmp_path / f"schema-index-{'a' * 64}.npz"
