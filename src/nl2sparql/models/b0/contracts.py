"""Immutable contracts for the deterministic B0 baseline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Literal

from nl2sparql.dataset.templates.validate import SUPPORTED_SLOT_TYPES

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TEMPLATE_ID_RE = re.compile(r"^T_[A-Z0-9_]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class B0Error(ValueError):
    """Raised when a B0 contract or construction artifact is invalid."""


def _probability(value: object, label: str, *, allow_zero: bool) -> float:
    if (
        not isinstance(value, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value > 1.0
        or value < 0.0
        or (not allow_zero and value == 0.0)
    ):
        interval = "[0, 1]" if allow_zero else "(0, 1]"
        raise B0Error(f"{label} must be a finite float in {interval}")
    return value


def _digest(value: str | None, label: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise B0Error(f"{label} must be a lowercase SHA-256 digest")


def _unique_tuple(values: tuple[str, ...], label: str, *, ordered: bool = False) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise B0Error(f"{label} must be a tuple of non-empty strings")
    if len(values) != len(set(values)):
        raise B0Error(f"{label} must be unique")
    if ordered and values != tuple(sorted(values)):
        raise B0Error(f"{label} must be ordered")


@dataclass(frozen=True)
class B0Policy:
    """Fingerprint-bound matching thresholds."""

    structural_threshold: float = 0.62
    ambiguity_margin: float = 0.03

    def __post_init__(self) -> None:
        _probability(self.structural_threshold, "structural threshold", allow_zero=False)
        margin = _probability(self.ambiguity_margin, "ambiguity margin", allow_zero=True)
        if margin >= 1.0:
            raise B0Error("ambiguity margin must be a finite float in [0, 1)")

    @property
    def sha256(self) -> str:
        body = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SlotValue:
    """One typed template value and its source span."""

    name: str
    slot_type: str
    value: str | int
    span_offset: tuple[int, int]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _IDENTIFIER_RE.fullmatch(self.name):
            raise B0Error("slot name is invalid")
        if self.slot_type not in SUPPORTED_SLOT_TYPES:
            raise B0Error("slot type is invalid")
        if isinstance(self.value, bool) or not isinstance(self.value, (str, int)):
            raise B0Error("slot value must be a string or integer")
        if isinstance(self.value, str) and not self.value:
            raise B0Error("slot string value must not be empty")
        if (
            not isinstance(self.span_offset, tuple)
            or len(self.span_offset) != 2
            or any(
                not isinstance(offset, int) or isinstance(offset, bool)
                for offset in self.span_offset
            )
            or self.span_offset[0] < 0
            or self.span_offset[1] <= self.span_offset[0]
        ):
            raise B0Error("slot span must be a valid half-open source range")


@dataclass(frozen=True)
class B0Prediction:
    """One safe SQL prediction with matching and source provenance."""

    sql: str
    template_id: str
    match_mode: Literal["seed", "structural"]
    score: float
    slots: tuple[SlotValue, ...]
    template_sha256: str
    policy_sha256: str
    catalog_sha256: str | None
    entities_sha256: str | None
    aliases_sha256: str | None
    concepts_sha256: str | None
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sql, str) or not self.sql.strip():
            raise B0Error("prediction SQL must not be empty")
        if not isinstance(self.template_id, str) or not _TEMPLATE_ID_RE.fullmatch(self.template_id):
            raise B0Error("prediction template ID is invalid")
        if self.match_mode not in {"seed", "structural"}:
            raise B0Error("prediction match mode is invalid")
        _probability(self.score, "prediction score", allow_zero=True)
        if not isinstance(self.slots, tuple) or any(
            not isinstance(value, SlotValue) for value in self.slots
        ):
            raise B0Error("prediction slots must contain SlotValue values")
        names = tuple(value.name for value in self.slots)
        if len(names) != len(set(names)):
            raise B0Error("prediction slot names must be unique")
        _digest(self.template_sha256, "template fingerprint")
        _digest(self.policy_sha256, "policy fingerprint")
        for label, value in (
            ("catalog fingerprint", self.catalog_sha256),
            ("entities fingerprint", self.entities_sha256),
            ("aliases fingerprint", self.aliases_sha256),
            ("concepts fingerprint", self.concepts_sha256),
        ):
            _digest(value, label, optional=True)
        _unique_tuple(self.schema_elements, "schema elements")
        _unique_tuple(self.cq_ids, "CQ IDs")
        _unique_tuple(self.warnings, "prediction warnings", ordered=True)
