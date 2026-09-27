"""Injected query-executor seam and credential-free scripted test implementation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from nl2sparql.evaluation.artifacts import canonical_json
from nl2sparql.evaluation.contracts import (
    DryRunEvidence,
    EvaluationError,
    ExecutionPolicy,
    ExecutorProvenance,
    QueryExecution,
)


@dataclass(frozen=True)
class QueryRequest:
    """One gold or predicted query with its result-order semantics."""

    case_id: str
    role: str
    sql: str
    order_sensitive: bool


class QueryExecutor(Protocol):
    """Minimal execution adapter required by guarded orchestration."""

    @property
    def provenance(self) -> ExecutorProvenance: ...

    def dry_run(self, request: QueryRequest, policy: ExecutionPolicy) -> DryRunEvidence: ...

    def execute(
        self,
        request: QueryRequest,
        policy: ExecutionPolicy,
        preflight: DryRunEvidence,
    ) -> QueryExecution: ...


class ExecutionJournal(Protocol):
    """Durable append boundary used before progressing to another query."""

    def append(self, record_type: str, body: Mapping[str, object]) -> None: ...

    def seal(self, body: Mapping[str, object]) -> str: ...


def deterministic_job_id(execution_id: str, request: QueryRequest) -> str:
    """Return the retry-stable BigQuery job ID for one execution slot."""
    payload = f"{execution_id}\0{request.case_id}\0{request.role}\0{request.sql}".encode()
    return f"nl2sql_eval_{hashlib.sha256(payload).hexdigest()[:40]}"


class ScriptedQueryExecutor:
    """Deterministic fake executor with per-case queues and observable call order."""

    def __init__(
        self,
        *,
        dry_runs: Mapping[tuple[str, str], list[DryRunEvidence | Exception]],
        executions: Mapping[tuple[str, str], QueryExecution | Exception],
    ) -> None:
        self.dry_runs = {key: list(values) for key, values in dry_runs.items()}
        self.executions = dict(executions)
        self.calls: list[str] = []
        self._journal: ExecutionJournal | None = None
        self._execution_id: str | None = None

    @property
    def provenance(self) -> ExecutorProvenance:
        return ExecutorProvenance("fake", "scripted-query-executor", "1", True)

    def dry_run(self, request: QueryRequest, policy: ExecutionPolicy) -> DryRunEvidence:
        del policy
        self.calls.append(f"dry:{request.case_id}:{request.role}")
        key = (request.case_id, request.role)
        try:
            outcome = self.dry_runs[key].pop(0)
        except (KeyError, IndexError) as exc:
            raise EvaluationError(f"missing scripted dry run for {key}") from exc
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def bind_execution_journal(self, journal: ExecutionJournal, *, execution_id: str) -> None:
        self._journal = journal
        self._execution_id = execution_id

    def execute(
        self,
        request: QueryRequest,
        policy: ExecutionPolicy,
        preflight: DryRunEvidence,
    ) -> QueryExecution:
        del policy
        self.calls.append(f"execute:{request.case_id}:{request.role}")
        key = (request.case_id, request.role)
        try:
            outcome = self.executions[key]
        except KeyError as exc:
            raise EvaluationError(f"missing scripted execution for {key}") from exc
        if isinstance(outcome, Exception):
            raise outcome
        if self._journal is None or self._execution_id is None:
            raise EvaluationError("scripted executor requires a bound execution journal")
        if outcome.submission_attempted:
            submitted_job_id = deterministic_job_id(self._execution_id, request)
            outcome = replace(
                outcome,
                job_id=submitted_job_id if outcome.job_id is not None else None,
                submission_job_id=submitted_job_id,
            )
            self._journal.append(
                "submission_intent",
                {
                    "case_id": request.case_id,
                    "role": request.role,
                    "request": request,
                    "job_id": submitted_job_id,
                    "preflight": preflight,
                },
            )
            self._journal.append(
                "submitted",
                {
                    "case_id": request.case_id,
                    "role": request.role,
                    "job_id": submitted_job_id,
                },
            )
        return outcome


class MemoryExecutionJournal:
    """In-memory hash-chain journal matching the durable journal record semantics."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []
        self.terminal_sha256: str | None = None

    def append(self, record_type: str, body: Mapping[str, object]) -> None:
        previous = str(self.records[-1]["record_sha256"]) if self.records else "0" * 64
        base = {
            "record_type": record_type,
            "body": dict(body),
            "previous_sha256": previous,
        }
        digest = hashlib.sha256(canonical_json(base)).hexdigest()
        self.records.append(base | {"record_sha256": digest})

    def seal(self, body: Mapping[str, object]) -> str:
        self.append("terminal_seal", body)
        self.terminal_sha256 = str(self.records[-1]["record_sha256"])
        return self.terminal_sha256
