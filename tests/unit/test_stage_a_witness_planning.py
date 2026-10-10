"""Tests for deterministic logical-to-physical Stage A witness planning."""

from __future__ import annotations

import hashlib

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a.evidence import WitnessEvidenceError, build_witness_groups
from nl2sparql.dataset.stage_a.planning import (
    build_single_witness_queries,
    build_stage_a_v2_witness_queries,
)
from nl2sparql.dataset.stage_a_v2 import generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates


@pytest.fixture(scope="module")
def records() -> list[dict[str, object]]:
    return generate_stage_a_v2_records(load_templates(), load_value_pools())


def test_default_planner_preserves_one_query_per_group_and_order(
    records: list[dict[str, object]],
) -> None:
    groups = build_witness_groups(records)
    queries = build_single_witness_queries(records)

    assert len(queries) == len(groups) == 170
    assert [query.group_ids for query in queries] == [(group.group_id,) for group in groups]
    assert all(query.proof_kind == "single" for query in queries)
    assert all(
        query.query_sha256 == hashlib.sha256(query.sql.encode()).hexdigest() for query in queries
    )


def test_v2_planner_batches_exact_transaction_hash_witnesses(
    records: list[dict[str, object]],
) -> None:
    queries = build_stage_a_v2_witness_queries(records)

    assert len(build_witness_groups(records)) == 170
    assert len(queries) == 126
    batch = next(query for query in queries if query.proof_kind == "tx_hash_batch")
    assert batch.template_id == "T_TX_BY_HASH"
    assert len(batch.group_ids) == 45
    assert batch.query_sha256 == hashlib.sha256(batch.sql.encode()).hexdigest()
    assert batch.sql.count("transaction_facts") == 1
    hashes = [
        str(record["slot_values"]["transaction_hash"])
        for record in records
        if record["template_id"] == "T_TX_BY_HASH"
    ]
    assert all(batch.sql.count(f"'{transaction_hash}'") == 1 for transaction_hash in hashes)


def test_v2_plan_is_deterministic_under_record_reordering(
    records: list[dict[str, object]],
) -> None:
    assert build_stage_a_v2_witness_queries(list(reversed(records))) == (
        build_stage_a_v2_witness_queries(records)
    )


@pytest.mark.parametrize("failure", ["invalid_group", "repeated_hash", "mixed_window", "singleton"])
def test_v2_batch_planner_rejects_ambiguous_inputs(
    records: list[dict[str, object]], failure: str
) -> None:
    changed = [dict(record) for record in records]
    hash_indexes = [
        index for index, record in enumerate(changed) if record["template_id"] == "T_TX_BY_HASH"
    ]
    if failure == "invalid_group":
        changed[hash_indexes[0]]["witness_group_id"] = "NOT-LOWERCASE-HEX"
    elif failure == "repeated_hash":
        first = changed[hash_indexes[0]]
        second = changed[hash_indexes[1]]
        second["slot_values"] = dict(second["slot_values"])
        second["slot_values"]["transaction_hash"] = first["slot_values"]["transaction_hash"]
    elif failure == "mixed_window":
        changed[hash_indexes[0]]["slot_values"] = dict(changed[hash_indexes[0]]["slot_values"])
        changed[hash_indexes[0]]["slot_values"]["end_date"] = "2026-06-17"
    else:
        changed = [changed[hash_indexes[0]]]

    with pytest.raises(WitnessEvidenceError):
        build_stage_a_v2_witness_queries(changed)
