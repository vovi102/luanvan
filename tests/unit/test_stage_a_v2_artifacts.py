"""Tests for Stage A v2 candidate artifacts and lifecycle evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a.evidence import (
    LogicalWitnessResult,
    StageAVerificationReport,
    WitnessDryRun,
    WitnessExecution,
    WitnessPreflight,
    build_witness_groups,
)
from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries
from nl2sparql.dataset.stage_a.v2_artifacts import (
    DEFAULT_V2_ACCEPTED_CONFIG_PATH,
    DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
    DEFAULT_V2_ACCEPTED_STATS_PATH,
    DEFAULT_V2_CANDIDATE_CONFIG_PATH,
    DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
    DEFAULT_V2_CANDIDATE_STATS_PATH,
    StageAV2ArtifactError,
    build_stage_a_v2_accepted_manifest,
    build_stage_a_v2_candidate_manifest,
    has_evidence_backed_live_values,
    write_stage_a_v2_accepted_artifacts,
    write_stage_a_v2_candidate_artifacts,
)
from nl2sparql.dataset.stage_a_v2 import generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates

V1_ARTIFACT = Path("data/dataset/raw/synthetic-stage-a.jsonl")
V1_CONFIG = Path("data/dataset/raw/generation-config.json")
V1_STATS = Path("data/dataset/raw/stats.md")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_live_report(candidates: list[dict[str, object]]):
    records = copy.deepcopy(candidates)
    groups = build_witness_groups(records)
    templates_by_id = {template["id"]: template for template in load_templates()}
    groups_by_id = {group.group_id: group for group in groups}
    queries = build_stage_a_v2_witness_queries(records)
    preflight_witnesses = tuple(
        WitnessDryRun(
            group_id=query.group_ids[0],
            template_id=query.template_id,
            witness_record_id=groups_by_id[query.group_ids[0]].witness_record_id,
            estimated_bytes=10,
            query_id=query.query_id,
            query_sha256=query.query_sha256,
            proof_kind=query.proof_kind,
            group_ids=query.group_ids,
            job_id=f"dry-{index}",
            location="US",
        )
        for index, query in enumerate(queries)
    )
    executions = tuple(
        WitnessExecution(
            group_id=query.group_ids[0],
            template_id=query.template_id,
            witness_record_id=groups_by_id[query.group_ids[0]].witness_record_id,
            row_count=len(query.group_ids),
            columns=(
                ("witness_group_id", *templates_by_id[query.template_id]["expected_columns"])
                if query.proof_kind == "tx_hash_batch"
                else tuple(templates_by_id[query.template_id]["expected_columns"])
            ),
            estimated_bytes=11,
            processed_bytes=12,
            billed_bytes=13,
            wall_latency_ms=1.0,
            server_latency_ms=0.5,
            slot_millis=1,
            cache_hit=False,
            query_id=query.query_id,
            query_sha256=query.query_sha256,
            proof_kind=query.proof_kind,
            group_ids=query.group_ids,
            job_id=f"exec-{index}",
            location="US",
            immediate_dry_run=replace(
                preflight_witnesses[index], estimated_bytes=11, job_id=f"redry-{index}"
            ),
            logical_results=tuple(
                LogicalWitnessResult(
                    group_id=group_id,
                    witness_record_id=groups_by_id[group_id].witness_record_id,
                    row_count=1,
                    columns=tuple(templates_by_id[query.template_id]["expected_columns"]),
                )
                for group_id in query.group_ids
            ),
        )
        for index, query in enumerate(queries)
    )
    executions_by_group = {
        group_id: execution for execution in executions for group_id in execution.group_ids
    }
    for record in records:
        group = groups_by_id[record["witness_group_id"]]
        execution = executions_by_group[group.group_id]
        record["verification"] = {
            "mode": (
                "live_exact" if record["id"] == group.witness_record_id else "live_limit_monotonic"
            ),
            "non_empty": True,
            "witness_group_id": record["witness_group_id"],
            "witness_record_id": group.witness_record_id,
            "witness_row_count": 1,
            "estimated_bytes": 11,
            "processed_bytes": 12,
            "billed_bytes": 13,
            "wall_latency_ms": 1.0,
            "server_latency_ms": 0.5,
            "slot_millis": 1,
            "cache_hit": False,
            "physical_query_id": execution.query_id,
            "query_sha256": execution.query_sha256,
            "job_id": execution.job_id,
            "location": execution.location,
            "verified_at": "2026-10-09T12:00:00+00:00",
        }
    return StageAVerificationReport(
        preflight=WitnessPreflight(
            witnesses=preflight_witnesses,
            total_estimated_bytes=10 * len(preflight_witnesses),
        ),
        witnesses=executions,
        records=tuple(records),
    )


@pytest.fixture(scope="module")
def inputs():
    templates = load_templates()
    pools = load_value_pools()
    return templates, pools, generate_stage_a_v2_records(templates, pools)


def test_v2_candidate_defaults_are_separate_from_v1() -> None:
    assert DEFAULT_V2_CANDIDATE_OUTPUT_PATH.name == "synthetic-stage-a-v2-candidate.jsonl"
    assert DEFAULT_V2_CANDIDATE_CONFIG_PATH.name == "generation-config-v2-candidate.json"
    assert DEFAULT_V2_CANDIDATE_STATS_PATH.name == "stats-v2-candidate.md"
    assert {
        DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
        DEFAULT_V2_CANDIDATE_CONFIG_PATH,
        DEFAULT_V2_CANDIDATE_STATS_PATH,
    }.isdisjoint({V1_ARTIFACT, V1_CONFIG, V1_STATS})


def test_candidate_manifest_is_hash_bound_and_ineligible_for_acceptance(inputs) -> None:
    templates, pools, records = inputs

    manifest = build_stage_a_v2_candidate_manifest(records, templates, pools)

    assert manifest["version"] == 2
    assert manifest["lifecycle_state"] == "candidate"
    assert manifest["acceptance_eligible"] is False
    assert manifest["verification_mode"] == "offline_candidates"
    assert manifest["record_count"] == 1000
    assert manifest["represented_intent_count"] == 25
    assert manifest["generation_seed"] == 42
    assert manifest["supersedes"]["artifact_sha256"] == _sha256(V1_ARTIFACT)
    assert manifest["candidate_value_derivation"] == {
        "block_number": "deterministic_offset_unverified",
        "transaction_hash": "sha256_syntax_only_unverified",
    }
    assert len(manifest["artifact_sha256"]) == 64


def test_replacement_uses_34_monotonic_limits_without_changing_population(inputs) -> None:
    _, _, records = inputs
    replacement = [
        record for record in records if record["template_id"] == "T_CATEGORY_OWNER_DISTRIBUTION"
    ]

    assert len(replacement) == 34
    assert [record["slot_values"] for record in replacement] == [{"n": n} for n in range(1, 35)]
    assert len({record["witness_group_id"] for record in replacement}) == 1
    assert Counter(record["difficulty"] for record in records) == {
        "easy": 350,
        "medium": 450,
        "hard": 200,
    }
    assert len(records) == 1000
    assert len({record["template_id"] for record in records}) == 25


def test_candidate_writer_is_deterministic_and_preserves_v1_bytes(tmp_path: Path, inputs) -> None:
    templates, pools, records = inputs
    v1_before = {path: path.read_bytes() for path in (V1_ARTIFACT, V1_CONFIG, V1_STATS)}
    first = tuple(tmp_path / "first" / name for name in ("data.jsonl", "config.json", "stats.md"))
    second = tuple(tmp_path / "second" / name for name in ("data.jsonl", "config.json", "stats.md"))

    first_result = write_stage_a_v2_candidate_artifacts(
        records,
        templates,
        pools,
        output_path=first[0],
        config_path=first[1],
        stats_path=first[2],
    )
    second_result = write_stage_a_v2_candidate_artifacts(
        records,
        templates,
        pools,
        output_path=second[0],
        config_path=second[1],
        stats_path=second[2],
    )

    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
    assert first_result.artifact_sha256 == second_result.artifact_sha256
    assert json.loads(first[1].read_text())["lifecycle_state"] == "candidate"
    assert first[2].read_text().startswith("# GoogleSQL Stage A v2 Candidate Stats\n")
    assert {path: path.read_bytes() for path in v1_before} == v1_before


def test_candidate_manifest_rejects_any_live_verification_claim(inputs) -> None:
    templates, pools, records = inputs
    tampered = [dict(record) for record in records]
    tampered[0]["verification"] = {"non_empty": True}

    with pytest.raises(StageAV2ArtifactError, match="unverified"):
        build_stage_a_v2_candidate_manifest(tampered, templates, pools)


def _live_pools(pools: dict[str, object]) -> dict[str, object]:
    enriched = dict(pools)
    enriched["block_number"] = [
        {"value": 10_000_000 + index, "source": "BigQuery", "evidence": f"block-{index}"}
        for index in range(45)
    ]
    enriched["transaction_hash"] = [
        {
            "value": "0x" + f"{index:064x}",
            "source": "BigQuery",
            "evidence": f"transaction-{index}",
        }
        for index in range(45)
    ]
    return enriched


def test_live_values_require_45_unique_provenance_bearing_entries(inputs) -> None:
    _, pools, _ = inputs

    assert has_evidence_backed_live_values(pools) is False
    assert has_evidence_backed_live_values(_live_pools(pools)) is True

    incomplete = _live_pools(pools)
    incomplete["transaction_hash"] = incomplete["transaction_hash"][:-1]
    assert has_evidence_backed_live_values(incomplete) is False


def test_genuine_evidence_pool_is_hash_bound_and_well_formed() -> None:
    path = Path("data/dataset/raw/stage-a-v2-evidence-pools.json")
    pools = load_value_pools(path)

    assert _sha256(path) == "1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8"
    assert has_evidence_backed_live_values(pools) is True
    entries = [*pools["block_number"], *pools["transaction_hash"]]
    assert all(set(entry) == {"value", "source", "evidence"} for entry in entries)


def test_accepted_artifacts_require_live_report_and_evidence_backed_values(
    tmp_path: Path, inputs
) -> None:
    templates, pools, _ = inputs
    live_pools = _live_pools(pools)
    records = generate_stage_a_v2_records(templates, live_pools)
    report = _fake_live_report(records)

    manifest = build_stage_a_v2_accepted_manifest(report, templates, live_pools)

    assert manifest["lifecycle_state"] == "accepted"
    assert manifest["acceptance_eligible"] is True
    assert manifest["verification_mode"] == "live_witness"
    assert manifest["represented_intent_count"] == 25
    assert manifest["verified_record_count"] == 1000
    assert manifest["witness_count"] == 170
    assert manifest["physical_query_count"] == 126
    assert len(manifest["preflight_evidence"]) == 126
    assert len(manifest["execution_evidence"]) == 126
    batch = next(
        item for item in manifest["execution_evidence"] if item["proof_kind"] == "tx_hash_batch"
    )
    assert len(batch["group_ids"]) == 45
    assert manifest["total_processed_bytes"] == 12 * 126
    assert manifest["cache_hit_count"] == 0

    targets = tuple(tmp_path / name for name in ("accepted.jsonl", "accepted.json", "stats.md"))
    result = write_stage_a_v2_accepted_artifacts(
        report,
        templates,
        live_pools,
        output_path=targets[0],
        config_path=targets[1],
        stats_path=targets[2],
    )
    assert result.artifact_sha256 == manifest["artifact_sha256"]
    assert json.loads(targets[1].read_text())["lifecycle_state"] == "accepted"

    with pytest.raises(StageAV2ArtifactError, match="evidence-backed"):
        build_stage_a_v2_accepted_manifest(report, templates, pools)


def test_accepted_manifest_rejects_fabricated_or_incomplete_reports(inputs) -> None:
    templates, pools, _ = inputs
    live_pools = _live_pools(pools)
    records = generate_stage_a_v2_records(templates, live_pools)
    complete = _fake_live_report(records)

    forged = SimpleNamespace(
        all_passed=True,
        records=complete.records,
        witnesses=complete.witnesses,
        preflight=complete.preflight,
    )
    with pytest.raises(StageAV2ArtifactError, match="StageAVerificationReport"):
        build_stage_a_v2_accepted_manifest(forged, templates, live_pools)

    incomplete = replace(complete, witnesses=complete.witnesses[:-1])
    with pytest.raises(StageAV2ArtifactError, match="complete witness evidence"):
        build_stage_a_v2_accepted_manifest(incomplete, templates, live_pools)


@pytest.mark.parametrize(
    "tampering",
    ["duplicate_query", "missing_edge", "digest", "job", "cache", "immediate"],
)
def test_accepted_manifest_rejects_tampered_physical_evidence(inputs, tampering: str) -> None:
    templates, pools, _ = inputs
    live_pools = _live_pools(pools)
    records = generate_stage_a_v2_records(templates, live_pools)
    complete = _fake_live_report(records)
    executions = list(complete.witnesses)
    if tampering == "duplicate_query":
        executions[1] = replace(executions[1], query_id=executions[0].query_id)
    elif tampering == "missing_edge":
        executions[0] = replace(executions[0], logical_results=executions[0].logical_results[:-1])
    elif tampering == "digest":
        executions[0] = replace(executions[0], query_sha256="0" * 64)
    elif tampering == "job":
        executions[0] = replace(executions[0], job_id="different-job")
    elif tampering == "cache":
        executions[0] = replace(executions[0], cache_hit=True)
    else:
        executions[0] = replace(executions[0], immediate_dry_run=None)

    with pytest.raises(StageAV2ArtifactError):
        build_stage_a_v2_accepted_manifest(
            replace(complete, witnesses=tuple(executions)), templates, live_pools
        )


@pytest.mark.parametrize(
    "protected_path",
    [
        V1_ARTIFACT,
        V1_CONFIG,
        V1_STATS,
        DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
        DEFAULT_V2_ACCEPTED_CONFIG_PATH,
        DEFAULT_V2_ACCEPTED_STATS_PATH,
    ],
)
def test_candidate_writer_rejects_every_cross_lifecycle_path(
    protected_path: Path, tmp_path: Path, inputs
) -> None:
    templates, pools, records = inputs
    alias = tmp_path / "protected-alias"
    alias.symlink_to(protected_path.resolve())
    with pytest.raises(StageAV2ArtifactError, match="lifecycle"):
        write_stage_a_v2_candidate_artifacts(
            records,
            templates,
            pools,
            output_path=alias,
            config_path=tmp_path / "config.json",
            stats_path=tmp_path / "stats.md",
        )


@pytest.mark.parametrize("protected_path", [V1_ARTIFACT, V1_CONFIG, V1_STATS])
def test_accepted_writer_rejects_every_v1_path(
    protected_path: Path, tmp_path: Path, inputs
) -> None:
    templates, pools, records = inputs
    alias = tmp_path / "protected-alias"
    alias.symlink_to(protected_path.resolve())
    with pytest.raises(StageAV2ArtifactError, match="lifecycle"):
        write_stage_a_v2_accepted_artifacts(
            _fake_live_report(records),
            templates,
            _live_pools(pools),
            output_path=alias,
            config_path=tmp_path / "config.json",
            stats_path=tmp_path / "stats.md",
        )


def test_accepted_defaults_are_separate_from_candidate_and_v1() -> None:
    assert DEFAULT_V2_ACCEPTED_OUTPUT_PATH.name == "synthetic-stage-a-v2.jsonl"
    assert DEFAULT_V2_ACCEPTED_CONFIG_PATH.name == "generation-config-v2.json"
    assert DEFAULT_V2_ACCEPTED_STATS_PATH.name == "stats-v2.md"
    assert {
        DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
        DEFAULT_V2_ACCEPTED_CONFIG_PATH,
        DEFAULT_V2_ACCEPTED_STATS_PATH,
    }.isdisjoint(
        {
            DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
            DEFAULT_V2_CANDIDATE_CONFIG_PATH,
            DEFAULT_V2_CANDIDATE_STATS_PATH,
            V1_ARTIFACT,
            V1_CONFIG,
            V1_STATS,
        }
    )
