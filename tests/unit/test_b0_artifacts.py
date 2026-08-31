from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import scripts.b0_rule_baseline_workflow as workflow


def test_report_failure_restores_previous_predictions(tmp_path: Path, monkeypatch) -> None:
    predictions = tmp_path / "predictions.jsonl"
    report = tmp_path / "report.json"
    predictions.write_bytes(b'{"accepted":true}\n')
    original_replace = os.replace

    def fail_report(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == report:
            raise OSError("report disk failure")
        original_replace(source, destination)

    monkeypatch.setattr(workflow.os, "replace", fail_report)

    with pytest.raises(workflow.ReportPublicationError, match="report disk failure"):
        workflow.publish_evaluation_artifacts(
            predictions,
            report,
            ({"case_id": "Q001"},),
            {"status": "not_ready"},
        )

    assert predictions.read_bytes() == b'{"accepted":true}\n'
    assert not report.exists()


def test_publication_is_canonical_and_report_is_last(tmp_path: Path, monkeypatch) -> None:
    predictions = tmp_path / "predictions.jsonl"
    report = tmp_path / "report.json"
    destinations: list[Path] = []
    original_replace = os.replace

    def record_replace(source: str | Path, destination: str | Path) -> None:
        destinations.append(Path(destination))
        original_replace(source, destination)

    monkeypatch.setattr(workflow.os, "replace", record_replace)

    workflow.publish_evaluation_artifacts(
        predictions,
        report,
        ({"z": 1, "a": 2},),
        {"z": 1, "status": "not_ready"},
    )

    assert destinations[-1] == report
    assert predictions.read_text(encoding="utf-8") == '{"a":2,"z":1}\n'
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "not_ready"
    assert len(payload["report_sha256"]) == 64
