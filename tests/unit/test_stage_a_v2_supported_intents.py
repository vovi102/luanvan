"""Approved coverage revision must not rewrite historical research inputs."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from nl2sparql.dataset.templates import load_templates, validate_template_library
from nl2sparql.sql.schema import CATALOG_PATH, SchemaCatalogError, load_catalog, validate_catalog

ROOT = Path(__file__).resolve().parents[2]
REVISION = CATALOG_PATH.with_name("ethereum_analytics_stage_a_v2.json")
REPLACEMENTS = {
    "owner_net_native_flow": ("T_OWNER_NET_NATIVE_FLOW", "CQ32"),
    "treasury_native_counterparty_concentration": ("T_TREASURY_NATIVE_COUNTERPARTY_CONCENTRATION", "CQ33"),
    "treasury_token_counterparty_diversity": ("T_TREASURY_TOKEN_COUNTERPARTY_DIVERSITY", "CQ34"),
}


def test_catalogue_revision_preserves_historical_inputs():
    assert hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest() == "db8393aa7258d1331387eff9825e22ca729daf93234419f00d7dd538196cb3dd"
    old, new = load_catalog(), load_catalog(REVISION)
    assert new["catalog_version"] == "1.1.0"
    assert new["competency_questions"][:30] == old["competency_questions"]
    assert validate_catalog(new).competency_question_count == 34
    for version, count in [("1.0.0", 34), ("1.1.0", 30)]:
        invalid = deepcopy(new)
        invalid["catalog_version"] = version
        invalid["competency_questions"] = new["competency_questions"][:count]
        with pytest.raises(SchemaCatalogError, match="exactly CQ01"):
            validate_catalog(invalid)


def test_replacements_match_audited_sql_and_cqs():
    templates = {t["id"]: t for t in load_templates()}
    audit = json.loads((ROOT / "docs/evidence/stage-a-v2-hard-intent-coverage-audit.json").read_text())
    probes = {p["name"]: p for p in audit["executions"]}
    for probe, (template_id, cq) in REPLACEMENTS.items():
        template = templates[template_id]
        sql = probes[probe]["sql"]
        expected = sql.replace("2026-06-15", "{start_date}").replace("2026-06-16", "{end_date}").replace("LIMIT 3", "LIMIT {n}")
        assert template["sql_template"] == expected
        assert template["expected_columns"] == probes[probe]["columns"]
        assert template["cq_ids"] == [cq]
        assert set(template["slots"]) == {"start_date", "end_date", "n"}
        assert template["difficulty"] == "hard"
    assert len(templates) == 25
    validate_template_library(list(templates.values()))


def test_funding_requires_successful_positive_value_without_causal_claims():
    template = next(t for t in load_templates() if t["id"] == "T_TOKEN_AFTER_NATIVE_FUNDING")
    assert "value_wei > 0" in template["sql_template"]
    assert "receipt_status = 1" in template["sql_template"]
    assert "transfers.block_timestamp >= funding.block_timestamp" in template["sql_template"]
    assert template["cq_ids"] == ["CQ31"]
    assert len(template["expected_columns"]) == 6
