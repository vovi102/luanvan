#!/usr/bin/env python3
"""Prepare the approved T5.4 shared protocol offline; never submit network requests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nl2sparql.evaluation.artifacts import canonical_json, publish_immutable
from nl2sparql.evaluation.shared_config import load_shared_config
from nl2sparql.evaluation.shared_execution import plan_shared_campaign

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path("docs/evidence/t54-shared-protocol-2026-10-24")
CONFIG = Path("configs/t54/shared-campaign-2026-10-24.json")


def pin(path):
    path = Path(path)
    return {"path": str(path), "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def publish(path, value):
    publish_immutable(path, canonical_json(value), protected_paths=())


def main():
    if Path.cwd() != ROOT:
        raise SystemExit(f"Run from {ROOT}")
    mapping = json.loads(
        Path("docs/evidence/t54-phase-a-2026-10-24/privacy-bound-runs.json").read_bytes()
    )
    proposal = json.loads(Path("configs/t54/b12-bigquery-review-proposal.json").read_bytes())
    context = {
        "kind": "shared_campaign_source_context_not_live_verification",
        "project": "nl2sparql-thesis",
        "location": "US",
        "query_cache": False,
        "sql_normalization": False,
        "cross_campaign_reuse": False,
        "inputs": [
            pin(p)
            for p in (
                "docs/evidence/t54-bigquery-review-2026-10-24/manifest.json",
                "docs/evidence/t54-bigquery-review-2026-10-24/metadata.json",
                "docs/evidence/t54-phase-a-2026-10-24/privacy-bound-runs.json",
                "docs/evidence/t54-phase-a-final-2026-10-24/manifest.json",
                "docs/evidence/t54-phase-a-final-2026-10-24/combined-estimates.json",
            )
        ],
        "source_expiry_review": "Some managed sources expire 2026-12-09 UTC; refresh before live.",
        "limitations": [
            "monthly remaining free allowance unknown",
            "public view transitive dependencies not fully visible",
            "dry-run survey is not live execution evidence",
        ],
    }
    context_path = EVIDENCE / "source-context.json"
    publish(context_path, context)
    policy = {
        "project": "nl2sparql-thesis",
        "location": "US",
        "timeout_seconds": 120.0,
        "per_query_byte_cap": 24 * 2**30,
        "aggregate_byte_cap": 775 * 2**30,
        "aggregate_billed_byte_cap": 775 * 2**30,
        "estimated_cost_cap": "4.75",
        "pricing": {
            key: proposal["pricing"][key]
            for key in (
                "policy_id",
                "currency",
                "amount_per_tib",
                "source_sha256",
                "minimum_billed_bytes",
                "billing_increment_bytes",
            )
        },
    }
    settings = {
        "protocol_id": "exact-sql-shared-v1",
        "campaign_id": "t54-b12-envi-shared-20261024-c01",
        "allow_bigquery": False,
        "live_approval": None,
        "source_context": pin(context_path),
        "prediction_runs": [
            {"path": row["canonical_path"], "file_sha256": row["canonical_file_sha256"]}
            for row in sorted(mapping["runs"], key=lambda row: row["run_id"])
        ],
        "policy": policy,
        "free_only": {
            "project": "nl2sparql-thesis",
            "location": "US",
            "billing_enabled": False,
            "paid_spend_authorized_usd": "0",
            "verified_remaining_bytes": None,
            "reservation_bytes": 800 * 2**30,
            "observed_at_utc": None,
            "valid_until_utc": None,
            "evidence": None,
            "note": "775 GiB campaign caps + 25 GiB reserve; proposed, not live approved.",
        },
    }
    publish(CONFIG, settings)
    _, runs, execution_policy, scope, scope_sha, _ = load_shared_config(CONFIG)
    plan = plan_shared_campaign(runs)
    publish(
        EVIDENCE / "campaign-plan.json",
        {
            "kind": "shared_campaign_plan_not_execution_evidence",
            "scope_sha256": scope_sha,
            "scope": scope,
        },
    )
    survey = json.loads(
        Path("docs/evidence/t54-phase-a-final-2026-10-24/combined-estimates.json").read_bytes()
    )
    inventory = {row["sql_sha256"]: row for row in survey["query_inventory"]}
    assert set(inventory) == dict(plan.queries).keys()
    gold = {case.gold_query_sha256 for ref in plan.runs for case in ref.cases}
    eligible = []
    rejected = []
    for key, _ in plan.queries:
        item = inventory[key]
        amount = item["estimated_bytes"]
        if amount is None or amount > execution_policy.per_query_byte_cap:
            assert key not in gold
            rejected.append(item)
        else:
            eligible.append(amount)
    summary = {
        "kind": "offline_shared_preparation_not_execution_evidence",
        "scope_sha256": scope_sha,
        "canonical_runs": len(runs),
        "logical_cases": sum(len(r.cases) for r in runs),
        "unique_physical_SQL": len(plan.queries),
        "unique_gold_SQL": len(gold),
        "logical_query_uses": sum(
            1 + (c.prediction_query_sha256 is not None) for r in plan.runs for c in r.cases
        ),
        "previous_survey_eligible_unique_SQL": len(eligible),
        "previous_survey_rejected_predictions": rejected,
        "previous_survey_eligible_bytes": sum(eligible),
        "previous_survey_eligible_conservative_billed_bytes": sum(
            execution_policy.pricing.conservative_billed_bytes(v) for v in eligible
        ),
        "live_queries_submitted": 0,
        "free_allowance_verified": False,
        "live_approval": None,
        "note": (
            "Previous survey is a forecast only; all initial/immediate preflights stay required."
        ),
    }
    publish(EVIDENCE / "offline-preparation.json", summary)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "previous_survey_rejected_predictions"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
