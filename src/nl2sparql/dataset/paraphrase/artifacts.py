"""Final artifact validation and serialization for T3.3."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from random import Random
from typing import Any

from nl2sparql.dataset.paraphrase.contracts import STAGE_B_MODEL, STAGE_C_MODEL
from nl2sparql.dataset.paraphrase.quality import normalize_question


class ParaphraseArtifactError(ValueError):
    """Raised when paraphrase outputs do not satisfy publication gates."""


def deterministic_audit_ids(
    records: Sequence[dict[str, Any]], sample_size: int, *, seed: int = 42
) -> list[str]:
    ids = sorted({str(record["id"]) for record in records})
    if sample_size < 0 or sample_size > len(ids):
        raise ParaphraseArtifactError(
            f"Cannot sample {sample_size} audit IDs from {len(ids)} records"
        )
    return sorted(Random(seed).sample(ids, sample_size))


def total_generation_cost(
    records_by_stage: dict[str, Sequence[dict[str, Any]]],
) -> float:
    total = 0.0
    seen: set[str] = set()
    for stage, records in records_by_stage.items():
        for record in records:
            metadata = record.get(stage)
            if not metadata:
                continue
            generation_id = metadata.get("generation_id")
            if not generation_id or generation_id in seen:
                continue
            seen.add(generation_id)
            try:
                cost = float(metadata["cost_usd"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ParaphraseArtifactError(
                    f"Generation {generation_id} is missing valid cost metadata"
                ) from exc
            if cost < 0:
                raise ParaphraseArtifactError(
                    f"Generation {generation_id} has negative cost metadata"
                )
            total += cost
    return total


def build_run_manifest(
    *,
    source_sha256: str,
    stage_b_sha256: str,
    stage_c_sha256: str,
    stage_b_records: Sequence[dict[str, Any]],
    stage_c_records: Sequence[dict[str, Any]],
    actual_cost_usd: float,
    cost_cap_usd: float,
    generated_at: str,
) -> dict[str, Any]:
    parents: dict[str, dict[str, Any]] = {}
    for record in stage_c_records:
        parents.setdefault(str(record["parent_id"]), record)
    distances = [
        float(distance)
        for record in parents.values()
        for distance in record["stage_c"]["pairwise_distances"]
    ]
    if not distances:
        raise ParaphraseArtifactError("Stage C manifest requires distance evidence")
    parent_rows = [{"id": parent_id} for parent_id in parents]
    return {
        "schema_version": 1,
        "status": "completed",
        "generated_at": generated_at,
        "source": {
            "stage_a_sha256": source_sha256,
            "stage_a_records": 1000,
        },
        "models": {
            "stage_b": {"id": STAGE_B_MODEL, "temperature": 0.0},
            "stage_c": {"id": STAGE_C_MODEL, "temperature": 0.7},
        },
        "outputs": {
            "stage_b_records": len(stage_b_records),
            "stage_b_sha256": stage_b_sha256,
            "stage_c_records": len(stage_c_records),
            "stage_c_sha256": stage_c_sha256,
        },
        "quality": {
            "unique_stage_c_questions": len(
                {record["nl_normalized"] for record in stage_c_records}
            ),
            "mean_stage_c_distance": sum(distances) / len(distances),
        },
        "cost": {
            "actual_usd": actual_cost_usd,
            "cap_usd": cost_cap_usd,
        },
        "audits": {
            "seed": 42,
            "stage_b_record_ids": deterministic_audit_ids(stage_b_records, 50),
            "stage_c_parent_ids": deterministic_audit_ids(parent_rows, 100),
            "stage_b_completed": False,
            "stage_c_completed": False,
        },
    }


def validate_stage_b_records(records: Sequence[dict[str, Any]]) -> None:
    if len(records) != 1000:
        raise ParaphraseArtifactError(f"Stage B requires 1000 records, received {len(records)}")
    if any(not record.get("nl_formal") or not record.get("stage_b") for record in records):
        raise ParaphraseArtifactError("Every Stage B record requires formal text and metadata")


def expand_stage_c_records(parents: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for parent in parents:
        responses = parent["stage_c"]["responses"]
        for version in ("casual", "abbreviated", "alternative"):
            question = responses[version]
            children.append(
                {
                    **parent,
                    "id": f"{parent['id']}-{version}",
                    "parent_id": parent["id"],
                    "version": version,
                    "nl": question,
                    "nl_normalized": normalize_question(question),
                }
            )
    return children


def validate_stage_c_records(records: Sequence[dict[str, Any]]) -> None:
    if len(records) != 3000:
        raise ParaphraseArtifactError(f"Stage C requires 3000 records, received {len(records)}")
    normalized = [record.get("nl_normalized") for record in records]
    if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
        raise ParaphraseArtifactError("Stage C requires 3000 unique normalized questions")
    parents: dict[str, dict[str, Any]] = {}
    for record in records:
        parents[record["parent_id"]] = record
    distances = [
        distance
        for record in parents.values()
        for distance in record["stage_c"]["pairwise_distances"]
    ]
    mean_distance = sum(distances) / len(distances)
    if mean_distance <= 0.30:
        raise ParaphraseArtifactError(
            f"Stage C mean normalized edit distance must exceed 0.30: {mean_distance:.4f}"
        )


def write_jsonl_atomic(records: Sequence[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in records),
            encoding="utf-8",
        )
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def write_json_atomic(value: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def write_cost_log(records_by_stage: dict[str, Sequence[dict[str, Any]]], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for stage, records in records_by_stage.items():
        for record in records:
            metadata = record.get(stage)
            if not metadata or metadata["generation_id"] in seen:
                continue
            seen.add(metadata["generation_id"])
            rows.append(
                {
                    "stage": stage,
                    "record_id": record["id"],
                    "generation_id": metadata["generation_id"],
                    "model": metadata["model"],
                    "prompt_tokens": metadata["prompt_tokens"],
                    "completion_tokens": metadata["completion_tokens"],
                    "total_tokens": metadata["total_tokens"],
                    "cost_usd": metadata["cost_usd"],
                    "latency_ms": metadata["latency_ms"],
                    "attempts": metadata["attempts"],
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["stage"])
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
