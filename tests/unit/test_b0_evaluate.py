from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.models.b0 import B0Prediction
from nl2sparql.models.b0.evaluate import (
    B0CaseSet,
    B0EvaluationCase,
    B0EvaluationError,
    evaluate_b0,
    load_b0_cases,
)

GOLD_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


def _row(case_id: str, *, verified: bool = True) -> dict[str, object]:
    return {
        "ambiguity_flag": False,
        "categories": ["entity_lookup"],
        "cq_ids": ["CQ07"],
        "difficulty": "easy",
        "evidence_sha256": hashlib.sha256(GOLD_SQL.encode()).hexdigest() if verified else None,
        "expected_result_size": 1 if verified else None,
        "id": case_id,
        "nl": f"Question {case_id}",
        "pool_b_writer": "writer_1",
        "pool_c_reviewers": ["reviewer_1"],
        "schema_elements": ["entity_labels_v1.address"],
        "source": "author_1",
        "sql": GOLD_SQL,
        "verified_at": "2026-08-15T00:00:00Z" if verified else None,
        "verified_executable": verified,
    }


def _write_jsonl(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _prediction(sql: str) -> B0Prediction:
    return B0Prediction(
        sql=sql,
        template_id="T_LIST_KNOWN_EXCHANGES",
        match_mode="seed",
        score=1.0,
        slots=(),
        template_sha256="a" * 64,
        policy_sha256="b" * 64,
        catalog_sha256=None,
        entities_sha256=None,
        aliases_sha256=None,
        concepts_sha256=None,
        schema_elements=("entity_labels_v1.address",),
        cq_ids=("CQ07",),
        warnings=(),
    )


class _Baseline:
    def __init__(self, predictions: dict[str, B0Prediction | None]) -> None:
        self.predictions = predictions

    def predict_detailed(self, question: str) -> B0Prediction | None:
        return self.predictions[question]


def _clock() -> object:
    values = iter(range(0, 1_000_000_000, 1_000_000))
    return lambda: next(values)


def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path, [_row("Q001"), _row("Q001")])

    with pytest.raises(B0EvaluationError, match="duplicate"):
        load_b0_cases(path, synthetic=True)


def test_scientific_rows_require_live_verification(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path, [_row("Q001", verified=False)])

    with pytest.raises(B0EvaluationError, match="verified"):
        load_b0_cases(path, synthetic=False)


def test_synthetic_rows_allow_explicitly_unverified_fixture(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path, [_row("Q001", verified=False)])

    cases = load_b0_cases(path, synthetic=True)

    assert cases.synthetic is True
    assert cases.cases[0].case_id == "Q001"


def test_metrics_separate_coverage_and_matched_accuracy() -> None:
    cases = B0CaseSet(
        cases=tuple(
            B0EvaluationCase(
                case_id=f"Q00{index}",
                question=f"question-{index}",
                gold_sql=GOLD_SQL,
                difficulty="easy",
            )
            for index in range(1, 4)
        ),
        input_sha256="c" * 64,
        synthetic=False,
    )
    baseline = _Baseline(
        {
            "question-1": _prediction(GOLD_SQL),
            "question-2": _prediction(GOLD_SQL.lower()),
            "question-3": None,
        }
    )

    results, report = evaluate_b0(baseline, cases, clock=_clock())

    assert len(results) == 3
    assert report.coverage == pytest.approx(2 / 3)
    assert report.exact_match_accuracy == pytest.approx(1 / 2)
    assert report.structural_accuracy == pytest.approx(1.0)
    assert report.execution_accuracy is None
    assert report.local_status == "ready"
    assert report.scientific_status == "not_ready"


def test_synthetic_report_never_becomes_ready() -> None:
    cases = B0CaseSet(
        cases=(B0EvaluationCase("Q001", "question", GOLD_SQL, "easy"),),
        input_sha256="d" * 64,
        synthetic=True,
    )
    baseline = _Baseline({"question": _prediction(GOLD_SQL)})

    _, report = evaluate_b0(baseline, cases, clock=_clock())

    assert report.local_status == "not_ready"
    assert report.scientific_status == "not_ready"
