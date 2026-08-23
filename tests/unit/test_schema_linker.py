"""Tests for hybrid analytical relation and field ranking."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from nl2sparql.linking.schema import (
    DOCUMENT_VERSION,
    INDEX_SCHEMA_VERSION,
    LinkResult,
    SchemaElement,
    SchemaIndex,
    SchemaIndexMetadata,
    SchemaLinker,
    SchemaLinkerError,
    SchemaMatch,
    ScoreWeights,
)


def _element(element_id: str, kind: str, document: str) -> SchemaElement:
    return SchemaElement(element_id, kind, document, hashlib.sha256(document.encode()).hexdigest())


def _index() -> SchemaIndex:
    relations = (
        _element("token_transfer_facts", "relation", "token transfer asset movement"),
        _element("transaction_facts", "relation", "transaction facts payment transactions"),
    )
    fields = (
        _element(
            "transaction_facts.from_address",
            "field",
            "transaction from address sender sent outgoing originating wallet account",
        ),
        _element(
            "transaction_facts.receipt_gas_used",
            "field",
            "transaction receipt gas used execution fee transaction cost",
        ),
        _element(
            "transaction_facts.gas_price_wei",
            "field",
            "transaction gas price wei fee execution fee transaction cost",
        ),
        _element(
            "transaction_facts.gas_limit",
            "field",
            "transaction gas limit maximum allowed gas units",
        ),
        _element(
            "transaction_facts.to_address",
            "field",
            "transaction to address recipient received incoming destination wallet account",
        ),
        _element(
            "transaction_facts.value_wei",
            "field",
            "transaction value wei amount volume worth",
        ),
    )
    relation_embeddings = np.asarray([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    field_embeddings = np.asarray([[1.0, 0.0]] * len(fields), dtype=np.float32)
    relation_embeddings.setflags(write=False)
    field_embeddings.setflags(write=False)
    metadata = SchemaIndexMetadata(
        schema_version=INDEX_SCHEMA_VERSION,
        model_id="test/constant",
        document_version=DOCUMENT_VERSION,
        catalog_sha256="a" * 64,
        matrices_sha256="b" * 64,
        dimension=2,
        weights=ScoreWeights(),
        relation_elements=relations,
        field_elements=fields,
        manifest_sha256="c" * 64,
    )
    return SchemaIndex(metadata, relation_embeddings, field_embeddings)


class ConstantEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        assert isinstance(sentences, str)
        assert normalize_embeddings is True
        return np.asarray([1.0, 0.0], dtype=np.float64)


class InvalidQueryEncoder:
    def __init__(self, vector: object) -> None:
        self.vector = vector

    def encode(self, sentences, *, normalize_embeddings=True):
        return self.vector


class ExplodingEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        raise AssertionError("invalid input reached the encoder")


def test_link_returns_typed_separate_rankings_with_score_components() -> None:
    linker = SchemaLinker(_index(), ConstantEncoder(), {"from": ("sender", "sent", "outgoing")})

    result = linker.link("sender sent outgoing from address", top_k=3)

    assert isinstance(result, LinkResult)
    assert isinstance(result.relations, tuple)
    assert isinstance(result.fields, tuple)
    assert all(row.kind == "relation" for row in result.relations)
    assert all(isinstance(row, SchemaMatch) for row in result.fields)
    assert all(row.kind == "field" for row in result.fields)
    assert [row.score for row in result.relations] == sorted(
        (row.score for row in result.relations), reverse=True
    )
    assert [row.score for row in result.fields] == sorted(
        (row.score for row in result.fields), reverse=True
    )
    assert result.fields[0].element_id == "transaction_facts.from_address"
    assert result.fields[0].kind == "field"
    assert result.fields[0].semantic_score == pytest.approx(1.0)
    assert result.fields[0].lexical_score == pytest.approx(1.0)
    assert result.fields[0].score == pytest.approx(1.0)
    assert len(result.fields) == 3
    assert len(result.relations) == 2


def test_directional_and_measure_synonyms_rank_the_correct_fields() -> None:
    linker = SchemaLinker(
        _index(),
        ConstantEncoder(),
        {
            "from": ("sender", "sent", "outgoing"),
            "to": ("recipient", "received", "incoming"),
            "value": ("amount", "volume", "worth"),
            "gas": ("execution fee", "fee", "transaction cost"),
        },
    )

    assert (
        linker.link("transactions sent by an exchange", 3)
        .fields[0]
        .element_id.endswith(".from_address")
    )
    assert (
        linker.link("transactions received by an exchange", 3)
        .fields[0]
        .element_id.endswith(".to_address")
    )
    assert linker.link("largest transaction amount", 3).fields[0].element_id.endswith(".value_wei")
    gas_matches = linker.link("gas fee used", 6).fields

    assert [row.element_id for row in gas_matches if "gas" in row.element_id] == [
        "transaction_facts.receipt_gas_used",
        "transaction_facts.gas_price_wei",
        "transaction_facts.gas_limit",
    ]
    assert gas_matches[0].element_id == "transaction_facts.receipt_gas_used"


def test_link_uses_stable_element_id_ties_and_does_not_mutate_index() -> None:
    index = _index()
    relation_before = index.relation_embeddings.copy()
    fields_before = index.field_embeddings.copy()
    linker = SchemaLinker(index, ConstantEncoder(), {})

    result = linker.link("unrelated words", top_k=4)

    assert [row.element_id for row in result.relations] == [
        "token_transfer_facts",
        "transaction_facts",
    ]
    assert [row.element_id for row in result.fields] == sorted(
        row.element_id for row in result.fields
    )
    np.testing.assert_array_equal(index.relation_embeddings, relation_before)
    np.testing.assert_array_equal(index.field_embeddings, fields_before)
    assert index.field_embeddings.flags.writeable is False


def test_link_none_cutoff_returns_complete_relation_and_field_pools() -> None:
    linker = SchemaLinker(_index(), ConstantEncoder(), {})

    result = linker.link("unrelated words", top_k=None)

    assert len(result.relations) == 2
    assert len(result.fields) == 6


@pytest.mark.parametrize(
    "question",
    ("", "   ", "!!!", "bad\u0001question", 123, "x" * 2001),
)
def test_link_rejects_invalid_questions_before_encoding(question: object) -> None:
    linker = SchemaLinker(_index(), ExplodingEncoder(), {})

    with pytest.raises(SchemaLinkerError, match="question"):
        linker.link(question, top_k=2)


@pytest.mark.parametrize("top_k", (0, -1, True, "2", 7))
def test_link_rejects_invalid_top_k(top_k: object) -> None:
    linker = SchemaLinker(_index(), ExplodingEncoder(), {})

    with pytest.raises(SchemaLinkerError, match="top_k"):
        linker.link("valid question", top_k=top_k)


@pytest.mark.parametrize(
    ("vector", "message"),
    (
        (np.asarray([1.0, 0.0, 0.0]), "dimension"),
        (np.asarray([np.nan, 0.0]), "finite"),
        (np.asarray([2.0, 0.0]), "normalized"),
        (np.asarray([[1.0, 0.0], [1.0, 0.0]]), "one vector"),
    ),
)
def test_link_rejects_invalid_query_vectors(vector: object, message: str) -> None:
    linker = SchemaLinker(_index(), InvalidQueryEncoder(vector), {})

    with pytest.raises(SchemaLinkerError, match=message):
        linker.link("valid question", top_k=2)


def test_link_uses_weights_bound_to_index_metadata() -> None:
    index = _index()
    lexical_only = replace(index.metadata, weights=ScoreWeights(semantic=0.0, lexical=1.0))
    linker = SchemaLinker(replace(index, metadata=lexical_only), ConstantEncoder(), {})

    result = linker.link("sender", top_k=4)

    assert result.fields[0].element_id == "transaction_facts.from_address"
    assert result.fields[-1].score == pytest.approx(0.0)
