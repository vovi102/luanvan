from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).with_name("catalog") / "ethereum_analytics.json"
CATALOG_VERSION = "1.0.0"
GOOGLESQL_DIALECT = "google_standard_sql"
BIGQUERY_LOCATION = "US"
SOURCE_KINDS = {"partitioned_table", "logical_view", "managed_table"}
DEPLOYMENT_STATUSES = {"live", "deferred"}
BIGQUERY_TYPES = {
    "BIGNUMERIC",
    "BOOLEAN",
    "DATE",
    "INTEGER",
    "JSON",
    "NUMERIC",
    "RECORD",
    "STRING",
    "TIMESTAMP",
}
BIGQUERY_MODES = {"NULLABLE", "REPEATED", "REQUIRED"}
RELATION_KINDS = {
    "parameterized_fact",
    "bounded_dimension",
    "parameterless_dimension",
}
JOIN_KINDS = {"equi_join", "address_lookup"}
JOIN_TYPES = {"inner", "left"}
CARDINALITIES = {"many_to_one", "one_to_one"}
ADDRESS_ROLES = {"operational", "treasury", "token"}
SEMANTIC_STATUSES = {"supported", "semantic_adjustment", "unsupported"}
COMPETENCY_STATUSES = {"supported", "coverage_gap", "unsupported"}


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


@dataclass(frozen=True)
class LiveField:
    """Normalized BigQuery field metadata used by the drift boundary."""

    name: str
    field_type: str
    mode: str
    fields: tuple[LiveField, ...] = ()


@dataclass(frozen=True)
class LiveSchemaSummary:
    """Counts emitted after successful read-only live schema validation."""

    checked_source_count: int
    deferred_source_count: int
    checked_field_count: int


def load_catalog(path: Path = CATALOG_PATH, *, snapshot: bytes | None = None) -> dict[str, object]:
    """Load a JSON schema catalog and fail closed on I/O or parse errors."""
    if snapshot is None:
        try:
            snapshot = path.read_bytes()
        except OSError as exc:
            raise SchemaCatalogError(f"Unable to read schema catalog {path}: {exc}") from exc

    try:
        catalog = json.loads(snapshot)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaCatalogError(f"{label} must be an object")
    return value


def _as_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaCatalogError(f"{label} must be an array")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaCatalogError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    items = _as_list(value, label)
    if not allow_empty and not items:
        raise SchemaCatalogError(f"{label} must not be empty")
    if any(not isinstance(item, str) or not item for item in items):
        raise SchemaCatalogError(f"{label} must contain non-empty strings")
    if len(items) != len(set(items)):
        raise SchemaCatalogError(f"{label} must not contain duplicates")
    return items


def validate_date_window(start_date: date, end_date: date, *, max_days: int = 31) -> None:
    """Validate a non-empty half-open date interval within the configured cap."""

    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise SchemaCatalogError("start_date and end_date must be date instances")
    if start_date >= end_date:
        raise SchemaCatalogError("start_date must be before end_date")
    if not isinstance(max_days, int) or isinstance(max_days, bool) or max_days <= 0:
        raise SchemaCatalogError("max_days must be a positive integer")
    if (end_date - start_date).days > max_days:
        raise SchemaCatalogError(f"Date window must not exceed {max_days} days")


def _validate_field_definition(field: str, value: Any, owner: str) -> None:
    definition = _as_mapping(value, f"{owner}.{field}")
    field_type = definition.get("type")
    if field_type not in BIGQUERY_TYPES:
        raise SchemaCatalogError(f"Unknown BigQuery type for {owner}.{field}: {field_type!r}")
    mode = definition.get("mode")
    if mode not in BIGQUERY_MODES:
        raise SchemaCatalogError(f"Unknown BigQuery mode for {owner}.{field}: {mode!r}")
    if field_type == "RECORD":
        nested = _as_mapping(definition.get("fields"), f"{owner}.{field}.fields")
        if not nested:
            raise SchemaCatalogError(f"{owner}.{field}.fields must not be empty")
        for nested_name, nested_definition in nested.items():
            _validate_field_definition(nested_name, nested_definition, f"{owner}.{field}.fields")


