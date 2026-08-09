from __future__ import annotations

import copy
import importlib.util
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from nl2sparql.sql.schema import (
    CATALOG_PATH,
    LiveField,
    SchemaCatalogError,
    load_catalog,
    normalize_live_schema,
    validate_catalog,
    validate_date_window,
    validate_live_schemas,
)

EXPECTED_SOURCE_IDS = {
    "transactions",
    "blocks",
    "token_transfers",
    "contracts",
    "amended_tokens",
    "entity_labels_v1",
}
EXPECTED_RELATION_IDS = {
    "transaction_facts",
    "block_facts",
    "token_transfer_facts",
    "contract_dimension",
    "token_dimension",
    "entity_labels_v1",
}
EXPECTED_JOIN_IDS = {
    "transaction_to_block",
    "transaction_to_contract",
    "transfer_to_transaction",
    "transfer_to_contract",
    "transfer_to_token",
    "fact_address_to_entity",
}


@pytest.fixture
def catalog() -> dict[str, object]:
    return load_catalog()


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_committed_catalog_declares_approved_top_level_contract(
    catalog: dict[str, object],
) -> None:
    summary = validate_catalog(catalog)

    assert CATALOG_PATH.name == "ethereum_analytics.json"
    assert set(catalog["physical_sources"]) == EXPECTED_SOURCE_IDS
    assert set(catalog["analytical_relations"]) == EXPECTED_RELATION_IDS
    assert set(catalog["join_paths"]) == EXPECTED_JOIN_IDS
    assert summary.source_count == 6
    assert summary.relation_count == 6
    assert summary.join_count == 6


def test_load_catalog_fails_closed_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SchemaCatalogError, match="Unable to read schema catalog"):
        load_catalog(tmp_path / "missing.json")


def test_load_catalog_fails_closed_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SchemaCatalogError, match="Invalid schema catalog JSON"):
        load_catalog(path)


