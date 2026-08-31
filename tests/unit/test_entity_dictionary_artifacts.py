import json
from pathlib import Path

import pytest

from nl2sparql.linking.dictionary import (
    CONCEPTS_PATH,
    ENTITIES_PATH,
    SOURCES_PATH,
)
from nl2sparql.linking.dictionary.schema import DictionaryValidationError
from nl2sparql.linking.dictionary.validate import (
    DictionaryArtifacts,
    validate_artifact_data,
    validate_artifacts,
)


def write_minimal_chain_aware_artifacts(
    tmp_path: Path,
    *,
    entity_updates: dict[str, object] | None = None,
    source_updates: dict[str, object] | None = None,
) -> DictionaryArtifacts:
    entity = {
        "address": "0x1111111111111111111111111111111111111111",
        "address_lower": "0x1111111111111111111111111111111111111111",
        "primary_label": "Reviewed entity",
        "owner": "Reviewed Owner",
        "category": "category_0",
        "concept_class": "ReviewedClass",
        "aliases": ["reviewed owner"],
        "chain_id": 1,
        "address_role": "operational",
        "sources": [
            {
                "name": "reviewed_source",
                "url": "https://example.test/source",
                "revision": "a" * 40,
                "locator": "deployments/ethereum.json:/reviewed",
                "retrieved_date": "2026-08-09",
                "note": "Operational evidence for Reviewed Owner",
            }
        ],
        "confidence": "high",
        "verified_date": "2026-08-09",
    }
    entity.update(entity_updates or {})
    entity["sources"][0].update(source_updates or {})
    concepts = {
        f"category_{index}": {
            "ontology_class": f"https://example.test/Category{index}",
            "aliases": [f"category {index}"],
            "instances": ["Reviewed Owner"] if index == 0 else [],
            "description": f"Category {index}",
        }
        for index in range(8)
    }
    paths = DictionaryArtifacts(
        entities_path=tmp_path / "entities.json",
        concepts_path=tmp_path / "concepts.json",
        aliases_path=tmp_path / "aliases.json",
        sources_path=tmp_path / "sources.md",
    )
    paths.entities_path.write_text(json.dumps([entity]), encoding="utf-8")
    paths.concepts_path.write_text(json.dumps(concepts), encoding="utf-8")
    paths.aliases_path.write_text(
        json.dumps({"reviewed owner": "Reviewed Owner"}), encoding="utf-8"
    )
    paths.sources_path.write_text(
        "Retrieved date: 2026-08-09\nManual verification: pending\nAutomated acceptance criteria\n",
        encoding="utf-8",
    )
    return paths


def _valid_concepts_data() -> dict[str, dict[str, object]]:
    return {
        f"category_{index}": {
            "ontology_class": f"https://example.test/Category{index}",
            "aliases": [f"category {index}"],
            "instances": [],
            "description": f"Category {index}",
        }
        for index in range(8)
    }


def test_validate_artifacts_reports_missing_files(tmp_path):
    artifacts = DictionaryArtifacts(
        entities_path=tmp_path / "entities.json",
        concepts_path=tmp_path / "concepts.json",
        aliases_path=tmp_path / "aliases.json",
        sources_path=tmp_path / "sources.md",
    )

    with pytest.raises(DictionaryValidationError, match="Missing dictionary artifact"):
        validate_artifacts(artifacts, min_entities=1, min_aliases=1)


@pytest.mark.parametrize(
    ("entity_updates", "source_updates", "error"),
    [
        ({"chain_id": 10}, {}, "Ethereum chain_id"),
        ({"address_role": "protocol"}, {}, "address_role"),
        ({}, {"revision": "main"}, "source_revision"),
        ({}, {"locator": "  "}, "source_locator"),
    ],
)
def test_validate_artifacts_rejects_invalid_chain_role_or_provenance(
    tmp_path,
    entity_updates,
    source_updates,
    error,
):
    artifacts = write_minimal_chain_aware_artifacts(
        tmp_path,
        entity_updates=entity_updates,
        source_updates=source_updates,
    )

    with pytest.raises(DictionaryValidationError, match=error):
        validate_artifacts(artifacts, min_entities=1, min_aliases=1)


