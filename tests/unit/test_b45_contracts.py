from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from nl2sparql.models.b45.contracts import (
    LargeLLMConfig,
    LargeLLMError,
    LargeLLMPrediction,
    ProviderPolicy,
    RemoteCompletion,
    canonical_money,
)


def policy() -> ProviderPolicy:
    return ProviderPolicy(
        provider_slug="deepinfra",
        prompt_price_per_million_usd=Decimal("0.50"),
        completion_price_per_million_usd=Decimal("1.00"),
    )


def test_config_is_pinned_and_self_fingerprinting() -> None:
    config = LargeLLMConfig(provider=policy())
    assert config.model_id == "meta-llama/llama-3.3-70b-instruct"
    assert config.temperature == Decimal("0")
    assert config.seed == 42
    assert config.max_tokens == 512
    assert config.max_cost_usd == Decimal("20.00")
    assert len(config.sha256) == 64
    with pytest.raises(FrozenInstanceError):
        config.seed = 7  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_id", "openrouter/auto", "model_id"),
        ("temperature", Decimal("0.1"), "temperature"),
        ("seed", 7, "seed"),
        ("max_tokens", 513, "max_tokens"),
        ("max_cost_usd", Decimal("20.01"), "at most USD 20"),
    ],
)
def test_config_rejects_scientific_drift(field, value, message) -> None:
    with pytest.raises(LargeLLMError, match=message):
        replace(LargeLLMConfig(provider=policy()), **{field: value})


def test_completion_is_synthetic_by_default_and_cannot_be_relabelled() -> None:
    completion = RemoteCompletion.synthetic(
        raw_text="SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
        model_id="meta-llama/llama-3.3-70b-instruct",
        provider_slug="scripted",
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=Decimal("0"),
        latency_ms=1.0,
    )
    assert completion.synthetic_backend is True
    with pytest.raises(TypeError):
        RemoteCompletion(  # type: ignore[call-arg]
            raw_text="x", synthetic_backend=False
        )
    with pytest.raises((TypeError, ValueError)):
        replace(completion, synthetic_backend=False)
    assert completion.synthetic_backend is True


def test_completion_rejects_noncanonical_model_id() -> None:
    with pytest.raises(LargeLLMError, match="model_id"):
        RemoteCompletion.synthetic(
            raw_text="SELECT 1",
            model_id="openrouter/auto",
            provider_slug="scripted",
            input_tokens=1,
            output_tokens=1,
            charged_cost_usd=Decimal("0"),
            latency_ms=1.0,
        )


def test_money_and_config_fingerprint_are_decimal_canonical() -> None:
    first = LargeLLMConfig(provider=policy())
    second = LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.5000"),
            completion_price_per_million_usd=Decimal("1.000"),
        ),
        max_cost_usd=Decimal("20.000"),
        timeout_seconds=Decimal("60.0"),
    )

    assert canonical_money(Decimal("1.2300")) == "1.23"
    assert canonical_money(Decimal("-0.00")) == "0"
    assert first.sha256 == second.sha256


@pytest.mark.parametrize(
    "price",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")],
)
def test_provider_rejects_invalid_price_ceiling(price: Decimal) -> None:
    with pytest.raises(LargeLLMError, match="price"):
        ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=price,
            completion_price_per_million_usd=Decimal("1.00"),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"input_tokens": True}, "token"),
        ({"charged_cost_usd": Decimal("-0.01")}, "cost"),
        ({"latency_ms": float("nan")}, "latency"),
        ({"attempt_count": 0}, "attempt"),
    ],
)
def test_completion_rejects_invalid_accounting(kwargs, message) -> None:
    values = {
        "raw_text": "SELECT 1",
        "model_id": "meta-llama/llama-3.3-70b-instruct",
        "provider_slug": "scripted",
        "input_tokens": 1,
        "output_tokens": 1,
        "charged_cost_usd": Decimal("0"),
        "latency_ms": 1.0,
    }
    values.update(kwargs)
    with pytest.raises(LargeLLMError, match=message):
        RemoteCompletion.synthetic(**values)


def _completion(raw_text: str = "SELECT 1") -> RemoteCompletion:
    return RemoteCompletion.synthetic(
        raw_text=raw_text,
        model_id="meta-llama/llama-3.3-70b-instruct",
        provider_slug="scripted",
        input_tokens=1,
        output_tokens=1,
        charged_cost_usd=Decimal("0"),
        latency_ms=1.0,
    )


def _prediction(**kwargs) -> LargeLLMPrediction:
    values = {
        "baseline": "b4",
        "question": "List labels",
        "raw_output": "SELECT 1",
        "sql": "SELECT 1",
        "extraction_status": "ok",
        "completion": _completion(),
        "catalog_sha256": "a" * 64,
        "summary_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "latency_ms": 1.0,
    }
    values.update(kwargs)
    return LargeLLMPrediction(**values)


def test_b4_rejects_b5_provenance() -> None:
    with pytest.raises(LargeLLMError, match="B4 prediction"):
        _prediction(training_sha256="e" * 64)


def test_prediction_requires_raw_output_to_match_completion() -> None:
    with pytest.raises(LargeLLMError, match="raw output"):
        _prediction(raw_output="SELECT 2")


def test_prediction_rejects_control_characters_in_safe_sql() -> None:
    with pytest.raises(LargeLLMError, match="SQL"):
        _prediction(sql="SELECT\x001")


def test_prediction_rejects_non_completion_provenance() -> None:
    with pytest.raises(LargeLLMError, match="completion"):
        _prediction(completion=object())


def test_b5_requires_exactly_five_unique_selected_examples() -> None:
    from nl2sparql.models.b12.contracts import SelectedExample

    examples = tuple(
        SelectedExample(
            record_id=f"train-{number}",
            question=f"Question {number}",
            sql="SELECT 1",
            score=1.0 - number / 10,
        )
        for number in range(5)
    )
    result = _prediction(
        baseline="b5",
        training_sha256="e" * 64,
        encoder_id="sentence-transformers/all-MiniLM-L6-v2",
        encoder_revision="f" * 40,
        selected_examples=examples,
    )

    assert result.selected_examples == examples
    with pytest.raises(LargeLLMError, match="exactly five"):
        _prediction(
            baseline="b5",
            training_sha256="e" * 64,
            encoder_id="sentence-transformers/all-MiniLM-L6-v2",
            encoder_revision="f" * 40,
            selected_examples=examples[:4],
        )
