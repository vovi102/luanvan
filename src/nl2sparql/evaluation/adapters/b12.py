"""Adapter from native B1/B2 artifacts to the canonical prediction contract."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class B12AdaptRequest:
    """Paths and provenance mode for one native B1/B2 run."""

    test_set_path: Path
    predictions_path: Path
    log_path: Path
    report_path: Path
    privacy_review_path: Path | None = None
    synthetic: bool = False


def _load_report(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read B1/B2 report: {exc}") from exc
    if not isinstance(document, dict):
        raise EvaluationError("B1/B2 report must be an object")
    supplied = document.pop("report_sha256", None)
    expected = hashlib.sha256(canonical_json(document)).hexdigest()
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        raise EvaluationError("B1/B2 report digest mismatch")
    return document


def _identity(row: dict[str, Any]) -> tuple[object, ...]:
    return (
        row.get("run_id"),
        row.get("seed"),
        row.get("generated_at_utc"),
        row.get("input_sha256"),
    )


def _privacy(
    path: Path | None, baseline: str, test_set_sha256: str
) -> tuple[PrivacyEvidence, ArtifactRef | None]:
    if path is None:
        return PrivacyEvidence("undocumented", "unknown", None, None, None), None
    review = load_privacy_review(path)
    if review.baseline_id != baseline or review.test_set_sha256 != test_set_sha256:
        raise EvaluationError("privacy review identity does not match baseline/test-set identity")
    digest = sha256_file(path)
    return (
        PrivacyEvidence(
            "documented", review.data_egress, review.provider, review.policy_sha256, digest
        ),
        ArtifactRef("privacy_review", "application/json", digest, 1),
    )


def _stable_single(values: list[object], label: str) -> object:
    first = values[0]
    if any(value != first for value in values[1:]):
        raise EvaluationError(f"B1/B2 predictions contain inconsistent {label}")
    return first


def adapt_b12(request: B12AdaptRequest) -> CanonicalPredictionRun:
    """Validate all native cross-file identities before canonical conversion."""
    paths = [
        request.test_set_path,
        request.predictions_path,
        request.log_path,
        request.report_path,
    ]
    if request.privacy_review_path is not None:
        paths.append(request.privacy_review_path)
    require_distinct_files(*paths)
    authoritative = load_authoritative_test_set(request.test_set_path, synthetic=request.synthetic)
    prediction_rows = read_jsonl_objects(request.predictions_path)
    log_rows = read_jsonl_objects(request.log_path)
    report = _load_report(request.report_path)
    if not prediction_rows or len(prediction_rows) != len(log_rows):
        raise EvaluationError("B1/B2 artifacts require complete equal-length rows")

    primary_identity = _identity(prediction_rows[0])
    if any(_identity(row) != primary_identity for row in prediction_rows):
        raise EvaluationError("B1/B2 prediction cross-file identity is inconsistent")
    if any(_identity(row) != primary_identity for row in log_rows):
        raise EvaluationError("B1/B2 log cross-file identity mismatch")
    report_identity = tuple(
        report.get(key) for key in ("run_id", "seed", "generated_at_utc", "input_sha256")
    )
    if report_identity != primary_identity:
        raise EvaluationError("B1/B2 report cross-file identity mismatch")
    if report.get("prediction_count") != len(prediction_rows):
        raise EvaluationError("B1/B2 report prediction count mismatch")
    if primary_identity[3] != authoritative.sha256:
        raise EvaluationError("B1/B2 input hash does not match authoritative test set")

    expected_order = tuple(case.case_id for case in authoritative.cases)
    prediction_order = tuple(row.get("case_id") for row in prediction_rows)
    log_order = tuple(row.get("case_id") for row in log_rows)
    if prediction_order != expected_order:
        raise EvaluationError("B1/B2 prediction case order must match authoritative order")
    if log_order != prediction_order:
        raise EvaluationError("B1/B2 log case order does not match predictions")

    baseline = prediction_rows[0].get("prediction", {}).get("baseline")
    if baseline not in ("b1", "b2") or any(row.get("baseline") != baseline for row in log_rows):
        raise EvaluationError("B1/B2 baseline identity mismatch")
    report_selected = report.get("selected_examples_sha256")
    selected = [
        row.get("prediction", {}).get("selected_examples_sha256") for row in prediction_rows
    ]
    if report_selected != selected:
        raise EvaluationError("B1/B2 selected-example report binding mismatch")

    model_revisions = [row["prediction"]["completion"]["model_revision"] for row in prediction_rows]
    model_revision = _stable_single(model_revisions, "model revision")
    model_ids = [row["prediction"]["completion"]["model_id"] for row in prediction_rows]
    model_id = _stable_single(model_ids, "model ID")
    for field, label in (
        ("config_sha256", "config fingerprint"),
        ("catalog_sha256", "catalog fingerprint"),
        ("summary_sha256", "summary fingerprint"),
        ("prompt_sha256", "prompt fingerprint"),
        ("training_sha256", "training fingerprint"),
        ("encoder_id", "encoder ID"),
        ("encoder_revision", "encoder revision"),
    ):
        _stable_single([row["prediction"].get(field) for row in prediction_rows], label)
    for row, log in zip(prediction_rows, log_rows, strict=True):
        prediction = row["prediction"]
        if log.get("selected_examples_sha256") != prediction.get("selected_examples_sha256"):
            raise EvaluationError("B1/B2 selected-example cross-file identity mismatch")
        if log.get("extraction_status") != prediction.get("extraction_status"):
            raise EvaluationError("B1/B2 extraction-status cross-file identity mismatch")
        for field in ("latency_ms",):
            if log.get(field) != prediction.get(field):
                raise EvaluationError(f"B1/B2 {field} cross-file identity mismatch")
        completion = prediction["completion"]
        if (log.get("input_tokens"), log.get("output_tokens")) != (
            completion.get("input_tokens"),
            completion.get("output_tokens"),
        ):
            raise EvaluationError("B1/B2 token cross-file identity mismatch")

    generated_raw = primary_identity[2]
    try:
        generated_at = datetime.fromisoformat(str(generated_raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationError("B1/B2 generated timestamp is invalid") from exc
    privacy, privacy_ref = _privacy(request.privacy_review_path, baseline, authoritative.sha256)
    unmeasured = CostEvidence("unmeasured", None, None, None)
    by_id = {case.case_id: case for case in authoritative.cases}
    cases: list[PredictionCase] = []
    status_map = {
        "ok": "ok",
        "empty": "no_output",
        "prose": "no_output",
        "invalid_sql": "invalid_sql",
        "unsafe_sql": "unsafe_sql",
    }
    for row, log in zip(prediction_rows, log_rows, strict=True):
        gold = by_id[row["case_id"]]
        prediction = row["prediction"]
        if (
            row.get("gold_sql") != gold.gold_sql
            or row.get("difficulty") != gold.difficulty
            or tuple(row.get("categories", ())) != gold.categories
            or prediction.get("question") != gold.question
        ):
            raise EvaluationError("B1/B2 duplicated gold metadata mismatch")
        native_status = prediction.get("extraction_status")
        if native_status not in status_map:
            raise EvaluationError("B1/B2 extraction status is unsupported")
        raw_output = prediction.get("raw_output")
        if not isinstance(raw_output, str):
            raise EvaluationError("B1/B2 raw output must be text")
        cases.append(
            PredictionCase(
                case_id=gold.case_id,
                question=gold.question,
                gold_sql=gold.gold_sql,
                difficulty=gold.difficulty,
                categories=gold.categories,
                prediction_status=status_map[native_status],
                predicted_sql=prediction.get("sql"),
                raw_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest(),
                error_code=None if native_status == "ok" else native_status,
                inference=InferenceEvidence(
                    latency_ms=float(log["latency_ms"]),
                    input_tokens=log["input_tokens"],
                    output_tokens=log["output_tokens"],
                    cost=unmeasured,
                ),
                privacy=privacy,
            )
        )

    first_prediction = prediction_rows[0]["prediction"]
    fingerprint_values: dict[str, str] = {
        "catalog": first_prediction["catalog_sha256"],
        "config": first_prediction["config_sha256"],
        "model_id": hashlib.sha256(str(model_id).encode()).hexdigest(),
        "model_revision": str(model_revision),
        "prompt": first_prediction["prompt_sha256"],
        "selected_examples": hashlib.sha256(canonical_json(selected)).hexdigest(),
        "summary": first_prediction["summary_sha256"],
    }
    for key in ("training_sha256", "encoder_revision"):
        value = first_prediction.get(key)
        if isinstance(value, str):
            fingerprint_values[key.removesuffix("_sha256")] = value
    refs = [
        ArtifactRef("inference_log", "application/jsonl", sha256_file(request.log_path), 1),
        ArtifactRef("predictions", "application/jsonl", sha256_file(request.predictions_path), 1),
        ArtifactRef("report", "application/json", sha256_file(request.report_path), 1),
        ArtifactRef("test_set", "application/jsonl", authoritative.sha256, 1),
    ]
    if privacy_ref is not None:
        refs.append(privacy_ref)
    synthetic_backend = any(bool(row.get("synthetic_backend")) for row in log_rows)
    return CanonicalPredictionRun(
        baseline_id=baseline,
        run_id=str(primary_identity[0]),
        seed=int(primary_identity[1]),
        generated_at=generated_at,
        test_set_sha256=authoritative.sha256,
        test_case_count=len(cases),
        provenance=RunProvenance(
            reviewed=authoritative.reviewed,
            live_verified=authoritative.live_verified,
            synthetic=request.synthetic or synthetic_backend,
            fingerprints=tuple(sorted(fingerprint_values.items())),
        ),
        source_artifacts=tuple(sorted(refs, key=lambda ref: ref.role)),
        adapter_id="b12-native-v1",
        adapter_schema_version=1,
        cases=tuple(cases),
    )
