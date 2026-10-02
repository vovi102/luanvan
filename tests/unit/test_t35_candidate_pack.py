"""Repository acceptance test for the agent-authored T3.5 review pack."""

from collections import Counter
from pathlib import Path

from nl2sparql.dataset.testset.reviewed_contracts import (
    ReviewedTestSetPaths,
    load_candidates,
    load_review_events,
    load_reviewed_selections,
)
from nl2sparql.dataset.testset.reviewed_validate import validate_candidate_pack

REPOSITORY = Path(__file__).resolve().parents[2]
DRAFT_ROOT = REPOSITORY / "data/review_drafts/t3_5_candidate_set_2026-09-27"
FINAL_ROOT = REPOSITORY / "data/dataset/test"
CATALOG = REPOSITORY / "src/nl2sparql/sql/catalog/ethereum_analytics.json"


def test_repository_t35_candidate_pack_is_draft_ready() -> None:
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
    assert load_review_events(paths.review_events) == ()
    assert load_reviewed_selections(paths.final_selection) == ()
    assert paths.review_guide.is_file()
    assert not paths.final_jsonl.exists()
