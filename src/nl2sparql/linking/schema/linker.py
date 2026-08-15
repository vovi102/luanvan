"""Hybrid lexical and embedding retrieval over analytical schema elements."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from nl2sparql.linking.schema.contracts import Encoder, SchemaElement, SchemaLinkerError
from nl2sparql.linking.schema.index import SchemaIndex

MAX_QUESTION_CHARS = 2_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SchemaMatch:
    """One ranked relation or field with decomposed retrieval scores."""

    element_id: str
    kind: str
    score: float
    lexical_score: float
    semantic_score: float
    document_sha256: str


@dataclass(frozen=True)
class LinkResult:
    """Separate ranked relation and field pools for one question."""

    relations: tuple[SchemaMatch, ...]
    fields: tuple[SchemaMatch, ...]


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _tokens(value: str) -> tuple[str, ...]:
    return _normalized_tokens(_normalize(value))


def _normalized_tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(value))


def _contains_phrase(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(tokens):
        return False
    width = len(phrase)
    return any(tokens[index : index + width] == phrase for index in range(len(tokens) - width + 1))


def _validated_synonyms(
    synonyms: Mapping[str, Sequence[str]],
) -> tuple[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], ...]:
    groups: list[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]] = []
    owners: dict[tuple[str, ...], tuple[str, ...]] = {}
    for canonical, aliases in sorted(synonyms.items()):
        canonical_tokens = _tokens(canonical) if isinstance(canonical, str) else ()
        if not canonical_tokens or isinstance(aliases, (str, bytes)) or not aliases:
            raise SchemaLinkerError("schema synonyms are invalid")
        phrases = [canonical_tokens]
        for alias in aliases:
            alias_tokens = _tokens(alias) if isinstance(alias, str) else ()
            if not alias_tokens:
                raise SchemaLinkerError("schema synonyms are invalid")
            phrases.append(alias_tokens)
        if len(phrases) != len(set(phrases)):
            raise SchemaLinkerError("schema synonyms contain duplicate phrases")
        for phrase in phrases:
            previous = owners.get(phrase)
            if previous is not None and previous != canonical_tokens:
                raise SchemaLinkerError("schema synonym phrase belongs to multiple groups")
            owners[phrase] = canonical_tokens
        groups.append((canonical_tokens, tuple(sorted(phrases))))
    return tuple(groups)


def _lexical_score(
    question_tokens: tuple[str, ...],
    document: str,
    synonym_groups: tuple[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], ...],
) -> float:
    document_tokens = set(_tokens(document))
    base_tokens = set(question_tokens)
    expanded = set(base_tokens)
    matching_phrases: set[tuple[str, ...]] = set()
    for canonical, phrases in synonym_groups:
        matched = [phrase for phrase in phrases if _contains_phrase(question_tokens, phrase)]
        if not matched:
            continue
        matching_phrases.update(matched)
        for phrase in phrases:
            expanded.update(phrase)
        expanded.update(canonical)
    base_score = len(base_tokens & document_tokens) / len(base_tokens)
    expanded_score = len(expanded & document_tokens) / len(expanded)
    phrase_score = float(any(set(phrase) <= document_tokens for phrase in matching_phrases))
    return min(1.0, 0.6 * base_score + 0.3 * expanded_score + 0.1 * phrase_score)


def _query_vector(encoder: Encoder, question: str, dimension: int) -> np.ndarray:
    try:
        raw = encoder.encode(question, normalize_embeddings=True)
        vector = np.asarray(raw, dtype=np.float32)
    except Exception as exc:
        raise SchemaLinkerError(f"schema query encoder failed: {exc}") from exc
    if vector.ndim != 1:
        raise SchemaLinkerError("schema query encoder must return one vector")
    if vector.shape[0] != dimension:
        raise SchemaLinkerError("schema query encoder dimension mismatch")
    if not np.isfinite(vector).all():
        raise SchemaLinkerError("schema query encoder vector must be finite")
    if not math.isclose(float(np.linalg.norm(vector)), 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise SchemaLinkerError("schema query encoder vector must be normalized")
    vector.setflags(write=False)
    return vector


def _rank(
    elements: tuple[SchemaElement, ...],
    semantic_scores: np.ndarray,
    question_tokens: tuple[str, ...],
    synonym_groups: tuple[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], ...],
    semantic_weight: float,
    lexical_weight: float,
    top_k: int,
) -> tuple[SchemaMatch, ...]:
    matches: list[SchemaMatch] = []
    for element, raw_semantic in zip(elements, semantic_scores, strict=True):
        semantic_score = float(raw_semantic)
        lexical_score = _lexical_score(question_tokens, element.document, synonym_groups)
        score = semantic_weight * semantic_score + lexical_weight * lexical_score
        matches.append(
            SchemaMatch(
                element_id=element.element_id,
                kind=element.kind,
                score=score,
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                document_sha256=element.document_sha256,
            )
        )
    return tuple(sorted(matches, key=lambda row: (-row.score, row.element_id))[:top_k])


class SchemaLinker:
    """Rank Plan B analytical relations and fields for one NL question."""

    def __init__(
        self,
        index: SchemaIndex,
        encoder: Encoder,
        synonyms: Mapping[str, Sequence[str]],
    ) -> None:
        self._index = index
        self._encoder = encoder
        self._synonym_groups = _validated_synonyms(synonyms)
        if index.relation_embeddings.shape != (
            len(index.metadata.relation_elements),
            index.metadata.dimension,
        ) or index.field_embeddings.shape != (
            len(index.metadata.field_elements),
            index.metadata.dimension,
        ):
            raise SchemaLinkerError("schema index shape does not match its metadata")

    def link(self, question: str, top_k: int = 10) -> LinkResult:
        """Return independently ranked relations and fields.

        Args:
            question: Natural-language Ethereum analytics question.
            top_k: Maximum results returned from each pool. A shorter relation
                pool is returned in full.

        Returns:
            Immutable relation and field rankings.

        Raises:
            SchemaLinkerError: If the input or query vector violates the contract.
        """
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question) > MAX_QUESTION_CHARS
            or _CONTROL_RE.search(question)
        ):
            raise SchemaLinkerError(
                f"question must be non-empty, control-free, and at most {MAX_QUESTION_CHARS} chars"
            )
        normalized = _normalize(question)
        question_tokens = _normalized_tokens(normalized)
        if not question_tokens:
            raise SchemaLinkerError("question must contain at least one text token")
        maximum = max(
            len(self._index.metadata.relation_elements),
            len(self._index.metadata.field_elements),
        )
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0 or top_k > maximum:
            raise SchemaLinkerError(f"top_k must be an integer from 1 to {maximum}")
        vector = _query_vector(self._encoder, normalized, self._index.metadata.dimension)
        relation_scores = self._index.relation_embeddings @ vector
        field_scores = self._index.field_embeddings @ vector
        weights = self._index.metadata.weights
        relations = _rank(
            self._index.metadata.relation_elements,
            relation_scores,
            question_tokens,
            self._synonym_groups,
            weights.semantic,
            weights.lexical,
            min(top_k, len(self._index.metadata.relation_elements)),
        )
        fields = _rank(
            self._index.metadata.field_elements,
            field_scores,
            question_tokens,
            self._synonym_groups,
            weights.semantic,
            weights.lexical,
            min(top_k, len(self._index.metadata.field_elements)),
        )
        return LinkResult(relations=relations, fields=fields)
