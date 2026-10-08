from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.dataset.bilingual.contracts import TEMPLATES_PATH, CatalogEntry, load_catalog
from nl2sparql.dataset.bilingual.rendering import (
    RENDERER_VERSION,
    RenderingValidationError,
    diversity_report,
    expand_stage_a,
    expanded_record_digest,
    render_pattern,
    serialize_records,
    validate_expansion,
)
from nl2sparql.dataset.templates.validate import load_templates

STAGE_A_PATH = Path("data/dataset/raw/synthetic-stage-a.jsonl")


def _entry(pattern: str, placeholders: tuple[str, ...]) -> CatalogEntry:
    return CatalogEntry(
        id="fixture__vi__formal",
        template_id="fixture",
        language="vi",
        style="formal",
        pattern=pattern,
        placeholders=placeholders,
        author_type="agent",
        review_type="agent-reviewed",
        catalog_schema_version="1.0.0",
        content_sha256="a" * 64,
    )


@pytest.fixture(scope="module")
def templates() -> list[dict[str, object]]:
    return load_templates()


@pytest.fixture(scope="module")
def stage_a() -> list[dict[str, object]]:
    return [json.loads(line) for line in STAGE_A_PATH.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def expanded(stage_a: list[dict[str, object]], templates: list[dict[str, object]]):
    return expand_stage_a(stage_a, load_catalog(TEMPLATES_PATH, templates), templates)


def test_render_pattern_binds_typed_values_and_preserves_utf8_exactly() -> None:
    entry = _entry(
        "Liệt kê {n} lượt chuyển {token_symbol} từ {account} vào {start_date}; "
        "tx {transaction_hash}.",
        ("account", "n", "start_date", "token_symbol", "transaction_hash"),
    )
    values = {
        "n": 7,
        "token_symbol": "USDC",
        "account": "0x0d0707963952f2fba59dd06f2b425ace40b492fe",
        "start_date": "2026-06-15",
        "transaction_hash": "0x" + "f" * 64,
    }

    assert render_pattern(entry, values) == (
        "Liệt kê 7 lượt chuyển USDC từ "
        "0x0d0707963952f2fba59dd06f2b425ace40b492fe vào 2026-06-15; tx 0x" + "f" * 64 + "."
    )


def test_render_pattern_treats_braces_inside_slot_values_as_literal_text() -> None:
    entry = _entry("Look up {token_symbol}.", ("token_symbol",))

    assert render_pattern(entry, {"token_symbol": "TOKEN{literal}"}) == ("Look up TOKEN{literal}.")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"start_date": "2026-06-15"}, "missing"),
        (
            {"start_date": "2026-06-15", "end_date": "2026-06-16", "extra": 1},
            "extra",
        ),
        ({"start_date": "", "end_date": "2026-06-16"}, "non-empty"),
    ],
)
def test_render_pattern_rejects_missing_extra_or_empty_slots(
    values: dict[str, object], message: str
) -> None:
    entry = _entry("From {start_date} to {end_date}?", ("end_date", "start_date"))

    with pytest.raises(RenderingValidationError, match=message):
        render_pattern(entry, values)


def test_render_pattern_rejects_duplicate_or_undeclared_fields() -> None:
    duplicate = _entry("{n} plus {n}", ("n",))
    undeclared = replace(duplicate, pattern="{n} plus {other}")

    with pytest.raises(RenderingValidationError, match="repeated"):
        render_pattern(duplicate, {"n": 1})
    with pytest.raises(RenderingValidationError, match="placeholder"):
        render_pattern(undeclared, {"n": 1})


def test_full_expansion_has_exact_balanced_counts_and_unique_identity(
    expanded,
    stage_a: list[dict[str, object]],
) -> None:
    assert len(stage_a) == 1000
    assert len(expanded) == 8000
    assert Counter(record.language for record in expanded) == {"en": 4000, "vi": 4000}
    assert Counter(record.style for record in expanded) == {
        "formal": 2000,
        "conversational": 2000,
        "abbreviated": 2000,
        "alternative": 2000,
    }
    families = Counter(record.semantic_family_id for record in expanded)
    assert len(families) == 1000
    assert set(families.values()) == {8}
    assert len({record.id for record in expanded}) == 8000
    assert len({record.normalized_question for record in expanded}) == 8000

    source_counts = Counter(record["template_id"] for record in stage_a)
    expanded_counts = Counter(record.catalog_entry_id.split("__", 1)[0] for record in expanded)
    assert expanded_counts == {
        template_id: count * 8 for template_id, count in source_counts.items()
    }


