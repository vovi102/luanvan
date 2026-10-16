"""Tests for the deterministic 25-intent Stage A v2 candidate."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from nl2sparql.dataset.generate import RECORD_FIELDS, load_value_pools
from nl2sparql.dataset.stage_a.account_pairs import canonical_account_pair_mappings
from nl2sparql.dataset.stage_a_v2 import (
    V2_DIFFICULTY_ALLOCATION,
    V2_TEMPLATE_ALLOCATION,
    StageAV2GenerationError,
    generate_stage_a_v2_records,
    serialize_stage_a_v2_records,
    validate_stage_a_v2_records,
)
from nl2sparql.dataset.templates import load_templates, render_template


@pytest.fixture(scope="module")
def templates() -> list[dict[str, object]]:
    return load_templates()


@pytest.fixture(scope="module")
def pools() -> dict[str, object]:
    return load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))


@pytest.fixture(scope="module")
def records(
    templates: list[dict[str, object]], pools: dict[str, object]
) -> list[dict[str, object]]:
    return generate_stage_a_v2_records(templates, pools)


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def test_v2_allocation_covers_25_intents_and_preserves_scientific_caps(
    records: list[dict[str, object]],
) -> None:
    template_counts = Counter(record["template_id"] for record in records)
    difficulty_counts = Counter(record["difficulty"] for record in records)
    entity_counts = Counter(
        entity["value"] for record in records for entity in record["entities_used"]
    )

    assert len(records) == 1000
    assert len(template_counts) == 25
    assert template_counts == V2_TEMPLATE_ALLOCATION
    assert (
        difficulty_counts
        == V2_DIFFICULTY_ALLOCATION
        == {
            "easy": 350,
            "medium": 450,
            "hard": 200,
        }
    )
    assert max(template_counts.values()) <= 100
    assert max(entity_counts.values()) <= 50
    assert len({record["id"] for record in records}) == 1000
    assert len({record["sql"] for record in records}) == 1000
    assert len({record["record_sha256"] for record in records}) == 1000


def test_v2_records_preserve_the_production_template_contract(
    records: list[dict[str, object]], templates: list[dict[str, object]]
) -> None:
    template_index = {template["id"]: template for template in templates}

    for index, record in enumerate(records):
        template = template_index[record["template_id"]]
        assert set(record) == RECORD_FIELDS
        assert record["id"] == f"syn-v2-{index:06d}"
        assert record["sql"] == render_template(template, record["slot_values"])
        assert record["nl_seed"] == template["nl_seed"].format(**record["slot_values"])
        assert record["category"] == template["category"]
        assert record["difficulty"] == template["difficulty"]
        assert record["schema_elements"] == template["schema_elements"]
        assert record["cq_ids"] == template["cq_ids"]
        assert record["template_sha256"] == _digest(template)
        assert record["verification"] is None


def test_v2_generation_is_stable_under_template_input_order(
    records: list[dict[str, object]],
    templates: list[dict[str, object]],
    pools: dict[str, object],
) -> None:
    reordered = generate_stage_a_v2_records(list(reversed(templates)), pools)

    assert reordered == records
    assert serialize_stage_a_v2_records(reordered) == serialize_stage_a_v2_records(records)
    assert serialize_stage_a_v2_records(records).endswith(b"\n")


def test_v2_generation_is_stable_under_pool_and_slot_input_order(
    records: list[dict[str, object]],
    templates: list[dict[str, object]],
    pools: dict[str, object],
) -> None:
    reordered_pools = copy.deepcopy(pools)
    for key, entries in reordered_pools.items():
        if isinstance(entries, list):
            reordered_pools[key] = list(reversed(entries))
    reordered_templates = copy.deepcopy(templates)
    for template in reordered_templates:
        template["slots"] = dict(reversed(list(template["slots"].items())))

    reordered = generate_stage_a_v2_records(reordered_templates, reordered_pools)

    assert reordered == records
    assert serialize_stage_a_v2_records(reordered) == serialize_stage_a_v2_records(records)


def test_v2_candidate_varies_data_bound_hash_and_block_slots(
    records: list[dict[str, object]],
) -> None:
    hashes = [
        record["slot_values"]["transaction_hash"]
        for record in records
        if record["template_id"] == "T_TX_BY_HASH"
    ]
    blocks = [
        record["slot_values"]["block_number"]
        for record in records
        if record["template_id"] == "T_BLOCK_BY_NUMBER"
    ]

    assert len(hashes) == len(set(hashes)) == V2_TEMPLATE_ALLOCATION["T_TX_BY_HASH"]
    assert len(blocks) == len(set(blocks)) == V2_TEMPLATE_ALLOCATION["T_BLOCK_BY_NUMBER"]
    assert all(value.startswith("0x") and len(value) == 66 for value in hashes)


def test_between_accounts_consumes_verified_pairs_atomically(
    records: list[dict[str, object]], pools: dict[str, object]
) -> None:
    pair_records = [
        record for record in records if record["template_id"] == "T_TX_BETWEEN_ACCOUNTS"
    ]
    canonical_pairs = canonical_account_pair_mappings(pools)

    assert len(pair_records) == len(canonical_pairs) == 40
    for record, pair in zip(pair_records, canonical_pairs, strict=True):
        slots = record["slot_values"]
        assert isinstance(slots, dict)
        assert {
            name: slots[name] for name in ("account", "account_b", "start_date", "end_date")
        } == {name: pair[name] for name in ("account", "account_b", "start_date", "end_date")}
    failed_pair = frozenset(
        {
            "0x8fca4ade3a517133ff23ca55cdaea29c78c990b8",
            "0x77021d475e36b3ab1921a0e3a8380f069d3263de",
        }
    )
    evidenced_pairs = {
        frozenset({str(pair["account"]), str(pair["account_b"])}) for pair in canonical_pairs
    }
    generated_pairs = {
        frozenset({str(record["slot_values"]["account"]), str(record["slot_values"]["account_b"])})
        for record in pair_records
    }
    assert failed_pair not in generated_pairs
    assert generated_pairs == evidenced_pairs


@pytest.mark.parametrize(
    "mutation",
    ["missing", "empty", "short", "malformed", "endpoint_copy", "window_copy", "evidence_copy"],
)
def test_v2_generation_fails_closed_on_invalid_relationship_pool(
    templates: list[dict[str, object]], pools: dict[str, object], mutation: str
) -> None:
    changed = copy.deepcopy(pools)
    entries = changed["account_pair"]
    assert isinstance(entries, list)
    if mutation == "missing":
        changed.pop("account_pair")
    elif mutation == "empty":
        changed["account_pair"] = []
    elif mutation == "short":
        entries.pop()
    elif mutation == "malformed":
        entries[0] = "not-an-object"
    elif mutation == "endpoint_copy":
        entries[1]["account"] = entries[0]["account"]
    elif mutation == "window_copy":
        entries[1]["start_date"] = "2026-06-14"
    else:
        entries[1]["evidence"] = copy.deepcopy(entries[0]["evidence"])

    with pytest.raises(StageAV2GenerationError, match="account"):
        generate_stage_a_v2_records(templates, changed)


def test_v2_validation_rejects_coverage_and_digest_tampering(
    records: list[dict[str, object]], templates: list[dict[str, object]]
) -> None:
    missing_intent = [dict(record) for record in records]
    replacement_template = next(
        record["template_id"]
        for record in records
        if record["template_id"] != missing_intent[0]["template_id"]
    )
    missing_intent[0]["template_id"] = replacement_template
    with pytest.raises(StageAV2GenerationError, match="allocation"):
        validate_stage_a_v2_records(missing_intent, templates)

    bad_digest = [dict(record) for record in records]
    bad_digest[0]["record_sha256"] = "0" * 64
    with pytest.raises(StageAV2GenerationError, match="record hash"):
        validate_stage_a_v2_records(bad_digest, templates)


def test_v2_generation_rejects_noncanonical_target_or_seed(
    templates: list[dict[str, object]], pools: dict[str, object]
) -> None:
    with pytest.raises(StageAV2GenerationError, match="exactly 1000"):
        generate_stage_a_v2_records(templates, pools, target_count=999)
    with pytest.raises(StageAV2GenerationError, match="seed 42"):
        generate_stage_a_v2_records(templates, pools, seed=7)
