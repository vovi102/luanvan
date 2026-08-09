from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.linking.dictionary import ENTITIES_PATH
from nl2sparql.sql.label_layer import (
    LABEL_TABLE_SCHEMA,
    LabelLayerError,
    build_label_snapshot,
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
