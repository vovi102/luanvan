"""Behavior and historical-input compatibility of the approved CQ35 correction."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a.evidence import build_witness_groups
from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries
from nl2sparql.dataset.stage_a_v2 import generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates, render_template, validate_template_library
from nl2sparql.sql.schema import (
    CATALOG_PATH,
    TRAINING_CATALOG_PATH,
    SchemaCatalogError,
    load_catalog,
    validate_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_TEMPLATES = ROOT / "tests/fixtures/dataset/stage-a-v2-pre-cq35-templates.json"


def test_active_training_revision_accepts_cq35_and_preserves_old_catalogues():
    assert (
        hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
        == "db8393aa7258d1331387eff9825e22ca729daf93234419f00d7dd538196cb3dd"
    )
    previous = CATALOG_PATH.with_name("ethereum_analytics_stage_a_v2.json")
    assert (
        hashlib.sha256(previous.read_bytes()).hexdigest()
        == "2c800d4c1af74f24aed73bcb7881f1cd514ab068fecdb301d6c478fd3ce34fa0"
    )
    active = load_catalog(TRAINING_CATALOG_PATH)
    assert hashlib.sha256(TRAINING_CATALOG_PATH.read_bytes()).hexdigest() == (
        "37101b56dbb7fb0ad135b73f2aafdf66e44a9a2c00ab0963ad45569969f057f5"
    )
    assert active["catalog_version"] == "1.2.0"
    assert validate_catalog(active).competency_question_count == 35
    assert active["competency_questions"][:34] == load_catalog(previous)["competency_questions"]
    for version, count in [("1.2.0", 34), ("1.1.0", 35), ("1.0.0", 35)]:
        invalid = deepcopy(active)
        invalid["catalog_version"] = version
        invalid["competency_questions"] = invalid["competency_questions"][:count]
        with pytest.raises(SchemaCatalogError, match="exactly CQ01"):
            validate_catalog(invalid)


def test_class_fill_matches_audited_production_witness_without_new_predicates():
    templates = load_templates()
    template = next(t for t in templates if t["id"] == "T_LARGE_TX_TO_CLASS")
    audit = json.loads(
        (ROOT / "docs/evidence/stage-a-v2-large-class-coverage-audit.json").read_text()
    )
    witness = next(
        e for e in audit["executions"] if e["name"] == "production_witness_BridgeProtocol"
    )
    fill = {**template["example_fill"], "n": 1}
    assert fill == {
        "concept_class": "BridgeProtocol",
        "value_wei": "1000000000000000000",
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
        "n": 1,
    }
    assert render_template(template, fill) == witness["sql"]
    assert template["expected_columns"] == witness["columns"]
    assert template["cq_ids"] == ["CQ35"]
    assert template["difficulty"] == "medium"
    validate_template_library(templates)


def test_generation_changes_only_41_class_records_and_preserves_topology():
    pools = load_value_pools(ROOT / "data/dataset/raw/stage-a-v2-evidence-pools.json")
    old = generate_stage_a_v2_records(load_templates(HISTORICAL_TEMPLATES), pools)
    new = generate_stage_a_v2_records(load_templates(), pools)
    changed = [n["id"] for o, n in zip(old, new, strict=True) if o != n]
    assert changed == [f"syn-v2-{i:06d}" for i in range(759, 800)]
    assert len(new) == 1000
    assert len(build_witness_groups(new)) == 206
    assert len(build_stage_a_v2_witness_queries(new)) == 126


def test_bilingual_class_questions_describe_native_value_not_successful_movement():
    entries = json.loads((ROOT / "src/nl2sparql/dataset/bilingual/templates.json").read_text())[
        "entries"
    ]
    selected = [e for e in entries if e["template_id"] == "T_LARGE_TX_TO_CLASS"]
    assert len(selected) == 8
    for entry in selected:
        text = entry["pattern"].casefold()
        if entry["language"] == "en":
            assert "native value" in text
            assert "moved" not in text and "transfers" not in text
        else:
            assert "giá trị native" in text
            assert "chuyển" not in text
