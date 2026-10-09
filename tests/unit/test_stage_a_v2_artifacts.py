"""Tests for Stage A v2 candidate artifacts and lifecycle evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a.v2_artifacts import (
    DEFAULT_V2_CANDIDATE_CONFIG_PATH,
    DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
    DEFAULT_V2_CANDIDATE_STATS_PATH,
    StageAV2ArtifactError,
    build_stage_a_v2_candidate_manifest,
    write_stage_a_v2_candidate_artifacts,
)
from nl2sparql.dataset.stage_a_v2 import generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates

V1_ARTIFACT = Path("data/dataset/raw/synthetic-stage-a.jsonl")
V1_CONFIG = Path("data/dataset/raw/generation-config.json")
V1_STATS = Path("data/dataset/raw/stats.md")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
