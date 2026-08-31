"""Behavioral tests for the deterministic entity-linker cascade."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from nl2sparql.linking.entity import (
    DEFAULT_LINKER_POLICY,
    EntityCorpus,
    EntityEncoderUnavailableError,
    EntityIndex,
    EntityIndexMetadata,
    EntityLinker,
    EntityLinkerError,
    EntityLinkerPolicy,
    EntityTarget,
    build_entity_corpus,
)


def _target(
    target_id: str,
    owner: str | None,
    aliases: tuple[str, ...],
    *,
    addresses: tuple[str, ...] = (),
    categories: tuple[str, ...] | None = None,
    concept_classes: tuple[str, ...] | None = None,
) -> EntityTarget:
    document = f"Target: {target_id}"
    return EntityTarget(
        target_id=target_id,
        target_kind="owner" if owner else "concept",
        owner=owner,
        addresses=addresses,
        primary_labels=(owner,) if owner else (),
        aliases=aliases,
        categories=(
            categories if categories is not None else (("exchange",) if owner else ("mixer",))
        ),
        concept_classes=(
            concept_classes
            if concept_classes is not None
            else (("ExchangeAccount",) if owner else ("MixerAccount",))
        ),
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
        rows = np.tile(np.asarray([2**-0.5, -(2**-0.5), 0.0], dtype=np.float32), (len(texts), 1))
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


class FixedEncoder:
    def __init__(self, vector: list[float]) -> None:
        self._vector = np.asarray(vector, dtype=np.float32)
        self.calls = 0

    def encode(self, sentences, *, normalize_embeddings=True):
        self.calls += 1
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        return np.tile(self._vector, (len(texts), 1))


class RecordingFixedEncoder(FixedEncoder):
    def __init__(self, vector: list[float]) -> None:
        super().__init__(vector)
        self.sentences: tuple[str, ...] = ()

    def encode(self, sentences, *, normalize_embeddings=True):
        self.sentences = tuple(sentences)
        return super().encode(sentences, normalize_embeddings=normalize_embeddings)


def _index_for(corpus: EntityCorpus, embeddings: np.ndarray) -> EntityIndex:
    embeddings = np.asarray(embeddings, dtype=np.float32)
    embeddings.setflags(write=False)
    return EntityIndex(
        EntityIndexMetadata(
            schema_version=1,
            model_id="fake/model",
            document_version="1.0.0",
            entities_sha256=corpus.entities_sha256,
            aliases_sha256=corpus.aliases_sha256,
            concepts_sha256=corpus.concepts_sha256,
            matrices_sha256="d" * 64,
            dimension=embeddings.shape[1],
            target_ids=tuple(target.target_id for target in corpus.targets),
            target_document_sha256=tuple(target.document_sha256 for target in corpus.targets),
            manifest_sha256="e" * 64,
        ),
        embeddings,
    )


@pytest.fixture
def token_symbol_corpus() -> EntityCorpus:
    token_metadata = {
        "categories": ("token_contract",),
        "concept_classes": ("TokenContract",),
    }
    targets = (
        _target("owner:Payme", "Payme", ("longticker", "payme"), **token_metadata),
        _target(
            "owner:TickerPhrase",
            "TickerPhrase",
            ("asset ticker", "show up"),
            **token_metadata,
        ),
    )
    return EntityCorpus(
        targets=targets,
        targets_by_id={target.target_id: target for target in targets},
        phrase_targets={
            "asset ticker": ("owner:TickerPhrase",),
            "longticker": ("owner:Payme",),
            "payme": ("owner:Payme",),
            "show up": ("owner:TickerPhrase",),
        },
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )


@pytest.fixture
def token_symbol_index(token_symbol_corpus: EntityCorpus) -> EntityIndex:
    return _index_for(token_symbol_corpus, np.eye(2, dtype=np.float32))


@pytest.fixture(scope="module")
def production_corpus() -> EntityCorpus:
    return build_entity_corpus()


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


def test_linker_rejects_an_index_built_with_a_different_policy(
    corpus: EntityCorpus, index: EntityIndex
) -> None:
    mismatched_index = EntityIndex(
        replace(index.metadata, linker_policy=EntityLinkerPolicy(0.86, 0.75, 0.03)),
        index.target_embeddings,
    )

    with pytest.raises(EntityLinkerError, match="policy"):
        EntityLinker(corpus, mismatched_index, FakeEncoder(), linker_policy=DEFAULT_LINKER_POLICY)


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


def test_address_recognition_rejects_unicode_word_boundaries(linker: EntityLinker) -> None:
    address = "0x1111111111111111111111111111111111111111"

    assert linker.link(f"é{address}") == ()
    assert linker.link(f"{address}β") == ()


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


def test_concept_one_token_alias_remains_exact_eligible(
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

    assert linker.link("show")[0].target_id == "concept:show"


def test_lowercase_token_symbol_alias_requires_signal_at_exact_stage(
    token_symbol_corpus: EntityCorpus, token_symbol_index: EntityIndex
) -> None:
    low_encoder = FixedEncoder([-1.0, 0.0])
    linker = EntityLinker(token_symbol_corpus, token_symbol_index, low_encoder)

    assert linker.link("payme") == ()
    assert linker.link("PAYME")[0].target_id == "owner:Payme"


def test_lowercase_token_symbol_alias_requires_signal_at_fuzzy_stage(
    token_symbol_corpus: EntityCorpus, token_symbol_index: EntityIndex
) -> None:
    low_encoder = FixedEncoder([-1.0, 0.0])
    linker = EntityLinker(token_symbol_corpus, token_symbol_index, low_encoder)

    assert linker.link("paymee") == ()
    assert linker.link("PAYMEE")[0].stage == "fuzzy"


def test_lowercase_one_token_window_requires_signal_at_embedding_stage(
    token_symbol_corpus: EntityCorpus, token_symbol_index: EntityIndex
) -> None:
    encoder = FixedEncoder([0.0, 1.0])
    linker = EntityLinker(token_symbol_corpus, token_symbol_index, encoder)

    assert linker.link("ordinary") == ()
    assert linker.link("ORDINARY")[0].stage == "embedding"


def test_stopword_only_windows_do_not_reach_fuzzy_or_embedding_retrieval() -> None:
    target = _target("concept:theory", None, ("theory",))
    stopword_corpus = EntityCorpus(
        targets=(target,),
        targets_by_id={target.target_id: target},
        phrase_targets={"theory": (target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    linker = EntityLinker(
        stopword_corpus,
        _index_for(stopword_corpus, np.asarray([[1.0]], dtype=np.float32)),
        FixedEncoder([1.0]),
    )

    assert linker.link("the") == ()
    assert linker.link("the theory")[-1].target_id == "concept:theory"


def test_question_word_only_windows_are_discarded_but_exact_aliases_are_exempt() -> None:
    exact_target = _target("concept:there", None, ("there",))
    semantic_target = _target("concept:ledger", None, ("ledger",))
    exact_corpus = EntityCorpus(
        targets=(exact_target,),
        targets_by_id={exact_target.target_id: exact_target},
        phrase_targets={"there": (exact_target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    semantic_corpus = EntityCorpus(
        targets=(semantic_target,),
        targets_by_id={semantic_target.target_id: semantic_target},
        phrase_targets={"ledger": (semantic_target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    exact_linker = EntityLinker(
        exact_corpus,
        _index_for(exact_corpus, np.asarray([[1.0]], dtype=np.float32)),
        FixedEncoder([1.0]),
    )
    semantic_linker = EntityLinker(
        semantic_corpus,
        _index_for(semantic_corpus, np.asarray([[1.0]], dtype=np.float32)),
        FixedEncoder([1.0]),
    )

    assert exact_linker.link("there")[0].stage == "exact"
    assert semantic_linker.link("can you") == ()
    assert semantic_linker.link("can you please") == ()
    assert semantic_linker.link("can you balance")[0].target_id == "concept:ledger"


@pytest.mark.parametrize(
    "question",
    (
        pytest.param("the that these", id="articles-determiners-demonstratives"),
        pytest.param("he she they myself", id="personal-possessive-reflexive-pronouns"),
        pytest.param("what which whom", id="interrogatives-relatives"),
        pytest.param("do would can", id="auxiliaries-modals"),
        pytest.param("and through up", id="conjunctions-prepositions-particles"),
        pytest.param("please show list", id="request-scaffolding"),
        pytest.param("do they", id="auxiliary-pronoun-combination"),
        pytest.param("would she", id="modal-pronoun-combination"),
        pytest.param("what is this", id="interrogative-copula-demonstrative-combination"),
    ),
)
def test_function_word_only_windows_never_reach_semantic_retrieval(question: str) -> None:
    target = _target("concept:ledger", None, ("ledger",))
    corpus = EntityCorpus(
        targets=(target,),
        targets_by_id={target.target_id: target},
        phrase_targets={"ledger": (target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    linker = EntityLinker(
        corpus,
        _index_for(corpus, np.asarray([[1.0]], dtype=np.float32)),
        FixedEncoder([1.0]),
    )

    assert linker.link(question) == ()


@pytest.mark.parametrize(
    "question",
    (
        pytest.param("is there any", id="existential-singular"),
        pytest.param("are there any", id="existential-plural"),
        pytest.param("if they can", id="subordinator-pronoun-modal"),
    ),
)
def test_snowball_function_word_windows_never_reach_semantic_retrieval(question: str) -> None:
    target = _target("concept:ledger", None, ("ledger",))
    corpus = EntityCorpus(
        targets=(target,),
        targets_by_id={target.target_id: target},
        phrase_targets={"ledger": (target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    linker = EntityLinker(
        corpus,
        _index_for(corpus, np.asarray([[1.0]], dtype=np.float32)),
        FixedEncoder([1.0]),
    )

    assert linker.link(question) == ()


def test_snowball_scaffolding_subwindows_are_filtered_but_balance_is_retrieved() -> None:
    target = _target("concept:ledger", None, ("ledger",))
    corpus = EntityCorpus(
        targets=(target,),
        targets_by_id={target.target_id: target},
        phrase_targets={"ledger": (target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    encoder = RecordingFixedEncoder([1.0])
    linker = EntityLinker(
        corpus,
        _index_for(corpus, np.asarray([[1.0]], dtype=np.float32)),
        encoder,
    )

    matches = linker.link("is there any balance")

    assert matches[0].span == "is there any balance"
    assert "balance" in encoder.sentences
    assert not {
        "is",
        "there",
        "any",
        "is there",
        "there any",
        "is there any",
    }.intersection(encoder.sentences)


def test_lowercase_token_winner_is_suppressed_despite_a_distant_non_token_candidate() -> None:
    token_metadata = {
        "categories": ("token_contract",),
        "concept_classes": ("TokenContract",),
    }
    token = _target("owner:Ticker", "Ticker", ("ticker",), **token_metadata)
    concept = _target("concept:mev", None, ("mev",))
    corpus = EntityCorpus(
        targets=(concept, token),
        targets_by_id={concept.target_id: concept, token.target_id: token},
        phrase_targets={"mev": (concept.target_id,), "ticker": (token.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    linker = EntityLinker(
        corpus,
        _index_for(corpus, np.asarray([[0.8, 0.6], [1.0, 0.0]], dtype=np.float32)),
        FixedEncoder([1.0, 0.0]),
    )

    assert linker.link("ordinary") == ()


def test_mixed_embedding_near_tie_keeps_token_alternative_for_ambiguity() -> None:
    token_metadata = {
        "categories": ("token_contract",),
        "concept_classes": ("TokenContract",),
    }
    concept = _target("concept:mev", None, ("mev",))
    token = _target("owner:Ticker", "Ticker", ("ticker",), **token_metadata)
    corpus = EntityCorpus(
        targets=(concept, token),
        targets_by_id={concept.target_id: concept, token.target_id: token},
        phrase_targets={"mev": (concept.target_id,), "ticker": (token.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )
    linker = EntityLinker(
        corpus,
        _index_for(
            corpus,
            np.asarray([[1.0, 0.0], [0.99, np.sqrt(1.0 - 0.99**2)]], dtype=np.float32),
        ),
        FixedEncoder([1.0, 0.0]),
    )

    match = linker.link("ordinary")[0]

    assert match.stage == "ambiguous"
    assert [alternative.target_id for alternative in match.alternatives] == [
        "concept:mev",
        "owner:Ticker",
    ]


def test_multi_token_windows_remain_eligible_for_fuzzy_and_embedding(
    token_symbol_corpus: EntityCorpus, token_symbol_index: EntityIndex
) -> None:
    fuzzy_linker = EntityLinker(token_symbol_corpus, token_symbol_index, FixedEncoder([-1.0, 0.0]))
    embedding_linker = EntityLinker(
        token_symbol_corpus, token_symbol_index, FixedEncoder([0.0, 1.0])
    )

    assert fuzzy_linker.link("shwo up")[0].stage == "fuzzy"
    assert fuzzy_linker.link("longticker x")[0].stage == "fuzzy"
    assert embedding_linker.link("please show transfers")[0].stage == "embedding"


@pytest.mark.parametrize(
    "question",
    ("can you list my wallets", "show up transfers", "wait for transfers"),
)
def test_production_token_symbol_aliases_do_not_fabricate_lowercase_entities(
    production_corpus: EntityCorpus, question: str
) -> None:
    linker = EntityLinker(
        production_corpus,
        _index_for(production_corpus, np.ones((len(production_corpus.targets), 1))),
        FixedEncoder([-1.0]),
    )

    assert linker.link(question) == ()


def test_production_uppercase_ticker_remains_recoverable(production_corpus: EntityCorpus) -> None:
    linker = EntityLinker(
        production_corpus,
        _index_for(production_corpus, np.ones((len(production_corpus.targets), 1))),
        FixedEncoder([-1.0]),
    )

    match = linker.link("show UP transfers")[0]

    assert match.stage == "ambiguous"
    assert [alternative.target_id for alternative in match.alternatives] == [
        "owner:Superform",
        "owner:Unitas",
    ]


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
