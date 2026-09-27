"""Tests for agent-authored, human-reviewed T3.5 contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.reviewed_contracts import (
    AGENT_REVIEWED_PROFILE,
    CandidateRecord,
    ReviewedTestSetPaths,
    ReviewEvent,
    load_candidates,
    load_review_events,
    load_reviewed_selections,
)


def _candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "schema_version": "1.0.0",
        "provenance_profile": AGENT_REVIEWED_PROFILE,
        "question_id": "t35-001",
        "author_type": "agent",
        "nl": "How many transactions were recorded in June 2026?",
        "sql": (
            "SELECT COUNT(*) AS transaction_count FROM `transaction_facts`"
            "(DATE '2026-06-01', DATE '2026-07-01')"
        ),
        "expected_columns": ["transaction_count"],
        "expected_empty": False,
        "ambiguity_flag": False,
        "difficulty": "easy",
        "categories": ["transaction_aggregation", "time_range"],
        "entity_kinds": ["address_only"],
        "schema_elements": ["transaction_facts", "transaction_facts.transaction_hash"],
        "cq_ids": ["CQ01"],
        "rationale": "A bounded count over one analytical relation.",
        "generation_batch": "t35-agent-batch-01",
        "catalog_sha256": "a" * 64,
        "source_commit": "b" * 40,
    }
    row.update(overrides)
    return row


def test_candidate_record_requires_exact_agent_profile_and_fields() -> None:
    record = CandidateRecord.from_mapping(_candidate())

    assert record.question_id == "t35-001"
    assert record.expected_columns == ("transaction_count",)
    assert record.expected_empty is False

    for override, message in (
        ({"schema_version": "2.0.0"}, "schema_version"),
        ({"provenance_profile": "three_pool_v1"}, "provenance_profile"),
        ({"author_type": "human"}, "author_type"),
        ({"expected_empty": 0}, "expected_empty"),
        ({"expected_columns": []}, "expected_columns"),
        ({"expected_columns": ["value", "value"]}, "expected_columns"),
    ):
        with pytest.raises(TestSetError, match=message):
            CandidateRecord.from_mapping(_candidate(**override))


def test_load_candidates_rejects_duplicate_json_keys_and_blank_lines(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        json.dumps(_candidate())[:-1] + ',"question_id":"t35-002"}\n', encoding="utf-8"
    )
    blank = tmp_path / "blank.jsonl"
    blank.write_text(json.dumps(_candidate()) + "\n\n", encoding="utf-8")

    with pytest.raises(TestSetError, match="duplicate JSON key"):
        load_candidates(duplicate)
    with pytest.raises(TestSetError, match="blank line"):
        load_candidates(blank)


def test_review_event_requires_valid_round_scores_and_revision_shape(tmp_path: Path) -> None:
    accepted = ReviewEvent(
        "t35-001", 1, "reviewer_01", 4, 5, "easy", "ACCEPT", "", "", "looks good"
    )
    revised = ReviewEvent(
        "t35-002",
        1,
        "reviewer_01",
        3,
        2,
        "medium",
        "REVISE",
        "Clarified question",
        "",
        "clarify intent",
    )

    assert accepted.review_round == 1
    assert revised.revised_nl == "Clarified question"

    invalid = (
        (("t35-001", 0, "reviewer_01", 4, 4, "easy", "ACCEPT", "", "", ""), "round"),
        (("t35-001", 1, "person@example.com", 4, 4, "easy", "ACCEPT", "", "", ""), "pseudonym"),
        (("t35-001", 1, "reviewer_01", 0, 4, "easy", "ACCEPT", "", "", ""), "scores"),
        (("t35-001", 1, "reviewer_01", 4, 4, "easy", "REVISE", "", "", ""), "revision"),
        (("t35-001", 1, "reviewer_01", 4, 4, "easy", "ACCEPT", "changed", "", ""), "ACCEPT"),
    )
    for args, message in invalid:
        with pytest.raises(TestSetError, match=message):
            ReviewEvent(*args)

    events = tmp_path / "review_events.csv"
    events.write_text(
        "question_id,reviewer_id,review_round,nl_quality,sql_faithfulness,difficulty,decision,revised_nl,revised_sql,notes\n",
        encoding="utf-8",
    )
    with pytest.raises(TestSetError, match="header"):
        load_review_events(events)


def test_reviewed_paths_separate_draft_and_final_roots(tmp_path: Path) -> None:
    paths = ReviewedTestSetPaths.from_roots(tmp_path / "draft", tmp_path / "final")

    assert paths.candidates == tmp_path / "draft" / "candidates.jsonl"
    assert paths.review_events == tmp_path / "draft" / "review_events.csv"
    assert paths.final_selection == tmp_path / "draft" / "final_selection.csv"
    assert paths.review_guide == tmp_path / "draft" / "REVIEW_GUIDE.md"
    assert paths.candidate_manifest == tmp_path / "draft" / "manifest.json"
    assert paths.validation_report == tmp_path / "draft" / "validation-report.json"
    assert paths.live_evidence == tmp_path / "final" / "live-evidence.json"
    assert paths.final_jsonl == tmp_path / "final" / "test-100.jsonl"
    assert paths.final_manifest == tmp_path / "final" / "manifest.json"


def test_profile_confusion_never_falls_back_to_three_pool(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        json.dumps(_candidate(provenance_profile="three_pool_v1")) + "\n", encoding="utf-8"
    )
    selections = tmp_path / "final_selection.csv"
    selections.write_text(
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,selection_note\n"
        "t35-001,easy,simple_filter,address_only,transaction_facts,CQ01,accept\n",
        encoding="utf-8",
    )

    with pytest.raises(TestSetError, match="provenance_profile"):
        load_candidates(candidates)

    loaded = load_reviewed_selections(selections)
    assert loaded[0].question_id == "t35-001"
