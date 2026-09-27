import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from nl2sparql.evaluation.contracts import ResultField
from nl2sparql.evaluation.result_semantics import (
    answer_scores,
    canonicalize_result,
    canonicalize_value,
    results_equal,
)


class MappingRow:
    """Small mapping-like stand-in for google.cloud.bigquery.Row."""

    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> object:
        return self._values[key]


def test_scalar_values_are_typed_and_numeric_values_compare_exactly() -> None:
    integer = ResultField("v", "INT64")
    numeric = ResultField("v", "NUMERIC")
    floating = ResultField("v", "FLOAT64")

    assert canonicalize_value(None, integer) == ("null",)
    assert canonicalize_value(True, ResultField("v", "BOOL")) != canonicalize_value(1, integer)
    assert canonicalize_value(1, integer) == canonicalize_value(Decimal("1.00"), numeric)
    assert canonicalize_value(-0.0, floating) == canonicalize_value(0, integer)
    assert canonicalize_value(0.1, floating) == canonicalize_value(Decimal("0.1"), numeric)
    assert canonicalize_value(float("nan"), floating) == ("float_special", "nan")
    assert canonicalize_value(float("inf"), floating) == ("float_special", "+inf")
    assert canonicalize_value(float("-inf"), floating) == ("float_special", "-inf")


def test_temporal_bytes_and_strings_preserve_semantics() -> None:
    timestamp = datetime(2026, 9, 26, 19, 0, tzinfo=timezone(timedelta(hours=7)))
    assert canonicalize_value(timestamp, ResultField("v", "TIMESTAMP")) == (
        "timestamp",
        "2026-09-26T12:00:00Z",
    )
    assert canonicalize_value(date(2026, 9, 26), ResultField("v", "DATE"))[0] == "date"
    assert canonicalize_value(time(12, 1, 2), ResultField("v", "TIME"))[0] == "time"
    assert (
        canonicalize_value(datetime(2026, 9, 26, 12, 0), ResultField("v", "DATETIME"))[0]
        == "datetime"
    )
    assert canonicalize_value(b"\x00\xff", ResultField("v", "BYTES")) == (
        "bytes",
        "AP8=",
    )
    assert canonicalize_value("Binance", ResultField("v", "STRING")) == (
        "string",
        "Binance",
    )


def test_arrays_nested_structs_and_json_are_recursive_and_key_order_independent() -> None:
    struct = ResultField(
        "items",
        "STRUCT",
        mode="REPEATED",
        fields=(ResultField("amount", "NUMERIC"), ResultField("owner", "STRING")),
    )
    left = [{"owner": "A", "amount": Decimal("2.0")}, {"owner": "B", "amount": 3}]
    right = [{"amount": Decimal("2"), "owner": "A"}, {"amount": 3, "owner": "B"}]
    assert canonicalize_value(left, struct) == canonicalize_value(right, struct)

    json_field = ResultField("payload", "JSON")
    assert canonicalize_value({"z": [1, True], "a": None}, json_field) == canonicalize_value(
        {"a": None, "z": [Decimal("1.0"), True]}, json_field
    )


def test_rows_follow_schema_order_for_mapping_like_bigquery_rows() -> None:
    schema = (ResultField("first", "INT64"), ResultField("second", "STRING"))
    mapping_result = canonicalize_result(
        [MappingRow({"second": "x", "first": 1})], schema, order_sensitive=False
    )
    tuple_result = canonicalize_result([(1, "x")], schema, order_sensitive=False)

    assert mapping_result.row_digests == tuple_result.row_digests
    assert results_equal(mapping_result, tuple_result)


def test_unordered_results_preserve_duplicates_and_ordered_results_preserve_sequence() -> None:
    schema = (ResultField("v", "INT64"),)
    two_duplicates = canonicalize_result([(1,), (1,), (2,)], schema, order_sensitive=False)
    one_duplicate = canonicalize_result([(1,), (2,)], schema, order_sensitive=False)
    reordered = canonicalize_result([(2,), (1,), (1,)], schema, order_sensitive=False)

    assert not results_equal(two_duplicates, one_duplicate)
    assert results_equal(two_duplicates, reordered)

    ordered = canonicalize_result([(1,), (2,)], schema, order_sensitive=True)
    reversed_order = canonicalize_result([(2,), (1,)], schema, order_sensitive=True)
    assert not results_equal(ordered, reversed_order)
    assert answer_scores(ordered, reversed_order).f1 == 1.0


def test_aliases_do_not_affect_equality_but_arity_and_position_do() -> None:
    gold = canonicalize_result(
        [(1, "x")],
        (ResultField("owner", "INT64"), ResultField("label", "STRING")),
        order_sensitive=False,
    )
    aliased = canonicalize_result(
        [(1, "x")],
        (ResultField("sender", "INT64"), ResultField("name", "STRING")),
        order_sensitive=False,
    )
    swapped = canonicalize_result(
        [("x", 1)],
        (ResultField("label", "STRING"), ResultField("owner", "INT64")),
        order_sensitive=False,
    )
    fewer = canonicalize_result([(1,)], (ResultField("owner", "INT64"),), order_sensitive=False)

    assert results_equal(gold, aliased)
    assert not results_equal(gold, swapped)
    assert not results_equal(gold, fewer)


def test_answer_overlap_uses_multisets_and_explicit_empty_conventions() -> None:
    schema = (ResultField("v", "INT64"),)
    empty = canonicalize_result([], schema, order_sensitive=False)
    gold = canonicalize_result([(1,), (1,), (2,)], schema, order_sensitive=False)
    predicted = canonicalize_result([(1,), (2,), (2,)], schema, order_sensitive=False)

    both_empty = answer_scores(empty, empty)
    assert (both_empty.precision, both_empty.recall, both_empty.f1) == (1.0, 1.0, 1.0)
    assert answer_scores(gold, empty).f1 == 0.0
    assert answer_scores(empty, predicted).f1 == 0.0
    scores = answer_scores(gold, predicted)
    assert math.isclose(scores.precision, 2 / 3)
    assert math.isclose(scores.recall, 2 / 3)
    assert math.isclose(scores.f1, 2 / 3)
