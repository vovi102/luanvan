"""Tests for Stage A v2 candidate artifacts and lifecycle evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a.evidence import (
    StageAVerificationReport,
    WitnessDryRun,
    WitnessExecution,
    WitnessPreflight,
    build_witness_groups,
)
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
    executions = tuple(
        WitnessExecution(
            group_id=group.group_id,
            template_id=group.template_id,
            witness_record_id=group.witness_record_id,
            row_count=1,
            columns=tuple(templates_by_id[group.template_id]["expected_columns"]),
            estimated_bytes=10,
            processed_bytes=10,
            billed_bytes=10,
            wall_latency_ms=1.0,
            server_latency_ms=0.5,
            slot_millis=1,
            cache_hit=False,
        )
        for group in groups
    )
    groups_by_id = {group.group_id: group for group in groups}
    for record in records:
        group = groups_by_id[record["witness_group_id"]]
        record["verification"] = {
            "mode": (
                "live_exact" if record["id"] == group.witness_record_id else "live_limit_monotonic"
            ),
            "non_empty": True,
            "witness_group_id": record["witness_group_id"],
            "witness_record_id": group.witness_record_id,
            "witness_row_count": 1,
            "estimated_bytes": 10,
            "processed_bytes": 10,
            "billed_bytes": 10,
            "wall_latency_ms": 1.0,
            "server_latency_ms": 0.5,
            "slot_millis": 1,
            "cache_hit": False,
            "verified_at": "2026-10-09T12:00:00+00:00",
        }
    preflight_witnesses = tuple(
        WitnessDryRun(
            group_id=group.group_id,
            template_id=group.template_id,
            witness_record_id=group.witness_record_id,
            estimated_bytes=10,
        )
        for group in groups
    )
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
