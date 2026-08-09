"""Deterministic faithfulness and diversity checks for paraphrases."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from itertools import combinations
from typing import Any

from nl2sparql.dataset.paraphrase.contracts import (
    ParaphraseValidationError,
    StageCResponse,
)

NUMERIC_SLOTS = {"n", "value_wei", "gas_used", "block_number", "duration_minutes"}


def normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized)
    return " ".join(normalized.split())


def _contains_number(question: str, value: object) -> bool:
    return re.search(rf"(?<!\d){re.escape(str(value))}(?!\d)", question) is not None


def _date_variants(value: str) -> set[str]:
    parsed = date.fromisoformat(value)
    return {
        value.casefold(),
        f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}".casefold(),
        f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}".casefold(),
    }


def validate_question_anchors(
    question: str,
    record: dict[str, Any],
    entity_index: dict[str, dict[str, str]],
) -> None:
    lowered = question.casefold()
    entity_types = {entity["slot"]: entity["type"] for entity in record.get("entities_used", [])}
    for name, value in record["slot_values"].items():
        if name in {"start_date", "end_date"}:
            if not any(variant in lowered for variant in _date_variants(str(value))):
                raise ParaphraseValidationError(f"question lost date anchor {name}")
        elif name in NUMERIC_SLOTS:
            if not _contains_number(question, value):
                raise ParaphraseValidationError(f"question lost numeric anchor {name}")
        elif entity_types.get(name) == "ethereum_address":
            candidates = {str(value).casefold()}
            known = entity_index.get(str(value).lower())
            if known:
                candidates.update(item.casefold() for item in known.values())
            if not any(candidate in lowered for candidate in candidates):
                raise ParaphraseValidationError(f"question lost entity anchor {name}")
        elif str(value).casefold() not in lowered:
            raise ParaphraseValidationError(f"question lost {name} anchor")


def normalized_levenshtein(left: str, right: str) -> float:
    if left == right:
        return 0.0
    if not left or not right:
        return 1.0
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1] / max(len(left), len(right))


def validate_stage_c_questions(
    response: StageCResponse,
    record: dict[str, Any],
    entity_index: dict[str, dict[str, str]],
) -> tuple[float, float, float]:
    questions = (response.casual, response.abbreviated, response.alternative)
    normalized = tuple(normalize_question(question) for question in questions)
    if len(set(normalized)) != 3:
        raise ParaphraseValidationError("Stage C questions must be unique")
    for question in questions:
        validate_question_anchors(question, record, entity_index)
    return tuple(normalized_levenshtein(left, right) for left, right in combinations(normalized, 2))


def mean_stage_c_distance(values: list[tuple[float, float, float]]) -> float:
    distances = [distance for group in values for distance in group]
    if not distances:
        raise ParaphraseValidationError("No Stage C distances were provided")
    return sum(distances) / len(distances)
