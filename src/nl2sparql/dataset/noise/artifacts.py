"""Manifest evidence and coordinated atomic publication for Stage D."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nl2sparql.dataset.noise.contracts import NoiseConfig, NoiseValidationError
from nl2sparql.dataset.noise.pipeline import NoiseStats
from nl2sparql.dataset.noise.transforms import ABBREVIATIONS_PATH
from nl2sparql.dataset.paraphrase.artifacts import deterministic_audit_ids


def jsonl_bytes(records: Sequence[dict[str, Any]]) -> bytes:
    """Serialize records using the repository's canonical sorted-key JSONL form."""
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in records).encode()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stats_payload(stats: NoiseStats) -> dict[str, Any]:
    return {
        "original_count": stats.original_count,
        "noisy_count": stats.noisy_count,
        "output_count": stats.output_count,
        "type_counts": dict(stats.type_counts),
        "unique_raw_questions": stats.unique_raw_questions,
        "unique_normalized_questions": stats.unique_normalized_questions,
        "mean_nonzero_distance": stats.mean_nonzero_distance,
        "max_distance": stats.max_distance,
    }


def build_noise_manifest(
    *,
    source_path: Path,
    output_bytes: bytes,
    abbreviations_path: Path = ABBREVIATIONS_PATH,
    stage_c: Sequence[dict[str, Any]],
    stage_d: Sequence[dict[str, Any]],
    stats: NoiseStats,
    config: NoiseConfig,
    generated_at: str,
) -> dict[str, Any]:
    """Build complete hash, selection, quality, and audit evidence for Stage D."""
    if source_path.read_bytes() != jsonl_bytes(stage_c):
        raise NoiseValidationError("Stage C records do not match source file bytes")
    if output_bytes != jsonl_bytes(stage_d):
        raise NoiseValidationError("Stage D records do not match output bytes")
    noisy_rows = [record for record in stage_d if "noise_type" in record]
    if len(noisy_rows) != 150:
        raise NoiseValidationError("noise manifest requires exactly 150 noisy rows")
    return {
        "schema_version": 1,
        "status": "generated",
        "generated_at": generated_at,
        "source": {
            "records": len(stage_c),
            "sha256": file_sha256(source_path),
        },
        "output": {
            "records": len(stage_d),
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
        },
        "abbreviation_dictionary": {
            "sha256": file_sha256(abbreviations_path),
        },
        "config": {
            "seed": config.seed,
            "quotas": {noise_type.value: count for noise_type, count in config.quotas.items()},
        },
        "quality": _stats_payload(stats),
        "selection": {"source_ids": [str(record["noise_parent_id"]) for record in noisy_rows]},
        "manual_audit": {
            "seed": 42,
            "record_ids": deterministic_audit_ids(noisy_rows, 30, seed=42),
            "completed": False,
            "decipherable_count": None,
            "decisions": [],
        },
    }


def _validate_manual_audit(audit: object, expected_ids: list[str]) -> None:
    if not isinstance(audit, dict):
        raise NoiseValidationError("manual audit must be an object")
    if audit.get("seed") != 42 or audit.get("record_ids") != expected_ids:
        raise NoiseValidationError("manual audit IDs do not match seed-42 selection")
    if audit.get("completed") is False:
        if audit.get("decipherable_count") is not None or audit.get("decisions") != []:
            raise NoiseValidationError("incomplete manual audit cannot contain decisions")
        return
    if audit.get("completed") is not True:
        raise NoiseValidationError("manual audit completed flag must be boolean")
    decisions = audit.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 30:
        raise NoiseValidationError("completed manual audit requires exactly 30 decisions")
    decision_ids: list[str] = []
    decipherable_count = 0
    for decision in decisions:
        if not isinstance(decision, dict):
            raise NoiseValidationError("manual audit decisions must be objects")
        record_id = decision.get("id")
        decipherable = decision.get("decipherable")
        notes = decision.get("notes")
        if not isinstance(record_id, str) or not isinstance(decipherable, bool):
            raise NoiseValidationError("manual audit decision fields are invalid")
        if not isinstance(notes, str):
            raise NoiseValidationError("manual audit notes must be strings")
        decision_ids.append(record_id)
        decipherable_count += int(decipherable)
    if sorted(decision_ids) != sorted(expected_ids) or len(set(decision_ids)) != 30:
        raise NoiseValidationError("manual audit decisions do not match selected IDs")
    if audit.get("decipherable_count") != decipherable_count:
        raise NoiseValidationError("manual audit decipherable count does not match decisions")
    if decipherable_count < 27:
        raise NoiseValidationError("manual audit requires at least 27 decipherable records")


def validate_noise_manifest(
    manifest: dict[str, Any],
    *,
    source_path: Path,
    output_path: Path,
    abbreviations_path: Path = ABBREVIATIONS_PATH,
    stage_c: Sequence[dict[str, Any]],
    stage_d: Sequence[dict[str, Any]],
    stats: NoiseStats,
    config: NoiseConfig,
) -> None:
    """Recompute and validate every machine-verifiable manifest field."""
    generated_at = manifest.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        raise NoiseValidationError("noise manifest requires generated_at")
    output_bytes = output_path.read_bytes()
    expected = build_noise_manifest(
        source_path=source_path,
        output_bytes=output_bytes,
        abbreviations_path=abbreviations_path,
        stage_c=stage_c,
        stage_d=stage_d,
        stats=stats,
        config=config,
        generated_at=generated_at,
    )
    for key in (
        "schema_version",
        "status",
        "generated_at",
        "source",
        "output",
        "abbreviation_dictionary",
        "config",
        "quality",
        "selection",
    ):
        if manifest.get(key) != expected[key]:
            raise NoiseValidationError(f"noise manifest {key} evidence does not match")
    _validate_manual_audit(manifest.get("manual_audit"), expected["manual_audit"]["record_ids"])


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    restore_path = path.with_name(f".{path.name}.restore.tmp")
    restore_path.write_bytes(previous)
    restore_path.replace(path)


def publish_noise_artifacts(
    output_bytes: bytes,
    manifest: dict[str, Any],
    *,
    output_path: Path,
    manifest_path: Path,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    """Publish output and manifest together, rolling both back on replace failure."""
    if output_path == manifest_path:
        raise NoiseValidationError("output and manifest paths must differ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_temp = output_path.with_name(f".{output_path.name}.tmp")
    manifest_temp = manifest_path.with_name(f".{manifest_path.name}.tmp")
    output_restore = output_path.with_name(f".{output_path.name}.restore.tmp")
    manifest_restore = manifest_path.with_name(f".{manifest_path.name}.restore.tmp")
    previous_output = output_path.read_bytes() if output_path.exists() else None
    previous_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    output_replaced = False
    manifest_replaced = False
    try:
        output_temp.write_bytes(output_bytes)
        manifest_temp.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        replace(output_temp, output_path)
        output_replaced = True
        replace(manifest_temp, manifest_path)
        manifest_replaced = True
    except Exception:
        if output_replaced:
            _restore(output_path, previous_output)
        if manifest_replaced:
            _restore(manifest_path, previous_manifest)
        raise
    finally:
        for path in (output_temp, manifest_temp, output_restore, manifest_restore):
            path.unlink(missing_ok=True)
