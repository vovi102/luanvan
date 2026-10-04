"""Public language and normalization contracts."""

from nl2sparql.language.contracts import (
    NORMALIZATION_VERSION,
    Language,
    NormalizedInput,
    TextVariant,
)
from nl2sparql.language.normalization import normalize_input

__all__ = [
    "NORMALIZATION_VERSION",
    "Language",
    "NormalizedInput",
    "TextVariant",
    "normalize_input",
]
