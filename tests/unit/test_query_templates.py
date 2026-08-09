"""Tests for the active T3.1 GoogleSQL query template library."""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from nl2sparql.dataset.templates.validate import (
    TEMPLATES_PATH,
    TemplateExecutionReport,
    TemplatePreflight,
    TemplateValidationError,
    dry_run_templates,
    execute_templates,
    load_templates,
    render_template,
    validate_template_library,
)

PER_TEMPLATE_BYTES_CAP = 5_368_709_120

ROOT = Path(__file__).resolve().parents[2]
README_PATH = ROOT / "src/nl2sparql/dataset/templates/README.md"
NOTEBOOK_PATH = ROOT / "notebooks/07_template_validate.ipynb"
EXPECTED_IDS = (
    "T_COUNT_TX_IN_RANGE",
    "T_LIST_TX_FROM_ACCOUNT",
    "T_LIST_TX_TO_ACCOUNT",
    "T_FILTER_TX_BY_VALUE",
    "T_LIST_FAILED_TX",
    "T_BLOCK_BY_NUMBER",
    "T_TX_BY_HASH",
    "T_LIST_KNOWN_EXCHANGES",
    "T_TOP_SENDERS_BY_VALUE",
    "T_TOP_RECIPIENTS_BY_COUNT",
    "T_TX_BETWEEN_ACCOUNTS",
    "T_TX_GROUPED_BY_OWNER",
    "T_TOKEN_VOLUME_BY_SYMBOL",
    "T_TOKEN_TRANSFERS_OF_TOKEN",
    "T_FAILED_HIGH_GAS_TX",
    "T_BLOCKS_BY_VALIDATOR",
    "T_ACCOUNTS_BY_CATEGORY",
    "T_TX_BY_HOUR",
    "T_LARGE_TX_TO_CLASS",
    "T_EXCHANGE_TO_DEX_FLOW",
    "T_MIXER_TO_DEX_LARGE_FLOW",
    "T_TOKEN_AFTER_NATIVE_FUNDING",
    "T_CROSS_EXCHANGE_FLOW",
    "T_BRIDGE_OUTFLOW_AFTER_EXCHANGE",
    "T_REPEATED_PAIR_FLOW",
)
SUPPORTED_CATEGORIES = {
    "simple_filter",
    "time_range",
    "entity_lookup",
    "transaction_aggregation",
    "top_k",
    "multi_hop",
    "class_level",
    "token_specific",
    "comparison",
    "temporal_pattern",
}


@pytest.fixture(scope="module")
def templates() -> list[dict[str, object]]:
    return load_templates()


def test_template_library_is_exactly_the_migrated_stable_taxonomy(
    templates: list[dict[str, object]],
) -> None:
    summary = validate_template_library(templates)

    assert TEMPLATES_PATH.name == "templates.json"
    assert tuple(template["id"] for template in templates) == EXPECTED_IDS
    assert summary.template_count == 25
    assert summary.category_count == 10
    assert summary.difficulty_counts == {"easy": 8, "medium": 11, "hard": 6}


def test_template_library_preserves_approved_distribution(
    templates: list[dict[str, object]],
) -> None:
    difficulties = Counter(template["difficulty"] for template in templates)
    categories = Counter(template["category"] for template in templates)

    assert difficulties == {"medium": 11, "easy": 8, "hard": 6}
    assert set(categories) == SUPPORTED_CATEGORIES


def test_every_template_uses_contract_v2_without_legacy_sparql_fields(
    templates: list[dict[str, object]],
) -> None:
    required = {
        "id",
        "name",
        "category",
        "difficulty",
        "slots",
        "sql_template",
        "nl_seed",
        "expected_columns",
        "schema_elements",
        "cq_ids",
        "example_fill",
        "validation",
    }
    for template in templates:
        assert set(template) == required, template["id"]
        assert "sparql_template" not in template
        assert "ontology_elements" not in template
        assert template["cq_ids"]
        assert template["schema_elements"]
        assert "CQ24" not in template["cq_ids"]


def test_rendered_examples_are_safe_bounded_managed_googlesql(
    templates: list[dict[str, object]],
) -> None:
    for template in templates:
        sql = render_template(template)
        assert sql.lstrip().upper().startswith(("SELECT", "WITH")), template["id"]
        assert not re.search(
            r"\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE)\b",
            sql,
            re.IGNORECASE,
        )
        assert re.search(r"SELECT\s+\*", sql, re.IGNORECASE) is None
        assert "bigquery-public-data" not in sql
        assert "nl2sparql-thesis.nl2sparql_analytics" in sql
        assert not re.search(r"{[A-Za-z_]", sql)
        assert all(column in sql for column in template["expected_columns"])
        if any(
            marker in sql
            for marker in (
                "transaction_facts`(",
                "block_facts`(",
                "labeled_transactions`(",
                "labeled_token_transfers`(",
            )
        ):
            assert "DATE '2026-06-15'" in sql
            assert "DATE '2026-06-16'" in sql


