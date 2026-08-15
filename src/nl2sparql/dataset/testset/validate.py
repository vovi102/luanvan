"""Credential-free validation and review statistics for a test-set bundle."""

from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from nl2sparql.dataset.testset.contracts import (
    PoolARecord,
    PoolBRecord,
    ReviewRecord,
    SelectionRecord,
    TestSetError,
    TestSetPaths,
    load_csv,
    parse_bool,
)


@dataclass(frozen=True)
class Bundle:
    """All human-produced rows for one test-set run."""

    pool_a: tuple[PoolARecord, ...]
    pool_b: tuple[PoolBRecord, ...]
    reviews: tuple[ReviewRecord, ...]
    selections: tuple[SelectionRecord, ...]


@dataclass(frozen=True)
class BundleReport:
    """Machine-readable evidence from credential-free bundle validation."""

    pool_a_count: int
    pool_b_count: int
    review_count: int
    author_counts: dict[str, int]
    reject_rate: float
    kappa: float
    double_review_ids: tuple[str, ...]
    accepted_ids: tuple[str, ...]
    category_count: int
    entity_kind_count: int


def _canonical_nl(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    """Compute nominal Cohen's kappa for two equally sized label sequences."""
    if len(labels_a) != len(labels_b):
        raise TestSetError("kappa inputs must have the same length")
    if not labels_a:
        raise TestSetError("kappa inputs must not be empty")
    observed = sum(left == right for left, right in zip(labels_a, labels_b, strict=True))
    first_counts = Counter(labels_a)
    second_counts = Counter(labels_b)
    total = len(labels_a)
    chance = sum(
        first_counts[label] * second_counts[label]
        for label in set(first_counts) | set(second_counts)
    ) / (total * total)
    if math.isclose(chance, 1.0):
        if observed == total:
            return 1.0
        raise TestSetError("kappa chance agreement is 1; statistic is undefined")
    observed_rate = observed / total
    return (observed_rate - chance) / (1.0 - chance)


def _unique_ids(values: Sequence[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise TestSetError(f"{label} IDs must be unique")


def validate_bundle(bundle: Bundle) -> BundleReport:
    """Validate cross-pool joins, coverage, review quality, and kappa."""
    if not bundle.pool_a:
        raise TestSetError("Pool A must not be empty")
    pool_a_ids = tuple(record.question_id for record in bundle.pool_a)
    _unique_ids(pool_a_ids, "Pool A")
    normalized_questions = [_canonical_nl(record.nl) for record in bundle.pool_a]
    _unique_ids(normalized_questions, "Pool A normalized question")

    author_counts = Counter(record.author_id for record in bundle.pool_a)
    if len(author_counts) < 3 or any(count < 20 for count in author_counts.values()):
        raise TestSetError("Pool A requires at least three authors with 20 questions each")

    pool_b_by_id: defaultdict[str, list[PoolBRecord]] = defaultdict(list)
    for record in bundle.pool_b:
        pool_b_by_id[record.question_id].append(record)
    if set(pool_b_by_id) != set(pool_a_ids):
        raise TestSetError("Pool B IDs must exactly match Pool A IDs")
    if any(len(rows) != 1 for rows in pool_b_by_id.values()):
        raise TestSetError("Pool B requires exactly one canonical row per question")

    reviews_by_id: defaultdict[str, list[ReviewRecord]] = defaultdict(list)
    for review in bundle.reviews:
        if review.question_id not in set(pool_a_ids):
            raise TestSetError("reviews contain an unknown question ID")
        reviews_by_id[review.question_id].append(review)
    if set(reviews_by_id) != set(pool_a_ids):
        raise TestSetError("every Pool A question requires a Pool C review")
    if any(
        len({review.reviewer_id for review in rows}) != len(rows) for rows in reviews_by_id.values()
    ):
        raise TestSetError("a question cannot have duplicate reviews from one reviewer")

    reject_rate = sum(review.decision == "REJECT" for review in bundle.reviews) / len(
        bundle.reviews
    )
    if reject_rate >= 0.30:
        raise TestSetError("Pool C reject rate must be below 30%")

    double_review_ids = tuple(
        sorted(question_id for question_id, rows in reviews_by_id.items() if len(rows) == 2)[:30]
    )
    if len(double_review_ids) != 30:
        raise TestSetError("Pool C requires a deterministic 30-question double-review subset")
    decisions = [
        sorted(reviews_by_id[question_id], key=lambda row: row.reviewer_id)
        for question_id in double_review_ids
    ]
    kappa = cohen_kappa(
        tuple(rows[0].decision for rows in decisions),
        tuple(rows[1].decision for rows in decisions),
    )
    if kappa < 0.7:
        raise TestSetError(f"Cohen's kappa must be at least 0.7, received {kappa:.3f}")

    accepted_ids = tuple(
        sorted(
            question_id
            for question_id, rows in reviews_by_id.items()
            if rows and all(review.decision == "ACCEPT" for review in rows)
        )
    )
    categories = {category for row in bundle.selections for category in row.categories}
    entity_kinds = {kind for row in bundle.selections for kind in row.entity_kinds}
    return BundleReport(
        pool_a_count=len(bundle.pool_a),
        pool_b_count=len(bundle.pool_b),
        review_count=len(bundle.reviews),
        author_counts=dict(sorted(author_counts.items())),
        reject_rate=reject_rate,
        kappa=kappa,
        double_review_ids=double_review_ids,
        accepted_ids=accepted_ids,
        category_count=len(categories),
        entity_kind_count=len(entity_kinds),
    )


def validate_selection(bundle: Bundle) -> tuple[SelectionRecord, ...]:
    """Validate the lead-owned 100-row selection and its exact quotas."""
    selections = bundle.selections
    if len(selections) != 100:
        raise TestSetError("final selection requires exactly 100 rows")
    ids = tuple(row.question_id for row in selections)
    _unique_ids(ids, "final selection")
    source_ids = {record.question_id for record in bundle.pool_a}
    if not set(ids) <= source_ids:
        raise TestSetError("final selection contains an unknown question ID")
    decisions_by_id: defaultdict[str, list[str]] = defaultdict(list)
    for review in bundle.reviews:
        decisions_by_id[review.question_id].append(review.decision)
    accepted_ids = {
        question_id
        for question_id, decisions in decisions_by_id.items()
        if decisions and all(decision == "ACCEPT" for decision in decisions)
    }
    if not set(ids) <= accepted_ids:
        raise TestSetError("final selection contains a question without ACCEPT consensus")
    difficulties = Counter(row.final_difficulty for row in selections)
    if difficulties != {"easy": 30, "medium": 50, "hard": 20}:
        raise TestSetError(f"final selection difficulty quota mismatch: {dict(difficulties)}")
    categories = {category for row in selections for category in row.categories}
    if len(categories) < 6:
        raise TestSetError("final selection must cover at least six categories")
    entity_kinds = {kind for row in selections for kind in row.entity_kinds}
    if len(entity_kinds) < 3:
        raise TestSetError("final selection must cover at least three entity kinds")
    return selections


def load_bundle(paths: TestSetPaths) -> Bundle:
    """Load the four CSV inputs into typed records."""
    pool_a_rows = load_csv(
        paths.raw_pool_a,
        ("question_id", "author_id", "nl", "persona", "source_batch"),
    )
    pool_b_rows = load_csv(
        paths.sql_pool_b,
        ("question_id", "writer_id", "sql", "expected_empty", "ambiguity_flag", "notes"),
        required_values=("question_id", "writer_id", "sql", "expected_empty", "ambiguity_flag"),
    )
    review_rows = load_csv(
        paths.review_pool_c,
        (
            "question_id",
            "reviewer_id",
            "nl_quality",
            "faithfulness",
            "difficulty",
            "decision",
            "notes",
        ),
        required_values=(
            "question_id",
            "reviewer_id",
            "nl_quality",
            "faithfulness",
            "difficulty",
            "decision",
        ),
    )
    selection_rows = load_csv(
        paths.final_selection,
        ("question_id", "final_difficulty", "categories", "entity_kinds", "selection_note"),
        required_values=("question_id", "final_difficulty", "categories", "entity_kinds"),
    )
    return Bundle(
        pool_a=tuple(PoolARecord(**row) for row in pool_a_rows),
        pool_b=tuple(
            PoolBRecord(
                question_id=row["question_id"],
                writer_id=row["writer_id"],
                sql=row["sql"],
                expected_empty=parse_bool(row["expected_empty"]),
                ambiguity_flag=parse_bool(row["ambiguity_flag"]),
                notes=row["notes"],
            )
            for row in pool_b_rows
        ),
        reviews=tuple(
            ReviewRecord(
                question_id=row["question_id"],
                reviewer_id=row["reviewer_id"],
                nl_quality=int(row["nl_quality"]),
                faithfulness=int(row["faithfulness"]),
                difficulty=row["difficulty"],
                decision=row["decision"],
                notes=row["notes"],
            )
            for row in review_rows
        ),
        selections=tuple(
            SelectionRecord(
                question_id=row["question_id"],
                final_difficulty=row["final_difficulty"],
                categories=tuple(filter(None, row["categories"].split("|"))),
                entity_kinds=tuple(filter(None, row["entity_kinds"].split("|"))),
                selection_note=row["selection_note"],
            )
            for row in selection_rows
        ),
    )
