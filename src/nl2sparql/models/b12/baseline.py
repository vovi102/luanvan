"""Deep public B1/B2 prediction interfaces."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from nl2sparql.models.b12.backend import GenerationBackend
from nl2sparql.models.b12.contracts import (
    CatalogSummary,
    Completion,
    GenerationConfig,
    SelectedExample,
    SmallLLMError,
    SmallLLMPrediction,
    validate_question,
)
from nl2sparql.models.b12.extraction import extract_google_sql
from nl2sparql.models.b12.prompts import build_messages, prompt_sha256


class _Retriever(Protocol):
    @property
    def training_sha256(self) -> str: ...

    @property
    def encoder_id(self) -> str: ...

    @property
    def encoder_revision(self) -> str: ...

    def retrieve(
        self,
        question: str,
        *,
        target_id: str | None = None,
    ) -> tuple[SelectedExample, ...]: ...


def _validate_dependencies(
    summary: object,
    config: object,
    backend: object,
    clock_ns: object,
) -> None:
    if not isinstance(summary, CatalogSummary):
        raise SmallLLMError("summary must be a CatalogSummary")
    if not isinstance(config, GenerationConfig):
        raise SmallLLMError("config must be a GenerationConfig")
    if not callable(getattr(backend, "generate", None)):
        raise SmallLLMError("backend must provide generate")
    if not callable(clock_ns):
        raise SmallLLMError("clock_ns must be callable")


def _generate(
    question: str,
    *,
    baseline: str,
    summary: CatalogSummary,
    config: GenerationConfig,
    backend: GenerationBackend,
    examples: tuple[SelectedExample, ...],
    clock_ns: Callable[[], int],
    training_sha256: str | None = None,
    encoder_id: str | None = None,
    encoder_revision: str | None = None,
) -> SmallLLMPrediction:
    messages = build_messages(question, summary, examples=examples)
    start = clock_ns()
    try:
        completion = backend.generate(messages, config)
    except SmallLLMError:
        raise
    except Exception as exc:
        raise SmallLLMError(f"model generation failed: {exc}") from exc
    end = clock_ns()
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or end < start
    ):
        raise SmallLLMError("monotonic clock returned an invalid interval")
    if not isinstance(completion, Completion):
        raise SmallLLMError("generation backend must return Completion")
    if completion.model_id != config.model_id or completion.model_revision != config.model_revision:
        raise SmallLLMError("completion model identity does not match generation config")
    sql, status = extract_google_sql(completion.raw_text)
    return SmallLLMPrediction(
        baseline=baseline,  # type: ignore[arg-type]
        question=question,
        raw_output=completion.raw_text,
        sql=sql,
        extraction_status=status,
        completion=completion,
        catalog_sha256=summary.catalog_sha256,
        summary_sha256=summary.summary_sha256,
        prompt_sha256=prompt_sha256(messages),
        config_sha256=config.sha256,
        latency_ms=(end - start) / 1_000_000.0,
        training_sha256=training_sha256,
        encoder_id=encoder_id,
        encoder_revision=encoder_revision,
        selected_examples=examples,
    )


class BaselineB1:
    """Raw zero-shot Llama baseline over catalog-only prompt context."""

    def __init__(
        self,
        summary: CatalogSummary,
        config: GenerationConfig,
        backend: GenerationBackend,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        _validate_dependencies(summary, config, backend, clock_ns)
        self._summary = summary
        self._config = config
        self._backend = backend
        self._clock_ns = clock_ns

    def predict(self, question: str) -> str | None:
        """Return one safe query or None when generation cannot be extracted."""
        return self.predict_detailed(question).sql

    def predict_detailed(self, question: str) -> SmallLLMPrediction:
        """Return raw generation, extraction status, latency, and provenance."""
        validate_question(question)
        return _generate(
            question,
            baseline="b1",
            summary=self._summary,
            config=self._config,
            backend=self._backend,
            examples=(),
            clock_ns=self._clock_ns,
        )


class BaselineB2:
    """Raw five-shot Llama baseline with deterministic training retrieval."""

    def __init__(
        self,
        summary: CatalogSummary,
        config: GenerationConfig,
        backend: GenerationBackend,
        retriever: _Retriever,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        _validate_dependencies(summary, config, backend, clock_ns)
        if not callable(getattr(retriever, "retrieve", None)):
            raise SmallLLMError("retriever must provide retrieve")
        self._summary = summary
        self._config = config
        self._backend = backend
        self._retriever = retriever
        self._clock_ns = clock_ns

    def predict(self, question: str, *, target_id: str | None = None) -> str | None:
        """Return one safe query or None when generation cannot be extracted."""
        return self.predict_detailed(question, target_id=target_id).sql

    def predict_detailed(
        self,
        question: str,
        *,
        target_id: str | None = None,
    ) -> SmallLLMPrediction:
        """Retrieve five examples, then return generation and provenance."""
        validate_question(question)
        examples = self._retriever.retrieve(question, target_id=target_id)
        return _generate(
            question,
            baseline="b2",
            summary=self._summary,
            config=self._config,
            backend=self._backend,
            examples=examples,
            clock_ns=self._clock_ns,
            training_sha256=self._retriever.training_sha256,
            encoder_id=self._retriever.encoder_id,
            encoder_revision=self._retriever.encoder_revision,
        )
