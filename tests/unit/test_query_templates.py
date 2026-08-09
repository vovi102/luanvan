"""Tests for the active T3.1 GoogleSQL query template library."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from nl2sparql.dataset.templates.validate import (
    TEMPLATES_PATH,
    TemplateValidationError,
    load_templates,
    render_template,
    validate_template_library,
)

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
