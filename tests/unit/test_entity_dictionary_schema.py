import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from nl2sparql.linking.dictionary import ALIASES_PATH, CONCEPTS_PATH, ENTITIES_PATH, SOURCES_PATH
from nl2sparql.linking.dictionary.build import build_dictionary, write_dictionary
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
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import build_entity_corpus


@pytest.fixture(scope="module")
def fetcher() -> ModuleType:
    script_path = Path("scripts/03_fetch_entity_labels.py").resolve()
    spec = importlib.util.spec_from_file_location("fetch_entity_labels", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_chain_aware_row(*, address: str) -> dict[str, str]:
    return {
        "address": address,
        "primary_label": "Reviewed entity",
        "owner": "Reviewed Owner",
        "category": "dex",
        "concept_class": "DEXProtocol",
        "aliases": "reviewed owner",
        "chain_id": "1",
        "address_role": "operational",
        "source_name": "reviewed_source",
        "source_url": "https://example.test/pinned-source",
        "source_revision": "a" * 40,
        "source_locator": "projects/reviewed/index.js:L1-L4",
        "retrieved_date": "2026-08-09",
        "confidence": "high",
    }


def test_normalize_alias_lowercases_trims_and_collapses_spaces():
    assert normalize_alias("  Binance   Hot Wallet  ") == "binance hot wallet"


def test_normalize_alias_applies_nfkc_before_casefolding():
    assert normalize_alias("bitcoin.ℏ") == "bitcoin.ħ"


def test_committed_dictionary_rebuild_is_byte_equivalent_and_accepted_by_entity_corpus(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "dictionary"
    write_dictionary(
        build_dictionary(
            Path("data/entity_dictionary/raw/entities.csv"),
            Path("data/entity_dictionary/curated/concepts.json"),
        ),
        output_dir,
    )

    for filename, committed_path in (
        ("entities.json", ENTITIES_PATH),
        ("concepts.json", CONCEPTS_PATH),
        ("aliases.json", ALIASES_PATH),
    ):
        assert (output_dir / filename).read_bytes() == committed_path.read_bytes()

    artifacts = DictionaryArtifacts(
        entities_path=output_dir / "entities.json",
        concepts_path=output_dir / "concepts.json",
        aliases_path=output_dir / "aliases.json",
        sources_path=SOURCES_PATH,
    )
    assert build_entity_corpus(artifacts) == build_entity_corpus(artifacts)


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


def test_coingecko_compiler_keeps_only_exact_ethereum_mainnet_tokens(fetcher):
    snapshot = {
        "tokens": [
            {
                "chainId": 1,
                "address": "0x" + "1" * 40,
                "name": "One Token",
                "symbol": "ONE",
            },
            {
                "chainId": 42161,
                "address": "0x" + "2" * 40,
                "name": "Two Token",
                "symbol": "TWO",
            },
        ]
    }

    rows = fetcher.rows_from_coingecko(
        snapshot,
        revision="sha256:" + "a" * 64,
        retrieved_date="2026-08-09",
    )

    assert len(rows) == 1
    assert rows[0]["address"] == "0x" + "1" * 40
    assert rows[0]["chain_id"] == "1"
    assert rows[0]["address_role"] == "token"
    assert rows[0]["source_locator"] == "/tokens/0"


def test_coingecko_compiler_rejects_address_prefix_embedded_in_long_identifier(
    fetcher,
):
    snapshot = {
        "tokens": [
            {
                "chainId": 1,
                "address": "0x" + "3" * 64,
                "name": "Aptos-shaped",
                "symbol": "BAD",
            }
        ]
    }

    with pytest.raises(DictionaryValidationError, match="Invalid Ethereum address"):
        fetcher.rows_from_coingecko(
            snapshot,
            revision="sha256:" + "b" * 64,
            retrieved_date="2026-08-09",
        )


def test_coingecko_compiler_excludes_addresses_claimed_by_reviewed_rows(fetcher):
    address = "0x" + "3" * 40
    snapshot = {
        "tokens": [
            {
                "chainId": 1,
                "address": address,
                "name": "Protocol Token",
                "symbol": "PT",
            }
        ]
    }

    rows = fetcher.rows_from_coingecko(
        snapshot,
        revision="sha256:" + "b" * 64,
        retrieved_date="2026-08-09",
        excluded_addresses={address.lower()},
    )

    assert rows == []


def test_compile_rows_rejects_duplicate_address_across_sources(fetcher):
    row = valid_chain_aware_row(address="0x" + "4" * 40)

    with pytest.raises(DictionaryValidationError, match="Duplicate Ethereum entity"):
        fetcher.compile_rows([row], [dict(row)])


@pytest.mark.parametrize(
    ("case_name", "chain_id", "address", "locator"),
    [
        ("swissborg_arbitrum", "42161", "0x" + "5" * 40, "ethereum:L1"),
        ("bitget_bsc", "56", "0x" + "6" * 40, "ethereum:L1"),
        ("kelp_zksync", "324", "0x" + "7" * 40, "ethereum:L1"),
        ("buidl_aptos", "1", "0x" + "8" * 64, "aptos:L1"),
        ("curve_base", "8453", "0x" + "9" * 40, "ethereum:L1"),
        ("spiko_polygon", "137", "0x" + "a" * 40, "ethereum:L1"),
        ("avalon_mantle", "5000", "0x" + "b" * 40, "ethereum:L1"),
        ("missing_locator", "1", "0x" + "c" * 40, "  "),
    ],
)
def test_compile_rows_rejects_audited_chain_and_provenance_failures(
    fetcher,
    case_name,
    chain_id,
    address,
    locator,
):
    row = valid_chain_aware_row(address=address)
    row["chain_id"] = chain_id
    row["source_locator"] = locator

    with pytest.raises(DictionaryValidationError, match="chain_id|address|locator"):
        fetcher.compile_rows([], [row])


def test_compiler_cli_writes_deterministic_offline_snapshot(tmp_path):
    token_snapshot = tmp_path / "tokens.json"
    reviewed_snapshot = tmp_path / "reviewed.csv"
    output = tmp_path / "entities.csv"
    token_snapshot.write_text(
        json.dumps(
            {
                "tokens": [
                    {
                        "chainId": 1,
                        "address": "0x" + "d" * 40,
                        "name": "Delta Token",
                        "symbol": "DELTA",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    row = valid_chain_aware_row(address="0x" + "e" * 40)
    with reviewed_snapshot.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/03_fetch_entity_labels.py",
            "--coingecko-snapshot",
            str(token_snapshot),
            "--reviewed-rows",
            str(reviewed_snapshot),
            "--retrieved-date",
            "2026-08-09",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [entry["owner"] for entry in rows] == ["Reviewed Owner", "Delta Token"]
    assert rows[0]["address_role"] == "operational"
    assert rows[1]["source_revision"].startswith("sha256:")
    assert b"\r\n" not in output.read_bytes()


def test_build_dictionary_merges_real_source_rows_and_sorts_outputs(tmp_path):
    raw_path = tmp_path / "entities.csv"
    concepts_path = tmp_path / "concepts.json"
    raw_path.write_text(
        "\n".join(
            [
                "address,primary_label,owner,category,concept_class,aliases,"
                "chain_id,address_role,source_name,source_url,source_revision,"
                "source_locator,retrieved_date,confidence",
                "0x28C6c06298d514Db089934071355E5743bf21d60,"
                "Binance: Hot Wallet 14,Binance,exchange,ExchangeAccount,"
                "binance|binance hot wallet,1,treasury,etherscan,"
                "https://etherscan.io/address/"
                "0x28C6c06298d514Db089934071355E5743bf21d60,"
                f"{'a' * 40},accounts/binance:L14,2026-06-28,high",
                "0x0000000000000000000000000000000000000000,"
                "Curve: Registry,Curve,dex,DEXProtocol,curve|curve protocol,"
                f"1,operational,curated_seed,https://curve.fi,{'b' * 40},"
                "deployments/ethereum.json:/registry,2026-06-28,medium",
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
    assert built["entities"][0]["address_lower"] == "0x0000000000000000000000000000000000000000"
    assert built["aliases"]["binance hot wallet"] == "Binance"
    assert built["concepts"]["exchange"]["instances"] == ["Binance"]
    assert built["entities"][0]["chain_id"] == 1
    assert built["entities"][0]["address_role"] == "operational"
    assert built["entities"][0]["sources"][0]["revision"] == "b" * 40
    assert built["entities"][0]["sources"][0]["locator"] == "deployments/ethereum.json:/registry"


def test_build_dictionary_drops_ambiguous_aliases_without_dropping_entities(tmp_path):
    raw_path = tmp_path / "entities.csv"
    concepts_path = tmp_path / "concepts.json"
    raw_path.write_text(
        "\n".join(
            [
                "address,primary_label,owner,category,concept_class,aliases,"
                "chain_id,address_role,source_name,source_url,source_revision,"
                "source_locator,retrieved_date,confidence",
                "0x1111111111111111111111111111111111111111,Spurdo token,Spurdo,"
                "token_contract,TokenContract,spurdo|spurdo token,"
                "1,token,coingecko_token_list,"
                "https://tokens.coingecko.com/uniswap/all.json,"
                f"sha256:{'c' * 64},/tokens/0,2026-06-28,medium",
                "0x2222222222222222222222222222222222222222,SPURDO token,SPURDO,"
                "token_contract,TokenContract,spurdo|spurdo token,"
                "1,token,coingecko_token_list,"
                "https://tokens.coingecko.com/uniswap/all.json,"
                f"sha256:{'c' * 64},/tokens/1,2026-06-28,medium",
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
