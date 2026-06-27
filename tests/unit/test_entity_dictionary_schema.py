import pytest

from nl2sparql.linking.dictionary.schema import (
    DictionaryValidationError,
    normalize_alias,
    normalize_address,
    validate_confidence,
)


def test_normalize_alias_lowercases_trims_and_collapses_spaces():
    assert normalize_alias("  Binance   Hot Wallet  ") == "binance hot wallet"


def test_normalize_address_returns_lowercase_key():
    assert (
        normalize_address("0x28C6c06298d514Db089934071355E5743bf21d60")
        == "0x28c6c06298d514db089934071355e5743bf21d60"
    )


def test_normalize_address_rejects_malformed_value():
    with pytest.raises(DictionaryValidationError, match="Invalid Ethereum address"):
        normalize_address("0x1234")


def test_validate_confidence_accepts_known_values():
    assert validate_confidence("high") == "high"
    assert validate_confidence("medium") == "medium"
    assert validate_confidence("low") == "low"


def test_validate_confidence_rejects_unknown_value():
    with pytest.raises(DictionaryValidationError, match="Invalid confidence"):
        validate_confidence("certain")
