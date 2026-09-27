import pytest

from nl2sparql.evaluation.contracts import EvaluationError
from nl2sparql.evaluation.sql_semantics import analyze_sql, exact_match, structural_match


def test_exact_match_normalizes_format_and_keywords_but_preserves_string_case() -> None:
    assert exact_match(
        "select owner from `p.d.labels` where label = 'Binance'",
        "SELECT owner\nFROM `p.d.labels`\nWHERE label='Binance'",
    )
    assert not exact_match(
        "SELECT owner FROM `p.d.labels` WHERE label = 'binance'",
        "SELECT owner FROM `p.d.labels` WHERE label = 'Binance'",
    )


def test_alias_only_differences_structural_match() -> None:
    assert structural_match(
        "SELECT a.address AS sender FROM `p.d.tx` AS a WHERE a.value > 10",
        "SELECT transaction.address AS source FROM `p.d.tx` transaction "
        "WHERE transaction.value > 20",
    )


def test_typed_literal_changes_share_signature_but_keep_distinct_filter_facts() -> None:
    string_analysis = analyze_sql("SELECT x FROM `p.d.t` WHERE label = 'ABC'")
    other_string = analyze_sql("SELECT x FROM `p.d.t` WHERE label = 'abc'")
    numeric_analysis = analyze_sql("SELECT x FROM `p.d.t` WHERE label = 3")

    assert string_analysis.structural_signature == other_string.structural_signature
    assert string_analysis.facts.filters != other_string.facts.filters
    assert string_analysis.structural_signature != numeric_analysis.structural_signature


def test_cte_names_are_not_reported_as_relations() -> None:
    analysis = analyze_sql(
        "WITH recent AS (SELECT address, value FROM `p.d.tx`) "
        "SELECT address FROM recent WHERE value > 0"
    )
    assert analysis.facts.relations == ("p.d.tx",)


def test_only_top_level_order_by_selects_sequence_semantics() -> None:
    nested = analyze_sql("SELECT address FROM (SELECT address FROM `p.d.tx` ORDER BY address)")
    top_level = analyze_sql("SELECT address FROM `p.d.tx` ORDER BY address")

    assert nested.result_order == "multiset"
    assert top_level.result_order == "sequence"


def test_structural_facts_cover_projection_join_aggregation_window_order_and_limits() -> None:
    analysis = analyze_sql(
        "SELECT a.owner, COUNT(*) AS n, "
        "ROW_NUMBER() OVER (PARTITION BY a.owner ORDER BY b.block_number DESC) AS rn "
        "FROM `p.d.addresses` a LEFT JOIN `p.d.blocks` b "
        "ON a.block_number = b.block_number "
        "WHERE a.active = TRUE GROUP BY a.owner HAVING COUNT(*) > 1 "
        "QUALIFY rn = 1 ORDER BY n DESC LIMIT 10 OFFSET 2"
    )

    assert analysis.facts.relations == ("p.d.addresses", "p.d.blocks")
    assert len(analysis.facts.projections) == 3
    assert analysis.facts.joins and "LEFT" in analysis.facts.joins[0]
    assert analysis.facts.aggregations == ("COUNT(*)", "COUNT(*)")
    assert analysis.facts.windows
    assert analysis.facts.ordering
    assert analysis.facts.limit == "10"
    assert analysis.facts.offset == "2"
    assert len(analysis.facts.filters) == 3


def test_invalid_or_non_query_sql_raises_typed_error() -> None:
    with pytest.raises(EvaluationError, match="GoogleSQL"):
        analyze_sql("SELECT FROM")
    with pytest.raises(EvaluationError, match="read-only query"):
        analyze_sql("DELETE FROM `p.d.tx` WHERE TRUE")
