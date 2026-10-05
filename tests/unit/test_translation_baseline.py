import hashlib
from dataclasses import dataclass
from decimal import Decimal

import pytest

from nl2sparql.baselines.translation import (
    TranslationBaselineError,
    TranslationConfig,
    TranslationFirstBaseline,
    TranslatorOutcome,
)
from nl2sparql.evaluation.contracts import CostEvidence, PrivacyEvidence

REVISION = "a" * 40
SHA_A = "a" * 64
SHA_B = "b" * 64


def _cost() -> CostEvidence:
    return CostEvidence("observed", Decimal("0.0020"), "USD", "translator-meter")


def _privacy() -> PrivacyEvidence:
    return PrivacyEvidence("documented", "provider", "translator.example", SHA_A, SHA_B)


class ScriptedTranslator:
    def __init__(self, outcome: TranslatorOutcome | Exception) -> None:
        self.config = TranslationConfig(
            translator_id="translator-v1",
            model_id="translation-model",
            model_revision=REVISION,
            settings_sha256=SHA_A,
        )
        self.outcome = outcome
        self.calls: list[tuple[str, str]] = []

    def translate(self, question: str, *, request_id: str) -> TranslatorOutcome:
        self.calls.append((question, request_id))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@dataclass(frozen=True)
class EnglishPrediction:
    sql: str | None
    extraction_status: str


class ScriptedPredictor:
    def __init__(self, prediction: EnglishPrediction | Exception) -> None:
        self.prediction = prediction
        self.calls: list[str] = []

    def predict_detailed(self, question: str) -> EnglishPrediction:
        self.calls.append(question)
        if isinstance(self.prediction, Exception):
            raise self.prediction
        return self.prediction


class ScriptedClock:
    def __init__(self, *values: int) -> None:
        self.values = iter(values)

    def __call__(self) -> int:
        return next(self.values)


def test_translation_first_records_pinned_hash_bound_evidence_and_latency() -> None:
    translated = "How many transactions are there?"
    translator = ScriptedTranslator(TranslatorOutcome("ok", translated, _cost(), _privacy()))
    predictor = ScriptedPredictor(EnglishPrediction("SELECT COUNT(*) FROM `p.d.t`", "ok"))
    baseline = TranslationFirstBaseline(
        translator,
        predictor,
        clock_ns=ScriptedClock(1_000_000, 4_000_000, 11_000_000),
    )

    prediction = baseline.predict_detailed("Có bao nhiêu giao dịch?", request_id="req-001")

    assert prediction.status == "ok"
    assert prediction.sql == "SELECT COUNT(*) FROM `p.d.t`"
    assert prediction.translated_question == translated
    assert predictor.calls == [translated]
    assert prediction.evidence.request_id == "req-001"
    assert prediction.evidence.translator_id == "translator-v1"
    assert prediction.evidence.model_id == "translation-model"
    assert prediction.evidence.model_revision == REVISION
    assert prediction.evidence.config_sha256 == translator.config.sha256
    assert (
        prediction.evidence.original_text_sha256
        == hashlib.sha256("Có bao nhiêu giao dịch?".encode()).hexdigest()
    )
    assert prediction.evidence.translated_text == translated
    assert (
        prediction.evidence.translated_text_sha256
        == hashlib.sha256(translated.encode()).hexdigest()
    )
    assert prediction.evidence.translation_latency_ms == 3.0
    assert prediction.evidence.downstream_latency_ms == 7.0
    assert prediction.evidence.total_latency_ms == 10.0
    assert prediction.evidence.cost == _cost()
    assert prediction.evidence.privacy == _privacy()


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (
            TranslatorOutcome("missing", None, _cost(), _privacy(), "empty_response"),
            "missing_translation",
        ),
        (
            TranslatorOutcome("error", None, _cost(), _privacy(), "provider_error"),
            "translation_error",
        ),
        (
            TranslatorOutcome("timeout", None, _cost(), _privacy(), "deadline"),
            "translation_timeout",
        ),
        (TranslatorOutcome("ok", "   ", _cost(), _privacy()), "invalid_translation"),
    ],
)
def test_translation_failure_is_a_denominator_failure_and_skips_downstream(
    outcome: TranslatorOutcome,
    expected_status: str,
) -> None:
    translator = ScriptedTranslator(outcome)
    predictor = ScriptedPredictor(EnglishPrediction("SELECT 1", "ok"))
    baseline = TranslationFirstBaseline(
        translator,
        predictor,
        clock_ns=ScriptedClock(0, 2_000_000),
    )

    prediction = baseline.predict_detailed("Đếm giao dịch", request_id="req-failed")

    assert prediction.status == expected_status
    assert prediction.sql is None
    assert prediction.downstream_prediction is None
    assert predictor.calls == []
    assert prediction.evidence.downstream_latency_ms is None
    assert prediction.evidence.total_latency_ms == 2.0


