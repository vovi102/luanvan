from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nl2sparql.models.b12 import (
    Completion,
    GenerationConfig,
    SmallLLMError,
    SmallLLMPrediction,
)


def _completion(
    raw_text: str = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
) -> Completion:
    return Completion(
        raw_text=raw_text,
        model_id="meta-llama/Meta-Llama-3-8B-Instruct",
        model_revision="a" * 40,
        input_tokens=17,
        output_tokens=11,
    )


def test_generation_config_is_immutable_and_fingerprint_bound() -> None:
    config = GenerationConfig(model_revision="a" * 40)

    assert config.model_id == "meta-llama/Meta-Llama-3-8B-Instruct"
    assert config.seed == 42
    assert config.do_sample is False
    assert config.max_new_tokens == 512
    assert len(config.sha256) == 64
    with pytest.raises(FrozenInstanceError):
        config.seed = 7  # type: ignore[misc]


def test_generation_config_rejects_unpinned_revision() -> None:
    with pytest.raises(SmallLLMError, match="revision"):
        GenerationConfig(model_revision="main")


def test_prediction_rejects_ok_status_without_sql() -> None:
    with pytest.raises(SmallLLMError, match="ok prediction"):
        SmallLLMPrediction(
            baseline="b1",
            question="Count transactions",
            raw_output="not sql",
            sql=None,
            extraction_status="ok",
            completion=_completion("not sql"),
            catalog_sha256="b" * 64,
            summary_sha256="c" * 64,
            prompt_sha256="d" * 64,
            config_sha256="e" * 64,
            latency_ms=1.0,
        )


def test_b1_prediction_rejects_b2_provenance() -> None:
    with pytest.raises(SmallLLMError, match="B1 prediction"):
        SmallLLMPrediction(
            baseline="b1",
            question="Count transactions",
            raw_output="",
            sql=None,
            extraction_status="empty",
            completion=_completion(""),
            catalog_sha256="b" * 64,
            summary_sha256="c" * 64,
            prompt_sha256="d" * 64,
            config_sha256="e" * 64,
            latency_ms=1.0,
            training_sha256="f" * 64,
            encoder_id="sentence-transformers/all-MiniLM-L6-v2",
            encoder_revision="1" * 40,
        )


def test_completion_rejects_boolean_token_count() -> None:
    with pytest.raises(SmallLLMError, match="token counts"):
        Completion(
            raw_text="",
            model_id="meta-llama/Meta-Llama-3-8B-Instruct",
            model_revision="a" * 40,
            input_tokens=True,  # type: ignore[arg-type]
            output_tokens=0,
        )
