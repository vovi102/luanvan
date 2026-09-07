"""Async B4/B5 GoogleSQL prompt orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal, Protocol

from nl2sparql.models.b12.contracts import (
    CatalogSummary,
    SelectedExample,
    SmallLLMError,
    validate_question,
)
from nl2sparql.models.b12.extraction import extract_google_sql
from nl2sparql.models.b12.prompts import build_messages, prompt_sha256
from nl2sparql.models.b45.contracts import (
    LargeLLMConfig,
    LargeLLMError,
    LargeLLMPrediction,
    RemoteCompletion,
)
from nl2sparql.models.b45.transport import CompletionTransport


class _Retriever(Protocol):
    """B2-compatible source of five provenance-bearing examples."""

    @property
    def training_sha256(self) -> str: ...

    @property
    def encoder_id(self) -> str: ...

    @property
    def encoder_revision(self) -> str: ...

    @property
    def training_accepted(self) -> bool: ...

    def retrieve(
        self,
        question: str,
        *,
        target_id: str | None = None,
    ) -> tuple[SelectedExample, ...]: ...


def _validate_dependencies(
    summary: object,
    config: object,
    transport: object,
    clock_ns: object,
) -> None:
    if not isinstance(summary, CatalogSummary):
        raise LargeLLMError("summary must be a CatalogSummary")
    if not isinstance(config, LargeLLMConfig):
        raise LargeLLMError("config must be a LargeLLMConfig")
    if not callable(getattr(transport, "complete", None)):
        raise LargeLLMError("transport must provide complete")
    if not callable(clock_ns):
        raise LargeLLMError("clock_ns must be callable")


def _validate_request_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise LargeLLMError("request ID must be non-empty and control-free")
    return value


def _validated_question(value: object) -> str:
    try:
        return validate_question(value)
    except SmallLLMError as exc:
        raise LargeLLMError(str(exc)) from exc


def _interval_ms(start: object, end: object) -> float:
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or end < start
    ):
        raise LargeLLMError("monotonic clock returned an invalid interval")
    return (end - start) / 1_000_000.0


async def _predict(
    question: str,
    *,
    request_id: str,
    baseline: Literal["b4", "b5"],
    summary: CatalogSummary,
    config: LargeLLMConfig,
    transport: CompletionTransport,
    examples: tuple[SelectedExample, ...],
    clock_ns: Callable[[], int],
    training_sha256: str | None = None,
    encoder_id: str | None = None,
    encoder_revision: str | None = None,
    training_accepted: bool = False,
) -> LargeLLMPrediction:
    """Build one shared prompt, await completion, and preserve all provenance."""
    question = _validated_question(question)
    request_id = _validate_request_id(request_id)
    try:
        messages = build_messages(question, summary, examples=examples)
    except SmallLLMError as exc:
        raise LargeLLMError(str(exc)) from exc

    start = clock_ns()
    try:
        completion = await transport.complete(messages, config, request_id=request_id)
    except LargeLLMError:
        raise
    except Exception as exc:
        raise LargeLLMError(f"remote completion failed ({type(exc).__name__})") from exc
    latency_ms = _interval_ms(start, clock_ns())

    if not isinstance(completion, RemoteCompletion):
        raise LargeLLMError("completion transport must return RemoteCompletion")
    if completion.model_id != config.model_id:
        raise LargeLLMError("completion model identity does not match large-LLM config")

    try:
        sql, status = extract_google_sql(completion.raw_text)
    except SmallLLMError as exc:
        raise LargeLLMError(str(exc)) from exc
    return LargeLLMPrediction(
        baseline=baseline,
        question=question,
        raw_output=completion.raw_text,
        sql=sql,
        extraction_status=status,
        completion=completion,
        catalog_sha256=summary.catalog_sha256,
        summary_sha256=summary.summary_sha256,
        prompt_sha256=prompt_sha256(messages),
        config_sha256=config.sha256,
        latency_ms=latency_ms,
        training_sha256=training_sha256,
        encoder_id=encoder_id,
        encoder_revision=encoder_revision,
        training_accepted=training_accepted,
        selected_examples=examples,
    )


class BaselineB4:
    """Catalog-only large-LLM GoogleSQL baseline."""

    def __init__(
        self,
        summary: CatalogSummary,
        config: LargeLLMConfig,
        transport: CompletionTransport,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        _validate_dependencies(summary, config, transport, clock_ns)
        self._summary = summary
        self._config = config
        self._transport = transport
        self._clock_ns = clock_ns

    async def predict(self, question: str, *, request_id: str) -> str | None:
        """Return extracted safe GoogleSQL, if the response is a whole query."""
        return (await self.predict_detailed(question, request_id=request_id)).sql

    async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
        """Return the completion, fail-closed extraction, and B4 provenance."""
        return await _predict(
            question,
            request_id=request_id,
            baseline="b4",
            summary=self._summary,
            config=self._config,
            transport=self._transport,
            examples=(),
            clock_ns=self._clock_ns,
        )


class BaselineB5:
    """Five-shot large-LLM GoogleSQL baseline with deterministic retrieval."""

    def __init__(
        self,
        summary: CatalogSummary,
        config: LargeLLMConfig,
        transport: CompletionTransport,
        retriever: _Retriever,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        _validate_dependencies(summary, config, transport, clock_ns)
        if not callable(getattr(retriever, "retrieve", None)):
            raise LargeLLMError("retriever must provide retrieve")
        self._summary = summary
        self._config = config
        self._transport = transport
        self._retriever = retriever
        self._clock_ns = clock_ns

    async def predict(
        self,
        question: str,
        *,
        request_id: str,
        target_id: str | None = None,
    ) -> str | None:
        """Return extracted safe GoogleSQL, if the response is a whole query."""
        return (
            await self.predict_detailed(question, request_id=request_id, target_id=target_id)
        ).sql

    async def predict_detailed(
        self,
        question: str,
        *,
        request_id: str,
        target_id: str | None = None,
    ) -> LargeLLMPrediction:
        """Retrieve five examples, then return completion and B5 provenance."""
        question = _validated_question(question)
        _validate_request_id(request_id)
        try:
            examples = self._retriever.retrieve(question, target_id=target_id)
        except LargeLLMError:
            raise
        except Exception as exc:
            raise LargeLLMError(f"few-shot retrieval failed ({type(exc).__name__})") from exc
        return await _predict(
            question,
            request_id=request_id,
            baseline="b5",
            summary=self._summary,
            config=self._config,
            transport=self._transport,
            examples=examples,
            clock_ns=self._clock_ns,
            training_sha256=self._retriever.training_sha256,
            encoder_id=self._retriever.encoder_id,
            encoder_revision=self._retriever.encoder_revision,
            training_accepted=self._retriever.training_accepted,
        )
