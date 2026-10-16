"""Stage A support with live provider modules loaded only on demand."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "AccountPair": "account_pairs",
    "AccountPairError": "account_pairs",
    "AccountPairEvidence": "account_pairs",
    "canonical_account_pair_mappings": "account_pairs",
    "load_account_pairs": "account_pairs",
    "DiagnosticError": "diagnostics",
    "DiagnosticRecorder": "diagnostics",
    "ProjectBillingState": "diagnostics",
    "require_unbilled_project": "diagnostics",
    "serialize_diagnostic_report": "diagnostics",
    "validate_diagnostic_report": "diagnostics",
    "write_diagnostic_report": "diagnostics",
    "StageAArtifactError": "artifacts",
    "StageAArtifacts": "artifacts",
    "build_generation_config": "artifacts",
    "render_stats": "artifacts",
    "write_stage_a_artifacts": "artifacts",
    "StageAVerificationReport": "evidence",
    "LogicalWitnessResult": "evidence",
    "WitnessDryRun": "evidence",
    "WitnessExecution": "evidence",
    "WitnessGroup": "evidence",
    "WitnessPreflight": "evidence",
    "WitnessQuery": "evidence",
    "build_witness_groups": "evidence",
    "build_single_witness_queries": "planning",
    "build_stage_a_v2_witness_queries": "planning",
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
