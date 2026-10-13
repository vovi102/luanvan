"""Deterministic logical-to-physical query planning for Stage A witnesses."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from nl2sparql.dataset.stage_a.evidence import (
    WitnessEvidenceError,
    WitnessGroup,
    WitnessQuery,
    build_witness_groups,
)

_HEX_64_RE = re.compile(r"[0-9a-f]{64}")
_TRANSACTION_HASH_RE = re.compile(r"0x[0-9a-f]{64}")
_ETHEREUM_ADDRESS_RE = re.compile(r"0x[0-9a-f]{40}")
_TX_TEMPLATE_ID = "T_TX_BY_HASH"
_ACCOUNT_PAIR_TEMPLATE_ID = "T_TX_BETWEEN_ACCOUNTS"
_ACCOUNT_PAIR_BATCH_SIZE = 10
_TX_COLUMNS = (
    "transaction_hash",
    "block_timestamp",
    "from_address",
    "to_address",
    "value_wei",
    "is_success",
)


def _query_id(
    *, proof_kind: str, template_id: str, group_ids: tuple[str, ...], query_sha256: str
) -> str:
    identity = json.dumps(
        {
            "proof_kind": proof_kind,
            "template_id": template_id,
            "group_ids": group_ids,
            "query_sha256": query_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _witness_query(
    *, proof_kind: str, template_id: str, group_ids: tuple[str, ...], sql: str
) -> WitnessQuery:
    query_sha256 = hashlib.sha256(sql.encode()).hexdigest()
    return WitnessQuery(
        query_id=_query_id(
            proof_kind=proof_kind,
            template_id=template_id,
            group_ids=group_ids,
            query_sha256=query_sha256,
        ),
        query_sha256=query_sha256,
        proof_kind=proof_kind,
        template_id=template_id,
        group_ids=group_ids,
        sql=sql,
    )


def build_single_witness_queries(
    records: Sequence[Mapping[str, Any]],
) -> tuple[WitnessQuery, ...]:
    """Map each logical witness to its existing SQL, preserving group order."""
    return tuple(
        _witness_query(
            proof_kind="single",
            template_id=group.template_id,
            group_ids=(group.group_id,),
            sql=group.sql,
        )
        for group in build_witness_groups(records)
    )


def _validate_group_id(group_id: str) -> None:
    if not _HEX_64_RE.fullmatch(group_id):
        raise WitnessEvidenceError("Batch witness group IDs must be lowercase SHA-256 hex")


def _strict_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise WitnessEvidenceError(f"Batch {field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise WitnessEvidenceError(f"Batch {field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise WitnessEvidenceError(f"Batch {field} must use YYYY-MM-DD")
    return value


def _render_tx_hash_batch(
    groups: Sequence[WitnessGroup], records_by_id: Mapping[str, Mapping[str, Any]]
) -> WitnessQuery:
    if len(groups) < 2:
        raise WitnessEvidenceError("Transaction-hash batch requires at least two witnesses")
    requested: list[tuple[str, str]] = []
    windows: set[tuple[str, str]] = set()
    for group in groups:
        if group.template_id != _TX_TEMPLATE_ID or len(group.member_record_ids) != 1:
            raise WitnessEvidenceError(
                "Transaction-hash batch requires singleton T_TX_BY_HASH groups"
            )
        _validate_group_id(group.group_id)
        record = records_by_id.get(group.witness_record_id)
        if record is None:
            raise WitnessEvidenceError("Transaction-hash witness record is missing")
        slots = record.get("slot_values")
        if not isinstance(slots, Mapping):
            raise WitnessEvidenceError("Transaction-hash witness slots are missing")
        transaction_hash = slots.get("transaction_hash")
        if not isinstance(transaction_hash, str) or not _TRANSACTION_HASH_RE.fullmatch(
            transaction_hash
        ):
            raise WitnessEvidenceError("Transaction hashes must be lowercase 0x-prefixed hex")
        windows.add(
            (
                _strict_date(slots.get("start_date"), "start_date"),
                _strict_date(slots.get("end_date"), "end_date"),
            )
        )
        requested.append((group.group_id, transaction_hash))
    if len(windows) != 1:
        raise WitnessEvidenceError("Transaction-hash batch requires one shared date window")
    if len({group_id for group_id, _ in requested}) != len(requested):
        raise WitnessEvidenceError("Transaction-hash batch contains repeated group IDs")
    if len({transaction_hash for _, transaction_hash in requested}) != len(requested):
        raise WitnessEvidenceError("Transaction-hash batch contains repeated hashes")

    requested.sort()
    start_date, end_date = next(iter(windows))
    structs = ",\n    ".join(
        f"STRUCT('{group_id}' AS witness_group_id, '{transaction_hash}' AS transaction_hash)"
        for group_id, transaction_hash in requested
    )
    selected_columns = ",\n  ".join(f"facts.{column}" for column in _TX_COLUMNS)
    sql = (
        "WITH requested AS (\n"
        "  SELECT *\n"
        "  FROM UNNEST([\n"
        f"    {structs}\n"
        "  ])\n"
        ")\n"
        "SELECT\n"
        "  requested.witness_group_id,\n"
        f"  {selected_columns}\n"
        "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
        f"(DATE '{start_date}', DATE '{end_date}') AS facts\n"
        "JOIN requested USING (transaction_hash)"
    )
    return _witness_query(
        proof_kind="tx_hash_batch",
        template_id=_TX_TEMPLATE_ID,
        group_ids=tuple(group_id for group_id, _ in requested),
        sql=sql,
    )


def _render_account_pair_batch(
    groups: Sequence[WitnessGroup], records_by_id: Mapping[str, Mapping[str, Any]]
) -> WitnessQuery:
    if len(groups) != _ACCOUNT_PAIR_BATCH_SIZE:
        raise WitnessEvidenceError("Account-pair batch requires exactly 10 witnesses")
    requested: list[tuple[str, str, str]] = []
    windows: set[tuple[str, str]] = set()
    for group in groups:
        if group.template_id != _ACCOUNT_PAIR_TEMPLATE_ID or len(group.member_record_ids) != 1:
            raise WitnessEvidenceError(
                "Account-pair batch requires singleton T_TX_BETWEEN_ACCOUNTS groups"
            )
        _validate_group_id(group.group_id)
        record = records_by_id.get(group.witness_record_id)
        if record is None:
            raise WitnessEvidenceError("Account-pair witness record is missing")
        slots = record.get("slot_values")
        if not isinstance(slots, Mapping):
            raise WitnessEvidenceError("Account-pair witness slots are missing")
        account = slots.get("account")
        account_b = slots.get("account_b")
        if (
            not isinstance(account, str)
            or not isinstance(account_b, str)
            or _ETHEREUM_ADDRESS_RE.fullmatch(account) is None
            or _ETHEREUM_ADDRESS_RE.fullmatch(account_b) is None
            or account >= account_b
        ):
            raise WitnessEvidenceError("Account-pair witnesses require canonical endpoints")
        windows.add(
            (
                _strict_date(slots.get("start_date"), "start_date"),
                _strict_date(slots.get("end_date"), "end_date"),
            )
        )
        requested.append((group.group_id, account, account_b))
    if len(windows) != 1:
        raise WitnessEvidenceError("Account-pair batch requires one shared date window")
    if len({group_id for group_id, _, _ in requested}) != len(requested):
        raise WitnessEvidenceError("Account-pair batch contains repeated group IDs")
    if len({(account, account_b) for _, account, account_b in requested}) != len(requested):
        raise WitnessEvidenceError("Account-pair batch contains repeated endpoint pairs")

    requested.sort()
    start_date, end_date = next(iter(windows))
    structs = ",\n    ".join(
        "STRUCT("
        f"'{group_id}' AS witness_group_id, "
        f"'{account}' AS account, "
        f"'{account_b}' AS account_b)"
        for group_id, account, account_b in requested
    )
    selected_columns = ",\n  ".join(f"facts.{column}" for column in _TX_COLUMNS[:-1])
    sql = (
        "WITH requested AS (\n"
        "  SELECT *\n"
        "  FROM UNNEST([\n"
        f"    {structs}\n"
        "  ])\n"
        ")\n"
        "SELECT\n"
        "  requested.witness_group_id,\n"
        f"  {selected_columns}\n"
        "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
        f"(DATE '{start_date}', DATE '{end_date}') AS facts\n"
        "JOIN requested\n"
        "  ON (facts.from_address = requested.account "
        "AND facts.to_address = requested.account_b)\n"
        "  OR (facts.from_address = requested.account_b "
        "AND facts.to_address = requested.account)\n"
        "QUALIFY ROW_NUMBER() OVER (\n"
        "  PARTITION BY requested.witness_group_id\n"
        "  ORDER BY facts.block_timestamp DESC, facts.transaction_hash\n"
        ") = 1"
    )
    return _witness_query(
        proof_kind="account_pair_batch",
        template_id=_ACCOUNT_PAIR_TEMPLATE_ID,
        group_ids=tuple(group_id for group_id, _, _ in requested),
        sql=sql,
    )


def build_stage_a_v2_witness_queries(
    records: Sequence[Mapping[str, Any]],
) -> tuple[WitnessQuery, ...]:
    """Build the canonical v2 plan with hash and account-pair batch scans."""
    groups = build_witness_groups(records)
    records_by_id = {str(record.get("id")): record for record in records}
    hash_groups = [group for group in groups if group.template_id == _TX_TEMPLATE_ID]
    pair_groups = sorted(
        (group for group in groups if group.template_id == _ACCOUNT_PAIR_TEMPLATE_ID),
        key=lambda group: group.group_id,
    )
    if len(pair_groups) != 40:
        raise WitnessEvidenceError("Stage A v2 requires exactly 40 account-pair witnesses")
    queries = [
        _witness_query(
            proof_kind="single",
            template_id=group.template_id,
            group_ids=(group.group_id,),
            sql=group.sql,
        )
        for group in groups
        if group.template_id not in {_TX_TEMPLATE_ID, _ACCOUNT_PAIR_TEMPLATE_ID}
    ]
    queries.append(_render_tx_hash_batch(hash_groups, records_by_id))
    queries.extend(
        _render_account_pair_batch(
            pair_groups[index : index + _ACCOUNT_PAIR_BATCH_SIZE],
            records_by_id,
        )
        for index in range(0, len(pair_groups), _ACCOUNT_PAIR_BATCH_SIZE)
    )
    return tuple(sorted(queries, key=lambda query: query.group_ids))
