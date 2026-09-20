"""Canonical, local privacy-review evidence for live B4/B5 evaluation."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path

from nl2sparql.models.b45.contracts import LargeLLMError

_SCHEMA_VERSION = 1
_RECORD_TYPE = "privacy_review"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {
    "schema_version",
    "record_type",
    "input_sha256",
    "reviewed",
    "no_secrets",
    "no_personal_data",
}


@dataclass(frozen=True)
class PrivacyReviewEvidence:
    """Human-review marker for an exact evaluation snapshot.

    The marker is deliberately narrow: it asserts that a reviewer inspected the
    exact input snapshot and found neither secrets nor personal data.  Its
    ``privacy_sha256`` is the digest of the canonical serialized marker and is
    therefore suitable for an externally accepted CLI value.
    """

    input_sha256: str
    reviewed: bool
    no_secrets: bool
    no_personal_data: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.input_sha256, str)
            or _SHA256_RE.fullmatch(self.input_sha256) is None
        ):
            raise LargeLLMError("privacy review input fingerprint is invalid")
        if any(
            not isinstance(value, bool)
            for value in (self.reviewed, self.no_secrets, self.no_personal_data)
        ):
            raise LargeLLMError("privacy review assertions must be boolean")
        if not self.reviewed:
            raise LargeLLMError("privacy review must assert reviewed")
        if not self.no_secrets:
            raise LargeLLMError("privacy review must assert no secrets")
        if not self.no_personal_data:
            raise LargeLLMError("privacy review must assert no personal data")

    @property
    def privacy_sha256(self) -> str:
        """Return the digest of the canonical sidecar payload."""
        return hashlib.sha256(serialize_privacy_review(self)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _payload(evidence: PrivacyReviewEvidence) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "record_type": _RECORD_TYPE,
        "input_sha256": evidence.input_sha256,
        "reviewed": evidence.reviewed,
        "no_secrets": evidence.no_secrets,
        "no_personal_data": evidence.no_personal_data,
    }


def serialize_privacy_review(evidence: PrivacyReviewEvidence) -> bytes:
    """Serialize one validated privacy marker in canonical JSONL form.

    Args:
        evidence: Immutable review assertions bound to one input digest.

    Returns:
        UTF-8 canonical JSON with one trailing newline.

    Raises:
        LargeLLMError: If ``evidence`` is not validated privacy evidence.
    """
    if not isinstance(evidence, PrivacyReviewEvidence):
        raise LargeLLMError("privacy review evidence is invalid")
    return _canonical_json(_payload(evidence))


def privacy_review_path(test_set: Path) -> Path:
    """Return the default sidecar path for one evaluation snapshot."""
    if not isinstance(test_set, Path):
        raise LargeLLMError("evaluation snapshot path must be a pathlib.Path")
    return Path(f"{test_set}.privacy.json")


def _parse_payload(payload: bytes) -> PrivacyReviewEvidence:
    if not payload or not payload.endswith(b"\n"):
        raise LargeLLMError("privacy review sidecar is not canonical")
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LargeLLMError("privacy review sidecar is invalid JSON") from error
    if not isinstance(raw, dict) or set(raw) != _KEYS or _canonical_json(raw) != payload:
        raise LargeLLMError("privacy review sidecar is not canonical")
    if raw["schema_version"] != _SCHEMA_VERSION or raw["record_type"] != _RECORD_TYPE:
        raise LargeLLMError("privacy review sidecar schema is invalid")
    try:
        return PrivacyReviewEvidence(
            input_sha256=raw["input_sha256"],  # type: ignore[arg-type]
            reviewed=raw["reviewed"],  # type: ignore[arg-type]
            no_secrets=raw["no_secrets"],  # type: ignore[arg-type]
            no_personal_data=raw["no_personal_data"],  # type: ignore[arg-type]
        )
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"privacy review sidecar is invalid: {error}") from error


def load_privacy_review(
    path: Path,
    *,
    expected_input_sha256: str,
    accepted_sha256: str | None = None,
) -> PrivacyReviewEvidence:
    """Load and validate a privacy marker against input and accepted digest.

    Args:
        path: Canonical local privacy-review sidecar path.
        expected_input_sha256: Digest of the exact evaluation snapshot bytes.
        accepted_sha256: Optional externally accepted digest of the sidecar.

    Returns:
        Validated immutable privacy-review evidence.

    Raises:
        LargeLLMError: If the marker is missing, stale, tampered, or incomplete.
    """
    if not isinstance(path, Path):
        raise LargeLLMError("privacy review path must be a pathlib.Path")
    if (
        not isinstance(expected_input_sha256, str)
        or _SHA256_RE.fullmatch(expected_input_sha256) is None
    ):
        raise LargeLLMError("expected privacy input fingerprint is invalid")
    if accepted_sha256 is not None and _SHA256_RE.fullmatch(accepted_sha256) is None:
        raise LargeLLMError("accepted privacy review fingerprint is invalid")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise LargeLLMError("privacy review sidecar does not exist") from error
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if accepted_sha256 is not None and not hmac.compare_digest(actual_sha256, accepted_sha256):
        raise LargeLLMError("privacy review fingerprint does not match accepted evidence")
    evidence = _parse_payload(payload)
    if evidence.input_sha256 != expected_input_sha256:
        raise LargeLLMError("privacy review input fingerprint does not match evaluation snapshot")
    return evidence


__all__ = [
    "PrivacyReviewEvidence",
    "load_privacy_review",
    "privacy_review_path",
    "serialize_privacy_review",
]
