"""Tests for the T3.1 SPARQL query template library."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_PATH = ROOT / "src/nl2sparql/dataset/templates/templates.json"
README_PATH = ROOT / "src/nl2sparql/dataset/templates/README.md"
NOTEBOOK_PATH = ROOT / "notebooks/07_template_validate.ipynb"
SUPPORTED_DIFFICULTIES = {"easy", "medium", "hard"}
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


def _load_templates() -> list[dict]:
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))


def _format_fields(text: str) -> set[str]:
    return set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", text))


def test_template_library_has_required_count_and_unique_ids() -> None:
    templates = _load_templates()
    ids = [template["id"] for template in templates]

    assert len(templates) >= 25
    assert len(ids) == len(set(ids))
    assert all(identifier.startswith("T_") for identifier in ids)


def test_template_library_meets_distribution_targets() -> None:
    templates = _load_templates()
    difficulty_counts = Counter(template["difficulty"] for template in templates)
    category_counts = Counter(template["category"] for template in templates)
    total = len(templates)

    assert set(difficulty_counts) <= SUPPORTED_DIFFICULTIES
    assert set(category_counts) <= SUPPORTED_CATEGORIES
    assert difficulty_counts["easy"] / total >= 0.30
    assert difficulty_counts["medium"] / total >= 0.40
    assert difficulty_counts["hard"] / total >= 0.20
    assert len(category_counts) >= 6


def test_each_template_has_valid_schema_and_placeholder_fill() -> None:
    templates = _load_templates()
    required_fields = {
        "id",
        "name",
        "category",
        "difficulty",
        "slots",
        "sparql_template",
        "nl_seed",
        "expected_columns",
        "ontology_elements",
        "example_fill",
    }

    for template in templates:
        assert required_fields <= set(template), template["id"]
        assert template["difficulty"] in SUPPORTED_DIFFICULTIES
        assert template["category"] in SUPPORTED_CATEGORIES
        assert template["slots"]
        assert template["expected_columns"]
        assert template["ontology_elements"]
        slot_names = set(template["slots"])
        placeholders = _format_fields(template["sparql_template"]) | _format_fields(
            template["nl_seed"]
        )
        assert placeholders <= slot_names, template["id"]
        assert placeholders <= set(template["example_fill"]), template["id"]
        template["sparql_template"].format(**template["example_fill"])
        template["nl_seed"].format(**template["example_fill"])
        assert all(element.startswith(":") for element in template["ontology_elements"])


def test_select_templates_project_expected_columns() -> None:
    for template in _load_templates():
        query = template["sparql_template"]
        if query.lstrip().upper().startswith("ASK"):
            assert template["expected_columns"] == ["ask"]
            continue
        select_head = query.split("WHERE", 1)[0]
        for column in template["expected_columns"]:
            assert f"?{column}" in select_head, template["id"]


def test_template_readme_documents_schema_and_slot_types() -> None:
    text = README_PATH.read_text(encoding="utf-8")

    assert "Template schema" in text
    assert "Slot types" in text
    assert "example_fill" in text
    assert "Fuseki" in text


def test_template_validation_notebook_is_unexecuted_and_references_artifacts() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    source = "\n".join("".join(cell["source"]) for cell in code_cells)

    assert "templates.json" in source
    assert "SPARQLWrapper" in source
    assert "example_fill" in source
    assert all(cell.get("execution_count") is None for cell in code_cells)
    assert all(cell.get("outputs") == [] for cell in code_cells)