def test_translator_exception_is_sanitized_and_skips_downstream() -> None:
    translator = ScriptedTranslator(RuntimeError("secret provider detail"))
    predictor = ScriptedPredictor(EnglishPrediction("SELECT 1", "ok"))
    baseline = TranslationFirstBaseline(
        translator,
        predictor,
        clock_ns=ScriptedClock(0, 1_000_000),
    )

    prediction = baseline.predict_detailed("Đếm giao dịch", request_id="req-error")

    assert prediction.status == "translation_error"
    assert prediction.evidence.error_code == "translator_exception"
    assert predictor.calls == []
    assert prediction.evidence.cost.measurement_status == "unmeasured"
    assert prediction.evidence.privacy.data_egress == "unknown"


def test_downstream_failure_retains_translation_and_separate_latency() -> None:
    translated = "Count transactions"
    translator = ScriptedTranslator(TranslatorOutcome("ok", translated, _cost(), _privacy()))
    predictor = ScriptedPredictor(EnglishPrediction(None, "unsafe_sql"))
    baseline = TranslationFirstBaseline(
        translator,
        predictor,
        clock_ns=ScriptedClock(0, 1_000_000, 5_000_000),
    )

    prediction = baseline.predict_detailed("Đếm giao dịch", request_id="req-downstream")

    assert prediction.status == "downstream_unsafe_sql"
    assert prediction.sql is None
    assert prediction.translated_question == translated
    assert prediction.evidence.translation_latency_ms == 1.0
    assert prediction.evidence.downstream_latency_ms == 4.0
    assert prediction.evidence.total_latency_ms == 5.0


def test_unpinned_translator_and_invalid_request_are_rejected_before_calls() -> None:
    translator = ScriptedTranslator(
        TranslatorOutcome("ok", "Count transactions", _cost(), _privacy())
    )
    predictor = ScriptedPredictor(EnglishPrediction("SELECT 1", "ok"))
    translator.config = TranslationConfig(
        translator_id="translator-v1",
        model_id="translation-model",
        model_revision=REVISION,
        settings_sha256=SHA_A,
    )
    baseline = TranslationFirstBaseline(translator, predictor)

    with pytest.raises(TranslationBaselineError, match="request_id"):
        baseline.predict_detailed("Đếm giao dịch", request_id="")
    assert translator.calls == []

    with pytest.raises(TranslationBaselineError, match="revision"):
        TranslationConfig("translator", "model", "latest", SHA_A)


def test_translator_configuration_cannot_change_after_baseline_construction() -> None:
    translator = ScriptedTranslator(
        TranslatorOutcome("ok", "Count transactions", _cost(), _privacy())
    )
    baseline = TranslationFirstBaseline(
        translator,
        ScriptedPredictor(EnglishPrediction("SELECT 1", "ok")),
    )
    translator.config = TranslationConfig(
        "different-translator", "translation-model", REVISION, SHA_A
    )

    with pytest.raises(TranslationBaselineError, match="changed after pinning"):
        baseline.predict_detailed("Đếm giao dịch", request_id="req-001")
    assert translator.calls == []
