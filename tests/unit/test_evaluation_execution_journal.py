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
    journal.append("execution", {"case_id": "q1", "status": "ok"})
    terminal = journal.seal({"case_count": 0})
    evidence = ExecutionEvidence(
        execution_id="exec-1",
        prediction_run_sha256=SHA,
        policy_sha256=SHA,
        executor=ExecutorProvenance("fake", "test", "1", True),
        journal_terminal_sha256=terminal,
        cases=(),
    )

    assert verify_sealed_journal(path) == terminal
    verify_execution_evidence_journal(evidence, path)

    payload = path.read_bytes()
    path.write_bytes(payload.replace(b'"q1"', b'"q2"'))
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