def _validate_sources(physical_sources: Mapping[str, Any]) -> None:
    for source_id, raw_source in physical_sources.items():
        source = _as_mapping(raw_source, f"physical_sources.{source_id}")
        if source.get("object_kind") not in SOURCE_KINDS:
            raise SchemaCatalogError(
                f"Invalid object_kind for physical_sources.{source_id}: "
                f"{source.get('object_kind')!r}"
            )
        if source.get("deployment_status") not in DEPLOYMENT_STATUSES:
            raise SchemaCatalogError(f"Invalid deployment_status for physical_sources.{source_id}")
        if source.get("location") != BIGQUERY_LOCATION:
            raise SchemaCatalogError(f"Invalid location for physical_sources.{source_id}")
        object_field = "object" if source.get("deployment_status") == "live" else "object_template"
        _require_string(source.get(object_field), f"physical_sources.{source_id}.{object_field}")

        fields = _as_mapping(source.get("fields"), f"physical_sources.{source_id}.fields")
        if not fields:
            raise SchemaCatalogError(f"physical_sources.{source_id}.fields must not be empty")
        for field_name, definition in fields.items():
            _validate_field_definition(
                field_name, definition, f"physical_sources.{source_id}.fields"
            )

        key_fields = _require_string_list(
            source.get("key_fields"), f"physical_sources.{source_id}.key_fields"
        )
        missing_keys = sorted(set(key_fields) - set(fields))
        if missing_keys:
            raise SchemaCatalogError(
                f"physical_sources.{source_id}.key_fields reference unknown fields: {missing_keys}"
            )

        if source.get("object_kind") == "partitioned_table":
            partition_field = source.get("partition_field")
            if partition_field not in fields:
                raise SchemaCatalogError(
                    f"physical_sources.{source_id}.partition_field references "
                    f"unknown field: {partition_field!r}"
                )
            if fields[partition_field].get("type") not in {"DATE", "TIMESTAMP"}:
                raise SchemaCatalogError(
                    f"physical_sources.{source_id}.partition_field must be DATE or TIMESTAMP"
                )

    labels = _as_mapping(
        physical_sources.get("entity_labels_v1"), "physical_sources.entity_labels_v1"
    )
    label_fields = _as_mapping(labels.get("fields"), "physical_sources.entity_labels_v1.fields")
    required_labels = {
        "address",
        "chain_id",
        "primary_label",
        "owner",
        "category",
        "concept_class",
        "address_role",
        "aliases",
        "confidence",
        "verified_date",
        "sources",
        "dictionary_sha256",
    }
    missing_labels = sorted(required_labels - set(label_fields))
    if missing_labels:
        raise SchemaCatalogError(
            "physical_sources.entity_labels_v1 fields missing required provenance/role "
            f"fields: {missing_labels}"
        )


def _validate_relation_field(
    relation_id: str,
    field_name: str,
    raw_definition: Any,
    relation_sources: set[str],
    physical_sources: Mapping[str, Any],
) -> None:
    owner = f"analytical_relations.{relation_id}.fields"
    _validate_field_definition(field_name, raw_definition, owner)
    definition = _as_mapping(raw_definition, f"{owner}.{field_name}")
    lineage = _as_list(definition.get("lineage"), f"{owner}.{field_name}.lineage")
    if not lineage:
        raise SchemaCatalogError(f"{owner}.{field_name}.lineage must not be empty")
    for index, raw_item in enumerate(lineage):
        item = _as_mapping(raw_item, f"{owner}.{field_name}.lineage[{index}]")
        source_id = item.get("source")
        source_field = item.get("field")
        if source_id not in relation_sources:
            raise SchemaCatalogError(
                f"{owner}.{field_name} references unknown source {source_id!r}"
            )
        source = _as_mapping(physical_sources[source_id], f"physical_sources.{source_id}")
        source_fields = _as_mapping(source.get("fields"), f"physical_sources.{source_id}.fields")
        if source_field not in source_fields:
            raise SchemaCatalogError(
                f"{owner}.{field_name} references unknown lineage field {source_id}.{source_field}"
            )
    if "expression" in definition:
        _require_string(definition["expression"], f"{owner}.{field_name}.expression")


