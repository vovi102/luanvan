"""Deterministic dictionary grouping and target-document construction."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from types import MappingProxyType
from urllib.parse import quote

from nl2sparql.linking.dictionary.schema import DictionaryValidationError
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts, validate_artifacts
from nl2sparql.linking.entity.contracts import (
    EntityCorpus,
    EntityDocumentError,
    EntityTarget,
    required_text,
)


def normalize_phrase(value: str) -> str:
    """Normalize one phrase for deterministic matching."""
    text = required_text(value, "entity phrase")
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_document(lines: list[str]) -> tuple[str, str]:
    document = "\n".join(lines)
    return document, _sha256_bytes(document.encode("utf-8"))


def _owner_id(owner: str) -> str:
    return f"owner:{quote(owner, safe='')}"


def build_entity_corpus(
    artifacts: DictionaryArtifacts | None = None,
    *,
    min_entities: int = 3000,
    min_aliases: int = 1000,
) -> EntityCorpus:
    """Validate dictionary artifacts and derive canonical owner/concept targets."""
    artifacts = artifacts or DictionaryArtifacts()
    try:
        validate_artifacts(
            artifacts,
            min_entities=min_entities,
            min_aliases=min_aliases,
        )
    except (DictionaryValidationError, OSError, json.JSONDecodeError) as exc:
        raise EntityDocumentError(f"invalid entity dictionary: {exc}") from exc

    entities_raw = artifacts.entities_path.read_bytes()
    aliases_raw = artifacts.aliases_path.read_bytes()
    concepts_raw = artifacts.concepts_path.read_bytes()
    entities = _load_json(artifacts.entities_path)
    aliases = _load_json(artifacts.aliases_path)
    concepts = _load_json(artifacts.concepts_path)
    if (
        not isinstance(entities, list)
        or not isinstance(aliases, dict)
        or not isinstance(concepts, dict)
    ):
        raise EntityDocumentError("validated dictionary changed during corpus construction")

    owner_rows: dict[str, list[dict]] = defaultdict(list)
    for row in entities:
        owner_rows[row["owner"]].append(row)
    owner_ids = {owner: _owner_id(owner) for owner in owner_rows}

    phrase_targets: dict[str, set[str]] = defaultdict(set)
    owner_extra_aliases: dict[str, set[str]] = defaultdict(set)
    for phrase, owner in aliases.items():
        target_id = owner_ids.get(owner)
        if target_id is None:
            raise EntityDocumentError(f"alias target does not exist: {owner!r}")
        normalized = normalize_phrase(phrase)
        phrase_targets[normalized].add(target_id)
        owner_extra_aliases[owner].add(normalized)

    targets: list[EntityTarget] = []
    address_targets: dict[str, str] = {}
    for owner, rows in sorted(owner_rows.items()):
        target_id = owner_ids[owner]
        addresses = tuple(sorted({row["address_lower"] for row in rows}))
        labels = tuple(sorted({row["primary_label"] for row in rows}))
        categories = tuple(sorted({row["category"] for row in rows}))
        classes = tuple(sorted({row["concept_class"] for row in rows}))
        roles = tuple(sorted({row["address_role"] for row in rows}))
        normalized_aliases = {
            normalize_phrase(owner),
            *(normalize_phrase(label) for label in labels),
            *(normalize_phrase(alias) for row in rows for alias in row["aliases"]),
            *owner_extra_aliases[owner],
        }
        target_aliases = tuple(sorted(normalized_aliases))
        for phrase in target_aliases:
            phrase_targets[phrase].add(target_id)
        for address in addresses:
            address_targets[address] = target_id
        document, fingerprint = _target_document(
            [
                f"Owner: {owner}",
                f"Primary labels: {' | '.join(labels)}",
                f"Aliases: {' | '.join(target_aliases)}",
                f"Categories: {' | '.join(categories)}",
                f"Concept classes: {' | '.join(classes)}",
                f"Address roles: {' | '.join(roles)}",
            ]
        )
        targets.append(
            EntityTarget(
                target_id=target_id,
                target_kind="owner",
                owner=owner,
                addresses=addresses,
                primary_labels=labels,
                aliases=target_aliases,
                categories=categories,
                concept_classes=classes,
                address_roles=roles,
                description=f"Ethereum owner target {owner}.",
                document=document,
                document_sha256=fingerprint,
            )
        )

    for key, info in sorted(concepts.items()):
        target_id = f"concept:{key}"
        target_aliases = tuple(
            sorted({normalize_phrase(key), *(normalize_phrase(v) for v in info["aliases"])})
        )
        for phrase in target_aliases:
            phrase_targets[phrase].add(target_id)
        ontology_class = info["ontology_class"].rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        description = required_text(info["description"], f"concept {key} description")
        instances = tuple(sorted(info["instances"]))
        instance_sample = instances[:50]
        document, fingerprint = _target_document(
            [
                f"Concept: {key}",
                f"Description: {description}",
                f"Aliases: {' | '.join(target_aliases)}",
                f"Concept class: {ontology_class}",
                f"Known owner count: {len(instances)}",
                f"Known owner sample: {' | '.join(instance_sample)}",
            ]
        )
        targets.append(
            EntityTarget(
                target_id=target_id,
                target_kind="concept",
                owner=None,
                addresses=(),
                primary_labels=(),
                aliases=target_aliases,
                categories=(key,),
                concept_classes=(ontology_class,),
                address_roles=(),
                description=description,
                document=document,
                document_sha256=fingerprint,
            )
        )

    ordered_targets = tuple(sorted(targets, key=lambda row: row.target_id))
    targets_by_id = MappingProxyType({row.target_id: row for row in ordered_targets})
    ordered_phrases = MappingProxyType(
        {phrase: tuple(sorted(target_ids)) for phrase, target_ids in sorted(phrase_targets.items())}
    )
    return EntityCorpus(
        targets=ordered_targets,
        targets_by_id=targets_by_id,
        phrase_targets=ordered_phrases,
        address_targets=MappingProxyType(dict(sorted(address_targets.items()))),
        entities_sha256=_sha256_bytes(entities_raw),
        aliases_sha256=_sha256_bytes(aliases_raw),
        concepts_sha256=_sha256_bytes(concepts_raw),
    )
