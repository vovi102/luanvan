"""Tests for the GoogleSQL three-pool test-set contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import (
    PoolARecord,
    PoolBRecord,
    SelectionRecord,
    TestSetError,
    TestSetPaths,
    load_csv,
    parse_bool,
)

POOL_A_HEADER = "question_id,author_id,nl,persona,source_batch\n"


def test_load_csv_returns_rows_for_the_exact_pool_a_header(tmp_path: Path) -> None:
    path = tmp_path / "raw_pool_a.csv"
    path.write_text(
        POOL_A_HEADER + "q-001,author_01,Who sent funds?,journalist,batch-1\n",
        encoding="utf-8",
    )

    rows = load_csv(path, ("question_id", "author_id", "nl", "persona", "source_batch"))

    assert rows == [
        {
            "question_id": "q-001",
            "author_id": "author_01",
            "nl": "Who sent funds?",
            "persona": "journalist",
            "source_batch": "batch-1",
        }
    ]


def test_load_csv_rejects_missing_and_extra_headers(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    missing.write_text("question_id,author_id\nq-001,author_01\n", encoding="utf-8")
    extra = tmp_path / "extra.csv"
    extra.write_text(POOL_A_HEADER.replace("source_batch", "source_batch,extra"), encoding="utf-8")

    with pytest.raises(TestSetError, match="header"):
        load_csv(missing, ("question_id", "author_id", "nl"))
    with pytest.raises(TestSetError, match="header"):
        load_csv(extra, ("question_id", "author_id", "nl", "persona", "source_batch"))


def test_load_csv_rejects_duplicate_headers_and_empty_required_values(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text("question_id,question_id\nq-001,q-001\n", encoding="utf-8")
    empty = tmp_path / "empty.csv"
    empty.write_text(POOL_A_HEADER + "q-001,,Who?,journalist,batch-1\n", encoding="utf-8")

    with pytest.raises(TestSetError, match="duplicate"):
        load_csv(duplicate, ("question_id",))
    with pytest.raises(TestSetError, match="empty"):
        load_csv(empty, ("question_id", "author_id", "nl", "persona", "source_batch"))


def test_pool_a_record_rejects_email_like_identifiers() -> None:
    with pytest.raises(TestSetError, match="pseudonym"):
        PoolARecord(
            question_id="q-001",
            author_id="person@example.com",
            nl="Who sent funds?",
            persona="journalist",
            source_batch="batch-1",
        )


def test_pool_b_record_requires_explicit_unique_result_columns() -> None:
    with pytest.raises(TestSetError, match="expected_columns"):
        PoolBRecord("q-001", "writer_01", "SELECT 1", (), False, False)
    with pytest.raises(TestSetError, match="expected_columns"):
        PoolBRecord("q-001", "writer_01", "SELECT 1", ("value", "value"), False, False)


def test_selection_record_normalizes_and_deduplicates_accepted_labels() -> None:
    record = SelectionRecord(
        "q-001",
        "easy",
        (" Simple_Filter ", "simple_filter", "TIME_RANGE"),
        "accepted",
        (" Named_Entity ", "named_entity", "ADDRESS_ONLY"),
        (" transaction_facts ", "transaction_facts"),
        (" CQ01 ", "CQ01"),
    )

    assert record.categories == ("simple_filter", "time_range")
    assert record.entity_kinds == ("named_entity", "address_only")
    assert record.schema_elements == ("transaction_facts",)
    assert record.cq_ids == ("CQ01",)


@pytest.mark.parametrize(
    ("categories", "entity_kinds", "message"),
    (
        (("simple_filter", ""), ("named_entity",), "empty"),
        (("unknown_category",), ("named_entity",), "category"),
        (("simple_filter",), ("unknown_kind",), "entity"),
    ),
)
def test_selection_record_rejects_empty_or_unknown_coverage_labels(
    categories: tuple[str, ...], entity_kinds: tuple[str, ...], message: str
) -> None:
    with pytest.raises(TestSetError, match=message):
        SelectionRecord(
            "q-001",
            "easy",
            categories,
            "accepted",
            entity_kinds,
            ("transaction_facts",),
            ("CQ01",),
        )


def test_parse_bool_accepts_only_explicit_boolean_tokens() -> None:
    assert parse_bool("true") is True
    assert parse_bool("FALSE") is False
    with pytest.raises(TestSetError, match="boolean"):
        parse_bool("maybe")


def test_test_set_paths_derive_all_artifact_locations(tmp_path: Path) -> None:
    paths = TestSetPaths.from_root(tmp_path)

    assert paths.raw_pool_a == tmp_path / "raw_pool_a.csv"
    assert paths.sql_pool_b == tmp_path / "sql_pool_b.csv"
    assert paths.review_pool_c == tmp_path / "review_pool_c.csv"
    assert paths.final_selection == tmp_path / "final_selection.csv"
    assert paths.final_jsonl == tmp_path / "test-100.jsonl"
