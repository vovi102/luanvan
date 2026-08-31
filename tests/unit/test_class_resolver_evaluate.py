from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nl2sparql.linking.entity import EntityCorpus, GitProvenance, build_entity_corpus
from nl2sparql.linking.resolver import (
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
    ResolverEvaluationError,
    evaluate_resolver,
    load_resolver_ground_truth,
)

ADDRESS = "0x" + "1" * 40
TARGET_ID = f"address:{ADDRESS}"
TARGET_SHA256 = hashlib.sha256(TARGET_ID.encode()).hexdigest()


@pytest.fixture(scope="module")
def corpus() -> EntityCorpus:
    return build_entity_corpus()


def _row(index: int) -> dict[str, object]:
    question = f"transactions to {ADDRESS} case {index:02d}"
    start = question.index(ADDRESS)
    match = {
        "span": ADDRESS,
        "span_offset": [start, start + len(ADDRESS)],
        "target_id": TARGET_ID,
        "target_kind": "address",
        "owner": None,
        "addresses": [ADDRESS],
        "categories": [],
        "concept_classes": [],
        "stage": "address",
        "confidence": 1.0,
        "alternatives": [],
        "target_sha256": TARGET_SHA256,
    }
    expected = {
        "span_offset": [start, start + len(ADDRESS)],
        "target_id": TARGET_ID,
        "resolution_kind": "instance",
        "direction": "to",
        "coverage_status": "supported",
    }
    return {
        "id": f"R{index:02d}",
        "question": question,
        "matches": [match],
        "expected": [expected],
        "expected_status": "resolved",
    }


def _rows(count: int = 50) -> list[dict[str, object]]:
    return [_row(index) for index in range(count)]


