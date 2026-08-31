from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.linking.class_resolver import ClassResolver
from nl2sparql.linking.entity import (
    EntityAlternative,
    EntityCorpus,
    EntityMatch,
    EntityTarget,
    build_entity_corpus,
)
from nl2sparql.linking.resolver import ClassResolverError, FieldCandidate
from nl2sparql.linking.schema_linker import LinkResult, SchemaMatch
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


def _schema_match(element_id: str, kind: str) -> SchemaMatch:
    return SchemaMatch(element_id, kind, 1.0, 1.0, 1.0, "9" * 64)


def _ambiguous_match(
    question: str,
    span: str,
    corpus: EntityCorpus,
    alternative_ids: tuple[str, ...] = ("owner:Binance", "concept:exchange"),
) -> EntityMatch:
    primary = corpus.targets_by_id[alternative_ids[0]]
    start = question.index(span)
    alternatives = tuple(
        EntityAlternative(
            target_id=target_id,
            target_kind=corpus.targets_by_id[target_id].target_kind,
            confidence=0.51 - index * 0.01,
        )
        for index, target_id in enumerate(alternative_ids)
    )
    return EntityMatch(
        span=span,
        span_offset=(start, start + len(span)),
        target_id=primary.target_id,
        target_kind=primary.target_kind,
        owner=primary.owner,
        addresses=primary.addresses,
        categories=primary.categories,
        concept_classes=primary.concept_classes,
        stage="ambiguous",
        confidence=alternatives[0].confidence,
        alternatives=alternatives,
        target_sha256=primary.document_sha256,
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


@pytest.mark.parametrize("trigger", ["any", "all", "every", "major"])
def test_class_trigger_selects_the_only_concept_alternative(
    resolver: ClassResolver, corpus: EntityCorpus, trigger: str
) -> None:
    question = f"transactions to {trigger} exchange"
    match = _ambiguous_match(question, "exchange", corpus)

    entity = resolver.resolve(question, (match,)).entities[0]

    target = corpus.targets_by_id["concept:exchange"]
    assert entity.resolution_kind == "concept"
    assert entity.target_id == target.target_id
    assert entity.target_sha256 == target.document_sha256
    assert entity.confidence == pytest.approx(0.50)


def test_ambiguous_match_without_a_class_trigger_remains_unresolved(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "show exchange activity"

    plan = resolver.resolve(question, (_ambiguous_match(question, "exchange", corpus),))

    assert plan.status == "unresolved"
    assert plan.entities[0].resolution_kind == "unresolved"


def test_class_trigger_with_two_concept_alternatives_remains_unresolved(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to any exchange"
    match = _ambiguous_match(
        question,
        "exchange",
        corpus,
        ("owner:Binance", "concept:dex", "concept:exchange"),
    )

    assert resolver.resolve(question, (match,)).entities[0].resolution_kind == "unresolved"


@pytest.mark.parametrize(
    ("question", "expected"),
    (
        ("transactions from Binance", "from"),
        ("transactions sent by Binance", "from"),
        ("transactions out of Binance", "from"),
        ("transactions to Binance", "to"),
        ("transactions into Binance", "to"),
        ("funds received by Binance", "to"),
        ("show Binance activity", "unspecified"),
    ),
)
def test_direction_is_inferred_from_bounded_local_context(
    resolver: ClassResolver, corpus: EntityCorpus, question: str, expected: str
) -> None:
    match = _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"])

    assert resolver.resolve(question, (match,)).entities[0].direction == expected


def test_conflicting_local_direction_cues_remain_unspecified(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions from and to Binance"
    match = _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"])

    plan = resolver.resolve(question, (match,))

    assert plan.entities[0].direction == "unspecified"
    assert plan.status == "partial"


def test_schema_links_narrow_but_never_expand_catalog_fields(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to Binance"
    match = _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"])
    links = LinkResult(
        relations=(_schema_match("transaction_facts", "relation"),),
        fields=(_schema_match("transaction_facts.to_address", "field"),),
    )

    entity = resolver.resolve(question, (match,), links).entities[0]

    assert entity.fields == (FieldCandidate("transaction_facts", "to_address"),)


def test_schema_token_field_can_supply_token_direction(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "show USDC transfers"
    match = _target_match(question, "USDC", corpus.targets_by_id["owner:USDC"])
    links = LinkResult(
        relations=(_schema_match("token_transfer_facts", "relation"),),
        fields=(_schema_match("token_transfer_facts.token_address", "field"),),
    )

    entity = resolver.resolve(question, (match,), links).entities[0]

    assert entity.direction == "token"
    assert entity.fields == (FieldCandidate("token_transfer_facts", "token_address"),)


def test_unknown_schema_identity_fails_closed(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to Binance"
    match = _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"])
    links = LinkResult((), (_schema_match("invented_relation.to_address", "field"),))

    with pytest.raises(ClassResolverError, match="schema link"):
        resolver.resolve(question, (match,), links)


def test_empty_concept_coverage_is_explicit(resolver: ClassResolver, corpus: EntityCorpus) -> None:
    question = "transactions to any mixer"
    target = corpus.targets_by_id["concept:mixer"]

    entity = resolver.resolve(question, (_target_match(question, "mixer", target),)).entities[0]

    assert entity.coverage_status == "coverage_gap"
    assert entity.required_role is None
    assert "coverage" in entity.explanation.casefold()


def test_supported_concept_uses_the_common_accepted_address_role(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "transactions to any exchange"
    target = corpus.targets_by_id["concept:exchange"]

    entity = resolver.resolve(question, (_target_match(question, "exchange", target),)).entities[0]

    assert entity.coverage_status == "supported"
    assert entity.required_role == "treasury"


def test_two_mentions_with_the_same_direction_emit_a_conflict_warning(
    resolver: ClassResolver, corpus: EntityCorpus
) -> None:
    question = "from Binance and from USDC"
    matches = (
        _target_match(question, "Binance", corpus.targets_by_id["owner:Binance"]),
        _target_match(question, "USDC", corpus.targets_by_id["owner:USDC"]),
    )

    plan = resolver.resolve(question, matches)

    assert plan.status == "partial"
    assert plan.warnings == ("multiple entities resolve to direction 'from'",)
