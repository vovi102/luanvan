"""Deterministic Stage D noise injection for the GoogleSQL dataset."""

from nl2sparql.dataset.noise.artifacts import (
    build_noise_manifest,
    file_sha256,
    jsonl_bytes,
    noise_artifact_lock,
    publish_noise_artifacts,
    validate_noise_manifest,
)
from nl2sparql.dataset.noise.contracts import (
    NoiseConfig,
    NoiseType,
    NoiseValidationError,
)
from nl2sparql.dataset.noise.pipeline import (
    NoiseStats,
    inject_noise,
    validate_stage_d_records,
)
from nl2sparql.dataset.noise.transforms import (
    load_abbreviations,
    noise_candidates,
    protected_terms,
    transform_question,
)

__all__ = [
    "NoiseConfig",
    "NoiseStats",
    "NoiseType",
    "NoiseValidationError",
    "build_noise_manifest",
    "file_sha256",
    "load_abbreviations",
    "noise_candidates",
    "inject_noise",
    "jsonl_bytes",
    "noise_artifact_lock",
    "publish_noise_artifacts",
    "protected_terms",
    "transform_question",
    "validate_stage_d_records",
    "validate_noise_manifest",
]
