"""Deterministic 25-intent Stage A v2 candidate generation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from nl2sparql.dataset.generate import (
    ENTITY_SLOT_TYPES,
    GENERATION_SEED,
    MAX_ENTITY_COUNT,
    MAX_TEMPLATE_COUNT,
    RECORD_FIELDS,
    TARGET_COUNT,
)
from nl2sparql.dataset.templates import render_template, validate_template_library

V2_DIFFICULTY_ALLOCATION = {"easy": 350, "medium": 450, "hard": 200}
V2_TEMPLATE_ALLOCATION = {
    "T_COUNT_TX_IN_RANGE": 45,
    "T_LIST_TX_FROM_ACCOUNT": 40,
    "T_LIST_TX_TO_ACCOUNT": 40,
    "T_FILTER_TX_BY_VALUE": 45,
    "T_LIST_FAILED_TX": 45,
    "T_BLOCK_BY_NUMBER": 45,
    "T_TX_BY_HASH": 45,
    "T_LIST_KNOWN_EXCHANGES": 45,
    "T_TOP_SENDERS_BY_VALUE": 42,
    "T_TOP_RECIPIENTS_BY_COUNT": 41,
    "T_TX_BETWEEN_ACCOUNTS": 40,
    "T_TX_GROUPED_BY_OWNER": 41,
    "T_TOKEN_VOLUME_BY_SYMBOL": 41,
    "T_TOKEN_TRANSFERS_OF_TOKEN": 41,
    "T_FAILED_HIGH_GAS_TX": 41,
    "T_BLOCKS_BY_VALIDATOR": 40,
    "T_ACCOUNTS_BY_CATEGORY": 41,
    "T_TX_BY_HOUR": 41,
    "T_LARGE_TX_TO_CLASS": 41,
    "T_EXCHANGE_TO_DEX_FLOW": 34,
    "T_MIXER_TO_DEX_LARGE_FLOW": 34,
    "T_TOKEN_AFTER_NATIVE_FUNDING": 33,
    "T_CROSS_EXCHANGE_FLOW": 33,
    "T_BRIDGE_OUTFLOW_AFTER_EXCHANGE": 33,
    "T_REPEATED_PAIR_FLOW": 33,
}


class StageAV2GenerationError(ValueError):
    """Raised when Stage A v2 candidate generation violates its contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _count_windows(count: int) -> list[tuple[str, str]]:
    first = date(2026, 6, 1)
    boundary = date(2026, 7, 1)
    windows: list[tuple[str, str]] = []
    for span_days in range(1, 32):
        start = first
        while start + timedelta(days=span_days) <= boundary:
            windows.append((start.isoformat(), (start + timedelta(days=span_days)).isoformat()))
            start += timedelta(days=1)
            if len(windows) == count:
                return windows
    raise StageAV2GenerationError(f"Unable to create {count} distinct bounded date windows")


def _pool_slot_names(template: Mapping[str, Any]) -> list[str]:
    return [
        name
        for name, definition in template["slots"].items()
        if definition["type"] in {"ethereum_address", "token_symbol"}
    ]


def _variant_fill(
    template: Mapping[str, Any], index: int, count: int, pools: Mapping[str, Any]
) -> dict[str, Any]:
    fill = dict(template["example_fill"])
    template_id = str(template["id"])
    if template_id == "T_COUNT_TX_IN_RANGE":
        fill["start_date"], fill["end_date"] = _count_windows(count)[index]
        return fill
    if template_id == "T_BLOCK_BY_NUMBER":
        fill["block_number"] = int(fill["block_number"]) + index
    if template_id == "T_TX_BY_HASH":
        digest = hashlib.sha256(f"stage-a-v2:{GENERATION_SEED}:{index}".encode()).hexdigest()
        fill["transaction_hash"] = f"0x{digest}"

    pool_period = 1
    for offset, name in enumerate(_pool_slot_names(template)):
        slot_type = template["slots"][name]["type"]
        entries = pools.get(slot_type)
        if not isinstance(entries, list) or not entries:
            raise StageAV2GenerationError(f"Missing non-empty value pool for {slot_type}")
        entry = entries[(index + offset) % len(entries)]
        if not isinstance(entry, Mapping) or not isinstance(entry.get("value"), str):
            raise StageAV2GenerationError(f"Invalid value pool entry for {slot_type}")
        fill[name] = entry["value"]
        pool_period = math.lcm(pool_period, len(entries))
    if "n" in template["slots"]:
        fill["n"] = index // pool_period + 1
    return fill


