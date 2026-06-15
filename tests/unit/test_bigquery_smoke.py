from google.cloud import bigquery

from nl2sparql.kg.extraction.bigquery_smoke import (
    BLOCKS_TABLE,
    CONTRACTS_TABLE,
    COUNT_TRANSACTIONS_SQL,
    TOKEN_TRANSFERS_TABLE,
    TRANSACTIONS_TABLE,
    build_monthly_extraction_estimate_sql,
    make_dry_run_config,
)


def test_bigquery_table_constants_point_to_public_ethereum_dataset() -> None:
    assert TRANSACTIONS_TABLE == "bigquery-public-data.crypto_ethereum.transactions"
    assert BLOCKS_TABLE == "bigquery-public-data.crypto_ethereum.blocks"
    assert TOKEN_TRANSFERS_TABLE == "bigquery-public-data.crypto_ethereum.token_transfers"
    assert CONTRACTS_TABLE == "bigquery-public-data.crypto_ethereum.contracts"


def test_count_transactions_sql_has_required_date_filter() -> None:
    assert "`bigquery-public-data.crypto_ethereum.transactions`" in COUNT_TRANSACTIONS_SQL
    assert "DATE(block_timestamp) = '2024-01-01'" in COUNT_TRANSACTIONS_SQL
    assert "COUNT(*) AS n" in COUNT_TRANSACTIONS_SQL


def test_monthly_estimate_sql_selects_only_needed_columns_and_filters_dates() -> None:
    sql = build_monthly_extraction_estimate_sql("2024-01-01", "2024-01-31")

    assert "SELECT `hash`, from_address, to_address, value, block_timestamp" in sql
    assert "SELECT *" not in sql
    assert "DATE(block_timestamp) BETWEEN '2024-01-01' AND '2024-01-31'" in sql


def test_dry_run_config_disables_query_cache() -> None:
    config = make_dry_run_config()

    assert isinstance(config, bigquery.QueryJobConfig)
    assert config.dry_run is True
    assert config.use_query_cache is False
