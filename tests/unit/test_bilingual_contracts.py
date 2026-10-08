from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from nl2sparql.dataset.bilingual.contracts import (
    CATALOG_SCHEMA_VERSION,
    TEMPLATES_PATH,
    AuditEvent,
    AuditSummary,
    Catalog,
    CatalogEntry,
    CatalogValidationError,
    ExclusionIndex,
    ExpandedTrainingRecord,
    SplitConfig,
    catalog_entry_digest,
    load_catalog,
)
from nl2sparql.dataset.templates.validate import load_templates


def _document(entry: dict[str, object]) -> dict[str, object]:
    return {"schema_version": CATALOG_SCHEMA_VERSION, "entries": [entry]}


def _entry(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "T_COUNT_TX_IN_RANGE__en__formal",
        "template_id": "T_COUNT_TX_IN_RANGE",
        "language": "en",
        "style": "formal",
        "pattern": "How many transactions occurred from {start_date} through {end_date}?",
        "placeholders": ["end_date", "start_date"],
        "author_type": "agent",
        "review_type": "agent-reviewed",
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
    }
    body.update(overrides)
    body["content_sha256"] = catalog_entry_digest(body)
    return body


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def test_public_contracts_are_frozen_and_have_exact_fields() -> None:
    expected = {
        CatalogEntry: (
            "id",
            "template_id",
            "language",
            "style",
            "pattern",
            "placeholders",
            "author_type",
            "review_type",
            "catalog_schema_version",
            "content_sha256",
        ),
        Catalog: ("schema_version", "entries"),
        ExpandedTrainingRecord: (
            "id",
            "language",
            "style",
            "semantic_family_id",
            "catalog_entry_id",
            "catalog_entry_sha256",
            "source_record_id",
            "source_record_sha256",
            "source_template_sha256",
            "renderer_version",
            "question",
            "normalized_question",
            "sql",
            "slot_values",
            "expected_columns",
            "schema_elements",
            "entities_used",
            "semantic_anchors",
            "split",
            "producer_type",
            "author_type",
            "review_type",
            "generation_model",
            "provider",
            "api_request_count",
            "recorded_cost_usd",
            "record_sha256",
        ),
        SplitConfig: ("seed", "development_percent"),
        ExclusionIndex: (
            "schema_version",
            "ngram_size",
            "source_sha256s",
            "source_record_counts",
            "normalized_text_sha256s",
            "ngram_sha256s",
            "index_sha256",
        ),
        AuditEvent: (
            "schema_version",
            "event_id",
            "record_id",
            "record_sha256",
            "decision",
            "faithful",
            "natural",
            "notes",
            "reviewer_type",
            "reviewed_at",
            "supersedes_event_id",
        ),
        AuditSummary: (
            "language",
            "sample_size",
            "faithful_count",
            "natural_count",
            "accepted_count",
            "passed",
        ),
    }
    for contract, names in expected.items():
        assert tuple(field.name for field in fields(contract)) == names

    entry = CatalogEntry(**_entry())
    with pytest.raises(FrozenInstanceError):
        entry.style = "alternative"  # type: ignore[misc]


def test_catalog_entry_digest_is_canonical_and_detects_tampering() -> None:
    entry = _entry()
    digest = entry["content_sha256"]
    assert digest == catalog_entry_digest(dict(reversed(tuple(entry.items()))))
    assert digest == hashlib.sha256(
        json.dumps(
            {key: value for key, value in entry.items() if key != "content_sha256"},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    assert digest != catalog_entry_digest(entry | {"pattern": "Changed {start_date} {end_date}"})


def test_canonical_catalog_has_exact_coverage_and_provenance() -> None:
    templates = load_templates()
    catalog = load_catalog(TEMPLATES_PATH, templates)

    assert catalog.schema_version == CATALOG_SCHEMA_VERSION
    assert len(catalog.entries) == 200
    assert len({entry.id for entry in catalog.entries}) == 200
    assert {entry.template_id for entry in catalog.entries} == {
        template["id"] for template in templates
    }
    assert {entry.language for entry in catalog.entries} == {"en", "vi"}
    assert {entry.style for entry in catalog.entries} == {
        "formal",
        "conversational",
        "abbreviated",
        "alternative",
    }
    assert {entry.author_type for entry in catalog.entries} == {"agent"}
    assert {entry.review_type for entry in catalog.entries} == {"agent-reviewed"}
    expected_combinations = {
        (template["id"], language, style)
        for template in templates
        for language in ("en", "vi")
        for style in ("formal", "conversational", "abbreviated", "alternative")
    }
    assert {
        (entry.template_id, entry.language, entry.style) for entry in catalog.entries
    } == expected_combinations
    slots = {template["id"]: frozenset(template["slots"]) for template in templates}
    assert all(
        frozenset(entry.placeholders) == slots[entry.template_id]
        for entry in catalog.entries
    )
    assert all(entry.content_sha256 == catalog_entry_digest(entry) for entry in catalog.entries)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"pattern": "Question about {start_date}?"}, "placeholder schema"),
        (
            {
                "pattern": "Question {start_date} {end_date} {unexpected}?",
                "placeholders": ["end_date", "start_date", "unexpected"],
            },
            "placeholder schema",
        ),
        (
            {"pattern": "From {start_date} to {start_date} and {end_date}?"},
            "repeated placeholder",
        ),
        ({"language": "fr"}, "language"),
        ({"style": "poetic"}, "style"),
    ],
)
def test_catalog_rejects_invalid_placeholder_language_or_style(
    tmp_path: Path, change: dict[str, object], message: str
) -> None:
    entry = _entry(**change)
    path = tmp_path / "catalog.json"
    _write(path, _document(entry))

    with pytest.raises(CatalogValidationError, match=message):
        load_catalog(path, [load_templates()[0]], expected_entry_count=1)


def test_catalog_rejects_duplicate_entries_extra_fields_and_digest_tampering(
    tmp_path: Path,
) -> None:
    entry = _entry()
    path = tmp_path / "catalog.json"
    _write(path, {"schema_version": CATALOG_SCHEMA_VERSION, "entries": [entry, entry]})
    with pytest.raises(CatalogValidationError, match="duplicate"):
        load_catalog(path, [load_templates()[0]], expected_entry_count=2)

    _write(path, _document(entry | {"unexpected": True}))
    with pytest.raises(CatalogValidationError, match="field set"):
        load_catalog(path, [load_templates()[0]], expected_entry_count=1)

    _write(path, _document(entry | {"content_sha256": "0" * 64}))
    with pytest.raises(CatalogValidationError, match="digest"):
        load_catalog(path, [load_templates()[0]], expected_entry_count=1)


def test_catalog_entry_id_is_bound_to_template_language_and_style(tmp_path: Path) -> None:
    entry = _entry(id="unrelated-id")
    path = tmp_path / "catalog.json"
    _write(path, _document(entry))

    with pytest.raises(CatalogValidationError, match="entry id"):
        load_catalog(path, [load_templates()[0]], expected_entry_count=1)


def test_replacing_catalog_entry_preserves_frozen_value_semantics() -> None:
    entry = CatalogEntry(**_entry())
    changed = replace(entry, pattern="Changed {start_date} and {end_date}")

    assert entry.pattern != changed.pattern
    assert entry.style == changed.style
