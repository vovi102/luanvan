"""Stage A support with live provider modules loaded only on demand."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "StageAArtifactError": "artifacts",
    "StageAArtifacts": "artifacts",
    "build_generation_config": "artifacts",
    "render_stats": "artifacts",
    "write_stage_a_artifacts": "artifacts",
    "StageAVerificationReport": "evidence",
    "WitnessDryRun": "evidence",
    "WitnessExecution": "evidence",
    "WitnessGroup": "evidence",
    "WitnessPreflight": "evidence",
    "build_witness_groups": "evidence",
    "TOTAL_WITNESS_BYTES_CAP": "verify",
    "StageAVerificationError": "verify",
    "dry_run_witnesses": "verify",
    "verify_stage_a": "verify",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(f"nl2sparql.dataset.stage_a.{module_name}"), name)
    globals()[name] = value
    return value
