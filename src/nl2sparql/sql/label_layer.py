from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from nl2sparql.linking.dictionary import ENTITIES_PATH
from nl2sparql.linking.dictionary.schema import (
    DictionaryValidationError,
    normalize_address,
    normalize_alias,
    validate_address_role,
    validate_chain_id,
    validate_confidence,
    validate_source_locator,
    validate_source_revision,
)
from nl2sparql.linking.dictionary.validate import validate_artifacts

LABEL_SNAPSHOT_PREFIX = "entity_labels_snapshot_"
LABEL_ROLES = ("operational", "token", "treasury")

SOURCE_SCHEMA = (
    bigquery.SchemaField("name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("url", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("revision", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("locator", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("retrieved_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("note", "STRING", mode="REQUIRED"),
)

LABEL_TABLE_SCHEMA = (
    bigquery.SchemaField("address", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("chain_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("primary_label", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("owner", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("concept_class", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("address_role", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("aliases", "STRING", mode="REPEATED"),
    bigquery.SchemaField("confidence", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("verified_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("sources", "RECORD", mode="REPEATED", fields=SOURCE_SCHEMA),
    bigquery.SchemaField("dictionary_sha256", "STRING", mode="REQUIRED"),
)


class LabelLayerError(ValueError):
    """Raised when the managed SQL label layer contract is invalid."""


@dataclass(frozen=True)
class LabelSnapshot:
    entities_path: Path
    digest: str
    table_name: str
    entity_count: int
    role_counts: dict[str, int]
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class SqlObject:
    name: str
    kind: str
    dependencies: tuple[str, ...]
    ddl: str


_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")
_OBJECT_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifiers(project: str, dataset: str, object_name: str) -> None:
    if not _PROJECT_ID_RE.fullmatch(project):
        raise LabelLayerError(f"Unsafe project identifier: {project!r}")
    for label, value in (("dataset", dataset), ("object", object_name)):
        if not _OBJECT_ID_RE.fullmatch(value):
            raise LabelLayerError(f"Unsafe {label} identifier: {value!r}")


def _qualified(project: str, dataset: str, object_name: str) -> str:
    _validate_identifiers(project, dataset, object_name)
    return f"`{project}.{dataset}.{object_name}`"


def _stable_label_view_ddl(project: str, dataset: str, snapshot_table: str) -> str:
    target = _qualified(project, dataset, "entity_labels_v1")
    snapshot = _qualified(project, dataset, snapshot_table)
    return f"""CREATE OR REPLACE VIEW {target} AS
SELECT
  address,
  chain_id,
  primary_label,
  owner,
  category,
  concept_class,
  address_role,
  aliases,
  confidence,
  verified_date,
  sources,
  dictionary_sha256
FROM {snapshot}"""


def _bounds_guard() -> str:
    return """CROSS JOIN (
  SELECT IF(
    start_date IS NOT NULL
      AND end_date IS NOT NULL
      AND start_date < end_date
      AND DATE_DIFF(end_date, start_date, DAY) <= 31,
    TRUE,
    ERROR('Date bounds must form a non-empty half-open window of at most 31 days')
  ) AS bounds_valid
) AS bounds"""


def _token_dimension_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "token_dimension")
    return f"""CREATE OR REPLACE VIEW {target} AS
SELECT
  LOWER(tok.address) AS address,
  tok.symbol AS symbol,
  tok.name AS name,
  SAFE_CAST(tok.decimals AS INT64) AS decimals
FROM `bigquery-public-data.crypto_ethereum.amended_tokens` AS tok"""


def _transaction_facts_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "transaction_facts")
    return f"""CREATE OR REPLACE TABLE FUNCTION {target}(start_date DATE, end_date DATE) AS (
SELECT
  LOWER(t.hash) AS transaction_hash,
  t.transaction_index AS transaction_index,
  t.block_timestamp AS block_timestamp,
  t.block_number AS block_number,
  LOWER(t.block_hash) AS block_hash,
  LOWER(t.from_address) AS from_address,
  LOWER(t.to_address) AS to_address,
  t.value AS value_wei,
  t.gas AS gas_limit,
  t.gas_price AS gas_price_wei,
  t.receipt_gas_used AS receipt_gas_used,
  t.receipt_status AS receipt_status,
  t.receipt_status = 1 AS is_success,
  t.input AS input,
  LOWER(t.receipt_contract_address) AS receipt_contract_address,
  t.transaction_type AS transaction_type
FROM `bigquery-public-data.crypto_ethereum.transactions` AS t
{_bounds_guard()}
WHERE bounds.bounds_valid
  AND t.block_timestamp >= TIMESTAMP(start_date)
  AND t.block_timestamp < TIMESTAMP(end_date)
)"""


def _block_facts_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "block_facts")
    return f"""CREATE OR REPLACE TABLE FUNCTION {target}(start_date DATE, end_date DATE) AS (
SELECT
  b.number AS block_number,
  LOWER(b.hash) AS block_hash,
  b.timestamp AS block_timestamp,
  LOWER(b.miner) AS beneficiary_address,
  b.gas_used AS gas_used,
  b.transaction_count AS transaction_count,
  b.base_fee_per_gas AS base_fee_per_gas_wei
FROM `bigquery-public-data.crypto_ethereum.blocks` AS b
{_bounds_guard()}
WHERE bounds.bounds_valid
  AND b.timestamp >= TIMESTAMP(start_date)
  AND b.timestamp < TIMESTAMP(end_date)
)"""


def _contract_dimension_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "contract_dimension")
    return f"""CREATE OR REPLACE TABLE FUNCTION {target}(end_date DATE) AS (
SELECT
  LOWER(c.address) AS address,
  c.is_erc20 AS is_erc20,
  c.is_erc721 AS is_erc721,
  c.block_timestamp AS created_at,
  c.block_number AS block_number,
  LOWER(c.block_hash) AS block_hash
FROM `bigquery-public-data.crypto_ethereum.contracts` AS c
CROSS JOIN (
  SELECT IF(
    end_date IS NOT NULL,
    TRUE,
    ERROR('end_date must not be NULL')
  ) AS bounds_valid
) AS bounds
WHERE bounds.bounds_valid
  AND c.block_timestamp < TIMESTAMP(end_date)
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY LOWER(c.address)
  ORDER BY c.block_timestamp DESC, c.block_number DESC, c.block_hash DESC
) = 1
)"""


def _token_transfer_facts_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "token_transfer_facts")
    contracts = _qualified(project, dataset, "contract_dimension")
    tokens = _qualified(project, dataset, "token_dimension")
    return f"""CREATE OR REPLACE TABLE FUNCTION {target}(start_date DATE, end_date DATE) AS (
SELECT
  LOWER(tt.transaction_hash) AS transaction_hash,
  tt.log_index AS log_index,
  tt.block_timestamp AS block_timestamp,
  tt.block_number AS block_number,
  LOWER(tt.block_hash) AS block_hash,
  LOWER(tt.token_address) AS token_address,
  LOWER(tt.from_address) AS from_address,
  LOWER(tt.to_address) AS to_address,
  tt.value AS value_raw,
  SAFE_CAST(tt.value AS BIGNUMERIC) AS value_bignumeric,
  tt.value IS NOT NULL
    AND SAFE_CAST(tt.value AS BIGNUMERIC) IS NOT NULL AS value_cast_valid,
  c.is_erc20 AS is_erc20,
  c.is_erc721 AS is_erc721,
  tok.symbol AS token_symbol,
  tok.name AS token_name,
  tok.decimals AS token_decimals,
  CASE
    WHEN c.is_erc20 IS TRUE
      AND COALESCE(c.is_erc721, FALSE) IS FALSE
      AND SAFE_CAST(tok.decimals AS INT64) BETWEEN 0 AND 38
    THEN SAFE_DIVIDE(
      SAFE_CAST(tt.value AS BIGNUMERIC),
      POW(BIGNUMERIC '10', SAFE_CAST(tok.decimals AS INT64))
    )
  END AS normalized_amount
FROM `bigquery-public-data.crypto_ethereum.token_transfers` AS tt
{_bounds_guard()}
LEFT JOIN {contracts}(end_date) AS c
  ON LOWER(tt.token_address) = c.address
LEFT JOIN {tokens} AS tok
  ON LOWER(tt.token_address) = tok.address
WHERE bounds.bounds_valid
  AND tt.block_timestamp >= TIMESTAMP(start_date)
  AND tt.block_timestamp < TIMESTAMP(end_date)
)"""