def _validate_relations(
    analytical_relations: Mapping[str, Any], physical_sources: Mapping[str, Any]
) -> None:
    for relation_id, raw_relation in analytical_relations.items():
        relation = _as_mapping(raw_relation, f"analytical_relations.{relation_id}")
        kind = relation.get("kind")
        if kind not in RELATION_KINDS:
            raise SchemaCatalogError(
                f"Invalid relation kind for analytical_relations.{relation_id}: {kind!r}"
            )
        relation_sources = set(
            _require_string_list(
                relation.get("sources"), f"analytical_relations.{relation_id}.sources"
            )
        )
        unknown_sources = sorted(relation_sources - set(physical_sources))
        if unknown_sources:
            raise SchemaCatalogError(
                f"analytical_relations.{relation_id} references unknown source: {unknown_sources}"
            )

        fields = _as_mapping(relation.get("fields"), f"analytical_relations.{relation_id}.fields")
        if not fields:
            raise SchemaCatalogError(f"analytical_relations.{relation_id}.fields is empty")
        for field_name, definition in fields.items():
            _validate_relation_field(
                relation_id,
                field_name,
                definition,
                relation_sources,
                physical_sources,
            )

        primary_key = _require_string_list(
            relation.get("primary_key"), f"analytical_relations.{relation_id}.primary_key"
        )
        missing_key_fields = sorted(set(primary_key) - set(fields))
        if missing_key_fields:
            raise SchemaCatalogError(
                f"analytical_relations.{relation_id}.primary_key references unknown fields: "
                f"{missing_key_fields}"
            )

        parameters = _as_mapping(
            relation.get("parameters", {}),
            f"analytical_relations.{relation_id}.parameters",
        )
        if any(value != "DATE" for value in parameters.values()):
            raise SchemaCatalogError(f"analytical_relations.{relation_id}.parameters must be DATE")
        if kind == "parameterized_fact" and set(parameters) != {
            "start_date",
            "end_date",
        }:
            raise SchemaCatalogError(
                f"analytical_relations.{relation_id} requires start_date/end_date"
            )
        if kind == "bounded_dimension" and set(parameters) != {"end_date"}:
            raise SchemaCatalogError(f"analytical_relations.{relation_id} requires end_date")
        if kind == "parameterless_dimension" and parameters:
            raise SchemaCatalogError(f"analytical_relations.{relation_id} must be parameterless")

        partitioned_sources = {
            source_id
            for source_id in relation_sources
            if physical_sources[source_id].get("object_kind") == "partitioned_table"
        }
        filters = _as_mapping(
            relation.get("source_time_filters", {}),
            f"analytical_relations.{relation_id}.source_time_filters",
        )
        if set(filters) != partitioned_sources:
            raise SchemaCatalogError(
                f"analytical_relations.{relation_id}.source_time_filters must cover "
                f"partitioned sources {sorted(partitioned_sources)}"
            )
        for source_id, raw_filter in filters.items():
            time_filter = _as_mapping(
                raw_filter,
                f"analytical_relations.{relation_id}.source_time_filters.{source_id}",
            )
            source = physical_sources[source_id]
            if time_filter.get("field") != source.get("partition_field"):
                raise SchemaCatalogError(
                    f"analytical_relations.{relation_id}.source_time_filters.{source_id} "
                    "must use the partition field"
                )
            interval = time_filter.get("interval")
            if interval not in {"half_open", "before_end"}:
                raise SchemaCatalogError(
                    f"Invalid time-filter interval for {relation_id}.{source_id}"
                )
            required_parameters = (
                {"start_date", "end_date"} if interval == "half_open" else {"end_date"}
            )
            if not required_parameters <= set(parameters):
                raise SchemaCatalogError(
                    f"Time filter for {relation_id}.{source_id} lacks required parameters"
                )
            _require_string(
                time_filter.get("predicate"),
                f"analytical_relations.{relation_id}.source_time_filters.{source_id}.predicate",
            )


