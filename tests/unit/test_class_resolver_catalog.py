from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.linking.resolver import (
    ClassResolverError,
    FieldCandidate,
    load_resolver_catalog,
)
from nl2sparql.sql.schema import CATALOG_PATH


def _catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.json"
    path.write_bytes(CATALOG_PATH.read_bytes())
    return path


def test_catalog_index_hashes_the_exact_validated_snapshot(tmp_path: Path) -> None:
    path = _catalog_path(tmp_path)
    snapshot = path.read_bytes()

    index = load_resolver_catalog(path)

    assert index.catalog_sha256 == hashlib.sha256(snapshot).hexdigest()
    assert index.entity_join == "fact_address_to_entity"
    assert index.entity_relation == "entity_labels_v1"
    assert index.entity_address_field == "address"
    assert index.concept_field == FieldCandidate("entity_labels_v1", "concept_class")
    assert index.allowed_roles == ("operational", "token", "treasury")


def test_catalog_index_derives_direction_fields_from_the_address_lookup(tmp_path: Path) -> None:
    index = load_resolver_catalog(_catalog_path(tmp_path))

    assert index.fields_by_direction["from"] == (
        FieldCandidate("token_transfer_facts", "from_address"),
        FieldCandidate("transaction_facts", "from_address"),
    )
    assert index.fields_by_direction["to"] == (
        FieldCandidate("token_transfer_facts", "to_address"),
        FieldCandidate("transaction_facts", "to_address"),
    )
    assert index.fields_by_direction["token"] == (
        FieldCandidate("token_transfer_facts", "token_address"),
    )


def test_catalog_index_derives_concept_role_and_competency_coverage(tmp_path: Path) -> None:
    index = load_resolver_catalog(_catalog_path(tmp_path))

    assert index.concept_policies["exchange"].required_role == "treasury"
    assert index.concept_policies["exchange"].coverage_status == "supported"
    assert index.concept_policies["dex"].required_role == "operational"
    assert index.concept_policies["dex"].coverage_status == "supported"
    assert index.concept_policies["mixer"].required_role == "operational"
    assert index.concept_policies["mixer"].coverage_status == "coverage_gap"
    assert index.concept_policies["nft_marketplace"].coverage_status == "coverage_gap"
    assert index.concept_policies["mev"].coverage_status == "coverage_gap"
    assert index.concept_policies["token_contract"].required_role == "token"


def test_catalog_index_rejects_a_semantically_wrong_entity_lookup(tmp_path: Path) -> None:
    path = _catalog_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["join_paths"]["fact_address_to_entity"]["right_field"] = "owner"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ClassResolverError, match="entity lookup"):
        load_resolver_catalog(path)


def test_catalog_index_rejects_missing_direction_fields(tmp_path: Path) -> None:
    path = _catalog_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    left_relations = raw["join_paths"]["fact_address_to_entity"]["left_relations"]
    for fields in left_relations.values():
        if "to_address" in fields:
            fields.remove("to_address")
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ClassResolverError, match="to direction"):
        load_resolver_catalog(path)


def test_catalog_index_wraps_invalid_catalog_errors(tmp_path: Path) -> None:
    path = _catalog_path(tmp_path)
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ClassResolverError, match="invalid analytical catalog"):
        load_resolver_catalog(path)
