"""End-to-end behavior tests for exact Stage D allocation and validation."""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy

import pytest

from nl2sparql.dataset.noise.contracts import NoiseConfig, NoiseValidationError
from nl2sparql.dataset.noise.pipeline import (
    inject_noise,
    validate_stage_d_records,
)
from nl2sparql.dataset.noise.transforms import load_abbreviations
from nl2sparql.dataset.paraphrase.quality import (
    normalize_question,
    normalized_levenshtein,
)


def stage_c_records() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(3000):
        question = f"Show transaction number {index} between 2026-06-01 and 2026-06-02?"
        rows.append(
            {
                "id": f"stage-c-{index:04d}",
                "parent_id": f"stage-b-{index // 3:04d}",
                "nl": question,
                "nl_normalized": normalize_question(question),
                "sql": f"SELECT {index} AS row_id",
                "record_sha256": f"{index:064x}",
                "slot_values": {
                    "n": index,
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-02",
                },
                "entities_used": [],
                "stage_c": {"pairwise_distances": [0.4, 0.5, 0.6]},
            }
        )
    return rows


@pytest.fixture(scope="module")
def generated() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    source = stage_c_records()
    output = inject_noise(source, load_abbreviations(), {}, NoiseConfig())
    return source, output


def _canonical_noisy(records: list[dict[str, object]]) -> list[str]:
    return sorted(
        json.dumps(record, sort_keys=True) for record in records if "noise_type" in record
    )


def _remove_start_date_anchor(rows: list[dict[str, object]]) -> None:
    row = rows[3000]
    changed = str(row["nl"]).replace("2026-06-01", "2026-06-03")
    changed_normalized = normalize_question(changed)
    row["nl"] = changed
    row["nl_normalized"] = changed_normalized
    row["noise_distance"] = normalized_levenshtein(
        normalize_question(str(row["nl_original"])), changed_normalized
    )


def test_injection_has_exact_quota_and_is_input_order_independent(
    generated: tuple[list[dict[str, object]], list[dict[str, object]]],
) -> None:
    source, output = generated
    reversed_output = inject_noise(list(reversed(source)), load_abbreviations(), {}, NoiseConfig())
    noisy = output[3000:]

    assert len(output) == 3150
    assert output[:3000] == source
    assert _canonical_noisy(output) == _canonical_noisy(reversed_output)
    assert Counter(row["noise_type"] for row in noisy) == {
        "typo": 38,
        "abbrev": 38,
        "fragment": 37,
        "mixed_case": 37,
    }
    assert len({row["noise_parent_id"] for row in noisy}) == 150


def test_validator_proves_source_immutability_and_quality_stats(
    generated: tuple[list[dict[str, object]], list[dict[str, object]]],
) -> None:
    source, output = generated

    stats = validate_stage_d_records(source, output, {}, NoiseConfig())

    assert stats.original_count == 3000
    assert stats.noisy_count == 150
    assert stats.output_count == 3150
    assert stats.type_counts == {
        "typo": 38,
        "abbrev": 38,
        "fragment": 37,
        "mixed_case": 37,
    }
    assert stats.unique_raw_questions == 3150
    parent_by_id = {row["id"]: row for row in source}
    for row in output[3000:]:
        parent = parent_by_id[row["noise_parent_id"]]
        assert row["sql"] == parent["sql"]
        assert row["record_sha256"] == parent["record_sha256"]
        assert row["nl_normalized"] == normalize_question(str(row["nl"]))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows: rows[3000].__setitem__("sql", "SELECT 'mutated'"), "immutable"),
        (
            lambda rows: rows[3000].__setitem__("noise_parent_id", rows[3001]["noise_parent_id"]),
            "source",
        ),
        (_remove_start_date_anchor, "anchor"),
        (lambda rows: rows[3000].__setitem__("noise_distance", 0.99), "distance"),
    ],
)
def test_validator_rejects_tampered_variants(
    generated: tuple[list[dict[str, object]], list[dict[str, object]]],
    mutation,
    message: str,
) -> None:
    source, output = generated
    tampered = deepcopy(output)
    mutation(tampered)

    with pytest.raises(NoiseValidationError, match=message):
        validate_stage_d_records(source, tampered, {}, NoiseConfig())


def test_injection_fails_before_output_when_typo_quota_cannot_be_filled() -> None:
    records = stage_c_records()
    for index, record in enumerate(records):
        question = f"{index} 2026-06-01 2026-06-02"
        record["nl"] = question
        record["nl_normalized"] = normalize_question(question)

    with pytest.raises(NoiseValidationError, match="insufficient valid typo"):
        inject_noise(records, load_abbreviations(), {}, NoiseConfig())