def _write_rows(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_ground_truth_requires_exactly_fifty_unique_questions(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    with pytest.raises(ResolverEvaluationError, match="exactly 50"):
        load_resolver_ground_truth(_write_rows(tmp_path / "short.jsonl", _rows(49)), corpus)

    duplicate = _rows()
    duplicate[-1]["question"] = duplicate[0]["question"]
    with pytest.raises(ResolverEvaluationError, match=r"line 50.*duplicate question"):
        load_resolver_ground_truth(_write_rows(tmp_path / "duplicate.jsonl", duplicate), corpus)


def test_ground_truth_rejects_invalid_expected_vocabulary_with_line_context(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    rows = _rows()
    rows[-1]["expected"][0]["direction"] = "sideways"  # type: ignore[index]

    with pytest.raises(ResolverEvaluationError, match=r"line 50.*direction"):
        load_resolver_ground_truth(_write_rows(tmp_path / "bad.jsonl", rows), corpus)


def test_ground_truth_rejects_duplicate_json_keys(tmp_path: Path, corpus: EntityCorpus) -> None:
    valid = json.dumps(_row(0))
    duplicate = valid[:-1] + ', "id": "duplicate"}'
    path = tmp_path / "duplicate-key.jsonl"
    path.write_text(duplicate + "\n", encoding="utf-8")

    with pytest.raises(ResolverEvaluationError, match="duplicate JSON key"):
        load_resolver_ground_truth(path, corpus)


def test_ground_truth_wraps_invalid_alternative_with_line_context(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    rows = _rows()
    rows[0]["matches"][0]["alternatives"] = [  # type: ignore[index]
        {"target_id": "owner:Binance", "target_kind": "invalid", "confidence": 0.5}
    ]

    with pytest.raises(ResolverEvaluationError, match=r"line 1.*alternative"):
        load_resolver_ground_truth(_write_rows(tmp_path / "bad-alternative.jsonl", rows), corpus)


def test_ground_truth_hashes_exact_bytes_and_returns_immutable_types(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    path = _write_rows(tmp_path / "ground-truth.jsonl", _rows())

    dataset = load_resolver_ground_truth(path, corpus)

    assert dataset.ground_truth_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert dataset.entities_sha256 == corpus.entities_sha256
    assert len(dataset.cases) == 50
    assert dataset.cases[0].matches[0].target_id == TARGET_ID
    with pytest.raises(FrozenInstanceError):
        dataset.cases[0].id = "changed"  # type: ignore[misc]


class HandDerivedResolver:
    def __init__(self, dataset, corpus: EntityCorpus) -> None:
        self.dataset = dataset
        self.corpus = corpus
        self.catalog_sha256 = "c" * 64

    def resolve(self, question, matches, schema_links=None) -> ResolutionPlan:
        index = int(question.rsplit(" ", 1)[-1])
        match = matches[0]
        direction = "from" if index < 5 else "to"
        if index < 2:
            concept = self.corpus.targets_by_id["concept:exchange"]
            entity = ResolvedEntity(
                span=match.span,
                span_offset=match.span_offset,
                target_id=concept.target_id,
                target_sha256=concept.document_sha256,
                resolution_kind="concept",
                direction=direction,
                fields=(FieldCandidate("transaction_facts", "to_address"),),
                operator="equals",
                values=concept.concept_classes,
                required_relation="entity_labels_v1",
                required_join="fact_address_to_entity",
                required_role=None,
                coverage_status="coverage_gap",
                confidence=1.0,
                explanation="Hand-derived concept mismatch.",
            )
        else:
            target_id = TARGET_ID if index != 5 else "address:0x" + "2" * 40
            value = ADDRESS if index != 5 else "0x" + "2" * 40
            entity = ResolvedEntity(
                span=match.span,
                span_offset=match.span_offset,
                target_id=target_id,
                target_sha256=hashlib.sha256(target_id.encode()).hexdigest(),
                resolution_kind="instance",
                direction=direction,
                fields=(FieldCandidate("transaction_facts", "to_address"),),
                operator="in",
                values=(value,),
                required_relation=None,
                required_join=None,
                required_role=None,
                coverage_status="supported",
                confidence=1.0,
                explanation="Hand-derived instance prediction.",
            )
        return ResolutionPlan(
            question_sha256=hashlib.sha256(question.encode()).hexdigest(),
            entities=(entity,),
            catalog_sha256=self.catalog_sha256,
            entities_sha256=self.corpus.entities_sha256,
            aliases_sha256=self.corpus.aliases_sha256,
            concepts_sha256=self.corpus.concepts_sha256,
            status="resolved",
            warnings=(),
        )


def test_evaluator_reports_hand_derived_metrics(tmp_path: Path, corpus: EntityCorpus) -> None:
    dataset = load_resolver_ground_truth(
        _write_rows(tmp_path / "ground-truth.jsonl", _rows()), corpus
    )

    report = evaluate_resolver(
        HandDerivedResolver(dataset, corpus),
        dataset,
        GitProvenance("1" * 40, False),
    )

    assert report.case_count == 50
    assert report.entity_count == 50
    assert report.resolution_kind_accuracy == pytest.approx(48 / 50)
    assert report.direction_accuracy == pytest.approx(45 / 50)
    assert report.fully_resolved_plan_accuracy == pytest.approx(44 / 50)
    assert report.coverage_gap_count == 2
    assert report.ready is False
    assert report.catalog_sha256 == "c" * 64
    assert report.ground_truth_sha256 == dataset.ground_truth_sha256
    assert report.git_sha == "1" * 40


def test_evaluator_rejects_non_dataset_and_missing_git_provenance(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    dataset = load_resolver_ground_truth(
        _write_rows(tmp_path / "ground-truth.jsonl", _rows()), corpus
    )
    resolver = HandDerivedResolver(dataset, corpus)

    with pytest.raises(ResolverEvaluationError, match="dataset"):
        evaluate_resolver(resolver, object(), GitProvenance("1" * 40, False))  # type: ignore[arg-type]
    with pytest.raises(ResolverEvaluationError, match="git provenance"):
        evaluate_resolver(resolver, dataset, None)  # type: ignore[arg-type]
