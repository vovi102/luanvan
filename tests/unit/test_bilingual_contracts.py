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
    assert (
        digest
        == hashlib.sha256(
            json.dumps(
                {key: value for key, value in entry.items() if key != "content_sha256"},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    )
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
        frozenset(entry.placeholders) == slots[entry.template_id] for entry in catalog.entries
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


def test_supported_category_distribution_and_bridge_patterns_match_sql_semantics() -> None:
    catalog = load_catalog(TEMPLATES_PATH, load_templates())
    patterns = {entry.id: entry.pattern for entry in catalog.entries}
    expected = {
        "T_CATEGORY_OWNER_DISTRIBUTION__en__formal": (
            "List the top {n} label categories ranked by distinct owner count, including "
            "account count and accounts per owner."
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__en__conversational": (
            "Which {n} label categories have the most distinct owners, and how many "
            "accounts and accounts per owner does each have?"
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__en__abbreviated": (
            "Top {n} label categories by owners, with accounts and accounts/owner."
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__en__alternative": (
            "Rank {n} categories in the accepted label dictionary by unique owners and "
            "return each category's account total and accounts-per-owner ratio."
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__vi__formal": (
            "Liệt kê {n} danh mục nhãn đứng đầu theo số chủ sở hữu riêng biệt, kèm số "
            "tài khoản và số tài khoản trên mỗi chủ sở hữu."
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__vi__conversational": (
            "{n} danh mục nhãn nào có nhiều chủ sở hữu riêng biệt nhất, và mỗi danh mục "
            "có bao nhiêu tài khoản cùng tỷ lệ tài khoản trên chủ sở hữu?"
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__vi__abbreviated": (
            "Top {n} danh mục nhãn theo số chủ sở hữu, kèm số tài khoản và tài khoản/chủ sở hữu."
        ),
        "T_CATEGORY_OWNER_DISTRIBUTION__vi__alternative": (
            "Xếp hạng {n} danh mục trong từ điển nhãn đã chấp nhận theo số chủ sở hữu "
            "duy nhất, đồng thời trả về tổng tài khoản và tỷ lệ tài khoản trên mỗi chủ sở hữu."
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__en__formal": (
            "Find {n} token transfers from funded addresses at or after successful "
            "positive native treasury funding and strictly before {duration_minutes} "
            "minutes elapse, between {start_date} and {end_date}."
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__en__conversational": (
            "Which {n} token events leave funded addresses at or after successful "
            "positive native treasury funding, but less than {duration_minutes} "
            "minutes later, from {start_date} to {end_date}?"
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__en__abbreviated": (
            "First {n} funded-address token transfers at or after successful positive "
            "native treasury funding, elapsed < {duration_minutes} min, "
            "{start_date}–{end_date}."
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__en__alternative": (
            "For {start_date} to {end_date}, return {n} token transfers sent by "
            "funded addresses at or after successful positive native treasury funding "
            "and before the {duration_minutes}-minute timestamp boundary."
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__vi__formal": (
            "Tìm {n} lượt chuyển token từ địa chỉ được cấp native thành công có value "
            "dương bởi kho quỹ, timestamp không trước khoản cấp và chưa đủ "
            "{duration_minutes} phút, từ {start_date} đến {end_date}."
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__vi__conversational": (
            "Từ {start_date} tới {end_date}, {n} sự kiện token nào rời địa chỉ nhận "
            "native từ kho quỹ thành công có value dương, timestamp không trước khoản "
            "cấp và cách dưới {duration_minutes} phút?"
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__vi__abbreviated": (
            "{n} token transfer đầu tiên từ địa chỉ nhận native kho quỹ thành công có "
            "value dương; timestamp không trước khoản cấp, cách < {duration_minutes} "
            "phút, {start_date}–{end_date}."
        ),
        "T_TOKEN_AFTER_NATIVE_FUNDING__vi__alternative": (
            "Trong {start_date} đến {end_date}, trả {n} sự kiện token do địa chỉ được "
            "kho quỹ cấp native thành công có value dương gửi, timestamp không trước "
            "khoản cấp và nhỏ hơn mốc cộng {duration_minutes} phút."
        ),
    }

    assert {entry_id: patterns[entry_id] for entry_id in expected} == expected
    replacements = [
        entry for entry in catalog.entries if entry.template_id == "T_CATEGORY_OWNER_DISTRIBUTION"
    ]
    assert len(replacements) == 8
    assert all(entry.placeholders == ("n",) for entry in replacements)
    assert len({" ".join(entry.pattern.casefold().split()) for entry in replacements}) == 8
    assert all(entry.template_id != "T_MIXER_TO_DEX_LARGE_FLOW" for entry in catalog.entries)
    normalized_replacement_copy = " ".join(entry.pattern.casefold() for entry in replacements)
    assert "one owner spans multiple categories" not in normalized_replacement_copy
    assert "owner belongs to multiple categories" not in normalized_replacement_copy
    assert "một chủ sở hữu thuộc nhiều danh mục" not in normalized_replacement_copy