_TRANSACTION_FIELDS = (
    "transaction_hash",
    "transaction_index",
    "block_timestamp",
    "block_number",
    "block_hash",
    "from_address",
    "to_address",
    "value_wei",
    "gas_limit",
    "gas_price_wei",
    "receipt_gas_used",
    "receipt_status",
    "is_success",
    "input",
    "receipt_contract_address",
    "transaction_type",
)

_TRANSFER_FIELDS = (
    "transaction_hash",
    "log_index",
    "block_timestamp",
    "block_number",
    "block_hash",
    "token_address",
    "from_address",
    "to_address",
    "value_raw",
    "value_bignumeric",
    "value_cast_valid",
    "is_erc20",
    "is_erc721",
    "token_symbol",
    "token_name",
    "token_decimals",
    "normalized_amount",
)

_FLAT_LABEL_FIELDS = (
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "address_role",
    "confidence",
)


def _fact_projection(fields: tuple[str, ...]) -> str:
    return ",\n".join(f"  facts.{field} AS {field}" for field in fields)


def _label_projection(alias: str, prefix: str) -> str:
    return ",\n".join(f"  {alias}.{field} AS {prefix}_{field}" for field in _FLAT_LABEL_FIELDS)


def _labeled_transactions_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "labeled_transactions")
    facts = _qualified(project, dataset, "transaction_facts")
    labels = _qualified(project, dataset, "entity_labels_v1")
    return f"""CREATE OR REPLACE TABLE FUNCTION {target}(start_date DATE, end_date DATE) AS (
SELECT
{_fact_projection(_TRANSACTION_FIELDS)},
{_label_projection("from_label", "from")},
{_label_projection("to_label", "to")}
FROM {facts}(start_date, end_date) AS facts
LEFT JOIN {labels} AS from_label
  ON facts.from_address = from_label.address
LEFT JOIN {labels} AS to_label
  ON facts.to_address = to_label.address
)"""


