"""CLI tests for the offline-first reviewed T3.5 workflow."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import google.auth
import pytest
from click.testing import CliRunner

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.reviewed_artifacts import LIMITATIONS
from nl2sparql.dataset.testset.reviewed_contracts import AGENT_REVIEWED_PROFILE
from nl2sparql.dataset.testset.reviewed_validate import (
    CandidatePackReport,
    LeakageSource,
)


def _workflow():
    path = Path("scripts/test_set_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("reviewed_test_set_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def offline_workflow(monkeypatch: pytest.MonkeyPatch):
    module = _workflow()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline command touched cloud credentials or BigQuery")

    monkeypatch.setattr(google.auth, "default", forbidden)
    monkeypatch.setattr(module.bigquery, "Client", forbidden)
    return module


def _roots(tmp_path: Path) -> list[str]:
    return [
        "--draft-root",
        str(tmp_path / "draft"),
        "--final-root",
        str(tmp_path / "final"),
    ]


def _candidate_report(tmp_path: Path) -> CandidatePackReport:
    return CandidatePackReport(
        status="draft_ready",
        provenance_profile=AGENT_REVIEWED_PROFILE,
        candidate_count=120,
        difficulty_counts=(("easy", 36), ("hard", 24), ("medium", 60)),
        category_count=6,
        entity_kind_count=3,
        candidate_sha256="a" * 64,
        catalog_sha256="b" * 64,
        leakage_sources=(LeakageSource(tmp_path / "leakage.jsonl", "c" * 64, 2),),
        source_commit="d" * 40,
    )


def test_help_exposes_reviewed_subgroup_without_credentials(offline_workflow) -> None:
    result = CliRunner().invoke(offline_workflow.main, ["--help"])

    assert result.exit_code == 0
    assert "reviewed" in result.output
    reviewed = CliRunner().invoke(offline_workflow.main, ["reviewed", "--help"])
    assert reviewed.exit_code == 0
    for command in (
        "scaffold",
        "validate-candidates",
        "validate-review",
        "verify-live",
        "finalize",
    ):
        assert command in reviewed.output


def test_scaffold_creates_only_human_headers_and_guide(tmp_path: Path, offline_workflow) -> None:
    result = CliRunner().invoke(offline_workflow.main, ["reviewed", "scaffold", *_roots(tmp_path)])

    assert result.exit_code == 0, result.output
    draft = tmp_path / "draft"
    assert (draft / "review_events.csv").read_text(encoding="utf-8").count("\n") == 1
    assert (draft / "final_selection.csv").read_text(encoding="utf-8").count("\n") == 1
    assert (draft / "REVIEW_GUIDE.md").is_file()
    assert not (draft / "candidates.jsonl").exists()


def test_validate_candidates_writes_draft_ready_manifest_and_report(
    tmp_path: Path, offline_workflow, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = tmp_path / "draft"
    draft.mkdir()
    (draft / "candidates.jsonl").write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        offline_workflow,
        "validate_candidate_pack",
        lambda *_args, **_kwargs: _candidate_report(tmp_path),
    )

    result = CliRunner().invoke(
        offline_workflow.main,
        ["reviewed", "validate-candidates", *_roots(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["status"] == "draft_ready"
    report = offline_workflow.read_report(draft / "validation-report.json")
    manifest = offline_workflow.read_report(draft / "manifest.json")
    for artifact in (report, manifest):
        assert artifact["status"] == "draft_ready"
        assert artifact["provenance_profile"] == AGENT_REVIEWED_PROFILE
        assert artifact["candidate_sha256"] == "a" * 64
        assert artifact["catalog_sha256"] == "b" * 64
        assert artifact["source_commit"] == "d" * 40
        assert artifact["limitations"] == list(LIMITATIONS)
        assert artifact["leakage_sources"][0]["sha256"] == "c" * 64


def test_validate_candidates_check_only_writes_nothing(
    tmp_path: Path, offline_workflow, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = tmp_path / "draft"
    draft.mkdir()
    (draft / "candidates.jsonl").write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        offline_workflow,
        "validate_candidate_pack",
        lambda *_args, **_kwargs: _candidate_report(tmp_path),
    )

    result = CliRunner().invoke(
        offline_workflow.main,
        ["reviewed", "validate-candidates", "--check-only", *_roots(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert not (draft / "validation-report.json").exists()
    assert not (draft / "manifest.json").exists()


def test_validate_review_reports_missing_human_decisions_as_blocked(
    tmp_path: Path, offline_workflow, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = tmp_path / "draft"
    draft.mkdir()
    candidate = draft / "candidates.jsonl"
    candidate.write_bytes(b"candidate-source")
    before = candidate.read_bytes()
    monkeypatch.setattr(
        offline_workflow,
        "load_reviewed_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TestSetError("every candidate requires at least one human review event")
        ),
    )

    result = CliRunner().invoke(
        offline_workflow.main,
        ["reviewed", "validate-review", *_roots(tmp_path)],
    )

    assert result.exit_code != 0
    report = offline_workflow.read_report(draft / "validation-report.json")
    assert report["status"] == "blocked"
    assert "human review" in report["reason"]
    assert candidate.read_bytes() == before


def test_finalize_without_live_evidence_is_blocked(tmp_path: Path, offline_workflow) -> None:
    result = CliRunner().invoke(
        offline_workflow.main,
        ["reviewed", "finalize", *_roots(tmp_path)],
    )

    assert result.exit_code != 0
    report = offline_workflow.read_report(tmp_path / "draft" / "validation-report.json")
    assert report["status"] == "blocked"
    assert "live" in report["reason"].casefold()
    assert not (tmp_path / "final" / "test-100.jsonl").exists()


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--allow-bigquery",),
        ("--project", "test-project"),
    ),
)
def test_verify_live_requires_opt_in_and_explicit_project_before_client(
    tmp_path: Path, offline_workflow, arguments: tuple[str, ...]
) -> None:
    result = CliRunner().invoke(
        offline_workflow.main,
        ["reviewed", "verify-live", *arguments, *_roots(tmp_path)],
    )

    assert result.exit_code != 0


def test_verify_live_validates_review_bundle_before_creating_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _workflow()
    touched = False

    def forbidden_client(*_args, **_kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("client created before review validation")

    monkeypatch.setattr(module.bigquery, "Client", forbidden_client)
    monkeypatch.setattr(
        module,
        "load_reviewed_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TestSetError("human review incomplete")),
    )

    result = CliRunner().invoke(
        module.main,
        [
            "reviewed",
            "verify-live",
            "--allow-bigquery",
            "--project",
            "test-project",
            *_roots(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert touched is False
    report = module.read_report(tmp_path / "draft" / "validation-report.json")
    assert report["status"] == "blocked"
