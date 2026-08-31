"""Validated resolver lookup derived from the analytical catalog."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from nl2sparql.linking.resolver.contracts import ClassResolverError, FieldCandidate
from nl2sparql.sql.schema import SchemaCatalogError, load_catalog, validate_catalog

_ROLE_REQUIREMENT_CONCEPTS = {
    "bridge": "bridge",
    "dex": "dex",
    "exchange": "exchange",
    "lending": "lending",
    "marketplace": "nft_marketplace",
    "mev_actor": "mev",
    "mixer": "mixer",
    "token": "token_contract",
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ClassResolverError(f"invalid analytical catalog {label}")
    return value


@dataclass(frozen=True)
class ConceptPolicy:
    """Catalog-derived role and competency coverage for one concept category."""

    required_role: str
    coverage_status: str


@dataclass(frozen=True)
class ResolverCatalog:
    """Small immutable subset of catalog semantics needed by the resolver."""

    catalog_sha256: str
    fields_by_direction: Mapping[str, tuple[FieldCandidate, ...]]
    entity_join: str
    entity_relation: str
    entity_address_field: str
    concept_field: FieldCandidate
    allowed_roles: tuple[str, ...]
    concept_policies: Mapping[str, ConceptPolicy]
    semantic_status_by_class: Mapping[str, str]
    all_relations: frozenset[str]
    all_fields: frozenset[FieldCandidate]


def load_resolver_catalog(path: Path) -> ResolverCatalog:
    """Read, validate, fingerprint, and index one exact catalog snapshot."""
    try:
        snapshot = path.read_bytes()
        catalog = load_catalog(path, snapshot=snapshot)
        validate_catalog(catalog)
    except (OSError, SchemaCatalogError, TypeError, ValueError) as exc:
        raise ClassResolverError(f"invalid analytical catalog: {exc}") from exc

    joins = _mapping(catalog.get("join_paths"), "join paths")
    lookup = _mapping(joins.get("fact_address_to_entity"), "entity lookup")
    if (
        lookup.get("kind") != "address_lookup"
        or lookup.get("right_relation") != "entity_labels_v1"
        or lookup.get("right_field") != "address"
    ):
        raise ClassResolverError("entity lookup must target entity_labels_v1.address")
    left_relations = _mapping(lookup.get("left_relations"), "entity lookup left relations")
    candidates: dict[str, list[FieldCandidate]] = {"from": [], "to": [], "token": []}
    for relation, raw_fields in left_relations.items():
        if not isinstance(relation, str) or not isinstance(raw_fields, list):
            raise ClassResolverError("invalid analytical catalog entity lookup fields")
        for field in raw_fields:
            if not isinstance(field, str):
                raise ClassResolverError("invalid analytical catalog entity lookup field")
            for direction, expected in (
                ("from", "from_address"),
                ("to", "to_address"),
                ("token", "token_address"),
            ):
                if field == expected:
                    candidates[direction].append(FieldCandidate(relation, field))
    for direction, values in candidates.items():
        if not values:
            raise ClassResolverError(f"entity lookup has no {direction} direction fields")

    relations = _mapping(catalog.get("analytical_relations"), "analytical relations")
    labels = _mapping(relations.get("entity_labels_v1"), "entity label relation")
    label_fields = _mapping(labels.get("fields"), "entity label fields")
    if "concept_class" not in label_fields:
        raise ClassResolverError("entity label relation lacks concept class")

    raw_roles = lookup.get("allowed_right_roles")
    if not isinstance(raw_roles, list) or any(not isinstance(value, str) for value in raw_roles):
        raise ClassResolverError("invalid analytical catalog entity lookup roles")

    statuses: dict[str, str] = {}
    mappings = catalog.get("semantic_mappings")
    if not isinstance(mappings, list):
        raise ClassResolverError("invalid analytical catalog semantic mappings")
    for raw_mapping in mappings:
        mapping = _mapping(raw_mapping, "semantic mapping")
        semantic_id = mapping.get("semantic_id")
        targets = mapping.get("targets")
        if not isinstance(semantic_id, str) or not isinstance(targets, list):
            continue
        if any(
            isinstance(target, Mapping)
            and target.get("relation") == "entity_labels_v1"
            and target.get("field") == "concept_class"
            for target in targets
        ):
            statuses[semantic_id.lstrip(":")] = str(mapping.get("status"))

    raw_questions = catalog.get("competency_questions")
    if not isinstance(raw_questions, list):
        raise ClassResolverError("invalid analytical catalog competency questions")
    policy_roles: dict[str, set[str]] = {}
    policy_statuses: dict[str, set[str]] = {}
    for raw_question in raw_questions:
        question = _mapping(raw_question, "competency question")
        requirements = _mapping(
            question.get("role_requirements", {}), "competency role requirements"
        )
        for vocabulary_key, role in requirements.items():
            category = _ROLE_REQUIREMENT_CONCEPTS.get(str(vocabulary_key))
            if category is None:
                continue
            if not isinstance(role, str) or role not in raw_roles:
                raise ClassResolverError("invalid competency concept role")
            policy_roles.setdefault(category, set()).add(role)
            policy_statuses.setdefault(category, set()).add(str(question.get("status")))

    concept_policies: dict[str, ConceptPolicy] = {}
    for category, roles_for_category in sorted(policy_roles.items()):
        if len(roles_for_category) != 1:
            raise ClassResolverError(
                f"conflicting competency roles for concept category {category!r}"
            )
        coverage_status = (
            "supported" if "supported" in policy_statuses.get(category, set()) else "coverage_gap"
        )
        concept_policies[category] = ConceptPolicy(
            required_role=next(iter(roles_for_category)),
            coverage_status=coverage_status,
        )
    frozen_candidates = MappingProxyType(
        {key: tuple(sorted(values)) for key, values in sorted(candidates.items())}
    )
    all_fields = frozenset(
        FieldCandidate(str(relation_id), str(field_id))
        for relation_id, raw_relation in relations.items()
        for field_id in _mapping(raw_relation, f"analytical relation {relation_id}").get(
            "fields", {}
        )
    )
    return ResolverCatalog(
        catalog_sha256=hashlib.sha256(snapshot).hexdigest(),
        fields_by_direction=frozen_candidates,
        entity_join="fact_address_to_entity",
        entity_relation="entity_labels_v1",
        entity_address_field="address",
        concept_field=FieldCandidate("entity_labels_v1", "concept_class"),
        allowed_roles=tuple(sorted(raw_roles)),
        concept_policies=MappingProxyType(concept_policies),
        semantic_status_by_class=MappingProxyType(dict(sorted(statuses.items()))),
        all_relations=frozenset(map(str, relations)),
        all_fields=all_fields,
    )