def _relation_fields(
    analytical_relations: Mapping[str, Any], relation_id: str
) -> Mapping[str, Any]:
    relation = _as_mapping(
        analytical_relations.get(relation_id), f"analytical_relations.{relation_id}"
    )
    return _as_mapping(relation.get("fields"), f"analytical_relations.{relation_id}.fields")


def _validate_join_field(
    analytical_relations: Mapping[str, Any], relation_id: Any, field: Any
) -> None:
    if relation_id not in analytical_relations:
        raise SchemaCatalogError(f"Join references unknown relation {relation_id!r}")
    if field not in _relation_fields(analytical_relations, relation_id):
        raise SchemaCatalogError(f"Unknown join field: {relation_id}.{field}")


def _validate_joins(
    join_paths: Mapping[str, Any],
    analytical_relations: Mapping[str, Any],
    role_policies: Mapping[str, Any],
) -> None:
    for join_id, raw_join in join_paths.items():
        join = _as_mapping(raw_join, f"join_paths.{join_id}")
        kind = join.get("kind")
        if kind not in JOIN_KINDS:
            raise SchemaCatalogError(f"Invalid join kind for join_paths.{join_id}")
        if join.get("join_type") not in JOIN_TYPES:
            raise SchemaCatalogError(f"Invalid join_type for join_paths.{join_id}")
        if join.get("cardinality") not in CARDINALITIES:
            raise SchemaCatalogError(f"Invalid cardinality for join_paths.{join_id}")

        relevant_relations: set[str]
        if kind == "equi_join":
            left_relation = join.get("left_relation")
            right_relation = join.get("right_relation")
            if (
                left_relation not in analytical_relations
                or right_relation not in analytical_relations
            ):
                raise SchemaCatalogError(f"join_paths.{join_id} references unknown relation")
            conditions = _as_list(join.get("conditions"), f"join_paths.{join_id}.conditions")
            if not conditions:
                raise SchemaCatalogError(f"join_paths.{join_id}.conditions must not be empty")
            for raw_condition in conditions:
                condition = _as_mapping(raw_condition, f"join_paths.{join_id}.condition")
                _validate_join_field(
                    analytical_relations, left_relation, condition.get("left_field")
                )
                _validate_join_field(
                    analytical_relations, right_relation, condition.get("right_field")
                )
            relevant_relations = {left_relation, right_relation}
        else:
            left_relations = _as_mapping(
                join.get("left_relations"), f"join_paths.{join_id}.left_relations"
            )
            if not left_relations:
                raise SchemaCatalogError(f"join_paths.{join_id}.left_relations must not be empty")
            for relation_id, raw_fields in left_relations.items():
                for field in _require_string_list(
                    raw_fields, f"join_paths.{join_id}.left_relations.{relation_id}"
                ):
                    _validate_join_field(analytical_relations, relation_id, field)
            right_relation = join.get("right_relation")
            _validate_join_field(analytical_relations, right_relation, join.get("right_field"))
            relevant_relations = {*left_relations, right_relation}

        date_bounded = {
            relation_id
            for relation_id in relevant_relations
            if analytical_relations[relation_id].get("kind")
            in {"parameterized_fact", "bounded_dimension"}
        }
        date_covered = set(
            _require_string_list(
                join.get("date_covered_relations"),
                f"join_paths.{join_id}.date_covered_relations",
                allow_empty=True,
            )
        )
        if not date_bounded <= date_covered or not date_covered <= relevant_relations:
            raise SchemaCatalogError(
                f"join_paths.{join_id}.date_covered_relations must cover {sorted(date_bounded)}"
            )

        roles = _require_string_list(
            join.get("allowed_right_roles", []),
            f"join_paths.{join_id}.allowed_right_roles",
            allow_empty=True,
        )
        unknown_roles = sorted(set(roles) - set(role_policies))
        if unknown_roles:
            raise SchemaCatalogError(
                f"join_paths.{join_id} references unknown role: {unknown_roles}"
            )


