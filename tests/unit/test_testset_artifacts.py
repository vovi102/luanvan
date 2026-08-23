"""Tests for test-set scaffold, reports, and fail-closed publication."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner
from google.api_core.exceptions import BadRequest, ServiceUnavailable

from nl2sparql.dataset.testset import artifacts as artifacts_module
from nl2sparql.dataset.testset.artifacts import (
    finalize_bundle,
    read_report,
    write_report,
    write_scaffold,
)
from nl2sparql.dataset.testset.contracts import (
    PoolARecord,
    PoolBRecord,
    ReviewRecord,
    SelectionRecord,
    TestSetError,
)
from nl2sparql.dataset.testset.live import (
    LiveEvidence,
    LiveEvidenceRecord,
    evidence_input_sha256,
)
from nl2sparql.dataset.testset.validate import Bundle

SAFE_SQL = (
    "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
    "(DATE '2026-06-01', DATE '2026-06-02') LIMIT 1"
)


def _final_bundle(tmp_path: Path) -> tuple[Bundle, LiveEvidence, Path]:
    pool_a = tuple(
        PoolARecord(
            f"q-{index:03d}",
            f"author_{index % 3}",
            f"Find transaction {index}",
            "researcher",
            "batch-1",
        )
        for index in range(105)
    )
    pool_b = tuple(
        PoolBRecord(
            row.question_id,
            "writer_01",
            SAFE_SQL,
            ("transaction_hash",),
            False,
            False,
        )
        for row in pool_a
    )
    reviews = tuple(
        ReviewRecord(
            row.question_id,
            "reviewer_01",
            4,
            4,
            "easy",
            "REVISE" if index < 5 else "ACCEPT",
        )
        for index, row in enumerate(pool_a)
    ) + tuple(
        ReviewRecord(
            row.question_id,
            "reviewer_02",
            4,
            4,
            "easy",
            "REVISE" if index < 5 else "ACCEPT",
        )
        for index, row in enumerate(pool_a[:30])
    )
    difficulties = ("easy",) * 30 + ("medium",) * 50 + ("hard",) * 20
    selections = tuple(
        SelectionRecord(
            row.question_id,
            difficulty,
            (
                "simple_filter",
                "entity_lookup",
                "time_range",
                "top_k",
                "transaction_aggregation",
                "multi_hop",
            ),
            "accepted",
            ("named_entity", "address_only", "concept_class"),
            ("transaction_facts", "transaction_facts.transaction_hash"),
            ("CQ01",),
        )
        for row, difficulty in zip(pool_a[5:], difficulties, strict=True)
    )
    selection_path = tmp_path / "final_selection.csv"
    lines = [
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,selection_note"
    ]
    lines.extend(
        f"{row.question_id},{row.final_difficulty},{'|'.join(row.categories)},"
        f"{'|'.join(row.entity_kinds)},{'|'.join(row.schema_elements)},"
        f"{'|'.join(row.cq_ids)},{row.selection_note}"
        for row in selections
    )
    selection_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sql_hash = hashlib.sha256(SAFE_SQL.encode()).hexdigest()
    records = tuple(
        LiveEvidenceRecord(
            question_id=row.question_id,
            sql_sha256=sql_hash,
            row_count=1,
            columns=("transaction_hash",),
            processed_bytes=1,
            billed_bytes=1,
            cache_hit=False,
            job_id=f"job-{row.question_id}",
            wall_latency_ms=1.0,
        )
        for row in selections
    )
    evidence = LiveEvidence(
        status="ready",
        generated_at="2026-08-15T00:00:00Z",
        records=records,
        total_processed_bytes=100,
        total_billed_bytes=100,
        input_sha256=evidence_input_sha256(
            (record.question_id, record.sql_sha256) for record in records
        ),
    )
    return Bundle(pool_a, pool_b, reviews, selections), evidence, selection_path


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
    source = tmp_path / "input.csv"
    source.write_text("id\nq-001\n", encoding="utf-8")
    path = tmp_path / "report.json"
    write_report(
        {"status": "blocked", "reason": "missing credentials"},
        path,
        input_paths=(source,),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["schema_version"] == 1
    assert len(payload["git_commit"]) == 40
    assert payload["git_commit"] == payload["git_commit"].lower()
    assert isinstance(payload["git_worktree_dirty"], bool)
    assert payload["generated_at"].endswith("Z")
    assert len(payload["input_digests"][str(source)]) == 64
    assert payload["policy_caps"]["per_query_bytes"] == 20 * 2**30
    assert len(payload["report_sha256"]) == 64

    payload["reason"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TestSetError, match="digest mismatch"):
        read_report(path)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("categories", "simple_filter||time_range"),
        ("entity_kinds", "named_entity||address_only"),
        ("schema_elements", "transaction_facts||transaction_facts.transaction_hash"),
        ("cq_ids", "CQ01||CQ02"),
    ),
)
def test_finalization_parser_rejects_empty_pipe_delimited_selection_tokens(
    tmp_path: Path, field: str, value: str
) -> None:
    selection = {
        "categories": "simple_filter|time_range",
        "entity_kinds": "named_entity|address_only",
        "schema_elements": "transaction_facts|transaction_facts.transaction_hash",
        "cq_ids": "CQ01|CQ02",
    }
    selection[field] = value
    path = tmp_path / "final_selection.csv"
    path.write_text(
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,"
        "selection_note\n"
        f"q-001,easy,{selection['categories']},{selection['entity_kinds']},"
        f"{selection['schema_elements']},{selection['cq_ids']},accepted\n",
        encoding="utf-8",
    )

    with pytest.raises(TestSetError, match="empty"):
        artifacts_module._selection_rows(path)


def test_write_report_rejects_ready_status_without_full_git_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(b"accepted report\n")
    monkeypatch.setattr(artifacts_module, "_git_provenance", lambda: ("unknown", False))

    with pytest.raises(TestSetError, match="git commit"):
        write_report({"status": "ready"}, path)

    assert path.read_bytes() == b"accepted report\n"


def test_write_report_records_dirty_worktree_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "report.json"
    monkeypatch.setattr(artifacts_module, "_git_provenance", lambda: ("a" * 40, True))

    write_report({"status": "ready"}, path)

    assert read_report(path)["git_worktree_dirty"] is True


def test_finalize_bundle_rejects_missing_live_evidence(tmp_path: Path) -> None:
    with pytest.raises(TestSetError, match="evidence"):
        finalize_bundle(
            Bundle(pool_a=(), pool_b=(), reviews=(), selections=()),
            None,
            tmp_path / "final_selection.csv",
            tmp_path / "test-100.jsonl",
        )


def test_finalize_bundle_rejects_nonready_live_evidence(tmp_path: Path) -> None:
    selection = tmp_path / "final_selection.csv"
    selection.write_text(
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,"
        "selection_note\n",
        encoding="utf-8",
    )
    evidence = LiveEvidence(
        status="blocked",
        generated_at="2026-08-15T00:00:00Z",
        records=(),
        total_processed_bytes=0,
        total_billed_bytes=0,
        input_sha256="0" * 64,
    )

    with pytest.raises(TestSetError, match="ready"):
        finalize_bundle(
            Bundle(pool_a=(), pool_b=(), reviews=(), selections=()),
            evidence,
            selection,
            tmp_path / "test-100.jsonl",
        )


def test_finalize_bundle_publishes_only_exact_policy_compliant_evidence(tmp_path: Path) -> None:
    bundle, evidence, selection_path = _final_bundle(tmp_path)
    output = tmp_path / "test-100.jsonl"

    report = finalize_bundle(bundle, evidence, selection_path, output)
    first_payload = output.read_bytes()
    second_report = finalize_bundle(bundle, evidence, selection_path, output)

    assert report.status == "ready"
    assert report.record_count == 100
    assert second_report.output_sha256 == report.output_sha256
    assert output.read_bytes() == first_payload
    first = json.loads(first_payload.splitlines()[0])
    assert first["schema_elements"] == [
        "transaction_facts",
        "transaction_facts.transaction_hash",
    ]
    assert first["cq_ids"] == ["CQ01"]

    cache_tampered = replace(
        evidence,
        records=(replace(evidence.records[0], cache_hit=True), *evidence.records[1:]),
    )
    with pytest.raises(TestSetError, match="execution policy"):
        finalize_bundle(bundle, cache_tampered, selection_path, output)

    columns_tampered = replace(
        evidence,
        records=(
            replace(evidence.records[0], columns=("wrong_column",)),
            *evidence.records[1:],
        ),
    )
    with pytest.raises(TestSetError, match="columns"):
        finalize_bundle(bundle, columns_tampered, selection_path, output)


def test_cli_help_is_available_without_credentials() -> None:
    path = Path("scripts/test_set_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("test_set_workflow", path)
    assert spec and spec.loader
    test_set_workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_set_workflow)

    result = CliRunner().invoke(test_set_workflow.main, ["--help"])

    assert result.exit_code == 0
    assert "verify-live" in result.output


def test_cli_validate_writes_structured_blocked_report_for_missing_inputs(tmp_path: Path) -> None:
    path = Path("scripts/test_set_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("test_set_workflow", path)
    assert spec and spec.loader
    test_set_workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_set_workflow)

    result = CliRunner().invoke(test_set_workflow.main, ["validate", "--root", str(tmp_path)])

    assert result.exit_code != 0
    report = json.loads((tmp_path / "validation-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert report["command"] == "validate"


@pytest.mark.parametrize(
    ("error", "expected_status"),
    (
        (BadRequest("invalid GoogleSQL"), "failed"),
        (ServiceUnavailable("BigQuery unavailable"), "blocked"),
    ),
)
def test_cli_verify_live_classifies_deterministic_and_transient_bigquery_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: str,
) -> None:
    path = Path("scripts/test_set_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("test_set_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_require_inputs", lambda paths: None)
    monkeypatch.setattr(module, "load_bundle", lambda paths: object())
    monkeypatch.setattr(module, "validate_bundle", lambda bundle: None)
    monkeypatch.setattr(module, "validate_selection", lambda bundle: None)
    monkeypatch.setattr(module, "_cases_from_bundle", lambda bundle: ())
    monkeypatch.setattr(module.bigquery, "Client", lambda project: object())

    def fail_verify(client, cases):
        raise error

    monkeypatch.setattr(module, "verify_sql", fail_verify)

    result = CliRunner().invoke(module.main, ["verify-live", "--root", str(tmp_path)])

    assert result.exit_code != 0
    report = json.loads((tmp_path / "live-evidence.json").read_text(encoding="utf-8"))
    assert report["status"] == expected_status
    assert report["command"] == "verify-live"