def test_schema_and_cq_references_resolve_against_analytical_catalog(
    templates: list[dict[str, object]],
) -> None:
    summary = validate_template_library(templates)

    assert summary.schema_element_count >= 30
    assert summary.cq_count >= 20


@pytest.mark.parametrize(
    ("slot", "value", "message"),
    [
        ("account", "0xnot-an-address", "ethereum_address"),
        ("start_date", "2026-06-99", "date"),
        ("n", 1001, "integer"),
    ],
)
def test_renderer_fails_closed_for_invalid_slot_values(
    templates: list[dict[str, object]], slot: str, value: object, message: str
) -> None:
    template = next(template for template in templates if slot in template["slots"])
    values = dict(template["example_fill"])
    values[slot] = value

    with pytest.raises(TemplateValidationError, match=message):
        render_template(template, values)


def test_renderer_rejects_reversed_or_overlong_fact_windows(
    templates: list[dict[str, object]],
) -> None:
    template = templates[0]
    values = dict(template["example_fill"])
    values.update(start_date="2026-06-16", end_date="2026-06-15")
    with pytest.raises(TemplateValidationError, match="date window"):
        render_template(template, values)

    values.update(start_date="2026-05-01", end_date="2026-06-15")
    with pytest.raises(TemplateValidationError, match="31 days"):
        render_template(template, values)


def test_readme_documents_only_active_googlesql_contract() -> None:
    text = README_PATH.read_text(encoding="utf-8")

    for phrase in (
        "Template contract v2",
        "GoogleSQL",
        "Slot types",
        "sql_template",
        "schema_elements",
        "BigQuery",
        "table-valued functions",
    ):
        assert phrase in text
    assert "SPARQL template" not in text
    assert "Fuseki" not in text


def test_template_validation_notebook_is_unexecuted_and_uses_bigquery_cli() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    source = "\n".join("".join(cell["source"]) for cell in code_cells)

    assert "templates.json" in source
    assert "08_validate_sql_templates.py" in source
    assert "sql_template" in source
    assert "SPARQLWrapper" not in source
    assert "Fuseki" not in source
    assert all(cell.get("execution_count") is None for cell in code_cells)
    assert all(cell.get("outputs") == [] for cell in code_cells)


def test_date_slot_examples_are_iso_dates(templates: list[dict[str, object]]) -> None:
    for template in templates:
        for name, definition in template["slots"].items():
            if definition["type"] == "date":
                date.fromisoformat(template["example_fill"][name])


class FakeTemplateRows(list):
    def __init__(self, rows: list[object], columns: list[str]) -> None:
        super().__init__(rows)
        self.schema = [SimpleNamespace(name=column) for column in columns]


class FakeTemplateJob:
    def __init__(
        self,
        *,
        estimated_bytes: int = 0,
        rows: FakeTemplateRows | None = None,
    ) -> None:
        self.total_bytes_processed = estimated_bytes
        self.total_bytes_billed = estimated_bytes
        self.slot_millis = 125
        self.cache_hit = False
        self.started = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        self.ended = self.started + timedelta(milliseconds=75)
        self._rows = rows

    def result(self) -> FakeTemplateRows:
        assert self._rows is not None
        return self._rows


class FakeTemplateClient:
    def __init__(
        self,
        templates: list[dict[str, object]],
        *,
        estimates: dict[str, int] | None = None,
        result_overrides: dict[str, FakeTemplateRows] | None = None,
    ) -> None:
        self.templates = templates
        self.rendered_to_template = {render_template(template): template for template in templates}
        self.estimates = estimates or {
            template["id"]: (index + 1) * 1_000_000 for index, template in enumerate(templates)
        }
        self.result_overrides = result_overrides or {}
        self.calls: list[tuple[str, str, object, str]] = []

    def query(self, sql: str, *, job_config, location: str) -> FakeTemplateJob:
        template = self.rendered_to_template[sql]
        template_id = template["id"]
        mode = "dry_run" if job_config.dry_run else "execute"
        self.calls.append((mode, template_id, job_config, location))
        estimate = self.estimates[template_id]
        if job_config.dry_run:
            return FakeTemplateJob(estimated_bytes=estimate)
        columns = list(template["expected_columns"])
        rows = self.result_overrides.get(
            template_id,
            FakeTemplateRows(
                [SimpleNamespace(**{column: 1 for column in columns})],
                columns,
            ),
        )
        return FakeTemplateJob(estimated_bytes=estimate, rows=rows)


