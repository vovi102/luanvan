"""Candidate-only artifact serialization for Stage A v2."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sparql.dataset.generate import GENERATION_SEED, PROJECT_ROOT
from nl2sparql.dataset.stage_a_v2 import (
    V2_DIFFICULTY_ALLOCATION,
    V2_TEMPLATE_ALLOCATION,
    serialize_stage_a_v2_records,
    validate_stage_a_v2_records,
)

RAW_DATA_DIR = PROJECT_ROOT / "data/dataset/raw"
DEFAULT_V2_CANDIDATE_OUTPUT_PATH = RAW_DATA_DIR / "synthetic-stage-a-v2-candidate.jsonl"
DEFAULT_V2_CANDIDATE_CONFIG_PATH = RAW_DATA_DIR / "generation-config-v2-candidate.json"
DEFAULT_V2_CANDIDATE_STATS_PATH = RAW_DATA_DIR / "stats-v2-candidate.md"
V1_OUTPUT_PATH = RAW_DATA_DIR / "synthetic-stage-a.jsonl"


class StageAV2ArtifactError(ValueError):
    """Raised when a Stage A v2 artifact would misrepresent its evidence."""


@dataclass(frozen=True)
class StageAV2CandidateArtifacts:
    output_path: Path
    config_path: Path
    stats_path: Path
    artifact_sha256: str
    manifest: dict[str, Any]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_stage_a_v2_candidate_manifest(
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a hash-bound manifest that is categorically ineligible for acceptance."""
    if any(record.get("verification") is not None for record in records):
        raise StageAV2ArtifactError("Stage A v2 candidate records must remain unverified")
    validate_stage_a_v2_records(records, templates)
    payload = serialize_stage_a_v2_records(records)
    return {
        "version": 2,
        "lifecycle_state": "candidate",
        "acceptance_eligible": False,
        "verification_mode": "offline_candidates",
        "record_count": len(records),
        "represented_intent_count": len({record["template_id"] for record in records}),
        "generation_seed": GENERATION_SEED,
        "difficulty_allocation": V2_DIFFICULTY_ALLOCATION,
        "template_allocation": V2_TEMPLATE_ALLOCATION,
        "artifact_sha256": _sha256(payload),
        "template_library_sha256": _sha256(_canonical_json(list(templates))),
        "value_pools_sha256": _sha256(_canonical_json(pools)),
        "candidate_value_derivation": {
            "block_number": "deterministic_offset_unverified",
            "transaction_hash": "sha256_syntax_only_unverified",
        },
        "supersedes": {
            "path": str(V1_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
            "artifact_sha256": _sha256(V1_OUTPUT_PATH.read_bytes()),
            "preserved": True,
        },
    }


def render_stage_a_v2_candidate_stats(records: Sequence[Mapping[str, Any]]) -> str:
    """Render deterministic human-readable candidate statistics."""
    difficulties = Counter(str(record["difficulty"]) for record in records)
    templates = Counter(str(record["template_id"]) for record in records)
    entities = Counter(entity["value"] for record in records for entity in record["entities_used"])
    lines = [
        "# GoogleSQL Stage A v2 Candidate Stats",
        "",
        f"Records: {len(records)}",
        "Lifecycle state: candidate",
        "Acceptance eligible: false",
        f"Represented intents: {len(templates)}",
        f"Unique SQL: {len({record['sql'] for record in records})}",
        f"Maximum template frequency: {max(templates.values())}",
        f"Maximum entity frequency: {max(entities.values(), default=0)}",
        "",
        "## Difficulty",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(difficulties.items()))
    lines.extend(["", "## Templates", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(templates.items()))
    return "\n".join(lines) + "\n"


def _write_temp(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    return temporary


def write_stage_a_v2_candidate_artifacts(
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    *,
    output_path: Path = DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
    config_path: Path = DEFAULT_V2_CANDIDATE_CONFIG_PATH,
    stats_path: Path = DEFAULT_V2_CANDIDATE_STATS_PATH,
) -> StageAV2CandidateArtifacts:
    """Atomically replace the three separate Stage A v2 candidate outputs."""
    paths = tuple(path.resolve() for path in (output_path, config_path, stats_path))
    if len(set(paths)) != 3 or V1_OUTPUT_PATH.resolve() in paths:
        raise StageAV2ArtifactError("Stage A v2 candidate output paths must be separate from v1")
    manifest = build_stage_a_v2_candidate_manifest(records, templates, pools)
    contents = (
        serialize_stage_a_v2_records(records),
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        render_stage_a_v2_candidate_stats(records).encode(),
    )
    temporary_paths: list[Path] = []
    try:
        for path, content in zip((output_path, config_path, stats_path), contents, strict=True):
            temporary_paths.append(_write_temp(path, content))
        for temporary, path in zip(
            temporary_paths, (output_path, config_path, stats_path), strict=True
        ):
            temporary.replace(path)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    return StageAV2CandidateArtifacts(
        output_path=output_path,
        config_path=config_path,
        stats_path=stats_path,
        artifact_sha256=str(manifest["artifact_sha256"]),
        manifest=manifest,
    )
