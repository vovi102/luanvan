"""Deterministic T3.2 GoogleSQL Stage A candidate generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from nl2sparql.dataset.templates import (
    TEMPLATES_PATH,
    render_template,
    validate_template_library,
)
from nl2sparql.dataset.templates import (
    load_templates as load_template_library,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATES_PATH = TEMPLATES_PATH
DEFAULT_VALUE_POOLS_PATH = Path(__file__).with_name("stage_a") / "value_pools.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/dataset/raw/synthetic-stage-a.jsonl"
DEFAULT_STATS_PATH = PROJECT_ROOT / "data/dataset/raw/stats.md"
TARGET_COUNT = 1000
GENERATION_SEED = 42
MAX_TEMPLATE_COUNT = 100
MAX_ENTITY_COUNT = 50
DIFFICULTY_ALLOCATION = {"easy": 350, "medium": 450, "hard": 200}
TEMPLATE_ALLOCATION = {
    "T_COUNT_TX_IN_RANGE": 59,
    "T_LIST_TX_FROM_ACCOUNT": 59,
    "T_LIST_TX_TO_ACCOUNT": 58,
    "T_FILTER_TX_BY_VALUE": 58,
    "T_LIST_FAILED_TX": 58,
    "T_LIST_KNOWN_EXCHANGES": 58,
    "T_TOP_SENDERS_BY_VALUE": 57,
    "T_TOP_RECIPIENTS_BY_COUNT": 57,
    "T_TX_GROUPED_BY_OWNER": 56,
    "T_TOKEN_VOLUME_BY_SYMBOL": 56,
    "T_TOKEN_TRANSFERS_OF_TOKEN": 56,
    "T_FAILED_HIGH_GAS_TX": 56,
    "T_ACCOUNTS_BY_CATEGORY": 56,
    "T_TX_BY_HOUR": 56,
    "T_TOKEN_AFTER_NATIVE_FUNDING": 100,
    "T_REPEATED_PAIR_FLOW": 100,
}
ENTITY_SLOT_TYPES = {
    "ethereum_address",
    "transaction_hash",
    "token_symbol",
    "entity_owner",
    "entity_category",
    "concept_class",
}
RECORD_FIELDS = {
    "id",
    "template_id",
    "category",
    "difficulty",
    "slot_values",
    "entities_used",
    "sql",
    "nl_seed",
    "schema_elements",
    "cq_ids",
    "template_sha256",
    "record_sha256",
    "generation_seed",
    "witness_group_id",
    "verification",
}


class StageAGenerationError(ValueError):
    """Raised when candidate generation violates the accepted Stage A contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def load_templates(path: Path = DEFAULT_TEMPLATES_PATH) -> list[dict[str, Any]]:
    """Compatibility wrapper around the active T3.1 template loader."""
    return load_template_library(path)


def load_value_pools(path: Path = DEFAULT_VALUE_POOLS_PATH) -> dict[str, Any]:
    """Load and validate immutable, provenance-bearing generation values."""
    try:
        pools = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageAGenerationError(f"Unable to load value pools: {path}") from exc
    if not isinstance(pools, dict) or pools.get("version") != 1:
        raise StageAGenerationError("Value pools must use version 1")
    if pools.get("window") != {
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }:
        raise StageAGenerationError("Value pools must pin the accepted June 2026 window")
    for slot_type, minimum in (("ethereum_address", 4), ("token_symbol", 2)):
        values = pools.get(slot_type)
        if not isinstance(values, list) or len(values) < minimum:
            raise StageAGenerationError(f"Value pool {slot_type} requires {minimum} entries")
        for item in values:
            if not isinstance(item, dict) or set(item) != {"value", "source", "evidence"}:
                raise StageAGenerationError(f"Invalid provenance entry in {slot_type} pool")
            if not all(isinstance(item[key], str) and item[key] for key in item):
                raise StageAGenerationError(f"Empty provenance entry in {slot_type} pool")
    return pools


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
    raise StageAGenerationError(f"Unable to create {count} distinct bounded date windows")


def _pool_slots(template: Mapping[str, Any]) -> list[str]:
    return [
        name
        for name, definition in template["slots"].items()
        if definition["type"] in {"ethereum_address", "token_symbol"}
    ]


def _variant_fill(
    template: Mapping[str, Any],
    index: int,
    count: int,
    pools: Mapping[str, Any],
) -> dict[str, Any]:
    fill = dict(template["example_fill"])
    if template["id"] == "T_COUNT_TX_IN_RANGE":
        fill["start_date"], fill["end_date"] = _count_windows(count)[index]
        return fill
    pool_slots = _pool_slots(template)
    divisor = 1
    for name in pool_slots:
        slot_type = template["slots"][name]["type"]
        entries = pools[slot_type]
        fill[name] = entries[index % len(entries)]["value"]
        divisor *= len(entries)
    if "n" in template["slots"]:
        fill["n"] = index // divisor + 1
    return fill


