"""Immutable contracts shared by the B1 and B2 GoogleSQL baselines."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Literal

MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"

BaselineName = Literal["b1", "b2"]
ExtractionStatus = Literal["ok", "empty", "prose", "invalid_sql", "unsafe_sql"]

_HEX_40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SmallLLMError(ValueError):
    """Raised when a B1/B2 input, artifact, or invariant is invalid."""


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SmallLLMError(f"{label} must be a lowercase SHA-256 digest")


def _revision(value: object, label: str = "model revision") -> None:
    if not isinstance(value, str) or not _HEX_40_RE.fullmatch(value):
        raise SmallLLMError(f"{label} must be a pinned lowercase 40-hex revision")


def validate_question(value: object) -> str:
    """Return a valid question without changing its source text."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 2_000
        or _CONTROL_RE.search(value)
        or not any(character.isalnum() for character in unicodedata.normalize("NFKC", value))
    ):
        raise SmallLLMError(
            "question must contain text, be control-free, and at most 2000 characters"
        )
    return value


@dataclass(frozen=True)
class GenerationConfig:
    """Pinned greedy-decoding configuration for both small-LLM baselines."""

    model_revision: str
    model_id: str = MODEL_ID
    seed: int = 42
    do_sample: bool = False
    max_new_tokens: int = 512
    load_in_4bit: bool = True

    def __post_init__(self) -> None:
        _revision(self.model_revision)
        if self.model_id != MODEL_ID:
            raise SmallLLMError(f"model_id must be {MODEL_ID!r}")
        if self.seed != 42 or isinstance(self.seed, bool):
            raise SmallLLMError("seed must be 42")
        if self.do_sample is not False:
            raise SmallLLMError("do_sample must be false for greedy decoding")
        if self.max_new_tokens != 512 or isinstance(self.max_new_tokens, bool):
            raise SmallLLMError("max_new_tokens must be 512")
        if self.load_in_4bit is not True:
            raise SmallLLMError("load_in_4bit must be true for the Kaggle adapter")

    @property
    def sha256(self) -> str:
        """Return a canonical fingerprint of every generation setting."""
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChatMessage:
    """One validated chat message sent to the generation backend."""

    role: Literal["system", "user"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user"}:
            raise SmallLLMError("chat role must be system or user")
        if (
            not isinstance(self.content, str)
            or not self.content.strip()
            or _CONTROL_RE.search(self.content)
        ):
            raise SmallLLMError("chat content must be non-empty and control-free")


@dataclass(frozen=True)
class Completion:
    """Raw completion and backend-reported accounting."""

    raw_text: str
    model_id: str
    model_revision: str
    input_tokens: int
    output_tokens: int
    synthetic_backend: bool = field(init=False, default=True)

    def __post_init__(self) -> None:
        if not isinstance(self.raw_text, str):
            raise SmallLLMError("completion raw_text must be a string")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise SmallLLMError("completion model_id must not be empty")
        _revision(self.model_revision, "completion model revision")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (self.input_tokens, self.output_tokens)
        ):
            raise SmallLLMError("completion token counts must be non-negative integers")


def _attest_completion(completion: Completion) -> Completion:
    """Mark a completion created by the production-only model loading path."""
    object.__setattr__(completion, "synthetic_backend", False)
    return completion


@dataclass(frozen=True)
class CatalogSummary:
    """Compact catalog prompt context bound to its exact source bytes."""

    text: str
    catalog_sha256: str
    summary_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise SmallLLMError("catalog summary must not be empty")
        _digest(self.catalog_sha256, "catalog fingerprint")
        _digest(self.summary_sha256, "summary fingerprint")
        actual = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if actual != self.summary_sha256:
            raise SmallLLMError("summary fingerprint does not match summary text")


@dataclass(frozen=True)
class SelectedExample:
    """One provenance-bearing few-shot example."""

    record_id: str
    question: str
    sql: str
    score: float

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not _RECORD_ID_RE.fullmatch(self.record_id):
            raise SmallLLMError("selected example ID is invalid")
        validate_question(self.question)
        if not isinstance(self.sql, str) or not self.sql.strip():
            raise SmallLLMError("selected example SQL must not be empty")
        if (
            not isinstance(self.score, float)
            or isinstance(self.score, bool)
            or not math.isfinite(self.score)
            or not -1.0 <= self.score <= 1.0
        ):
            raise SmallLLMError("selected example score must be a finite float in [-1, 1]")


@dataclass(frozen=True)
class SmallLLMPrediction:
    """One B1/B2 model response with extraction and provenance evidence."""

    baseline: BaselineName
    question: str
    raw_output: str
    sql: str | None
    extraction_status: ExtractionStatus
    completion: Completion
    catalog_sha256: str
    summary_sha256: str
    prompt_sha256: str
    config_sha256: str
    latency_ms: float
    training_sha256: str | None = None
    encoder_id: str | None = None
    encoder_revision: str | None = None
    selected_examples: tuple[SelectedExample, ...] = ()
    selected_examples_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.baseline not in {"b1", "b2"}:
            raise SmallLLMError("baseline must be b1 or b2")
        validate_question(self.question)
        if not isinstance(self.raw_output, str) or self.raw_output != self.completion.raw_text:
            raise SmallLLMError("raw output must equal the completion text")
        if self.extraction_status not in {
            "ok",
            "empty",
            "prose",
            "invalid_sql",
            "unsafe_sql",
        }:
            raise SmallLLMError("extraction status is invalid")
        if self.extraction_status == "ok" and (
            not isinstance(self.sql, str) or not self.sql.strip()
        ):
            raise SmallLLMError("ok prediction must contain SQL")
        if self.extraction_status != "ok" and self.sql is not None:
            raise SmallLLMError("failed prediction must not contain SQL")
        for label, value in (
            ("catalog fingerprint", self.catalog_sha256),
            ("summary fingerprint", self.summary_sha256),
            ("prompt fingerprint", self.prompt_sha256),
            ("config fingerprint", self.config_sha256),
        ):
            _digest(value, label)
        if (
            not isinstance(self.latency_ms, float)
            or isinstance(self.latency_ms, bool)
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0.0
        ):
            raise SmallLLMError("latency_ms must be a finite non-negative float")
        if not isinstance(self.selected_examples, tuple) or any(
            not isinstance(item, SelectedExample) for item in self.selected_examples
        ):
            raise SmallLLMError("selected examples must be an immutable tuple")
        examples_payload = json.dumps(
            [asdict(example) for example in self.selected_examples],
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(
            self,
            "selected_examples_sha256",
            hashlib.sha256(examples_payload.encode("utf-8")).hexdigest(),
        )

        provenance = (self.training_sha256, self.encoder_id, self.encoder_revision)
        if self.baseline == "b1":
            if any(value is not None for value in provenance) or self.selected_examples:
                raise SmallLLMError("B1 prediction must not contain B2 provenance")
            return

        if self.training_sha256 is None:
            raise SmallLLMError("B2 prediction requires a training fingerprint")
        _digest(self.training_sha256, "training fingerprint")
        if not isinstance(self.encoder_id, str) or not self.encoder_id.strip():
            raise SmallLLMError("B2 prediction requires an encoder ID")
        _revision(self.encoder_revision, "encoder revision")
        if len(self.selected_examples) != 5:
            raise SmallLLMError("B2 prediction requires exactly five selected examples")
        ids = tuple(example.record_id for example in self.selected_examples)
        if len(ids) != len(set(ids)):
            raise SmallLLMError("B2 selected example IDs must be unique")