def test_load_catalog_requires_a_json_object(tmp_path: Path) -> None:
    path = write_json(tmp_path / "array.json", [])

    with pytest.raises(SchemaCatalogError, match="top level must be an object"):
        load_catalog(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("catalog_version", "2.0.0", "catalog_version"),
        ("dialect", "legacy_sql", "dialect"),
        ("location", "EU", "location"),
    ],
)
def test_validate_catalog_rejects_unknown_global_contract_values(
    catalog: dict[str, object], field: str, value: object, message: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid[field] = value

    with pytest.raises(SchemaCatalogError, match=message):
        validate_catalog(invalid)


@pytest.mark.parametrize(
    "section",
    [
        "evaluation_window",
        "cost_policy",
        "physical_sources",
        "analytical_relations",
        "join_paths",
        "role_policies",
        "semantic_mappings",
        "competency_questions",
    ],
)
def test_validate_catalog_requires_every_top_level_section(
    catalog: dict[str, object], section: str
) -> None:
    invalid = copy.deepcopy(catalog)
    del invalid[section]

    with pytest.raises(SchemaCatalogError, match=section):
        validate_catalog(invalid)


@pytest.mark.parametrize("maximum_bytes_billed", [0, -1, 12.5, "53687091200"])
def test_validate_catalog_requires_positive_integer_byte_cap(
    catalog: dict[str, object], maximum_bytes_billed: object
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["cost_policy"]["maximum_bytes_billed"] = maximum_bytes_billed

    with pytest.raises(SchemaCatalogError, match="maximum_bytes_billed"):
        validate_catalog(invalid)


def test_validate_catalog_requires_dry_run(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["cost_policy"]["dry_run_required"] = False

    with pytest.raises(SchemaCatalogError, match="dry_run_required"):
        validate_catalog(invalid)


@pytest.mark.parametrize(
    "section",
    ["physical_sources", "analytical_relations", "join_paths", "role_policies"],
)
def test_validate_catalog_requires_mapping_sections(
    catalog: dict[str, object], section: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid[section] = []

    with pytest.raises(SchemaCatalogError, match=section):
        validate_catalog(invalid)


@pytest.mark.parametrize("section", ["semantic_mappings", "competency_questions"])
def test_validate_catalog_requires_sequence_sections(
    catalog: dict[str, object], section: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid[section] = {}

    with pytest.raises(SchemaCatalogError, match=section):
        validate_catalog(invalid)


def test_committed_catalog_encodes_approved_source_and_relation_contract(
    catalog: dict[str, object],
) -> None:
    summary = validate_catalog(catalog)
    sources = catalog["physical_sources"]
    relations = catalog["analytical_relations"]

    assert sources["transactions"]["object"] == (
        "bigquery-public-data.crypto_ethereum.transactions"
    )
    assert sources["transactions"]["partition_field"] == "block_timestamp"
    assert sources["amended_tokens"]["object_kind"] == "logical_view"
    assert sources["entity_labels_v1"]["deployment_status"] == "deferred"
    assert relations["transaction_facts"]["kind"] == "parameterized_fact"
    assert relations["contract_dimension"]["kind"] == "bounded_dimension"
    assert relations["token_dimension"]["kind"] == "parameterless_dimension"
    assert set(catalog["role_policies"]) == {"operational", "treasury", "token"}
    assert summary.semantic_mapping_count >= 25


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        (date(2026, 5, 31), date(2026, 6, 1)),
        (date(2026, 5, 31), date(2026, 7, 1)),
    ],
)
def test_validate_date_window_accepts_half_open_windows_up_to_31_days(
    start_date: date, end_date: date
) -> None:
    validate_date_window(start_date, end_date)


@pytest.mark.parametrize(
    ("start_date", "end_date", "message"),
    [
        (date(2026, 6, 1), date(2026, 6, 1), "before"),
        (date(2026, 6, 2), date(2026, 6, 1), "before"),
        (date(2026, 5, 31), date(2026, 7, 2), "31 days"),
    ],
)
def test_validate_date_window_rejects_empty_reversed_or_overlong_windows(
    start_date: date, end_date: date, message: str
) -> None:
    with pytest.raises(SchemaCatalogError, match=message):
        validate_date_window(start_date, end_date)


def test_validate_date_window_rejects_non_dates() -> None:
    with pytest.raises(SchemaCatalogError, match="date instances"):
        validate_date_window("2026-05-31", "2026-07-01")


def test_validate_catalog_rejects_unknown_source_kind(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["physical_sources"]["transactions"]["object_kind"] = "external"

    with pytest.raises(SchemaCatalogError, match="object_kind"):
        validate_catalog(invalid)


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("type", "DECIMAL", "BigQuery type"),
        ("mode", "OPTIONAL", "BigQuery mode"),
    ],
)
def test_validate_catalog_rejects_unknown_physical_field_contract(
    catalog: dict[str, object], attribute: str, value: str, message: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["physical_sources"]["transactions"]["fields"]["hash"][attribute] = value

    with pytest.raises(SchemaCatalogError, match=message):
        validate_catalog(invalid)


def test_validate_catalog_rejects_missing_partition_field(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["physical_sources"]["transactions"]["partition_field"] = "missing"

    with pytest.raises(SchemaCatalogError, match="partition_field"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_unknown_relation_source(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["analytical_relations"]["transaction_facts"]["sources"] = ["missing"]

    with pytest.raises(SchemaCatalogError, match="unknown source"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_unknown_lineage_field(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["analytical_relations"]["transaction_facts"]["fields"]["transaction_hash"]["lineage"][
        0
    ]["field"] = "missing"

    with pytest.raises(SchemaCatalogError, match="lineage field"):
        validate_catalog(invalid)


def test_validate_catalog_requires_partition_coverage_for_every_relation_source(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    del invalid["analytical_relations"]["token_transfer_facts"]["source_time_filters"]["contracts"]

    with pytest.raises(SchemaCatalogError, match="source_time_filters"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_unknown_join_field(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["join_paths"]["transaction_to_block"]["conditions"][0]["left_field"] = "missing"

    with pytest.raises(SchemaCatalogError, match="join field"):
        validate_catalog(invalid)


def test_validate_catalog_requires_join_date_coverage(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["join_paths"]["transaction_to_block"]["date_covered_relations"] = ["transaction_facts"]

    with pytest.raises(SchemaCatalogError, match="date_covered_relations"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_unknown_join_role(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["join_paths"]["fact_address_to_entity"]["allowed_right_roles"].append("protocol")

    with pytest.raises(SchemaCatalogError, match="role"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_unknown_semantic_target(catalog: dict[str, object]) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["semantic_mappings"][0]["targets"][0]["relation"] = "missing"

    with pytest.raises(SchemaCatalogError, match="semantic target"):
        validate_catalog(invalid)


def test_validate_catalog_requires_explicit_unsupported_semantic_reason(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    mapping = next(item for item in invalid["semantic_mappings"] if item["status"] == "unsupported")
    mapping["reason"] = ""

    with pytest.raises(SchemaCatalogError, match="reason"):
        validate_catalog(invalid)


def test_validate_catalog_requires_managed_label_provenance(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    del invalid["physical_sources"]["entity_labels_v1"]["fields"]["sources"]

    with pytest.raises(SchemaCatalogError, match="entity_labels_v1.*sources"):
        validate_catalog(invalid)


def test_contract_dimension_deduplicates_redeployments_by_latest_block(
    catalog: dict[str, object],
) -> None:
    contract_dimension = catalog["analytical_relations"]["contract_dimension"]

    assert contract_dimension["primary_key"] == ["address"]
    assert "ROW_NUMBER() OVER (PARTITION BY LOWER(c.address)" in contract_dimension["deduplication"]
    assert "c.block_number DESC" in contract_dimension["deduplication"]


def test_token_value_precision_contract_preserves_raw_and_rejects_null_casts(
    catalog: dict[str, object],
) -> None:
    fields = catalog["analytical_relations"]["token_transfer_facts"]["fields"]

    assert fields["value_raw"]["type"] == "STRING"
    assert fields["value_bignumeric"]["type"] == "BIGNUMERIC"
    assert fields["normalized_amount"]["type"] == "BIGNUMERIC"
    assert "FLOAT64" not in fields["normalized_amount"]["expression"]
    assert fields["value_cast_valid"]["expression"] == (
        "tt.value IS NOT NULL AND SAFE_CAST(tt.value AS BIGNUMERIC) IS NOT NULL"
    )


def live_field_from_catalog(name: str, definition: dict[str, object]) -> LiveField:
    nested = tuple(
        live_field_from_catalog(child_name, child_definition)
        for child_name, child_definition in definition.get("fields", {}).items()
    )
    return LiveField(
        name=name,
        field_type=definition["type"],
        mode=definition["mode"],
        fields=nested,
    )


def live_schemas_from_catalog(
    catalog: dict[str, object],
) -> dict[str, dict[str, LiveField]]:
    return {
        source_id: {
            field_name: live_field_from_catalog(field_name, definition)
            for field_name, definition in source["fields"].items()
        }
        for source_id, source in catalog["physical_sources"].items()
        if source["deployment_status"] == "live"
    }


def test_committed_catalog_maps_exactly_cq01_through_cq30(
    catalog: dict[str, object],
) -> None:
    summary = validate_catalog(catalog)
    questions = {item["id"]: item for item in catalog["competency_questions"]}

    assert set(questions) == {f"CQ{index:02d}" for index in range(1, 31)}
    assert summary.competency_question_count == 30
    assert sum(item["status"] == "supported" for item in questions.values()) == 25
    assert sum(item["status"] == "coverage_gap" for item in questions.values()) == 4
    assert sum(item["status"] == "unsupported" for item in questions.values()) == 1


def test_cq24_is_explicitly_unsupported_without_meta_transaction_decoding(
    catalog: dict[str, object],
) -> None:
    question = next(item for item in catalog["competency_questions"] if item["id"] == "CQ24")

    assert question["status"] == "unsupported"
    assert "initiator" in question["reason"]
    assert "executor" in question["reason"]


def test_cq17_uses_block_beneficiary_without_claiming_validator_identity(
    catalog: dict[str, object],
) -> None:
    question = next(item for item in catalog["competency_questions"] if item["id"] == "CQ17")

    assert question["status"] == "supported"
    assert question["semantic_adjustment"] is True
    assert "beneficiary" in question["notes"]
    assert "not validator identity" in question["notes"]


def test_cq18_proves_contract_recipient_via_canonical_join(
    catalog: dict[str, object],
) -> None:
    question = next(item for item in catalog["competency_questions"] if item["id"] == "CQ18")

    assert question["join_paths"] == ["transaction_to_contract"]
    assert question["relations"] == ["transaction_facts", "contract_dimension"]


def test_validate_catalog_rejects_missing_competency_question(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["competency_questions"].pop()

    with pytest.raises(SchemaCatalogError, match="CQ01-CQ30"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_duplicate_competency_question(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["competency_questions"][-1]["id"] = "CQ01"

    with pytest.raises(SchemaCatalogError, match="Duplicate competency question"):
        validate_catalog(invalid)


def test_validate_catalog_rejects_unknown_competency_status(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["competency_questions"][0]["status"] = "partial"

    with pytest.raises(SchemaCatalogError, match="competency status"):
        validate_catalog(invalid)


@pytest.mark.parametrize("field", ["relations", "join_paths", "semantic_ids"])
def test_validate_catalog_rejects_unknown_competency_references(
    catalog: dict[str, object], field: str
) -> None:
    invalid = copy.deepcopy(catalog)
    invalid["competency_questions"][0][field] = ["missing"]

    with pytest.raises(SchemaCatalogError, match="competency reference"):
        validate_catalog(invalid)


def test_validate_catalog_requires_reason_for_non_supported_competency(
    catalog: dict[str, object],
) -> None:
    invalid = copy.deepcopy(catalog)
    question = next(
        item for item in invalid["competency_questions"] if item["status"] == "coverage_gap"
    )
    question["reason"] = ""

    with pytest.raises(SchemaCatalogError, match="reason"):
        validate_catalog(invalid)


def test_normalize_live_schema_converts_nested_bigquery_fields() -> None:
    table = SimpleNamespace(
        schema=[
            SimpleNamespace(name="address", field_type="STRING", mode="REQUIRED", fields=()),
            SimpleNamespace(
                name="sources",
                field_type="RECORD",
                mode="REPEATED",
                fields=(
                    SimpleNamespace(
                        name="revision", field_type="STRING", mode="REQUIRED", fields=()
                    ),
                ),
            ),
        ]
    )

    schema = normalize_live_schema(table)

    assert schema["address"] == LiveField("address", "STRING", "REQUIRED")
    assert schema["sources"].fields == (LiveField("revision", "STRING", "REQUIRED"),)


def test_validate_live_schemas_accepts_expected_and_extra_upstream_fields(
    catalog: dict[str, object],
) -> None:
    schemas = live_schemas_from_catalog(catalog)
    schemas["transactions"]["future_field"] = LiveField("future_field", "STRING", "NULLABLE")

    summary = validate_live_schemas(catalog, schemas)

    assert summary.checked_source_count == 5
    assert summary.deferred_source_count == 1
    assert summary.checked_field_count > 40


def test_validate_live_schemas_rejects_missing_live_source(
    catalog: dict[str, object],
) -> None:
    schemas = live_schemas_from_catalog(catalog)
    del schemas["transactions"]

    with pytest.raises(SchemaCatalogError, match="Missing live schema.*transactions"):
        validate_live_schemas(catalog, schemas)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "missing required field"),
        ("type", "type mismatch"),
        ("mode", "mode mismatch"),
    ],
)
def test_validate_live_schemas_rejects_required_field_drift(
    catalog: dict[str, object], mutation: str, message: str
) -> None:
    schemas = live_schemas_from_catalog(catalog)
    if mutation == "missing":
        del schemas["transactions"]["hash"]
    elif mutation == "type":
        schemas["transactions"]["hash"] = LiveField("hash", "BYTES", "REQUIRED")
    else:
        schemas["transactions"]["hash"] = LiveField("hash", "STRING", "NULLABLE")

    with pytest.raises(SchemaCatalogError, match=message):
        validate_live_schemas(catalog, schemas)


def test_validate_live_schemas_does_not_require_deferred_managed_source(
    catalog: dict[str, object],
) -> None:
    schemas = live_schemas_from_catalog(catalog)

    assert "entity_labels_v1" not in schemas
    assert validate_live_schemas(catalog, schemas).deferred_source_count == 1


def load_validate_sql_schema_script():
    script_path = Path("scripts/05_validate_sql_schema.py").resolve()
    spec = importlib.util.spec_from_file_location("validate_sql_schema_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def simple_field_from_live(field: LiveField) -> SimpleNamespace:
    return SimpleNamespace(
        name=field.name,
        field_type=field.field_type,
        mode=field.mode,
        fields=tuple(simple_field_from_live(child) for child in field.fields),
    )


class FakeMetadataClient:
    def __init__(
        self,
        catalog: dict[str, object],
        *,
        mutate_transactions: bool = False,
    ) -> None:
        self.project = "nl2sparql-thesis"
        self.requested_objects: list[str] = []
        self.tables: dict[str, SimpleNamespace] = {}
        for source in catalog["physical_sources"].values():
            if source["deployment_status"] != "live":
                continue
            fields = [
                simple_field_from_live(live_field_from_catalog(name, definition))
                for name, definition in source["fields"].items()
            ]
            if mutate_transactions and source["object"].endswith(".transactions"):
                fields = [field for field in fields if field.name != "hash"]
            self.tables[source["object"]] = SimpleNamespace(schema=fields, location="US")

    def get_table(self, object_name: str) -> SimpleNamespace:
        self.requested_objects.append(object_name)
        return self.tables[object_name]


def test_schema_cli_validates_catalog_offline_without_creating_client() -> None:
    script = load_validate_sql_schema_script()

    class ForbiddenClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("offline mode must not create a BigQuery client")

    script.bigquery.Client = ForbiddenClient
    result = CliRunner().invoke(script.main)

    assert result.exit_code == 0, result.output
    assert "sources=6" in result.output
    assert "relations=6" in result.output
    assert "joins=6" in result.output
    assert "competency_questions=30" in result.output
    assert "live_checked_sources" not in result.output


def test_schema_cli_fails_closed_for_invalid_catalog(tmp_path: Path) -> None:
    script = load_validate_sql_schema_script()
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(script.main, ["--catalog", str(invalid_path)])

    assert result.exit_code != 0
    assert "catalog_version" in result.output


def test_schema_cli_live_mode_reads_only_current_public_metadata(
    catalog: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load_validate_sql_schema_script()
    client = FakeMetadataClient(catalog)
    projects: list[str | None] = []

    def client_factory(*, project=None):
        projects.append(project)
        return client

    monkeypatch.setattr(script.bigquery, "Client", client_factory)
    result = CliRunner().invoke(script.main, ["--live", "--project", "nl2sparql-thesis"])

    assert result.exit_code == 0, result.output
    assert projects == ["nl2sparql-thesis"]
    assert len(client.requested_objects) == 5
    assert all("entity_labels_v1" not in name for name in client.requested_objects)
    assert "live_checked_sources=5" in result.output
    assert "live_deferred_sources=1" in result.output


def test_schema_cli_live_mode_exits_nonzero_on_schema_drift(
    catalog: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load_validate_sql_schema_script()
    client = FakeMetadataClient(catalog, mutate_transactions=True)
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: client)

    result = CliRunner().invoke(script.main, ["--live"])

    assert result.exit_code != 0
    assert "missing required field: transactions.hash" in result.output
