from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.linking.dictionary import ENTITIES_PATH
from nl2sparql.sql.label_layer import (
    DEFAULT_MAXIMUM_BYTES_BILLED,
    LABEL_TABLE_SCHEMA,
    DeploymentPlan,
    LabelLayerError,
    apply_deployment,
    apply_rollback,
    build_deployment_plan,
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

    assert snapshot.digest == ("cdc7856df81f2cce61290ef27a8872477f1b77da998a6aa88ca0ed75cc19617e")
    assert snapshot.table_name == "entity_labels_snapshot_cdc7856df81f"
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


class FakeJob:
    def __init__(self, rows=()) -> None:
        self.rows = rows

    def result(self):
        return self.rows


class FakeBigQueryClient:
    def __init__(
        self,
        *,
        dataset_exists: bool = False,
        snapshot_exists: bool = False,
        validation_overrides: dict[str, object] | None = None,
        dataset_location: str = "US",
        default_table_expiration_ms: int | None = None,
        default_partition_expiration_ms: int | None = None,
        server_default_after_create_ms: int | None = None,
        snapshot_expires: datetime | None = None,
    ) -> None:
        from google.api_core.exceptions import NotFound

        self.NotFound = NotFound
        self.calls: list[tuple[str, object]] = []
        self.dataset = (
            SimpleNamespace(
                location=dataset_location,
                default_table_expiration_ms=default_table_expiration_ms,
                default_partition_expiration_ms=default_partition_expiration_ms,
            )
            if dataset_exists
            else None
        )
        self.snapshot_exists = snapshot_exists
        self.server_default_after_create_ms = server_default_after_create_ms
        self.snapshot_expires = snapshot_expires
        self.validation_overrides = validation_overrides or {}
        self.loaded_rows: list[dict[str, object]] = []
        self.load_config = None

    def get_dataset(self, dataset_ref: str):
        self.calls.append(("get_dataset", dataset_ref))
        if self.dataset is None:
            raise self.NotFound("dataset missing")
        return self.dataset

    def create_dataset(self, dataset, *, exists_ok: bool = False):
        self.calls.append(("create_dataset", dataset.full_dataset_id))
        self.dataset = SimpleNamespace(
            location=dataset.location,
            default_table_expiration_ms=self.server_default_after_create_ms,
            default_partition_expiration_ms=self.server_default_after_create_ms,
        )
        return self.dataset

    def get_table(self, table_ref: str):
        self.calls.append(("get_table", table_ref))
        if not self.snapshot_exists:
            raise self.NotFound("table missing")
        return SimpleNamespace(
            schema=LABEL_TABLE_SCHEMA,
            location="US",
            expires=self.snapshot_expires,
        )

    def load_table_from_json(self, rows, destination: str, *, job_config, location: str):
        self.calls.append(("load_table_from_json", destination))
        self.loaded_rows = list(rows)
        self.load_config = job_config
        self.snapshot_exists = True
        if self.dataset.default_table_expiration_ms is not None:
            self.snapshot_expires = datetime(2026, 10, 8, tzinfo=UTC)
        return FakeJob()

    def query(self, sql: str, *, job_config, location: str):
        self.calls.append(("query", sql))
        if sql.lstrip().startswith("SELECT"):
            expected = {
                "entity_count": 5135,
                "unique_address_count": 5135,
                "operational_count": 14,
                "token_count": 5091,
                "treasury_count": 30,
                "digest_count": 1,
                "dictionary_sha256": (
                    "cdc7856df81f2cce61290ef27a8872477f1b77da998a6aa88ca0ed75cc19617e"
                ),
            }
            expected.update(self.validation_overrides)
            return FakeJob([SimpleNamespace(**expected)])
        return FakeJob()


def test_build_deployment_plan_is_deterministic_and_side_effect_free() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis")

    assert isinstance(plan, DeploymentPlan)
    assert plan.dataset == "nl2sparql_analytics"
    assert plan.location == "US"
    assert plan.maximum_bytes_billed == DEFAULT_MAXIMUM_BYTES_BILLED
    assert plan.allow_expiring_objects is False
    assert plan.snapshot.table_name == "entity_labels_snapshot_cdc7856df81f"
    assert len(plan.sql_objects) == 8


def test_apply_deployment_creates_durable_dataset_then_validates_before_view_swap() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis")
    client = FakeBigQueryClient()

    result = apply_deployment(plan, client)

    operation_names = [call[0] for call in client.calls]
    assert operation_names[:5] == [
        "get_dataset",
        "create_dataset",
        "get_dataset",
        "get_table",
        "load_table_from_json",
    ]
    validation_index = next(
        index
        for index, call in enumerate(client.calls)
        if call[0] == "query" and str(call[1]).lstrip().startswith("SELECT")
    )
    view_swap_index = next(
        index
        for index, call in enumerate(client.calls)
        if call[0] == "query" and "CREATE OR REPLACE VIEW" in str(call[1])
    )
    assert validation_index < view_swap_index
    assert client.load_config.write_disposition == "WRITE_EMPTY"
    assert client.load_config.create_disposition == "CREATE_IF_NEEDED"
    assert tuple(client.load_config.schema) == LABEL_TABLE_SCHEMA
    assert len(client.loaded_rows) == 5135
    assert result.created_dataset is True
    assert result.snapshot_action == "loaded"
    assert result.snapshot_expires is None
    assert result.deployed_objects == tuple(obj.name for obj in plan.sql_objects)


@pytest.mark.parametrize(
    ("client", "message"),
    [
        (
            FakeBigQueryClient(dataset_exists=True, dataset_location="EU"),
            "location",
        ),
        (
            FakeBigQueryClient(dataset_exists=True, default_table_expiration_ms=86_400_000),
            "default table expiration",
        ),
        (
            FakeBigQueryClient(dataset_exists=True, default_partition_expiration_ms=86_400_000),
            "default partition expiration",
        ),
    ],
)
def test_apply_deployment_fails_closed_for_incompatible_dataset(
    client: FakeBigQueryClient, message: str
) -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis")

    with pytest.raises(LabelLayerError, match=message):
        apply_deployment(plan, client)

    assert all(call[0] != "load_table_from_json" for call in client.calls)


def test_same_digest_deployment_reuses_existing_snapshot_idempotently() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis")
    client = FakeBigQueryClient(dataset_exists=True, snapshot_exists=True)

    result = apply_deployment(plan, client)

    assert result.created_dataset is False
    assert result.snapshot_action == "reused"
    assert all(call[0] != "load_table_from_json" for call in client.calls)


def test_server_applied_sandbox_expiration_fails_closed_after_dataset_create() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis")
    client = FakeBigQueryClient(server_default_after_create_ms=5_184_000_000)

    with pytest.raises(LabelLayerError, match="default table expiration"):
        apply_deployment(plan, client)

    assert [call[0] for call in client.calls][:3] == [
        "get_dataset",
        "create_dataset",
        "get_dataset",
    ]
    assert all(call[0] != "load_table_from_json" for call in client.calls)


def test_explicit_sandbox_mode_accepts_only_known_60_day_policy_and_records_expiry() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis", allow_expiring_objects=True)
    expiry = datetime(2026, 10, 8, tzinfo=UTC)
    client = FakeBigQueryClient(
        dataset_exists=True,
        snapshot_exists=True,
        default_table_expiration_ms=5_184_000_000,
        default_partition_expiration_ms=5_184_000_000,
        snapshot_expires=expiry,
    )

    result = apply_deployment(plan, client)

    assert result.dataset_default_expiration_ms == 5_184_000_000
    assert result.snapshot_expires == expiry


def test_sandbox_mode_rejects_an_unexpected_expiration_policy() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis", allow_expiring_objects=True)
    client = FakeBigQueryClient(
        dataset_exists=True,
        default_table_expiration_ms=86_400_000,
        default_partition_expiration_ms=86_400_000,
    )

    with pytest.raises(LabelLayerError, match="60-day sandbox"):
        apply_deployment(plan, client)


def test_snapshot_validation_mismatch_fails_before_stable_view_swap() -> None:
    plan = build_deployment_plan(project="nl2sparql-thesis")
    client = FakeBigQueryClient(validation_overrides={"unique_address_count": 5134})

    with pytest.raises(LabelLayerError, match="unique_address_count"):
        apply_deployment(plan, client)

    assert all(
        not (call[0] == "query" and "CREATE OR REPLACE VIEW" in str(call[1]))
        for call in client.calls
    )


def test_rollback_validates_named_snapshot_then_only_repoints_view() -> None:
    snapshot = build_label_snapshot()
    client = FakeBigQueryClient(dataset_exists=True, snapshot_exists=True)

    apply_rollback(
        project="nl2sparql-thesis",
        dataset="nl2sparql_analytics",
        snapshot=snapshot,
        client=client,
    )

    queries = [str(call[1]) for call in client.calls if call[0] == "query"]
    assert queries[0].lstrip().startswith("SELECT")
    assert len(queries) == 2
    assert queries[1].startswith("CREATE OR REPLACE VIEW")
    assert all("DROP " not in sql and "DELETE " not in sql for sql in queries)


def load_deploy_script():
    script_path = Path("scripts/06_deploy_sql_label_layer.py").resolve()
    spec = importlib.util.spec_from_file_location("deploy_sql_label_layer_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deploy_cli_defaults_to_plan_only_without_creating_client() -> None:
    from click.testing import CliRunner

    script = load_deploy_script()

    class ForbiddenClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("plan-only mode must not create a BigQuery client")

    script.bigquery.Client = ForbiddenClient
    result = CliRunner().invoke(script.main, ["--project", "nl2sparql-thesis"])

    assert result.exit_code == 0, result.output
    assert "mode=plan" in result.output
    assert "snapshot=entity_labels_snapshot_cdc7856df81f" in result.output
    assert "entities=5135" in result.output
    assert "objects=8" in result.output


def test_deploy_cli_requires_explicit_apply_before_remote_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    script = load_deploy_script()
    client = FakeBigQueryClient()
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: client)

    result = CliRunner().invoke(script.main, ["--project", "nl2sparql-thesis", "--apply"])

    assert result.exit_code == 0, result.output
    assert "mode=apply" in result.output
    assert "snapshot_action=loaded" in result.output
    assert "deployed_objects=8" in result.output


def test_deploy_cli_exposes_expiring_sandbox_mode_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    script = load_deploy_script()
    client = FakeBigQueryClient(
        dataset_exists=True,
        snapshot_exists=True,
        default_table_expiration_ms=5_184_000_000,
        default_partition_expiration_ms=5_184_000_000,
        snapshot_expires=datetime(2026, 10, 8, tzinfo=UTC),
    )
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: client)

    result = CliRunner().invoke(
        script.main,
        [
            "--project",
            "nl2sparql-thesis",
            "--apply",
            "--allow-sandbox-expiration",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "expiration_policy=sandbox-60-day" in result.output
    assert "dataset_default_expiration_ms=5184000000" in result.output
    assert "snapshot_expires=2026-10-08" in result.output
