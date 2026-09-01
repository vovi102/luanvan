from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.b0_rule_baseline_workflow as workflow
from nl2sparql.dataset.templates import TEMPLATES_PATH
from nl2sparql.linking.schema import SchemaIndexError
from nl2sparql.models.b0 import B0Prediction

SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


class _Baseline:
    def predict_detailed(self, question: str) -> B0Prediction | None:
        if question == "unmatched":
            return None
        return B0Prediction(
            sql=SQL,
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


def _synthetic_input(path: Path) -> Path:
    row = {
        "ambiguity_flag": False,
        "categories": ["entity_lookup"],
        "cq_ids": ["CQ07"],
        "difficulty": "easy",
        "evidence_sha256": None,
        "expected_result_size": None,
        "id": "Q001",
        "nl": "known exchange accounts",
        "pool_b_writer": "writer_1",
        "pool_c_reviewers": ["reviewer_1"],
        "schema_elements": ["entity_labels_v1.address"],
        "source": "author_1",
        "sql": SQL,
        "verified_at": None,
        "verified_executable": False,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def _factory(path: Path) -> _Baseline:
    assert path.is_file()
    return _Baseline()


def test_help_does_not_initialize_baseline() -> None:
    def forbidden(path: Path) -> _Baseline:
        raise AssertionError(f"help initialized baseline from {path}")

    result = CliRunner().invoke(workflow.create_cli(baseline_factory=forbidden), ["--help"])

    assert result.exit_code == 0
    assert "predict" in result.output
    assert "evaluate" in result.output


def test_invalid_question_fails_before_baseline_initialization() -> None:
    def forbidden(path: Path) -> _Baseline:
        raise AssertionError(f"invalid input initialized baseline from {path}")

    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=forbidden),
        ["predict", "--question", "   "],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "invalid_input"


def test_invalid_question_precedes_missing_template_evidence(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=_factory),
        [
            "predict",
            "--question",
            "   ",
            "--templates",
            str(tmp_path / "missing.json"),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "invalid_input"


def test_predict_emits_canonical_unmatched_result() -> None:
    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=_factory),
        ["predict", "--question", "unmatched"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "command": "predict",
        "question_sha256": hashlib.sha256(b"unmatched").hexdigest(),
        "status": "unmatched",
    }
    assert result.output == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def test_missing_test_set_is_structured_blocked(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=_factory),
        ["evaluate", "--test-set", str(tmp_path / "missing.jsonl")],
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["cause"] == "external_evidence_unavailable"


def test_evaluate_publishes_synthetic_not_ready_artifacts(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.jsonl"
    report = tmp_path / "report.json"
    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=_factory),
        [
            "evaluate",
            "--test-set",
            str(_synthetic_input(tmp_path / "cases.jsonl")),
            "--synthetic",
            "--predictions",
            str(predictions),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "not_ready"
    prediction = json.loads(predictions.read_text(encoding="utf-8"))
    assert prediction["case_id"] == "Q001"
    assert prediction["predicted_sql"] == SQL


def test_output_may_not_alias_input(tmp_path: Path) -> None:
    input_path = _synthetic_input(tmp_path / "cases.jsonl")
    original = input_path.read_bytes()

    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=_factory),
        [
            "evaluate",
            "--test-set",
            str(input_path),
            "--synthetic",
            "--report",
            str(input_path),
        ],
    )

    assert result.exit_code == 1
    assert input_path.read_bytes() == original


def test_output_may_not_alias_catalog_input(tmp_path: Path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text("accepted catalog", encoding="utf-8")
    monkeypatch.setattr(workflow, "CATALOG_PATH", catalog)

    result = CliRunner().invoke(
        workflow.create_cli(baseline_factory=_factory),
        [
            "evaluate",
            "--test-set",
            str(_synthetic_input(tmp_path / "cases.jsonl")),
            "--synthetic",
            "--report",
            str(catalog),
        ],
    )

    assert result.exit_code == 1
    assert catalog.read_text(encoding="utf-8") == "accepted catalog"


def test_stale_schema_index_is_classified_as_blocked(monkeypatch) -> None:
    def stale_index(*args, **kwargs):
        raise SchemaIndexError("stale schema cache")

    monkeypatch.setattr(workflow, "load_schema_index", stale_index)

    with pytest.raises(workflow.ExternalEvidenceUnavailableError, match="stale schema cache"):
        workflow._production_baseline(TEMPLATES_PATH)
