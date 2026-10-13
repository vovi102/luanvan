"""Contract tests for relationship-proven Stage A account pairs."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nl2sparql.dataset.stage_a.account_pairs import (
    AccountPair,
    AccountPairError,
    AccountPairEvidence,
    canonical_account_pair_mappings,
    load_account_pairs,
)

POOL_PATH = Path("data/dataset/raw/stage-a-v2-evidence-pools.json")
JOB_ID = "d7aa2151-18e4-4f3f-99c4-2c255bdbfe0e"
QUERY_SHA256 = "d85c553b8fef8621e68f847b31179b80e4b7bbab6397c7c8ed5a01b06569436d"


def _evidence(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "project": "nl2sparql-thesis",
        "location": "US",
        "job_id": JOB_ID,
        "query_sha256": QUERY_SHA256,
        "result_row": 1,
        "transaction_count": 3,
        "first_seen_at": "2026-06-15T00:00:11+00:00",
        "last_seen_at": "2026-06-15T23:59:59+00:00",
        "total_bytes_processed": 190_675_508,
        "total_bytes_billed": 190_840_832,
        "cache_hit": False,
        "billing_enabled": False,
        "maximum_bytes_billed": 1_073_741_824,
    }
    value.update(overrides)
    return value


def _pair(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "account": "0x0000000000000000000000000000000000000001",
        "account_b": "0x0000000000000000000000000000000000000002",
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
        "source": "BigQuery nl2sparql_analytics.transaction_facts",
        "evidence": _evidence(),
    }
    value.update(overrides)
    return value


def _two_pair_pool() -> dict[str, object]:
    second = _pair(
        account="0x0000000000000000000000000000000000000003",
        account_b="0x0000000000000000000000000000000000000004",
        evidence=_evidence(result_row=2),
    )
    return {"account_pair": [_pair(), second]}


def test_committed_pool_has_complete_relationship_provenance() -> None:
    pools = json.loads(POOL_PATH.read_text())

    pairs = load_account_pairs(pools)

    assert len(pairs) == 40
    endpoints = [endpoint for pair in pairs for endpoint in (pair.account, pair.account_b)]
    assert len(set(endpoints)) == 80
    assert endpoints == [endpoint.lower() for endpoint in endpoints]
    assert all(pair.account < pair.account_b for pair in pairs)
    assert {(pair.start_date, pair.end_date) for pair in pairs} == {("2026-06-15", "2026-06-16")}
    assert {pair.evidence.job_id for pair in pairs} == {JOB_ID}
    assert {pair.evidence.query_sha256 for pair in pairs} == {QUERY_SHA256}
    assert {pair.evidence.maximum_bytes_billed for pair in pairs} == {1_073_741_824}
    assert {pair.evidence.cache_hit for pair in pairs} == {False}
    assert {pair.evidence.billing_enabled for pair in pairs} == {False}
    assert all(pair.evidence.transaction_count > 0 for pair in pairs)
    rows = [pair.evidence.result_row for pair in pairs]
    assert len(set(rows)) == len(rows)
    assert all(row > 0 for row in rows)


def test_dataclasses_are_frozen_and_round_trip_exactly() -> None:
    pair = AccountPair.from_mapping(_pair())

    assert pair.to_mapping() == _pair()
    assert AccountPair.from_mapping(pair.to_mapping()) == pair
    assert AccountPairEvidence.from_mapping(_evidence()).to_mapping() == _evidence()
    with pytest.raises(FrozenInstanceError):
        pair.account = "0x0000000000000000000000000000000000000009"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value.pop("source"), "fields"),
        (lambda value: value.update(extra="unexpected"), "fields"),
        (lambda value: value.update(account=value["account_b"]), "differ"),
        (lambda value: value.update(account="0xABC"), "address"),
        (
            lambda value: value.update(account_b="0x0000000000000000000000000000000000000000"),
            "order",
        ),
        (lambda value: value.update(start_date="2026-02-30"), "date"),
        (lambda value: value.update(start_date="2026-06-14"), "window"),
        (lambda value: value.update(source=""), "source"),
    ],
)
def test_pair_rejects_invalid_schema_and_bound_values(mutate, match: str) -> None:
    value = _pair()
    mutate(value)

    with pytest.raises(AccountPairError, match=match):
        AccountPair.from_mapping(value)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("project", "other", "project"),
        ("location", "EU", "location"),
        ("job_id", "", "job_id"),
        ("query_sha256", "", "query_sha256"),
        ("query_sha256", "f" * 64, "query_sha256"),
        ("result_row", 0, "result_row"),
        ("result_row", True, "result_row"),
        ("transaction_count", 0, "transaction_count"),
        ("transaction_count", True, "transaction_count"),
        ("first_seen_at", "not-a-timestamp", "first_seen_at"),
        ("first_seen_at", "2026-06-15T00:00:11+01:00", "UTC"),
        ("first_seen_at", "2026-06-14T23:59:59+00:00", "window"),
        ("last_seen_at", "2026-06-16T00:00:00+00:00", "window"),
        ("total_bytes_processed", -1, "total_bytes_processed"),
        ("total_bytes_billed", -1, "total_bytes_billed"),
        ("total_bytes_billed", 190_000_000, "bytes"),
        ("total_bytes_billed", 1_073_741_825, "maximum"),
        ("cache_hit", True, "cache"),
        ("billing_enabled", True, "billing"),
        ("maximum_bytes_billed", 1_073_741_823, "maximum"),
    ],
)
def test_evidence_rejects_invalid_provenance(field: str, value: object, match: str) -> None:
    pair = _pair(evidence=_evidence(**{field: value}))

    with pytest.raises(AccountPairError, match=match):
        AccountPair.from_mapping(pair)


def test_evidence_rejects_missing_and_extra_fields() -> None:
    missing = _evidence()
    missing.pop("job_id")
    extra = _evidence(extra="unexpected")

    with pytest.raises(AccountPairError, match="fields"):
        AccountPairEvidence.from_mapping(missing)
    with pytest.raises(AccountPairError, match="fields"):
        AccountPairEvidence.from_mapping(extra)


def test_pair_rejects_reversed_timestamps() -> None:
    value = _pair(
        evidence=_evidence(
            first_seen_at="2026-06-15T12:00:00+00:00",
            last_seen_at="2026-06-15T11:59:59+00:00",
        )
    )

    with pytest.raises(AccountPairError, match="timestamp order"):
        AccountPair.from_mapping(value)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("duplicate_endpoint", "endpoint"),
        ("duplicate_result_row", "result_row"),
        ("metadata_drift", "metadata"),
    ],
)
def test_loader_rejects_cross_entry_contradictions(mutation: str, match: str) -> None:
    pools = _two_pair_pool()
    entries = pools["account_pair"]
    assert isinstance(entries, list)
    second = entries[1]
    assert isinstance(second, dict)
    if mutation == "duplicate_endpoint":
        second["account"] = _pair()["account"]
    elif mutation == "duplicate_result_row":
        evidence = second["evidence"]
        assert isinstance(evidence, dict)
        evidence["result_row"] = 1
    else:
        evidence = second["evidence"]
        assert isinstance(evidence, dict)
        evidence["total_bytes_processed"] = 190_675_507

    with pytest.raises(AccountPairError, match=match):
        load_account_pairs(pools, expected_count=2)


@pytest.mark.parametrize("expected_count", [0, -1, True])
def test_loader_rejects_invalid_expected_count(expected_count: object) -> None:
    with pytest.raises(AccountPairError, match="expected_count"):
        load_account_pairs(_two_pair_pool(), expected_count=expected_count)  # type: ignore[arg-type]


def test_loader_requires_an_exact_nonempty_pair_array() -> None:
    with pytest.raises(AccountPairError, match="account_pair"):
        load_account_pairs({}, expected_count=2)
    with pytest.raises(AccountPairError, match="exactly 2"):
        load_account_pairs({"account_pair": [_pair()]}, expected_count=2)


def test_canonicalization_sorts_whole_entries_without_mutating_input() -> None:
    pools = json.loads(POOL_PATH.read_text())
    original = copy.deepcopy(pools)
    entries = pools["account_pair"]
    assert isinstance(entries, list)
    entries.reverse()
    reordered = copy.deepcopy(pools)

    canonical = canonical_account_pair_mappings(pools)

    assert pools == reordered
    assert canonical == sorted(
        canonical,
        key=lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ),
    )
    assert {json.dumps(value, sort_keys=True) for value in canonical} == {
        json.dumps(value, sort_keys=True)
        for value in original["account_pair"]  # type: ignore[union-attr]
    }