def _validate_role_policies(role_policies: Mapping[str, Any]) -> None:
    if set(role_policies) != ADDRESS_ROLES:
        raise SchemaCatalogError(
            f"role_policies must define exactly these roles: {sorted(ADDRESS_ROLES)}"
        )
    for role, raw_policy in role_policies.items():
        policy = _as_mapping(raw_policy, f"role_policies.{role}")
        _require_string(policy.get("description"), f"role_policies.{role}.description")
        _require_string_list(policy.get("allowed_uses"), f"role_policies.{role}.allowed_uses")


def _validate_semantic_mappings(
    semantic_mappings: Sequence[Any], analytical_relations: Mapping[str, Any]
) -> None:
    seen: set[str] = set()
    for index, raw_mapping in enumerate(semantic_mappings):
        mapping = _as_mapping(raw_mapping, f"semantic_mappings[{index}]")
        semantic_id = _require_string(
            mapping.get("semantic_id"), f"semantic_mappings[{index}].semantic_id"
        )
        if semantic_id in seen:
            raise SchemaCatalogError(f"Duplicate semantic mapping: {semantic_id}")
        seen.add(semantic_id)
        status = mapping.get("status")
        if status not in SEMANTIC_STATUSES:
            raise SchemaCatalogError(
                f"Invalid semantic mapping status for {semantic_id}: {status!r}"
            )
        targets = _as_list(mapping.get("targets"), f"semantic_mappings[{index}].targets")
        if status == "unsupported":
            _require_string(mapping.get("reason"), f"semantic_mappings[{index}].reason")
            if targets:
                raise SchemaCatalogError(
                    f"Unsupported semantic mapping {semantic_id} must not have targets"
                )
        elif not targets:
            raise SchemaCatalogError(f"Semantic mapping {semantic_id} requires targets")
        for raw_target in targets:
            target = _as_mapping(raw_target, f"semantic target for {semantic_id}")
            relation_id = target.get("relation")
            if relation_id not in analytical_relations:
                raise SchemaCatalogError(
                    f"Unknown semantic target relation for {semantic_id}: {relation_id!r}"
                )
            if "field" in target and target["field"] not in _relation_fields(
                analytical_relations, relation_id
            ):
                raise SchemaCatalogError(
                    f"Unknown semantic target field for {semantic_id}: "
                    f"{relation_id}.{target['field']}"
                )


