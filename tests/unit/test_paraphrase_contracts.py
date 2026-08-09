"""Tests for SQL paraphrasing prompts, schemas, and quality gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nl2sparql.dataset.paraphrase.contracts import (
    STAGE_B_MODEL,
    STAGE_C_MODEL,
    ParaphraseValidationError,
    StageBResponse,
    StageCResponse,
    build_preserved_facts,
    load_entity_index,
    validate_preserved_facts,
)
from nl2sparql.dataset.paraphrase.prompts import (
    build_stage_b_request,
    build_stage_c_request,
)
from nl2sparql.dataset.paraphrase.quality import (
    mean_stage_c_distance,
    normalized_levenshtein,
    validate_question_anchors,
    validate_stage_c_questions,
)

STAGE_A_PATH = Path("data/dataset/raw/synthetic-stage-a.jsonl")


@pytest.fixture(scope="module")
def records() -> list[dict[str, object]]:
    return [json.loads(line) for line in STAGE_A_PATH.read_text().splitlines()]


@pytest.fixture(scope="module")
def entity_index() -> dict[str, dict[str, str]]:
    return load_entity_index()


def record_for(records: list[dict[str, object]], template_id: str) -> dict[str, object]:
    return next(record for record in records if record["template_id"] == template_id)


def test_structured_responses_are_strict_and_trimmed() -> None:
    stage_b = StageBResponse(
        question="  How many transactions occurred?  ",
        preserved_facts=["start_date=2026-06-01"],
    )
    stage_c = StageCResponse(
        casual=" How many transactions happened? ",
        abbreviated=" Transaction count? ",
        alternative=" What was the number of transactions? ",
        preserved_facts=["start_date=2026-06-01"],
    )

    assert stage_b.question == "How many transactions occurred?"
    assert stage_c.casual == "How many transactions happened?"
    with pytest.raises(ValidationError, match="extra"):
        StageBResponse(
            question="How many transactions occurred?",
            preserved_facts=["start_date=2026-06-01"],
            unexpected=True,
        )
    with pytest.raises(ValidationError, match="code fence"):
        StageBResponse(question="```sql SELECT 1```", preserved_facts=[])


def test_preserved_facts_are_canonical_and_must_match_exactly(
    records: list[dict[str, object]],
) -> None:
    record = record_for(records, "T_TOKEN_AFTER_NATIVE_FUNDING")

    facts = build_preserved_facts(record)

    assert facts == [
        "duration_minutes=60",
        "end_date=2026-06-16",
        "n=1",
        "start_date=2026-06-15",
    ]
    validate_preserved_facts(facts, record)
    with pytest.raises(ParaphraseValidationError, match="preserved facts"):
        validate_preserved_facts(facts[:-1], record)


def test_entity_index_exposes_address_owner_and_primary_label(
    entity_index: dict[str, dict[str, str]],
) -> None:
    gate = entity_index["0x0d0707963952f2fba59dd06f2b425ace40b492fe"]

    assert gate == {
        "owner": "Gate.io",
        "primary_label": "Gate.io: Ethereum treasury",
    }


def test_stage_b_prompt_is_sql_specific_stable_and_context_rich(
    records: list[dict[str, object]], entity_index: dict[str, dict[str, str]]
) -> None:
    record = record_for(records, "T_LIST_TX_FROM_ACCOUNT")

    first = build_stage_b_request(record, entity_index)
    second = build_stage_b_request(record, entity_index)

    assert first == second
    assert first.stage == "stage_b"
    assert first.model == STAGE_B_MODEL
    assert first.temperature == 0.0
    assert "GoogleSQL" in first.system_prompt
    assert "SPARQL" not in first.system_prompt
    assert record["sql"] in first.user_prompt
    assert "Gate.io" in first.user_prompt
    assert "account=0x0d0707963952f2fba59dd06f2b425ace40b492fe" in first.user_prompt
    assert len(first.prompt_sha256) == 64


def test_stage_c_prompt_uses_formal_question_not_sql_generation(
    records: list[dict[str, object]], entity_index: dict[str, dict[str, str]]
) -> None:
    source = record_for(records, "T_TOKEN_TRANSFERS_OF_TOKEN")
    stage_b_record = {
        **source,
        "nl_formal": "List 1 USDC transfer between 2026-06-15 and 2026-06-16.",
        "stage_b": {"preserved_facts": build_preserved_facts(source)},
    }

    request = build_stage_c_request(stage_b_record, entity_index)

    assert request.stage == "stage_c"
    assert request.model == STAGE_C_MODEL
    assert request.temperature == 0.7
    assert stage_b_record["nl_formal"] in request.user_prompt
    assert "Do not rewrite or output SQL" in request.system_prompt
    assert request.response_schema["required"] == [
        "casual",
        "abbreviated",
        "alternative",
        "preserved_facts",
    ]


def test_anchor_validation_accepts_entity_alias_and_rejects_lost_facts(
    records: list[dict[str, object]], entity_index: dict[str, dict[str, str]]
) -> None:
    record = record_for(records, "T_LIST_TX_FROM_ACCOUNT")
    valid = "Which 1 transaction did Gate.io send between 2026-06-15 and 2026-06-16?"

    validate_question_anchors(valid, record, entity_index)
    with pytest.raises(ParaphraseValidationError, match="account"):
        validate_question_anchors(
            "Which 1 transaction was sent between 2026-06-15 and 2026-06-16?",
            record,
            entity_index,
        )
    with pytest.raises(ParaphraseValidationError, match="n"):
        validate_question_anchors(
            "Which transactions did Gate.io send between 2026-06-15 and 2026-06-16?",
            record,
            entity_index,
        )


def test_anchor_validation_accepts_human_dates_and_preserves_token_symbol(
    records: list[dict[str, object]], entity_index: dict[str, dict[str, str]]
) -> None:
    record = record_for(records, "T_TOKEN_TRANSFERS_OF_TOKEN")

    validate_question_anchors(
        "Show 1 USDC transfer from June 15, 2026 through June 16, 2026.",
        record,
        entity_index,
    )
    with pytest.raises(ParaphraseValidationError, match="token_symbol"):
        validate_question_anchors(
            "Show 1 token transfer from June 15, 2026 through June 16, 2026.",
            record,
            entity_index,
        )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("same", "same", 0.0),
        ("", "abc", 1.0),
        ("kitten", "sitting", 3 / 7),
    ],
)
def test_normalized_levenshtein_known_values(left: str, right: str, expected: float) -> None:
    assert normalized_levenshtein(left, right) == pytest.approx(expected)


def test_stage_c_quality_rejects_duplicates_and_measures_all_pairs(
    records: list[dict[str, object]], entity_index: dict[str, dict[str, str]]
) -> None:
    record = record_for(records, "T_COUNT_TX_IN_RANGE")
    response = StageCResponse(
        casual="How many transactions happened from 2026-06-01 to 2026-06-02?",
        abbreviated="Transaction count, 2026-06-01–2026-06-02?",
        alternative="Between 2026-06-01 and 2026-06-02, what was the transaction total?",
        preserved_facts=build_preserved_facts(record),
    )

    distances = validate_stage_c_questions(response, record, entity_index)

    assert len(distances) == 3
    assert mean_stage_c_distance([distances]) == pytest.approx(sum(distances) / 3)
    duplicate = response.model_copy(update={"abbreviated": response.casual.upper()})
    with pytest.raises(ParaphraseValidationError, match="unique"):
        validate_stage_c_questions(duplicate, record, entity_index)
