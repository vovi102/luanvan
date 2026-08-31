"""Immutable contracts for GoogleSQL entity-constraint resolution."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_CLASS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class ClassResolverError(ValueError):
    """Raised when resolver input, evidence, or output violates its contract."""


def _required_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 10_000
        or _CONTROL_RE.search(value)
    ):
        raise ClassResolverError(f"{label} must be non-empty, bounded, and control-free")
    return value


def _validate_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ClassResolverError(f"{label} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, order=True)
class FieldCandidate:
    """One validated analytical relation/field identity, never SQL text."""

    relation: str
    field: str

    def __post_init__(self) -> None:
        if not isinstance(self.relation, str) or not _IDENTIFIER_RE.fullmatch(self.relation):
            raise ClassResolverError("field candidate relation is invalid")
        if not isinstance(self.field, str) or not _IDENTIFIER_RE.fullmatch(self.field):
            raise ClassResolverError("field candidate field is invalid")


@dataclass(frozen=True)
class ResolvedEntity:
    """One entity mention expressed as a typed, non-executable constraint."""

    span: str
    span_offset: tuple[int, int]
    target_id: str
    target_sha256: str
    resolution_kind: Literal["instance", "concept", "unresolved"]
    direction: Literal["from", "to", "token", "unspecified"]
    fields: tuple[FieldCandidate, ...]
    operator: Literal["in", "equals", "none"]
    values: tuple[str, ...]
    required_relation: str | None
    required_join: str | None
    required_role: str | None
    coverage_status: Literal["supported", "coverage_gap", "unresolved"]
    confidence: float
    explanation: str

    def __post_init__(self) -> None:
        _required_text(self.span, "resolved span")
        _required_text(self.target_id, "resolved target ID")
        _required_text(self.explanation, "resolved explanation")
        _validate_digest(self.target_sha256, "resolved target fingerprint")
        if (
            not isinstance(self.span_offset, tuple)
            or len(self.span_offset) != 2
            or any(
                not isinstance(value, int) or isinstance(value, bool) for value in self.span_offset
            )
            or self.span_offset[0] < 0
            or self.span_offset[1] <= self.span_offset[0]
        ):
            raise ClassResolverError("resolved span offset must be a valid two-item tuple")
        if self.resolution_kind not in {"instance", "concept", "unresolved"}:
            raise ClassResolverError("resolution kind is invalid")
        if self.direction not in {"from", "to", "token", "unspecified"}:
            raise ClassResolverError("resolution direction is invalid")
        if not isinstance(self.fields, tuple):
            raise ClassResolverError("resolved fields must be a tuple")
        if any(not isinstance(value, FieldCandidate) for value in self.fields):
            raise ClassResolverError("resolved fields must contain field candidates")
        if tuple(sorted(set(self.fields))) != self.fields:
            raise ClassResolverError("resolved fields must be unique and ordered")
        if not isinstance(self.values, tuple) or any(
            not isinstance(value, str) for value in self.values
        ):
            raise ClassResolverError("resolved values must be a tuple of strings")
        if tuple(sorted(set(self.values))) != self.values:
            raise ClassResolverError("resolved values must be unique and ordered")
        if self.operator not in {"in", "equals", "none"}:
            raise ClassResolverError("resolved operator is invalid")
        if self.coverage_status not in {"supported", "coverage_gap", "unresolved"}:
            raise ClassResolverError("coverage status is invalid")
        if (
            not isinstance(self.confidence, float)
            or isinstance(self.confidence, bool)
            or not math.isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ClassResolverError("resolved confidence must be finite in [0, 1]")
        for label, value in (
            ("required relation", self.required_relation),
            ("required join", self.required_join),
            ("required role", self.required_role),
        ):
            if value is not None and (
                not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value)
            ):
                raise ClassResolverError(f"{label} is invalid")

        if self.resolution_kind == "unresolved":
            if (
                self.operator != "none"
                or self.values
                or self.fields
                or self.required_relation is not None
                or self.required_join is not None
                or self.required_role is not None
                or self.coverage_status != "unresolved"
            ):
                raise ClassResolverError("unresolved entities cannot claim a constraint")
        elif self.resolution_kind == "instance":
            if self.operator != "in" or not self.values:
                raise ClassResolverError("instance operator must bind at least one address")
            if any(not _ADDRESS_RE.fullmatch(value) for value in self.values):
                raise ClassResolverError("instance values must be canonical addresses")
            if self.required_relation is not None or self.required_join is not None:
                raise ClassResolverError("instance constraints cannot require a label join")
            if self.coverage_status != "supported":
                raise ClassResolverError("instance constraints must have supported coverage")
        else:
            if (
                self.operator != "equals"
                or len(self.values) != 1
                or not _CLASS_RE.fullmatch(self.values[0])
            ):
                raise ClassResolverError("concept operator must equal one canonical class")
            if self.required_relation is None or self.required_join is None:
                raise ClassResolverError("concept constraints require a relation and join")
            if self.coverage_status == "unresolved":
                raise ClassResolverError("resolved concepts must declare coverage")


@dataclass(frozen=True)
class ResolutionPlan:
    """Provenance-bound resolver output for one natural-language question."""

    question_sha256: str
    entities: tuple[ResolvedEntity, ...]
    catalog_sha256: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str
    status: Literal["resolved", "partial", "unresolved"]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("question fingerprint", self.question_sha256),
            ("catalog fingerprint", self.catalog_sha256),
            ("entities fingerprint", self.entities_sha256),
            ("aliases fingerprint", self.aliases_sha256),
            ("concepts fingerprint", self.concepts_sha256),
        ):
            _validate_digest(value, label)
        if not isinstance(self.entities, tuple):
            raise ClassResolverError("resolution plan entities must be a tuple")
        if any(not isinstance(value, ResolvedEntity) for value in self.entities):
            raise ClassResolverError("resolution plan contains an invalid entity")
        if not isinstance(self.warnings, tuple):
            raise ClassResolverError("resolution plan warnings must be a tuple")
        if any(not isinstance(value, str) or not value for value in self.warnings):
            raise ClassResolverError("resolution plan warnings are invalid")
        if tuple(sorted(set(self.warnings))) != self.warnings:
            raise ClassResolverError("resolution plan warnings must be unique and ordered")
        if self.status not in {"resolved", "partial", "unresolved"}:
            raise ClassResolverError("resolution plan status is invalid")

        unresolved = sum(value.resolution_kind == "unresolved" for value in self.entities)
        if not self.entities or unresolved == len(self.entities):
            expected = "unresolved"
        elif unresolved or self.warnings:
            expected = "partial"
        else:
            expected = "resolved"
        if self.status != expected:
            raise ClassResolverError(
                f"resolution plan status {self.status!r} must be {expected!r} "
                "for its entities and warnings"
            )