def _validate_competency_questions(
    competency_questions: Sequence[Any],
    analytical_relations: Mapping[str, Any],
    join_paths: Mapping[str, Any],
    semantic_mappings: Sequence[Any],
    role_policies: Mapping[str, Any],
) -> None:
    expected_ids = {f"CQ{index:02d}" for index in range(1, 31)}
    semantic_ids = {mapping["semantic_id"] for mapping in semantic_mappings}
    seen: set[str] = set()
    questions: dict[str, Mapping[str, Any]] = {}

    for index, raw_question in enumerate(competency_questions):
        question = _as_mapping(raw_question, f"competency_questions[{index}]")
        question_id = _require_string(question.get("id"), f"competency_questions[{index}].id")
        if question_id in seen:
            raise SchemaCatalogError(f"Duplicate competency question: {question_id}")
        seen.add(question_id)
        questions[question_id] = question

        status = question.get("status")
        if status not in COMPETENCY_STATUSES:
            raise SchemaCatalogError(f"Invalid competency status for {question_id}: {status!r}")
        if status != "supported":
            _require_string(question.get("reason"), f"competency_questions[{index}].reason")

        relations = _require_string_list(
            question.get("relations"),
            f"competency_questions[{index}].relations",
            allow_empty=status == "unsupported",
        )
        joins = _require_string_list(
            question.get("join_paths"),
            f"competency_questions[{index}].join_paths",
            allow_empty=True,
        )
        semantics = _require_string_list(
            question.get("semantic_ids"),
            f"competency_questions[{index}].semantic_ids",
        )
        if set(relations) - set(analytical_relations):
            raise SchemaCatalogError(f"Unknown competency reference in {question_id}.relations")
        if set(joins) - set(join_paths):
            raise SchemaCatalogError(f"Unknown competency reference in {question_id}.join_paths")
        if set(semantics) - semantic_ids:
            raise SchemaCatalogError(f"Unknown competency reference in {question_id}.semantic_ids")

        role_requirements = _as_mapping(
            question.get("role_requirements", {}),
            f"competency_questions[{index}].role_requirements",
        )
        unknown_roles = sorted(set(role_requirements.values()) - set(role_policies))
        if unknown_roles:
            raise SchemaCatalogError(
                f"Unknown competency role reference in {question_id}: {unknown_roles}"
            )

        if question.get("semantic_adjustment", False) is True:
            _require_string(question.get("notes"), f"competency_questions[{index}].notes")

    if seen != expected_ids:
        missing = sorted(expected_ids - seen)
        unexpected = sorted(seen - expected_ids)
        raise SchemaCatalogError(
            f"competency_questions must contain exactly CQ01-CQ30; "
            f"missing={missing}, unexpected={unexpected}"
        )

    cq24 = questions["CQ24"]
    if cq24.get("status") != "unsupported":
        raise SchemaCatalogError("CQ24 must remain unsupported without meta-transaction decoding")
    cq17 = questions["CQ17"]
    if cq17.get("semantic_adjustment") is not True:
        raise SchemaCatalogError("CQ17 must document the beneficiary semantic adjustment")


def _normalize_live_field(raw_field: Any) -> LiveField:
    try:
        name = raw_field.name
        field_type = raw_field.field_type
        mode = raw_field.mode
        nested = raw_field.fields
    except AttributeError as exc:
        raise SchemaCatalogError("Invalid BigQuery live field metadata") from exc
    _require_string(name, "live field name")
    _require_string(field_type, f"live field {name} type")
    _require_string(mode, f"live field {name} mode")
    return LiveField(
        name=name,
        field_type=field_type,
        mode=mode,
        fields=tuple(_normalize_live_field(field) for field in nested or ()),
    )


def normalize_live_schema(table: object) -> dict[str, LiveField]:
    """Normalize a BigQuery table/view schema without coupling tests to its SDK."""

    try:
        raw_schema = table.schema
    except AttributeError as exc:
        raise SchemaCatalogError("BigQuery table metadata has no schema") from exc
    normalized: dict[str, LiveField] = {}
    for raw_field in raw_schema:
        field = _normalize_live_field(raw_field)
        if field.name in normalized:
            raise SchemaCatalogError(f"Duplicate live schema field: {field.name}")
        normalized[field.name] = field
    return normalized


def _validate_live_field(
    source_id: str,
    path: str,
    expected: Mapping[str, Any],
    actual: LiveField,
) -> int:
    if actual.field_type != expected.get("type"):
        raise SchemaCatalogError(
            f"Live schema type mismatch for {source_id}.{path}: "
            f"expected {expected.get('type')}, received {actual.field_type}"
        )
    if actual.mode != expected.get("mode"):
        raise SchemaCatalogError(
            f"Live schema mode mismatch for {source_id}.{path}: "
            f"expected {expected.get('mode')}, received {actual.mode}"
        )
    checked = 1
    expected_nested = expected.get("fields", {})
    actual_nested = {field.name: field for field in actual.fields}
    for nested_name, raw_nested_definition in expected_nested.items():
        if nested_name not in actual_nested:
            raise SchemaCatalogError(
                f"Live schema missing required field: {source_id}.{path}.{nested_name}"
            )
        nested_definition = _as_mapping(
            raw_nested_definition, f"expected field {source_id}.{path}.{nested_name}"
        )
        checked += _validate_live_field(
            source_id,
            f"{path}.{nested_name}",
            nested_definition,
            actual_nested[nested_name],
        )
    return checked