def _labeled_token_transfers_ddl(project: str, dataset: str) -> str:
    target = _qualified(project, dataset, "labeled_token_transfers")
    facts = _qualified(project, dataset, "token_transfer_facts")
    labels = _qualified(project, dataset, "entity_labels_v1")
    return f"""CREATE OR REPLACE TABLE FUNCTION {target}(start_date DATE, end_date DATE) AS (
SELECT
{_fact_projection(_TRANSFER_FIELDS)},
{_label_projection("from_label", "from")},
{_label_projection("to_label", "to")},
{_label_projection("token_label", "token")}
FROM {facts}(start_date, end_date) AS facts
LEFT JOIN {labels} AS from_label
  ON facts.from_address = from_label.address
LEFT JOIN {labels} AS to_label
  ON facts.to_address = to_label.address
LEFT JOIN {labels} AS token_label
  ON facts.token_address = token_label.address
)"""


def render_label_layer_ddl(
    project: str, dataset: str, snapshot_table: str
) -> tuple[SqlObject, ...]:
    """Render managed objects in dependency-safe deployment order."""
    _validate_identifiers(project, dataset, snapshot_table)
    return (
        SqlObject(
            name="entity_labels_v1",
            kind="VIEW",
            dependencies=(snapshot_table,),
            ddl=_stable_label_view_ddl(project, dataset, snapshot_table),
        ),
        SqlObject(
            name="token_dimension",
            kind="VIEW",
            dependencies=("bigquery-public-data.crypto_ethereum.amended_tokens",),
            ddl=_token_dimension_ddl(project, dataset),
        ),
        SqlObject(
            name="transaction_facts",
            kind="TABLE FUNCTION",
            dependencies=("bigquery-public-data.crypto_ethereum.transactions",),
            ddl=_transaction_facts_ddl(project, dataset),
        ),
        SqlObject(
            name="block_facts",
            kind="TABLE FUNCTION",
            dependencies=("bigquery-public-data.crypto_ethereum.blocks",),
            ddl=_block_facts_ddl(project, dataset),
        ),
        SqlObject(
            name="contract_dimension",
            kind="TABLE FUNCTION",
            dependencies=("bigquery-public-data.crypto_ethereum.contracts",),
            ddl=_contract_dimension_ddl(project, dataset),
        ),
        SqlObject(
            name="token_transfer_facts",
            kind="TABLE FUNCTION",
            dependencies=("contract_dimension", "token_dimension"),
            ddl=_token_transfer_facts_ddl(project, dataset),
        ),
        SqlObject(
            name="labeled_transactions",
            kind="TABLE FUNCTION",
            dependencies=("transaction_facts", "entity_labels_v1"),
            ddl=_labeled_transactions_ddl(project, dataset),
        ),
        SqlObject(
            name="labeled_token_transfers",
            kind="TABLE FUNCTION",
            dependencies=("token_transfer_facts", "entity_labels_v1"),
            ddl=_labeled_token_transfers_ddl(project, dataset),
        ),
    )


def render_rollback_ddl(project: str, dataset: str, snapshot_table: str) -> str:
    """Render a non-destructive stable-view rollback to an accepted snapshot."""
    return _stable_label_view_ddl(project, dataset, snapshot_table)


