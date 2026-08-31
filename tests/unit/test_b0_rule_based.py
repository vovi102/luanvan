from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl2sparql.dataset.templates import TEMPLATES_PATH
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.linking.schema_linker import LinkResult, SchemaMatch
from nl2sparql.models.b0_rule_based import B0Error, BaselineB0

ADDRESS = "0x1111111111111111111111111111111111111111"


class _SchemaLinker:
    def __init__(self, element_id: str) -> None:
        self.element_id = element_id

    def link(self, question: str) -> LinkResult:
        del question
        return LinkResult(
            relations=(),
            fields=(
                SchemaMatch(
                    element_id=self.element_id,
                    kind="field",
                    score=1.0,
                    lexical_score=1.0,
                    semantic_score=1.0,
                    document_sha256="a" * 64,
                ),
            ),
        )


def _tied_templates(tmp_path: Path) -> Path:
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    by_id = {template["id"]: template for template in templates}
    by_id["T_LIST_TX_FROM_ACCOUNT"]["nl_seed"] = (
        "Alpha {n} from {account} on {start_date} until {end_date}."
    )
    by_id["T_LIST_TX_TO_ACCOUNT"]["nl_seed"] = (
        "Alpha {n} to {account} on {start_date} until {end_date}."
    )
    by_id["T_LIST_TX_FROM_ACCOUNT"]["schema_elements"] = ["transaction_facts.from_address"]
    by_id["T_LIST_TX_TO_ACCOUNT"]["schema_elements"] = ["transaction_facts.to_address"]
    path = tmp_path / "templates.json"
    path.write_text(json.dumps(templates), encoding="utf-8")
    return path


def test_predict_returns_validated_google_sql() -> None:
    baseline = BaselineB0(TEMPLATES_PATH)

    sql = baseline.predict("How many transactions happened between 2026-06-15 and 2026-06-16?")

    assert sql == (
        "SELECT COUNT(*) AS transaction_count\n"
        "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
        "(DATE '2026-06-15', DATE '2026-06-16')"
    )
    validate_sql_text(sql)


def test_predict_detailed_records_seed_provenance() -> None:
    baseline = BaselineB0(TEMPLATES_PATH)

    result = baseline.predict_detailed(
        "How many transactions happened between 2026-06-15 and 2026-06-16?"
    )

    assert result is not None
    assert result.template_id == "T_COUNT_TX_IN_RANGE"
    assert result.match_mode == "seed"
    assert result.score == 1.0
    assert result.template_sha256
    assert result.catalog_sha256 is None


def test_structural_fallback_matches_unique_anchor_set() -> None:
    baseline = BaselineB0(TEMPLATES_PATH)

    result = baseline.predict_detailed(
        "How many transactions occurred between 2026-06-15 and 2026-06-16?"
    )

    assert result is not None
    assert result.template_id == "T_COUNT_TX_IN_RANGE"
    assert result.match_mode == "structural"


def test_structural_tie_without_schema_evidence_returns_none(tmp_path: Path) -> None:
    baseline = BaselineB0(_tied_templates(tmp_path))
    question = f"Alpha 5 account {ADDRESS} on 2026-06-15 until 2026-06-16."

    assert baseline.predict_detailed(question) is None


def test_schema_overlap_breaks_one_structural_tie(tmp_path: Path) -> None:
    baseline = BaselineB0(
        _tied_templates(tmp_path),
        schema_linker=_SchemaLinker("transaction_facts.to_address"),
    )
    question = f"Alpha 5 account {ADDRESS} on 2026-06-15 until 2026-06-16."

    result = baseline.predict_detailed(question)

    assert result is not None
    assert result.template_id == "T_LIST_TX_TO_ACCOUNT"


@pytest.mark.parametrize("question", ["", "   ", "\x00", "x" * 2001])
def test_invalid_public_question_raises(question: str) -> None:
    baseline = BaselineB0(TEMPLATES_PATH)

    with pytest.raises(B0Error, match="question"):
        baseline.predict(question)
