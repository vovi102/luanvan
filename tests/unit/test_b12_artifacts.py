from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import scripts.small_llm_baselines_workflow as workflow
from nl2sparql.models.b12 import (
    BaselineB1,
    CatalogSummary,
    Completion,
    GenerationConfig,
    SmallLLMError,
    evaluate_baseline,
    load_evaluation_cases,
)

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


class SequenceBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)

    def generate(self, messages, config):
        raw = next(self.outputs)
        return Completion(
            raw_text=raw,
            model_id=config.model_id,
            model_revision=config.model_revision,
            input_tokens=10,
            output_tokens=5,
        )


def _write_cases(path: Path) -> Path:
    rows = [
        {
            "id": "test-001",
            "nl": "List known addresses",
            "sql": SAFE_SQL,
            "difficulty": "easy",
            "categories": ["entity_lookup"],
        },
        {
            "id": "test-002",
            "nl": "List addresses again",
            "sql": SAFE_SQL,
            "difficulty": "medium",
            "categories": ["entity_lookup", "ranking"],
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _run(tmp_path: Path):
    test_set = _write_cases(tmp_path / "test.jsonl")
    cases = load_evaluation_cases(test_set, synthetic=True)
    text = "CATALOG\nRelation entity_labels_v1\n"
    summary = CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    clock = iter([0, 1_000_000, 2_000_000, 4_000_000])
    baseline = BaselineB1(
        summary,
        GenerationConfig("b" * 40),
        SequenceBackend([SAFE_SQL, ""]),
        clock_ns=lambda: next(clock),
    )
    return evaluate_baseline(cases, baseline, run_id="run-001"), test_set


def test_load_evaluation_cases_normalizes_category_order(tmp_path: Path) -> None:
    path = _write_cases(tmp_path / "test.jsonl")
    raw = path.read_text().replace(
        '["entity_lookup", "ranking"]', '["ranking", "entity_lookup", "ranking"]'
    )
    path.write_text(raw)

    cases = load_evaluation_cases(path, synthetic=True)

    assert cases[1].categories == ("entity_lookup", "ranking")


def test_publish_writes_canonical_predictions_logs_and_report(tmp_path: Path) -> None:
    run, test_set = _run(tmp_path)
    predictions = tmp_path / "predictions.jsonl"
    logs = tmp_path / "run.jsonl"
    report = tmp_path / "report.json"

    workflow.publish_evaluation_run(
        run,
        predictions_path=predictions,
        log_path=logs,
        report_path=report,
        protected_paths=(test_set,),
    )

    prediction_rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    log_rows = [json.loads(line) for line in logs.read_text().splitlines()]
    report_payload = json.loads(report.read_text())
    assert [row["case_id"] for row in prediction_rows] == ["test-001", "test-002"]
    assert all(row["run_id"] == "run-001" for row in prediction_rows)
    assert all(row["seed"] == 42 for row in prediction_rows)
    assert all(row["generated_at_utc"].endswith("Z") for row in prediction_rows)
    assert all(len(row["input_sha256"]) == 64 for row in prediction_rows)
    assert all(len(row["prediction"]["selected_examples_sha256"]) == 64 for row in prediction_rows)
    assert log_rows[0]["input_tokens"] == 10
    assert log_rows[0]["seed"] == 42
    assert len(log_rows[0]["selected_examples_sha256"]) == 64
    assert report_payload["seed"] == 42
    assert report_payload["generated_at_utc"].endswith("Z")
    assert len(report_payload["input_sha256"]) == 64
    assert len(report_payload["selected_examples_sha256"]) == 2
    assert all(len(value) == 64 for value in report_payload["selected_examples_sha256"])
    assert report_payload["scientific_ready"] is False
    assert "synthetic_backend" in report_payload["blockers"]
    assert predictions.read_bytes().endswith(b"\n")
    assert logs.read_bytes().endswith(b"\n")
    assert report.read_bytes().endswith(b"\n")


def test_output_cannot_alias_protected_input(tmp_path: Path) -> None:
    run, test_set = _run(tmp_path)
    original = test_set.read_bytes()

    with pytest.raises(SmallLLMError, match="alias"):
        workflow.publish_evaluation_run(
            run,
            predictions_path=test_set,
            log_path=tmp_path / "run.jsonl",
            report_path=tmp_path / "report.json",
            protected_paths=(test_set,),
        )

    assert test_set.read_bytes() == original


def test_hardlink_output_alias_is_rejected(tmp_path: Path) -> None:
    run, test_set = _run(tmp_path)
    alias = tmp_path / "alias.jsonl"
    os.link(test_set, alias)

    with pytest.raises(SmallLLMError, match="alias"):
        workflow.publish_evaluation_run(
            run,
            predictions_path=alias,
            log_path=tmp_path / "run.jsonl",
            report_path=tmp_path / "report.json",
            protected_paths=(test_set,),
        )


def test_report_failure_restores_all_previous_outputs(tmp_path: Path, monkeypatch) -> None:
    run, test_set = _run(tmp_path)
    predictions = tmp_path / "predictions.jsonl"
    logs = tmp_path / "run.jsonl"
    report = tmp_path / "report.json"
    previous = {predictions: b"old predictions\n", logs: b"old logs\n", report: b"old report\n"}
    for path, payload in previous.items():
        path.write_bytes(payload)
    original_write = workflow._atomic_write

    def fail_report(path: Path, payload: bytes) -> None:
        if path == report:
            raise OSError("disk full")
        original_write(path, payload)

    monkeypatch.setattr(workflow, "_atomic_write", fail_report)

    with pytest.raises(SmallLLMError, match="publish"):
        workflow.publish_evaluation_run(
            run,
            predictions_path=predictions,
            log_path=logs,
            report_path=report,
            protected_paths=(test_set,),
        )

    assert {path: path.read_bytes() for path in previous} == previous
