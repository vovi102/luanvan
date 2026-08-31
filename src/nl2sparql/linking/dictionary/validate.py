from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sparql.linking.dictionary import (
    ALIASES_PATH,
    CONCEPTS_PATH,
    ENTITIES_PATH,
    SOURCES_PATH,
)
from nl2sparql.linking.dictionary.schema import (
    DictionaryValidationError,
    normalize_address,
    normalize_alias,
    validate_address_role,
    validate_chain_id,
    validate_confidence,
    validate_source_locator,
    validate_source_revision,
)


@dataclass(frozen=True)
class DictionaryArtifacts:
    entities_path: Path = ENTITIES_PATH
    concepts_path: Path = CONCEPTS_PATH
    aliases_path: Path = ALIASES_PATH
    sources_path: Path = SOURCES_PATH


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise DictionaryValidationError(f"Missing dictionary artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_artifacts(
    artifacts: DictionaryArtifacts | None = None,
    *,
    min_entities: int = 3000,
    min_aliases: int = 1000,
) -> dict[str, int]:
    if artifacts is None:
        artifacts = DictionaryArtifacts()
    entities = _load_json(artifacts.entities_path)
    concepts = _load_json(artifacts.concepts_path)
    aliases = _load_json(artifacts.aliases_path)
    if not artifacts.sources_path.exists():
        raise DictionaryValidationError(f"Missing dictionary artifact: {artifacts.sources_path}")
    return validate_artifact_data(
        entities,
        concepts,
        aliases,
        artifacts.sources_path.read_text(encoding="utf-8"),
        min_entities=min_entities,
        min_aliases=min_aliases,
    )


