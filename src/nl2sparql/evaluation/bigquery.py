"""Lazy, guarded BigQuery query-execution adapter."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from nl2sparql.evaluation.contracts import (
    CostEvidence,
    DryRunEvidence,
    EvaluationError,
    ExecutionPolicy,
    ExecutorProvenance,
    QueryExecution,
    ResultField,
)
from nl2sparql.evaluation.executor import QueryExecutor, QueryRequest
from nl2sparql.evaluation.result_semantics import canonicalize_result


def _non_negative_stat(job: object, name: str) -> int | None:
    value = getattr(job, name, None)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationError(f"BigQuery {name} must be a non-negative integer")
    return value


def _result_field(field: object) -> ResultField:
    try:
        name = str(field.name)
        type_name = str(field.field_type)
        mode = str(getattr(field, "mode", "NULLABLE"))
        nested = tuple(_result_field(item) for item in getattr(field, "fields", ()))
    except (TypeError, ValueError) as exc:
        raise EvaluationError("invalid BigQuery result schema") from exc
    return ResultField(name, type_name, mode, nested)


def _estimated_cost(billed_bytes: int | None, policy: ExecutionPolicy) -> CostEvidence:
    if billed_bytes is None:
        return CostEvidence("unmeasured", None, None, None)
    amount = policy.pricing.estimate_cost(billed_bytes)
    return CostEvidence(
        "estimated",
        amount,
        policy.pricing.currency,
        f"pricing-policy:{policy.pricing.policy_id}",
    )


class BigQueryExecutor:
    """Adapter over an injected BigQuery client; construction is factory-controlled."""

    def __init__(
        self,
        *,
        client: object,
        query_job_config: Callable[..., object],
        policy: ExecutionPolicy,
        library_version: str,
    ) -> None:
        self._client = client
        self._query_job_config = query_job_config
        self._policy = policy
        self._provenance = ExecutorProvenance(
            "bigquery",
            f"{policy.project}:{policy.location}",
            library_version,
            False,
        )

    @property
    def provenance(self) -> ExecutorProvenance:
        return self._provenance

    @staticmethod
    def _validate_policy(policy: ExecutionPolicy) -> None:
        if policy.per_query_byte_cap <= 0 or policy.aggregate_byte_cap <= 0:
            raise EvaluationError("BigQuery byte caps must be positive")
        if policy.estimated_cost_cap <= Decimal(0):
            raise EvaluationError("BigQuery estimated cost cap must be positive")

    def _config(self, *, dry_run: bool, policy: ExecutionPolicy) -> object:
        return self._query_job_config(
            dry_run=dry_run,
            use_legacy_sql=False,
            use_query_cache=False,
            maximum_bytes_billed=policy.per_query_byte_cap,
        )

    def dry_run(self, request: QueryRequest, policy: ExecutionPolicy) -> DryRunEvidence:
        self._validate_policy(policy)
        job = self._client.query(  # type: ignore[attr-defined]
            request.sql,
            job_config=self._config(dry_run=True, policy=policy),
            location=policy.location,
        )
        processed = _non_negative_stat(job, "total_bytes_processed")
        if processed is None:
            raise EvaluationError("BigQuery dry-run did not provide total_bytes_processed")
        return DryRunEvidence(processed, datetime.now(UTC), True)

    def execute(
        self,
        request: QueryRequest,
        policy: ExecutionPolicy,
        preflight: DryRunEvidence,
    ) -> QueryExecution:
        self._validate_policy(policy)
        if preflight.estimated_bytes > policy.per_query_byte_cap:
            raise EvaluationError("preflight exceeds per-query byte cap")
        if policy.pricing.estimate_cost(preflight.estimated_bytes) > policy.estimated_cost_cap:
            raise EvaluationError("preflight exceeds estimated cost cap")

        started = time.monotonic()
        job = self._client.query(  # type: ignore[attr-defined]
            request.sql,
            job_config=self._config(dry_run=False, policy=policy),
            location=policy.location,
        )
        job_id = getattr(job, "job_id", None)
        try:
            rows = job.result(timeout=policy.timeout_seconds)
        except TimeoutError:
            try:
                cancelled = job.cancel()
            except Exception:
                cancellation_status = "unknown"
            else:
                cancellation_status = "succeeded" if cancelled else "failed"
            billed = _non_negative_stat(job, "total_bytes_billed")
            return QueryExecution(
                status="timeout",
                job_id=str(job_id) if job_id is not None else None,
                latency_ms=(time.monotonic() - started) * 1000,
                billed_bytes=billed,
                cost=_estimated_cost(billed, policy),
                result=None,
                error_code="bigquery_timeout",
                processed_bytes=_non_negative_stat(job, "total_bytes_processed"),
                cache_hit=getattr(job, "cache_hit", None),
                cancellation_status=cancellation_status,
            )
        except Exception as exc:
            billed = _non_negative_stat(job, "total_bytes_billed")
            return QueryExecution(
                status="error",
                job_id=str(job_id) if job_id is not None else None,
                latency_ms=(time.monotonic() - started) * 1000,
                billed_bytes=billed,
                cost=_estimated_cost(billed, policy),
                result=None,
                error_code=type(exc).__name__,
                processed_bytes=_non_negative_stat(job, "total_bytes_processed"),
                cache_hit=getattr(job, "cache_hit", None),
            )

        billed = _non_negative_stat(job, "total_bytes_billed")
        processed = _non_negative_stat(job, "total_bytes_processed")
        schema_source = getattr(rows, "schema", None) or getattr(job, "schema", ())
        schema = tuple(_result_field(field) for field in schema_source)
        result = canonicalize_result(rows, schema, order_sensitive=request.order_sensitive)
        status = "ok" if billed is not None else "unresolved_cost"
        return QueryExecution(
            status=status,
            job_id=str(job_id) if job_id is not None else None,
            latency_ms=(time.monotonic() - started) * 1000,
            billed_bytes=billed,
            cost=_estimated_cost(billed, policy),
            result=result,
            error_code=None if status == "ok" else "unresolved_billing",
            processed_bytes=processed,
            cache_hit=getattr(job, "cache_hit", None),
        )


def create_bigquery_executor(
    policy: ExecutionPolicy,
    *,
    allow_bigquery: bool,
    client_factory: Callable[[], object] | None = None,
) -> QueryExecutor:
    """Validate all guards before importing BigQuery or constructing credentials."""
    if not allow_bigquery:
        raise EvaluationError("BigQuery execution requires explicit --allow-bigquery")
    if not isinstance(policy, ExecutionPolicy):
        raise EvaluationError("a complete execution policy is required")
    BigQueryExecutor._validate_policy(policy)

    from google.cloud import bigquery  # imported only on the explicit live path

    factory = client_factory or (lambda: bigquery.Client(project=policy.project))
    client = factory()
    return BigQueryExecutor(
        client=client,
        query_job_config=bigquery.QueryJobConfig,
        policy=policy,
        library_version=getattr(bigquery, "__version__", "unknown"),
    )
