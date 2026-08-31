from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.class_resolver_workflow as workflow
from nl2sparql.linking.entity import GitProvenance

ADDRESS = "0x" + "1" * 40
TARGET_ID = f"address:{ADDRESS}"
TARGET_SHA256 = hashlib.sha256(TARGET_ID.encode()).hexdigest()


def _match() -> dict[str, object]:
    return {
        "span": ADDRESS,
        "span_offset": [16, 58],
        "target_id": TARGET_ID,
        "target_kind": "address",
        "owner": None,
        "addresses": [ADDRESS],
        "categories": [],
        "concept_classes": [],
        "stage": "address",
        "confidence": 1.0,
        "alternatives": [],
        "target_sha256": TARGET_SHA256,
    }


def _payload(path: Path) -> Path:
    path.write_text(
        json.dumps({"question": f"transactions to {ADDRESS}", "matches": [_match()]}),
        encoding="utf-8",
    )
    return path


def _ground_truth(path: Path) -> Path:
    rows: list[str] = []
    for index in range(50):
        question = f"transactions to {ADDRESS} case {index:02d}"
        match = {**_match(), "span_offset": [16, 58]}
        row = {
            "id": f"R{index:02d}",
            "question": question,
            "matches": [match],
            "expected": [
                {
                    "span_offset": [16, 58],
                    "target_id": TARGET_ID,
                    "resolution_kind": "instance",
                    "direction": "to",
                    "coverage_status": "supported",
                }
            ],
            "expected_status": "resolved",
        }
        rows.append(json.dumps(row) + "\n")
    path.write_text("".join(rows), encoding="utf-8")
    return path


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def test_help_never_builds_the_entity_corpus() -> None:
    def forbidden_builder(*args, **kwargs):
        raise AssertionError("help initialized the corpus")

    result = CliRunner().invoke(workflow.create_cli(corpus_builder=forbidden_builder), ["--help"])

    assert result.exit_code == 0
    assert "resolve" in result.output
    assert "evaluate" in result.output


def test_resolve_emits_one_canonical_plan_without_external_dependencies(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        workflow.create_cli(), ["resolve", "--input", str(_payload(tmp_path / "input.json"))]
    )

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["status"] == "ready"
    assert parsed["command"] == "resolve"
    assert parsed["plan"]["entities"][0]["operator"] == "in"
    assert result.output == _canonical(parsed)


def test_resolve_rejects_duplicate_json_keys_as_structured_failure(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"question":"a","question":"b","matches":[]}', encoding="utf-8")

    result = CliRunner().invoke(workflow.create_cli(), ["resolve", "--input", str(path)])

    assert result.exit_code == 1
    parsed = json.loads(result.output)
    assert parsed["status"] == "failed"
    assert parsed["cause"] == "invalid_input"
    assert "duplicate JSON key" in parsed["reason"]


def test_evaluate_missing_ground_truth_is_blocked_without_creating_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.json"

    result = CliRunner().invoke(
        workflow.create_cli(),
        [
            "evaluate",
            "--ground-truth",
            str(tmp_path / "missing.jsonl"),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "blocked"
    assert not report.exists()


def test_evaluate_publishes_a_canonical_hash_bound_report(tmp_path: Path) -> None:
    ground_truth = _ground_truth(tmp_path / "ground-truth.jsonl")
    report = tmp_path / "report.json"
    cli = workflow.create_cli(git_provenance_factory=lambda _path: GitProvenance("1" * 40, False))

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["status"] == "ready"
    assert body["case_count"] == 50
    assert body["fully_resolved_plan_accuracy"] == 1.0
    report_hash = body.pop("report_sha256")
    assert report_hash == hashlib.sha256(_canonical(body).encode()).hexdigest()
    body["report_sha256"] = report_hash
    assert report.read_text(encoding="utf-8") == _canonical(body)


def test_evaluate_rejects_report_aliasing_ground_truth_before_mutation(tmp_path: Path) -> None:
    ground_truth = _ground_truth(tmp_path / "ground-truth.jsonl")
    original = ground_truth.read_bytes()

    result = CliRunner().invoke(
        workflow.create_cli(),
        [
            "evaluate",
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(ground_truth),
        ],
    )

    assert result.exit_code == 1
    assert "must not overwrite ground truth" in result.output
    assert ground_truth.read_bytes() == original


def test_failed_atomic_replace_preserves_an_existing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ground_truth = _ground_truth(tmp_path / "ground-truth.jsonl")
    report = tmp_path / "report.json"
    report.write_bytes(b"accepted\n")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(workflow.os, "replace", fail_replace)
    result = CliRunner().invoke(
        workflow.create_cli(git_provenance_factory=lambda _path: GitProvenance("1" * 40, False)),
        [
            "evaluate",
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert "publication" in json.loads(result.output)["cause"]
    assert report.read_bytes() == b"accepted\n"
