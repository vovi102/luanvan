"""Compile the accepted analytical catalog into deterministic prompt context."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nl2sparql.models.b12.contracts import CatalogSummary, SmallLLMError
from nl2sparql.sql.schema import SchemaCatalogError, load_catalog, validate_catalog


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SmallLLMError(f"catalog {label} must be an object")
    return value


def _relation_lines(relation_id: str, raw_relation: object) -> list[str]:
    relation = _mapping(raw_relation, f"relation {relation_id}")
    parameters = _mapping(relation.get("parameters", {}), f"relation {relation_id} parameters")
    parameter_text = ", ".join(
        f"{name} {field_type}" for name, field_type in sorted(parameters.items())
    )
    lines = [f"Relation {relation_id} ({relation['kind']}; parameters: {parameter_text or 'none'})"]
    fields = _mapping(relation.get("fields"), f"relation {relation_id} fields")
    for field_name, raw_field in sorted(fields.items()):
        field = _mapping(raw_field, f"field {relation_id}.{field_name}")
        lines.append(f"  - {field_name}: {field['type']} {field['mode']}")
    return lines


def _join_lines(join_id: str, raw_join: object) -> list[str]:
    join = _mapping(raw_join, f"join {join_id}")
    if join["kind"] == "equi_join":
        left = str(join["left_relation"])
        right = str(join["right_relation"])
        conditions = join["conditions"]
        pairs = ", ".join(
            f"{left}.{condition['left_field']} = {right}.{condition['right_field']}"
            for condition in conditions
        )
    else:
        right = str(join["right_relation"])
        left_parts = [
            f"{relation}.{field}"
            for relation, fields in sorted(join["left_relations"].items())
            for field in fields
        ]
        pairs = f"{', '.join(left_parts)} = {right}.{join['right_field']}"
    return [f"Join {join_id} ({join['join_type']}, {join['cardinality']}): {pairs}"]


def compile_catalog_summary(path: Path, *, max_chars: int = 12_000) -> CatalogSummary:
    """Validate and summarize exactly the catalog bytes being fingerprinted."""
    if not isinstance(path, Path):
        raise SmallLLMError("catalog path must be a pathlib.Path")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise SmallLLMError("max_chars must be a positive integer")
    try:
        snapshot = path.read_bytes()
    except OSError as exc:
        raise SmallLLMError(f"unable to read catalog {path}: {exc}") from exc
    try:
        catalog = load_catalog(path, snapshot=snapshot)
        validate_catalog(catalog)
    except SchemaCatalogError as exc:
        raise SmallLLMError(f"catalog is invalid: {exc}") from exc

    evaluation = _mapping(catalog["evaluation_window"], "evaluation_window")
    lines = [
        "GOOGLESQL ANALYTICAL CATALOG",
        f"Dialect: {catalog['dialect']}",
        (
            "Evaluation window: half-open [start_date, end_date), "
            f"maximum {evaluation['max_days']} days"
        ),
        "",
        "MANAGED RELATIONS",
    ]
    relations = _mapping(catalog["analytical_relations"], "analytical_relations")
    for relation_id, relation in sorted(relations.items()):
        lines.extend(_relation_lines(relation_id, relation))

    lines.extend(["", "APPROVED JOINS"])
    joins = _mapping(catalog["join_paths"], "join_paths")
    for join_id, join in sorted(joins.items()):
        lines.extend(_join_lines(join_id, join))

    lines.extend(
        [
            "",
            "QUERY RULES",
            "- Produce exactly one read-only GoogleSQL query.",
            "- Use explicit projections; SELECT * is forbidden.",
            "- Use managed relations only and never physical source tables directly.",
            "- Supply every required date parameter and keep the half-open interval bounded.",
            "- Do not invent entity values, columns, relations, joins, or defaults.",
        ]
    )
    text = "\n".join(lines).strip() + "\n"
    if len(text) > max_chars:
        raise SmallLLMError(
            f"catalog summary exceeds max_chars ({len(text)} > {max_chars}); refusing truncation"
        )
    return CatalogSummary(
        text=text,
        catalog_sha256=hashlib.sha256(snapshot).hexdigest(),
        summary_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
