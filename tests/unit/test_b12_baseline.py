from __future__ import annotations

import hashlib

import pytest

from nl2sparql.models.b12 import (
    BaselineB1,
    BaselineB2,
    CatalogSummary,
    Completion,
    GenerationConfig,
    SelectedExample,
    SmallLLMError,
)

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


def _summary() -> CatalogSummary:
    text = "CATALOG\nRelation entity_labels_v1\n"
    return CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


class ScriptedBackend:
    def __init__(
        self,
        raw_text: str,
        *,
        model_id: str = "meta-llama/Meta-Llama-3-8B-Instruct",
        model_revision: str = "b" * 40,
    ) -> None:
        self.raw_text = raw_text
        self.model_id = model_id
        self.model_revision = model_revision
        self.calls = 0

    def generate(self, messages, config):
        self.calls += 1
        return Completion(
            raw_text=self.raw_text,
            model_id=self.model_id,
            model_revision=self.model_revision,
            input_tokens=17,
            output_tokens=11,
            synthetic_backend=True,
        )


class BombBackend:
    def generate(self, messages, config):
        raise AssertionError("backend must not be called")


class StaticRetriever:
    training_sha256 = "c" * 64
    encoder_id = "sentence-transformers/all-MiniLM-L6-v2"
    encoder_revision = "d" * 40

    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, question: str, *, target_id: str | None = None):
        self.calls += 1
        return tuple(
            SelectedExample(
                record_id=f"train-{index:03d}",
                question=f"Question {index}",
                sql=SAFE_SQL,
                score=1.0 - index / 10,
            )
            for index in range(1, 6)
        )


def _clock(*values: int):
    iterator = iter(values)
    return lambda: next(iterator)


def test_b1_returns_safe_sql_and_full_provenance() -> None:
    config = GenerationConfig("b" * 40)
    baseline = BaselineB1(
        _summary(),
        config,
        ScriptedBackend(SAFE_SQL),
        clock_ns=_clock(1_000_000, 3_500_000),
    )

    result = baseline.predict_detailed("Count transactions")

    assert result.baseline == "b1"
    assert result.sql == SAFE_SQL
    assert result.extraction_status == "ok"
    assert result.selected_examples == ()
    assert result.completion.synthetic_backend is True
    assert result.latency_ms == 2.5
    assert result.config_sha256 == config.sha256


def test_b2_uses_exactly_retrieved_examples() -> None:
    retriever = StaticRetriever()
    baseline = BaselineB2(
        _summary(),
        GenerationConfig("b" * 40),
        ScriptedBackend(SAFE_SQL),
        retriever,
        clock_ns=_clock(0, 1_000_000),
    )

    result = baseline.predict_detailed("Count transactions", target_id="test-001")

    assert result.baseline == "b2"
    assert len(result.selected_examples) == 5
    assert result.training_sha256 == retriever.training_sha256
    assert result.encoder_id == retriever.encoder_id
    assert result.encoder_revision == retriever.encoder_revision


def test_invalid_question_fails_before_retrieval_or_generation() -> None:
    retriever = StaticRetriever()
    baseline = BaselineB2(_summary(), GenerationConfig("b" * 40), BombBackend(), retriever)

    with pytest.raises(SmallLLMError, match="question"):
        baseline.predict_detailed("\x00", target_id="test-001")
    assert retriever.calls == 0


def test_backend_model_identity_must_match_config() -> None:
    baseline = BaselineB1(
        _summary(),
        GenerationConfig("b" * 40),
        ScriptedBackend(SAFE_SQL, model_revision="e" * 40),
    )

    with pytest.raises(SmallLLMError, match="identity"):
        baseline.predict_detailed("Count transactions")


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("", "empty"),
        ("Here is SQL: " + SAFE_SQL, "prose"),
        ("SELECT FROM", "invalid_sql"),
    ],
)
def test_failed_extraction_retains_raw_output_and_predict_returns_none(
    raw: str, status: str
) -> None:
    detailed = BaselineB1(
        _summary(), GenerationConfig("b" * 40), ScriptedBackend(raw)
    ).predict_detailed("Count transactions")
    compatibility = BaselineB1(
        _summary(), GenerationConfig("b" * 40), ScriptedBackend(raw)
    ).predict("Count transactions")

    assert detailed.raw_output == raw
    assert detailed.extraction_status == status
    assert detailed.sql is None
    assert compatibility is None


def test_backend_failure_is_wrapped_as_inference_error() -> None:
    class FailingBackend:
        def generate(self, messages, config):
            raise RuntimeError("GPU unavailable")

    baseline = BaselineB1(_summary(), GenerationConfig("b" * 40), FailingBackend())

    with pytest.raises(SmallLLMError, match="generation failed.*GPU unavailable"):
        baseline.predict_detailed("Count transactions")
