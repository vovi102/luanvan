"""Canonical and atomic artifact serialization for GoogleSQL Stage A."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sparql.dataset.generate import (
    DIFFICULTY_ALLOCATION,
    GENERATION_SEED,
    TEMPLATE_ALLOCATION,
    validate_stage_a_records,
)
from nl2sparql.dataset.stage_a.verify import (
    TOTAL_WITNESS_BYTES_CAP,
    StageAVerificationReport,
)
from nl2sparql.dataset.templates import PER_TEMPLATE_BYTES_CAP


class StageAArtifactError(ValueError):
    """Raised when final Stage A artifacts would misrepresent their evidence."""


@dataclass(frozen=True)
class StageAArtifacts:
    output_path: Path
    config_path: Path
    stats_path: Path
    artifact_sha256: str
    config: dict[str, Any]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _jsonl_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(_canonical_json(record) + "\n" for record in records).encode()


def _verification_mode(
    records: Sequence[Mapping[str, Any]], report: StageAVerificationReport | None
) -> str:
    states = {record.get("verification") is None for record in records}
    if len(states) != 1:
        raise StageAArtifactError("Stage A records contain mixed verification states")
    offline = states == {True}
    if offline:
        if report is not None:
            raise StageAArtifactError("Offline candidates cannot include a live report")
        return "offline_candidates"
    if report is None or not report.all_passed:
        raise StageAArtifactError("Live records require a passing witness report")
    if any(record["verification"].get("non_empty") is not True for record in records):
        raise StageAArtifactError("Every live Stage A record requires non-empty evidence")
    if any(record["verification"].get("cache_hit") is not False for record in records):
        raise StageAArtifactError("Every live Stage A record must use cache-free evidence")
    return "live_witness"


def build_generation_config(
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    *,
    report: StageAVerificationReport | None = None,
) -> dict[str, Any]:
    """Build a deterministic manifest for offline or live Stage A records."""
    validate_stage_a_records(records, templates)
    mode = _verification_mode(records, report)
    config: dict[str, Any] = {
        "version": 1,
        "record_count": len(records),
        "generation_seed": GENERATION_SEED,
        "verification_mode": mode,
        "difficulty_allocation": DIFFICULTY_ALLOCATION,
        "template_allocation": TEMPLATE_ALLOCATION,
        "excluded_template_ids": sorted(
            {template["id"] for template in templates} - set(TEMPLATE_ALLOCATION)
        ),
        "template_library_sha256": _sha256_bytes(_canonical_json(list(templates)).encode()),
        "value_pools_sha256": _sha256_bytes(_canonical_json(pools).encode()),
        "artifact_sha256": _sha256_bytes(_jsonl_bytes(records)),
    }
    if report is not None:
        verified_at_values = {record["verification"]["verified_at"] for record in records}
        if len(verified_at_values) != 1:
            raise StageAArtifactError("Live records require one verified_at timestamp")
        config.update(
            {
                "verified_at": next(iter(verified_at_values)),
                "verified_record_count": len(records),
                "witness_count": len(report.witnesses),
                "per_witness_bytes_cap": PER_TEMPLATE_BYTES_CAP,
                "total_witness_bytes_cap": TOTAL_WITNESS_BYTES_CAP,
                "total_estimated_bytes": report.preflight.total_estimated_bytes,
                "total_processed_bytes": sum(
                    witness.processed_bytes for witness in report.witnesses
                ),
                "total_billed_bytes": sum(witness.billed_bytes for witness in report.witnesses),
                "total_wall_latency_ms": sum(
                    witness.wall_latency_ms for witness in report.witnesses
                ),
                "cache_hit_count": sum(witness.cache_hit for witness in report.witnesses),
            }
        )
    return config


def render_stats(
    records: Sequence[Mapping[str, Any]],
    *,
    report: StageAVerificationReport | None = None,
) -> str:
    """Render human-readable distribution and live-evidence statistics."""
    mode = _verification_mode(records, report)
    difficulties = Counter(record["difficulty"] for record in records)
    templates = Counter(record["template_id"] for record in records)
    entities = Counter(entity["value"] for record in records for entity in record["entities_used"])
    proof_modes = Counter(
        record["verification"]["mode"] for record in records if record["verification"] is not None
    )
    lines = [
        "# GoogleSQL Stage A Stats",
        "",
        f"Records: {len(records)}",
        f"Verification mode: {mode}",
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
    if report is not None:
        lines.extend(
            [
                "",
                "## Live witnesses",
                "",
                f"Witnesses: {len(report.witnesses)}",
                f"Estimated bytes: {report.preflight.total_estimated_bytes}",
                f"Processed bytes: {sum(witness.processed_bytes for witness in report.witnesses)}",
                f"Billed bytes: {sum(witness.billed_bytes for witness in report.witnesses)}",
                f"Cache hits: {sum(witness.cache_hit for witness in report.witnesses)}",
            ]
        )
        lines.extend(f"- {key}: {value}" for key, value in sorted(proof_modes.items()))
    return "\n".join(lines) + "\n"


def _write_temp(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    return temp_path


def write_stage_a_artifacts(
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    *,
    output_path: Path,
    config_path: Path,
    stats_path: Path,
    report: StageAVerificationReport | None = None,
) -> StageAArtifacts:
    """Validate and replace all three output files only after content is ready."""
    config = build_generation_config(records, templates, pools, report=report)
    output_content = _jsonl_bytes(records).decode()
    config_content = json.dumps(config, indent=2, sort_keys=True) + "\n"
    stats_content = render_stats(records, report=report)
    paths_and_content = (
        (output_path, output_content),
        (config_path, config_content),
        (stats_path, stats_content),
    )
    temp_paths: list[Path] = []
    try:
        for path, content in paths_and_content:
            temp_paths.append(_write_temp(path, content))
        for temp_path, (path, _) in zip(temp_paths, paths_and_content, strict=True):
            temp_path.replace(path)
    finally:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
    return StageAArtifacts(
        output_path=output_path,
        config_path=config_path,
        stats_path=stats_path,
        artifact_sha256=config["artifact_sha256"],
        config=config,
    )
