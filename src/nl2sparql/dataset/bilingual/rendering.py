"""Pure literal rendering for deterministic bilingual training questions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from statistics import mean
from string import Formatter
from typing import Any, cast

from nl2sparql.dataset.bilingual.contracts import (
    AUTHOR_TYPE,
    PRODUCER_TYPE,
    REVIEW_TYPE,
    STYLES,
    Catalog,
    CatalogEntry,
    ExpandedTrainingRecord,
    JsonScalar,
)
from nl2sparql.dataset.generate import validate_stage_a_records
from nl2sparql.dataset.paraphrase.quality import normalize_question, normalized_levenshtein

RENDERER_VERSION = "deterministic-bilingual-renderer-v1"
DIVERSITY_THRESHOLD = 0.30


class RenderingValidationError(ValueError):
    """Raised when rendering or expanded-record validation fails."""


def render_pattern(entry: CatalogEntry, slot_values: Mapping[str, object]) -> str:
    """Bind named placeholders without interpreting slot values as format text."""
    declared = frozenset(entry.placeholders)
    supplied = frozenset(slot_values)
    missing = declared - supplied
    extra = supplied - declared
    if missing:
        raise RenderingValidationError(f"missing slot values: {sorted(missing)}")
    if extra:
        raise RenderingValidationError(f"extra slot values: {sorted(extra)}")
    if any(
        value is None or (isinstance(value, str) and not value) for value in slot_values.values()
    ):
        raise RenderingValidationError("slot values must be non-empty")

    try:
        parsed = tuple(Formatter().parse(entry.pattern))
    except ValueError as exc:
        raise RenderingValidationError("pattern contains malformed braces") from exc
    pieces: list[str] = []
    names: list[str] = []
    for literal, field_name, format_spec, conversion in parsed:
        pieces.append(literal)
        if field_name is None:
            continue
        if not field_name.isidentifier() or format_spec or conversion:
            raise RenderingValidationError("pattern contains an invalid placeholder")
        names.append(field_name)
        if field_name not in declared:
            raise RenderingValidationError(f"undeclared placeholder: {field_name}")
        pieces.append(str(slot_values[field_name]))
    if len(names) != len(set(names)):
        raise RenderingValidationError("pattern contains a repeated placeholder")
    if frozenset(names) != declared:
        raise RenderingValidationError("pattern placeholder set does not match declaration")
    rendered = "".join(pieces)
    if not rendered.strip() or rendered != rendered.strip() or not rendered.isprintable():
        raise RenderingValidationError("rendered question must be one non-empty printable line")
    return rendered


@dataclass(frozen=True, slots=True)
class DiversityReport:
    family_language_count: int
    minimum: float
    mean: float
    maximum: float
    p25: float
    median: float
    p75: float
    failing_family_ids: tuple[str, ...]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _record_dict(record: ExpandedTrainingRecord) -> dict[str, Any]:
    return cast(dict[str, Any], asdict(record))


def expanded_record_digest(record: ExpandedTrainingRecord) -> str:
    """Hash every expanded field except the self-referential record digest."""
    body = _record_dict(record)
    body.pop("record_sha256", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _freeze_values(values: Mapping[str, object]) -> tuple[tuple[str, JsonScalar], ...]:
    frozen: list[tuple[str, JsonScalar]] = []
    for name in sorted(values):
        value = values[name]
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise RenderingValidationError(f"slot {name} is not a JSON scalar")
        frozen.append((name, cast(JsonScalar, value)))
    return tuple(frozen)


def _freeze_entities(
    values: object,
) -> tuple[tuple[tuple[str, JsonScalar], ...], ...]:
    if not isinstance(values, list):
        raise RenderingValidationError("entities_used must be an array")
    result: list[tuple[tuple[str, JsonScalar], ...]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise RenderingValidationError("entity annotations must be mappings")
        result.append(_freeze_values(value))
    return tuple(result)


def _template_index(templates: list[dict[str, Any]] | tuple[dict[str, Any], ...]):
    return {str(template["id"]): template for template in templates}


def _catalog_index(catalog: Catalog) -> dict[str, tuple[CatalogEntry, ...]]:
    grouped: dict[str, list[CatalogEntry]] = defaultdict(list)
    for entry in catalog.entries:
        grouped[entry.template_id].append(entry)
    return {
        template_id: tuple(sorted(entries, key=lambda entry: entry.id))
        for template_id, entries in grouped.items()
    }


def _require_source_mapping(record: object) -> Mapping[str, Any]:
    if not isinstance(record, Mapping):
        raise RenderingValidationError("Stage A records must be mappings")
    return record


def _assert_literal_anchors(question: str, slot_values: Mapping[str, object]) -> None:
    folded = question.casefold()
    missing = [name for name, value in slot_values.items() if str(value).casefold() not in folded]
    if missing:
        raise RenderingValidationError(f"rendered question lost semantic anchors: {missing}")


def expand_stage_a(
    records: list[dict[str, Any]],
    catalog: Catalog,
    templates: list[dict[str, Any]],
) -> tuple[ExpandedTrainingRecord, ...]:
    """Expand accepted Stage A rows into eight stable clean variants each."""
    try:
        validate_stage_a_records(records, templates)
    except ValueError as exc:
        raise RenderingValidationError(f"Stage A validation failed: {exc}") from exc
    template_index = _template_index(templates)
    catalog_index = _catalog_index(catalog)
    expanded: list[ExpandedTrainingRecord] = []
    for source_value in sorted(records, key=lambda value: str(value["id"])):
        source = _require_source_mapping(source_value)
        source_id = str(source["id"])
        template_id = str(source["template_id"])
        entries = catalog_index.get(template_id, ())
        if len(entries) != 8:
            raise RenderingValidationError(f"catalog requires eight entries for {template_id}")
        template = template_index[template_id]
        slot_values = cast(Mapping[str, object], source["slot_values"])
        frozen_slots = _freeze_values(slot_values)
        for entry in entries:
            question = render_pattern(entry, slot_values)
            _assert_literal_anchors(question, slot_values)
            record = ExpandedTrainingRecord(
                id=f"{source_id}__{entry.language}__{entry.style}",
                language=entry.language,
                style=entry.style,
                semantic_family_id=source_id,
                catalog_entry_id=entry.id,
                catalog_entry_sha256=entry.content_sha256,
                source_record_id=source_id,
                source_record_sha256=str(source["record_sha256"]),
                source_template_sha256=str(source["template_sha256"]),
                renderer_version=RENDERER_VERSION,
                question=question,
                normalized_question=normalize_question(question),
                sql=str(source["sql"]),
                slot_values=frozen_slots,
                expected_columns=tuple(str(value) for value in template["expected_columns"]),
                schema_elements=tuple(str(value) for value in source["schema_elements"]),
                entities_used=_freeze_entities(source["entities_used"]),
                semantic_anchors=frozen_slots,
                split="unassigned",
                producer_type=PRODUCER_TYPE,
                author_type=AUTHOR_TYPE,
                review_type=REVIEW_TYPE,
                generation_model=None,
                provider=None,
                api_request_count=0,
                recorded_cost_usd=0.0,
                record_sha256="",
            )
            expanded.append(replace(record, record_sha256=expanded_record_digest(record)))
    result = tuple(sorted(expanded, key=lambda record: record.id))
    validate_expansion(result, records, templates)
    return result


def _quantile(values: list[float], fraction: float) -> float:
    index = round((len(values) - 1) * fraction)
    return values[index]


def diversity_report(
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    *,
    threshold: float = DIVERSITY_THRESHOLD,
) -> DiversityReport:
    """Measure six pairwise distances for each family and language."""
    grouped: dict[tuple[str, str], list[ExpandedTrainingRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.semantic_family_id, record.language)].append(record)
    group_means: list[tuple[str, float]] = []
    for (family_id, language), variants in sorted(grouped.items()):
        if len(variants) != 4 or {record.style for record in variants} != set(STYLES):
            raise RenderingValidationError(
                f"family {family_id}/{language} does not contain all four styles"
            )
        questions = [record.normalized_question for record in variants]
        distances = [
            normalized_levenshtein(left, right) for left, right in combinations(questions, 2)
        ]
        group_means.append((f"{family_id}:{language}", mean(distances)))
    if not group_means:
        raise RenderingValidationError("no family/language diversity groups were provided")
    values = sorted(value for _, value in group_means)
    failing = tuple(group_id for group_id, value in group_means if value <= threshold)
    report = DiversityReport(
        family_language_count=len(values),
        minimum=values[0],
        mean=mean(values),
        maximum=values[-1],
        p25=_quantile(values, 0.25),
        median=_quantile(values, 0.50),
        p75=_quantile(values, 0.75),
        failing_family_ids=failing,
    )
    if failing:
        raise RenderingValidationError(
            "mean pairwise normalized Levenshtein distance must be strictly greater "
            f"than {threshold:.6f}; failing groups: {list(failing[:10])}"
        )
    return report


def _validate_semantics(
    record: ExpandedTrainingRecord,
    source: Mapping[str, Any],
    template: Mapping[str, Any],
) -> None:
    expected_slots = _freeze_values(cast(Mapping[str, object], source["slot_values"]))
    expected_entities = _freeze_entities(source["entities_used"])
    checks = (
        (record.source_record_sha256 == source["record_sha256"], "source record digest"),
        (record.source_template_sha256 == source["template_sha256"], "template digest"),
        (record.sql == source["sql"], "sql"),
        (record.slot_values == expected_slots, "slot values"),
        (record.expected_columns == tuple(template["expected_columns"]), "expected columns"),
        (record.schema_elements == tuple(source["schema_elements"]), "schema elements"),
        (record.entities_used == expected_entities, "entities"),
        (record.semantic_anchors == expected_slots, "semantic anchors"),
    )
    for passed, label in checks:
        if not passed:
            raise RenderingValidationError(f"expanded record changed immutable {label}")


def validate_expansion(
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    stage_a: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> DiversityReport:
    """Recompute all clean-expansion gates from source evidence."""
    try:
        validate_stage_a_records(stage_a, templates)
    except ValueError as exc:
        raise RenderingValidationError(f"Stage A validation failed: {exc}") from exc
    if len(records) != 8000:
        raise RenderingValidationError(
            f"clean expansion requires 8000 records, received {len(records)}"
        )
    sources = {str(record["id"]): record for record in stage_a}
    template_index = _template_index(templates)
    ids = [record.id for record in records]
    normalized = [record.normalized_question for record in records]
    if len(set(ids)) != len(ids):
        raise RenderingValidationError("clean expansion requires unique record IDs")
    if len(set(normalized)) != len(normalized):
        raise RenderingValidationError("clean expansion requires unique normalized questions")
    if Counter(record.language for record in records) != {"en": 4000, "vi": 4000}:
        raise RenderingValidationError("clean expansion requires 4000 records per language")
    if Counter(record.style for record in records) != {style: 2000 for style in STYLES}:
        raise RenderingValidationError("clean expansion requires 2000 records per style")
    family_counts = Counter(record.semantic_family_id for record in records)
    if len(family_counts) != 1000 or set(family_counts.values()) != {8}:
        raise RenderingValidationError("clean expansion requires eight variants per family")
    for record in records:
        source = sources.get(record.source_record_id)
        if source is None or record.semantic_family_id != record.source_record_id:
            raise RenderingValidationError("semantic family does not match its Stage A source")
        template = template_index[str(source["template_id"])]
        _validate_semantics(record, source, template)
        if record.id != f"{record.source_record_id}__{record.language}__{record.style}":
            raise RenderingValidationError("expanded record id is not canonical")
        expected_normalized = normalize_question(record.question)
        if record.normalized_question != expected_normalized:
            raise RenderingValidationError("expanded normalized question is stale")
        _assert_literal_anchors(record.question, dict(record.semantic_anchors))
        if record.record_sha256 != expanded_record_digest(record):
            raise RenderingValidationError("expanded record digest does not match")
        if (
            record.renderer_version != RENDERER_VERSION
            or record.producer_type != PRODUCER_TYPE
            or record.author_type != AUTHOR_TYPE
            or record.review_type != REVIEW_TYPE
            or record.generation_model is not None
            or record.provider is not None
            or record.api_request_count != 0
            or record.recorded_cost_usd != 0.0
        ):
            raise RenderingValidationError("expanded record provenance is invalid")
    return diversity_report(records)


def serialize_records(records: tuple[ExpandedTrainingRecord, ...]) -> bytes:
    """Serialize records as canonical sorted JSONL bytes."""
    return b"".join(_canonical_json(_record_dict(record)) + b"\n" for record in records)
