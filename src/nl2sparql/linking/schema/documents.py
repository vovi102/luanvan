"""Deterministic analytical relation and field documents."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nl2sparql.linking.schema.contracts import SchemaDocumentError, SchemaElement
from nl2sparql.sql.schema import SchemaCatalogError, validate_catalog

SYNONYMS_PATH = Path(__file__).with_name("synonyms.json")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(value.replace("_", " ").split())


def _words(value: str) -> tuple[str, ...]:
    expanded = _CAMEL_BOUNDARY_RE.sub(" ", value.lstrip(":"))
    return tuple(re.findall(r"[a-z0-9]+", _normalize(expanded)))


def load_synonyms(
    path: Path = SYNONYMS_PATH, *, snapshot: bytes | None = None
) -> dict[str, tuple[str, ...]]:
    """Load reviewed synonym groups with global alias ownership."""
    if snapshot is None:
        try:
            snapshot = path.read_bytes()
        except OSError as exc:
            raise SchemaDocumentError(f"unable to read schema synonyms {path}: {exc}") from exc
    try:
        raw = json.loads(snapshot)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaDocumentError(f"unable to read schema synonyms {path}: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise SchemaDocumentError("schema synonyms must be a non-empty JSON object")
    normalized: dict[str, tuple[str, ...]] = {}
    owners: dict[tuple[str, ...], str] = {}
    for raw_key, raw_aliases in raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip() or _CONTROL_RE.search(raw_key):
            raise SchemaDocumentError("synonym group names must be non-empty and control-free")
        key = _normalize(raw_key)
        key_tokens = _words(key)
        if not key_tokens:
            raise SchemaDocumentError("synonym group names must contain normalized text tokens")
        if key in normalized:
            raise SchemaDocumentError(f"synonym groups collide after normalized key {key!r}")
        if not isinstance(raw_aliases, list) or not raw_aliases:
            raise SchemaDocumentError(f"synonym group {key!r} must be a non-empty array")
        aliases: list[str] = []
        phrases = {key_tokens}
        previous = owners.get(key_tokens)
        if previous is not None and previous != key:
            raise SchemaDocumentError(
                f"normalized synonym phrase belongs to both {previous!r} and {key!r}"
            )
        owners[key_tokens] = key
        for raw_alias in raw_aliases:
            if (
                not isinstance(raw_alias, str)
                or not raw_alias.strip()
                or _CONTROL_RE.search(raw_alias)
            ):
                raise SchemaDocumentError(f"synonym group {key!r} contains an invalid alias")
            alias = _normalize(raw_alias)
            alias_tokens = _words(alias)
            if not alias_tokens:
                raise SchemaDocumentError(
                    f"synonym group {key!r} contains a tokenless normalized alias"
                )
            if alias_tokens in phrases:
                raise SchemaDocumentError(f"synonym group {key!r} contains duplicate aliases")
            previous = owners.get(alias_tokens)
            if previous is not None and previous != key:
                raise SchemaDocumentError(
                    f"synonym alias {alias!r} belongs to both {previous!r} and {key!r}"
                )
            owners[alias_tokens] = key
            phrases.add(alias_tokens)
            aliases.append(alias)
        normalized[key] = tuple(sorted(aliases))
    return dict(sorted(normalized.items()))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaDocumentError(f"catalog {label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaDocumentError(f"catalog {label} must be an array")
    return value


def _semantic_and_cq_indexes(
    catalog: Mapping[str, Any],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    semantic_targets: defaultdict[str, set[str]] = defaultdict(set)
    targets_by_semantic: defaultdict[str, set[str]] = defaultdict(set)
    mappings = _sequence(catalog.get("semantic_mappings"), "semantic_mappings")
    for raw_mapping in mappings:
        mapping = _mapping(raw_mapping, "semantic mapping")
        semantic_id = str(mapping["semantic_id"])
        for raw_target in _sequence(mapping.get("targets"), f"{semantic_id}.targets"):
            target = _mapping(raw_target, f"{semantic_id}.target")
            relation = str(target["relation"])
            element_id = f"{relation}.{target['field']}" if "field" in target else relation
            semantic_targets[element_id].add(semantic_id)
            targets_by_semantic[semantic_id].add(element_id)
            semantic_targets[relation].add(semantic_id)

    cq_targets: defaultdict[str, set[str]] = defaultdict(set)
    questions = _sequence(catalog.get("competency_questions"), "competency_questions")
    for raw_question in questions:
        question = _mapping(raw_question, "competency question")
        cq_label = f"{question['id']} {question['status']}"
        relations = {str(value) for value in _sequence(question.get("relations"), cq_label)}
        for relation in relations:
            cq_targets[relation].add(cq_label)
        for semantic_id in _sequence(question.get("semantic_ids"), cq_label):
            for element_id in targets_by_semantic[str(semantic_id)]:
                relation = element_id.split(".", 1)[0]
                if relation in relations:
                    cq_targets[element_id].add(cq_label)
    return dict(semantic_targets), dict(cq_targets)


def _synonym_terms(
    element_id: str, semantics: set[str], synonyms: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    tokens = set(_words(element_id))
    for semantic_id in semantics:
        tokens.update(_words(semantic_id))
    terms: set[str] = set()
    for token in tokens:
        if token in synonyms:
            terms.add(token)
            terms.update(synonyms[token])
    return tuple(sorted(terms))


def _document(lines: list[str]) -> tuple[str, str]:
    text = "\n".join(line for line in lines if not line.endswith(": "))
    return text, hashlib.sha256(text.encode()).hexdigest()


def build_schema_elements(
    catalog: Mapping[str, Any],
    synonyms: Mapping[str, tuple[str, ...]],
) -> tuple[SchemaElement, ...]:
    """Build deterministic Plan B relation and field retrieval documents."""
    try:
        validate_catalog(catalog)
    except (SchemaCatalogError, TypeError, ValueError) as exc:
        raise SchemaDocumentError(f"invalid analytical catalog: {exc}") from exc
    relations = _mapping(catalog.get("analytical_relations"), "analytical_relations")
    semantics_by_element, cqs_by_element = _semantic_and_cq_indexes(catalog)
    rows: list[SchemaElement] = []
    for relation_id in sorted(relations):
        relation = _mapping(relations[relation_id], f"analytical_relations.{relation_id}")
        relation_semantics = semantics_by_element.get(relation_id, set())
        relation_terms = _synonym_terms(relation_id, relation_semantics, synonyms)
        relation_doc, relation_hash = _document(
            [
                f"Relation: {' '.join(_words(relation_id))}",
                f"Kind: {relation['kind']}",
                f"Sources: {' '.join(sorted(map(str, relation['sources'])))}",
                f"Parameters: {' '.join(sorted(map(str, relation.get('parameters', {}))))}",
                f"Primary key: {' '.join(map(str, relation['primary_key']))}",
                f"Semantics: {' '.join(sorted(relation_semantics))}",
                f"Competency questions: {' '.join(sorted(cqs_by_element.get(relation_id, set())))}",
                f"Synonyms: {' '.join(relation_terms)}",
            ]
        )
        rows.append(SchemaElement(relation_id, "relation", relation_doc, relation_hash))
        fields = _mapping(relation.get("fields"), f"analytical_relations.{relation_id}.fields")
        for field_id in sorted(fields):
            element_id = f"{relation_id}.{field_id}"
            field = _mapping(fields[field_id], element_id)
            lineage = " ".join(
                f"{item['source']}.{item['field']}"
                for item in _sequence(field.get("lineage"), f"{element_id}.lineage")
            )
            field_semantics = semantics_by_element.get(element_id, set())
            field_terms = _synonym_terms(element_id, field_semantics, synonyms)
            field_cqs = " ".join(sorted(cqs_by_element.get(element_id, set())))
            field_doc, field_hash = _document(
                [
                    f"Field: {' '.join(_words(element_id))}",
                    f"Relation: {' '.join(_words(relation_id))}",
                    f"Type: {field['type']} {field['mode']}",
                    f"Lineage: {lineage}",
                    f"Expression: {field.get('expression', '')}",
                    f"Semantics: {' '.join(sorted(field_semantics))}",
                    f"Competency questions: {field_cqs}",
                    f"Synonyms: {' '.join(field_terms)}",
                ]
            )
            rows.append(SchemaElement(element_id, "field", field_doc, field_hash))
    if len({row.element_id for row in rows}) != len(rows):
        raise SchemaDocumentError("catalog generated duplicate schema element IDs")
    return tuple(sorted(rows, key=lambda row: row.element_id))
