"""Tests for deterministic T3.2 GoogleSQL Stage A generation."""

from __future__ import annotations

from collections import Counter

import pytest

from nl2sparql.dataset.generate import (
    DEFAULT_VALUE_POOLS_PATH,
    StageAGenerationError,
    generate_stage_a_records,
    load_value_pools,
    validate_stage_a_records,
)
from nl2sparql.dataset.templates import load_templates, render_template

EXPECTED_DIFFICULTIES = {"easy": 350, "medium": 450, "hard": 200}
EXPECTED_TEMPLATE_COUNTS = {
    "T_COUNT_TX_IN_RANGE": 59,
    "T_LIST_TX_FROM_ACCOUNT": 59,
    "T_LIST_TX_TO_ACCOUNT": 58,
    "T_FILTER_TX_BY_VALUE": 58,
    "T_LIST_FAILED_TX": 58,
    "T_LIST_KNOWN_EXCHANGES": 58,
    "T_TOP_SENDERS_BY_VALUE": 57,
    "T_TOP_RECIPIENTS_BY_COUNT": 57,
    "T_TX_GROUPED_BY_OWNER": 56,
    "T_TOKEN_VOLUME_BY_SYMBOL": 56,
    "T_TOKEN_TRANSFERS_OF_TOKEN": 56,
    "T_FAILED_HIGH_GAS_TX": 56,
    "T_ACCOUNTS_BY_CATEGORY": 56,
    "T_TX_BY_HOUR": 56,
    "T_TOKEN_AFTER_NATIVE_FUNDING": 100,
    "T_REPEATED_PAIR_FLOW": 100,
}
RECORD_FIELDS = {
    "id",
    "template_id",
    "category",
    "difficulty",
    "slot_values",
    "entities_used",
    "sql",
    "nl_seed",
    "schema_elements",
    "cq_ids",
    "template_sha256",
    "record_sha256",
    "generation_seed",
    "witness_group_id",
    "verification",
}


@pytest.fixture(scope="module")
def templates() -> list[dict[str, object]]:
    return load_templates()


@pytest.fixture(scope="module")
def value_pools() -> dict[str, object]:
    return load_value_pools()


@pytest.fixture(scope="module")
def records(
    templates: list[dict[str, object]], value_pools: dict[str, object]
) -> list[dict[str, object]]:
    return generate_stage_a_records(templates, value_pools, target_count=1000, seed=42)


def test_value_pools_are_pinned_and_provenance_bearing(
    value_pools: dict[str, object],
) -> None:
    assert DEFAULT_VALUE_POOLS_PATH.name == "value_pools.json"
    assert value_pools["version"] == 1
    assert value_pools["window"] == {
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }
    assert len(value_pools["ethereum_address"]) >= 4
    assert len(value_pools["token_symbol"]) >= 2
    for kind in ("ethereum_address", "token_symbol"):
        assert all({"value", "source", "evidence"} <= set(item) for item in value_pools[kind])


def test_generation_is_byte_stable_for_seed_42(
    templates: list[dict[str, object]], value_pools: dict[str, object]
) -> None:
    first = generate_stage_a_records(templates, value_pools, target_count=1000, seed=42)
    second = generate_stage_a_records(templates, value_pools, target_count=1000, seed=42)

    assert first == second
    assert [record["id"] for record in first] == [f"syn-{index:06d}" for index in range(1000)]
    assert all(record["generation_seed"] == 42 for record in first)
    assert all(record["verification"] is None for record in first)


def test_records_use_only_the_google_sql_contract(
    records: list[dict[str, object]], templates: list[dict[str, object]]
) -> None:
    templates_by_id = {template["id"]: template for template in templates}

    assert len(records) == 1000
    assert len({record["sql"] for record in records}) == 1000
    assert len({record["record_sha256"] for record in records}) == 1000
    for record in records:
        assert set(record) == RECORD_FIELDS
        assert "sparql" not in record
        assert record["sql"].lstrip().upper().startswith(("SELECT", "WITH"))
        assert "nl2sparql-thesis.nl2sparql_analytics" in record["sql"]
        assert record["sql"] == render_template(
            templates_by_id[record["template_id"]], record["slot_values"]
        )
        assert len(record["template_sha256"]) == 64
        assert len(record["record_sha256"]) == 64
        assert len(record["witness_group_id"]) == 64


def test_generation_meets_accepted_distribution_and_caps(
    records: list[dict[str, object]],
) -> None:
    difficulties = Counter(record["difficulty"] for record in records)
    templates = Counter(record["template_id"] for record in records)
    entities = Counter(entity["value"] for record in records for entity in record["entities_used"])

    assert difficulties == EXPECTED_DIFFICULTIES
    assert templates == EXPECTED_TEMPLATE_COUNTS
    assert max(templates.values()) <= 100
    assert entities
    assert max(entities.values()) <= 50


def test_entities_are_derived_from_typed_slots(records: list[dict[str, object]]) -> None:
    address_record = next(
        record for record in records if record["template_id"] == "T_LIST_TX_FROM_ACCOUNT"
    )
    token_record = next(
        record for record in records if record["template_id"] == "T_TOKEN_TRANSFERS_OF_TOKEN"
    )

    assert address_record["entities_used"] == [
        {
            "slot": "account",
            "type": "ethereum_address",
            "value": address_record["slot_values"]["account"],
        }
    ]
    assert token_record["entities_used"] == [
        {
            "slot": "token_symbol",
            "type": "token_symbol",
            "value": token_record["slot_values"]["token_symbol"],
        }
    ]


def test_witness_groups_ignore_only_limit_slot(records: list[dict[str, object]]) -> None:
    limit_records = [
        record for record in records if record["template_id"] == "T_REPEATED_PAIR_FLOW"
    ]
    count_records = [record for record in records if record["template_id"] == "T_COUNT_TX_IN_RANGE"]

    assert len({record["witness_group_id"] for record in limit_records}) == 1
    assert len({record["witness_group_id"] for record in count_records}) == len(count_records)


def test_generation_fails_closed_for_wrong_target_or_tampering(
    templates: list[dict[str, object]], value_pools: dict[str, object], records
) -> None:
    with pytest.raises(StageAGenerationError, match="exactly 1000"):
        generate_stage_a_records(templates, value_pools, target_count=999, seed=42)
    with pytest.raises(StageAGenerationError, match="seed 42"):
        generate_stage_a_records(templates, value_pools, target_count=1000, seed=7)

    tampered = [dict(record) for record in records]
    tampered[1]["sql"] = tampered[0]["sql"]
    with pytest.raises(StageAGenerationError, match="unique SQL"):
        validate_stage_a_records(tampered, templates)
