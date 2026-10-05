"""Pinned translation-first composition used only as a scientific baseline."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from nl2sparql.evaluation.contracts import (
    CostEvidence,
    PrivacyEvidence,
    TranslationEvidence,
    TranslationStatus,
)
from nl2sparql.models.b12.contracts import SmallLLMError, validate_question

_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TranslationBaselineError(ValueError):
    """Raised when translation-baseline configuration or input is invalid."""


@dataclass(frozen=True)
class TranslationConfig:
    """Pinned identity and opaque settings fingerprint for a translator."""

    translator_id: str
    model_id: str
    model_revision: str
    settings_sha256: str
    source_language: Literal["vi"] = "vi"
    target_language: Literal["en"] = "en"

    def __post_init__(self) -> None:
        for field, value in (
            ("translator_id", self.translator_id),
            ("model_id", self.model_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise TranslationBaselineError(f"{field} must be non-empty text")
        if not isinstance(self.model_revision, str) or not _REVISION_RE.fullmatch(
            self.model_revision
        ):
            raise TranslationBaselineError(
                "model revision must be a pinned lowercase 40-hex revision"
            )
        if not isinstance(self.settings_sha256, str) or not _SHA256_RE.fullmatch(
            self.settings_sha256
        ):
            raise TranslationBaselineError("settings_sha256 must be a lowercase SHA-256")
        if self.source_language != "vi" or self.target_language != "en":
            raise TranslationBaselineError("translation baseline must translate vi to en")

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


TranslatorOutcomeStatus = Literal["ok", "missing", "error", "timeout"]


@dataclass(frozen=True)
class TranslatorOutcome:
    """Terminal translator response with call-specific accounting evidence."""

    status: TranslatorOutcomeStatus
    translated_text: str | None
    cost: CostEvidence
    privacy: PrivacyEvidence
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ok", "missing", "error", "timeout"}:
            raise TranslationBaselineError("unknown translator outcome status")
        if self.status == "ok":
            if not isinstance(self.translated_text, str):
                raise TranslationBaselineError("ok translator outcome requires text")
            if self.error_code is not None:
                raise TranslationBaselineError("ok translator outcome cannot carry an error")
        else:
            if self.translated_text is not None:
                raise TranslationBaselineError("failed translator outcome cannot carry text")
            if not isinstance(self.error_code, str) or not self.error_code.strip():
                raise TranslationBaselineError("failed translator outcome requires error_code")


class Translator(Protocol):
    """Narrow translator seam; concrete network clients live outside this module."""

    config: TranslationConfig

    def translate(self, question: str, *, request_id: str) -> TranslatorOutcome: ...


class EnglishPrediction(Protocol):
    sql: str | None
    extraction_status: str


class EnglishPredictor(Protocol):
    def predict_detailed(self, question: str) -> EnglishPrediction: ...


@dataclass(frozen=True)
class TranslationPrediction:
    """One denominator-preserving terminal result from the composed baseline."""

    request_id: str
    original_question: str
    translated_question: str | None
    sql: str | None
    status: TranslationStatus
    evidence: TranslationEvidence
    downstream_prediction: object | None

    def __post_init__(self) -> None:
        if self.request_id != self.evidence.request_id or self.status != self.evidence.status:
            raise TranslationBaselineError("prediction identity must match its evidence")
        if self.translated_question != self.evidence.translated_text:
            raise TranslationBaselineError("prediction translation must match its evidence")
        if self.status == "ok":
            if not isinstance(self.sql, str) or not self.sql.strip():
                raise TranslationBaselineError("ok prediction requires SQL")
            if self.downstream_prediction is None:
                raise TranslationBaselineError("ok prediction requires downstream evidence")
        elif self.sql is not None:
            raise TranslationBaselineError("failed prediction cannot carry SQL")


def _unmeasured_cost() -> CostEvidence:
    return CostEvidence("unmeasured", None, None, None)


def _unknown_privacy() -> PrivacyEvidence:
    return PrivacyEvidence("undocumented", "unknown", None, None, None)


def _clock_value(clock_ns: Callable[[], int]) -> int:
    value = clock_ns()
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TranslationBaselineError("clock_ns must return a non-negative integer")
    return value


def _elapsed_ms(start: int, end: int) -> float:
    if end < start:
        raise TranslationBaselineError("clock_ns must be monotonic")
    value = (end - start) / 1_000_000
    if not math.isfinite(value):
        raise TranslationBaselineError("measured latency must be finite")
    return value


def _downstream_status(prediction: object) -> tuple[TranslationStatus, str | None, str | None]:
    if prediction is None:
        return "downstream_no_output", None, "no_output"
    extraction_status = getattr(prediction, "extraction_status", None)
    sql = getattr(prediction, "sql", None)
    if extraction_status == "ok" and isinstance(sql, str) and sql.strip():
        return "ok", sql, None
    mapping: dict[object, tuple[TranslationStatus, str]] = {
        "empty": ("downstream_no_output", "no_output"),
        "prose": ("downstream_invalid_sql", "prose_output"),
        "invalid_sql": ("downstream_invalid_sql", "invalid_sql"),
        "unsafe_sql": ("downstream_unsafe_sql", "unsafe_sql"),
        "timeout": ("downstream_timeout", "timeout"),
    }
    status, error = mapping.get(
        extraction_status, ("downstream_error", "invalid_downstream_prediction")
    )
    return status, None, error


class TranslationFirstBaseline:
    """Compose a pinned Vietnamese translator with an accepted English predictor."""

    def __init__(
        self,
        translator: Translator,
        predictor: EnglishPredictor,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if not isinstance(getattr(translator, "config", None), TranslationConfig):
            raise TranslationBaselineError("translator must expose a pinned TranslationConfig")
        if not callable(getattr(translator, "translate", None)):
            raise TranslationBaselineError("translator must provide translate")
        if not callable(getattr(predictor, "predict_detailed", None)):
            raise TranslationBaselineError("predictor must provide predict_detailed")
        if not callable(clock_ns):
            raise TranslationBaselineError("clock_ns must be callable")
        self._translator = translator
        self._config = translator.config
        self._predictor = predictor
        self._clock_ns = clock_ns

    def predict_detailed(self, question: str, *, request_id: str) -> TranslationPrediction:
        if not isinstance(request_id, str) or not request_id.strip():
            raise TranslationBaselineError("request_id must be non-empty text")
        try:
            original = validate_question(question)
        except SmallLLMError as exc:
            raise TranslationBaselineError(str(exc)) from exc
        if self._translator.config != self._config:
            raise TranslationBaselineError("translator configuration changed after pinning")

        start = _clock_value(self._clock_ns)
        try:
            outcome = self._translator.translate(original, request_id=request_id)
            if not isinstance(outcome, TranslatorOutcome):
                raise TypeError("translator returned an invalid outcome")
        except Exception:
            translated_at = _clock_value(self._clock_ns)
            return self._failure(
                request_id=request_id,
                original=original,
                status="translation_error",
                error_code="translator_exception",
                start=start,
                translated_at=translated_at,
                cost=_unmeasured_cost(),
                privacy=_unknown_privacy(),
            )

        translated_at = _clock_value(self._clock_ns)
        status_map: dict[TranslatorOutcomeStatus, TranslationStatus] = {
            "missing": "missing_translation",
            "error": "translation_error",
            "timeout": "translation_timeout",
            "ok": "ok",
        }
        if outcome.status != "ok":
            return self._failure(
                request_id=request_id,
                original=original,
                status=status_map[outcome.status],
                error_code=outcome.error_code or "translation_failed",
                start=start,
                translated_at=translated_at,
                cost=outcome.cost,
                privacy=outcome.privacy,
            )
        try:
            assert outcome.translated_text is not None
            translated = validate_question(outcome.translated_text)
        except (SmallLLMError, AssertionError):
            return self._failure(
                request_id=request_id,
                original=original,
                status="invalid_translation",
                error_code="invalid_translated_text",
                start=start,
                translated_at=translated_at,
                cost=outcome.cost,
                privacy=outcome.privacy,
            )

        try:
            downstream = self._predictor.predict_detailed(translated)
        except Exception:
            finished_at = _clock_value(self._clock_ns)
            status: TranslationStatus = "downstream_error"
            sql = None
            error_code = "downstream_exception"
            downstream = None
        else:
            finished_at = _clock_value(self._clock_ns)
            status, sql, error_code = _downstream_status(downstream)

        translation_latency = _elapsed_ms(start, translated_at)
        downstream_latency = _elapsed_ms(translated_at, finished_at)
        evidence = TranslationEvidence(
            request_id=request_id,
            translator_id=self._config.translator_id,
            model_id=self._config.model_id,
            model_revision=self._config.model_revision,
            config_sha256=self._config.sha256,
            original_text_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
            translated_text=translated,
            translated_text_sha256=hashlib.sha256(translated.encode("utf-8")).hexdigest(),
            translation_latency_ms=translation_latency,
            downstream_latency_ms=downstream_latency,
            total_latency_ms=translation_latency + downstream_latency,
            status=status,
            error_code=error_code,
            cost=outcome.cost,
            privacy=outcome.privacy,
        )
        return TranslationPrediction(
            request_id,
            original,
            translated,
            sql,
            status,
            evidence,
            downstream,
        )

    def _failure(
        self,
        *,
        request_id: str,
        original: str,
        status: TranslationStatus,
        error_code: str,
        start: int,
        translated_at: int,
        cost: CostEvidence,
        privacy: PrivacyEvidence,
    ) -> TranslationPrediction:
        latency = _elapsed_ms(start, translated_at)
        evidence = TranslationEvidence(
            request_id=request_id,
            translator_id=self._config.translator_id,
            model_id=self._config.model_id,
            model_revision=self._config.model_revision,
            config_sha256=self._config.sha256,
            original_text_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
            translated_text=None,
            translated_text_sha256=None,
            translation_latency_ms=latency,
            downstream_latency_ms=None,
            total_latency_ms=latency,
            status=status,
            error_code=error_code,
            cost=cost,
            privacy=privacy,
        )
        return TranslationPrediction(request_id, original, None, None, status, evidence, None)
