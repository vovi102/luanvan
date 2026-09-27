"""Tests for T3.5 candidate quality, catalog, and leakage validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.reviewed_contracts import AGENT_REVIEWED_PROFILE
from nl2sparql.dataset.testset.reviewed_validate import (
    canonical_leakage_paths,
    validate_candidate_pack,
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


def _candidate_rows(catalog_sha256: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(1, 121):
        difficulty = "easy" if index <= 36 else "medium" if index <= 96 else "hard"
        rows.append(
            {
                "schema_version": "1.0.0",
                "provenance_profile": AGENT_REVIEWED_PROFILE,
                "question_id": f"t35-{index:03d}",
                "author_type": "agent",
                "nl": f"Candidate question {index:03d} about June transaction activity?",
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
                "rationale": f"Hand-checked fixture rationale {index:03d}.",
                "generation_batch": "t35-agent-batch-01",
                "catalog_sha256": catalog_sha256,
                "source_commit": "b" * 40,
            }
        )
    return rows


def _write_pack(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _valid_pack(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    catalog_sha256 = hashlib.sha256(CATALOG.read_bytes()).hexdigest()
    rows = _candidate_rows(catalog_sha256)
    path = tmp_path / "candidates.jsonl"
    _write_pack(path, rows)
    return path, rows


def test_validate_candidate_pack_accepts_exact_counts_and_coverage(tmp_path: Path) -> None:
    path, _ = _valid_pack(tmp_path)

    report = validate_candidate_pack(path, repo_root=tmp_path, catalog_path=CATALOG)

    assert report.status == "draft_ready"
    assert report.provenance_profile == AGENT_REVIEWED_PROFILE
    assert report.candidate_count == 120
    assert report.difficulty_counts == (("easy", 36), ("hard", 24), ("medium", 60))
    assert report.category_count == 6
    assert report.entity_kind_count == 3
    assert report.candidate_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report.catalog_sha256 == hashlib.sha256(CATALOG.read_bytes()).hexdigest()
    assert report.source_commit == "b" * 40


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing_id", "IDs"),
        ("duplicate_nl", "normalized"),
        ("quota", "difficulty"),
        ("unsafe_sql", "read-only"),
        ("alias", "expected_columns"),
        ("schema", "schema"),
        ("cq", "CQ"),
        ("categories", "categories"),
        ("entity_kinds", "entity kinds"),
        ("catalog_hash", "catalog_sha256"),
        ("source_commit", "source_commit"),
    ),
)
def test_validate_candidate_pack_rejects_invalid_quality_inputs(
    tmp_path: Path, mutation: str, message: str
) -> None:
    path, rows = _valid_pack(tmp_path)
    if mutation == "missing_id":
        rows[0]["question_id"] = "t35-999"
    elif mutation == "duplicate_nl":
        rows[1]["nl"] = "  candidate   question 001 ABOUT june transaction activity?  "
    elif mutation == "quota":
        rows[35]["difficulty"] = "medium"
    elif mutation == "unsafe_sql":
        rows[0]["sql"] = "DELETE FROM dataset.table WHERE TRUE"
    elif mutation == "alias":
        rows[0]["expected_columns"] = ["wrong_alias"]
    elif mutation == "schema":
        rows[0]["schema_elements"] = ["unknown_relation"]
    elif mutation == "cq":
        rows[0]["cq_ids"] = ["CQ999"]
    elif mutation == "categories":
        for row in rows:
            row["categories"] = ["simple_filter"]
    elif mutation == "entity_kinds":
        for row in rows:
            row["entity_kinds"] = ["address_only"]
    elif mutation == "catalog_hash":
        rows[0]["catalog_sha256"] = "c" * 64
    elif mutation == "source_commit":
        rows[0]["source_commit"] = "short"
    _write_pack(path, rows)

    with pytest.raises(TestSetError, match=message):
        validate_candidate_pack(path, repo_root=tmp_path, catalog_path=CATALOG)


def test_validate_candidate_pack_rejects_normalized_leakage_from_jsonl_csv_and_json(
    tmp_path: Path,
) -> None:
    path, rows = _valid_pack(tmp_path)
    leaked = "Existing leakage question"
    rows[0]["nl"] = "  existing   LEAKAGE question  "
    _write_pack(path, rows)
    dataset = tmp_path / "data" / "dataset"
    dataset.mkdir(parents=True)
    (dataset / "stage-a.jsonl").write_text(
        json.dumps({"nl_seed": leaked}) + "\n" + json.dumps({"metadata": 1}) + "\n",
        encoding="utf-8",
    )
    evaluation = tmp_path / "data" / "eval"
    evaluation.mkdir(parents=True)
    (evaluation / "questions.csv").write_text(
        "id,question\nq1,Another prior question\n", encoding="utf-8"
    )
    review = tmp_path / "data" / "review_drafts" / "t4_candidate_set_2026-09-24"
    review.mkdir(parents=True)
    (review / "questions.json").write_text(
        json.dumps([{"question": "A T4 question"}, {"unrelated": True}]), encoding="utf-8"
    )

    with pytest.raises(TestSetError, match="leakage"):
        validate_candidate_pack(path, repo_root=tmp_path, catalog_path=CATALOG)

    discovered = canonical_leakage_paths(tmp_path)
    assert discovered == tuple(sorted(discovered, key=lambda item: item.as_posix()))
    assert {item.name for item in discovered} == {
        "questions.csv",
        "questions.json",
        "stage-a.jsonl",
    }


@pytest.mark.parametrize("kind", ("utf8", "json", "csv"))
def test_validate_candidate_pack_fails_closed_on_malformed_leakage(
    tmp_path: Path, kind: str
) -> None:
    path, _ = _valid_pack(tmp_path)
    root = tmp_path / "data" / "dataset"
    root.mkdir(parents=True)
    malformed = root / f"malformed.{kind if kind != 'utf8' else 'jsonl'}"
    if kind == "utf8":
        malformed.write_bytes(b"\xff")
    elif kind == "json":
        malformed.write_text("{", encoding="utf-8")
    else:
        malformed.write_text('question\n"unterminated\n', encoding="utf-8")

    with pytest.raises(TestSetError, match="malformed"):
        validate_candidate_pack(path, repo_root=tmp_path, catalog_path=CATALOG)
