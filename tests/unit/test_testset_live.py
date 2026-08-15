"""Tests for bounded GoogleSQL safety and live evidence collection."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import (
    FinalCase,
    PoolARecord,
    PoolBRecord,
    ReviewRecord,
    SelectionRecord,
    TestSetError,
)
from nl2sparql.dataset.testset.live import (
    SqlPolicy,
    validate_sql_text,
    verify_sql,
)
from nl2sparql.dataset.testset.validate import Bundle

SAFE_SQL = (
    "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transactions` LIMIT 1"
)


def _case(sql: str = SAFE_SQL, *, expected_empty: bool = False) -> FinalCase:
    return FinalCase(
        id="q-001",
        source="author_01",
        nl="Find one transaction",
        sql=sql,
        difficulty="easy",
        categories=("simple_filter",),
        schema_elements=("transactions.transaction_hash",),
        cq_ids=("CQ01",),
        expected_result_size=None if expected_empty else 1,
        expected_columns=("transaction_hash",),
        ambiguity_flag=False,
        pool_b_writer="writer_01",
        pool_c_reviewers=("reviewer_01",),
        verified_executable=False,
        verified_at=None,
        evidence_sha256=None,
    )


@dataclass
class FakeField:
    name: str


class FakeRows(list):
    schema = [FakeField("transaction_hash")]


class FakeJob:
    def __init__(self, *, dry_run: bool, bytes_processed: int = 100, rows: list | None = None):
        self.total_bytes_processed = bytes_processed
        self.total_bytes_billed = bytes_processed
        self.cache_hit = False
        self.job_id = f"job-{dry_run}"
        self._rows = FakeRows([{"transaction_hash": "0xabc"}] if rows is None else rows)

    def result(self) -> FakeRows:
        return self._rows


class FakeClient:
    def __init__(self, *, bytes_processed: int = 100, rows: list | None = None):
        self.calls: list[object] = []
        self.bytes_processed = bytes_processed
        self.rows = rows

    def query(self, sql: str, *, job_config: object, location: str) -> FakeJob:
        self.calls.append((sql, job_config, location))
        return FakeJob(
            dry_run=bool(getattr(job_config, "dry_run", False)),
            bytes_processed=self.bytes_processed,
            rows=self.rows,
        )


def test_validate_sql_text_rejects_mutation_comments_wildcards_and_unmanaged_objects() -> None:
    for sql in (
        "DROP TABLE `nl2sparql-thesis.nl2sparql_analytics.transactions`",
        "SELECT * FROM `nl2sparql-thesis.nl2sparql_analytics.transactions`",
        "SELECT 1 -- hidden mutation",
        "SELECT 1; SELECT 2",
        "SELECT transaction_hash FROM `other-project.dataset.transactions`",
    ):
        with pytest.raises(TestSetError):
            validate_sql_text(sql)


def test_verify_sql_preflights_twice_and_disables_query_cache() -> None:
    client = FakeClient()

    evidence = verify_sql(client, (_case(),), SqlPolicy())

    assert len(client.calls) == 3
    assert all(call[1].use_query_cache is False for call in client.calls)
    assert all(call[1].maximum_bytes_billed == 20 * 2**30 for call in client.calls)
    assert evidence.records[0].row_count == 1
    assert evidence.records[0].sql_sha256


def test_verify_sql_rejects_aggregate_budget_before_execution() -> None:
    client = FakeClient(bytes_processed=100)
    policy = SqlPolicy(total_bytes=50)

    with pytest.raises(TestSetError, match="aggregate"):
        verify_sql(client, (_case(),), policy)
    assert len(client.calls) == 1


def test_verify_sql_rejects_empty_result_when_not_explicitly_expected() -> None:
    client = FakeClient(rows=[])

    with pytest.raises(TestSetError, match="non-empty"):
        verify_sql(client, (_case(),), SqlPolicy())


def test_verify_sql_accepts_empty_result_when_explicitly_expected() -> None:
    client = FakeClient(rows=[])

    evidence = verify_sql(client, (_case(expected_empty=True),), SqlPolicy())

    assert evidence.records[0].row_count == 0


def test_cli_case_builder_preserves_pool_b_expected_empty_policy() -> None:
    path = Path("scripts/test_set_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("test_set_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bundle = Bundle(
        pool_a=(PoolARecord("q-001", "author_01", "Find no transaction", "researcher", "batch-1"),),
        pool_b=(PoolBRecord("q-001", "writer_01", SAFE_SQL, True, False),),
        reviews=(ReviewRecord("q-001", "reviewer_01", 4, 4, "easy", "ACCEPT"),),
        selections=(
            SelectionRecord("q-001", "easy", ("simple_filter",), "accepted", ("named_entity",)),
        ),
    )

    case = module._cases_from_bundle(bundle)[0]

    assert case.expected_result_size is None
