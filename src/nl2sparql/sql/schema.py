from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).with_name("catalog") / "ethereum_analytics.json"
CATALOG_VERSION = "1.0.0"
GOOGLESQL_DIALECT = "google_standard_sql"
BIGQUERY_LOCATION = "US"


class SchemaCatalogError(ValueError):
    """Raised when an analytical schema catalog violates its contract."""


@dataclass(frozen=True)
class CatalogSummary:
    """Stable counts emitted after successful catalog validation."""

    source_count: int
    relation_count: int
    join_count: int
    semantic_mapping_count: int
    competency_question_count: int


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, object]:
    """Load a JSON schema catalog and fail closed on I/O or parse errors."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaCatalogError(f"Unable to read schema catalog {path}: {exc}") from exc

    try:
        catalog = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaCatalogError(f"Invalid schema catalog JSON in {path}: {exc}") from exc

    if not isinstance(catalog, dict):
        raise SchemaCatalogError("Schema catalog top level must be an object")
    return catalog


def _require_mapping(catalog: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = catalog.get(field)
    if not isinstance(value, Mapping):
        raise SchemaCatalogError(f"Catalog field {field!r} must be an object")
    return value


def _require_sequence(catalog: Mapping[str, Any], field: str) -> Sequence[Any]:
    value = catalog.get(field)
    if not isinstance(value, list):
        raise SchemaCatalogError(f"Catalog field {field!r} must be an array")
    return value


def validate_catalog(catalog: Mapping[str, Any]) -> CatalogSummary:
    """Validate the catalog's global contract and return stable counts."""

    if catalog.get("catalog_version") != CATALOG_VERSION:
        raise SchemaCatalogError(f"Unsupported catalog_version: {catalog.get('catalog_version')!r}")
    if catalog.get("dialect") != GOOGLESQL_DIALECT:
        raise SchemaCatalogError(f"Unsupported dialect: {catalog.get('dialect')!r}")
    if catalog.get("location") != BIGQUERY_LOCATION:
        raise SchemaCatalogError(f"Unsupported location: {catalog.get('location')!r}")

    _require_mapping(catalog, "evaluation_window")
    cost_policy = _require_mapping(catalog, "cost_policy")
    maximum_bytes_billed = cost_policy.get("maximum_bytes_billed")
    if (
        not isinstance(maximum_bytes_billed, int)
        or isinstance(maximum_bytes_billed, bool)
        or maximum_bytes_billed <= 0
    ):
        raise SchemaCatalogError("maximum_bytes_billed must be a positive integer")
    if cost_policy.get("dry_run_required") is not True:
        raise SchemaCatalogError("dry_run_required must be true")

    physical_sources = _require_mapping(catalog, "physical_sources")
    analytical_relations = _require_mapping(catalog, "analytical_relations")
    join_paths = _require_mapping(catalog, "join_paths")
    _require_mapping(catalog, "role_policies")
    semantic_mappings = _require_sequence(catalog, "semantic_mappings")
    competency_questions = _require_sequence(catalog, "competency_questions")

    return CatalogSummary(
        source_count=len(physical_sources),
        relation_count=len(analytical_relations),
        join_count=len(join_paths),
        semantic_mapping_count=len(semantic_mappings),
        competency_question_count=len(competency_questions),
    )
