from __future__ import annotations

import hashlib

import pytest

from nl2sparql.models.b12 import (
    BaselineB1,
    CatalogSummary,
    Completion,
    EvaluationCase,
    GenerationConfig,
    SmallLLMError,
    compare_reproducibility,
    evaluate_baseline,
)

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


class SequenceBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)

    def generate(self, messages, config):
        raw = next(self.outputs)
        return Completion(
            raw_text=raw,
            model_id=config.model_id,
            model_revision=config.model_revision,
            input_tokens=10,
            output_tokens=5,
        )


def _summary() -> CatalogSummary:
    text = "CATALOG\nRelation entity_labels_v1\n"
    return CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def _cases() -> tuple[EvaluationCase, ...]:
    return (
        EvaluationCase(
            case_id="test-001",
            question="List known addresses",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
        ),
        EvaluationCase(
            case_id="test-002",
            question="List addresses again",
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup", "ranking"),
        ),
    )


def _clock():
    values = iter([0, 1_000_000, 2_000_000, 5_000_000])
    return lambda: next(values)


def test_evaluator_preserves_case_order_and_operational_counts() -> None:
    baseline = BaselineB1(
        _summary(),
        GenerationConfig("b" * 40),
        SequenceBackend([SAFE_SQL, "Here is SQL: " + SAFE_SQL]),
        clock_ns=_clock(),
    )

    run = evaluate_baseline(_cases(), baseline, run_id="run-001")

    assert [row.case_id for row in run.predictions] == ["test-001", "test-002"]
    assert run.metrics.total == 2
    assert run.metrics.generated == 2
    assert run.metrics.extraction_ok == 1
    assert run.metrics.extraction_failed == 1
    assert run.metrics.p50_latency_ms == 2.0
    assert run.metrics.p95_latency_ms == pytest.approx(2.9)
    assert run.metrics.input_tokens == 20
    assert run.metrics.output_tokens == 10
    assert dict(run.metrics.status_counts) == {"ok": 1, "prose": 1}
    assert dict(run.metrics.difficulty_counts) == {"easy": 1, "medium": 1}
    assert dict(run.metrics.category_counts) == {"entity_lookup": 2, "ranking": 1}
    assert run.scientific_ready is False


def test_fake_backend_can_never_be_scientifically_ready() -> None:
    baseline = BaselineB1(
        _summary(),
        GenerationConfig("b" * 40),
        SequenceBackend([SAFE_SQL, SAFE_SQL]),
        clock_ns=_clock(),
    )

    run = evaluate_baseline(_cases(), baseline, run_id="run-001", reviewed=True, live_verified=True)

    assert run.scientific_ready is False
    assert "synthetic_backend" in run.blockers
    assert "synthetic_test_set" in run.blockers
    assert "expected_100_cases" in run.blockers


def test_caller_cannot_claim_a_genuine_completion() -> None:
    with pytest.raises(TypeError, match="synthetic_backend"):
        Completion(
            raw_text=SAFE_SQL,
            model_id="meta-llama/Meta-Llama-3-8B-Instruct",
            model_revision="b" * 40,
            input_tokens=10,
            output_tokens=5,
            synthetic_backend=False,  # type: ignore[call-arg]
        )


def test_manually_constructed_cases_cannot_be_promoted() -> None:
    baseline = BaselineB1(
        _summary(),
        GenerationConfig("b" * 40),
        SequenceBackend([SAFE_SQL, SAFE_SQL]),
        clock_ns=_clock(),
    )

    run = evaluate_baseline(_cases(), baseline, run_id="run-001")

    assert run.scientific_ready is False
    assert "synthetic_test_set" in run.blockers
    assert "trusted_test_set_provenance_missing" in run.blockers


def test_evaluation_case_rejects_unsafe_gold_sql() -> None:
    with pytest.raises(SmallLLMError, match="gold SQL"):
        EvaluationCase(
            case_id="test-001",
            question="Delete data",
            gold_sql="DELETE FROM x",
            difficulty="easy",
            categories=("mutation",),
        )


def test_evaluator_rejects_duplicate_case_ids() -> None:
    baseline = BaselineB1(_summary(), GenerationConfig("b" * 40), SequenceBackend([SAFE_SQL]))

    with pytest.raises(SmallLLMError, match="duplicate"):
        evaluate_baseline((_cases()[0], _cases()[0]), baseline, run_id="run-001")


def test_reproducibility_compares_case_identity_and_observable_output() -> None:
    first = evaluate_baseline(
        _cases(),
        BaselineB1(
            _summary(),
            GenerationConfig("b" * 40),
            SequenceBackend([SAFE_SQL, SAFE_SQL]),
            clock_ns=_clock(),
        ),
        run_id="run-001",
    )
    same = evaluate_baseline(
        _cases(),
        BaselineB1(
            _summary(),
            GenerationConfig("b" * 40),
            SequenceBackend([SAFE_SQL, SAFE_SQL]),
            clock_ns=_clock(),
        ),
        run_id="run-002",
    )
    changed = evaluate_baseline(
        _cases(),
        BaselineB1(
            _summary(),
            GenerationConfig("b" * 40),
            SequenceBackend([SAFE_SQL, ""]),
            clock_ns=_clock(),
        ),
        run_id="run-003",
    )

    assert compare_reproducibility(first, same) is True
    assert compare_reproducibility(first, changed) is False
