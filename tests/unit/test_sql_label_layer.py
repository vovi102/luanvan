from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from nl2sparql.linking.dictionary import ENTITIES_PATH
from nl2sparql.sql.label_layer import (
    LABEL_TABLE_SCHEMA,
    LabelLayerError,
    build_label_snapshot,
    render_label_layer_ddl,
    render_rollback_ddl,
)


def write_entities(path: Path, entities: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps(entities, indent=2), encoding="utf-8")
    return path


def entity_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "address": "0x1111111111111111111111111111111111111111",
        "address_lower": "0x1111111111111111111111111111111111111111",
        "primary_label": "Protocol: Router",
        "owner": "Protocol",
        "category": "dex",
        "concept_class": "DEXProtocol",
        "aliases": ["protocol", "protocol router"],
        "chain_id": 1,
        "address_role": "operational",
        "sources": [
            {
                "name": "source",
                "url": "https://example.com/source",
                "revision": "a" * 40,
                "locator": "contracts/router.json:L1",
                "retrieved_date": "2026-08-09",
                "note": "Verified operational endpoint",
            }
        ],
        "confidence": "high",
        "verified_date": "2026-08-09",
    }
    row.update(overrides)
    return row


def test_committed_dictionary_builds_expected_immutable_snapshot() -> None:
    snapshot = build_label_snapshot()

    assert snapshot.digest == ("190f73a91b7affa8b8396cc189e4a6b332dc6f7f0109037a0d44edb14531c536")
    assert snapshot.table_name == "entity_labels_snapshot_190f73a91b7a"
    assert snapshot.entity_count == 5135
    assert snapshot.role_counts == {
        "operational": 14,
        "token": 5091,
        "treasury": 30,
    }
    assert len(snapshot.rows) == snapshot.entity_count
    assert len({row["address"] for row in snapshot.rows}) == snapshot.entity_count
    assert {row["dictionary_sha256"] for row in snapshot.rows} == {snapshot.digest}


def test_snapshot_mapping_is_deterministic_and_preserves_nested_evidence(
    tmp_path: Path,
) -> None:
    path = write_entities(tmp_path / "entities.json", [entity_row()])
    expected_digest = hashlib.sha256(path.read_bytes()).hexdigest()

    first = build_label_snapshot(path)
    second = build_label_snapshot(path)

    assert first == second
    assert first.table_name == f"entity_labels_snapshot_{expected_digest[:12]}"
    assert first.rows == (
        {
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "primary_label": "Protocol: Router",
            "owner": "Protocol",
            "category": "dex",
            "concept_class": "DEXProtocol",
            "address_role": "operational",
            "aliases": ["protocol", "protocol router"],
            "confidence": "high",
            "verified_date": "2026-08-09",
            "sources": [
                {
                    "name": "source",
                    "url": "https://example.com/source",
                    "revision": "a" * 40,
                    "locator": "contracts/router.json:L1",
                    "retrieved_date": "2026-08-09",
                    "note": "Verified operational endpoint",
                }
            ],
            "dictionary_sha256": expected_digest,
        },
    )