def test_live_preflight_dry_runs_all_templates_with_strict_budgets(
    templates: list[dict[str, object]],
) -> None:
    client = FakeTemplateClient(templates)

    preflight = dry_run_templates(client, templates=templates)

    assert isinstance(preflight, TemplatePreflight)
    assert tuple(item.template_id for item in preflight.templates) == EXPECTED_IDS
    assert preflight.total_estimated_bytes == 325_000_000
    assert len(client.calls) == 25
    for mode, _, config, location in client.calls:
        assert mode == "dry_run"
        assert location == "US"
        assert config.dry_run is True
        assert config.use_query_cache is False
        assert config.use_legacy_sql is False
        assert config.maximum_bytes_billed == PER_TEMPLATE_BYTES_CAP


def test_live_preflight_rejects_per_template_or_aggregate_overflow(
    templates: list[dict[str, object]],
) -> None:
    per_template = {template["id"]: 1 for template in templates}
    per_template[templates[3]["id"]] = PER_TEMPLATE_BYTES_CAP + 1
    with pytest.raises(TemplateValidationError, match="T_FILTER_TX_BY_VALUE.*5 GiB"):
        dry_run_templates(
            FakeTemplateClient(templates, estimates=per_template),
            templates=templates,
        )

    aggregate = {template["id"]: 1_300_000_000 for template in templates}
    client = FakeTemplateClient(templates, estimates=aggregate)
    with pytest.raises(TemplateValidationError, match="aggregate.*30 GiB"):
        execute_templates(client, templates=templates)
    assert all(mode == "dry_run" for mode, *_ in client.calls)


def test_execute_redry_runs_and_records_schema_cardinality_and_metrics(
    templates: list[dict[str, object]],
) -> None:
    client = FakeTemplateClient(templates)
    ticks = iter(index * 1_000_000 for index in range(50))

    report = execute_templates(
        client,
        templates=templates,
        clock_ns=lambda: next(ticks),
    )

    assert isinstance(report, TemplateExecutionReport)
    assert report.all_passed is True
    assert len(report.results) == 25
    assert [mode for mode, *_ in client.calls] == ["dry_run"] * 25 + [
        mode for _ in templates for mode in ("dry_run", "execute")
    ]
    first = report.results[0]
    assert first.template_id == EXPECTED_IDS[0]
    assert first.row_count == 1
    assert first.columns == tuple(templates[0]["expected_columns"])
    assert first.estimated_bytes == 1_000_000
    assert first.processed_bytes == 1_000_000
    assert first.billed_bytes == 1_000_000
    assert first.wall_latency_ms == 1.0
    assert first.server_latency_ms == 75.0
    assert first.slot_millis == 125
    assert first.cache_hit is False


def test_execute_fails_closed_for_missing_columns_or_required_rows(
    templates: list[dict[str, object]],
) -> None:
    required = next(
        template for template in templates if template["validation"]["expect_non_empty"]
    )
    required_id = required["id"]
    empty = FakeTemplateRows([], list(required["expected_columns"]))
    with pytest.raises(TemplateValidationError, match=f"{required_id}.*non-empty"):
        execute_templates(
            FakeTemplateClient(templates, result_overrides={required_id: empty}),
            templates=templates,
        )

    first_id = templates[0]["id"]
    wrong_schema = FakeTemplateRows([SimpleNamespace(wrong=1)], ["wrong"])
    with pytest.raises(TemplateValidationError, match=f"{first_id}.*columns"):
        execute_templates(
            FakeTemplateClient(templates, result_overrides={first_id: wrong_schema}),
            templates=templates,
        )


def load_template_validation_script():
    script_path = Path("scripts/08_validate_sql_templates.py").resolve()
    spec = importlib.util.spec_from_file_location("validate_sql_templates_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_defaults_to_offline_without_constructing_bigquery_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_template_validation_script()

    class ForbiddenClient:
        def __init__(self, **_: object) -> None:
            raise AssertionError("offline mode must not construct a client")

    monkeypatch.setattr(script.bigquery, "Client", ForbiddenClient)
    result = CliRunner().invoke(script.main)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "offline"
    assert payload["template_count"] == 25


def test_cli_live_dry_runs_and_execute_requires_explicit_flag(
    monkeypatch: pytest.MonkeyPatch, templates: list[dict[str, object]]
) -> None:
    script = load_template_validation_script()
    dry_client = FakeTemplateClient(templates)
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: dry_client)
    result = CliRunner().invoke(script.main, ["--live"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "dry-run"
    assert all(mode == "dry_run" for mode, *_ in dry_client.calls)

    execute_client = FakeTemplateClient(templates)
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: execute_client)
    result = CliRunner().invoke(script.main, ["--execute"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "execute"
    assert payload["all_passed"] is True
    assert sum(mode == "execute" for mode, *_ in execute_client.calls) == 25
