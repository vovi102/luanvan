"""Tests for test-set scaffold, reports, and fail-closed publication."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from nl2sparql.dataset.testset.artifacts import (
    finalize_bundle,
    write_report,
    write_scaffold,
)
from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.validate import Bundle


def test_write_scaffold_creates_collaborator_headers_and_handoff_docs(tmp_path: Path) -> None:
    report = write_scaffold(tmp_path)

    assert report.created_count >= 6
    assert (
        (tmp_path / "raw_pool_a.csv")
        .read_text(encoding="utf-8")
        .startswith("question_id,author_id,nl")
    )
    assert (tmp_path / "PROCESS.md").exists()
    assert (tmp_path / "CONSENT.md").exists()


def test_write_scaffold_does_not_overwrite_nonempty_files_without_force(tmp_path: Path) -> None:
    write_scaffold(tmp_path)
    target = tmp_path / "raw_pool_a.csv"
    target.write_text("human submission\n", encoding="utf-8")

    with pytest.raises(TestSetError, match="overwrite"):
        write_scaffold(tmp_path)
    write_scaffold(tmp_path, force=True)
    assert target.read_text(encoding="utf-8").startswith("question_id,")


def test_write_report_adds_a_stable_digest(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    write_report({"status": "blocked", "reason": "missing credentials"}, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert len(payload["report_sha256"]) == 64


def test_finalize_bundle_rejects_missing_live_evidence(tmp_path: Path) -> None:
    with pytest.raises(TestSetError, match="evidence"):
        finalize_bundle(
            Bundle(pool_a=(), pool_b=(), reviews=(), selections=()),
            None,
            tmp_path / "final_selection.csv",
            tmp_path / "test-100.jsonl",
        )


def test_cli_help_is_available_without_credentials() -> None:
    path = Path("scripts/test_set_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("test_set_workflow", path)
    assert spec and spec.loader
    test_set_workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_set_workflow)

    result = CliRunner().invoke(test_set_workflow.main, ["--help"])

    assert result.exit_code == 0
    assert "verify-live" in result.output
