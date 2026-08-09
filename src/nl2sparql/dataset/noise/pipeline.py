"""Exact-quota allocation and validation for the Stage D noise dataset."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random
from types import MappingProxyType
from typing import Any

from nl2sparql.dataset.noise.contracts import (
    NoiseConfig,
    NoiseType,
    NoiseValidationError,
)
from nl2sparql.dataset.noise.transforms import protected_terms, transform_question
from nl2sparql.dataset.paraphrase.artifacts import (
    ParaphraseArtifactError,
    validate_stage_c_records,
)
from nl2sparql.dataset.paraphrase.contracts import ParaphraseValidationError
from nl2sparql.dataset.paraphrase.quality import (
    normalize_question,
    normalized_levenshtein,
    validate_question_anchors,
)

MAX_NORMALIZED_DISTANCE = {
    NoiseType.TYPO: 0.10,
    NoiseType.ABBREV: 0.35,
    NoiseType.FRAGMENT: 0.45,
}
NOISE_FIELDS = {
    "id",
    "nl",
    "nl_normalized",
    "noise_parent_id",
    "nl_original",
    "noise_type",
    "noise_seed",
    "noise_distance",
}


@dataclass(frozen=True)
class NoiseStats:
    """Verified aggregate statistics for a complete Stage D artifact."""

    original_count: int
    noisy_count: int
    output_count: int
    type_counts: Mapping[str, int]
    unique_raw_questions: int
    unique_normalized_questions: int
    mean_nonzero_distance: float
    max_distance: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "type_counts", MappingProxyType(dict(self.type_counts)))


def _validate_source(records: Sequence[dict[str, Any]]) -> None:
    try:
        validate_stage_c_records(records)
    except ParaphraseArtifactError as exc:
        raise NoiseValidationError(f"invalid Stage C source: {exc}") from exc
    ids = [record.get("id") for record in records]
    if any(not isinstance(value, str) or not value for value in ids):
        raise NoiseValidationError("every Stage C source requires a non-empty string ID")
    if len(set(ids)) != len(ids):
        raise NoiseValidationError("Stage C source IDs must be unique")


def _candidate_seed(seed: int, noise_type: NoiseType) -> int:
    digest = hashlib.sha256(f"{seed}:{noise_type.value}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _distance_is_valid(noise_type: NoiseType, distance: float) -> bool:
    if noise_type is NoiseType.MIXED_CASE:
        return distance == 0.0
    return 0.0 < distance <= MAX_NORMALIZED_DISTANCE[noise_type]


def _make_candidate(
    record: dict[str, Any],
    noise_type: NoiseType,
    abbreviations: dict[str, tuple[str, ...]],
    entity_index: dict[str, dict[str, str]],
    config: NoiseConfig,
    rng: Random,
) -> dict[str, Any] | None:
    original = str(record["nl"])
    transformed = transform_question(
        original,
        noise_type,
        abbreviations,
        protected_terms(record, entity_index),
        rng,
    )
    if transformed is None or transformed == original:
        return None
    try:
        validate_question_anchors(transformed, record, entity_index)
    except ParaphraseValidationError:
        return None
    original_normalized = normalize_question(original)
    transformed_normalized = normalize_question(transformed)
    distance = normalized_levenshtein(original_normalized, transformed_normalized)
    if not _distance_is_valid(noise_type, distance):
        return None
    return {
        **record,
        "id": f"{record['id']}-noise-{noise_type.value}",
        "noise_parent_id": record["id"],
        "nl_original": original,
        "nl": transformed,
        "nl_normalized": transformed_normalized,
        "noise_type": noise_type.value,
        "noise_seed": config.seed,
        "noise_distance": distance,
    }


def inject_noise(
    records: Sequence[dict[str, Any]],
    abbreviations: dict[str, tuple[str, ...]],
    entity_index: dict[str, dict[str, str]],
    config: NoiseConfig | None = None,
) -> list[dict[str, Any]]:
    """Append exact deterministic noise quotas to a valid Stage C corpus."""
    config = config or NoiseConfig()
    _validate_source(records)
    records_by_id = {str(record["id"]): record for record in records}
    sorted_ids = sorted(records_by_id)
    selected_sources: set[str] = set()
    raw_questions = {str(record["nl"]) for record in records}
    normalized_questions = {normalize_question(str(record["nl"])) for record in records}
    noisy_rows: list[dict[str, Any]] = []

    for noise_type in NoiseType:
        rng = Random(_candidate_seed(config.seed, noise_type))
        candidate_ids = list(sorted_ids)
        rng.shuffle(candidate_ids)
        accepted: list[dict[str, Any]] = []
        for source_id in candidate_ids:
            if source_id in selected_sources:
                continue
            candidate = _make_candidate(
                records_by_id[source_id],
                noise_type,
                abbreviations,
                entity_index,
                config,
                rng,
            )
            if candidate is None:
                continue
            raw = str(candidate["nl"])
            normalized = str(candidate["nl_normalized"])
            if raw in raw_questions:
                continue
            if noise_type is not NoiseType.MIXED_CASE and normalized in normalized_questions:
                continue
            raw_questions.add(raw)
            if noise_type is not NoiseType.MIXED_CASE:
                normalized_questions.add(normalized)
            selected_sources.add(source_id)
            accepted.append(candidate)
            if len(accepted) == config.quotas[noise_type]:
                break
        if len(accepted) != config.quotas[noise_type]:
            raise NoiseValidationError(
                f"insufficient valid {noise_type.value} candidates: "
                f"required {config.quotas[noise_type]}, received {len(accepted)}"
            )
        noisy_rows.extend(sorted(accepted, key=lambda row: str(row["noise_parent_id"])))

    output = [*records, *noisy_rows]
    validate_stage_d_records(records, output, entity_index, config)
    return output


def _assert_immutable(parent: dict[str, Any], noisy: dict[str, Any]) -> None:
    parent_fields = {key: value for key, value in parent.items() if key not in NOISE_FIELDS}
    noisy_fields = {key: value for key, value in noisy.items() if key not in NOISE_FIELDS}
    if noisy_fields != parent_fields:
        raise NoiseValidationError(
            f"noisy record {noisy.get('id')} changed immutable source fields"
        )


def validate_stage_d_records(
    stage_c: Sequence[dict[str, Any]],
    stage_d: Sequence[dict[str, Any]],
    entity_index: dict[str, dict[str, str]],
    config: NoiseConfig | None = None,
) -> NoiseStats:
    """Validate the complete Stage D corpus and recompute all quality statistics."""
    config = config or NoiseConfig()
    _validate_source(stage_c)
    if len(stage_d) != 3150:
        raise NoiseValidationError(f"Stage D requires 3150 records, received {len(stage_d)}")
    originals = list(stage_d[:3000])
    if originals != list(stage_c):
        raise NoiseValidationError("Stage D originals must equal Stage C in source order")
    noisy_rows = list(stage_d[3000:])
    ids = [record.get("id") for record in stage_d]
    if len(set(ids)) != len(ids):
        raise NoiseValidationError("Stage D IDs must be unique")
    raw_questions = [str(record.get("nl", "")) for record in stage_d]
    if any(not value for value in raw_questions) or len(set(raw_questions)) != len(raw_questions):
        raise NoiseValidationError("Stage D raw questions must be non-empty and unique")

    source_by_id = {str(record["id"]): record for record in stage_c}
    selected_sources: set[str] = set()
    normalized_seen = {normalize_question(str(record["nl"])) for record in stage_c}
    type_counts: Counter[str] = Counter()
    distances: list[float] = []

    for noisy in noisy_rows:
        source_id = noisy.get("noise_parent_id")
        if not isinstance(source_id, str) or source_id not in source_by_id:
            raise NoiseValidationError("noisy record references an unknown source")
        if source_id in selected_sources:
            raise NoiseValidationError(f"source {source_id} has more than one noisy variant")
        selected_sources.add(source_id)
        parent = source_by_id[source_id]
        try:
            noise_type = NoiseType(noisy.get("noise_type"))
        except (TypeError, ValueError) as exc:
            raise NoiseValidationError("noisy record has an invalid noise_type") from exc
        type_counts[noise_type.value] += 1
        if noisy.get("id") != f"{source_id}-noise-{noise_type.value}":
            raise NoiseValidationError("noisy record ID does not match its source and type")
        if noisy.get("noise_seed") != config.seed:
            raise NoiseValidationError("noisy record seed does not match the run config")
        if noisy.get("nl_original") != parent.get("nl"):
            raise NoiseValidationError("noisy record nl_original does not match its source")
        if noisy.get("nl") == parent.get("nl"):
            raise NoiseValidationError("noisy record must change the raw question")
        _assert_immutable(parent, noisy)

        normalized = normalize_question(str(noisy.get("nl", "")))
        if noisy.get("nl_normalized") != normalized:
            raise NoiseValidationError("noisy record has stale nl_normalized data")
        original_normalized = normalize_question(str(parent["nl"]))
        distance = normalized_levenshtein(original_normalized, normalized)
        try:
            stored_distance = float(noisy.get("noise_distance"))
        except (TypeError, ValueError) as exc:
            raise NoiseValidationError("noisy record has invalid distance metadata") from exc
        if abs(stored_distance - distance) > 1e-12:
            raise NoiseValidationError("noisy record distance metadata does not match text")
        if not _distance_is_valid(noise_type, distance):
            raise NoiseValidationError(
                f"noisy record distance violates the {noise_type.value} quality gate"
            )
        if noise_type is NoiseType.MIXED_CASE:
            if normalized != original_normalized:
                raise NoiseValidationError("mixed_case noise must normalize to its source")
        else:
            if normalized in normalized_seen:
                raise NoiseValidationError("non-mixed noisy normalized question collides")
            normalized_seen.add(normalized)
            distances.append(distance)
        try:
            validate_question_anchors(str(noisy["nl"]), parent, entity_index)
        except ParaphraseValidationError as exc:
            raise NoiseValidationError(
                f"noisy record {noisy['id']} failed anchor validation: {exc}"
            ) from exc

    expected_counts = {noise_type.value: count for noise_type, count in config.quotas.items()}
    if dict(type_counts) != expected_counts:
        raise NoiseValidationError(f"noise type quotas do not match contract: {dict(type_counts)}")
    if not distances:
        raise NoiseValidationError("Stage D requires nonzero-distance variants")
    return NoiseStats(
        original_count=len(originals),
        noisy_count=len(noisy_rows),
        output_count=len(stage_d),
        type_counts=expected_counts,
        unique_raw_questions=len(set(raw_questions)),
        unique_normalized_questions=len(normalized_seen),
        mean_nonzero_distance=sum(distances) / len(distances),
        max_distance=max(distances),
    )