def test_expansion_preserves_semantics_and_uses_honest_zero_cost_provenance(
    expanded,
    stage_a: list[dict[str, object]],
    templates: list[dict[str, object]],
) -> None:
    sources = {record["id"]: record for record in stage_a}
    template_index = {template["id"]: template for template in templates}
    for record in expanded:
        source = sources[record.source_record_id]
        template = template_index[source["template_id"]]
        assert record.semantic_family_id == source["id"]
        assert record.source_record_sha256 == source["record_sha256"]
        assert record.source_template_sha256 == source["template_sha256"]
        assert record.sql == source["sql"]
        assert dict(record.slot_values) == source["slot_values"]
        assert record.expected_columns == tuple(template["expected_columns"])
        assert record.schema_elements == tuple(source["schema_elements"])
        assert [dict(entity) for entity in record.entities_used] == source["entities_used"]
        assert record.semantic_anchors == record.slot_values
        assert record.renderer_version == RENDERER_VERSION
        assert record.split == "unassigned"
        assert record.producer_type == "deterministic_template_renderer"
        assert record.author_type == "agent"
        assert record.review_type == "agent-reviewed"
        assert record.generation_model is None
        assert record.provider is None
        assert record.api_request_count == 0
        assert record.recorded_cost_usd == 0.0
        assert record.record_sha256 == expanded_record_digest(record)


def test_expansion_and_serialization_are_stable_under_input_order(
    expanded,
    stage_a: list[dict[str, object]],
    templates: list[dict[str, object]],
) -> None:
    catalog = load_catalog(TEMPLATES_PATH, templates)
    reversed_catalog = replace(catalog, entries=tuple(reversed(catalog.entries)))
    reordered = expand_stage_a(list(reversed(stage_a)), reversed_catalog, list(reversed(templates)))

    assert reordered == expanded
    assert serialize_records(reordered) == serialize_records(expanded)
    assert serialize_records(expanded).endswith(b"\n")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sql", "SELECT 1", "sql"),
        ("slot_values", (("start_date", "1999-01-01"),), "slot"),
        ("expected_columns", ("wrong",), "expected columns"),
        ("schema_elements", ("wrong.element",), "schema"),
        ("entities_used", (), "entities"),
        ("semantic_anchors", (("wrong", 1),), "semantic anchors"),
        ("source_record_sha256", "0" * 64, "source record"),
        ("source_template_sha256", "0" * 64, "template"),
    ],
)
def test_validation_rejects_each_immutable_semantic_field_mutation(
    expanded,
    stage_a: list[dict[str, object]],
    templates: list[dict[str, object]],
    field: str,
    value: object,
    message: str,
) -> None:
    index = next(index for index, record in enumerate(expanded) if record.entities_used)
    tampered = list(expanded)
    tampered[index] = replace(tampered[index], **{field: value})

    with pytest.raises(RenderingValidationError, match=message):
        validate_expansion(tampered, stage_a, templates)


def test_validation_rejects_record_digest_normalized_question_and_duplicate_ids(
    expanded,
    stage_a: list[dict[str, object]],
    templates: list[dict[str, object]],
) -> None:
    for field, value, message in (
        ("record_sha256", "0" * 64, "record digest"),
        ("normalized_question", "wrong", "normalized"),
        ("id", expanded[1].id, "unique record IDs"),
    ):
        tampered = list(expanded)
        tampered[0] = replace(tampered[0], **{field: value})
        with pytest.raises(RenderingValidationError, match=message):
            validate_expansion(tampered, stage_a, templates)


def test_every_family_language_exceeds_strict_diversity_gate(expanded) -> None:
    report = diversity_report(expanded)

    assert report.family_language_count == 2000
    assert report.failing_family_ids == ()
    assert report.minimum > 0.30
    assert report.minimum <= report.p25 <= report.median <= report.p75 <= report.maximum
    assert report.minimum <= report.mean <= report.maximum

    with pytest.raises(RenderingValidationError, match="strictly greater"):
        diversity_report(expanded, threshold=report.minimum)
