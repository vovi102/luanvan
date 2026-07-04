"""Tests for the T3.2 offline synthetic generation scaffold."""

from __future__ import annotations

import json
from pathlib import Path

from nl2sparql.dataset.generate import (
    generate_stage_a_records,
    load_templates,
    write_jsonl,
    write_stats,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_PATH = ROOT / "src/nl2sparql/dataset/templates/templates.json"


def test_generate_stage_a_records_is_deterministic_and_schema_complete() -> None:
    templates = load_templates(TEMPLATES_PATH)

    first = generate_stage_a_records(templates, target_count=30, seed=42)
    second = generate_stage_a_records(templates, target_count=30, seed=42)

    assert first == second
    assert len(first) == 30
    assert len({record["id"] for record in first}) == 30
    assert len({record["sparql"] for record in first}) == 30
    for record in first:
        assert {
            "id",
            "template_id",
            "difficulty",
            "slot_values",
            "entities_used",
            "sparql",
            "nl_seed",
            "result_preview",
            "result_count",
            "execution_time_ms",
            "verified_at",
            "verification_mode",
        } <= set(record)
        assert record["verification_mode"] == "offline_render_only"
        assert record["result_count"] is None
        assert record["execution_time_ms"] is None


def test_generate_stage_a_records_caps_template_frequency() -> None:
    templates = load_templates(TEMPLATES_PATH)
    records = generate_stage_a_records(templates, target_count=50, seed=42)
    counts: dict[str, int] = {}
    for record in records:
        counts[record["template_id"]] = counts.get(record["template_id"], 0) + 1

    assert max(counts.values()) <= 5


def test_write_jsonl_and_stats(tmp_path: Path) -> None:
    records = generate_stage_a_records(load_templates(TEMPLATES_PATH), target_count=10, seed=42)
    jsonl_path = write_jsonl(records, tmp_path / "synthetic-stage-a.jsonl")
    stats_path = write_stats(records, tmp_path / "stats.md")

    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    stats = stats_path.read_text(encoding="utf-8")

    assert rows == records
    assert "Synthetic Stage A Stats" in stats
    assert "offline_render_only" in stats