def _entities_used(
    template: Mapping[str, Any], slot_values: Mapping[str, Any]
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for slot, definition in template["slots"].items():
        slot_type = definition["type"]
        if slot_type in ENTITY_SLOT_TYPES:
            entities.append({"slot": slot, "type": slot_type, "value": slot_values[slot]})
    return entities


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


def generate_stage_a_records(
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    target_count: int = TARGET_COUNT,
    seed: int = GENERATION_SEED,
) -> list[dict[str, Any]]:
    """Render the accepted deterministic Stage A candidate population."""
    if target_count != TARGET_COUNT:
        raise StageAGenerationError("Stage A generation requires exactly 1000 records")
    if seed != GENERATION_SEED:
        raise StageAGenerationError("Stage A generation requires seed 42")
    values = list(templates)
    validate_template_library(values)
    templates_by_id = {template["id"]: template for template in values}
    missing = set(TEMPLATE_ALLOCATION) - set(templates_by_id)
    if missing:
        raise StageAGenerationError(f"Missing allocated templates: {sorted(missing)}")
    records: list[dict[str, Any]] = []
    for template_id, count in TEMPLATE_ALLOCATION.items():
        template = templates_by_id[template_id]
        template_sha256 = _sha256(template)
        for index in range(count):
            slot_values = _variant_fill(template, index, count, pools)
            record: dict[str, Any] = {
                "id": f"syn-{len(records):06d}",
                "template_id": template_id,
                "category": template["category"],
                "difficulty": template["difficulty"],
                "slot_values": slot_values,
                "entities_used": _entities_used(template, slot_values),
                "sql": render_template(template, slot_values),
                "nl_seed": template["nl_seed"].format(**slot_values),
                "schema_elements": list(template["schema_elements"]),
                "cq_ids": list(template["cq_ids"]),
                "template_sha256": template_sha256,
                "generation_seed": seed,
                "witness_group_id": _witness_group_id(template_id, slot_values),
                "verification": None,
            }
            record["record_sha256"] = _record_hash(record)
            records.append(record)
    validate_stage_a_records(records, values)
    return records


def validate_stage_a_records(
    records: Sequence[dict[str, Any]], templates: Sequence[dict[str, Any]]
) -> None:
    """Fail closed if candidate records drift from the accepted contract."""
    if len(records) != TARGET_COUNT:
        raise StageAGenerationError(f"Expected exactly 1000 records, received {len(records)}")
    templates_by_id = {template["id"]: template for template in templates}
    if any(set(record) != RECORD_FIELDS for record in records):
        raise StageAGenerationError("Stage A record fields do not match the SQL contract")
    ids = [record["id"] for record in records]
    sql_values = [record["sql"] for record in records]
    hashes = [record["record_sha256"] for record in records]
    if len(set(ids)) != len(ids):
        raise StageAGenerationError("Stage A records require unique IDs")
    if len(set(sql_values)) != len(sql_values):
        raise StageAGenerationError("Stage A records require unique SQL")
    if len(set(hashes)) != len(hashes):
        raise StageAGenerationError("Stage A records require unique record hashes")
    template_counts = Counter(record["template_id"] for record in records)
    difficulty_counts = Counter(record["difficulty"] for record in records)
    if template_counts != TEMPLATE_ALLOCATION:
        raise StageAGenerationError("Stage A template allocation does not match contract")
    if difficulty_counts != DIFFICULTY_ALLOCATION:
        raise StageAGenerationError("Stage A difficulty allocation does not match contract")
    if max(template_counts.values()) > MAX_TEMPLATE_COUNT:
        raise StageAGenerationError("A template exceeds the 10% cap")
    entity_counts = Counter(
        entity["value"] for record in records for entity in record["entities_used"]
    )
    if entity_counts and max(entity_counts.values()) > MAX_ENTITY_COUNT:
        raise StageAGenerationError("An entity exceeds the 5% cap")
    for record in records:
        template = templates_by_id.get(record["template_id"])
        if template is None:
            raise StageAGenerationError(f"Unknown template: {record['template_id']}")
        if record["sql"] != render_template(template, record["slot_values"]):
            raise StageAGenerationError(f"Rendered SQL drift for {record['id']}")
        if record["template_sha256"] != _sha256(template):
            raise StageAGenerationError(f"Template hash drift for {record['id']}")
        if record["record_sha256"] != _record_hash(record):
            raise StageAGenerationError(f"Record hash drift for {record['id']}")
        if record["generation_seed"] != GENERATION_SEED:
            raise StageAGenerationError(f"Generation seed drift for {record['id']}")
        expected_group = _witness_group_id(record["template_id"], record["slot_values"])
        if record["witness_group_id"] != expected_group:
            raise StageAGenerationError(f"Witness group drift for {record['id']}")


def write_jsonl(records: Sequence[dict[str, Any]], output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    """Write records as canonical JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(_canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return output_path


def write_stats(records: Sequence[dict[str, Any]], stats_path: Path = DEFAULT_STATS_PATH) -> Path:
    """Write candidate distribution statistics."""
    difficulties = Counter(record["difficulty"] for record in records)
    templates = Counter(record["template_id"] for record in records)
    lines = ["# Synthetic Stage A Stats", "", f"Records: {len(records)}", ""]
    lines.extend(
        ["## Difficulty", ""] + [f"- {key}: {value}" for key, value in sorted(difficulties.items())]
    )
    lines.extend(
        ["", "## Templates", ""] + [f"- {key}: {value}" for key, value in sorted(templates.items())]
    )
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES_PATH)
    parser.add_argument("--value-pools", type=Path, default=DEFAULT_VALUE_POOLS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    records = generate_stage_a_records(
        load_templates(args.templates),
        load_value_pools(args.value_pools),
    )
    write_jsonl(records, args.output)
    print(f"Wrote {len(records)} deterministic candidates to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
