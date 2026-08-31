from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nl2sparql.linking.resolver import (
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)


def _entity(**changes: object) -> ResolvedEntity:
    values: dict[str, object] = {
        "span": "Binance",
        "span_offset": (16, 23),
        "target_id": "owner:Binance",
        "target_sha256": "a" * 64,
        "resolution_kind": "instance",
        "direction": "to",
        "fields": (FieldCandidate("transaction_facts", "to_address"),),
        "operator": "in",
        "values": ("0x" + "1" * 40,),
        "required_relation": None,
        "required_join": None,
        "required_role": None,
        "coverage_status": "supported",
        "confidence": 1.0,
        "explanation": "Exact owner target resolved to verified addresses.",
    }
    values.update(changes)
    return ResolvedEntity(**values)  # type: ignore[arg-type]


def _plan(entity: ResolvedEntity, **changes: object) -> ResolutionPlan:
    values: dict[str, object] = {
        "question_sha256": "b" * 64,
        "entities": (entity,),
        "catalog_sha256": "c" * 64,
        "entities_sha256": "d" * 64,
        "aliases_sha256": "e" * 64,
        "concepts_sha256": "f" * 64,
        "status": "resolved",
        "warnings": (),
    }
    values.update(changes)
    return ResolutionPlan(**values)  # type: ignore[arg-type]


def test_field_candidate_rejects_non_catalog_identifier_syntax() -> None:
    with pytest.raises(ClassResolverError, match="field"):
        FieldCandidate("transaction_facts", "to_address; DROP TABLE labels")


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"operator": "equals", "values": ()}, "operator"),
        ({"operator": "none", "values": ("ExchangeAccount",)}, "operator"),
        ({"resolution_kind": "unresolved", "operator": "in"}, "unresolved"),
        ({"resolution_kind": "concept", "operator": "equals", "values": ("bad class",)}, "class"),
        ({"confidence": float("nan")}, "confidence"),
        ({"fields": [FieldCandidate("transaction_facts", "to_address")]}, "tuple"),
    ),
)
def test_resolved_entity_rejects_incoherent_constraint_shapes(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ClassResolverError, match=message):
        _entity(**changes)


def test_resolution_plan_is_deeply_immutable() -> None:
    entity = _entity()
    plan = _plan(entity)

    with pytest.raises(FrozenInstanceError):
        plan.status = "partial"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.entities[0].direction = "from"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"status": "unresolved"}, "status"),
        ({"entities": [_entity()]}, "tuple"),
        ({"warnings": ("z warning", "a warning")}, "ordered"),
        ({"question_sha256": "A" * 64}, "SHA-256"),
    ),
)
def test_resolution_plan_rejects_incoherent_or_mutable_values(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ClassResolverError, match=message):
        _plan(_entity(), **changes)


def test_partial_plan_requires_a_warning_or_nonresolved_entity() -> None:
    with pytest.raises(ClassResolverError, match="partial"):
        _plan(_entity(), status="partial")