def _entities_used(
    template: Mapping[str, Any], slot_values: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [
        {"slot": name, "type": definition["type"], "value": slot_values[name]}
        for name, definition in template["slots"].items()
        if definition["type"] in ENTITY_SLOT_TYPES
    ]


def _witness_group_id(template_id: str, slot_values: Mapping[str, Any]) -> str:
    grouped_values = {key: value for key, value in slot_values.items() if key != "n"}
    return _sha256({"template_id": template_id, "slot_values": grouped_values})


def _record_hash(record: Mapping[str, Any]) -> str:
    return _sha256(
        {
            key: value
            for key, value in record.items()
            if key not in {"record_sha256", "verification"}
        }
    )


def generate_stage_a_v2_records(
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    target_count: int = TARGET_COUNT,
    seed: int = GENERATION_SEED,
) -> list[dict[str, Any]]:
    """Render the deterministic offline Stage A v2 candidate population."""
    if target_count != TARGET_COUNT:
        raise StageAV2GenerationError("Stage A v2 generation requires exactly 1000 records")
    if seed != GENERATION_SEED:
        raise StageAV2GenerationError("Stage A v2 generation requires seed 42")
    values = list(templates)
    validate_template_library(values)
    templates_by_id = {str(template["id"]): template for template in values}
    if set(templates_by_id) != set(V2_TEMPLATE_ALLOCATION):
        raise StageAV2GenerationError("Stage A v2 allocation must cover all production templates")

    records: list[dict[str, Any]] = []
    for template_id, count in V2_TEMPLATE_ALLOCATION.items():
        template = templates_by_id[template_id]
        template_sha256 = _sha256(template)
        for index in range(count):
            slot_values = _variant_fill(template, index, count, pools)
            record: dict[str, Any] = {
                "id": f"syn-v2-{len(records):06d}",
                "template_id": template_id,
                "category": template["category"],
                "difficulty": template["difficulty"],
                "slot_values": slot_values,
                "entities_used": _entities_used(template, slot_values),
                "sql": render_template(template, slot_values),
                "nl_seed": str(template["nl_seed"]).format(**slot_values),
                "schema_elements": list(template["schema_elements"]),
                "cq_ids": list(template["cq_ids"]),
                "template_sha256": template_sha256,
                "record_sha256": "",
                "generation_seed": seed,
                "witness_group_id": _witness_group_id(template_id, slot_values),
                "verification": None,
            }
            record["record_sha256"] = _record_hash(record)
            records.append(record)
    validate_stage_a_v2_records(records, values)
    return records


def validate_stage_a_v2_records(
    records: Sequence[dict[str, Any]], templates: Sequence[dict[str, Any]]
) -> None:
    """Fail closed if Stage A v2 records drift from the 25-intent contract."""
    if len(records) != TARGET_COUNT:
        raise StageAV2GenerationError(f"Expected exactly 1000 v2 records, received {len(records)}")
    if any(set(record) != RECORD_FIELDS for record in records):
        raise StageAV2GenerationError("Stage A v2 record fields do not match the SQL contract")
    templates_by_id = {str(template["id"]): template for template in templates}
    template_counts = Counter(str(record["template_id"]) for record in records)
    difficulty_counts = Counter(str(record["difficulty"]) for record in records)
    if template_counts != V2_TEMPLATE_ALLOCATION:
        raise StageAV2GenerationError("Stage A v2 template allocation does not match contract")
    if difficulty_counts != V2_DIFFICULTY_ALLOCATION:
        raise StageAV2GenerationError("Stage A v2 difficulty allocation does not match contract")
    if max(template_counts.values()) > MAX_TEMPLATE_COUNT:
        raise StageAV2GenerationError("A Stage A v2 template exceeds the 10% cap")

    ids = [str(record["id"]) for record in records]
    sql_values = [str(record["sql"]) for record in records]
    hashes = [str(record["record_sha256"]) for record in records]
    if len(set(ids)) != len(ids):
        raise StageAV2GenerationError("Stage A v2 records require unique IDs")
    if len(set(sql_values)) != len(sql_values):
        raise StageAV2GenerationError("Stage A v2 records require unique SQL")
    if len(set(hashes)) != len(hashes):
        raise StageAV2GenerationError("Stage A v2 records require unique record hashes")
    entity_counts = Counter(
        entity["value"] for record in records for entity in record["entities_used"]
    )
    if entity_counts and max(entity_counts.values()) > MAX_ENTITY_COUNT:
        raise StageAV2GenerationError("A Stage A v2 entity exceeds the 5% cap")

    for record in records:
        record_id = str(record["id"])
        template = templates_by_id.get(str(record["template_id"]))
        if template is None:
            raise StageAV2GenerationError(f"Unknown Stage A v2 template for {record_id}")
        if record["sql"] != render_template(template, record["slot_values"]):
            raise StageAV2GenerationError(f"Rendered SQL drift for {record_id}")
        if record["template_sha256"] != _sha256(template):
            raise StageAV2GenerationError(f"Template hash drift for {record_id}")
        if record["record_sha256"] != _record_hash(record):
            raise StageAV2GenerationError(f"Stage A v2 record hash drift for {record_id}")
        if record["generation_seed"] != GENERATION_SEED:
            raise StageAV2GenerationError(f"Generation seed drift for {record_id}")
        expected_group = _witness_group_id(str(record["template_id"]), record["slot_values"])
        if record["witness_group_id"] != expected_group:
            raise StageAV2GenerationError(f"Witness group drift for {record_id}")


def serialize_stage_a_v2_records(records: Sequence[Mapping[str, Any]]) -> bytes:
    """Serialize Stage A v2 rows as canonical UTF-8 JSONL."""
    return "".join(_canonical_json(record) + "\n" for record in records).encode()
