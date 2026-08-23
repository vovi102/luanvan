"""Tests for three-pool bundle validation and review statistics."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import (
    PoolARecord,
    PoolBRecord,
    ReviewRecord,
    SelectionRecord,
    TestSetError,
    TestSetPaths,
)
from nl2sparql.dataset.testset.validate import (
    Bundle,
    cohen_kappa,
    load_bundle,
    validate_bundle,
    validate_selection,
)


def test_load_bundle_preserves_ordered_pool_b_expected_columns(tmp_path: Path) -> None:
    paths = TestSetPaths.from_root(tmp_path)
    paths.raw_pool_a.write_text(
        "question_id,author_id,nl,persona,source_batch\n"
        "q-001,author_01,Find a transaction,researcher,batch-1\n",
        encoding="utf-8",
    )
    paths.sql_pool_b.write_text(
        "question_id,writer_id,sql,expected_columns,expected_empty,ambiguity_flag,notes\n"
        "q-001,writer_01,SELECT 1,transaction_hash|block_timestamp,false,false,\n",
        encoding="utf-8",
    )
    paths.review_pool_c.write_text(
        "question_id,reviewer_id,nl_quality,faithfulness,difficulty,decision,notes\n"
        "q-001,reviewer_01,4,4,easy,ACCEPT,\n",
        encoding="utf-8",
    )
    paths.final_selection.write_text(
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,"
        "selection_note\n",
        encoding="utf-8",
    )

    bundle = load_bundle(paths)

    assert bundle.pool_b[0].expected_columns == ("transaction_hash", "block_timestamp")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("categories", "simple_filter||time_range"),
        ("entity_kinds", "named_entity||address_only"),
        ("schema_elements", "transaction_facts||transaction_facts.transaction_hash"),
        ("cq_ids", "CQ01||CQ02"),
    ),
)
def test_load_bundle_rejects_empty_pipe_delimited_selection_tokens(
    tmp_path: Path, field: str, value: str
) -> None:
    paths = TestSetPaths.from_root(tmp_path)
    paths.raw_pool_a.write_text(
        "question_id,author_id,nl,persona,source_batch\n"
        "q-001,author_01,Find a transaction,researcher,batch-1\n",
        encoding="utf-8",
    )
    paths.sql_pool_b.write_text(
        "question_id,writer_id,sql,expected_columns,expected_empty,ambiguity_flag,notes\n"
        "q-001,writer_01,SELECT 1,transaction_hash,false,false,\n",
        encoding="utf-8",
    )
    paths.review_pool_c.write_text(
        "question_id,reviewer_id,nl_quality,faithfulness,difficulty,decision,notes\n"
        "q-001,reviewer_01,4,4,easy,ACCEPT,\n",
        encoding="utf-8",
    )
    selection = {
        "categories": "simple_filter|time_range",
        "entity_kinds": "named_entity|address_only",
        "schema_elements": "transaction_facts|transaction_facts.transaction_hash",
        "cq_ids": "CQ01|CQ02",
    }
    selection[field] = value
    paths.final_selection.write_text(
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,"
        "selection_note\n"
        f"q-001,easy,{selection['categories']},{selection['entity_kinds']},"
        f"{selection['schema_elements']},{selection['cq_ids']},accepted\n",
        encoding="utf-8",
    )

    with pytest.raises(TestSetError, match="empty"):
        load_bundle(paths)


def _bundle(count: int = 60, *, reject_count: int = 0) -> Bundle:
    pool_a = tuple(
        PoolARecord(
            question_id=f"q-{index:03d}",
            author_id=f"author_{index % 3}",
            nl=f"Find transaction flow {index}",
            persona="journalist",
            source_batch="batch-1",
        )
        for index in range(count)
    )
    pool_b = tuple(
        PoolBRecord(
            question_id=record.question_id,
            writer_id="writer_01",
            sql=(
                "SELECT transaction_hash FROM "
                "`nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
                "(DATE '2026-06-01', DATE '2026-06-02') LIMIT 1"
            ),
            expected_columns=("transaction_hash",),
            expected_empty=False,
            ambiguity_flag=False,
        )
        for record in pool_a
    )
    reviews: list[ReviewRecord] = []
    for index, record in enumerate(pool_a):
        baseline_decision = "REVISE" if index < 2 else "ACCEPT"
        reviews.append(
            ReviewRecord(
                question_id=record.question_id,
                reviewer_id="reviewer_01",
                nl_quality=4,
                faithfulness=4,
                difficulty="easy",
                decision="REJECT" if index >= count - reject_count else baseline_decision,
            )
        )
        if index < 30:
            reviews.append(
                ReviewRecord(
                    question_id=record.question_id,
                    reviewer_id="reviewer_02",
                    nl_quality=4,
                    faithfulness=4,
                    difficulty="easy",
                    decision=baseline_decision,
                )
            )
    return Bundle(pool_a=pool_a, pool_b=pool_b, reviews=tuple(reviews), selections=())


def _selection_rows(difficulties: Iterable[str], *, start: int = 2) -> tuple[SelectionRecord, ...]:
    return tuple(
        SelectionRecord(
            question_id=f"q-{index:03d}",
            final_difficulty=difficulty,
            categories=(
                "simple_filter",
                "entity_lookup",
                "time_range",
                "top_k",
                "transaction_aggregation",
                "multi_hop",
            ),
            entity_kinds=("named_entity", "address_only", "concept_class"),
            selection_note="accepted",
            schema_elements=("transaction_facts", "transaction_facts.transaction_hash"),
            cq_ids=("CQ01",),
        )
        for index, difficulty in enumerate(difficulties, start=start)
    )


def test_cohen_kappa_returns_one_for_identical_labels() -> None:
    assert cohen_kappa(("ACCEPT", "REJECT", "ACCEPT"), ("ACCEPT", "REJECT", "ACCEPT")) == 1.0


def test_cohen_kappa_rejects_unequal_or_degenerate_inputs() -> None:
    with pytest.raises(TestSetError, match="same length"):
        cohen_kappa(("ACCEPT",), ("ACCEPT", "REJECT"))
    with pytest.raises(TestSetError, match="empty"):
        cohen_kappa((), ())
    with pytest.raises(TestSetError, match="degenerate|undefined"):
        cohen_kappa(("ACCEPT", "ACCEPT"), ("ACCEPT", "ACCEPT"))


def test_validate_bundle_reports_author_coverage_and_double_review_kappa() -> None:
    report = validate_bundle(_bundle())

    assert report.pool_a_count == 60
    assert report.author_counts == {"author_0": 20, "author_1": 20, "author_2": 20}
    assert report.reject_rate == 0.0
    assert report.kappa == 1.0
    assert len(report.double_review_ids) == 30


def test_validate_bundle_rejects_author_undercoverage() -> None:
    bundle = _bundle()
    undercovered = Bundle(
        pool_a=tuple(
            PoolARecord(
                question_id=record.question_id,
                author_id="author_0",
                nl=record.nl,
                persona=record.persona,
                source_batch=record.source_batch,
            )
            for record in bundle.pool_a
        ),
        pool_b=bundle.pool_b,
        reviews=bundle.reviews,
        selections=(),
    )

    with pytest.raises(TestSetError, match="authors"):
        validate_bundle(undercovered)


def test_validate_bundle_rejects_pool_b_duplicate_and_review_reject_rate() -> None:
    bundle = _bundle(reject_count=30)
    duplicate_pool_b = bundle.pool_b + (bundle.pool_b[0],)
    duplicate = Bundle(
        pool_a=bundle.pool_a,
        pool_b=duplicate_pool_b,
        reviews=bundle.reviews,
        selections=(),
    )

    with pytest.raises(TestSetError, match="exactly one"):
        validate_bundle(duplicate)
    with pytest.raises(TestSetError, match="reject rate"):
        validate_bundle(bundle)


def test_validate_bundle_requires_reviewer_independence_per_question() -> None:
    bundle = _bundle()
    reviews = list(bundle.reviews)
    reviews[0] = ReviewRecord(
        question_id=reviews[0].question_id,
        reviewer_id=bundle.pool_a[0].author_id,
        nl_quality=4,
        faithfulness=4,
        difficulty="easy",
        decision="ACCEPT",
    )

    with pytest.raises(TestSetError, match="independent"):
        validate_bundle(
            Bundle(
                pool_a=bundle.pool_a,
                pool_b=bundle.pool_b,
                reviews=tuple(reviews),
                selections=(),
            )
        )


def test_validate_bundle_requires_one_stable_reviewer_pair_for_kappa_rows() -> None:
    bundle = _bundle()
    reviews = list(bundle.reviews)
    target = next(
        index
        for index, review in enumerate(reviews)
        if review.question_id == "q-029" and review.reviewer_id == "reviewer_02"
    )
    reviews[target] = ReviewRecord(
        question_id="q-029",
        reviewer_id="reviewer_03",
        nl_quality=4,
        faithfulness=4,
        difficulty="easy",
        decision="ACCEPT",
    )

    with pytest.raises(TestSetError, match="stable reviewer pair"):
        validate_bundle(Bundle(bundle.pool_a, bundle.pool_b, tuple(reviews), bundle.selections))


@pytest.mark.parametrize(
    ("overlap", "message"),
    (
        ("author_writer_same_question", "Pool A.*Pool B|role"),
        ("author_writer_cross_question", "Pool A.*Pool B|role"),
        ("author_reviewer_cross_question", "Pool A.*Pool C|role"),
        ("writer_reviewer_cross_question", "Pool B.*Pool C|role"),
    ),
)
def test_validate_bundle_rejects_cross_pool_identity_overlap(overlap: str, message: str) -> None:
    bundle = _bundle()
    pool_b = list(bundle.pool_b)
    reviews = list(bundle.reviews)
    if overlap == "author_writer_same_question":
        pool_b[0] = PoolBRecord(
            pool_b[0].question_id,
            bundle.pool_a[0].author_id,
            pool_b[0].sql,
            pool_b[0].expected_columns,
            False,
            False,
        )
    elif overlap == "author_writer_cross_question":
        pool_b[0] = PoolBRecord(
            pool_b[0].question_id,
            bundle.pool_a[1].author_id,
            pool_b[0].sql,
            pool_b[0].expected_columns,
            False,
            False,
        )
    elif overlap == "author_reviewer_cross_question":
        reviews[0] = ReviewRecord(
            reviews[0].question_id,
            bundle.pool_a[1].author_id,
            4,
            4,
            "easy",
            reviews[0].decision,
        )
    else:
        reviews[0] = ReviewRecord(
            reviews[0].question_id,
            bundle.pool_b[1].writer_id,
            4,
            4,
            "easy",
            reviews[0].decision,
        )

    with pytest.raises(TestSetError, match=message):
        validate_bundle(Bundle(bundle.pool_a, tuple(pool_b), tuple(reviews), ()))


def test_validate_bundle_applies_sql_safety_offline() -> None:
    bundle = _bundle()
    pool_b = list(bundle.pool_b)
    pool_b[0] = PoolBRecord(
        pool_b[0].question_id,
        pool_b[0].writer_id,
        "SELECT t.transaction_hash "
        "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
        "(DATE '2026-06-01', DATE '2026-06-02') AS t "
        "JOIN other_project.dataset.transactions AS external "
        "ON external.hash = t.transaction_hash",
        pool_b[0].expected_columns,
        False,
        False,
    )

    with pytest.raises(TestSetError, match="managed"):
        validate_bundle(Bundle(bundle.pool_a, tuple(pool_b), bundle.reviews, ()))


def test_validate_selection_requires_exact_easy_medium_hard_quotas() -> None:
    bundle = _bundle(102)
    valid = _selection_rows(("easy",) * 30 + ("medium",) * 50 + ("hard",) * 20)
    assert (
        len(
            validate_selection(
                Bundle(
                    pool_a=bundle.pool_a,
                    pool_b=bundle.pool_b,
                    reviews=bundle.reviews,
                    selections=valid,
                )
            )
        )
        == 100
    )

    invalid = _selection_rows(("easy",) * 31 + ("medium",) * 49 + ("hard",) * 20)
    with pytest.raises(TestSetError, match="difficulty"):
        validate_selection(
            Bundle(
                pool_a=bundle.pool_a,
                pool_b=bundle.pool_b,
                reviews=bundle.reviews,
                selections=invalid,
            )
        )


def test_validate_selection_rejects_conflicting_accept_and_reject_reviews() -> None:
    bundle = _bundle(102)
    conflicting_reviews = bundle.reviews + (
        ReviewRecord(
            question_id="q-099",
            reviewer_id="reviewer_03",
            nl_quality=2,
            faithfulness=2,
            difficulty="hard",
            decision="REJECT",
        ),
    )
    selections = _selection_rows(("easy",) * 30 + ("medium",) * 50 + ("hard",) * 20)
    conflicting = Bundle(
        pool_a=bundle.pool_a,
        pool_b=bundle.pool_b,
        reviews=conflicting_reviews,
        selections=selections,
    )

    with pytest.raises(TestSetError, match="without ACCEPT consensus"):
        validate_selection(conflicting)


@pytest.mark.parametrize(
    ("schema_elements", "cq_ids", "message"),
    (
        (("transaction_facts.unknown",), ("CQ01",), "schema"),
        (("transaction_facts",), ("CQ99",), "CQ"),
        ((), ("CQ01",), "schema"),
        (("transaction_facts",), (), "CQ"),
    ),
)
def test_validate_selection_rejects_missing_or_unknown_catalog_annotations(
    schema_elements: tuple[str, ...], cq_ids: tuple[str, ...], message: str
) -> None:
    bundle = _bundle(102)
    selections = list(_selection_rows(("easy",) * 30 + ("medium",) * 50 + ("hard",) * 20))
    selections[0] = SelectionRecord(
        question_id=selections[0].question_id,
        final_difficulty=selections[0].final_difficulty,
        categories=selections[0].categories,
        selection_note=selections[0].selection_note,
        entity_kinds=selections[0].entity_kinds,
        schema_elements=schema_elements,
        cq_ids=cq_ids,
    )

    with pytest.raises(TestSetError, match=message):
        validate_selection(Bundle(bundle.pool_a, bundle.pool_b, bundle.reviews, tuple(selections)))
