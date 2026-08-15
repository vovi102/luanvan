"""Tests for three-pool bundle validation and review statistics."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from nl2sparql.dataset.testset.contracts import (
    PoolARecord,
    PoolBRecord,
    ReviewRecord,
    SelectionRecord,
    TestSetError,
)
from nl2sparql.dataset.testset.validate import (
    Bundle,
    cohen_kappa,
    validate_bundle,
    validate_selection,
)


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
                "`nl2sparql-thesis.nl2sparql_analytics.transactions` LIMIT 1"
            ),
            expected_empty=False,
            ambiguity_flag=False,
        )
        for record in pool_a
    )
    reviews: list[ReviewRecord] = []
    for index, record in enumerate(pool_a):
        reviews.append(
            ReviewRecord(
                question_id=record.question_id,
                reviewer_id="reviewer_01",
                nl_quality=4,
                faithfulness=4,
                difficulty="easy",
                decision="REJECT" if index >= count - reject_count else "ACCEPT",
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
                    decision="ACCEPT",
                )
            )
    return Bundle(pool_a=pool_a, pool_b=pool_b, reviews=tuple(reviews), selections=())


def _selection_rows(difficulties: Iterable[str]) -> tuple[SelectionRecord, ...]:
    return tuple(
        SelectionRecord(
            question_id=f"q-{index:03d}",
            final_difficulty=difficulty,
            categories=(
                "simple_filter",
                "entity_lookup",
                "time_range",
                "top_k",
                "aggregation",
                "multi_hop",
            ),
            entity_kinds=("named_entity", "address", "concept"),
            selection_note="accepted",
        )
        for index, difficulty in enumerate(difficulties)
    )


def test_cohen_kappa_returns_one_for_identical_labels() -> None:
    assert cohen_kappa(("ACCEPT", "REJECT", "ACCEPT"), ("ACCEPT", "REJECT", "ACCEPT")) == 1.0


def test_cohen_kappa_rejects_unequal_or_degenerate_inputs() -> None:
    with pytest.raises(TestSetError, match="same length"):
        cohen_kappa(("ACCEPT",), ("ACCEPT", "REJECT"))
    with pytest.raises(TestSetError, match="empty"):
        cohen_kappa((), ())


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


def test_validate_selection_requires_exact_easy_medium_hard_quotas() -> None:
    bundle = _bundle(100)
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
    bundle = _bundle(100)
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
