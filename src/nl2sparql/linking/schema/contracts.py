"""Typed contracts for Plan B schema linking."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DOCUMENT_VERSION = "1.0.0"
INDEX_SCHEMA_VERSION = 1

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SchemaLinkerError(ValueError):
    """Raised when a schema-linker contract is invalid."""


class SchemaDocumentError(SchemaLinkerError):
    """Raised when catalog documents or synonyms are invalid."""


class Encoder(Protocol):
    """Minimal sentence-encoder boundary used by index and query code."""

    def encode(
        self,
        sentences: Sequence[str] | str,
        *,
        normalize_embeddings: bool = True,
    ) -> Any:
        """Encode one or more strings as normalized vectors."""


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or _CONTROL_RE.search(value):
        raise SchemaLinkerError(f"{label} must be non-empty and control-free")
    return value.strip()


@dataclass(frozen=True)
class SchemaElement:
    """One ranked analytical relation or relation field."""

    element_id: str
    kind: str
    document: str
    document_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "element_id", _required_text(self.element_id, "element ID"))
        if self.kind not in {"relation", "field"}:
            raise SchemaLinkerError("schema element kind must be relation or field")
        object.__setattr__(self, "document", _required_text(self.document, "document"))
        if not isinstance(self.document_sha256, str) or not _SHA256_RE.fullmatch(
            self.document_sha256
        ):
            raise SchemaLinkerError("document_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class ScoreWeights:
    """Validated semantic/lexical fusion weights."""

    semantic: float = 0.65
    lexical: float = 0.35

    def __post_init__(self) -> None:
        values = (self.semantic, self.lexical)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            for value in values
        ) or not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise SchemaLinkerError("score weights must be finite, non-negative, and sum to one")


@dataclass(frozen=True)
class SchemaCachePaths:
    """Stable paths for one schema-linker index pair and its lock."""

    manifest: Path
    matrices: Path
    lock: Path

    @classmethod
    def from_directory(cls, directory: Path) -> SchemaCachePaths:
        """Derive cache artifact paths below a directory."""
        return cls(
            manifest=directory / "schema-index.json",
            matrices=directory / "schema-index.npz",
            lock=directory / "schema-index.lock",
        )
