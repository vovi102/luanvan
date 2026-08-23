"""Tests for bounded GoogleSQL safety and live evidence collection."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, replace
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
    MAX_RESULT_PREVIEW_ROWS,
    SqlPolicy,
    validate_sql_text,
    verify_sql,
)
from nl2sparql.dataset.testset.validate import Bundle

SAFE_SQL = (
    "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
    "(DATE '2026-06-01', DATE '2026-06-02') LIMIT 1"
)


def _case(
    sql: str = SAFE_SQL,
    *,
    expected_empty: bool = False,
    question_id: str = "q-001",
) -> FinalCase:
    return FinalCase(
        id=question_id,
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
    def __init__(
        self,
        *,
        dry_run: bool,
        bytes_processed: int = 100,
        rows: list | object | None = None,
    ):
        self.total_bytes_processed = bytes_processed
        self.total_bytes_billed = bytes_processed
        self.cache_hit = False
        self.job_id = f"job-{dry_run}"
        if rows is None:
            self._rows = FakeRows([{"transaction_hash": "0xabc"}])
        elif isinstance(rows, list):
            self._rows = FakeRows(rows)
        else:
            self._rows = rows

    def result(self) -> object:
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


class SequencedClient:
    def __init__(self, estimates: list[int]):
        self.estimates = iter(estimates)
        self.calls: list[bool] = []

    def query(self, sql: str, *, job_config: object, location: str) -> FakeJob:
        dry_run = bool(getattr(job_config, "dry_run", False))
        self.calls.append(dry_run)
        return FakeJob(dry_run=dry_run, bytes_processed=next(self.estimates))


class CountingRows:
    schema = [FakeField("transaction_hash")]
    total_rows = 10_000

    def __init__(self) -> None:
        self.consumed = 0

    def __iter__(self):
        while True:
            self.consumed += 1
            if self.consumed > MAX_RESULT_PREVIEW_ROWS:
                raise AssertionError("result preview was not bounded")
            yield {"transaction_hash": f"0x{self.consumed:x}"}


def test_validate_sql_text_rejects_mutation_comments_wildcards_and_unmanaged_objects() -> None:
    for sql in (
        "DROP TABLE `nl2sparql-thesis.nl2sparql_analytics.transactions`",
        "SELECT * FROM `nl2sparql-thesis.nl2sparql_analytics.transactions`",
        "SELECT DISTINCT * FROM `nl2sparql-thesis.nl2sparql_analytics.transactions`",
        "SELECT t.* FROM `nl2sparql-thesis.nl2sparql_analytics.transactions` AS t",
        (
            "SELECT project.dataset.transactions.* "
            "FROM `nl2sparql-thesis.nl2sparql_analytics.transactions`"
        ),
        "SELECT 1 -- hidden mutation",
        "SELECT 1 # hidden mutation",
        "SELECT 1; SELECT 2",
        "SELECT transaction_hash FROM `other-project.dataset.transactions`",
        "SELECT transaction_hash FROM other_project.dataset.transactions",
        (
            "SELECT t.transaction_hash "
            "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
            "(DATE '2026-06-01', DATE '2026-06-02') AS t "
            "JOIN other_project.dataset.transactions AS external "
            "ON external.hash = t.transaction_hash"
        ),
        (
            "SELECT t.transaction_hash "
            "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
            "(DATE '2026-06-01', DATE '2026-06-02') AS t "
            "JOIN other_project.dataset.external_function() AS external "
            "ON external.hash = t.transaction_hash"
        ),
    ):
        with pytest.raises(TestSetError):
            validate_sql_text(sql)


@pytest.mark.parametrize(
    "managed_object",
    (
        "transaction_facts",
        "block_facts",
        "token_transfer_facts",
        "contract_dimension",
        "token_dimension",
        "entity_labels_v1",
        "labeled_transactions",
        "labeled_token_transfers",
    ),
)
def test_validate_sql_text_accepts_every_managed_relation_and_table_function(
    managed_object: str,
) -> None:
    suffix = (
        "(DATE '2026-06-01', DATE '2026-06-02')"
        if managed_object
        in {
            "transaction_facts",
            "block_facts",
            "token_transfer_facts",
            "labeled_transactions",
            "labeled_token_transfers",
        }
        else ""
    )
    if managed_object == "contract_dimension":
        suffix = "(DATE '2026-06-02')"
    sql = (
        "SELECT source.value "
        f"FROM `nl2sparql-thesis.nl2sparql_analytics.{managed_object}`{suffix} AS source"
    )

    validate_sql_text(sql)


def test_validate_sql_text_rejects_unmanaged_relation_producing_udtf() -> None:
    sql = (
        "SELECT source.transaction_hash, external.value "
        "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
        "(DATE '2026-06-01', DATE '2026-06-02') AS source "
        "CROSS JOIN UNNEST([STRUCT(1 AS value)]) AS external"
    )

    with pytest.raises(TestSetError, match="managed analytical"):
        validate_sql_text(sql)


def test_validate_sql_text_uses_ast_for_ctes_and_ignores_relation_text_in_strings() -> None:
    sql = """
    WITH managed AS (
      SELECT transaction_hash
      FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(
        DATE '2026-06-01', DATE '2026-06-02'
      )
    )
    SELECT transaction_hash, 'FROM `other-project.dataset.transactions`' AS note
    FROM managed
    """

    validate_sql_text(sql)


def test_verify_sql_preflights_twice_and_disables_query_cache() -> None:
    client = FakeClient()

    evidence = verify_sql(client, (_case(),), SqlPolicy())

    assert len(client.calls) == 3
    assert all(call[1].use_query_cache is False for call in client.calls)
    assert all(call[1].maximum_bytes_billed == 20 * 2**30 for call in client.calls)
    assert evidence.records[0].row_count == 1
    assert evidence.records[0].sql_sha256


def test_verify_sql_requires_expected_columns_for_every_case() -> None:
    client = FakeClient()

    with pytest.raises(TestSetError, match="expected columns"):
        verify_sql(client, (replace(_case(), expected_columns=()),), SqlPolicy())

    assert client.calls == []


def test_verify_sql_rejects_aggregate_budget_before_execution() -> None:
    client = FakeClient(bytes_processed=100)
    policy = SqlPolicy(total_bytes=50)

    with pytest.raises(TestSetError, match="aggregate"):
        verify_sql(client, (_case(),), policy)
    assert len(client.calls) == 1


def test_verify_sql_rechecks_whole_batch_budget_before_any_execution() -> None:
    client = SequencedClient([20, 20, 35, 35])
    policy = SqlPolicy(per_query_bytes=50, total_bytes=60)

    with pytest.raises(TestSetError, match="immediate aggregate"):
        verify_sql(
            client,
            (_case(question_id="q-001"), _case(question_id="q-002")),
            policy,
        )

    assert client.calls == [True, True, True, True]


def test_verify_sql_uses_bounded_preview_and_authoritative_total_rows() -> None:
    rows = CountingRows()
    client = FakeClient(rows=rows)

    evidence = verify_sql(client, (_case(),), SqlPolicy())

    assert rows.consumed == MAX_RESULT_PREVIEW_ROWS
    assert evidence.records[0].row_count == 10_000


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
        pool_b=(PoolBRecord("q-001", "writer_01", SAFE_SQL, ("transaction_hash",), True, False),),
        reviews=(ReviewRecord("q-001", "reviewer_01", 4, 4, "easy", "ACCEPT"),),
        selections=(
            SelectionRecord(
                "q-001",
                "easy",
                ("simple_filter",),
                "accepted",
                ("named_entity",),
                ("transaction_facts", "transaction_facts.transaction_hash"),
                ("CQ01",),
            ),
        ),
    )

    case = module._cases_from_bundle(bundle)[0]

    assert case.expected_result_size is None
    assert case.expected_columns == ("transaction_hash",)
    assert case.schema_elements == (
        "transaction_facts",
        "transaction_facts.transaction_hash",
    )
    assert case.cq_ids == ("CQ01",)
