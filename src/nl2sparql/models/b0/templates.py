"""Compile the accepted GoogleSQL template snapshot for B0 matching."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from types import MappingProxyType
from typing import Any

from nl2sparql.dataset.templates import TemplateValidationError, validate_template_library
from nl2sparql.dataset.templates.validate import PLACEHOLDER_RE
from nl2sparql.models.b0.contracts import B0Error, B0Policy

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SLOT_PATTERNS = {
    "integer": r"\d+",
    "date": r"\d{4}-\d{2}-\d{2}",
    "decimal_wei": r"\d+(?:\.\d+)?",
    "ethereum_address": r"0x[0-9a-f]{40}",
    "transaction_hash": r"0x[0-9a-f]{64}",
    "block_number": r"\d+",
    "token_symbol": r"[A-Za-z][A-Za-z0-9]{0,15}",
    "entity_owner": r".+?",
    "entity_category": r".+?",
    "concept_class": r".+?",
    "duration_minutes": r"\d+",
}


@dataclass(frozen=True)
class CompiledTemplate:
    """One immutable template plus its precomputed matching structures."""

    template_id: str
    raw: Mapping[str, Any]
    seed_pattern: Pattern[str]
    slot_order: tuple[str, ...]
    literal_tokens: tuple[str, ...]
    literal_token_count: int
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    template_sha256: str


def _literal_pattern(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    pieces = re.split(r"(\s+)", value)
    return "".join(r"\s+" if piece.isspace() else re.escape(piece) for piece in pieces if piece)


def _compile_seed(template: Mapping[str, Any]) -> tuple[Pattern[str], tuple[str, ...]]:
    seed = template["nl_seed"]
    slots = template["slots"]
    cursor = 0
    pattern_parts = [r"\A"]
    order: list[str] = []
    for placeholder in PLACEHOLDER_RE.finditer(seed):
        pattern_parts.append(_literal_pattern(seed[cursor : placeholder.start()]))
        name = placeholder.group(1)
        slot_type = slots[name]["type"]
        try:
            slot_pattern = _SLOT_PATTERNS[slot_type]
        except KeyError as exc:
            raise B0Error(f"unsupported B0 slot type: {slot_type!r}") from exc
        pattern_parts.append(f"(?P<{name}>{slot_pattern})")
        order.append(name)
        cursor = placeholder.end()
    pattern_parts.append(_literal_pattern(seed[cursor:]))
    pattern_parts.append(r"\Z")
    try:
        return re.compile("".join(pattern_parts), re.IGNORECASE), tuple(order)
    except re.error as exc:
        raise B0Error(f"unable to compile template {template['id']}: {exc}") from exc


def _literal_tokens(seed: str) -> tuple[str, ...]:
    literal = PLACEHOLDER_RE.sub(" ", seed)
    normalized = unicodedata.normalize("NFKC", literal).casefold()
    return tuple(_TOKEN_RE.findall(normalized))


def compile_template_snapshot(
    path: Path,
    policy: B0Policy,
) -> tuple[CompiledTemplate, ...]:
    """Validate and compile one exact template-library snapshot.

    Args:
        path: Template YAML snapshot to read.
        policy: Effective matching and abstention policy.

    Returns:
        Deterministically ordered compiled templates.

    Raises:
        B0Error: If inputs are invalid or the snapshot cannot be compiled.
        TemplateValidationError: If the template library violates its schema.
    """
    if not isinstance(path, Path):
        raise B0Error("template path must be a Path")
    if not isinstance(policy, B0Policy):
        raise B0Error("B0 policy is invalid")
    try:
        snapshot = path.read_bytes()
    except OSError as exc:
        raise B0Error(f"unable to read template snapshot: {exc}") from exc
    try:
        templates = json.loads(snapshot.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise TemplateValidationError(f"Invalid template encoding: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TemplateValidationError(f"Invalid template JSON: {path}") from exc
    if not isinstance(templates, list):
        raise TemplateValidationError("Template library must contain a list")
    validate_template_library(templates)
    fingerprint = hashlib.sha256(snapshot).hexdigest()
    compiled: list[CompiledTemplate] = []
    for template in templates:
        pattern, order = _compile_seed(template)
        tokens = _literal_tokens(template["nl_seed"])
        compiled.append(
            CompiledTemplate(
                template_id=template["id"],
                raw=MappingProxyType(template.copy()),
                seed_pattern=pattern,
                slot_order=order,
                literal_tokens=tokens,
                literal_token_count=len(tokens),
                schema_elements=tuple(template["schema_elements"]),
                cq_ids=tuple(template["cq_ids"]),
                template_sha256=fingerprint,
            )
        )
    return tuple(sorted(compiled, key=lambda row: (-row.literal_token_count, row.template_id)))
