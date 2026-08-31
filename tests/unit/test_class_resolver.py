from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.linking.class_resolver import ClassResolver
from nl2sparql.linking.entity import EntityCorpus, EntityMatch, EntityTarget, build_entity_corpus
from nl2sparql.linking.resolver import ClassResolverError, FieldCandidate
from nl2sparql.sql.schema import CATALOG_PATH


@pytest.fixture(scope="module")
def corpus() -> EntityCorpus:
    return build_entity_corpus()


@pytest.fixture(scope="module")
def resolver(corpus: EntityCorpus) -> ClassResolver:
    return ClassResolver(CATALOG_PATH, corpus)


def _target_match(question: str, span: str, target: EntityTarget) -> EntityMatch:
    start = question.index(span)
    return EntityMatch(
        span=span,
        span_offset=(start, start + len(span)),
        target_id=target.target_id,
        target_kind=target.target_kind,
        owner=target.owner,
        addresses=target.addresses,
        categories=target.categories,
        concept_classes=target.concept_classes,
        stage="exact",
        confidence=0.99,
        alternatives=(),
        target_sha256=target.document_sha256,
    )


def _raw_address_match(question: str, address: str) -> EntityMatch:
    start = question.index(address)
    target_id = f"address:{address}"
    return EntityMatch(
        span=address,
        span_offset=(start, start + len(address)),
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


def test_owner_resolves_to_canonical_address_membership(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to Binance"
    target = corpus.targets_by_id["owner:Binance"]

    plan = resolver.resolve(question, (_target_match(question, "Binance", target),))

    entity = plan.entities[0]
    assert plan.status == "resolved"
    assert entity.resolution_kind == "instance"
    assert entity.direction == "to"
    assert entity.operator == "in"
    assert entity.values == target.addresses
    assert entity.fields == (
        FieldCandidate("token_transfer_facts", "to_address"),
        FieldCandidate("transaction_facts", "to_address"),
    )


def test_unknown_raw_address_keeps_the_t42_self_authenticating_contract(
    resolver: ClassResolver,
) -> None:
    address = "0x" + "1" * 40
    question = f"transactions from {address}"

    plan = resolver.resolve(question, (_raw_address_match(question, address),))

    entity = plan.entities[0]
    assert entity.resolution_kind == "instance"
    assert entity.values == (address,)
    assert entity.direction == "from"


def test_concept_resolves_through_the_catalog_label_join(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to any exchange"
    target = corpus.targets_by_id["concept:exchange"]

    plan = resolver.resolve(question, (_target_match(question, "exchange", target),))

    entity = plan.entities[0]
    assert entity.resolution_kind == "concept"
    assert entity.operator == "equals"
    assert entity.values == ("ExchangeAccount",)
    assert entity.required_relation == "entity_labels_v1"
    assert entity.required_join == "fact_address_to_entity"
    assert entity.fields == (
        FieldCandidate("token_transfer_facts", "to_address"),
        FieldCandidate("transaction_facts", "to_address"),
    )


def test_empty_matches_return_an_unresolved_provenance_only_plan(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "show recent activity"

    plan = resolver.resolve(question, ())

    assert plan.status == "unresolved"
    assert plan.entities == ()
    assert plan.warnings == ("no entity evidence was supplied",)
    assert plan.question_sha256 == hashlib.sha256(question.encode()).hexdigest()
    assert plan.entities_sha256 == corpus.entities_sha256


@pytest.mark.parametrize("question", ["", "   ", "bad\x00question", "x" * 2_001])
def test_resolver_rejects_invalid_questions(resolver: ClassResolver, question: str) -> None:
    with pytest.raises(ClassResolverError, match="question"):
        resolver.resolve(question, ())


def test_resolver_rejects_a_span_that_is_not_the_original_question_slice(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to Binance"
    match = _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"])

    with pytest.raises(ClassResolverError, match="slice"):
        resolver.resolve(question, (replace(match, span="binance"),))


def test_resolver_rejects_stale_owner_target_evidence(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to Binance"
    match = _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"])

    with pytest.raises(ClassResolverError, match="fingerprint"):
        resolver.resolve(question, (replace(match, target_sha256="0" * 64),))


def test_resolver_rejects_unknown_owner_target(resolver: ClassResolver) -> None:
    question = "transactions to Missing Owner"
    match = EntityMatch(
        span="Missing Owner",
        span_offset=(16, 29),
        target_id="owner:Missing%20Owner",
        target_kind="owner",
        owner="Missing Owner",
        addresses=("0x" + "2" * 40,),
        categories=(),
        concept_classes=(),
        stage="exact",
        confidence=1.0,
        alternatives=(),
        target_sha256="3" * 64,
    )

    with pytest.raises(ClassResolverError, match="unknown target"):
        resolver.resolve(question, (match,))


def test_resolver_rejects_unsorted_or_overlapping_evidence(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "Binance to Binance"
    target = corpus.targets_by_id["owner:Binance"]
    first = _target_match(question, "Binance", target)
    second = replace(first, span_offset=(11, 18))

    with pytest.raises(ClassResolverError, match="ordered"):
        resolver.resolve(question, (second, first))
    with pytest.raises(ClassResolverError, match="overlap"):
        resolver.resolve(question, (first, replace(second, span_offset=(6, 13))))


def test_constructor_rejects_noncorpus_dependency() -> None:
    with pytest.raises(ClassResolverError, match="corpus"):
        ClassResolver(Path("missing.json"), object())  # type: ignore[arg-type]
