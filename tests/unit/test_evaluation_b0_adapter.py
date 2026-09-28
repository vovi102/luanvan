import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nl2sparql.evaluation.adapters.b0 import B0AdaptRequest, adapt_b0
from nl2sparql.evaluation.adapters.common import load_authoritative_test_set
from nl2sparql.evaluation.artifacts import publish_immutable, serialize_privacy_review
from nl2sparql.evaluation.contracts import EvaluationError, PrivacyReview
from scripts.b0_rule_baseline_workflow import publish_evaluation_artifacts

SQL = "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"


def _gold(case_id: str, *, question: str | None = None) -> dict[str, object]:
    return {
        "ambiguity_flag": False,
        "categories": ["entity_lookup", "simple_filter"],
        "cq_ids": ["CQ01"],
        "difficulty": "easy",
        "evidence_sha256": hashlib.sha256(SQL.encode()).hexdigest(),
        "expected_result_size": 1,
        "id": case_id,
        "nl": question or f"Authoritative {case_id}",
        "pool_b_writer": "writer_1",
        "pool_c_reviewers": ["reviewer_1"],
        "schema_elements": ["transaction_facts.transaction_hash"],
        "source": "author_1",
        "sql": SQL,
        "verified_at": "2026-09-26T00:00:00Z",
        "verified_executable": True,
    }


def _reviewed_gold(case_id: str) -> dict[str, object]:
    return _gold(case_id) | {
        "accepted_content_sha256": "1" * 64,
        "candidate_sha256": "2" * 64,
        "catalog_sha256": "3" * 64,
        "live_evidence_sha256": "4" * 64,
        "pool_b_writer": "agent",
        "pool_c_reviewers": ["reviewer_01"],
        "provenance_bundle_sha256": "5" * 64,
        "provenance_profile": "agent_authored_human_reviewed_v1",
        "review_provenance": "single_human_reviewer",
        "selection_sha256": "6" * 64,
        "source": "agent",
    }


def _write_test_set(path: Path, rows: list[dict[str, object]]) -> str:
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _prediction(case_id: str, sql: str | None, latency: float = 3.0) -> dict[str, object]:
    return {
        "case_id": case_id,
        "predicted_sql": sql,
        "template_id": "T_TEST" if sql else None,
        "match_mode": "seed" if sql else None,
        "exact_match": bool(sql),
        "structural_match": bool(sql),
        "latency_ms": latency,
        "rejection_reason": None if sql else "unmatched",
    }


def _report(test_sha: str, predictions: list[dict[str, object]]) -> dict[str, object]:
    matched = [row for row in predictions if row["predicted_sql"]]
    return {
        "schema_version": 1,
        "status": "not_ready",
        "case_count": len(predictions),
        "matched_count": len(matched),
        "coverage": len(matched) / len(predictions),
        "exact_match_accuracy": 1.0 if matched else 0.0,
        "structural_accuracy": 1.0 if matched else 0.0,
        "latency_p50_ms": 3.0,
        "latency_p95_ms": 4.0 if len(predictions) > 1 else 3.0,
        "execution_accuracy": None,
        "local_status": "not_ready",
        "scientific_status": "not_ready",
        "input_sha256": test_sha,
        "synthetic": True,
        "match_mode_counts": [["seed", len(matched)]] if matched else [],
        "template_counts": [["T_TEST", len(matched)]] if matched else [],
        "difficulty_counts": [["easy", len(predictions)]],
        "rejection_counts": [["unmatched", len(predictions) - len(matched)]],
        "template_sha256": "1" * 64 if matched else None,
        "policy_sha256": "2" * 64 if matched else None,
        "catalog_sha256": "3" * 64 if matched else None,
        "entities_sha256": None,
        "aliases_sha256": None,
        "concepts_sha256": None,
        "git_sha": "4" * 40,
        "git_dirty": False,
    }


