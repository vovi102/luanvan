"""Pinned, offline-reviewable shared campaign configuration and free-only live gates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nl2sparql.evaluation.artifacts import (
    _decode_dataclass,
    canonical_json,
    load_and_verify_artifact,
)
from nl2sparql.evaluation.contracts import CanonicalPredictionRun, EvaluationError, ExecutionPolicy
from nl2sparql.evaluation.shared_execution import plan_shared_campaign


def _pinned_file(item):
    path = Path(item["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != item["file_sha256"]:
        raise EvaluationError(f"shared input file hash mismatch: {path}")
    return path


def load_shared_config(path: Path):
    """Resolve all exact input bytes before exposing an executable plan."""
    try:
        config = json.loads(path.read_bytes())
        if config["protocol_id"] != "exact-sql-shared-v1":
            raise EvaluationError("unknown shared execution protocol")
        source = _pinned_file(config["source_context"])
        inputs = tuple(_pinned_file(item) for item in config["prediction_runs"])
        runs = tuple(load_and_verify_artifact(item) for item in inputs)
        if not all(isinstance(run, CanonicalPredictionRun) for run in runs):
            raise EvaluationError("shared inputs must be canonical prediction runs")
        policy = _decode_dataclass(config["policy"], ExecutionPolicy)
        plan = plan_shared_campaign(runs)
        scope = {
            "campaign_id": config["campaign_id"],
            "protocol_id": config["protocol_id"],
            "source_context": config["source_context"],
            "prediction_runs": config["prediction_runs"],
            "policy": policy,
            "runs": plan.runs,
            "queries": plan.queries,
            "free_only": config["free_only"],
        }
        scope_sha = hashlib.sha256(canonical_json(scope)).hexdigest()
        return config, runs, policy, scope, scope_sha, (path, source, *inputs)
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluationError(f"invalid shared campaign config: {exc}") from exc


def require_live_approval(config, scope_sha, policy, *, now=None):
    """Require fresh allowance evidence, zero paid authorization and exact-scope approval."""
    now = now or datetime.now(UTC)
    try:
        free = config["free_only"]
        approval = config["live_approval"]
        if config["allow_bigquery"] is not True or not isinstance(approval, dict):
            raise EvaluationError("shared live execution has not been approved")
        if (
            free["billing_enabled"] is not False
            or free["paid_spend_authorized_usd"] != "0"
            or free["project"] != policy.project
            or free["location"] != policy.location
        ):
            raise EvaluationError("shared execution requires free-only billing/project evidence")
        allowance = free["verified_remaining_bytes"]
        reservation = free["reservation_bytes"]
        if (
            type(allowance) is not int
            or type(reservation) is not int
            or not 0 < reservation <= allowance
            or policy.aggregate_byte_cap > reservation
            or policy.billed_byte_cap > reservation
        ):
            raise EvaluationError(
                "verified free allowance/reservation does not cover campaign caps"
            )
        _pinned_file(free["evidence"])
        observed = datetime.fromisoformat(free["observed_at_utc"])
        expires = datetime.fromisoformat(free["valid_until_utc"])
        if (
            observed.tzinfo is None
            or expires.tzinfo is None
            or observed > now
            or now - observed > timedelta(hours=24)
            or expires <= now
            or observed.year != now.year
            or observed.month != now.month
        ):
            raise EvaluationError("free allowance/source context evidence is stale")
        if (
            approval["scope_sha256"] != scope_sha
            or not approval["reviewer_id"]
            or not approval["approved_at_utc"]
        ):
            raise EvaluationError("final live approval does not bind this exact shared scope")
        approved = datetime.fromisoformat(approval["approved_at_utc"])
        if approved.tzinfo is None or approved > now or approved < observed:
            raise EvaluationError("final live approval must follow the allowance observation")
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluationError(f"incomplete shared live approval: {exc}") from exc
