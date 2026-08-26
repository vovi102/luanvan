"""Behavioral tests for the deterministic entity-linker cascade."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from nl2sparql.linking.entity import (
    EntityCorpus,
    EntityEncoderUnavailableError,
    EntityIndex,
    EntityIndexMetadata,
    EntityLinker,
    EntityLinkerError,
    EntityTarget,
    build_entity_corpus,
)


def _target(
    target_id: str,
    owner: str | None,
    aliases: tuple[str, ...],
    *,
    addresses: tuple[str, ...] = (),
) -> EntityTarget:
    document = f"Target: {target_id}"
    return EntityTarget(
        target_id=target_id,
        target_kind="owner" if owner else "concept",
        owner=owner,
        addresses=addresses,
        primary_labels=(owner,) if owner else (),
        aliases=aliases,
        categories=("exchange",) if owner else ("mixer",),
        concept_classes=("ExchangeAccount",) if owner else ("MixerAccount",),
        address_roles=("treasury",) if addresses else (),
        description=f"Fixture target {target_id}.",
        document=document,
        document_sha256=hashlib.sha256(document.encode()).hexdigest(),
    )


@pytest.fixture
def corpus() -> EntityCorpus:
    address = "0x2222222222222222222222222222222222222222"
    targets = (
        _target("concept:dex", None, ("dex", "swap")),
        _target("concept:mixer", None, ("privacy mixer", "tumbler")),
        _target("owner:Binance", "Binance", ("binance", "binance hot"), addresses=(address,)),
        _target("owner:TrustSwap", "TrustSwap", ("swap", "trustswap")),
    )
    return EntityCorpus(
        targets=targets,
        targets_by_id={target.target_id: target for target in targets},
        phrase_targets={
            "binance": ("owner:Binance",),
            "binance hot": ("owner:Binance",),
            "dex": ("concept:dex",),
            "privacy mixer": ("concept:mixer",),
            "swap": ("concept:dex", "owner:TrustSwap"),
            "trustswap": ("owner:TrustSwap",),
            "tumbler": ("concept:mixer",),
        },
        address_targets={address: "owner:Binance"},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )


@pytest.fixture
def index(corpus: EntityCorpus) -> EntityIndex:
    embeddings = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.6, 0.8],
        ],
        dtype=np.float32,
    )
    embeddings.setflags(write=False)
    metadata = EntityIndexMetadata(
        schema_version=1,
        model_id="fake/model",
        document_version="1.0.0",
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
        matrices_sha256="d" * 64,
        dimension=3,
        target_ids=tuple(target.target_id for target in corpus.targets),
        target_document_sha256=tuple(target.document_sha256 for target in corpus.targets),
        manifest_sha256="e" * 64,
    )
    return EntityIndex(metadata, embeddings)


class FakeEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        assert normalize_embeddings is True
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        rows = np.tile(
            np.asarray([2**-0.5, -(2**-0.5), 0.0], dtype=np.float32), (len(texts), 1)
        )
        return rows


class NearTieEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        vector = np.asarray([np.sqrt(1.0 - 0.8**2 - 0.3875**2), 0.8, 0.3875])
        return np.tile(vector, (len(texts), 1))


class CountingEmbeddingEncoder:
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, sentences, *, normalize_embeddings=True):
        self.calls += 1
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        return np.tile(np.asarray([0.0, 1.0, 0.0]), (len(texts), 1))


class LowScoreEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        return np.tile(np.asarray([2**-0.5, -(2**-0.5), 0.0]), (len(texts), 1))


class BrokenEncoder:
    def __init__(self, output: object) -> None:
        self.output = output

    def encode(self, sentences, *, normalize_embeddings=True):
        return self.output


class MissingEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        raise ImportError("encoder package is absent")


class NoModelEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        raise AssertionError("no encoder should be needed for this regression")


@pytest.fixture
def linker(corpus: EntityCorpus, index: EntityIndex) -> EntityLinker:
    return EntityLinker(corpus, index, FakeEncoder())


def test_link_returns_original_span_and_all_owner_addresses(linker: EntityLinker) -> None:
    result = linker.link("Transfers from  BINANCE, please")

    assert result[0].span == "BINANCE"
    assert result[0].span_offset == (16, 23)
    assert result[0].target_id == "owner:Binance"
    assert result[0].addresses == ("0x2222222222222222222222222222222222222222",)
    assert result[0].stage == "exact"


def test_unknown_valid_address_remains_queryable(linker: EntityLinker) -> None:
    address = "0x1111111111111111111111111111111111111111"

    result = linker.link(f"payments to {address}")

    assert result[0].target_id == f"address:{address}"
    assert result[0].target_kind == "address"
    assert result[0].owner is None
    assert result[0].addresses == (address,)
    assert result[0].stage == "address"


def test_known_address_is_enriched_from_its_owner(linker: EntityLinker) -> None:
    address = "0x2222222222222222222222222222222222222222"

    match = linker.link(f"payments to {address}")[0]

    assert (match.target_id, match.owner, match.stage) == ("owner:Binance", "Binance", "address")


def test_exact_matching_normalizes_unicode_case_and_whitespace_with_original_offsets(
    linker: EntityLinker,
) -> None:
    question = "show ＢＩＮＡＮＣＥ   HOT activity"

    match = linker.link(question)[0]

    assert match.span == "ＢＩＮＡＮＣＥ   HOT"
    assert match.span_offset == (5, 18)
    assert question[slice(*match.span_offset)] == match.span


def test_longest_non_overlapping_exact_span_wins(linker: EntityLinker) -> None:
    result = linker.link("binance hot then binance")

    assert [(match.span, match.target_id) for match in result] == [
        ("binance hot", "owner:Binance"),
        ("binance", "owner:Binance"),
    ]


def test_longest_crossing_exact_span_wins_before_source_offset(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    targets = tuple(
        _target(
            target.target_id,
            target.owner,
            tuple(sorted((*target.aliases, "alpha beta")))
            if target.target_id == "concept:dex"
            else target.aliases,
            addresses=target.addresses,
        )
        if target.target_id == "concept:dex"
        else _target(
            target.target_id,
            target.owner,
            tuple(sorted((*target.aliases, "beta gamma delta")))
            if target.target_id == "owner:TrustSwap"
            else target.aliases,
            addresses=target.addresses,
        )
        for target in corpus.targets
    )
    crossing_corpus = EntityCorpus(
        targets=targets,
        targets_by_id={target.target_id: target for target in targets},
        phrase_targets={
            **corpus.phrase_targets,
            "alpha beta": ("concept:dex",),
            "beta gamma delta": ("owner:TrustSwap",),
        },
        address_targets=corpus.address_targets,
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
    )
    crossing_index = EntityIndex(
        EntityIndexMetadata(
            **{
                **index.metadata.__dict__,
                "target_document_sha256": tuple(target.document_sha256 for target in targets),
            }
        ),
        index.target_embeddings,
    )
    linker = EntityLinker(crossing_corpus, crossing_index, FakeEncoder())

    assert [(match.span, match.target_id) for match in linker.link("alpha beta gamma delta")] == [
        ("beta gamma delta", "owner:TrustSwap")
    ]


def test_exact_matching_composes_unicode_before_mapping_original_offsets(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    target = _target("concept:cafe", None, ("café",))
    composed_corpus = EntityCorpus(
        targets=tuple(sorted((*corpus.targets, target), key=lambda item: item.target_id)),
        targets_by_id={**corpus.targets_by_id, target.target_id: target},
        phrase_targets={**corpus.phrase_targets, "café": (target.target_id,)},
        address_targets=corpus.address_targets,
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
    )
    embeddings = np.vstack(
        (index.target_embeddings, np.asarray([[1.0, 0.0, 0.0]], dtype=np.float32))
    )
    embeddings.setflags(write=False)
    composed_index = EntityIndex(
        EntityIndexMetadata(
            **{
                **index.metadata.__dict__,
                "target_ids": tuple(target.target_id for target in composed_corpus.targets),
                "target_document_sha256": tuple(
                    target.document_sha256 for target in composed_corpus.targets
                ),
            }
        ),
        embeddings,
    )
    linker = EntityLinker(composed_corpus, composed_index, FakeEncoder())
    question = "visit cafe\u0301 now"

    match = linker.link(question)[0]

    assert (match.span, match.span_offset, match.target_id) == (
        "cafe\u0301",
        (6, 11),
        "concept:cafe",
    )


def test_common_one_token_alias_requires_an_uppercase_entity_signal(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    target = _target("concept:show", None, ("show",))
    common_corpus = EntityCorpus(
        targets=tuple(sorted((*corpus.targets, target), key=lambda item: item.target_id)),
        targets_by_id={**corpus.targets_by_id, target.target_id: target},
        phrase_targets={**corpus.phrase_targets, "show": (target.target_id,)},
        address_targets=corpus.address_targets,
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
    )
    embeddings = np.vstack(
        (index.target_embeddings, np.asarray([[1.0, 0.0, 0.0]], dtype=np.float32))
    )
    embeddings.setflags(write=False)
    common_index = EntityIndex(
        EntityIndexMetadata(
            **{
                **index.metadata.__dict__,
                "target_ids": tuple(target.target_id for target in common_corpus.targets),
                "target_document_sha256": tuple(
                    target.document_sha256 for target in common_corpus.targets
                ),
            }
        ),
        embeddings,
    )
    linker = EntityLinker(common_corpus, common_index, FakeEncoder())

    assert linker.link("show") == ()
    assert linker.link("SHOW")[0].target_id == "concept:show"


def test_production_common_question_words_do_not_fabricate_an_entity() -> None:
    real_corpus = build_entity_corpus()
    embeddings = np.ones((len(real_corpus.targets), 1), dtype=np.float32)
    embeddings.setflags(write=False)
    real_index = EntityIndex(
        EntityIndexMetadata(
            schema_version=1,
            model_id="fake/model",
            document_version="1.0.0",
            entities_sha256=real_corpus.entities_sha256,
            aliases_sha256=real_corpus.aliases_sha256,
            concepts_sha256=real_corpus.concepts_sha256,
            matrices_sha256="d" * 64,
            dimension=1,
            target_ids=tuple(target.target_id for target in real_corpus.targets),
            target_document_sha256=tuple(target.document_sha256 for target in real_corpus.targets),
            manifest_sha256="e" * 64,
        ),
        embeddings,
    )

    linker = EntityLinker(real_corpus, real_index, NoModelEncoder())

    assert linker.link("show how many wallets") == ()


def test_exact_collision_returns_deterministic_ambiguity(linker: EntityLinker) -> None:
    match = linker.link("swap")[0]

    assert match.stage == "ambiguous"
    assert match.target_id == "concept:dex"
    assert [alternative.target_id for alternative in match.alternatives] == [
        "concept:dex",
        "owner:TrustSwap",
    ]


def test_results_are_ordered_by_source_offset_then_stable_target_id(linker: EntityLinker) -> None:
    result = linker.link("binance then swap")

    assert [(match.span_offset, match.target_id) for match in result] == [
        ((0, 7), "owner:Binance"),
        ((13, 17), "concept:dex"),
    ]


@pytest.mark.parametrize("question", [None, "", "  ", "ok\x00no", "x" * 10_001])
def test_link_rejects_invalid_questions(linker: EntityLinker, question: object) -> None:
    with pytest.raises(EntityLinkerError, match="question"):
        linker.link(question)  # type: ignore[arg-type]


def test_fuzzy_stage_recovers_unique_misspelling(linker: EntityLinker) -> None:
    match = linker.link("show binnance withdrawals")[0]

    assert (match.target_id, match.stage) == ("owner:Binance", "fuzzy")
    assert match.span == "binnance"


def test_embedding_near_tie_returns_ambiguous(corpus: EntityCorpus, index: EntityIndex) -> None:
    linker = EntityLinker(corpus, index, NearTieEncoder())

    match = linker.link("privacy transfer service")[0]

    assert match.stage == "ambiguous"
    assert [alternative.target_id for alternative in match.alternatives] == [
        "concept:mixer",
        "owner:TrustSwap",
    ]


def test_embedding_windows_are_encoded_in_a_single_batch(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    encoder = CountingEmbeddingEncoder()
    linker = EntityLinker(corpus, index, encoder)

    result = linker.link("unrelated language fragment")

    assert encoder.calls == 1
    assert result[0].stage == "embedding"


def test_no_entity_evidence_returns_an_empty_tuple(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    linker = EntityLinker(corpus, index, LowScoreEncoder())

    assert linker.link("unrelated language fragment") == ()


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (np.ones(3), "rank"),
        (np.ones((1, 3)), "row count"),
        (np.tile(np.asarray([[1.0, 0.0]]), (6, 1)), "dimension"),
        (np.tile(np.asarray([[np.nan, 0.0, 0.0]]), (6, 1)), "finite"),
        (np.ones((6, 3)), "normalized"),
        ([[1.0, 0.0, 0.0], [1.0]], "numeric"),
    ],
)
def test_link_rejects_malformed_encoder_outputs(
    corpus: EntityCorpus, index: EntityIndex, output: object, message: str
) -> None:
    linker = EntityLinker(corpus, index, BrokenEncoder(output))

    with pytest.raises(EntityLinkerError, match=message):
        linker.link("unrelated language fragment")


def test_link_only_classifies_import_failures_as_encoder_unavailable(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    linker = EntityLinker(corpus, index, MissingEncoder())

    with pytest.raises(EntityEncoderUnavailableError, match="unavailable"):
        linker.link("unrelated language fragment")
