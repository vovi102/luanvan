from __future__ import annotations

import re

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_ADDRESS_ROLES = {"operational", "token", "treasury"}


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


def validate_chain_id(value: str | int) -> int:
    if value not in (1, "1"):
        raise DictionaryValidationError(
            f"Expected Ethereum chain_id 1, received: {value!r}"
        )
    return 1


def validate_address_role(value: str) -> str:
    if value not in VALID_ADDRESS_ROLES:
        raise DictionaryValidationError(f"Invalid address_role: {value!r}")
    return value


def validate_source_revision(value: str) -> str:
    if not isinstance(value, str) or not (
        GIT_SHA_RE.fullmatch(value) or SHA256_RE.fullmatch(value)
    ):
        raise DictionaryValidationError(f"Invalid source_revision: {value!r}")
    return value


def validate_source_locator(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DictionaryValidationError(f"Invalid source_locator: {value!r}")
    return value.strip()
