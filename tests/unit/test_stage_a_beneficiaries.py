"""Regression tests for beneficiary-specific generation evidence."""

import copy
from pathlib import Path

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a_v2 import StageAV2GenerationError, generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates


def _pools():
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    pools["block_beneficiary"] = [
        {
            "value": "0x" + f"{index + 1:040x}",
            "source": "BigQuery nl2sparql_analytics.block_facts",
            "start_date": "2026-06-15",
            "end_date": "2026-06-16",
            "evidence": {
                "project": "nl2sparql-thesis",
                "location": "US",
                "job_id": "test-beneficiary-job",
                "query_sha256": "a" * 64,
                "block_count": index + 1,
                "first_seen_at": "2026-06-15T00:00:00+00:00",
                "last_seen_at": "2026-06-15T23:59:00+00:00",
                "total_bytes_processed": 100,
                "total_bytes_billed": 200,
                "cache_hit": False,
                "billing_enabled": False,
                "maximum_bytes_billed": 4 * 2**30,
            },
        }
        for index in range(4)
    ]
    return pools


def test_block_validator_records_consume_only_beneficiary_evidence():
    pools = _pools()
    records = generate_stage_a_v2_records(load_templates(), pools)
    beneficiaries = {entry["value"] for entry in pools["block_beneficiary"]}
    validators = [r for r in records if r["template_id"] == "T_BLOCKS_BY_VALIDATOR"]
    assert len(validators) == 40
    assert {r["slot_values"]["account"] for r in validators} == beneficiaries
    for account in beneficiaries:
        assert sorted(
            r["slot_values"]["n"] for r in validators if r["slot_values"]["account"] == account
        ) == list(range(1, 11))
    assert {
        r["slot_values"]["account"] for r in records if r["template_id"] == "T_LIST_TX_FROM_ACCOUNT"
    } == {entry["value"] for entry in pools["ethereum_address"]}


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "short",
        "duplicate",
        "role",
        "window",
        "count",
        "billing",
        "cache",
        "bytes",
        "job",
        "timestamp",
        "metadata",
    ],
)
def test_generation_rejects_invalid_beneficiary_evidence(mutation):
    pools = copy.deepcopy(_pools())
    entries = pools["block_beneficiary"]
    if mutation == "missing":
        pools.pop("block_beneficiary")
    elif mutation == "short":
        entries.pop()
    elif mutation == "duplicate":
        entries[1]["value"] = entries[0]["value"]
    elif mutation == "role":
        entries[0]["source"] = "transaction sender"
    elif mutation == "window":
        entries[0]["start_date"] = "2026-06-14"
    elif mutation == "count":
        entries[0]["evidence"]["block_count"] = 0
    elif mutation == "billing":
        entries[0]["evidence"]["billing_enabled"] = True
    elif mutation == "cache":
        entries[0]["evidence"]["cache_hit"] = True
    elif mutation == "bytes":
        entries[0]["evidence"]["total_bytes_billed"] = -1
    elif mutation == "job":
        entries[0]["evidence"]["job_id"] = ""
    elif mutation == "timestamp":
        entries[0]["evidence"]["first_seen_at"] = "2026-06-14T00:00:00+00:00"
    else:
        entries[0]["evidence"]["query_sha256"] = "b" * 64
    with pytest.raises(StageAV2GenerationError, match="beneficiary"):
        generate_stage_a_v2_records(load_templates(), pools)
