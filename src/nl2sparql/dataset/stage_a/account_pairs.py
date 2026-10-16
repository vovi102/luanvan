"""Strict relationship evidence for Stage A account-pair generation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Self

ACCOUNT_PAIR_COUNT = 40
ACCOUNT_PAIR_SOURCE = "BigQuery nl2sparql_analytics.transaction_facts"
ACCOUNT_PAIR_START_DATE = "2026-06-15"
ACCOUNT_PAIR_END_DATE = "2026-06-16"
ACCOUNT_PAIR_PROJECT = "nl2sparql-thesis"
ACCOUNT_PAIR_LOCATION = "US"
ACCOUNT_PAIR_JOB_ID = "d7aa2151-18e4-4f3f-99c4-2c255bdbfe0e"
ACCOUNT_PAIR_QUERY_SHA256 = "d85c553b8fef8621e68f847b31179b80e4b7bbab6397c7c8ed5a01b06569436d"
ACCOUNT_PAIR_MAXIMUM_BYTES_BILLED = 1_073_741_824

_ADDRESS_RE = re.compile(r"0x[0-9a-f]{40}")
_PAIR_FIELDS = {"account", "account_b", "start_date", "end_date", "source", "evidence"}
_EVIDENCE_FIELDS = {
    "project",
    "location",
    "job_id",
    "query_sha256",
    "result_row",
    "transaction_count",
    "first_seen_at",
    "last_seen_at",
    "total_bytes_processed",
    "total_bytes_billed",
    "cache_hit",
    "billing_enabled",
    "maximum_bytes_billed",
}


class AccountPairError(ValueError):
    """Raised when account-pair relationship evidence is incomplete or contradictory."""


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AccountPairError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AccountPairError(f"{field} must be a non-negative integer")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AccountPairError(f"{field} must be a non-empty string")
    return value


def _utc_timestamp(value: object, field: str) -> datetime:
    text = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AccountPairError(f"{field} must be a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise AccountPairError(f"{field} must be UTC")
    if not text.endswith("+00:00"):
        raise AccountPairError(f"{field} must use the canonical UTC offset")
    return parsed


def _fixed_date(value: object, field: str, expected: str) -> date:
    text = _required_text(value, field)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise AccountPairError(f"{field} must be a valid ISO date") from exc
    if text != expected:
        raise AccountPairError(
            f"account-pair window must be [{ACCOUNT_PAIR_START_DATE}, {ACCOUNT_PAIR_END_DATE})"
        )
    return parsed


@dataclass(frozen=True)
class AccountPairEvidence:
    """Provenance for one row from the bounded account-pair diagnostic query."""

    project: str
    location: str
    job_id: str
    query_sha256: str
    result_row: int
    transaction_count: int
    first_seen_at: str
    last_seen_at: str
    total_bytes_processed: int
    total_bytes_billed: int
    cache_hit: bool
    billing_enabled: bool
    maximum_bytes_billed: int

    def __post_init__(self) -> None:
        if self.project != ACCOUNT_PAIR_PROJECT:
            raise AccountPairError(f"project must be {ACCOUNT_PAIR_PROJECT}")
        if self.location != ACCOUNT_PAIR_LOCATION:
            raise AccountPairError(f"location must be {ACCOUNT_PAIR_LOCATION}")
        if self.job_id != ACCOUNT_PAIR_JOB_ID:
            raise AccountPairError("job_id does not match the captured diagnostic job")
        if self.query_sha256 != ACCOUNT_PAIR_QUERY_SHA256:
            raise AccountPairError("query_sha256 does not match the captured diagnostic query")
        _positive_int(self.result_row, "result_row")
        _positive_int(self.transaction_count, "transaction_count")
        first_seen = _utc_timestamp(self.first_seen_at, "first_seen_at")
        last_seen = _utc_timestamp(self.last_seen_at, "last_seen_at")
        if first_seen > last_seen:
            raise AccountPairError("account-pair timestamp order is invalid")
        processed = _nonnegative_int(self.total_bytes_processed, "total_bytes_processed")
        billed = _nonnegative_int(self.total_bytes_billed, "total_bytes_billed")
        maximum = _positive_int(self.maximum_bytes_billed, "maximum_bytes_billed")
        if processed > billed:
            raise AccountPairError("processed and billed bytes are contradictory")
        if billed > maximum:
            raise AccountPairError("billed bytes exceed maximum_bytes_billed")
        if maximum != ACCOUNT_PAIR_MAXIMUM_BYTES_BILLED:
            raise AccountPairError("maximum_bytes_billed must equal the 1 GiB diagnostic cap")
        if self.cache_hit is not False:
            raise AccountPairError("account-pair evidence must have cache disabled")
        if self.billing_enabled is not False:
            raise AccountPairError("account-pair evidence requires disabled billing")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Self:
        """Parse the exact evidence schema without coercing values."""
        if not isinstance(value, Mapping) or set(value) != _EVIDENCE_FIELDS:
            raise AccountPairError("account-pair evidence fields mismatch")
        try:
            return cls(**dict(value))
        except TypeError as exc:
            raise AccountPairError("account-pair evidence schema mismatch") from exc

    def to_mapping(self) -> dict[str, Any]:
        """Serialize the exact relationship-evidence schema."""
        return {
            "project": self.project,
            "location": self.location,
            "job_id": self.job_id,
            "query_sha256": self.query_sha256,
            "result_row": self.result_row,
            "transaction_count": self.transaction_count,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "total_bytes_processed": self.total_bytes_processed,
            "total_bytes_billed": self.total_bytes_billed,
            "cache_hit": self.cache_hit,
            "billing_enabled": self.billing_enabled,
            "maximum_bytes_billed": self.maximum_bytes_billed,
        }

    def diagnostic_identity(self) -> tuple[object, ...]:
        """Return fields that must remain identical across one captured job."""
        return (
            self.project,
            self.location,
            self.job_id,
            self.query_sha256,
            self.total_bytes_processed,
            self.total_bytes_billed,
            self.cache_hit,
            self.billing_enabled,
            self.maximum_bytes_billed,
        )


@dataclass(frozen=True)
class AccountPair:
    """An atomic endpoint/window binding proven by one diagnostic result row."""

    account: str
    account_b: str
    start_date: str
    end_date: str
    source: str
    evidence: AccountPairEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.account, str) or _ADDRESS_RE.fullmatch(self.account) is None:
            raise AccountPairError("account must be a lowercase Ethereum address")
        if not isinstance(self.account_b, str) or _ADDRESS_RE.fullmatch(self.account_b) is None:
            raise AccountPairError("account_b must be a lowercase Ethereum address")
        if self.account == self.account_b:
            raise AccountPairError("account endpoints must differ")
        if self.account >= self.account_b:
            raise AccountPairError("account endpoints must use lexicographic order")
        start = _fixed_date(self.start_date, "start_date", ACCOUNT_PAIR_START_DATE)
        end = _fixed_date(self.end_date, "end_date", ACCOUNT_PAIR_END_DATE)
        if start >= end:
            raise AccountPairError("account-pair date window must be increasing")
        if self.source != ACCOUNT_PAIR_SOURCE:
            raise AccountPairError(f"source must be {ACCOUNT_PAIR_SOURCE}")
        if not isinstance(self.evidence, AccountPairEvidence):
            raise AccountPairError("evidence must be complete account-pair provenance")
        first_seen = _utc_timestamp(self.evidence.first_seen_at, "first_seen_at")
        last_seen = _utc_timestamp(self.evidence.last_seen_at, "last_seen_at")
        window_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        window_end = datetime.combine(end, datetime.min.time(), tzinfo=UTC)
        if not (window_start <= first_seen <= last_seen < window_end):
            raise AccountPairError("evidence timestamps must fall within the half-open window")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Self:
        """Parse one complete pair without separating its endpoints or provenance."""
        if not isinstance(value, Mapping) or set(value) != _PAIR_FIELDS:
            raise AccountPairError("account-pair fields mismatch")
        evidence = value.get("evidence")
        if not isinstance(evidence, Mapping):
            raise AccountPairError("evidence must be a complete object")
        converted = dict(value)
        converted["evidence"] = AccountPairEvidence.from_mapping(evidence)
        try:
            return cls(**converted)
        except TypeError as exc:
            raise AccountPairError("account-pair schema mismatch") from exc

    def to_mapping(self) -> dict[str, Any]:
        """Serialize the pair as one indivisible mapping."""
        return {
            "account": self.account,
            "account_b": self.account_b,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source": self.source,
            "evidence": self.evidence.to_mapping(),
        }


def load_account_pairs(
    pools: Mapping[str, Any], *, expected_count: int = ACCOUNT_PAIR_COUNT
) -> tuple[AccountPair, ...]:
    """Load and cross-check the complete relationship-evidence pool."""
    _positive_int(expected_count, "expected_count")
    entries = pools.get("account_pair") if isinstance(pools, Mapping) else None
    if not isinstance(entries, list):
        raise AccountPairError("account_pair must be an array")
    if len(entries) != expected_count:
        raise AccountPairError(f"account_pair must contain exactly {expected_count} entries")
    pairs: list[AccountPair] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise AccountPairError("each account_pair entry must be an object")
        pairs.append(AccountPair.from_mapping(entry))
    endpoints = [endpoint for pair in pairs for endpoint in (pair.account, pair.account_b)]
    if len(set(endpoints)) != len(endpoints):
        raise AccountPairError("account_pair endpoints must be globally distinct")
    result_rows = [pair.evidence.result_row for pair in pairs]
    if len(set(result_rows)) != len(result_rows):
        raise AccountPairError("account_pair result_row values must be unique")
    identities = {pair.evidence.diagnostic_identity() for pair in pairs}
    if len(identities) != 1:
        raise AccountPairError("account_pair diagnostic metadata must be identical")
    return tuple(pairs)


def canonical_account_pair_mappings(pools: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Canonicalize by sorting complete pair mappings as atomic values."""
    mappings = [pair.to_mapping() for pair in load_account_pairs(pools)]
    return sorted(
        mappings,
        key=lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ),
    )
