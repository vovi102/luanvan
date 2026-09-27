from pathlib import Path

import pytest

from nl2sparql.evaluation.artifacts import (
    FileExecutionJournal,
    verify_execution_evidence_journal,
    verify_sealed_journal,
)
from nl2sparql.evaluation.contracts import EvaluationError, ExecutionEvidence, ExecutorProvenance

SHA = "a" * 64


def test_interrupted_journal_is_rejected_and_cannot_be_resumed(tmp_path: Path) -> None:
    path = tmp_path / "execution.jsonl"
    journal = FileExecutionJournal.create(
        path,
        header={"execution_id": "exec-1"},
        protected_paths=(),
    )
    journal.append("submitted", {"job_id": "job-1"})

    with pytest.raises(EvaluationError, match="unsealed"):
        verify_sealed_journal(path)
    with pytest.raises(EvaluationError, match="already exists"):
        FileExecutionJournal.create(path, header={}, protected_paths=())


def test_file_journal_fsync_seal_cross_hash_and_tamper_detection(tmp_path: Path) -> None:
    protected = tmp_path / "input.json"
    protected.write_text("input", encoding="utf-8")
    path = tmp_path / "execution.jsonl"
    journal = FileExecutionJournal.create(
        path,
        header={"execution_id": "exec-1"},
        protected_paths=(protected,),
    )
    provenance = ExecutorProvenance("fake", "test", "1", True)
    journal.append(
        "header",
        {
            "execution_id": "exec-1",
            "prediction_run_sha256": SHA,
            "policy_sha256": SHA,
            "executor": provenance,
        },
    )
    terminal = journal.seal({"case_count": 0})
    evidence = ExecutionEvidence(
        execution_id="exec-1",
        prediction_run_sha256=SHA,
        policy_sha256=SHA,
        executor=provenance,
        journal_terminal_sha256=terminal,
        cases=(),
        estimated_bytes_total=0,
    )

    assert verify_sealed_journal(path) == terminal
    verify_execution_evidence_journal(evidence, path)

    payload = path.read_bytes()
    path.write_bytes(payload.replace(b'"exec-1"', b'"exec-2"', 1))
    with pytest.raises(EvaluationError, match="digest mismatch"):
        verify_execution_evidence_journal(evidence, path)


def test_file_journal_rejects_protected_alias(tmp_path: Path) -> None:
    protected = tmp_path / "input.jsonl"
    protected.write_text("source", encoding="utf-8")

    with pytest.raises(EvaluationError, match="protected input"):
        FileExecutionJournal.create(
            protected,
            header={"execution_id": "exec-1"},
            protected_paths=(protected,),
        )


def test_execution_verifier_rejects_unknown_record_types(tmp_path: Path) -> None:
    path = tmp_path / "unknown-record.jsonl"
    journal = FileExecutionJournal.create(path, header={}, protected_paths=())
    provenance = ExecutorProvenance("fake", "test", "1", True)
    journal.append(
        "header",
        {
            "execution_id": "exec-1",
            "prediction_run_sha256": SHA,
            "policy_sha256": SHA,
            "executor": provenance,
        },
    )
    journal.append("unrecognized", {"value": 1})
    terminal = journal.seal({"case_count": 0})
    evidence = ExecutionEvidence(
        "exec-1",
        SHA,
        SHA,
        provenance,
        terminal,
        (),
        estimated_bytes_total=0,
    )

    with pytest.raises(EvaluationError, match="unknown record type"):
        verify_execution_evidence_journal(evidence, path)


def test_execution_verifier_rejects_creation_record_outside_prefix(tmp_path: Path) -> None:
    path = tmp_path / "misordered-record.jsonl"
    journal = FileExecutionJournal.create(path, header={}, protected_paths=())
    provenance = ExecutorProvenance("fake", "test", "1", True)
    journal.append(
        "header",
        {
            "execution_id": "exec-1",
            "prediction_run_sha256": SHA,
            "policy_sha256": SHA,
            "executor": provenance,
        },
    )
    journal.append("journal_created", {})
    terminal = journal.seal({"case_count": 0})
    evidence = ExecutionEvidence(
        "exec-1",
        SHA,
        SHA,
        provenance,
        terminal,
        (),
        estimated_bytes_total=0,
    )

    with pytest.raises(EvaluationError, match="creation record"):
        verify_execution_evidence_journal(evidence, path)
