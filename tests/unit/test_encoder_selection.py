from dataclasses import replace

import pytest

from nl2sparql.linking.encoder_selection import (
    DevelopmentSets,
    EncoderCandidate,
    EncoderSelectionError,
    evaluate_encoder_candidate,
    select_encoder,
)


def _development_sets(**overrides):
    values = {
        "english_path": "data/eval/schema_link_groundtruth.jsonl",
        "english_sha256": "a" * 64,
        "vietnamese_path": "data/eval/schema_link_groundtruth_vi.jsonl",
        "vietnamese_sha256": "b" * 64,
        "unaccented_path": "data/eval/schema_link_groundtruth_vi_unaccented.jsonl",
        "unaccented_sha256": "c" * 64,
    }
    values.update(overrides)
    return DevelopmentSets(**values)


def _candidate(model_id: str = "encoder/a", **overrides):
    values = {
        "model_id": model_id,
        "revision": "d" * 40,
        "artifact_sha256": "e" * 64,
        "license": "apache-2.0",
        "dimension": 384,
        "normalization": "l2",
        "english_metric": 0.80,
        "vietnamese_metric": 0.78,
        "unaccented_metric": 0.75,
        "schema_recall_at_5_en": 0.80,
        "schema_recall_at_5_vi": 0.78,
        "schema_recall_at_10_en": 0.88,
        "schema_recall_at_10_vi": 0.86,
        "schema_mrr_en": 0.76,
        "schema_mrr_vi": 0.74,
        "entity_top1_en": 0.82,
        "entity_top1_vi": 0.79,
        "entity_f1_en": 0.81,
        "entity_f1_vi": 0.78,
        "latency_ms": 12.0,
        "memory_mb": 240.0,
        "cache_size_bytes": 4096,
        "english_baseline": 0.81,
    }
    values.update(overrides)
    return EncoderCandidate(**values)


def test_evaluate_encoder_candidate_binds_revisions_development_hashes_and_metrics():
    score = evaluate_encoder_candidate(_candidate(), _development_sets())

    assert score.model_id == "encoder/a"
    assert score.revision == "d" * 40
    assert score.artifact_sha256 == "e" * 64
    assert score.development_sha256s == ("a" * 64, "b" * 64, "c" * 64)
    assert score.vietnamese_metric == 0.78
    assert score.english_metric == 0.80
    assert score.schema_recall_at_10_vi == 0.86
    assert score.schema_mrr_vi == 0.74
    assert score.entity_f1_vi == 0.78
    assert score.memory_mb == 240.0
    assert score.cache_size_bytes == 4096
    assert score.report_sha256 == score.recompute_sha256()


@pytest.mark.parametrize(
    "mutation",
    (
        {"english_path": "data/dataset/test/test-100.jsonl"},
        {"vietnamese_path": "data/dataset/test/test-100-vi.jsonl"},
        {"unaccented_path": "data/review_drafts/t3_5_vi_candidate_set/cases.jsonl"},
        {"english_sha256": "5d342a5c063ea2d4b5fb7cd62ab15fabb82d2164e5eca5cb248843797989ff0d"},
    ),
)
def test_evaluate_encoder_candidate_rejects_final_benchmark_paths_and_hashes(mutation):
    with pytest.raises(EncoderSelectionError, match="benchmark|held-out"):
        evaluate_encoder_candidate(_candidate(), _development_sets(**mutation))


def test_select_encoder_ranks_vi_then_english_then_latency_then_model_id():
    development = _development_sets()
    scores = tuple(
        evaluate_encoder_candidate(candidate, development)
        for candidate in (
            _candidate("encoder/z", vietnamese_metric=0.79, english_metric=0.80),
            _candidate("encoder/c", vietnamese_metric=0.80, english_metric=0.79),
            _candidate("encoder/b", vietnamese_metric=0.80, english_metric=0.80, latency_ms=13.0),
            _candidate("encoder/a", vietnamese_metric=0.80, english_metric=0.80, latency_ms=12.0),
        )
    )

    selection = select_encoder(scores)

    assert selection.winner_model_id == "encoder/a"
    assert selection.ranked_model_ids == (
        "encoder/a",
        "encoder/b",
        "encoder/c",
        "encoder/z",
    )
    assert selection.selection_rule == "vi_metric,english_metric,latency_ms,model_id"
    assert selection.report_sha256 == selection.recompute_sha256()


def test_select_encoder_rejects_candidates_beyond_english_regression_limit():
    development = _development_sets()
    acceptable = evaluate_encoder_candidate(_candidate("encoder/ok"), development)
    regressed = evaluate_encoder_candidate(
        _candidate("encoder/regressed", english_metric=0.789, english_baseline=0.81),
        development,
    )

    selection = select_encoder((regressed, acceptable), english_regression_limit=0.02)
    assert selection.ranked_model_ids == ("encoder/ok",)
    assert selection.rejected_model_ids == ("encoder/regressed",)

    with pytest.raises(EncoderSelectionError, match="English regression"):
        select_encoder((replace(regressed, report_sha256=regressed.report_sha256),))