def test_validate_artifacts_reports_operational_entity_count(tmp_path):
    artifacts = write_minimal_chain_aware_artifacts(tmp_path)

    report = validate_artifacts(artifacts, min_entities=1, min_aliases=1)

    assert report["operational_entity_count"] == 1


@pytest.mark.parametrize(
    ("artifact", "mutate"),
    (
        pytest.param(
            "entities",
            lambda payload: payload.__setitem__(0, 1),
            id="entity-must-be-object",
        ),
        pytest.param(
            "entities",
            lambda payload: payload[0].__setitem__("category", 1),
            id="entity-category-must-be-text-before-sort",
        ),
        pytest.param(
            "entities",
            lambda payload: payload.append({**payload[0], "category": 1}),
            id="mixed-category-types-must-not-leak-type-error",
        ),
        pytest.param(
            "entities",
            lambda payload: payload[0].pop("address_lower"),
            id="missing-sort-key-must-not-leak-type-error",
        ),
        pytest.param(
            "concepts",
            lambda payload: payload.__setitem__("category_0", 1),
            id="concept-must-be-object",
        ),
    ),
)
def test_validate_artifacts_rejects_malformed_entries_before_sorting(tmp_path, artifact, mutate):
    artifacts = write_minimal_chain_aware_artifacts(tmp_path)
    path = getattr(artifacts, f"{artifact}_path")
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DictionaryValidationError):
        validate_artifacts(artifacts, min_entities=1, min_aliases=1)


@pytest.mark.parametrize(
    ("entities", "concepts", "aliases"),
    (
        pytest.param(
            [],
            {**_valid_concepts_data(), 1: _valid_concepts_data()["category_0"]},
            {},
            id="concept-key-must-be-text",
        ),
        pytest.param(
            [],
            _valid_concepts_data(),
            {1: "Owner", "owner": "Owner"},
            id="alias-key-must-be-text-before-sort",
        ),
    ),
)
def test_validate_artifact_data_rejects_non_text_comparison_keys(entities, concepts, aliases):
    with pytest.raises(DictionaryValidationError):
        validate_artifact_data(
            entities,
            concepts,
            aliases,
            "Retrieved date:\nManual verification:\nAutomated acceptance criteria\n",
            min_entities=0,
            min_aliases=0,
        )


def test_committed_dictionary_artifacts_meet_t2_2_thresholds():
    report = validate_artifacts(min_entities=3000, min_aliases=1000)

    assert report["entity_count"] >= 3000
    assert 8 <= report["concept_count"] <= 12
    assert report["alias_count"] >= 1000
    assert report["operational_entity_count"] > 0


def test_committed_dictionary_covers_required_exchange_and_defi_owners():
    entities = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
    concepts = json.loads(CONCEPTS_PATH.read_text(encoding="utf-8"))
    coverage = json.loads(
        Path("data/entity_dictionary/curated/coverage.json").read_text(encoding="utf-8")
    )
    owners = {entry["owner"] for entry in entities}

    required_exchanges = set(coverage["top_exchanges"])
    required_defi = set(coverage["top_defi_protocols"])
    treasury_owners = {entry["owner"] for entry in entities if entry["address_role"] == "treasury"}
    operational_owners = {
        entry["owner"] for entry in entities if entry["address_role"] == "operational"
    }

    assert len(required_exchanges) == 30
    assert len(required_defi) == 50
    assert required_exchanges <= owners
    assert required_exchanges <= treasury_owners
    assert required_defi <= owners
    assert set(concepts["exchange"]["instances"]) >= required_exchanges
    assert operational_owners
    assert SOURCES_PATH.exists()
