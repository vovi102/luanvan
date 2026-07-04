"""Offline scaffold for T3.2 synthetic Stage A generation."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATES_PATH = PROJECT_ROOT / "src/nl2sparql/dataset/templates/templates.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/dataset/raw/synthetic-stage-a.jsonl"
DEFAULT_STATS_PATH = PROJECT_ROOT / "data/dataset/raw/stats.md"


def load_templates(path: Path = DEFAULT_TEMPLATES_PATH) -> list[dict[str, Any]]:
    """Load query templates from JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def _variant_fill(template: dict[str, Any], variant: int) -> dict[str, Any]:
    fill = dict(template["example_fill"])
    if "n" in template["slots"]:
        fill["n"] = [5, 10, 20, 50, 100][variant % 5]
    if "value_wei" in template["slots"]:
        fill["value_wei"] = ["1000000000000000000", "10000000000000000000"][
            variant % 2
        ]
    if "start_date" in template["slots"]:
        fill["start_date"] = ["2024-01-01", "2024-01-15", "2024-02-01"][variant % 3]
        fill["end_date"] = ["2024-02-01", "2024-02-15", "2024-03-01"][variant % 3]
    return fill


def _entities_used(slot_values: dict[str, Any]) -> list[dict[str, Any]]:
    entities = []
    for slot, value in slot_values.items():
        if isinstance(value, str) and value.startswith("<https://thesis.example.org/eth-kg/"):
            entities.append({"slot": slot, "type": "iri", "value": value})
    return entities


def generate_stage_a_records(
    templates: Sequence[dict[str, Any]],
    target_count: int = 1000,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Render deterministic offline Stage A records from templates."""
    rng = random.Random(seed)
    ordered_templates = list(templates)
    rng.shuffle(ordered_templates)
    cap = max(1, target_count // 10)
    counts: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    variant = 0
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    while len(records) < target_count:
        progressed = False
        for template in ordered_templates:
            if counts[template["id"]] >= cap:
                continue
            slot_values = _variant_fill(template, variant)
            sparql = (
                template["sparql_template"].format(**slot_values)
                + f"\n# synthetic_variant_{variant}"
            )
            if any(record["sparql"] == sparql for record in records):
                variant += 1
                continue
            nl_seed = template["nl_seed"].format(**slot_values)
            record_id = f"syn-{len(records):06d}"
            records.append(
                {
                    "id": record_id,
                    "template_id": template["id"],
                    "difficulty": template["difficulty"],
                    "slot_values": slot_values,
                    "entities_used": _entities_used(slot_values),
                    "sparql": sparql,
                    "nl_seed": nl_seed,
                    "result_preview": [],
                    "result_count": None,
                    "execution_time_ms": None,
                    "verified_at": generated_at,
                    "verification_mode": "offline_render_only",
                }
            )
            counts[template["id"]] += 1
            variant += 1
            progressed = True
            if len(records) >= target_count:
                break
        if not progressed:
            raise ValueError(
                f"Cannot generate {target_count} unique records with 10% template cap"
            )
    return records


def write_jsonl(records: Sequence[dict[str, Any]], output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    """Write generated records as JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return output_path


def write_stats(records: Sequence[dict[str, Any]], stats_path: Path = DEFAULT_STATS_PATH) -> Path:
    """Write a markdown stats report for generated records."""
    difficulties = Counter(record["difficulty"] for record in records)
    templates = Counter(record["template_id"] for record in records)
    lines = [
        "# Synthetic Stage A Stats",
        "",
        f"Records: {len(records)}",
        "Verification mode: offline_render_only",
        "",
        "## Difficulty",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(difficulties.items()))
    lines.extend(["", "## Templates", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(templates.items()))
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS_PATH)
    parser.add_argument("--target-count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate offline Stage A scaffold records."""
    args = parse_args(argv)
    records = generate_stage_a_records(
        load_templates(args.templates),
        target_count=args.target_count,
        seed=args.seed,
    )
    write_jsonl(records, args.output)
    write_stats(records, args.stats)
    print(f"Wrote {len(records)} records to {args.output}")
    print(f"Stats: {args.stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
