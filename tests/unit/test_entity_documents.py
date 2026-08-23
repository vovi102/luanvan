from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import EntityDocumentError, build_entity_corpus


def _write_artifacts(tmp_path: Path, *, missing_alias_target: bool = False) -> DictionaryArtifacts:
    source = {
        "name": "fixture",
        "url": "https://example.test/source",
        "revision": "a" * 40,
        "locator": "fixture.json:1",
        "retrieved_date": "2026-08-23",
        "note": "test evidence",
    }
    entities = [
        {
            "address": "0x1111111111111111111111111111111111111111",
            "address_lower": "0x1111111111111111111111111111111111111111",
            "primary_label": "Binance Treasury",
            "owner": "Binance",
            "category": "exchange",
            "concept_class": "ExchangeAccount",
            "aliases": ["binance"],
            "chain_id": 1,
            "address_role": "treasury",
            "sources": [source],
            "confidence": "high",
            "verified_date": "2026-08-23",
        },
        {
            "address": "0x2222222222222222222222222222222222222222",
            "address_lower": "0x2222222222222222222222222222222222222222",
            "primary_label": "Binance Hot Wallet",
            "owner": "Binance",
            "category": "exchange",
            "concept_class": "ExchangeAccount",
            "aliases": ["binance hot"],
            "chain_id": 1,
            "address_role": "operational",
            "sources": [source],
            "confidence": "high",
            "verified_date": "2026-08-23",
        },
        {
            "address": "0x3333333333333333333333333333333333333333",
            "address_lower": "0x3333333333333333333333333333333333333333",
            "primary_label": "TrustSwap Token",
            "owner": "TrustSwap",
            "category": "dex",
            "concept_class": "DEXProtocol",
            "aliases": ["swap"],
            "chain_id": 1,
            "address_role": "token",
            "sources": [source],
            "confidence": "medium",
            "verified_date": "2026-08-23",
        },
    ]
    concepts = {
        "bridge": _concept("BridgeProtocol", "bridge"),
        "dex": _concept("DEXProtocol", "swap"),
        "exchange": _concept("ExchangeAccount", "cex", instances=["Binance"]),
        "lending": _concept("LendingProtocol", "loan"),
        "mev": _concept("MEVActor", "searcher"),
        "stablecoin": _concept("StablecoinIssuer", "stable coin"),
        "staking": _concept("StakingAccount", "validator"),
        "token_contract": _concept("TokenContract", "token"),
    }
    aliases = {
        "binance": "Missing" if missing_alias_target else "Binance",
        "trustswap": "TrustSwap",
    }
    paths = DictionaryArtifacts(
        entities_path=tmp_path / "entities.json",
        concepts_path=tmp_path / "concepts.json",
        aliases_path=tmp_path / "aliases.json",
        sources_path=tmp_path / "sources.md",
    )
    entities.sort(key=lambda row: (row["category"], row["owner"], row["address_lower"]))
    paths.entities_path.write_text(json.dumps(entities), encoding="utf-8")
    paths.concepts_path.write_text(json.dumps(concepts), encoding="utf-8")
    paths.aliases_path.write_text(json.dumps(aliases, sort_keys=True), encoding="utf-8")
    paths.sources_path.write_text(
        "Retrieved date: 2026-08-23\nManual verification: fixture\n"
        "Automated acceptance criteria: fixture\n",
        encoding="utf-8",
    )
    return paths


def _concept(ontology_class: str, alias: str, *, instances: list[str] | None = None) -> dict:
    return {
        "ontology_class": f"https://example.test/{ontology_class}",
        "aliases": [alias],
        "instances": instances or [],
        "description": f"Fixture {ontology_class} concept.",
    }


def test_build_entity_corpus_groups_owner_addresses_and_concepts(tmp_path: Path) -> None:
    corpus = build_entity_corpus(_write_artifacts(tmp_path), min_entities=1, min_aliases=1)

    owner = corpus.targets_by_id["owner:Binance"]
    assert owner.addresses == (
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
    )
    assert owner.categories == ("exchange",)
    assert owner.address_roles == ("operational", "treasury")
    assert corpus.phrase_targets["binance"] == ("owner:Binance",)
    assert corpus.targets_by_id["concept:exchange"].target_kind == "concept"
    assert corpus.address_targets[owner.addresses[0]] == "owner:Binance"


def test_phrase_collision_is_preserved_as_ordered_ambiguity(tmp_path: Path) -> None:
    corpus = build_entity_corpus(_write_artifacts(tmp_path), min_entities=1, min_aliases=1)

    assert corpus.phrase_targets["swap"] == (
        "concept:dex",
        "owner:TrustSwap",
    )


def test_target_ids_percent_encode_owner_names(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    entities = json.loads(artifacts.entities_path.read_text(encoding="utf-8"))
    row = next(entry for entry in entities if entry["owner"] == "Binance")
    row["owner"] = "Owner / One"
    row["aliases"] = ["owner one"]
    entities.sort(key=lambda row: (row["category"], row["owner"], row["address_lower"]))
    artifacts.entities_path.write_text(json.dumps(entities), encoding="utf-8")
    aliases = json.loads(artifacts.aliases_path.read_text(encoding="utf-8"))
    aliases["owner one"] = "Owner / One"
    artifacts.aliases_path.write_text(json.dumps(aliases, sort_keys=True), encoding="utf-8")

    corpus = build_entity_corpus(artifacts, min_entities=1, min_aliases=1)

    assert "owner:Owner%20%2F%20One" in corpus.targets_by_id


def test_build_entity_corpus_rejects_alias_target_without_owner(tmp_path: Path) -> None:
    with pytest.raises(EntityDocumentError, match="[Aa]lias target"):
        build_entity_corpus(
            _write_artifacts(tmp_path, missing_alias_target=True),
            min_entities=1,
            min_aliases=1,
        )


def test_production_corpus_uses_bounded_target_documents() -> None:
    corpus = build_entity_corpus()

    assert len(corpus.targets) == 5107
    assert all(len(target.document) <= 10_000 for target in corpus.targets)
