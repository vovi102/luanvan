"""Immutable contracts for T3.4 deterministic noise injection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class NoiseValidationError(ValueError):
    """Raised when noise data violates the T3.4 contract."""


class NoiseType(StrEnum):
    """Allowed single-operation noise labels."""

    TYPO = "typo"
    ABBREV = "abbrev"
    FRAGMENT = "fragment"
    MIXED_CASE = "mixed_case"


DEFAULT_QUOTAS: dict[NoiseType, int] = {
    NoiseType.TYPO: 38,
    NoiseType.ABBREV: 38,
    NoiseType.FRAGMENT: 37,
    NoiseType.MIXED_CASE: 37,
}


@dataclass(frozen=True)
class NoiseConfig:
    """Pinned seed and exact output quotas for the Stage D dataset."""

    seed: int = 42
    quotas: Mapping[NoiseType, int] = field(default_factory=lambda: dict(DEFAULT_QUOTAS))

    def __post_init__(self) -> None:
        if self.seed != 42 or isinstance(self.seed, bool):
            raise NoiseValidationError("noise seed must equal the pinned value 42")
        if dict(self.quotas) != DEFAULT_QUOTAS:
            raise NoiseValidationError("noise quotas must equal the T3.4 contract")
        object.__setattr__(self, "quotas", MappingProxyType(dict(self.quotas)))
