"""Typed contracts for Plan B entity linking."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DOCUMENT_VERSION = "1.0.0"
INDEX_SCHEMA_VERSION = 1

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")


class EntityLinkerError(ValueError):
    """Raised when an entity-linker contract is invalid."""


class EntityDocumentError(EntityLinkerError):
    """Raised when canonical entity targets cannot be constructed."""


class EntityIndexError(EntityLinkerError):
    """Raised when an entity index is stale, corrupt, or unsafe."""


class EntityEncoderUnavailableError(EntityLinkerError):
    """Raised when explicit production encoder initialization is unavailable."""


class Encoder(Protocol):
    """Minimal sentence-encoder seam shared with deterministic test adapters."""

    def encode(
        self,
        sentences: Sequence[str] | str,
        *,
        normalize_embeddings: bool = True,
    ) -> Any:
        """Encode one string or a sequence as normalized vectors."""


def required_text(value: object, label: str) -> str:
    """Return bounded, stripped, control-free text or fail closed."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 10_000
        or _CONTROL_RE.search(value)
    ):
        raise EntityLinkerError(f"{label} must be non-empty, bounded, and control-free")
    return value.strip()


def validate_digest(value: str, label: str) -> str:
    """Validate a lowercase SHA-256 digest."""
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EntityLinkerError(f"{label} must be a lowercase SHA-256 digest")
    return value


def validate_canonical_phrase(value: object, label: str) -> str:
    """Return a canonical, token-bearing corpus phrase or fail closed."""
    text = required_text(value, label)
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    if value != normalized:
        raise EntityLinkerError(f"{label} must be normalized")
    if not any(character.isalnum() for character in normalized):
        raise EntityLinkerError(f"{label} must contain a token")
    return normalized


@dataclass(frozen=True)
class EntityTarget:
    """One immutable owner or concept target ranked by the linker."""

    target_id: str
    target_kind: str
    owner: str | None
    addresses: tuple[str, ...]
    primary_labels: tuple[str, ...]
    aliases: tuple[str, ...]
    categories: tuple[str, ...]
    concept_classes: tuple[str, ...]
    address_roles: tuple[str, ...]
    description: str
    document: str
    document_sha256: str

    def __post_init__(self) -> None:
        required_text(self.target_id, "target ID")
        if self.target_kind not in {"owner", "concept"}:
            raise EntityLinkerError("target kind must be owner or concept")
        if self.target_kind == "owner" and self.owner is None:
            raise EntityLinkerError("owner target must include owner")
        if self.target_kind == "concept" and self.owner is not None:
            raise EntityLinkerError("concept target cannot claim an owner")
        for address in self.addresses:
            if not _ADDRESS_RE.fullmatch(address):
                raise EntityLinkerError(f"invalid target address: {address!r}")
        for name, values in (
            ("addresses", self.addresses),
            ("primary labels", self.primary_labels),
            ("aliases", self.aliases),
            ("categories", self.categories),
            ("concept classes", self.concept_classes),
            ("address roles", self.address_roles),
        ):
            if tuple(sorted(set(values))) != values:
                raise EntityLinkerError(f"target {name} must be unique and sorted")
        required_text(self.description, "target description")
        required_text(self.document, "target document")
        validate_digest(self.document_sha256, "target document fingerprint")
        if hashlib.sha256(self.document.encode("utf-8")).hexdigest() != self.document_sha256:
            raise EntityLinkerError("target document fingerprint does not match document")
        for alias in self.aliases:
            validate_canonical_phrase(alias, "target alias")


@dataclass(frozen=True)
class EntityAlternative:
    """One alternative target for an ambiguous mention."""

    target_id: str
    target_kind: str
    confidence: float

    def __post_init__(self) -> None:
        required_text(self.target_id, "alternative target ID")
        if self.target_kind not in {"owner", "concept", "address"}:
            raise EntityLinkerError("alternative target kind is invalid")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise EntityLinkerError("alternative confidence must be finite in [0, 1]")


@dataclass(frozen=True)
class EntityMatch:
    """One entity mention resolved through the cascade."""

    span: str
    span_offset: tuple[int, int]
    target_id: str
    target_kind: str
    owner: str | None
    addresses: tuple[str, ...]
    categories: tuple[str, ...]
    concept_classes: tuple[str, ...]
    stage: str
    confidence: float
    alternatives: tuple[EntityAlternative, ...]
    target_sha256: str

    def __post_init__(self) -> None:
        required_text(self.span, "entity span")
        start, end = self.span_offset
        if isinstance(start, bool) or isinstance(end, bool) or start < 0 or end <= start:
            raise EntityLinkerError("entity span offsets are invalid")
        if self.target_kind not in {"owner", "concept", "address"}:
            raise EntityLinkerError("entity target kind is invalid")
        if self.stage not in {"address", "exact", "fuzzy", "embedding", "ambiguous"}:
            raise EntityLinkerError("entity match stage is invalid")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise EntityLinkerError("entity confidence must be finite in [0, 1]")
        validate_digest(self.target_sha256, "entity target fingerprint")


