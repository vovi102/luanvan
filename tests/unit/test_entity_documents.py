from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import (
    EntityAlternative,
    EntityCorpus,
    EntityDocumentError,
    EntityLinkerError,
    EntityMatch,
    EntityTarget,
    build_entity_corpus,
)


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


def test_build_entity_corpus_uses_one_validated_snapshot_during_replacement_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _write_artifacts(tmp_path)
    expected_entities_sha256 = hashlib.sha256(artifacts.entities_path.read_bytes()).hexdigest()
    import nl2sparql.linking.entity.documents as documents

    original_validate = documents._validate_snapshot

    def replace_after_snapshot(*args, **kwargs):
        artifacts.entities_path.write_text("[1]", encoding="utf-8")
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(documents, "_validate_snapshot", replace_after_snapshot)

    corpus = build_entity_corpus(artifacts, min_entities=1, min_aliases=1)

    assert corpus.entities_sha256 == expected_entities_sha256
    assert "owner:Binance" in corpus.targets_by_id


def test_build_entity_corpus_translates_structural_dictionary_errors(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    artifacts.entities_path.write_text("[1]", encoding="utf-8")

    with pytest.raises(EntityDocumentError, match="invalid entity dictionary"):
        build_entity_corpus(artifacts, min_entities=1, min_aliases=1)


@pytest.mark.parametrize(
    ("artifact", "field_path", "invalid"),
    (
        ("concepts", ("exchange",), 1),
        ("concepts", ("exchange", "ontology_class"), 1),
        ("concepts", ("exchange", "aliases"), 1),
        ("concepts", ("exchange", "aliases", 0), 1),
        ("concepts", ("exchange", "instances"), ["Binance", 1]),
        ("concepts", ("exchange", "description"), 1),
        ("entities", (0, "primary_label"), 1),
        ("entities", (0, "owner"), 1),
        ("entities", (0, "aliases"), ["binance", 1]),
        ("entities", (0, "concept_class"), 1),
        ("entities", (0, "sources"), [1]),
        ("entities", (0, "sources", 0, "name"), 1),
    ),
)
def test_build_entity_corpus_rejects_malformed_nested_snapshot_fields(
    tmp_path: Path, artifact: str, field_path: tuple[object, ...], invalid: object
) -> None:
    artifacts = _write_artifacts(tmp_path)
    path = getattr(artifacts, f"{artifact}_path")
    payload = json.loads(path.read_text(encoding="utf-8"))
    parent = payload
    for part in field_path[:-1]:
        parent = parent[part]
    parent[field_path[-1]] = invalid
    path.write_text(json.dumps(payload, sort_keys=artifact != "entities"), encoding="utf-8")

    with pytest.raises(EntityDocumentError, match="invalid entity dictionary"):
        build_entity_corpus(artifacts, min_entities=1, min_aliases=1)


@pytest.mark.parametrize(
    ("phrase", "message"),
    [
        ("\x01", "control-free"),
        ("!!!", "token"),
        ("ﬁnance", "normalized"),
    ],
)
def test_build_entity_corpus_rejects_malformed_tokenless_or_noncanonical_aliases(
    tmp_path: Path, phrase: str, message: str
) -> None:
    artifacts = _write_artifacts(tmp_path)
    aliases = json.loads(artifacts.aliases_path.read_text(encoding="utf-8"))
    aliases.pop("binance")
    aliases[phrase] = "Binance"
    artifacts.aliases_path.write_text(json.dumps(aliases, sort_keys=True), encoding="utf-8")

    with pytest.raises(EntityDocumentError, match=message):
        build_entity_corpus(artifacts, min_entities=1, min_aliases=1)


@pytest.mark.parametrize("alias", [" binance", "binance  treasury"])
def test_build_entity_corpus_rejects_noncanonical_entity_alias_whitespace(
    tmp_path: Path, alias: str
) -> None:
    artifacts = _write_artifacts(tmp_path)
    entities = json.loads(artifacts.entities_path.read_text(encoding="utf-8"))
    entities[0]["aliases"] = [alias]
    artifacts.entities_path.write_text(json.dumps(entities), encoding="utf-8")

    with pytest.raises(EntityDocumentError, match="normalized"):
        build_entity_corpus(artifacts, min_entities=1, min_aliases=1)


def _owner_target() -> EntityTarget:
    document = "Owner: Binance"
    return EntityTarget(
        target_id="owner:Binance",
        target_kind="owner",
        owner="Binance",
        addresses=("0x1111111111111111111111111111111111111111",),
        primary_labels=("Binance",),
        aliases=("binance",),
        categories=("exchange",),
        concept_classes=("ExchangeAccount",),
        address_roles=("treasury",),
        description="Ethereum owner target Binance.",
        document=document,
        document_sha256=hashlib.sha256(document.encode("utf-8")).hexdigest(),
    )


def test_entity_target_rejects_document_digest_not_matching_content() -> None:
    target = _owner_target()

    with pytest.raises(EntityLinkerError, match="fingerprint"):
        EntityTarget(
            **{
                **target.__dict__,
                "document_sha256": "0" * 64,
            }
        )


def test_entity_match_is_deeply_immutable_and_rejects_inconsistent_runtime_values() -> None:
    address = "0x1111111111111111111111111111111111111111"
    match = EntityMatch(
        span=address,
        span_offset=(0, len(address)),
        target_id=f"address:{address}",
        target_kind="address",
        owner=None,
        addresses=(address,),
        categories=(),
        concept_classes=(),
        stage="address",
        confidence=1.0,
        alternatives=(),
        target_sha256="a" * 64,
    )

    with pytest.raises((AttributeError, TypeError)):
        match.addresses += (address,)  # type: ignore[misc]
    with pytest.raises(EntityLinkerError, match="addresses must be a tuple"):
        EntityMatch(**{**match.__dict__, "addresses": [address]})
    with pytest.raises(EntityLinkerError, match="inconsistent"):
        EntityMatch(**{**match.__dict__, "target_id": "owner:Binance"})
    with pytest.raises(EntityLinkerError, match="non-ambiguous"):
        EntityMatch(**{**match.__dict__, "alternatives": (object(),)})
    with pytest.raises(EntityLinkerError, match="two-item tuple"):
        EntityMatch(**{**match.__dict__, "span_offset": [0, len(address)]})
    with pytest.raises(EntityLinkerError, match="addresses are invalid"):
        EntityMatch(**{**match.__dict__, "addresses": (address.upper(),)})
    with pytest.raises(EntityLinkerError, match="cannot claim an owner"):
        EntityMatch(**{**match.__dict__, "owner": "not an address owner"})
    with pytest.raises(EntityLinkerError, match="two or three alternatives"):
        EntityMatch(**{**match.__dict__, "stage": "ambiguous"})
    with pytest.raises(EntityLinkerError, match="alternative target ID and kind"):
        EntityAlternative("owner:Binance", "concept", 0.9)


def test_entity_match_requires_owner_and_coherent_ambiguous_primary() -> None:
    base = {
        "span": "Binance",
        "span_offset": (0, 7),
        "target_id": "owner:Binance",
        "target_kind": "owner",
        "owner": "Binance",
        "addresses": (),
        "categories": (),
        "concept_classes": (),
        "stage": "exact",
        "confidence": 1.0,
        "alternatives": (),
        "target_sha256": "a" * 64,
    }
    primary = EntityAlternative("owner:Binance", "owner", 1.0)
    other = EntityAlternative("concept:dex", "concept", 0.99)

    with pytest.raises(EntityLinkerError, match="owner target must include owner"):
        EntityMatch(**{**base, "owner": None})
    with pytest.raises(EntityLinkerError, match="two or three alternatives"):
        EntityMatch(**{**base, "stage": "ambiguous", "alternatives": (primary,)})
    with pytest.raises(EntityLinkerError, match="primary alternative"):
        EntityMatch(**{**base, "stage": "ambiguous", "alternatives": (other, primary)})
    assert EntityMatch(**{**base, "stage": "ambiguous", "alternatives": (primary, other)})


def test_entity_corpus_freezes_and_validates_lookup_relationships() -> None:
    target = _owner_target()
    targets_by_id = {target.target_id: target}
    phrase_targets = {"binance": (target.target_id,)}
    address_targets = {target.addresses[0]: target.target_id}
    corpus = EntityCorpus(
        targets=[target],
        targets_by_id=targets_by_id,
        phrase_targets=phrase_targets,
        address_targets=address_targets,
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )

    targets_by_id.clear()
    phrase_targets.clear()
    address_targets.clear()

    assert corpus.targets == (target,)
    assert corpus.targets_by_id == {target.target_id: target}
    assert corpus.phrase_targets == {"binance": (target.target_id,)}
    assert corpus.address_targets == {target.addresses[0]: target.target_id}
    with pytest.raises(TypeError):
        corpus.phrase_targets["other"] = (target.target_id,)  # type: ignore[index]

    with pytest.raises(EntityLinkerError, match="unknown target"):
        EntityCorpus(
            targets=(target,),
            targets_by_id={target.target_id: target},
            phrase_targets={"binance": ("owner:Unknown",)},
            address_targets={target.addresses[0]: target.target_id},
            entities_sha256="a" * 64,
            aliases_sha256="b" * 64,
            concepts_sha256="c" * 64,
        )


def test_build_entity_corpus_has_deterministic_documents_and_fingerprints(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    first = build_entity_corpus(artifacts, min_entities=1, min_aliases=1)
    second = build_entity_corpus(artifacts, min_entities=1, min_aliases=1)

    assert first.targets == second.targets
    assert tuple((target.target_id, target.document_sha256) for target in first.targets) == tuple(
        (target.target_id, hashlib.sha256(target.document.encode("utf-8")).hexdigest())
        for target in second.targets
    )


def test_production_corpus_uses_bounded_target_documents() -> None:
    corpus = build_entity_corpus()

    assert len(corpus.targets) == 5107
    assert all(len(target.document) <= 10_000 for target in corpus.targets)
