from __future__ import annotations

import hashlib

from nl2sparql.linking import (
    ClassResolver,
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)
from nl2sparql.linking.entity import EntityMatch, build_entity_corpus
from nl2sparql.sql.schema import CATALOG_PATH


def test_stable_linking_facade_executes_a_typed_resolution_plan() -> None:
    corpus = build_entity_corpus()
    address = "0x" + "1" * 40
    target_id = f"address:{address}"
    question = f"transactions to {address}"
    match = EntityMatch(
        span=address,
        span_offset=(16, 58),
        target_id=target_id,
        target_kind="address",
        owner=None,
        addresses=(address,),
        categories=(),
        concept_classes=(),
        stage="address",
        confidence=1.0,
        alternatives=(),
        target_sha256=hashlib.sha256(target_id.encode()).hexdigest(),
    )

    plan = ClassResolver(CATALOG_PATH, corpus).resolve(question, (match,))

    assert isinstance(plan, ResolutionPlan)
    assert isinstance(plan.entities[0], ResolvedEntity)
    assert plan.entities[0].fields == (
        FieldCandidate("token_transfer_facts", "to_address"),
        FieldCandidate("transaction_facts", "to_address"),
    )
    assert issubclass(ClassResolverError, ValueError)
