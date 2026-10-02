"""Repository acceptance test for the agent-authored T3.5 review pack."""

from collections import Counter
from pathlib import Path

from nl2sparql.dataset.testset.reviewed_artifacts import read_reviewed_live_evidence
from nl2sparql.dataset.testset.reviewed_contracts import (
    ReviewedTestSetPaths,
    load_candidates,
    load_review_events,
    load_reviewed_selections,
)
from nl2sparql.dataset.testset.reviewed_validate import (
    load_reviewed_bundle,
    validate_candidate_pack,
    validate_reviewed_selection,
)
from nl2sparql.evaluation.adapters.common import load_authoritative_test_set

REPOSITORY = Path(__file__).resolve().parents[2]
DRAFT_ROOT = REPOSITORY / "data/review_drafts/t3_5_candidate_set_2026-09-27"
FINAL_ROOT = REPOSITORY / "data/dataset/test"
CATALOG = REPOSITORY / "src/nl2sparql/sql/catalog/ethereum_analytics.json"


def test_repository_t35_benchmark_is_reviewed_live_verified_and_finalized() -> None:
    paths = ReviewedTestSetPaths.from_roots(DRAFT_ROOT, FINAL_ROOT)

    report = validate_candidate_pack(
        paths.candidates,
        repo_root=REPOSITORY,
        catalog_path=CATALOG,
    )
    candidates = load_candidates(paths.candidates)

    assert report.status == "draft_ready"
    assert tuple(row.question_id for row in candidates) == tuple(
        f"t35-{index:03d}" for index in range(1, 121)
    )
    assert Counter(row.difficulty for row in candidates) == {
        "easy": 36,
        "medium": 60,
        "hard": 24,
    }
    events = load_review_events(paths.review_events)
    selections = load_reviewed_selections(paths.final_selection)
    assert len(events) == 120
    assert {event.decision for event in events} == {"ACCEPT"}
    assert len(selections) == 100
    assert Counter(selection.final_difficulty for selection in selections) == {
        "easy": 30,
        "medium": 50,
        "hard": 20,
    }
    review = validate_reviewed_selection(
        load_reviewed_bundle(paths),
        repo_root=REPOSITORY,
        catalog_path=CATALOG,
    )
    assert review.status == "review_ready"
    assert review.selected_count == 100
    evidence = read_reviewed_live_evidence(paths.live_evidence)
    assert evidence.execution.status == "ready"
    assert len(evidence.execution.records) == 100
    assert evidence.policy.per_query_bytes == 24 * 2**30
    assert evidence.policy.total_bytes == 600 * 2**30
    authoritative = load_authoritative_test_set(paths.final_jsonl, synthetic=False)
    assert len(authoritative.cases) == 100
    assert authoritative.reviewed is True
    assert authoritative.live_verified is True
    assert paths.review_guide.is_file()
    assert paths.final_manifest.is_file()
