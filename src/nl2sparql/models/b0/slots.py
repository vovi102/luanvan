"""Typed slot extraction for accepted B0 templates."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import date
from re import Match

from nl2sparql.dataset.templates import TemplateValidationError, render_template
from nl2sparql.linking.resolver import ResolutionPlan, ResolvedEntity
from nl2sparql.models.b0.contracts import B0Error, LinkingProvenance, SlotValue
from nl2sparql.models.b0.templates import CompiledTemplate

_DATE_RE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_ADDRESS_RE = re.compile(r"(?<!\w)0x[0-9a-f]{40}(?!\w)", re.IGNORECASE)
_HASH_RE = re.compile(r"(?<!\w)0x[0-9a-f]{64}(?!\w)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
_SYMBOL_CUE_RE = re.compile(
    r"\b(?:token|for|of)\s+([A-Z][A-Z0-9]{1,15})\b",
)
_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,15}$")
_NUMERIC_TYPES = frozenset({"integer", "block_number", "duration_minutes", "decimal_wei"})


def slot_mapping(values: Sequence[SlotValue]) -> dict[str, str | int]:
    """Return the render-compatible mapping for one complete slot tuple.

    Args:
        values: Validated typed slot values.

    Returns:
        Slot names mapped to renderer-compatible scalar values.
    """
    return {value.name: value.value for value in values}


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _trusted_entities(
    question: str,
    plan: ResolutionPlan | None,
    expected_provenance: LinkingProvenance | None,
) -> tuple[ResolvedEntity, ...] | None:
    if plan is None:
        return ()
    if (
        not isinstance(plan, ResolutionPlan)
        or plan.question_sha256 != hashlib.sha256(question.encode()).hexdigest()
        or plan.status != "resolved"
        or plan.warnings
    ):
        return None
    if expected_provenance is not None and (
        plan.catalog_sha256 != expected_provenance.catalog_sha256
        or plan.entities_sha256 != expected_provenance.entities_sha256
        or plan.aliases_sha256 != expected_provenance.aliases_sha256
        or plan.concepts_sha256 != expected_provenance.concepts_sha256
    ):
        return None
    return plan.entities


def _entity_value(
    entities: tuple[ResolvedEntity, ...],
    slot_type: str,
    span: tuple[int, int] | None,
    expected_direction: str,
) -> tuple[str, tuple[int, int]] | None:
    candidates = tuple(
        entity for entity in entities if span is None or _overlaps(entity.span_offset, span)
    )
    candidates = tuple(
        entity for entity in candidates if _eligible_entity(entity, slot_type, expected_direction)
    )
    if len(candidates) != 1:
        return None
    return candidates[0].values[0], candidates[0].span_offset


def _eligible_entity(
    entity: ResolvedEntity,
    slot_type: str,
    expected_direction: str,
) -> bool:
    if slot_type == "ethereum_address":
        return (
            entity.resolution_kind == "instance"
            and entity.coverage_status == "supported"
            and entity.operator == "in"
            and len(entity.values) == 1
            and (
                expected_direction == "unspecified"
                or (
                    entity.direction == expected_direction
                    and any(
                        field.field == f"{expected_direction}_address" for field in entity.fields
                    )
                )
            )
        )
    if slot_type == "concept_class":
        return (
            entity.resolution_kind == "concept"
            and entity.coverage_status == "supported"
            and entity.operator == "equals"
            and len(entity.values) == 1
            and entity.required_relation == "entity_labels_v1"
            and entity.required_join == "fact_address_to_entity"
            and entity.required_role is not None
            and (
                expected_direction == "unspecified"
                or (
                    entity.direction == expected_direction
                    and any(
                        field.field == f"{expected_direction}_address" for field in entity.fields
                    )
                )
            )
        )
    return False


def _expected_direction(template: CompiledTemplate, name: str) -> str:
    sql = str(template.raw["sql_template"]).casefold()
    placeholder = "{" + name.casefold() + "}"
    directions = {
        direction
        for direction in ("from", "to", "token")
        if f"{direction}_address = '{placeholder}'" in sql
        or f"{direction}_concept_class = '{placeholder}'" in sql
    }
    return next(iter(directions)) if len(directions) == 1 else "unspecified"


def _direct_value(slot_type: str, text: str) -> str | int | None:
    if slot_type in {"integer", "block_number", "duration_minutes"}:
        return int(text) if text.isdigit() else None
    if slot_type == "decimal_wei":
        return text if re.fullmatch(r"\d+(?:\.\d+)?", text) else None
    if slot_type == "date":
        try:
            date.fromisoformat(text)
        except ValueError:
            return None
        return text
    if slot_type == "ethereum_address":
        return text.lower() if _ADDRESS_RE.fullmatch(text) else None
    if slot_type == "transaction_hash":
        return text.lower() if _HASH_RE.fullmatch(text) else None
    if slot_type == "token_symbol":
        return text if _SYMBOL_RE.fullmatch(text) else None
    return None


def _validated(
    template: CompiledTemplate,
    values: list[SlotValue],
) -> tuple[SlotValue, ...] | None:
    ordered = tuple(
        next(value for value in values if value.name == name) for name in template.slot_order
    )
    try:
        render_template(template.raw, slot_mapping(ordered))
    except (TemplateValidationError, B0Error, StopIteration, TypeError, ValueError):
        return None
    return ordered


def extract_seed_slots(
    template: CompiledTemplate,
    question: str,
    groups: Match[str],
    resolution_plan: ResolutionPlan | None,
    *,
    expected_provenance: LinkingProvenance | None = None,
) -> tuple[SlotValue, ...] | None:
    """Parse named seed groups and validate one complete template fill.

    Args:
        template: Compiled template selected by exact seed matching.
        question: Original natural-language question.
        groups: Full seed-pattern match with named slot groups.
        resolution_plan: Optional resolver evidence for linked slots.
        expected_provenance: Required resolver fingerprints when configured.

    Returns:
        Ordered validated slot values, or ``None`` when evidence is unsafe.
    """
    entities = _trusted_entities(question, resolution_plan, expected_provenance)
    if entities is None:
        return None
    values: list[SlotValue] = []
    definitions: Mapping[str, Mapping[str, object]] = template.raw["slots"]
    for name in template.slot_order:
        slot_type = str(definitions[name]["type"])
        span = (groups.start(name), groups.end(name))
        direct = _direct_value(slot_type, groups.group(name))
        if direct is not None:
            values.append(SlotValue(name, slot_type, direct, span))
            continue
        linked = _entity_value(
            entities,
            slot_type,
            span,
            _expected_direction(template, name),
        )
        if linked is None:
            return None
        value, source_span = linked
        values.append(SlotValue(name, slot_type, value, source_span))
    return _validated(template, values)


def _matches_without_overlap(
    pattern: re.Pattern[str],
    question: str,
    protected: Sequence[tuple[int, int]],
) -> list[tuple[str, tuple[int, int]]]:
    return [
        (match.group(), match.span())
        for match in pattern.finditer(question)
        if not any(_overlaps(match.span(), span) for span in protected)
    ]


def _assign(
    values: list[SlotValue],
    names: list[str],
    slot_type_by_name: Mapping[str, str],
    candidates: Sequence[tuple[str | int, tuple[int, int]]],
) -> bool:
    if len(names) != len(candidates):
        return False
    for name, (raw, span) in zip(names, candidates, strict=True):
        slot_type = slot_type_by_name[name]
        converted = _direct_value(slot_type, str(raw))
        if converted is None:
            return False
        values.append(SlotValue(name, slot_type, converted, span))
    return True


def extract_structural_slots(
    template: CompiledTemplate,
    question: str,
    resolution_plan: ResolutionPlan | None,
    *,
    expected_provenance: LinkingProvenance | None = None,
) -> tuple[SlotValue, ...] | None:
    """Extract every declared slot from source order or supported resolver evidence.

    Args:
        template: Compiled template selected by structural matching.
        question: Original natural-language question.
        resolution_plan: Optional resolver evidence for linked slots.
        expected_provenance: Required resolver fingerprints when configured.

    Returns:
        Ordered validated slot values, or ``None`` when extraction is ambiguous.
    """
    entities = _trusted_entities(question, resolution_plan, expected_provenance)
    if entities is None:
        return None
    definitions: Mapping[str, Mapping[str, object]] = template.raw["slots"]
    slot_type_by_name = {name: str(definitions[name]["type"]) for name in template.slot_order}
    values: list[SlotValue] = []

    date_candidates = [(match.group(), match.span()) for match in _DATE_RE.finditer(question)]
    hash_candidates = [
        (match.group().lower(), match.span()) for match in _HASH_RE.finditer(question)
    ]
    address_candidates = [
        (match.group().lower(), match.span())
        for match in _ADDRESS_RE.finditer(question)
        if not any(_overlaps(match.span(), span) for _, span in hash_candidates)
    ]
    protected = [span for _, span in (*date_candidates, *hash_candidates, *address_candidates)]
    number_candidates = _matches_without_overlap(_NUMBER_RE, question, protected)

    date_names = [name for name in template.slot_order if slot_type_by_name[name] == "date"]
    if not _assign(values, date_names, slot_type_by_name, date_candidates):
        return None
    hash_names = [
        name for name in template.slot_order if slot_type_by_name[name] == "transaction_hash"
    ]
    if not _assign(values, hash_names, slot_type_by_name, hash_candidates):
        return None

    address_names = [
        name for name in template.slot_order if slot_type_by_name[name] == "ethereum_address"
    ]
    linked_addresses: list[tuple[str, tuple[int, int]]] = []
    remaining_entities = list(entities)
    for name in address_names[len(address_candidates) :]:
        expected_direction = _expected_direction(template, name)
        eligible = sorted(
            (
                entity
                for entity in remaining_entities
                if _eligible_entity(entity, "ethereum_address", expected_direction)
            ),
            key=lambda entity: entity.span_offset,
        )
        if not eligible:
            return None
        selected = eligible[0]
        linked_addresses.append((selected.values[0], selected.span_offset))
        remaining_entities.remove(selected)
    all_addresses = sorted((*address_candidates, *linked_addresses), key=lambda item: item[1])
    if not _assign(values, address_names, slot_type_by_name, all_addresses):
        return None

    numeric_names = [
        name for name in template.slot_order if slot_type_by_name[name] in _NUMERIC_TYPES
    ]
    if not _assign(values, numeric_names, slot_type_by_name, number_candidates):
        return None

    concept_names = [
        name for name in template.slot_order if slot_type_by_name[name] == "concept_class"
    ]
    concepts = [
        linked
        for name in concept_names
        if (
            linked := _entity_value(
                entities,
                "concept_class",
                None,
                _expected_direction(template, name),
            )
        )
        is not None
    ]
    if len(concept_names) != len(concepts):
        return None
    for name, (value, span) in zip(concept_names, concepts, strict=True):
        values.append(SlotValue(name, "concept_class", value, span))

    symbol_names = [
        name for name in template.slot_order if slot_type_by_name[name] == "token_symbol"
    ]
    symbol_candidates = [
        (match.group(1), match.span(1)) for match in _SYMBOL_CUE_RE.finditer(question)
    ]
    if not _assign(values, symbol_names, slot_type_by_name, symbol_candidates):
        return None

    unsupported = {
        slot_type_by_name[name]
        for name in template.slot_order
        if slot_type_by_name[name] in {"entity_owner", "entity_category"}
    }
    if unsupported:
        return None
    return _validated(template, values)
