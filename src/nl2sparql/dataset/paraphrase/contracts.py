"""Strict response and fact contracts for T3.3 paraphrasing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from nl2sparql.linking.dictionary import ENTITIES_PATH

STAGE_B_MODEL = "openai/gpt-4.1-mini"
STAGE_C_MODEL = "google/gemini-2.5-flash"
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ParaphraseValidationError(ValueError):
    """Raised when paraphrase data loses meaning or violates its schema."""


def _clean_question(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("question must not be empty")
    if "```" in value:
        raise ValueError("question must not contain a code fence")
    if CONTROL_RE.search(value) or "\n" in value or "\r" in value:
        raise ValueError("question must be one printable line")
    if len(value) > 300:
        raise ValueError("question must not exceed 300 characters")
    return value


class StageBResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    preserved_facts: list[str]

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _clean_question(value)


class StageCResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    casual: str
    abbreviated: str
    alternative: str
    preserved_facts: list[str]

    @field_validator("casual", "abbreviated", "alternative")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _clean_question(value)


def _fact_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def build_preserved_facts(record: dict[str, Any]) -> list[str]:
    slots = record.get("slot_values")
    if not isinstance(slots, dict):
        raise ParaphraseValidationError("record requires slot_values")
    return [f"{name}={_fact_value(slots[name])}" for name in sorted(slots)]


def validate_preserved_facts(facts: list[str], record: dict[str, Any]) -> None:
    if facts != build_preserved_facts(record):
        raise ParaphraseValidationError("response preserved facts do not match source slots")


def load_entity_index(path: Path = ENTITIES_PATH) -> dict[str, dict[str, str]]:
    try:
        entities = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParaphraseValidationError(f"Unable to load entity context: {path}") from exc
    index: dict[str, dict[str, str]] = {}
    for entity in entities:
        index[entity["address_lower"]] = {
            "owner": entity["owner"],
            "primary_label": entity["primary_label"],
        }
    return index
