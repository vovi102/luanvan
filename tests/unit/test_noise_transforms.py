"""Behavior tests for deterministic, anchor-safe noise transformations."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from nl2sparql.dataset.noise.contracts import (
    NoiseConfig,
    NoiseType,
    NoiseValidationError,
)
from nl2sparql.dataset.noise.transforms import (
    load_abbreviations,
    noise_candidates,
    protected_terms,
    transform_question,
)


def test_default_config_enforces_exact_t3_4_quota() -> None:
    config = NoiseConfig()

    assert config.seed == 42
    assert config.quotas == {
        NoiseType.TYPO: 38,
        NoiseType.ABBREV: 38,
        NoiseType.FRAGMENT: 37,
        NoiseType.MIXED_CASE: 37,
    }
    assert sum(config.quotas.values()) == 150

    with pytest.raises(NoiseValidationError, match="quotas"):
        NoiseConfig(quotas={NoiseType.TYPO: 150})
    with pytest.raises(NoiseValidationError, match="seed.*42"):
        NoiseConfig(seed=7)


def test_default_abbreviations_are_normalized_and_exclude_named_entities() -> None:
    abbreviations = load_abbreviations()

    assert abbreviations["transactions"] == ("txs", "txns")
    assert abbreviations["token transfers"]
    assert all(key == key.casefold() for key in abbreviations)
    assert "binance" not in abbreviations
    assert "tornado cash" not in abbreviations


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"Transactions": ["txs"]}, "normalized"),
        ({"transactions": []}, "non-empty"),
        ({"transactions": ["txs", "txs"]}, "unique"),
        ({"transactions": [1]}, "strings"),
    ],
)
def test_abbreviation_loader_rejects_malformed_dictionary(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    path = tmp_path / "abbreviations.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(NoiseValidationError, match=message):
        load_abbreviations(path)


def test_protected_terms_include_slots_addresses_and_pinned_labels() -> None:
    address = "0x1111111111111111111111111111111111111111"
    record = {
        "slot_values": {
            "address": address,
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "n": 10,
            "token_symbol": "USDT",
        },
        "entities_used": [{"slot": "address", "type": "ethereum_address", "value": address}],
    }
    entity_index = {address: {"owner": "Binance", "primary_label": "Binance Hot Wallet 1"}}

    terms = protected_terms(record, entity_index)

    assert {
        address,
        "2026-06-01",
        "2026-06-02",
        "10",
        "usdt",
        "binance",
        "binance hot wallet 1",
    } <= terms


@pytest.mark.parametrize("noise_type", list(NoiseType))
def test_every_transform_changes_unprotected_text_but_preserves_anchors(
    noise_type: NoiseType,
) -> None:
    question = "Show transactions from Binance between 2026-06-01 and 2026-06-02?"
    protected = {"binance", "2026-06-01", "2026-06-02"}

    transformed = transform_question(
        question,
        noise_type,
        load_abbreviations(),
        protected,
        random.Random(42),
    )

    assert transformed is not None
    assert transformed != question
    assert "Binance" in transformed
    assert "2026-06-01" in transformed
    assert "2026-06-02" in transformed


def test_typo_is_one_adjacent_swap_and_abbreviation_uses_longest_phrase() -> None:
    typo = transform_question(
        "transactions",
        NoiseType.TYPO,
        {},
        set(),
        random.Random(42),
    )
    abbreviation = transform_question(
        "List token transfers now",
        NoiseType.ABBREV,
        {"token": ("tok",), "token transfers": ("token txfers",)},
        set(),
        random.Random(42),
    )

    assert typo is not None
    assert len(typo) == len("transactions")
    assert sum(left != right for left, right in zip(typo, "transactions", strict=True)) == 2
    assert abbreviation == "List token txfers now"


def test_typo_candidates_never_change_first_or_last_letter() -> None:
    assert noise_candidates("abcde", NoiseType.TYPO, {}, set()) == {
        "acbde",
        "abdce",
    }


def test_transform_returns_none_when_every_possible_edit_is_protected() -> None:
    for noise_type in NoiseType:
        assert (
            transform_question(
                "Transactions?",
                noise_type,
                {"transactions": ("txs",)},
                {"transactions", "?"},
                random.Random(42),
            )
            is None
        )
