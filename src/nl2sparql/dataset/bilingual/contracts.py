"""Strict contracts for deterministic bilingual training artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from string import Formatter
from typing import Any, Literal, TypeAlias, cast

Language = Literal["en", "vi"]
Style = Literal["formal", "conversational", "abbreviated", "alternative"]
Split = Literal["unassigned", "train", "development"]
JsonScalar: TypeAlias = str | int | float | bool | None

CATALOG_SCHEMA_VERSION = "1.0.0"
AUDIT_SCHEMA_VERSION = "1.0.0"
EXCLUSION_SCHEMA_VERSION = "1.0.0"
TEMPLATES_PATH = Path(__file__).with_name("templates.json")

LANGUAGES = ("en", "vi")
STYLES = ("formal", "conversational", "abbreviated", "alternative")
AUTHOR_TYPE = "agent"
REVIEW_TYPE = "agent-reviewed"
PRODUCER_TYPE = "deterministic_template_renderer"

_CATALOG_FIELDS = frozenset({"schema_version", "entries"})
_ENTRY_FIELDS = frozenset(
    {
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
    }
)


class CatalogValidationError(ValueError):
    """Raised when the finite authored catalog violates its strict contract."""


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    id: str
    template_id: str
    language: Language
    style: Style
    pattern: str
    placeholders: tuple[str, ...]
    author_type: str
    review_type: str
    catalog_schema_version: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class Catalog:
    schema_version: str
    entries: tuple[CatalogEntry, ...]


@dataclass(frozen=True, slots=True)
class ExpandedTrainingRecord:
    id: str
    language: Language
    style: Style
    semantic_family_id: str
    catalog_entry_id: str
    catalog_entry_sha256: str
    source_record_id: str
    source_record_sha256: str
    source_template_sha256: str
    renderer_version: str
    question: str
    normalized_question: str
    sql: str
    slot_values: tuple[tuple[str, JsonScalar], ...]
    expected_columns: tuple[str, ...]
    schema_elements: tuple[str, ...]
    entities_used: tuple[tuple[tuple[str, JsonScalar], ...], ...]
    semantic_anchors: tuple[tuple[str, JsonScalar], ...]
    split: Split
    producer_type: str
    author_type: str
    review_type: str
    generation_model: None
    provider: None
    api_request_count: int
    recorded_cost_usd: float
    record_sha256: str


@dataclass(frozen=True, slots=True)
class SplitConfig:
    seed: int = 42
    development_percent: int = 10


@dataclass(frozen=True, slots=True)
class ExclusionIndex:
    schema_version: str
    ngram_size: int
    source_sha256s: tuple[str, ...]
    source_record_counts: tuple[int, ...]
    normalized_text_sha256s: tuple[str, ...]
    ngram_sha256s: tuple[str, ...]
    index_sha256: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    schema_version: str
    event_id: str
    record_id: str
    record_sha256: str
    decision: str
    faithful: bool
    natural: bool
    notes: str
    reviewer_type: str
    reviewed_at: str
    supersedes_event_id: str | None


@dataclass(frozen=True, slots=True)
class AuditSummary:
    language: Language
    sample_size: int
    faithful_count: int
    natural_count: int
    accepted_count: int
    passed: bool


def _mapping(value: object) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        return cast(dict[str, Any], asdict(value))
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("catalog entry must be a mapping or dataclass")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def catalog_entry_digest(value: object) -> str:
    """Return the canonical digest of an entry, excluding its digest field."""
    body = _mapping(value)
    body.pop("content_sha256", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _load_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(f"unable to read catalog: {path}") from exc
    if not isinstance(value, dict) or set(value) != _CATALOG_FIELDS:
        raise CatalogValidationError("catalog field set is invalid")
    return value


def _template_slots(templates: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for template in templates:
        template_id = template.get("id")
        slots = template.get("slots")
        if not isinstance(template_id, str) or not isinstance(slots, Mapping):
            raise CatalogValidationError("production template contract is invalid")
        if template_id in result:
            raise CatalogValidationError(f"duplicate production template: {template_id}")
        result[template_id] = frozenset(str(name) for name in slots)
    return result


def _pattern_placeholders(pattern: str) -> tuple[str, ...]:
    names: list[str] = []
    try:
        parsed = Formatter().parse(pattern)
        for _, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            if not field_name or not field_name.isidentifier():
                raise CatalogValidationError("pattern contains an invalid placeholder")
            if format_spec or conversion:
                raise CatalogValidationError("placeholder formatting is not allowed")
            names.append(field_name)
    except ValueError as exc:
        raise CatalogValidationError("pattern contains malformed braces") from exc
    if len(names) != len(set(names)):
        raise CatalogValidationError("pattern contains a repeated placeholder")
    return tuple(names)


def _require_string(entry: Mapping[str, Any], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value:
        raise CatalogValidationError(f"catalog entry {field} must be a non-empty string")
    return value


def _parse_entry(raw: object, slots_by_template: Mapping[str, frozenset[str]]) -> CatalogEntry:
    if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
        raise CatalogValidationError("catalog entry field set is invalid")
    template_id = _require_string(raw, "template_id")
    if template_id not in slots_by_template:
        raise CatalogValidationError(f"unknown template_id: {template_id}")
    language = _require_string(raw, "language")
    if language not in LANGUAGES:
        raise CatalogValidationError(f"unsupported language: {language}")
    style = _require_string(raw, "style")
    if style not in STYLES:
        raise CatalogValidationError(f"unsupported style: {style}")
    entry_id = _require_string(raw, "id")
    if entry_id != f"{template_id}__{language}__{style}":
        raise CatalogValidationError("catalog entry id does not match template/language/style")
    pattern = _require_string(raw, "pattern")
    if "\n" in pattern or "\r" in pattern or pattern != pattern.strip():
        raise CatalogValidationError("catalog pattern must be one trimmed line")
    parsed_placeholders = _pattern_placeholders(pattern)
    declared = raw.get("placeholders")
    if (
        not isinstance(declared, list)
        or any(not isinstance(name, str) for name in declared)
        or declared != sorted(set(declared))
    ):
        raise CatalogValidationError("catalog placeholders must be sorted unique strings")
    declared_set = frozenset(declared)
    if (
        frozenset(parsed_placeholders) != declared_set
        or declared_set != slots_by_template[template_id]
    ):
        raise CatalogValidationError(f"placeholder schema does not match {template_id}")
    if raw.get("author_type") != AUTHOR_TYPE:
        raise CatalogValidationError("catalog author_type must be agent")
    if raw.get("review_type") != REVIEW_TYPE:
        raise CatalogValidationError("catalog review_type must be agent-reviewed")
    if raw.get("catalog_schema_version") != CATALOG_SCHEMA_VERSION:
        raise CatalogValidationError("catalog entry schema version is unsupported")
    content_sha256 = _require_string(raw, "content_sha256")
    if content_sha256 != catalog_entry_digest(raw):
        raise CatalogValidationError(f"catalog entry digest does not match: {entry_id}")
    return CatalogEntry(
        id=entry_id,
        template_id=template_id,
        language=cast(Language, language),
        style=cast(Style, style),
        pattern=pattern,
        placeholders=tuple(declared),
        author_type=AUTHOR_TYPE,
        review_type=REVIEW_TYPE,
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        content_sha256=content_sha256,
    )


def load_catalog(
    path: Path = TEMPLATES_PATH,
    templates: Sequence[Mapping[str, Any]] | None = None,
    *,
    expected_entry_count: int = 200,
) -> Catalog:
    """Load and fully validate the finite authored catalog."""
    if templates is None:
        from nl2sparql.dataset.templates.validate import load_templates

        templates = load_templates()
    slots_by_template = _template_slots(templates)
    document = _load_document(path)
    if document.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise CatalogValidationError("catalog schema version is unsupported")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) != expected_entry_count:
        count = len(raw_entries) if isinstance(raw_entries, list) else 0
        raise CatalogValidationError(
            f"catalog requires {expected_entry_count} entries, received {count}"
        )
    entries = tuple(_parse_entry(raw, slots_by_template) for raw in raw_entries)
    ids = [entry.id for entry in entries]
    combinations = [
        (entry.template_id, entry.language, entry.style) for entry in entries
    ]
    if len(ids) != len(set(ids)) or len(combinations) != len(set(combinations)):
        raise CatalogValidationError("catalog contains a duplicate entry")
    expected_combinations = {
        (template_id, language, style)
        for template_id in slots_by_template
        for language in LANGUAGES
        for style in STYLES
    }
    if (
        expected_entry_count == len(expected_combinations)
        and set(combinations) != expected_combinations
    ):
        raise CatalogValidationError("catalog language/style coverage is incomplete")
    return Catalog(schema_version=CATALOG_SCHEMA_VERSION, entries=entries)
