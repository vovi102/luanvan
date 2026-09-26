"""Adapter from native deterministic B0 artifacts to the canonical run contract."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.evaluation.adapters.common import (
    load_authoritative_test_set,
    read_jsonl_objects,
    require_distinct_files,
    sha256_file,
)
from nl2sparql.evaluation.artifacts import canonical_json, load_privacy_review
from nl2sparql.evaluation.contracts import (
    ArtifactRef,
    CanonicalPredictionRun,
    CostEvidence,
    EvaluationError,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    RunProvenance,
)

_PREDICTION_FIELDS = {
    "case_id",
    "predicted_sql",
    "template_id",
    "match_mode",
    "exact_match",
    "structural_match",
    "latency_ms",
    "rejection_reason",
}


@dataclass(frozen=True)
class B0AdaptRequest:
    """Explicit native B0 inputs and canonical run identity."""

    test_set_path: Path
    predictions_path: Path
    report_path: Path
    run_id: str
    privacy_review_path: Path | None = None
    synthetic: bool = False


def _load_report(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read B0 report: {exc}") from exc
    if not isinstance(document, dict):
        raise EvaluationError("B0 report must be a JSON object")
    supplied = document.pop("report_sha256", None)
    expected = hashlib.sha256(canonical_json(document)).hexdigest()
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        raise EvaluationError("B0 report digest mismatch")
    if document.get("schema_version") != 1:
        raise EvaluationError("unsupported B0 report schema version")
    return document


def _privacy(
    request: B0AdaptRequest, test_set_sha256: str
) -> tuple[PrivacyEvidence, ArtifactRef | None]:
    if request.privacy_review_path is None:
        return PrivacyEvidence("undocumented", "unknown", None, None, None), None
    review = load_privacy_review(request.privacy_review_path)
    if review.baseline_id != "b0" or review.test_set_sha256 != test_set_sha256:
        raise EvaluationError("privacy review identity does not match B0/test-set identity")
    digest = sha256_file(request.privacy_review_path)
    return (
        PrivacyEvidence(
            "documented",
            review.data_egress,
            review.provider,
            review.policy_sha256,
            digest,
        ),
        ArtifactRef("privacy_review", "application/json", digest, 1),
    )


def _validate_rows(rows: tuple[dict[str, Any], ...]) -> None:
    for index, row in enumerate(rows, start=1):
        if set(row) != _PREDICTION_FIELDS:
            raise EvaluationError(f"B0 prediction row {index} has invalid field set")
        if not isinstance(row["case_id"], str):
            raise EvaluationError(f"B0 prediction row {index} has invalid case_id")
        latency = row["latency_ms"]
        if (
            isinstance(latency, bool)
            or not isinstance(latency, (int, float))
            or not math.isfinite(latency)
            or latency < 0
        ):
            raise EvaluationError(f"B0 prediction row {index} has invalid latency")
        if row["predicted_sql"] is not None:
            if not isinstance(row["predicted_sql"], str):
                raise EvaluationError(f"B0 prediction row {index} has invalid SQL")
            try:
                validate_sql_text(row["predicted_sql"])
            except (TestSetError, TypeError) as exc:
                raise EvaluationError(f"B0 prediction row {index} has unsafe SQL: {exc}") from exc


def adapt_b0(request: B0AdaptRequest) -> CanonicalPredictionRun:
    """Validate native B0 evidence and deterministically adapt it."""
    paths = [request.test_set_path, request.predictions_path, request.report_path]
    if request.privacy_review_path is not None:
        paths.append(request.privacy_review_path)
    require_distinct_files(*paths)
    authoritative = load_authoritative_test_set(request.test_set_path, synthetic=request.synthetic)
    rows = read_jsonl_objects(request.predictions_path)
    _validate_rows(rows)
    expected_ids = tuple(case.case_id for case in authoritative.cases)
    observed_ids = tuple(row["case_id"] for row in rows)
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(expected_ids):
        raise EvaluationError("B0 prediction case IDs must exactly match the test set")
    by_id = {row["case_id"]: row for row in rows}

    report = _load_report(request.report_path)
    if report.get("input_sha256") != authoritative.sha256:
        raise EvaluationError("B0 report test-set hash does not match authoritative input")
    if report.get("case_count") != len(rows):
        raise EvaluationError("B0 report case count does not match predictions")
    if report.get("synthetic") is not request.synthetic:
        raise EvaluationError("B0 report synthetic marker mismatch")
    matched_count = sum(row["predicted_sql"] is not None for row in rows)
    if report.get("matched_count") != matched_count:
        raise EvaluationError("B0 report does not belong to the prediction rows")

    privacy, privacy_ref = _privacy(request, authoritative.sha256)
    unmeasured = CostEvidence("unmeasured", None, None, None)
    cases: list[PredictionCase] = []
    for gold in authoritative.cases:
        row = by_id[gold.case_id]
        predicted_sql = row["predicted_sql"]
        cases.append(
            PredictionCase(
                case_id=gold.case_id,
                question=gold.question,
                gold_sql=gold.gold_sql,
                difficulty=gold.difficulty,
                categories=gold.categories,
                prediction_status="ok" if predicted_sql is not None else "no_output",
                predicted_sql=predicted_sql,
                raw_output_sha256=(
                    hashlib.sha256(predicted_sql.encode()).hexdigest()
                    if predicted_sql is not None
                    else None
                ),
                error_code=None if predicted_sql is not None else str(row["rejection_reason"]),
                inference=InferenceEvidence(float(row["latency_ms"]), None, None, unmeasured),
                privacy=privacy,
            )
        )

    source_refs = [
        ArtifactRef("predictions", "application/jsonl", sha256_file(request.predictions_path), 1),
        ArtifactRef("report", "application/json", sha256_file(request.report_path), 1),
        ArtifactRef("test_set", "application/jsonl", authoritative.sha256, 1),
    ]
    if privacy_ref is not None:
        source_refs.append(privacy_ref)
    fingerprints = tuple(
        sorted(
            (name.removesuffix("_sha256"), value)
            for name, value in report.items()
            if name.endswith("_sha256")
            and name != "input_sha256"
            and isinstance(value, str)
            and len(value) == 64
        )
    )
    return CanonicalPredictionRun(
        baseline_id="b0",
        run_id=request.run_id,
        seed=0,
        generated_at=None,
        test_set_sha256=authoritative.sha256,
        test_case_count=len(cases),
        provenance=RunProvenance(
            reviewed=authoritative.reviewed,
            live_verified=authoritative.live_verified,
            synthetic=request.synthetic,
            fingerprints=fingerprints,
        ),
        source_artifacts=tuple(sorted(source_refs, key=lambda ref: ref.role)),
        adapter_id="b0-native-v1",
        adapter_schema_version=1,
        cases=tuple(cases),
    )
