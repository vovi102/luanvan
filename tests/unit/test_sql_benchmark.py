from __future__ import annotations

import re

import pytest

from nl2sparql.sql.benchmark import (
    BENCHMARK_CASES,
    TOTAL_BENCHMARK_BYTES_CAP,
    BenchmarkError,
    validate_benchmark_cases,
)
from nl2sparql.sql.label_layer import DEFAULT_MAXIMUM_BYTES_BILLED

EXPECTED_CASE_IDS = (
    "label_contract",
    "transaction_count",
    "block_count",
    "contract_dimension_contract",
    "labeled_transaction_cardinality",
    "labeled_token_transfer_contract",
)


def test_committed_benchmark_has_six_stable_machine_assertions() -> None:
    validate_benchmark_cases()

    assert tuple(case.case_id for case in BENCHMARK_CASES) == EXPECTED_CASE_IDS
    assert len({case.description for case in BENCHMARK_CASES}) == 6
    assert {case.difficulty for case in BENCHMARK_CASES} == {
        "small",
        "simple",
        "complex",
    }
    for case in BENCHMARK_CASES:
        assert case.sql.lstrip().upper().startswith(("SELECT", "WITH"))
        assert re.search(r"\bpassed\b", case.sql, re.IGNORECASE)
        assert (
            re.search(
                r"\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE)\b", case.sql, re.IGNORECASE
            )
            is None
        )


def test_fact_cases_pin_the_approved_half_open_window() -> None:
    for case in BENCHMARK_CASES[1:]:
        assert "DATE '2026-07-01'" in case.sql
    for case in (
        BENCHMARK_CASES[1],
        BENCHMARK_CASES[2],
        BENCHMARK_CASES[4],
        BENCHMARK_CASES[5],
    ):
        assert "DATE '2026-05-31'" in case.sql


def test_cases_use_only_fully_qualified_managed_interfaces() -> None:
    sql = "\n".join(case.sql for case in BENCHMARK_CASES)

    for object_name in (
        "entity_labels_v1",
        "transaction_facts",
        "block_facts",
        "contract_dimension",
        "labeled_transactions",
        "labeled_token_transfers",
    ):
        assert f"`nl2sparql-thesis.nl2sparql_analytics.{object_name}`" in sql
    assert "`bigquery-public-data." not in sql


def test_cases_encode_historical_counts_and_precision_invariants() -> None:
    cases = {case.case_id: case.sql for case in BENCHMARK_CASES}

    assert "5135" in cases["label_contract"]
    assert "14" in cases["label_contract"]
    assert "5091" in cases["label_contract"]
    assert "30" in cases["label_contract"]
    assert "4431329" in cases["transaction_count"]
    assert "221548" in cases["block_count"]
    assert "COUNT(DISTINCT address)" in cases["contract_dimension_contract"]
    assert "4431329" in cases["labeled_transaction_cardinality"]
    token_sql = cases["labeled_token_transfer_contract"]
    assert "4001230" in token_sql
    assert "value_cast_valid IS NOT TRUE" in token_sql
    assert "is_erc20 IS NOT TRUE" in token_sql
    assert "COALESCE(is_erc721, FALSE) IS NOT FALSE" in token_sql
    assert "token_decimals NOT BETWEEN 0 AND 38" in token_sql


def test_benchmark_caps_are_stricter_in_aggregate_than_six_query_caps() -> None:
    assert DEFAULT_MAXIMUM_BYTES_BILLED == 53_687_091_200
    assert TOTAL_BENCHMARK_BYTES_CAP == 107_374_182_400
    assert TOTAL_BENCHMARK_BYTES_CAP < len(BENCHMARK_CASES) * DEFAULT_MAXIMUM_BYTES_BILLED


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "duplicate"),
        ("unbounded", "approved date bounds"),
        ("mutation", "read-only"),
        ("no_assertion", "passed"),
    ],
)
def test_case_validation_fails_closed(mutation: str, message: str) -> None:
    cases = list(BENCHMARK_CASES)
    if mutation == "duplicate":
        cases[1] = cases[0]
    elif mutation == "unbounded":
        cases[1] = cases[1].__class__(
            case_id=cases[1].case_id,
            description=cases[1].description,
            difficulty=cases[1].difficulty,
            sql="SELECT TRUE AS passed",
            requires_window=True,
        )
    elif mutation == "mutation":
        cases[0] = cases[0].__class__(
            case_id=cases[0].case_id,
            description=cases[0].description,
            difficulty=cases[0].difficulty,
            sql="DELETE FROM `p.d.t` WHERE TRUE; SELECT TRUE AS passed",
            requires_window=False,
        )
    else:
        cases[0] = cases[0].__class__(
            case_id=cases[0].case_id,
            description=cases[0].description,
            difficulty=cases[0].difficulty,
            sql="SELECT TRUE AS ok",
            requires_window=False,
        )

    with pytest.raises(BenchmarkError, match=message):
        validate_benchmark_cases(tuple(cases))