def validate_live_schemas(
    catalog: Mapping[str, Any], schemas: Mapping[str, Mapping[str, LiveField]]
) -> LiveSchemaSummary:
    """Compare required catalog fields with read-only BigQuery metadata."""

    validate_catalog(catalog)
    physical_sources = _as_mapping(catalog["physical_sources"], "physical_sources")
    checked_sources = 0
    deferred_sources = 0
    checked_fields = 0

    for source_id, raw_source in physical_sources.items():
        source = _as_mapping(raw_source, f"physical_sources.{source_id}")
        if source.get("deployment_status") == "deferred":
            deferred_sources += 1
            continue
        if source_id not in schemas:
            raise SchemaCatalogError(f"Missing live schema for source: {source_id}")
        actual_fields = schemas[source_id]
        expected_fields = _as_mapping(source.get("fields"), f"physical_sources.{source_id}.fields")
        for field_name, raw_definition in expected_fields.items():
            if field_name not in actual_fields:
                raise SchemaCatalogError(
                    f"Live schema missing required field: {source_id}.{field_name}"
                )
            definition = _as_mapping(
                raw_definition, f"physical_sources.{source_id}.fields.{field_name}"
            )
            checked_fields += _validate_live_field(
                source_id, field_name, definition, actual_fields[field_name]
            )
        checked_sources += 1

    return LiveSchemaSummary(
        checked_source_count=checked_sources,
        deferred_source_count=deferred_sources,
        checked_field_count=checked_fields,
    )


def validate_catalog(catalog: Mapping[str, Any]) -> CatalogSummary:
    """Validate the catalog's global contract and return stable counts."""

    if catalog.get("catalog_version") != CATALOG_VERSION:
        raise SchemaCatalogError(f"Unsupported catalog_version: {catalog.get('catalog_version')!r}")
    if catalog.get("dialect") != GOOGLESQL_DIALECT:
        raise SchemaCatalogError(f"Unsupported dialect: {catalog.get('dialect')!r}")
    if catalog.get("location") != BIGQUERY_LOCATION:
        raise SchemaCatalogError(f"Unsupported location: {catalog.get('location')!r}")

    evaluation_window = _require_mapping(catalog, "evaluation_window")
    if evaluation_window.get("interval") != "half_open":
        raise SchemaCatalogError("evaluation_window.interval must be half_open")
    max_days = evaluation_window.get("max_days")
    if not isinstance(max_days, int) or isinstance(max_days, bool) or max_days <= 0:
        raise SchemaCatalogError("evaluation_window.max_days must be a positive integer")
    try:
        evaluation_start = date.fromisoformat(evaluation_window["start_date"])
        evaluation_end = date.fromisoformat(evaluation_window["end_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaCatalogError("evaluation_window dates must use ISO YYYY-MM-DD") from exc
    validate_date_window(evaluation_start, evaluation_end, max_days=max_days)

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
    role_policies = _require_mapping(catalog, "role_policies")
    semantic_mappings = _require_sequence(catalog, "semantic_mappings")
    competency_questions = _require_sequence(catalog, "competency_questions")

    _validate_sources(physical_sources)
    _validate_role_policies(role_policies)
    _validate_relations(analytical_relations, physical_sources)
    _validate_joins(join_paths, analytical_relations, role_policies)
    _validate_semantic_mappings(semantic_mappings, analytical_relations)
    _validate_competency_questions(
        competency_questions,
        analytical_relations,
        join_paths,
        semantic_mappings,
        role_policies,
    )

    return CatalogSummary(
        source_count=len(physical_sources),
        relation_count=len(analytical_relations),
        join_count=len(join_paths),
        semantic_mapping_count=len(semantic_mappings),
        competency_question_count=len(competency_questions),
    )
