"""Stable high-level facade for the offline-first NL2SQL evaluation framework."""

from __future__ import annotations

from nl2sparql.evaluation.adapters import (
    B0AdaptRequest,
    B12AdaptRequest,
    B45AdaptRequest,
    adapt_b0,
    adapt_b12,
    adapt_b45,
)
from nl2sparql.evaluation.artifacts import load_and_verify_artifact
from nl2sparql.evaluation.contracts import CanonicalPredictionRun, EvaluationError
from nl2sparql.evaluation.execution import execute_run
from nl2sparql.evaluation.reporting import build_report, compare_reports

AdaptRequest = B0AdaptRequest | B12AdaptRequest | B45AdaptRequest


def adapt_baseline_artifacts(request: AdaptRequest) -> CanonicalPredictionRun:
    """Dispatch a typed native-artifact request to its strict adapter."""
    if isinstance(request, B0AdaptRequest):
        return adapt_b0(request)
    if isinstance(request, B12AdaptRequest):
        return adapt_b12(request)
    if isinstance(request, B45AdaptRequest):
        return adapt_b45(request)
    raise EvaluationError(f"unsupported baseline adaptation request: {type(request).__name__}")


__all__ = [
    "B0AdaptRequest",
    "B12AdaptRequest",
    "B45AdaptRequest",
    "adapt_baseline_artifacts",
    "build_report",
    "compare_reports",
    "execute_run",
    "load_and_verify_artifact",
]
