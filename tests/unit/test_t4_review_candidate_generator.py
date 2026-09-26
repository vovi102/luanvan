"""Regression checks for the human-review T4 candidate generator."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "generate_t4_review_candidates.py"
SPEC = importlib.util.spec_from_file_location("t4_review_candidates", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_review_template_preserves_reviewed_rows_and_reopens_replacements(tmp_path: Path) -> None:
    decisions_path = tmp_path / "review_decisions.csv"
    with decisions_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["component", "id", "decision", "reviewer_note"])
        writer.writeheader()
        writer.writerow(
            {
                "component": "schema_linker",
                "id": "schema-candidate-01",
                "decision": "REVISE",
                "reviewer_note": "Remove transaction_hash.",
            }
        )
        writer.writerow(
            {
                "component": "class_resolver",
                "id": "resolver-candidate-36",
                "decision": "REJECT",
                "reviewer_note": "Replace with a distinct case.",
            }
        )

    rows = [
        {"component": "schema_linker", "id": "schema-candidate-01"},
        {"component": "class_resolver", "id": "resolver-candidate-36"},
    ]
    MODULE._write_review_template(decisions_path, rows, {"resolver-candidate-36"})

    with decisions_path.open(newline="", encoding="utf-8") as stream:
        saved = {row["id"]: row for row in csv.DictReader(stream)}
    assert saved["schema-candidate-01"]["decision"] == "REVISE"
    assert saved["schema-candidate-01"]["reviewer_note"] == "Remove transaction_hash."
    assert saved["resolver-candidate-36"]["decision"] == ""
    assert saved["resolver-candidate-36"]["reviewer_note"] == ""


def test_resolver_candidates_use_unique_questions() -> None:
    artifacts = MODULE.DictionaryArtifacts(
        MODULE.ENTITIES_PATH,
        MODULE.CONCEPTS_PATH,
        MODULE.ALIASES_PATH,
        MODULE.SOURCES_PATH,
    )
    corpus = MODULE.build_entity_corpus(artifacts)
    rows = MODULE._resolver_cases(corpus, MODULE._choose_owner_targets(corpus))

    assert len({row["question"] for row in rows}) == 50


def test_resolver_replacements_cover_the_approved_edge_case_groups() -> None:
    artifacts = MODULE.DictionaryArtifacts(
        MODULE.ENTITIES_PATH,
        MODULE.CONCEPTS_PATH,
        MODULE.ALIASES_PATH,
        MODULE.SOURCES_PATH,
    )
    corpus = MODULE.build_entity_corpus(artifacts)
    rows = MODULE._resolver_cases(corpus, MODULE._choose_owner_targets(corpus))
    by_id = {row["id"]: row for row in rows}

    ambiguous = [by_id[f"resolver-candidate-{index:02d}"] for index in range(36, 39)]
    assert all(row["matches"][0]["stage"] == "ambiguous" for row in ambiguous)
    assert all(row["expected_status"] == "unresolved" for row in ambiguous)

    direction_edges = [by_id[f"resolver-candidate-{index:02d}"] for index in range(39, 42)]
    assert all(len(row["matches"]) == 1 for row in direction_edges)
    assert all(row["expected"][0]["direction"] == "unspecified" for row in direction_edges)

    multi_mentions = [by_id[f"resolver-candidate-{index:02d}"] for index in range(42, 45)]
    assert all(len(row["matches"]) >= 2 for row in multi_mentions)

    raw_addresses = [by_id[f"resolver-candidate-{index:02d}"] for index in range(45, 48)]
    assert all(row["matches"][0]["target_kind"] == "address" for row in raw_addresses)

    concept_paraphrases = [by_id[f"resolver-candidate-{index:02d}"] for index in range(48, 51)]
    assert all(row["matches"][0]["target_kind"] == "concept" for row in concept_paraphrases)
    assert all(row["expected"][0]["direction"] != "unspecified" for row in concept_paraphrases)
    assert all("review case" not in row["question"].casefold() for row in rows)
