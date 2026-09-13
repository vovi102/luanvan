"""Async B4/B5 GoogleSQL prompt orchestration."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from nl2sparql.models.b12.contracts import (
    CatalogSummary,
    ChatMessage,
    SelectedExample,
    SmallLLMError,
    validate_question,
)
from nl2sparql.models.b12.extraction import extract_google_sql
from nl2sparql.models.b12.prompts import build_messages, prompt_sha256
from nl2sparql.models.b45.attempts import AttemptEvidencePersistenceError
from nl2sparql.models.b45.budget import BudgetLedger
from nl2sparql.models.b45.contracts import (
    LargeBaselineEvidence,
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


@dataclass(frozen=True)
class RetrievalEvidence:
    """Canonical, non-secret provenance for one local retrieval preview."""

    training_sha256: str | None
    encoder_id: str | None
    encoder_revision: str | None
    training_accepted: bool
    selected_examples: tuple[SelectedExample, ...]
    selected_examples_sha256: str
    retrieval_sha256: str


def _retrieval_evidence(
    *,
    training_sha256: str | None,
    encoder_id: str | None,
    encoder_revision: str | None,
    training_accepted: bool,
    selected_examples: tuple[SelectedExample, ...],
) -> RetrievalEvidence:
    examples = tuple(
        {
            "record_id": example.record_id,
            "question": example.question,
            "score": example.score,
            "sql": example.sql,
        }
        for example in selected_examples
    )
    examples_payload = json.dumps(
        examples, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    examples_sha256 = hashlib.sha256(examples_payload.encode("utf-8")).hexdigest()
    evidence = {
        "encoder_id": encoder_id,
        "encoder_revision": encoder_revision,
        "selected_examples": examples,
        "selected_examples_sha256": examples_sha256,
        "training_accepted": training_accepted,
        "training_sha256": training_sha256,
    }
    payload = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return RetrievalEvidence(
        training_sha256=training_sha256,
        encoder_id=encoder_id,
        encoder_revision=encoder_revision,
        training_accepted=training_accepted,
        selected_examples=selected_examples,
        selected_examples_sha256=examples_sha256,
        retrieval_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


@dataclass(frozen=True)
class PromptPreview:
    """Deterministic local prompt evidence prepared before transport access."""

    messages: tuple[ChatMessage, ...]
    prompt_sha256: str
    selected_examples: tuple[SelectedExample, ...] = ()
    retrieval_evidence: RetrievalEvidence | None = None

    def __post_init__(self) -> None:
        if self.retrieval_evidence is None:
            object.__setattr__(
                self,
                "retrieval_evidence",
                _retrieval_evidence(
                    training_sha256=None,
                    encoder_id=None,
                    encoder_revision=None,
                    training_accepted=False,
                    selected_examples=self.selected_examples,
                ),
            )

    @property
    def retrieval_sha256(self) -> str:
        """Return the canonical retrieval provenance fingerprint."""
        assert self.retrieval_evidence is not None
        return self.retrieval_evidence.retrieval_sha256

    @property
    def encoder_id(self) -> str | None:
        """Return the encoder identity used by B5, if applicable."""
        assert self.retrieval_evidence is not None
        return self.retrieval_evidence.encoder_id

    @property
    def encoder_revision(self) -> str | None:
        """Return the pinned encoder revision used by B5, if applicable."""
        assert self.retrieval_evidence is not None
        return self.retrieval_evidence.encoder_revision


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


def _build_prompt_preview(
    question: str,
    summary: CatalogSummary,
    *,
    examples: tuple[SelectedExample, ...],
    training_sha256: str | None = None,
    encoder_id: str | None = None,
    encoder_revision: str | None = None,
    training_accepted: bool = False,
) -> PromptPreview:
    """Build and fingerprint the exact production prompt without I/O."""
    question = _validated_question(question)
    try:
        messages = build_messages(question, summary, examples=examples)
    except SmallLLMError as exc:
        raise LargeLLMError(str(exc)) from exc
    return PromptPreview(
        messages=messages,
        prompt_sha256=prompt_sha256(messages),
        selected_examples=examples,
        retrieval_evidence=_retrieval_evidence(
            training_sha256=training_sha256,
            encoder_id=encoder_id,
            encoder_revision=encoder_revision,
            training_accepted=training_accepted,
            selected_examples=examples,
        ),
    )


def preview_b4_prompt(question: str, summary: CatalogSummary) -> PromptPreview:
    """Build B4's exact production prompt without creating a transport."""
    return _build_prompt_preview(question, summary, examples=())


