import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nl2sparql.evaluation.contracts import (
    CostEvidence,
    EvaluationError,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    QueryExecution,
    QueryResultEvidence,
)
from nl2sparql.evaluation.failures import classify_failure, load_manual_failure_reviews

SHA_A = "a" * 64
SHA_B = "b" * 64


def _cost(observed: bool = False) -> CostEvidence:
    return (
        CostEvidence("observed", Decimal("0"), "USD", "job")
        if observed
        else CostEvidence("unmeasured", None, None, None)
    )


def _execution(status: str = "ok") -> QueryExecution:
    submitted = status in ("ok", "unresolved_cost")
    return QueryExecution(
        status=status,
        job_id="job" if submitted else None,
        latency_ms=1.0 if submitted else None,
        billed_bytes=0 if status == "ok" else None,
        cost=_cost(status == "ok"),
        result=(QueryResultEvidence((), SHA_A, 0, 0, False, (), SHA_B) if submitted else None),
        error_code=None if status == "ok" else status,
    )


def _prediction(
    predicted_sql: str | None,
    status: str = "ok",
    *,
    gold_sql: str = "SELECT owner FROM `p.d.tx` WHERE value > 10",
) -> PredictionCase:
    return PredictionCase(
        case_id="q1",
        question="Question",
        gold_sql=gold_sql,
        difficulty="easy",
        categories=("simple",),
        prediction_status=status,
        predicted_sql=predicted_sql,
        raw_output_sha256=SHA_A if predicted_sql else None,
        error_code=None if status == "ok" else status,
        inference=InferenceEvidence(None, None, None, _cost()),
        privacy=PrivacyEvidence("documented", "none", None, SHA_A, SHA_B),
    )


@pytest.mark.parametrize(
    ("prediction_status", "expected"),
    [
        ("no_output", "no_output"),
        ("invalid_sql", "invalid_sql"),
        ("unsafe_sql", "unsafe_sql"),
        ("generation_error", "generation_error"),
        ("timeout", "timeout"),
    ],
)
def test_prediction_terminal_statuses_map_to_operational_tags(
    prediction_status: str, expected: str
) -> None:
    tags = classify_failure(
        prediction=_prediction(None, prediction_status),
        gold_execution=_execution(),
        predicted_execution=_execution("not_run"),
        execution_match=False,
    )
    assert expected in tags
    assert "semantic_drift" not in tags


@pytest.mark.parametrize(
    ("execution_status", "expected"),
    [
        ("error", "execution_error"),
        ("timeout", "timeout"),
        ("guard_blocked", "guard_blocked"),
        ("unresolved_cost", "cost_unresolved"),
    ],
)
def test_execution_statuses_add_operational_tags(execution_status: str, expected: str) -> None:
    tags = classify_failure(
        prediction=_prediction("SELECT owner FROM `p.d.tx` WHERE value > 10"),
        gold_execution=_execution(),
        predicted_execution=_execution(execution_status),
        execution_match=False,
    )
    assert expected in tags


def test_structural_failure_is_multi_label_and_answer_mismatch_is_a_symptom() -> None:
    prediction = _prediction(
        "SELECT COUNT(b.height) FROM `p.d.blocks` b JOIN `p.d.labels` l "
        "ON b.owner = l.owner WHERE b.value < 2 GROUP BY b.owner ORDER BY b.owner LIMIT 1"
    )
    tags = classify_failure(
        prediction=prediction,
        gold_execution=_execution(),
        predicted_execution=_execution(),
        execution_match=False,
    )
    assert tags == tuple(sorted(tags))
    assert {
        "answer_mismatch",
        "wrong_aggregation",
        "wrong_filter",
        "wrong_join",
        "wrong_order_or_limit",
        "wrong_projection",
        "wrong_relation",
    }.issubset(tags)
    assert "semantic_drift" not in tags


def test_execution_equivalent_alternative_has_no_failure_tags() -> None:
    tags = classify_failure(
        prediction=_prediction("SELECT sender AS owner FROM `p.d.tx` WHERE value > 10"),
        gold_execution=_execution(),
        predicted_execution=_execution(),
        execution_match=True,
    )
    assert tags == ()


def test_answer_mismatch_without_supported_root_cause_is_unclassified() -> None:
    sql = "SELECT owner FROM `p.d.tx` WHERE value > 10"
    tags = classify_failure(
        prediction=_prediction(sql),
        gold_execution=_execution(),
        predicted_execution=_execution(),
        execution_match=False,
    )
    assert tags == ("answer_mismatch", "unclassified")


def test_manual_sidecar_validates_exact_fields_digest_identity_and_canonical_bytes(
    tmp_path: Path,
) -> None:
    base = {
        "case_id": "q1",
        "note_sha256": SHA_A,
        "reviewer_id": "reviewer-01",
        "source": "manual_review",
        "tags": ["semantic_drift"],
    }
    canonical_base = (
        '{"case_id":"q1","note_sha256":"'
        + SHA_A
        + '","reviewer_id":"reviewer-01","source":"manual_review",'
        + '"tags":["semantic_drift"]}\n'
    ).encode()
    record = base | {"review_artifact_sha256": hashlib.sha256(canonical_base).hexdigest()}
    path = tmp_path / "manual.jsonl"
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    reviews = load_manual_failure_reviews(path)
    assert reviews[0].tags == ("semantic_drift",)
    assert reviews[0].source == "manual_review"

    record["review_artifact_sha256"] = SHA_B
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(EvaluationError, match="digest"):
        load_manual_failure_reviews(path)

    record["review_artifact_sha256"] = hashlib.sha256(canonical_base).hexdigest()
    record["extra"] = datetime(2026, 9, 26, tzinfo=UTC).isoformat()
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(EvaluationError, match="field set"):
        load_manual_failure_reviews(path)
