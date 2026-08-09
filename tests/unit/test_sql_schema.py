from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nl2sparql.sql.schema import (
    CATALOG_PATH,
    SchemaCatalogError,
    load_catalog,
    validate_catalog,
)

EXPECTED_SOURCE_IDS = {
    "transactions",
    "blocks",
    "token_transfers",
    "contracts",
    "amended_tokens",
    "entity_labels_v1",
}
EXPECTED_RELATION_IDS = {
    "transaction_facts",
    "block_facts",
    "token_transfer_facts",
    "contract_dimension",
    "token_dimension",
    "entity_labels_v1",
}
EXPECTED_JOIN_IDS = {
    "transaction_to_block",
    "transfer_to_transaction",
    "transfer_to_contract",
    "transfer_to_token",
    "fact_address_to_entity",
}


@pytest.fixture
def catalog() -> dict[str, object]:
    return load_catalog()


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_committed_catalog_declares_approved_top_level_contract(
    catalog: dict[str, object],
) -> None:
    summary = validate_catalog(catalog)

    assert CATALOG_PATH.name == "ethereum_analytics.json"
    assert set(catalog["physical_sources"]) == EXPECTED_SOURCE_IDS
    assert set(catalog["analytical_relations"]) == EXPECTED_RELATION_IDS
    assert set(catalog["join_paths"]) == EXPECTED_JOIN_IDS
    assert summary.source_count == 6
    assert summary.relation_count == 6
    assert summary.join_count == 5


def test_load_catalog_fails_closed_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SchemaCatalogError, match="Unable to read schema catalog"):
        load_catalog(tmp_path / "missing.json")


def test_load_catalog_fails_closed_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SchemaCatalogError, match="Invalid schema catalog JSON"):
        load_catalog(path)


def test_load_catalog_requires_a_json_object(tmp_path: Path) -> None:
    path = write_json(tmp_path / "array.json", [])

    with pytest.raises(SchemaCatalogError, match="top level must be an object"):
        load_catalog(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("catalog_version", "2.0.0", "catalog_version"),
        ("dialect", "legacy_sql", "dialect"),
        ("location", "EU", "location"),
    ],
)
def test_validate_catalog_rejects_unknown_global_contract_values(
    catalog: dict[str, object], field: str, value: object, message: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid[field] = value

    with pytest.raises(SchemaCatalogError, match=message):
        validate_catalog(invalid)


@pytest.mark.parametrize(
    "section",
    [
        "evaluation_window",
        "cost_policy",
        "physical_sources",
        "analytical_relations",
        "join_paths",
        "role_policies",
        "semantic_mappings",
        "competency_questions",
    ],
)
def test_validate_catalog_requires_every_top_level_section(
    catalog: dict[str, object], section: str
) -> None:
    invalid = copy.deepcopy(catalog)
    del invalid[section]

    with pytest.raises(SchemaCatalogError, match=section):
        validate_catalog(invalid)


@pytest.mark.parametrize("maximum_bytes_billed", [0, -1, 12.5, "53687091200"])
def test_validate_catalog_requires_positive_integer_byte_cap(
    catalog: dict[str, object], maximum_bytes_billed: object
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["cost_policy"]["maximum_bytes_billed"] = maximum_bytes_billed

    with pytest.raises(SchemaCatalogError, match="maximum_bytes_billed"):
        validate_catalog(invalid)


def test_validate_catalog_requires_dry_run(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["cost_policy"]["dry_run_required"] = False

    with pytest.raises(SchemaCatalogError, match="dry_run_required"):
        validate_catalog(invalid)


@pytest.mark.parametrize(
    "section",
    ["physical_sources", "analytical_relations", "join_paths", "role_policies"],
)
def test_validate_catalog_requires_mapping_sections(
    catalog: dict[str, object], section: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid[section] = []

    with pytest.raises(SchemaCatalogError, match=section):
        validate_catalog(invalid)


@pytest.mark.parametrize("section", ["semantic_mappings", "competency_questions"])
def test_validate_catalog_requires_sequence_sections(
    catalog: dict[str, object], section: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid[section] = {}

    with pytest.raises(SchemaCatalogError, match=section):
        validate_catalog(invalid)
