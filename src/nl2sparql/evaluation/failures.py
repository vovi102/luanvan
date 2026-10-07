"""Deterministic multi-label failure classification and manual sidecars."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from nl2sparql.evaluation.artifacts import canonical_json
from nl2sparql.evaluation.contracts import (
    EvaluationError,
    ManualFailureReview,
    PredictionCase,
    QueryExecution,
)
from nl2sparql.evaluation.sql_semantics import analyze_sql

_PREDICTION_TAGS = {
    "no_output": "no_output",
    "invalid_sql": "invalid_sql",
    "unsafe_sql": "unsafe_sql",
    "generation_error": "generation_error",
    "timeout": "timeout",
}
_EXECUTION_TAGS = {
    "error": "execution_error",
    "timeout": "timeout",
    "guard_blocked": "guard_blocked",
    "unresolved_cost": "cost_unresolved",
}
_ROOT_CAUSE_TAGS = {
    "no_output",
    "invalid_sql",
    "unsafe_sql",
    "execution_error",
    "timeout",
    "wrong_relation",
    "wrong_projection",
    "wrong_filter",
    "wrong_join",
    "wrong_aggregation",
    "wrong_order_or_limit",
    "guard_blocked",
    "generation_error",
    "cost_unresolved",
}
_MANUAL_TAGS = _ROOT_CAUSE_TAGS | {"answer_mismatch", "semantic_drift", "unclassified"}
FAILURE_MODE_TAGS = tuple(sorted(_MANUAL_TAGS | {"missing_execution"}))
_MANUAL_FIELDS = {
    "case_id",
    "reviewer_id",
    "tags",
    "note_sha256",
    "review_artifact_sha256",
    "source",
}


def classify_failure(
    *,
    prediction: PredictionCase,
    gold_execution: QueryExecution,
    predicted_execution: QueryExecution,
    execution_match: bool,
) -> tuple[str, ...]:
    """Return sorted supported failure tags; never infer semantic drift."""
    del gold_execution  # Gold validity is handled at the execution/report boundary.
    if execution_match:
        return ()

    tags: set[str] = set()
    if prediction.prediction_status != "ok":
        tags.add(_PREDICTION_TAGS[prediction.prediction_status])
    execution_tag = _EXECUTION_TAGS.get(predicted_execution.status)
    if execution_tag is not None:
        tags.add(execution_tag)

    if prediction.prediction_status == "ok" and prediction.predicted_sql is not None:
        try:
            gold = analyze_sql(prediction.gold_sql).facts
            predicted = analyze_sql(prediction.predicted_sql).facts
        except EvaluationError:
            tags.add("invalid_sql")
        else:
            if gold.relations != predicted.relations:
                tags.add("wrong_relation")
            if gold.projections != predicted.projections:
                tags.add("wrong_projection")
            if gold.filters != predicted.filters:
                tags.add("wrong_filter")
            if gold.joins != predicted.joins:
                tags.add("wrong_join")
            if (
                gold.aggregations,
                gold.grouping,
                gold.windows,
            ) != (
                predicted.aggregations,
                predicted.grouping,
                predicted.windows,
            ):
                tags.add("wrong_aggregation")
            if (gold.ordering, gold.limit, gold.offset) != (
                predicted.ordering,
                predicted.limit,
                predicted.offset,
            ):
                tags.add("wrong_order_or_limit")

    if predicted_execution.status == "ok":
        tags.add("answer_mismatch")
    if not tags.intersection(_ROOT_CAUSE_TAGS):
        tags.add("unclassified")
    return tuple(sorted(tags))


def load_manual_failure_reviews(path: Path) -> tuple[ManualFailureReview, ...]:
    """Load canonical JSONL manual reviews and verify each record identity digest."""
    try:
        raw_lines = path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise EvaluationError(f"cannot read manual failure reviews: {exc}") from exc
    reviews: list[ManualFailureReview] = []
    for index, raw_line in enumerate(raw_lines, start=1):
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvaluationError(f"manual review line {index} is invalid JSON") from exc
        if not isinstance(record, dict) or set(record) != _MANUAL_FIELDS:
            raise EvaluationError(f"manual review line {index} has invalid exact field set")
        if raw_line != canonical_json(record):
            raise EvaluationError(f"manual review line {index} is not canonical")
        tags = record["tags"]
        if (
            not isinstance(tags, list)
            or tuple(tags) != tuple(sorted(set(tags)))
            or any(tag not in _MANUAL_TAGS for tag in tags)
        ):
            raise EvaluationError(f"manual review line {index} has invalid sorted tags")
        base = {key: record[key] for key in _MANUAL_FIELDS - {"review_artifact_sha256"}}
        expected = hashlib.sha256(canonical_json(base)).hexdigest()
        supplied = record["review_artifact_sha256"]
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
            raise EvaluationError(f"manual review line {index} digest mismatch")
        try:
            reviews.append(
                ManualFailureReview(
                    case_id=record["case_id"],
                    reviewer_id=record["reviewer_id"],
                    tags=tuple(tags),
                    note_sha256=record["note_sha256"],
                    review_artifact_sha256=supplied,
                    source=record["source"],
                )
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, EvaluationError):
                raise
            raise EvaluationError(f"manual review line {index} is invalid") from exc
    if len({review.case_id for review in reviews}) != len(reviews):
        raise EvaluationError("manual failure review case IDs must be unique")
    return tuple(reviews)