def test_label_table_schema_is_explicit_and_preserves_repeated_sources() -> None:
    fields = {field.name: field for field in LABEL_TABLE_SCHEMA}

    assert set(fields) == {
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
    assert fields["address"].field_type == "STRING"
    assert fields["address"].mode == "REQUIRED"
    assert fields["aliases"].mode == "REPEATED"
    assert fields["verified_date"].field_type == "DATE"
    assert fields["sources"].field_type == "RECORD"
    assert fields["sources"].mode == "REPEATED"
    assert {field.name for field in fields["sources"].fields} == {
        "name",
        "url",
        "revision",
        "locator",
        "retrieved_date",
        "note",
    }


@pytest.mark.parametrize(
    ("entities", "message"),
    [
        ([], "at least one"),
        ([entity_row(address_role="unknown")], "address_role"),
        (
            [entity_row(), entity_row(primary_label="Duplicate")],
            "Duplicate address",
        ),
        (
            [entity_row(address_lower="0x2222222222222222222222222222222222222222")],
            "address_lower mismatch",
        ),
        ([entity_row(sources=[])], "at least one source"),
    ],
)
def test_snapshot_builder_fails_closed_for_invalid_entities(
    tmp_path: Path, entities: list[dict[str, object]], message: str
) -> None:
    path = write_entities(tmp_path / "entities.json", entities)

    with pytest.raises(LabelLayerError, match=message):
        build_label_snapshot(path)


def test_snapshot_builder_fails_closed_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "entities.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(LabelLayerError, match="Invalid entities JSON"):
        build_label_snapshot(path)


def test_snapshot_builder_defaults_to_committed_entities_path() -> None:
    assert ENTITIES_PATH.name == "entities.json"
    assert build_label_snapshot().entities_path == ENTITIES_PATH


@pytest.fixture
def sql_objects():
    return render_label_layer_ddl(
        "nl2sparql-thesis",
        "nl2sparql_analytics",
        "entity_labels_snapshot_190f73a91b7a",
    )


def test_ddl_renderer_returns_dependency_ordered_views_and_tvfs(sql_objects) -> None:
    assert [(obj.name, obj.kind) for obj in sql_objects] == [
        ("entity_labels_v1", "VIEW"),
        ("token_dimension", "VIEW"),
        ("transaction_facts", "TABLE FUNCTION"),
        ("block_facts", "TABLE FUNCTION"),
        ("contract_dimension", "TABLE FUNCTION"),
        ("token_transfer_facts", "TABLE FUNCTION"),
        ("labeled_transactions", "TABLE FUNCTION"),
        ("labeled_token_transfers", "TABLE FUNCTION"),
    ]
    assert sql_objects[0].dependencies == ("entity_labels_snapshot_190f73a91b7a",)
    assert sql_objects[-1].dependencies == (
        "token_transfer_facts",
        "entity_labels_v1",
    )
    for obj in sql_objects:
        assert obj.ddl.startswith(f"CREATE OR REPLACE {obj.kind}")
        assert f"`nl2sparql-thesis.nl2sparql_analytics.{obj.name}`" in obj.ddl
        assert re.search(r"SELECT\s+\*", obj.ddl, re.IGNORECASE) is None


def test_core_fact_tvfs_enforce_typed_half_open_partition_bounds(sql_objects) -> None:
    objects = {obj.name: obj.ddl for obj in sql_objects}

    transactions = objects["transaction_facts"]
    assert "(start_date DATE, end_date DATE)" in transactions
    assert "DATE_DIFF(end_date, start_date, DAY) <= 31" in transactions
    assert "ERROR(" in transactions
    assert "t.block_timestamp >= TIMESTAMP(start_date)" in transactions
    assert "t.block_timestamp < TIMESTAMP(end_date)" in transactions
    assert "`bigquery-public-data.crypto_ethereum.transactions` AS t" in transactions
    assert "LOWER(t.hash) AS transaction_hash" in transactions
    assert "t.value AS value_wei" in transactions

    blocks = objects["block_facts"]
    assert "b.timestamp >= TIMESTAMP(start_date)" in blocks
    assert "b.timestamp < TIMESTAMP(end_date)" in blocks
    assert "LOWER(b.miner) AS beneficiary_address" in blocks


def test_contract_and_token_transfer_sql_preserve_deduplication_and_precision(
    sql_objects,
) -> None:
    objects = {obj.name: obj.ddl for obj in sql_objects}

    contracts = objects["contract_dimension"]
    assert "(end_date DATE)" in contracts
    assert "c.block_timestamp < TIMESTAMP(end_date)" in contracts
    assert "ROW_NUMBER() OVER" in contracts
    assert "PARTITION BY LOWER(c.address)" in contracts
    assert "QUALIFY" in contracts

    transfers = objects["token_transfer_facts"]
    assert "tt.block_timestamp >= TIMESTAMP(start_date)" in transfers
    assert "tt.block_timestamp < TIMESTAMP(end_date)" in transfers
    assert "SAFE_CAST(tt.value AS BIGNUMERIC) AS value_bignumeric" in transfers
    assert "SAFE_CAST(tok.decimals AS INT64) BETWEEN 0 AND 38" in transfers
    assert "COALESCE(c.is_erc721, FALSE) IS FALSE" in transfers
    assert "POW(BIGNUMERIC '10', SAFE_CAST(tok.decimals AS INT64))" in transfers
    assert "LEFT JOIN `nl2sparql-thesis.nl2sparql_analytics.contract_dimension`" in transfers
    assert "LEFT JOIN `nl2sparql-thesis.nl2sparql_analytics.token_dimension`" in transfers


def test_enriched_tvfs_use_unique_left_joins_and_flat_role_fields(sql_objects) -> None:
    objects = {obj.name: obj.ddl for obj in sql_objects}

    transactions = objects["labeled_transactions"]
    assert transactions.count("LEFT JOIN") == 2
    assert "from_label.address_role AS from_address_role" in transactions
    assert "to_label.address_role AS to_address_role" in transactions
    assert "from_label.aliases" not in transactions
    assert "from_label.sources" not in transactions

    transfers = objects["labeled_token_transfers"]
    assert transfers.count("LEFT JOIN") == 3
    for field in (
        "from_address_role",
        "to_address_role",
        "token_address_role",
        "token_primary_label",
    ):
        assert field in transfers
    assert "ON facts.token_address = token_label.address" in transfers


@pytest.mark.parametrize(
    ("project", "dataset", "snapshot"),
    [
        ("bad`project", "nl2sparql_analytics", "entity_labels_snapshot_abc"),
        ("nl2sparql-thesis", "bad.dataset", "entity_labels_snapshot_abc"),
        ("nl2sparql-thesis", "nl2sparql_analytics", "bad;table"),
    ],
)
def test_ddl_renderer_rejects_unsafe_identifiers(project: str, dataset: str, snapshot: str) -> None:
    with pytest.raises(LabelLayerError, match="identifier"):
        render_label_layer_ddl(project, dataset, snapshot)


def test_rollback_ddl_only_repoints_stable_view_to_named_snapshot() -> None:
    ddl = render_rollback_ddl(
        "nl2sparql-thesis",
        "nl2sparql_analytics",
        "entity_labels_snapshot_0123456789ab",
    )

    assert ddl.startswith("CREATE OR REPLACE VIEW")
    assert "`nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`" in ddl
    assert "`nl2sparql-thesis.nl2sparql_analytics.entity_labels_snapshot_0123456789ab`" in ddl
    assert "DROP " not in ddl
    assert "DELETE " not in ddl