@dataclass(frozen=True)
class EntityCorpus:
    """Canonical target and exact-lookup corpus derived from dictionary artifacts."""

    targets: tuple[EntityTarget, ...]
    targets_by_id: Mapping[str, EntityTarget]
    phrase_targets: Mapping[str, tuple[str, ...]]
    address_targets: Mapping[str, str]
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str

    def __post_init__(self) -> None:
        targets = tuple(self.targets)
        if not targets:
            raise EntityLinkerError("entity corpus must include at least one target")
        if any(not isinstance(target, EntityTarget) for target in targets):
            raise EntityLinkerError("entity corpus targets must be entity targets")
        if tuple(sorted(targets, key=lambda target: target.target_id)) != targets:
            raise EntityLinkerError("entity corpus targets must be ordered by target ID")
        target_ids = tuple(target.target_id for target in targets)
        if len(set(target_ids)) != len(target_ids):
            raise EntityLinkerError("entity corpus target IDs must be unique")
        expected_targets_by_id = {target.target_id: target for target in targets}

        for mapping, label in (
            (self.targets_by_id, "targets by ID"),
            (self.phrase_targets, "phrase targets"),
            (self.address_targets, "address targets"),
        ):
            if not isinstance(mapping, Mapping):
                raise EntityLinkerError(f"entity corpus {label} must be a mapping")
        if dict(self.targets_by_id) != expected_targets_by_id:
            raise EntityLinkerError("entity corpus targets by ID must match targets")

        target_ids_set = set(target_ids)
        frozen_phrase_targets: dict[str, tuple[str, ...]] = {}
        for phrase, raw_target_ids in self.phrase_targets.items():
            normalized_phrase = validate_canonical_phrase(phrase, "entity corpus phrase")
            if normalized_phrase != phrase:
                raise EntityLinkerError("entity corpus phrases must be normalized")
            if isinstance(raw_target_ids, str):
                raise EntityLinkerError("entity corpus phrase targets must be target ID tuples")
            phrase_target_ids = tuple(raw_target_ids)
            if not phrase_target_ids or tuple(sorted(set(phrase_target_ids))) != phrase_target_ids:
                raise EntityLinkerError("entity corpus phrase targets must be unique and sorted")
            for target_id in phrase_target_ids:
                if target_id not in target_ids_set:
                    raise EntityLinkerError(
                        f"entity corpus phrase has unknown target: {target_id!r}"
                    )
                if phrase not in expected_targets_by_id[target_id].aliases:
                    raise EntityLinkerError(
                        f"entity corpus phrase is absent from target aliases: {phrase!r}"
                    )
            frozen_phrase_targets[phrase] = phrase_target_ids

        frozen_address_targets: dict[str, str] = {}
        for address, target_id in self.address_targets.items():
            if not isinstance(address, str) or not _ADDRESS_RE.fullmatch(address):
                raise EntityLinkerError(f"invalid entity corpus address: {address!r}")
            if target_id not in target_ids_set:
                raise EntityLinkerError(f"entity corpus address has unknown target: {target_id!r}")
            if address not in expected_targets_by_id[target_id].addresses:
                raise EntityLinkerError(
                    f"entity corpus address is absent from target addresses: {address!r}"
                )
            frozen_address_targets[address] = target_id

        validate_digest(self.entities_sha256, "entities fingerprint")
        validate_digest(self.aliases_sha256, "aliases fingerprint")
        validate_digest(self.concepts_sha256, "concepts fingerprint")
        object.__setattr__(self, "targets", targets)
        object.__setattr__(
            self,
            "targets_by_id",
            MappingProxyType(dict(sorted(expected_targets_by_id.items()))),
        )
        object.__setattr__(
            self,
            "phrase_targets",
            MappingProxyType(dict(sorted(frozen_phrase_targets.items()))),
        )
        object.__setattr__(
            self,
            "address_targets",
            MappingProxyType(dict(sorted(frozen_address_targets.items()))),
        )


@dataclass(frozen=True)
class EntityCachePaths:
    """Stable paths for an entity index manifest, matrix base, and lock."""

    manifest: Path
    matrices: Path
    lock: Path

    @classmethod
    def from_directory(cls, directory: Path) -> EntityCachePaths:
        return cls(
            manifest=directory / "entity-index.json",
            matrices=directory / "entity-index.npz",
            lock=directory / "entity-index.lock",
        )

    def matrix_generation(self, matrices_sha256: str) -> Path:
        validate_digest(matrices_sha256, "matrix generation digest")
        return self.matrices.with_name(
            f"{self.matrices.stem}-{matrices_sha256}{self.matrices.suffix}"
        )
