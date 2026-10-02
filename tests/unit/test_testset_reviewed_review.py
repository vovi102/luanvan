"""Tests for append-only T3.5 human review and explicit selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import SelectionRecord, TestSetError
from nl2sparql.dataset.testset.reviewed_contracts import (
    AGENT_REVIEWED_PROFILE,
    CandidateRecord,
    ReviewEvent,
)
from nl2sparql.dataset.testset.reviewed_validate import (
    ReviewedBundle,
    resolve_review_state,
    validate_reviewed_selection,
)

CATALOG = Path("src/nl2sparql/sql/catalog/ethereum_analytics.json")
SQL = (
    "SELECT COUNT(*) AS transaction_count "
    "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
    "(DATE '2026-06-01', DATE '2026-07-01')"
)
CATEGORIES = (
    "simple_filter",
    "time_range",
    "transaction_aggregation",
    "top_k",
    "comparison",
    "multi_hop",
)
ENTITY_KINDS = ("address_only", "concept_class", "named_entity")


def _candidate(index: int) -> CandidateRecord:
    difficulty = "easy" if index <= 36 else "medium" if index <= 96 else "hard"
    return CandidateRecord.from_mapping(
        {
            "schema_version": "1.0.0",
            "provenance_profile": AGENT_REVIEWED_PROFILE,
            "question_id": f"t35-{index:03d}",
            "author_type": "agent",
            "nl": f"Review fixture question {index:03d} about June activity?",
            "sql": SQL,
            "expected_columns": ["transaction_count"],
            "expected_empty": False,
            "ambiguity_flag": False,
            "difficulty": difficulty,
            "categories": [CATEGORIES[(index - 1) % len(CATEGORIES)]],
            "entity_kinds": [ENTITY_KINDS[(index - 1) % len(ENTITY_KINDS)]],
            "schema_elements": [
                "transaction_facts",
                "transaction_facts.transaction_hash",
            ],
            "cq_ids": ["CQ01"],
            "rationale": f"Review fixture rationale {index:03d}.",
            "generation_batch": "t35-agent-batch-01",
            "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
            "source_commit": "b" * 40,
        }
    )


def _selection(candidate: CandidateRecord) -> SelectionRecord:
    return SelectionRecord(
        question_id=candidate.question_id,
        final_difficulty=candidate.difficulty,
        categories=candidate.categories,
        entity_kinds=candidate.entity_kinds,
        schema_elements=candidate.schema_elements,
        cq_ids=candidate.cq_ids,
        selection_note="selected after review",
    )


def _bundle() -> ReviewedBundle:
    candidates = tuple(_candidate(index) for index in range(1, 121))
    events = tuple(
        ReviewEvent(
            candidate.question_id,
            1,
            "reviewer_01",
            4,
            4,
            candidate.difficulty,
            "ACCEPT",
        )
        for candidate in candidates
    )
    selected = candidates[:30] + candidates[36:86] + candidates[96:116]
    return ReviewedBundle(
        candidates, events, tuple(_selection(candidate) for candidate in selected)
    )


def test_resolve_review_state_requires_one_decision_for_every_candidate(tmp_path: Path) -> None:
    bundle = _bundle()

    with pytest.raises(TestSetError, match="every candidate"):
        resolve_review_state(
            replace(bundle, events=bundle.events[:-1]),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_resolve_review_state_requires_one_stable_reviewer_and_contiguous_rounds(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    second_reviewer = replace(bundle.events[0], reviewer_id="reviewer_02")
    with pytest.raises(TestSetError, match="stable reviewer"):
        resolve_review_state(
            replace(bundle, events=(second_reviewer, *bundle.events[1:])),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )

    agent_events = tuple(replace(event, reviewer_id="agent") for event in bundle.events)
    with pytest.raises(TestSetError, match="human reviewer|reserved"):
        resolve_review_state(
            replace(bundle, events=agent_events),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )

    extra = ReviewEvent("t35-001", 3, "reviewer_01", 4, 4, "easy", "ACCEPT")
    with pytest.raises(TestSetError, match="contiguous"):
        resolve_review_state(
            replace(bundle, events=(*bundle.events, extra)),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_resolve_review_state_rejects_low_score_acceptance(tmp_path: Path) -> None:
    bundle = _bundle()
    low_score = replace(bundle.events[0], nl_quality=3)

    with pytest.raises(TestSetError, match="scores of at least 4"):
        resolve_review_state(
            replace(bundle, events=(low_score, *bundle.events[1:])),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_revise_then_accept_binds_revised_content_and_digest(tmp_path: Path) -> None:
    bundle = _bundle()
    revised_nl = "How many successful transactions occurred during June 2026?"
    revised_sql = SQL.replace("COUNT(*)", "COUNTIF(is_success)")
    revision = ReviewEvent(
        "t35-001",
        1,
        "reviewer_01",
        3,
        3,
        "easy",
        "REVISE",
        revised_nl,
        revised_sql,
    )
    acceptance = ReviewEvent("t35-001", 2, "reviewer_01", 5, 5, "easy", "ACCEPT")
    events = (revision, acceptance, *bundle.events[1:])

    accepted = resolve_review_state(
        replace(bundle, events=events), repo_root=tmp_path, catalog_path=CATALOG
    )

    first = accepted[0]
    assert first.nl == revised_nl
    assert first.sql == revised_sql
    assert first.accepted_content_sha256 != first.candidate_sha256
    assert len(first.accepted_content_sha256) == 64


def test_review_rounds_must_be_append_only_file_order(tmp_path: Path) -> None:
    bundle = _bundle()
    revision = ReviewEvent(
        "t35-001",
        1,
        "reviewer_01",
        3,
        3,
        "easy",
        "REVISE",
        "Revised append-only question",
        "",
    )
    acceptance = ReviewEvent("t35-001", 2, "reviewer_01", 5, 5, "easy", "ACCEPT")

    with pytest.raises(TestSetError, match="file order|append-only"):
        resolve_review_state(
            replace(bundle, events=(acceptance, revision, *bundle.events[1:])),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_review_validation_replays_complete_candidate_contract(tmp_path: Path) -> None:
    bundle = _bundle()
    selected_ids = {row.question_id for row in bundle.selections}
    shortened = replace(
        bundle,
        candidates=tuple(row for row in bundle.candidates if row.question_id in selected_ids),
        events=tuple(row for row in bundle.events if row.question_id in selected_ids),
    )

    with pytest.raises(TestSetError, match="120|candidate IDs|quota"):
        validate_reviewed_selection(shortened, repo_root=tmp_path, catalog_path=CATALOG)


@pytest.mark.parametrize("mode", ("unsafe_sql", "leaked_nl"))
def test_resolve_review_state_revalidates_revisions(tmp_path: Path, mode: str) -> None:
    bundle = _bundle()
    revised_nl = "A revised question with no prior overlap"
    revised_sql = SQL
    if mode == "unsafe_sql":
        revised_sql = "DELETE FROM dataset.table WHERE TRUE"
    else:
        leaked = tmp_path / "data" / "eval"
        leaked.mkdir(parents=True)
        (leaked / "questions.jsonl").write_text(
            json.dumps({"question": "Previously used review question"}) + "\n",
            encoding="utf-8",
        )
        revised_nl = "  previously USED   review question "
    revision = ReviewEvent(
        "t35-001",
        1,
        "reviewer_01",
        3,
        3,
        "easy",
        "REVISE",
        revised_nl,
        revised_sql,
    )
    acceptance = ReviewEvent("t35-001", 2, "reviewer_01", 5, 5, "easy", "ACCEPT")

    with pytest.raises(TestSetError, match="read-only|leakage"):
        resolve_review_state(
            replace(bundle, events=(revision, acceptance, *bundle.events[1:])),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_validate_reviewed_selection_rejects_rejected_candidate(tmp_path: Path) -> None:
    bundle = _bundle()
    rejected = replace(bundle.events[0], decision="REJECT")

    with pytest.raises(TestSetError, match="accepted"):
        validate_reviewed_selection(
            replace(bundle, events=(rejected, *bundle.events[1:])),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("count", "100"),
        ("quota", "difficulty"),
        ("categories", "categories"),
        ("kinds", "entity kinds"),
    ),
)
def test_validate_reviewed_selection_enforces_final_quota_and_coverage(
    tmp_path: Path, mode: str, message: str
) -> None:
    bundle = _bundle()
    selections = list(bundle.selections)
    if mode == "count":
        selections.pop()
    elif mode == "quota":
        selections[0] = replace(selections[0], final_difficulty="medium")
    elif mode == "categories":
        selections = [replace(row, categories=("simple_filter",)) for row in selections]
    else:
        selections = [replace(row, entity_kinds=("address_only",)) for row in selections]

    with pytest.raises(TestSetError, match=message):
        validate_reviewed_selection(
            replace(bundle, selections=tuple(selections)),
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_validate_reviewed_selection_returns_hash_bound_report(tmp_path: Path) -> None:
    report = validate_reviewed_selection(_bundle(), repo_root=tmp_path, catalog_path=CATALOG)

    assert report.status == "review_ready"
    assert report.candidate_count == 120
    assert report.reviewed_count == 120
    assert report.accepted_count == 120
    assert report.revised_count == 0
    assert report.rejected_count == 0
    assert report.reviewer_id == "reviewer_01"
    assert report.selected_count == 100
    assert report.difficulty_counts == (("easy", 30), ("hard", 20), ("medium", 50))
    assert all(
        len(digest) == 64
        for digest in (
            report.accepted_content_sha256,
            report.review_sha256,
            report.selection_sha256,
        )
    )
