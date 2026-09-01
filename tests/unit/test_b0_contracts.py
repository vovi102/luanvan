from __future__ import annotations

import pytest

from nl2sparql.models.b0 import B0Error, B0Policy, B0Prediction, SlotValue


def test_policy_rejects_threshold_outside_probability_range() -> None:
    with pytest.raises(B0Error, match="structural threshold"):
        B0Policy(structural_threshold=1.1, ambiguity_margin=0.03)


def test_policy_fingerprint_changes_with_effective_behavior() -> None:
    default = B0Policy()
    stricter = B0Policy(structural_threshold=0.7)

    assert len(default.sha256) == 64
    assert default.sha256 != stricter.sha256


def test_prediction_rejects_duplicate_slot_names() -> None:
    with pytest.raises(B0Error, match="slot names"):
        B0Prediction(
            sql="SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
            template_id="T_LIST_KNOWN_EXCHANGES",
            match_mode="seed",
            score=1.0,
            slots=(
                SlotValue("n", "integer", 10, (5, 7)),
                SlotValue("n", "integer", 20, (8, 10)),
            ),
            template_sha256="a" * 64,
            policy_sha256="b" * 64,
            catalog_sha256=None,
            entities_sha256=None,
            aliases_sha256=None,
            concepts_sha256=None,
            schema_elements=("entity_labels_v1.address",),
            cq_ids=("CQ07",),
            warnings=(),
        )


def test_prediction_preserves_immutable_typed_slots() -> None:
    prediction = B0Prediction(
        sql="SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
        template_id="T_LIST_KNOWN_EXCHANGES",
        match_mode="seed",
        score=1.0,
        slots=(SlotValue("n", "integer", 10, (5, 7)),),
        template_sha256="a" * 64,
        policy_sha256="b" * 64,
        catalog_sha256=None,
        entities_sha256=None,
        aliases_sha256=None,
        concepts_sha256=None,
        schema_elements=("entity_labels_v1.address",),
        cq_ids=("CQ07",),
        warnings=(),
    )

    assert prediction.slots[0].value == 10
