"""Reviewed Vietnamese aliases bound to canonical English SQL/linker targets."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from nl2sparql.language import normalize_input
from nl2sparql.linking.schema.contracts import SchemaDocumentError

BILINGUAL_ALIASES_PATH = Path(__file__).with_name("bilingual_aliases.json")


@dataclass(frozen=True, slots=True)
class BilingualAliasCatalog:
    """NFC Vietnamese aliases grouped by unchanged canonical target ID."""

    schema: Mapping[str, tuple[str, ...]]
    entity: Mapping[str, tuple[str, ...]]
    schema_unaccented: Mapping[str, tuple[str, ...]]
    entity_unaccented: Mapping[str, tuple[str, ...]]
    source_bytes: bytes
    sha256: str


def _alias_groups(
    raw: object, label: str
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    if not isinstance(raw, dict):
        raise SchemaDocumentError(f"bilingual {label} aliases must be an object")
    accented: dict[str, tuple[str, ...]] = {}
    unaccented: dict[str, tuple[str, ...]] = {}
    owners: dict[str, str] = {}
    for target, values in sorted(raw.items()):
        if (
            not isinstance(target, str)
            or not target.strip()
            or not isinstance(values, list)
            or not values
        ):
            raise SchemaDocumentError(f"bilingual {label} alias target is invalid")
        normalized_values: list[str] = []
        folded_values: list[str] = []
        for value in values:
            if not isinstance(value, str) or value != unicodedata.normalize("NFC", value):
                raise SchemaDocumentError("Vietnamese aliases must be NFC-normalized strings")
            normalized = normalize_input(value, language="vi")
            if normalized.nfc != value.strip() or normalized.match != value.casefold():
                raise SchemaDocumentError("Vietnamese aliases must use canonical whitespace")
            for phrase in (normalized.match, normalized.accent_folded):
                previous = owners.get(phrase)
                if previous is not None and previous != target:
                    raise SchemaDocumentError(
                        f"bilingual alias {phrase!r} belongs to multiple {label} targets"
                    )
                owners[phrase] = target
            normalized_values.append(normalized.match)
            folded_values.append(normalized.accent_folded)
        if len(set(normalized_values)) != len(normalized_values):
            raise SchemaDocumentError(f"bilingual {label} aliases must be unique per target")
        accented[target] = tuple(sorted(normalized_values))
        unaccented[target] = tuple(sorted(set(folded_values)))
    return accented, unaccented


def load_bilingual_aliases(
    path: Path = BILINGUAL_ALIASES_PATH,
    *,
    snapshot: bytes | None = None,
) -> BilingualAliasCatalog:
    """Load and validate the reviewed bilingual alias catalog from one snapshot."""
    if snapshot is None:
        try:
            snapshot = path.read_bytes()
        except OSError as exc:
            raise SchemaDocumentError(f"unable to read bilingual aliases {path}: {exc}") from exc
    try:
        raw = json.loads(snapshot)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaDocumentError(f"invalid bilingual aliases: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "schema", "entity"}:
        raise SchemaDocumentError("bilingual alias catalog fields are invalid")
    if raw["schema_version"] != 1:
        raise SchemaDocumentError("bilingual alias schema version mismatch")
    schema, schema_unaccented = _alias_groups(raw["schema"], "schema")
    entity, entity_unaccented = _alias_groups(raw["entity"], "entity")
    return BilingualAliasCatalog(
        schema=MappingProxyType(schema),
        entity=MappingProxyType(entity),
        schema_unaccented=MappingProxyType(schema_unaccented),
        entity_unaccented=MappingProxyType(entity_unaccented),
        source_bytes=snapshot,
        sha256=hashlib.sha256(snapshot).hexdigest(),
    )