def _required_string(entry: dict[str, Any], field: str, *, context: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LabelLayerError(f"{context} requires non-empty {field}")
    return value


def _iso_date(entry: dict[str, Any], field: str, *, context: str) -> str:
    value = _required_string(entry, field, context=context)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise LabelLayerError(f"{context} has invalid {field}: {value!r}") from exc
    return value


def _build_sources(entry: dict[str, Any], *, context: str) -> list[dict[str, str]]:
    raw_sources = entry.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise LabelLayerError(f"{context} requires at least one source")

    sources: list[dict[str, str]] = []
    for index, raw_source in enumerate(raw_sources):
        source_context = f"{context} source {index}"
        if not isinstance(raw_source, dict):
            raise LabelLayerError(f"{source_context} must be an object")
        revision = _required_string(raw_source, "revision", context=source_context)
        locator = _required_string(raw_source, "locator", context=source_context)
        try:
            validate_source_revision(revision)
            validate_source_locator(locator)
        except DictionaryValidationError as exc:
            raise LabelLayerError(f"{source_context}: {exc}") from exc
        sources.append(
            {
                "name": _required_string(raw_source, "name", context=source_context),
                "url": _required_string(raw_source, "url", context=source_context),
                "revision": revision,
                "locator": locator,
                "retrieved_date": _iso_date(raw_source, "retrieved_date", context=source_context),
                "note": _required_string(raw_source, "note", context=source_context),
            }
        )
    return sources


def _build_row(entry: object, *, digest: str, index: int) -> dict[str, Any]:
    context = f"Entity {index}"
    if not isinstance(entry, dict):
        raise LabelLayerError(f"{context} must be an object")

    try:
        address = normalize_address(entry.get("address"))
        address_lower = entry.get("address_lower")
        if address_lower != address:
            raise LabelLayerError(f"address_lower mismatch for {entry.get('address')!r}")
        chain_id = validate_chain_id(entry.get("chain_id"))
        role = validate_address_role(entry.get("address_role"))
        confidence = validate_confidence(entry.get("confidence"))
    except DictionaryValidationError as exc:
        raise LabelLayerError(f"{context}: {exc}") from exc

    raw_aliases = entry.get("aliases")
    if not isinstance(raw_aliases, list):
        raise LabelLayerError(f"{context} aliases must be a list")
    aliases: list[str] = []
    for alias in raw_aliases:
        try:
            normalized = normalize_alias(alias)
        except (DictionaryValidationError, AttributeError) as exc:
            raise LabelLayerError(f"{context} has invalid alias: {alias!r}") from exc
        if normalized != alias:
            raise LabelLayerError(f"{context} alias is not normalized: {alias!r}")
        aliases.append(alias)

    return {
        "address": address,
        "chain_id": chain_id,
        "primary_label": _required_string(entry, "primary_label", context=context),
        "owner": _required_string(entry, "owner", context=context),
        "category": _required_string(entry, "category", context=context),
        "concept_class": _required_string(entry, "concept_class", context=context),
        "address_role": role,
        "aliases": aliases,
        "confidence": confidence,
        "verified_date": _iso_date(entry, "verified_date", context=context),
        "sources": _build_sources(entry, context=context),
        "dictionary_sha256": digest,
    }


def build_label_snapshot(entities_path: Path = ENTITIES_PATH) -> LabelSnapshot:
    """Build a deterministic BigQuery label snapshot from an accepted artifact."""
    path = Path(entities_path)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise LabelLayerError(f"Unable to read entities JSON: {path}") from exc

    try:
        entities = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LabelLayerError(f"Invalid entities JSON: {path}") from exc
    if not isinstance(entities, list):
        raise LabelLayerError("entities JSON must contain a list")
    if not entities:
        raise LabelLayerError("entities JSON must contain at least one entity")

    if path.resolve() == ENTITIES_PATH.resolve():
        try:
            validate_artifacts()
        except (DictionaryValidationError, json.JSONDecodeError) as exc:
            raise LabelLayerError(f"Committed dictionary validation failed: {exc}") from exc

    digest = hashlib.sha256(payload).hexdigest()
    rows = tuple(
        _build_row(entry, digest=digest, index=index) for index, entry in enumerate(entities)
    )
    addresses = [row["address"] for row in rows]
    if len(set(addresses)) != len(addresses):
        duplicates = sorted(address for address, count in Counter(addresses).items() if count > 1)
        raise LabelLayerError(f"Duplicate address: {duplicates[0]}")

    observed_counts = Counter(row["address_role"] for row in rows)
    role_counts = {role: observed_counts.get(role, 0) for role in LABEL_ROLES}
    return LabelSnapshot(
        entities_path=path,
        digest=digest,
        table_name=f"{LABEL_SNAPSHOT_PREFIX}{digest[:12]}",
        entity_count=len(rows),
        role_counts=role_counts,
        rows=rows,
    )
