from __future__ import annotations

import hashlib
import json
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
