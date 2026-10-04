"""Immutable contracts for language-aware natural-language input."""

from dataclasses import dataclass
from typing import Literal

Language = Literal["en", "vi"]
TextVariant = Literal["canonical", "unaccented"]

NORMALIZATION_VERSION = "bilingual-nfc-v1"


@dataclass(frozen=True, slots=True)
class NormalizedInput:
    """Original input plus deterministic, non-destructive comparison forms."""

    original: str
    nfc: str
    match: str
    accent_folded: str
    language: Language
    normalization_version: str = NORMALIZATION_VERSION
