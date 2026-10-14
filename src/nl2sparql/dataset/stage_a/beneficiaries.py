"""Role-specific block beneficiary evidence for Stage A v2."""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any


class BeneficiaryError(ValueError):
    """Raised when block beneficiary evidence is missing or contradictory."""


def load_block_beneficiaries(pools: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Validate four distinct beneficiaries from one bounded block-facts probe."""
    entries = pools.get("block_beneficiary")
    if not isinstance(entries, list) or len(entries) != 4:
        raise BeneficiaryError("block_beneficiary requires exactly four evidence entries")
    addresses: set[str] = set()
    identities: set[tuple[Any, ...]] = set()
    start = datetime(2026, 6, 15, tzinfo=UTC)
    end = datetime(2026, 6, 16, tzinfo=UTC)
    fields = {"value", "source", "start_date", "end_date", "evidence"}
    evidence_fields = {
        "project",
        "location",
        "job_id",
        "query_sha256",
        "block_count",
        "first_seen_at",
        "last_seen_at",
        "total_bytes_processed",
        "total_bytes_billed",
        "cache_hit",
        "billing_enabled",
        "maximum_bytes_billed",
    }
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != fields:
            raise BeneficiaryError("block_beneficiary entry fields mismatch")
        value = entry["value"]
        if (
            not isinstance(value, str)
            or not re.fullmatch(r"0x[0-9a-f]{40}", value)
            or value in addresses
        ):
            raise BeneficiaryError("block_beneficiary requires distinct lowercase addresses")
        addresses.add(value)
        if entry["source"] != "BigQuery nl2sparql_analytics.block_facts":
            raise BeneficiaryError("block_beneficiary requires block-facts role evidence")
        if entry["start_date"] != "2026-06-15" or entry["end_date"] != "2026-06-16":
            raise BeneficiaryError("block_beneficiary date window mismatch")
        evidence = entry["evidence"]
        if not isinstance(evidence, Mapping) or set(evidence) != evidence_fields:
            raise BeneficiaryError("block_beneficiary evidence fields mismatch")
        if evidence["project"] != "nl2sparql-thesis" or evidence["location"] != "US":
            raise BeneficiaryError("block_beneficiary project/location mismatch")
        if not isinstance(evidence["job_id"], str) or not evidence["job_id"].strip():
            raise BeneficiaryError("block_beneficiary job ID is missing")
        if not isinstance(evidence["query_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", evidence["query_sha256"]
        ):
            raise BeneficiaryError("block_beneficiary query digest is invalid")
        for name in (
            "block_count",
            "total_bytes_processed",
            "total_bytes_billed",
            "maximum_bytes_billed",
        ):
            amount = evidence[name]
            if (
                not isinstance(amount, int)
                or isinstance(amount, bool)
                or amount < 0
                or (name in {"block_count", "maximum_bytes_billed"} and amount == 0)
            ):
                raise BeneficiaryError(f"block_beneficiary {name} is invalid")
        if (
            not 0
            <= evidence["total_bytes_processed"]
            <= evidence["total_bytes_billed"]
            <= evidence["maximum_bytes_billed"]
            <= 4 * 2**30
        ):
            raise BeneficiaryError("block_beneficiary byte metrics contradict the cap")
        if evidence["cache_hit"] is not False or evidence["billing_enabled"] is not False:
            raise BeneficiaryError("block_beneficiary requires disabled cache and billing")
        timestamps = []
        for name in ("first_seen_at", "last_seen_at"):
            try:
                raw = evidence[name]
                if not isinstance(raw, str) or not raw.endswith("+00:00"):
                    raise ValueError("UTC timestamp required")
                timestamp = datetime.fromisoformat(raw)
                if (
                    timestamp.utcoffset() != UTC.utcoffset(timestamp)
                    or not start <= timestamp < end
                ):
                    raise ValueError("timestamp outside window")
            except (TypeError, ValueError) as exc:
                raise BeneficiaryError(f"block_beneficiary {name} is invalid") from exc
            timestamps.append(timestamp)
        if timestamps[0] > timestamps[1]:
            raise BeneficiaryError("block_beneficiary timestamps are reversed")
        identities.add(
            tuple(
                evidence[name]
                for name in sorted(
                    evidence_fields - {"block_count", "first_seen_at", "last_seen_at"}
                )
            )
        )
    if len(identities) != 1:
        raise BeneficiaryError("block_beneficiary diagnostic metadata differs across entries")
    return tuple(sorted(entries, key=lambda entry: entry["value"]))