def preview_b5_prompt(
    question: str,
    summary: CatalogSummary,
    retriever: _Retriever,
    *,
    target_id: str | None = None,
) -> PromptPreview:
    """Retrieve B5's examples and build its exact prompt without transport I/O."""
    question = _validated_question(question)
    try:
        examples = retriever.retrieve(question, target_id=target_id)
    except LargeLLMError:
        raise
    except Exception as exc:
        raise LargeLLMError(f"few-shot retrieval failed ({type(exc).__name__})") from exc
    return _build_prompt_preview(
        question,
        summary,
        examples=examples,
        training_sha256=retriever.training_sha256,
        encoder_id=retriever.encoder_id,
        encoder_revision=retriever.encoder_revision,
        training_accepted=retriever.training_accepted,
    )


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
    preview: PromptPreview | None,
    clock_ns: Callable[[], int],
    training_sha256: str | None = None,
    encoder_id: str | None = None,
    encoder_revision: str | None = None,
    training_accepted: bool = False,
) -> LargeLLMPrediction:
    """Build one shared prompt, await completion, and preserve all provenance."""
    question = _validated_question(question)
    request_id = _validate_request_id(request_id)
    if preview is None:
        preview = _build_prompt_preview(question, summary, examples=examples)
    messages = preview.messages
    prompt_fingerprint = preview.prompt_sha256

    start = clock_ns()
    try:
        completion = await transport.complete(messages, config, request_id=request_id)
    except AttemptEvidencePersistenceError:
        raise
    except LargeLLMError as exc:
        if getattr(exc, "prompt_sha256", None) is None:
            exc.prompt_sha256 = prompt_fingerprint
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
        prompt_sha256=prompt_fingerprint,
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

    @property
    def config(self) -> LargeLLMConfig:
        """Return the immutable generation configuration.

        Returns:
            The configuration bound to predictions and budget accounting.
        """
        return self._config

    @property
    def budget_ledger(self) -> BudgetLedger:
        """Return the transport's budget ledger through a read-only seam.

        Returns:
            The ledger owned by the configured transport.

        Raises:
            LargeLLMError: If the transport does not expose a budget ledger.
        """
        ledger = getattr(self._transport, "budget_ledger", None)
        if not isinstance(ledger, BudgetLedger):
            ledger = getattr(self._transport, "_ledger", None)
        if not isinstance(ledger, BudgetLedger):
            raise LargeLLMError("completion transport does not expose a budget ledger")
        return ledger

    @property
    def evaluation_evidence(self) -> LargeBaselineEvidence:
        """Return immutable baseline identity independently of predictions.

        Returns:
            Catalog, configuration, model, provider, and B4 identity evidence.
        """
        return LargeBaselineEvidence(
            baseline="b4",
            catalog_sha256=self._summary.catalog_sha256,
            summary_sha256=self._summary.summary_sha256,
            config_sha256=self._config.sha256,
            training_sha256=None,
            training_accepted=False,
            model_id=self._config.model_id,
            provider_slug=self._config.provider.provider_slug,
            provider_policy_sha256=self._config.provider.sha256,
        )

    async def predict(self, question: str, *, request_id: str) -> str | None:
        """Return extracted safe GoogleSQL, if the response is a whole query."""
        return (await self.predict_detailed(question, request_id=request_id)).sql

    def preview_prompt(self, question: str) -> PromptPreview:
        """Return B4's exact prompt and fingerprint without contacting transport."""
        return preview_b4_prompt(question, self._summary)

    async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
        """Return the completion, fail-closed extraction, and B4 provenance."""
        preview = self.preview_prompt(question)
        return await _predict(
            question,
            request_id=request_id,
            baseline="b4",
            summary=self._summary,
            config=self._config,
            transport=self._transport,
            examples=(),
            preview=preview,
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

    @property
    def config(self) -> LargeLLMConfig:
        """Return the immutable generation configuration.

        Returns:
            The configuration bound to predictions and budget accounting.
        """
        return self._config

    @property
    def budget_ledger(self) -> BudgetLedger:
        """Return the transport's budget ledger through a read-only seam.

        Returns:
            The ledger owned by the configured transport.

        Raises:
            LargeLLMError: If the transport does not expose a budget ledger.
        """
        ledger = getattr(self._transport, "budget_ledger", None)
        if not isinstance(ledger, BudgetLedger):
            ledger = getattr(self._transport, "_ledger", None)
        if not isinstance(ledger, BudgetLedger):
            raise LargeLLMError("completion transport does not expose a budget ledger")
        return ledger

    @property
    def evaluation_evidence(self) -> LargeBaselineEvidence:
        """Return immutable baseline identity independently of predictions.

        Returns:
            Catalog, configuration, training, model, provider, and B5 identity evidence.
        """
        return LargeBaselineEvidence(
            baseline="b5",
            catalog_sha256=self._summary.catalog_sha256,
            summary_sha256=self._summary.summary_sha256,
            config_sha256=self._config.sha256,
            training_sha256=self._retriever.training_sha256,
            training_accepted=self._retriever.training_accepted,
            model_id=self._config.model_id,
            provider_slug=self._config.provider.provider_slug,
            provider_policy_sha256=self._config.provider.sha256,
        )

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

    def preview_prompt(
        self,
        question: str,
        *,
        target_id: str | None = None,
    ) -> PromptPreview:
        """Retrieve five examples and fingerprint B5's exact prompt locally."""
        return preview_b5_prompt(
            question,
            self._summary,
            self._retriever,
            target_id=target_id,
        )

    async def predict_detailed(
        self,
        question: str,
        *,
        request_id: str,
        target_id: str | None = None,
    ) -> LargeLLMPrediction:
        """Retrieve five examples, then return completion and B5 provenance."""
        _validate_request_id(request_id)
        preview = self.preview_prompt(question, target_id=target_id)
        return await _predict(
            question,
            request_id=request_id,
            baseline="b5",
            summary=self._summary,
            config=self._config,
            transport=self._transport,
            examples=preview.selected_examples,
            preview=preview,
            clock_ns=self._clock_ns,
            training_sha256=self._retriever.training_sha256,
            encoder_id=self._retriever.encoder_id,
            encoder_revision=self._retriever.encoder_revision,
            training_accepted=self._retriever.training_accepted,
        )