def _artifacts(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    test_set = tmp_path / "test.jsonl"
    test_sha = _write_test_set(test_set, [_gold("q1"), _gold("q2")])
    predictions = [_prediction("q1", SQL), _prediction("q2", None, 4.0)]
    predictions_path = tmp_path / "predictions.jsonl"
    report_path = tmp_path / "report.json"
    publish_evaluation_artifacts(
        predictions_path, report_path, predictions, _report(test_sha, predictions)
    )
    return test_set, predictions_path, report_path, test_sha


def test_adapter_uses_authoritative_gold_and_maps_unmatched_without_inventing_cost(
    tmp_path: Path,
) -> None:
    test_set, predictions, report, test_sha = _artifacts(tmp_path)
    run = adapt_b0(B0AdaptRequest(test_set, predictions, report, "b0-run", synthetic=True))

    assert run.test_set_sha256 == test_sha
    assert tuple(case.case_id for case in run.cases) == ("q1", "q2")
    assert run.cases[0].question == "Authoritative q1"
    assert run.cases[0].categories == ("entity_lookup", "simple_filter")
    assert run.cases[1].prediction_status == "no_output"
    assert run.cases[0].inference.cost.measurement_status == "unmeasured"
    assert run.generated_at is None
    assert {ref.role for ref in run.source_artifacts} == {"predictions", "report", "test_set"}
    assert not hasattr(run, "coverage")
    assert run.cases[0].privacy.documentation_status == "undocumented"


def test_authoritative_loader_exposes_agent_reviewed_profile_truthfully(tmp_path: Path) -> None:
    path = tmp_path / "reviewed.jsonl"
    _write_test_set(path, [_reviewed_gold("t35-001")])

    case_set = load_authoritative_test_set(path, synthetic=False)

    assert case_set.provenance_profile == "agent_authored_human_reviewed_v1"
    assert case_set.reviewed is True
    assert case_set.live_verified is True
    assert case_set.synthetic is False


def test_matching_privacy_review_is_bound_and_mismatch_rejected(tmp_path: Path) -> None:
    test_set, predictions, report, test_sha = _artifacts(tmp_path)
    privacy_path = tmp_path / "privacy.json"
    review = PrivacyReview(
        baseline_id="b0",
        test_set_sha256=test_sha,
        data_egress="none",
        provider=None,
        policy_sha256="5" * 64,
        reviewer_id="reviewer-01",
        reviewed_at=datetime(2026, 9, 26, tzinfo=UTC),
        synthetic=True,
    )
    publish_immutable(privacy_path, serialize_privacy_review(review))

    run = adapt_b0(
        B0AdaptRequest(test_set, predictions, report, "b0-run", privacy_path, synthetic=True)
    )
    assert run.cases[0].privacy.documentation_status == "documented"
    assert run.cases[0].privacy.review_sha256 is not None

    wrong = PrivacyReview(**(review.__dict__ | {"baseline_id": "b1"}))
    wrong_path = tmp_path / "wrong-privacy.json"
    publish_immutable(wrong_path, serialize_privacy_review(wrong))
    with pytest.raises(EvaluationError, match="privacy review identity"):
        adapt_b0(B0AdaptRequest(test_set, predictions, report, "b0-run", wrong_path, True))


def test_adapter_rejects_cross_run_test_hash_and_tampered_report(tmp_path: Path) -> None:
    test_set, predictions, report, _ = _artifacts(tmp_path)
    body = json.loads(report.read_text())
    body.pop("report_sha256")
    body["input_sha256"] = "f" * 64
    publish_evaluation_artifacts(
        predictions, report, [_prediction("q1", SQL), _prediction("q2", None, 4.0)], body
    )
    with pytest.raises(EvaluationError, match="test-set hash"):
        adapt_b0(B0AdaptRequest(test_set, predictions, report, "b0-run", synthetic=True))

    payload = report.read_bytes().replace(b'"status":"not_ready"', b'"status":"ready"')
    report.write_bytes(payload)
    with pytest.raises(EvaluationError, match="digest"):
        adapt_b0(B0AdaptRequest(test_set, predictions, report, "b0-run", synthetic=True))


def test_adapter_rejects_report_mixed_with_different_prediction_payload(
    tmp_path: Path,
) -> None:
    test_set, predictions, report, _ = _artifacts(tmp_path)
    rows = [
        _prediction("q1", f"{SQL} WHERE transaction_hash = '0x1'"),
        _prediction("q2", None, 4.0),
    ]
    predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    with pytest.raises(EvaluationError, match="prediction payload binding"):
        adapt_b0(B0AdaptRequest(test_set, predictions, report, "b0-run", synthetic=True))


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "extra"])
def test_adapter_rejects_non_exact_prediction_case_ids(tmp_path: Path, mutation: str) -> None:
    test_set, predictions_path, report_path, test_sha = _artifacts(tmp_path)
    rows = [_prediction("q1", SQL), _prediction("q2", None, 4.0)]
    if mutation == "duplicate":
        rows[1]["case_id"] = "q1"
    elif mutation == "missing":
        rows.pop()
    else:
        rows.append(_prediction("q3", SQL))
    publish_evaluation_artifacts(predictions_path, report_path, rows, _report(test_sha, rows))

    with pytest.raises(EvaluationError, match="prediction case IDs"):
        adapt_b0(B0AdaptRequest(test_set, predictions_path, report_path, "b0-run", synthetic=True))


def test_adapter_rejects_native_input_aliases(tmp_path: Path) -> None:
    test_set, predictions, report, _ = _artifacts(tmp_path)
    report.unlink()
    os.link(predictions, report)

    with pytest.raises(EvaluationError, match="distinct files"):
        adapt_b0(B0AdaptRequest(test_set, predictions, report, "b0-run", synthetic=True))
