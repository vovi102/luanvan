"""Typed, digest-only BigQuery result comparison semantics."""

from __future__ import annotations

import base64
import hashlib
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation

from nl2sparql.evaluation.artifacts import canonical_json
from nl2sparql.evaluation.contracts import (
    AnswerScores,
    EvaluationError,
    QueryResultEvidence,
    ResultField,
)

_NUMERIC_TYPES = {"INT64", "INTEGER", "NUMERIC", "BIGNUMERIC", "FLOAT64", "FLOAT"}
_STRUCT_TYPES = {"STRUCT", "RECORD"}


def _decimal_text(value: object) -> str:
    if isinstance(value, bool):
        raise EvaluationError("boolean is not a numeric result value")
    try:
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EvaluationError("invalid numeric result value") from exc
    if not decimal.is_finite():
        raise EvaluationError("non-finite numeric value requires FLOAT64 special handling")
    if decimal.is_zero():
        return "0"
    rendered = format(decimal.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _json_value(value: object) -> object:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        return ("number", _decimal_text(value))
    if isinstance(value, float):
        if math.isnan(value):
            return ("float_special", "nan")
        if math.isinf(value):
            return ("float_special", "+inf" if value > 0 else "-inf")
        return ("number", _decimal_text(value))
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_json_value(item) for item in value))
    if isinstance(value, Mapping):
        return (
            "object",
            tuple((str(key), _json_value(item)) for key, item in sorted(value.items())),
        )
    raise EvaluationError(f"unsupported JSON result value: {type(value).__name__}")


def canonicalize_value(value: object, field: ResultField) -> object:
    """Normalize one BigQuery value to a recursively tagged immutable value."""
    if value is None:
        return ("null",)
    if field.mode == "REPEATED":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise EvaluationError(f"repeated field {field.name!r} must be an array")
        item_field = replace(field, mode="NULLABLE")
        return ("array", tuple(canonicalize_value(item, item_field) for item in value))

    type_name = field.type_name.upper()
    if type_name.startswith("ARRAY<") and type_name.endswith(">"):
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise EvaluationError(f"array field {field.name!r} must be an array")
        inner = type_name[6:-1]
        item_field = ResultField(field.name, inner, fields=field.fields)
        return ("array", tuple(canonicalize_value(item, item_field) for item in value))
    if type_name in _STRUCT_TYPES:
        if not isinstance(value, Mapping) and not hasattr(value, "__getitem__"):
            raise EvaluationError(f"struct field {field.name!r} must be mapping-like")
        return (
            "struct",
            tuple(
                (nested.name, canonicalize_value(value[nested.name], nested))  # type: ignore[index]
                for nested in sorted(field.fields, key=lambda item: item.name)
            ),
        )
    if type_name == "JSON":
        return ("json", _json_value(value))
    if type_name in {"BOOL", "BOOLEAN"}:
        if not isinstance(value, bool):
            raise EvaluationError("BOOL result must be boolean")
        return ("bool", value)
    if type_name in _NUMERIC_TYPES:
        if type_name in {"FLOAT64", "FLOAT"} and isinstance(value, float):
            if math.isnan(value):
                return ("float_special", "nan")
            if math.isinf(value):
                return ("float_special", "+inf" if value > 0 else "-inf")
        return ("number", _decimal_text(value))
    if type_name == "TIMESTAMP":
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise EvaluationError("TIMESTAMP result must be timezone-aware datetime")
        rendered = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return ("timestamp", rendered)
    if type_name == "DATE":
        if not isinstance(value, date) or isinstance(value, datetime):
            raise EvaluationError("DATE result must be a date")
        return ("date", value.isoformat())
    if type_name == "TIME":
        if not isinstance(value, time) or value.tzinfo is not None:
            raise EvaluationError("TIME result must be timezone-free time")
        return ("time", value.isoformat())
    if type_name == "DATETIME":
        if not isinstance(value, datetime) or value.tzinfo is not None:
            raise EvaluationError("DATETIME result must be timezone-free datetime")
        return ("datetime", value.isoformat())
    if type_name in {"BYTES", "BINARY"}:
        if not isinstance(value, bytes):
            raise EvaluationError("BYTES result must be bytes")
        return ("bytes", base64.b64encode(value).decode("ascii"))
    if type_name in {"STRING", "GEOGRAPHY"}:
        if not isinstance(value, str):
            raise EvaluationError(f"{type_name} result must be text")
        return ("string", value)
    raise EvaluationError(f"unsupported BigQuery result type {field.type_name!r}")


def _row_values(row: object, schema: Sequence[ResultField]) -> tuple[object, ...]:
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        if len(row) != len(schema):
            raise EvaluationError("result row arity does not match schema")
        return tuple(row)
    if isinstance(row, Mapping) or hasattr(row, "__getitem__"):
        try:
            return tuple(row[field.name] for field in schema)  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise EvaluationError("mapping-like result row does not match schema") from exc
    raise EvaluationError("result row must be positional or mapping-like")


def canonicalize_result(
    rows: Iterable[object],
    schema: Sequence[ResultField],
    *,
    order_sensitive: bool,
) -> QueryResultEvidence:
    """Hash typed rows in schema order, preserving sequence or multiset multiplicity."""
    fields = tuple(schema)
    normalized_digests: list[str] = []
    for row in rows:
        values = _row_values(row, fields)
        normalized = tuple(
            canonicalize_value(value, field) for value, field in zip(values, fields, strict=True)
        )
        normalized_digests.append(hashlib.sha256(canonical_json(normalized)).hexdigest())
    if not order_sensitive:
        normalized_digests.sort()
    row_digests = tuple(normalized_digests)
    schema_sha256 = hashlib.sha256(canonical_json(fields)).hexdigest()
    result_sha256 = hashlib.sha256(
        canonical_json(
            {
                "arity": len(fields),
                "order_sensitive": order_sensitive,
                "row_digests": row_digests,
            }
        )
    ).hexdigest()
    return QueryResultEvidence(
        fields=fields,
        schema_sha256=schema_sha256,
        row_count=len(row_digests),
        arity=len(fields),
        order_sensitive=order_sensitive,
        row_digests=row_digests,
        result_sha256=result_sha256,
    )


def results_equal(gold: QueryResultEvidence, predicted: QueryResultEvidence) -> bool:
    """Compare result values under the gold query's order semantics."""
    if gold.arity != predicted.arity or gold.row_count != predicted.row_count:
        return False
    if gold.order_sensitive:
        return gold.row_digests == predicted.row_digests
    return Counter(gold.row_digests) == Counter(predicted.row_digests)


def answer_scores(gold: QueryResultEvidence, predicted: QueryResultEvidence) -> AnswerScores:
    """Compute multiset answer precision, recall and F1 with explicit empty rules."""
    gold_counter = Counter(gold.row_digests)
    predicted_counter = Counter(predicted.row_digests)
    if not gold_counter and not predicted_counter:
        return AnswerScores(1.0, 1.0, 1.0)
    if not gold_counter or not predicted_counter:
        return AnswerScores(0.0, 0.0, 0.0)
    overlap = sum((gold_counter & predicted_counter).values())
    precision = overlap / sum(predicted_counter.values())
    recall = overlap / sum(gold_counter.values())
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return AnswerScores(precision, recall, f1)
