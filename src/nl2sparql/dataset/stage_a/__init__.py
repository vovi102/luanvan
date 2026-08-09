"""Witness-grounded Stage A dataset generation support."""

from nl2sparql.dataset.stage_a.artifacts import (
    StageAArtifactError,
    StageAArtifacts,
    build_generation_config,
    render_stats,
    write_stage_a_artifacts,
)
from nl2sparql.dataset.stage_a.verify import (
    TOTAL_WITNESS_BYTES_CAP,
    StageAVerificationError,
    StageAVerificationReport,
    WitnessDryRun,
    WitnessExecution,
    WitnessGroup,
    WitnessPreflight,
    build_witness_groups,
    dry_run_witnesses,
    verify_stage_a,
)

__all__ = [
    "TOTAL_WITNESS_BYTES_CAP",
    "StageAArtifactError",
    "StageAArtifacts",
    "StageAVerificationError",
    "StageAVerificationReport",
    "WitnessDryRun",
    "WitnessExecution",
    "WitnessGroup",
    "WitnessPreflight",
    "build_generation_config",
    "build_witness_groups",
    "dry_run_witnesses",
    "render_stats",
    "verify_stage_a",
    "write_stage_a_artifacts",
]