def validate_artifact_data(
    entities: Any,
    concepts: Any,
    aliases: Any,
    sources_text: str,
    *,
    min_entities: int = 3000,
    min_aliases: int = 1000,
) -> dict[str, int]:
    """Validate one already-read dictionary snapshot without rereading its paths."""
    if not isinstance(entities, list):
        raise DictionaryValidationError("entities.json must contain a list")
    if not isinstance(concepts, dict):
        raise DictionaryValidationError("concepts.json must contain an object")
    if not isinstance(aliases, dict):
        raise DictionaryValidationError("aliases.json must contain an object")
    if len(entities) < min_entities:
        raise DictionaryValidationError(
            f"entities.json has {len(entities)} entries; expected at least {min_entities}"
        )
    if not 8 <= len(concepts) <= 12:
        raise DictionaryValidationError(
            f"concepts.json has {len(concepts)} concepts; expected 8-12"
        )
    if len(aliases) < min_aliases:
        raise DictionaryValidationError(
            f"aliases.json has {len(aliases)} aliases; expected at least {min_aliases}"
        )
    if list(aliases) != sorted(aliases):
        raise DictionaryValidationError("aliases.json keys must be sorted")

    def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise DictionaryValidationError(f"{label} must contain an object")
        return value

    def require_text(value: Any, label: str) -> str:
        if not isinstance(value, str):
            raise DictionaryValidationError(f"{label} must contain text")
        return value

    def require_text_list(value: Any, label: str) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise DictionaryValidationError(f"{label} must contain a list of text values")
        return value

    for key, target in aliases.items():
        require_text(key, "alias key")
        require_text(target, "alias target")

    concept_keys = set(concepts)
    owners = set()
    seen_addresses = set()
    entity_sort_keys = []
    for index, raw_entry in enumerate(entities):
        entry = require_mapping(raw_entry, f"entity {index}")
        entity_sort_keys.append(
            (entry.get("category"), entry.get("owner"), entry.get("address_lower"))
        )
    if entity_sort_keys != sorted(entity_sort_keys):
        raise DictionaryValidationError(
            "entities.json must be sorted by category, owner, address_lower"
        )

    for concept_key, concept in concepts.items():
        require_text(concept_key, "concept key")
        concept = require_mapping(concept, f"concept {concept_key!r}")
        if normalize_alias(concept_key) != concept_key:
            raise DictionaryValidationError(f"Concept key is not normalized: {concept_key!r}")
        for field in ("ontology_class", "aliases", "instances", "description"):
            if field not in concept:
                raise DictionaryValidationError(f"Concept {concept_key!r} missing field {field!r}")
        require_text(concept["ontology_class"], f"concept {concept_key!r} ontology_class")
        require_text_list(concept["aliases"], f"concept {concept_key!r} aliases")
        owners.update(require_text_list(concept["instances"], f"concept {concept_key!r} instances"))
        require_text(concept["description"], f"concept {concept_key!r} description")

    required = {
        "address",
        "address_lower",
        "primary_label",
        "owner",
        "category",
        "concept_class",
        "aliases",
        "chain_id",
        "address_role",
        "sources",
        "confidence",
        "verified_date",
    }
    operational_entity_count = 0
    for index, raw_entry in enumerate(entities):
        entry = require_mapping(raw_entry, f"entity {index}")
        missing = required - set(entry)
        if missing:
            raise DictionaryValidationError(f"Entity missing fields: {sorted(missing)}")
        for field in (
            "address",
            "address_lower",
            "primary_label",
            "owner",
            "category",
            "concept_class",
            "address_role",
            "confidence",
            "verified_date",
        ):
            require_text(entry[field], f"entity {index} {field}")
        require_text_list(entry["aliases"], f"entity {index} aliases")
        if isinstance(entry["chain_id"], bool) or not isinstance(entry["chain_id"], (int, str)):
            raise DictionaryValidationError(f"entity {index} chain_id must be an integer or text")
        if not isinstance(entry["sources"], list):
            raise DictionaryValidationError(f"entity {index} sources must contain a list")
        address_lower = normalize_address(entry["address"])
        if entry["address_lower"] != address_lower:
            raise DictionaryValidationError(f"address_lower mismatch for {entry['address']}")
        if address_lower in seen_addresses:
            raise DictionaryValidationError(f"Duplicate address_lower: {address_lower}")
        seen_addresses.add(address_lower)
        if entry["category"] not in concept_keys:
            raise DictionaryValidationError(f"Unknown category: {entry['category']}")
        validate_chain_id(entry["chain_id"])
        role = validate_address_role(entry["address_role"])
        operational_entity_count += role == "operational"
        validate_confidence(entry["confidence"])
        if not entry["sources"]:
            raise DictionaryValidationError(f"Entity has no sources: {entry['address']}")
        owners.add(entry["owner"])
        for alias in entry["aliases"]:
            normalize_alias(alias)
        for source in entry["sources"]:
            source = require_mapping(source, f"source for {entry['address']}")
            for field in (
                "name",
                "url",
                "revision",
                "locator",
                "retrieved_date",
                "note",
            ):
                if field not in source:
                    raise DictionaryValidationError(
                        f"Source missing field {field!r} for {entry['address']}"
                    )
                require_text(source[field], f"source {field} for {entry['address']}")
            validate_source_revision(source["revision"])
            validate_source_locator(source["locator"])

    for alias, target in aliases.items():
        if normalize_alias(alias) != alias:
            raise DictionaryValidationError(f"Alias key is not normalized: {alias!r}")
        if target not in owners:
            raise DictionaryValidationError(f"Alias target does not exist: {target!r}")

    if not isinstance(sources_text, str):
        raise DictionaryValidationError("sources.md must contain text")
    for phrase in (
        "Retrieved date:",
        "Manual verification:",
        "Automated acceptance criteria",
    ):
        if phrase not in sources_text:
            raise DictionaryValidationError(f"sources.md missing phrase: {phrase}")

    return {
        "entity_count": len(entities),
        "concept_count": len(concepts),
        "alias_count": len(aliases),
        "operational_entity_count": operational_entity_count,
    }
