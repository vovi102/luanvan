from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nl2sparql.evaluation.bigquery import create_bigquery_executor
from nl2sparql.evaluation.contracts import (
    DryRunEvidence,
    EvaluationError,
    ExecutionPolicy,
    PricingPolicy,
)
from nl2sparql.evaluation.executor import MemoryExecutionJournal, QueryRequest

SHA = "a" * 64
NOW = datetime(2026, 9, 26, tzinfo=UTC)


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        project="test-project",
        location="EU",
        timeout_seconds=7.5,
        per_query_byte_cap=100_000_000,
        aggregate_byte_cap=200_000_000,
        estimated_cost_cap=Decimal("1"),
        pricing=PricingPolicy(
            "2026-09",
            "USD",
            Decimal("5"),
            SHA,
            minimum_billed_bytes=10 * 2**20,
            billing_increment_bytes=2**20,
        ),
    )


class _Field:
    def __init__(self, name: str, field_type: str, mode: str = "NULLABLE", fields=()) -> None:
        self.name = name
        self.field_type = field_type
        self.mode = mode
        self.fields = fields


class _Job:
    def __init__(
        self,
        *,
        job_id: str,
        processed: int | None,
        billed: int | None,
        rows=(),
        timeout: bool = False,
    ) -> None:
        self.job_id = job_id
        self.total_bytes_processed = processed
        self.total_bytes_billed = billed
        self.cache_hit = False
        self.schema = (
            _Field("value", "STRING"),
            _Field("metadata", "RECORD", fields=(_Field("count", "INT64"),)),
        )
        self._rows = rows
        self._timeout = timeout
        self.result_timeouts: list[float] = []
        self.cancel_calls = 0

    def result(self, *, timeout: float):
        self.result_timeouts.append(timeout)
        if self._timeout:
            raise TimeoutError("deadline")
        return self._rows

    def cancel(self) -> bool:
        self.cancel_calls += 1
        return True


class _Client:
    def __init__(self, jobs: list[_Job]) -> None:
        self.jobs = list(jobs)
        self.calls: list[tuple[str, object, str]] = []

    def query(self, sql: str, *, job_config: object, location: str, job_id: str | None = None):
        self.calls.append((sql, job_config, location))
        job = self.jobs.pop(0)
        if job_id is not None:
            job.job_id = job_id
        return job


def _executor(client: _Client):
    executor = create_bigquery_executor(
        _policy(), allow_bigquery=True, client_factory=lambda: client
    )
    journal = MemoryExecutionJournal()
    executor.bind_execution_journal(journal, execution_id="exec-1")  # type: ignore[attr-defined]
    return executor, journal


def test_factory_requires_explicit_opt_in_before_client_creation() -> None:
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        raise AssertionError("must not initialize credentials")

    with pytest.raises(EvaluationError, match="allow-bigquery"):
        create_bigquery_executor(_policy(), allow_bigquery=False, client_factory=factory)
    assert called is False


def test_factory_rejects_non_positive_live_pricing_before_client_creation() -> None:
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        raise AssertionError("must not initialize credentials")

    policy = _policy()
    policy = replace(
        policy,
        pricing=replace(policy.pricing, amount_per_tib=Decimal("0")),
    )
    with pytest.raises(EvaluationError, match="amount_per_tib"):
        create_bigquery_executor(policy, allow_bigquery=True, client_factory=factory)
    assert called is False


def test_dry_run_and_execution_capture_guarded_job_evidence() -> None:
    dry_job = _Job(job_id="dry-1", processed=1234, billed=None)
    live_job = _Job(
        job_id="live-1",
        processed=1234,
        billed=1,
        rows=[("alpha", {"count": 2})],
    )
    client = _Client([dry_job, live_job])
    executor, journal = _executor(client)
    request = QueryRequest("q1", "gold", "SELECT 'alpha'", False)

    preflight = executor.dry_run(request, _policy())
    outcome = executor.execute(request, _policy(), preflight)

    dry_config = client.calls[0][1]
    live_config = client.calls[1][1]
    assert dry_config.dry_run is True
    assert live_config.dry_run is False
    assert dry_config.use_legacy_sql is False
    assert dry_config.use_query_cache is False
    assert live_config.maximum_bytes_billed == _policy().per_query_byte_cap
    assert [call[2] for call in client.calls] == ["EU", "EU"]
    assert live_job.result_timeouts == [7.5]
    assert outcome.job_id is not None
    assert outcome.job_id.startswith("nl2sql_eval_")
    assert outcome.processed_bytes == 1234
    assert outcome.billed_bytes == 1
    assert outcome.cache_hit is False
    assert outcome.result is not None
    assert outcome.result.fields[1].fields[0].name == "count"
    assert outcome.cost.measurement_status == "estimated"
    expected = Decimal(10 * 2**20) / Decimal(2**40) * Decimal("5")
    assert outcome.cost.amount == expected
    assert [record["record_type"] for record in journal.records] == [
        "submission_intent",
        "submitted",
    ]
    assert journal.records[0]["body"]["job_id"] == outcome.job_id
    assert journal.records[1]["body"]["job_id"] == outcome.job_id


def test_execute_rejects_preflight_above_guard_without_submitting() -> None:
    client = _Client([])
    executor, _ = _executor(client)

    with pytest.raises(EvaluationError, match="preflight"):
        executor.execute(
            QueryRequest("q1", "gold", "SELECT 1", False),
            _policy(),
            DryRunEvidence(_policy().per_query_byte_cap + 1, NOW, True),
        )
    assert client.calls == []


def test_submission_request_error_remains_unresolved_and_journaled() -> None:
    client = _Client([])
    executor, journal = _executor(client)

    outcome = executor.execute(
        QueryRequest("q1", "gold", "SELECT 1", False),
        _policy(),
        DryRunEvidence(1, NOW, True),
    )

    assert outcome.status == "error"
    assert outcome.submission_attempted is True
    assert outcome.submission_acknowledged is False
    assert outcome.submission_job_id is not None
    assert outcome.billed_bytes is None
    assert outcome.cost.measurement_status == "unmeasured"
    assert [record["record_type"] for record in journal.records] == ["submission_intent"]


def test_timeout_requests_cancellation_without_inventing_zero_billing() -> None:
    timed_out = _Job(job_id="live-timeout", processed=None, billed=None, timeout=True)
    client = _Client([timed_out])
    executor, _ = _executor(client)

    outcome = executor.execute(
        QueryRequest("q1", "prediction", "SELECT 1", False),
        _policy(),
        DryRunEvidence(1, NOW, True),
    )

    assert outcome.status == "timeout"
    assert timed_out.cancel_calls == 1
    assert outcome.cancellation_status == "succeeded"
    assert outcome.billed_bytes is None
    assert outcome.cost.measurement_status == "unmeasured"
    assert outcome.cost.amount is None


def test_result_canonicalization_failure_preserves_submitted_job_billing() -> None:
    job = _Job(job_id="live-bad-result", processed=20, billed=10, rows=[("value",)])
    job.schema = (_Field("value", "INTERVAL"),)
    client = _Client([job])
    executor, _ = _executor(client)

    outcome = executor.execute(
        QueryRequest("q1", "gold", "SELECT 1", False),
        _policy(),
        DryRunEvidence(20, NOW, True),
    )

    assert outcome.status == "error"
    assert outcome.error_code == "EvaluationError"
    assert outcome.job_id is not None
    assert outcome.job_id.startswith("nl2sql_eval_")
    assert outcome.billed_bytes == 10
    assert outcome.cost.measurement_status == "estimated"
