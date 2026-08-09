"""Witness-grounded Stage A dataset generation support."""

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
    "StageAVerificationError",
    "StageAVerificationReport",
    "WitnessDryRun",
    "WitnessExecution",
    "WitnessGroup",
    "WitnessPreflight",
    "build_witness_groups",
    "dry_run_witnesses",
    "verify_stage_a",
]
