from __future__ import annotations

import hashlib
from collections.abc import Callable

import pytest

from nl2sparql.dataset.templates import TEMPLATES_PATH
from nl2sparql.linking.resolver import ResolutionPlan, ResolvedEntity
from nl2sparql.models.b0 import B0Policy, CompiledTemplate, compile_template_snapshot
from nl2sparql.models.b0.slots import (
    extract_seed_slots,
    extract_structural_slots,
    slot_mapping,
)

ADDRESS_A = "0x1111111111111111111111111111111111111111"
ADDRESS_B = "0x2222222222222222222222222222222222222222"
_DIGEST = "a" * 64


@pytest.fixture
def template_lookup() -> Callable[[str], CompiledTemplate]:
    templates = compile_template_snapshot(TEMPLATES_PATH, B0Policy())
    by_id = {template.template_id: template for template in templates}
    return by_id.__getitem__


def _plan(
    question: str,
    entity: ResolvedEntity,
    *,
    status: str = "resolved",
    warnings: tuple[str, ...] = (),
) -> ResolutionPlan:
    return ResolutionPlan(
        question_sha256=hashlib.sha256(question.encode()).hexdigest(),
        entities=(entity,),
        catalog_sha256=_DIGEST,
        entities_sha256=_DIGEST,
        aliases_sha256=_DIGEST,
        concepts_sha256=_DIGEST,
        status=status,
        warnings=warnings,
    )


def _instance(question: str, span: str, values: tuple[str, ...]) -> ResolutionPlan:
    start = question.index(span)
    entity = ResolvedEntity(
        span=span,
        span_offset=(start, start + len(span)),
        target_id="owner:test",
        target_sha256=_DIGEST,
        resolution_kind="instance",
        direction="from",
        fields=(),
        operator="in",
        values=values,
        required_relation=None,
        required_join=None,
        required_role=None,
        coverage_status="supported",
        confidence=1.0,
        explanation="Verified owner address.",
    )
    return _plan(question, entity)


def _concept(question: str, *, coverage: str = "supported") -> ResolutionPlan:
    span = "DEX protocols"
    start = question.index(span)
    entity = ResolvedEntity(
        span=span,
        span_offset=(start, start + len(span)),
        target_id="concept:dex",
        target_sha256=_DIGEST,
        resolution_kind="concept",
        direction="to",
        fields=(),
        operator="equals",
        values=("DEXProtocol",),
        required_relation="entity_labels_v1",
        required_join="fact_address_to_entity",
        required_role="operational",
        coverage_status=coverage,
        confidence=1.0,
        explanation="Catalog concept coverage.",
    )
    if coverage == "supported":
        return _plan(question, entity)
    return _plan(question, entity, status="partial", warnings=("coverage gap",))


def test_seed_slots_parse_dates_numbers_and_address(template_lookup) -> None:
    template = template_lookup("T_LIST_TX_FROM_ACCOUNT")
    question = f"List 10 transactions sent by {ADDRESS_A} between 2026-06-15 and 2026-06-16."
    match = template.seed_pattern.fullmatch(question)
    assert match is not None

    slots = extract_seed_slots(template, question, match, None)

    assert slot_mapping(slots or ()) == {
        "n": 10,
        "account": ADDRESS_A,
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }


def test_seed_slots_reject_out_of_range_value(template_lookup) -> None:
    template = template_lookup("T_LIST_KNOWN_EXCHANGES")
    question = "List 101 known exchange treasury accounts."
    match = template.seed_pattern.fullmatch(question)
    assert match is not None

    assert extract_seed_slots(template, question, match, None) is None


def test_structural_slots_assign_repeated_values_in_source_order(template_lookup) -> None:
    template = template_lookup("T_TX_BETWEEN_ACCOUNTS")
    question = (
        f"Find 5 transfers involving {ADDRESS_A} and {ADDRESS_B} from 2026-06-15 through 2026-06-16"
    )

    slots = extract_structural_slots(template, question, None)

    assert slot_mapping(slots or ()) == {
        "n": 5,
        "account": ADDRESS_A,
        "account_b": ADDRESS_B,
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }


def test_owner_evidence_must_resolve_to_one_address(template_lookup) -> None:
    template = template_lookup("T_LIST_TX_FROM_ACCOUNT")
    question = "List 10 transactions sent by Binance between 2026-06-15 and 2026-06-16."

    slots = extract_structural_slots(
        template, question, _instance(question, "Binance", (ADDRESS_A,))
    )

    assert slot_mapping(slots or ())["account"] == ADDRESS_A


def test_multi_address_owner_rejects_scalar_slot(template_lookup) -> None:
    template = template_lookup("T_LIST_TX_FROM_ACCOUNT")
    question = "List 10 transactions sent by Binance between 2026-06-15 and 2026-06-16."

    slots = extract_structural_slots(
        template,
        question,
        _instance(question, "Binance", (ADDRESS_A, ADDRESS_B)),
    )

    assert slots is None


def test_supported_concept_fills_catalog_class(template_lookup) -> None:
    template = template_lookup("T_LARGE_TX_TO_CLASS")
    question = (
        "Find 10 transfers of at least 1000 wei to DEX protocols between 2026-06-15 and 2026-06-16"
    )

    slots = extract_structural_slots(template, question, _concept(question))

    assert slot_mapping(slots or ())["concept_class"] == "DEXProtocol"


def test_coverage_gap_rejects_concept_slot(template_lookup) -> None:
    template = template_lookup("T_LARGE_TX_TO_CLASS")
    question = (
        "Find 10 transfers of at least 1000 wei to DEX protocols between 2026-06-15 and 2026-06-16"
    )

    assert (
        extract_structural_slots(template, question, _concept(question, coverage="coverage_gap"))
        is None
    )
