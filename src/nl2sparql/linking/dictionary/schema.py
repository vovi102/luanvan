from __future__ import annotations

import re

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
VALID_CONFIDENCE = {"high", "medium", "low"}


class DictionaryValidationError(ValueError):
    """Raised when an entity dictionary artifact is malformed."""


def normalize_alias(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    if not normalized:
        raise DictionaryValidationError("Alias must not be empty")
    return normalized


def normalize_address(value: str) -> str:
    if not isinstance(value, str) or not ADDRESS_RE.match(value):
        raise DictionaryValidationError(f"Invalid Ethereum address: {value!r}")
    return value.lower()


def validate_confidence(value: str) -> str:
    if value not in VALID_CONFIDENCE:
        raise DictionaryValidationError(f"Invalid confidence: {value!r}")
    return value
