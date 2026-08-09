import json

import pytest

from nl2sparql.linking.dictionary.build import build_dictionary
from nl2sparql.linking.dictionary.schema import (
    DictionaryValidationError,
    normalize_address,
    normalize_alias,
    validate_address_role,
    validate_chain_id,
    validate_confidence,
    validate_source_locator,
    validate_source_revision,
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


@pytest.mark.parametrize("value", [1, "1"])
def test_validate_chain_id_accepts_ethereum_mainnet(value):
    assert validate_chain_id(value) == 1


@pytest.mark.parametrize("value", [10, "42161", "ethereum", ""])
def test_validate_chain_id_rejects_non_mainnet_or_ambiguous_values(value):
    with pytest.raises(DictionaryValidationError, match="Ethereum chain_id"):
        validate_chain_id(value)


@pytest.mark.parametrize("role", ["operational", "token", "treasury"])
def test_validate_address_role_accepts_closed_vocabulary(role):
    assert validate_address_role(role) == role


def test_validate_address_role_rejects_unknown_role():
    with pytest.raises(DictionaryValidationError, match="address_role"):
        validate_address_role("protocol")


@pytest.mark.parametrize(
    "revision",
    ["sha256:" + "a" * 64, "0123456789abcdef0123456789abcdef01234567"],
)
def test_validate_source_revision_accepts_digest_or_git_sha(revision):
    assert validate_source_revision(revision) == revision


@pytest.mark.parametrize("revision", ["main", "master", "latest", ""])
def test_validate_source_revision_rejects_mutable_or_empty_values(revision):
    with pytest.raises(DictionaryValidationError, match="source_revision"):
        validate_source_revision(revision)


def test_validate_source_locator_rejects_blank_value():
    with pytest.raises(DictionaryValidationError, match="source_locator"):
        validate_source_locator("  ")


def test_build_dictionary_merges_real_source_rows_and_sorts_outputs(tmp_path):
    raw_path = tmp_path / "entities.csv"
    concepts_path = tmp_path / "concepts.json"
    raw_path.write_text(
        "\n".join(
            [
                "address,primary_label,owner,category,concept_class,aliases,"
                "source_name,source_url,retrieved_date,confidence",
                "0x28C6c06298d514Db089934071355E5743bf21d60,"
                "Binance: Hot Wallet 14,Binance,exchange,ExchangeAccount,"
                "binance|binance hot wallet,etherscan,"
                "https://etherscan.io/address/"
                "0x28C6c06298d514Db089934071355E5743bf21d60,2026-06-28,high",
                "0x0000000000000000000000000000000000000000,"
                "Curve: Registry,Curve,dex,DEXProtocol,curve|curve protocol,"
                "curated_seed,https://curve.fi,2026-06-28,medium",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    concepts_path.write_text(
        json.dumps(
            {
                "exchange": {
                    "ontology_class": "https://thesis.example.org/eth-kg/ExchangeAccount",
                    "aliases": ["exchange", "cex"],
                    "description": "Centralized exchange accounts",
                },
                "dex": {
                    "ontology_class": "https://thesis.example.org/eth-kg/DEXProtocol",
                    "aliases": ["dex", "amm"],
                    "description": "Decentralized exchange protocols",
                },
            }
        ),
        encoding="utf-8",
    )

    built = build_dictionary(raw_path, concepts_path)

    assert [entry["owner"] for entry in built["entities"]] == ["Curve", "Binance"]
    assert (
        built["entities"][0]["address_lower"]
        == "0x0000000000000000000000000000000000000000"
    )
    assert built["aliases"]["binance hot wallet"] == "Binance"
    assert built["concepts"]["exchange"]["instances"] == ["Binance"]


def test_build_dictionary_drops_ambiguous_aliases_without_dropping_entities(tmp_path):
    raw_path = tmp_path / "entities.csv"
    concepts_path = tmp_path / "concepts.json"
    raw_path.write_text(
        "\n".join(
            [
                "address,primary_label,owner,category,concept_class,aliases,"
                "source_name,source_url,retrieved_date,confidence",
                "0x1111111111111111111111111111111111111111,Spurdo token,Spurdo,"
                "token_contract,TokenContract,spurdo|spurdo token,"
                "coingecko_token_list,https://tokens.coingecko.com/uniswap/all.json,"
                "2026-06-28,medium",
                "0x2222222222222222222222222222222222222222,SPURDO token,SPURDO,"
                "token_contract,TokenContract,spurdo|spurdo token,"
                "coingecko_token_list,https://tokens.coingecko.com/uniswap/all.json,"
                "2026-06-28,medium",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    concepts_path.write_text(
        json.dumps(
            {
                "token_contract": {
                    "ontology_class": "https://thesis.example.org/eth-kg/TokenContract",
                    "aliases": ["token", "erc20"],
                    "description": "Token contracts",
                },
            }
        ),
        encoding="utf-8",
    )

    built = build_dictionary(raw_path, concepts_path)

    assert [entry["owner"] for entry in built["entities"]] == ["SPURDO", "Spurdo"]
    assert "spurdo" not in built["aliases"]
    assert "spurdo token" not in built["aliases"]
