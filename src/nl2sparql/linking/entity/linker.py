"""Deterministic address and exact-phrase entity recognition."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

import numpy as np
from rapidfuzz.fuzz import ratio

from nl2sparql.linking.entity.contracts import (
    EntityAlternative,
    EntityCorpus,
    EntityEncoderUnavailableError,
    EntityLinkerError,
    EntityMatch,
    EntityTarget,
    required_text,
)
from nl2sparql.linking.entity.index import EntityIndex

_ADDRESS_RE = re.compile(r"(?<![0-9a-zA-Z])0x[0-9a-f]{40}(?![0-9a-zA-Z])", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_FUZZY_CUTOFF = 0.85
_SEMANTIC_CUTOFF = 0.75
_DIFFERENT_TARGET_MARGIN = 0.03
_COMMON_QUERY_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "by",
        "can",
        "count",
        "counts",
        "could",
        "did",
        "do",
        "does",
        "find",
        "for",
        "from",
        "get",
        "give",
        "how",
        "in",
        "is",
        "list",
        "many",
        "of",
        "on",
        "or",
        "show",
        "the",
        "there",
        "to",
        "total",
        "wallet",
        "wallets",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
        "why",
    }
)


@dataclass(frozen=True)
class _NormalizedQuestion:
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]


@dataclass(frozen=True)
class _Proposal:
    start: int
    end: int
    target_ids: tuple[str, ...]
    stage: str
    confidence: float
    alternative_confidences: tuple[float, ...] = ()


@dataclass(frozen=True)
class _Token:
    normalized_start: int
    normalized_end: int
    source_start: int
    source_end: int


@dataclass(frozen=True)
class _Window:
    text: str
    source_start: int
    source_end: int


def _normalize_question(question: str) -> _NormalizedQuestion:
    """NFKC/casefold text while retaining source ranges for every output character."""
    canonical = unicodedata.normalize("NFKC", question).casefold()
    text, starts, ends = _segment_normalized_offsets(question)
    if text != canonical:
        text, starts, ends = _prefix_normalized_offsets(question)
    return _collapse_whitespace(text, starts, ends)


def _segment_normalized_offsets(question: str) -> tuple[str, list[int], list[int]]:
    """Map stable starter-plus-combining segments without splitting composition inputs."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    segment_start = 0
    for offset in range(1, len(question) + 1):
        if offset < len(question) and unicodedata.combining(question[offset]):
            continue
        normalized = unicodedata.normalize("NFKC", question[segment_start:offset]).casefold()
        for output_character in normalized:
            characters.append(output_character)
            starts.append(segment_start)
            ends.append(offset)
        segment_start = offset
    return "".join(characters), starts, ends


def _prefix_normalized_offsets(question: str) -> tuple[str, list[int], list[int]]:
    """Correctly map the rare NFKC interaction that crosses a starter boundary."""
    text = ""
    starts: list[int] = []
    ends: list[int] = []
    for offset in range(1, len(question) + 1):
        next_text = unicodedata.normalize("NFKC", question[:offset]).casefold()
        common = 0
        while common < len(text) and common < len(next_text) and text[common] == next_text[common]:
            common += 1
        source_start = starts[common] if common < len(starts) else offset - 1
        text = next_text
        starts[common:] = [source_start] * (len(text) - common)
        ends[common:] = [offset] * (len(text) - common)
    return text, starts, ends


def _collapse_whitespace(
    text: str, starts: list[int], ends: list[int]
) -> _NormalizedQuestion:
    characters: list[str] = []
    mapped_starts: list[int] = []
    mapped_ends: list[int] = []
    pending_space: tuple[int, int] | None = None
    for character, start, end in zip(text, starts, ends, strict=True):
        if character.isspace():
            if characters:
                pending_space = (
                    pending_space[0] if pending_space else start,
                    end,
                )
            continue
        if pending_space is not None:
            characters.append(" ")
            mapped_starts.append(pending_space[0])
            mapped_ends.append(pending_space[1])
            pending_space = None
        characters.append(character)
        mapped_starts.append(start)
        mapped_ends.append(end)
    return _NormalizedQuestion("".join(characters), tuple(mapped_starts), tuple(mapped_ends))


def _has_phrase_boundaries(text: str, start: int, end: int) -> bool:
    return (start == 0 or not text[start - 1].isalnum()) and (
        end == len(text) or not text[end].isalnum()
    )


class EntityLinker:
    """Resolve address, exact, fuzzy, and semantic entity evidence deterministically."""

    def __init__(self, corpus: EntityCorpus, index: EntityIndex, encoder: object) -> None:
        if not isinstance(corpus, EntityCorpus):
            raise EntityLinkerError("entity corpus is invalid")
        if not isinstance(index, EntityIndex):
            raise EntityLinkerError("entity index is invalid")
        if (
            index.metadata.entities_sha256 != corpus.entities_sha256
            or index.metadata.aliases_sha256 != corpus.aliases_sha256
            or index.metadata.concepts_sha256 != corpus.concepts_sha256
        ):
            raise EntityLinkerError("entity index dictionary does not match the corpus")
        if index.metadata.target_ids != tuple(target.target_id for target in corpus.targets):
            raise EntityLinkerError("entity index targets do not match the corpus")
        if index.metadata.target_document_sha256 != tuple(
            target.document_sha256 for target in corpus.targets
        ):
            raise EntityLinkerError("entity index documents do not match the corpus")
        matrix = np.asarray(index.target_embeddings)
        if matrix.ndim != 2 or matrix.shape != (len(corpus.targets), index.metadata.dimension):
            raise EntityLinkerError("entity index matrix shape is invalid")
        if matrix.dtype != np.float32:
            raise EntityLinkerError("entity index matrix must use float32")
        if not np.isfinite(matrix).all():
            raise EntityLinkerError("entity index matrix must be finite")
        if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, rtol=0.0, atol=1e-5):
            raise EntityLinkerError("entity index matrix must be normalized")
        self._corpus = corpus
        self._index = index
        self._encoder = encoder
        self._target_embeddings = matrix.copy()
        self._target_embeddings.setflags(write=False)

    def link(self, question: str) -> tuple[EntityMatch, ...]:
        """Return immutable entity matches with original source offsets."""
        required_text(question, "question")
        normalized = _normalize_question(question)
        address_matches = self._address_proposals(question)
        exact_matches = self._exact_proposals(question, normalized, address_matches)
        exact_selected = self._select_non_overlapping((*address_matches, *exact_matches))
        fuzzy_selected = self._select_non_overlapping(
            self._fuzzy_proposals(normalized, exact_selected)
        )
        embedding_selected = self._select_non_overlapping(
            self._embedding_proposals(normalized, (*exact_selected, *fuzzy_selected))
        )
        selected = self._select_non_overlapping(
            (*exact_selected, *fuzzy_selected, *embedding_selected)
        )
        return tuple(self._match(question, proposal) for proposal in selected)

    def _address_proposals(self, question: str) -> tuple[_Proposal, ...]:
        proposals: list[_Proposal] = []
        for match in _ADDRESS_RE.finditer(question):
            address = match.group().lower()
            target_id = self._corpus.address_targets.get(address, f"address:{address}")
            proposals.append(_Proposal(match.start(), match.end(), (target_id,), "address", 1.0))
        return tuple(proposals)

    def _exact_proposals(
        self,
        question: str,
        normalized: _NormalizedQuestion,
        addresses: tuple[_Proposal, ...],
    ) -> tuple[_Proposal, ...]:
        if not normalized.text:
            return ()
        proposals: list[_Proposal] = []
        for phrase, target_ids in self._corpus.phrase_targets.items():
            start = normalized.text.find(phrase)
            while start >= 0:
                end = start + len(phrase)
                if _has_phrase_boundaries(normalized.text, start, end):
                    source_start = normalized.starts[start]
                    source_end = normalized.ends[end - 1]
                    source_span = question[source_start:source_end]
                    if not any(
                        source_start < address.end and address.start < source_end
                        for address in addresses
                    ) and (
                        phrase not in _COMMON_QUERY_WORDS or source_span.isupper()
                    ):
                        proposals.append(
                            _Proposal(source_start, source_end, target_ids[:3], "exact", 1.0)
                        )
                start = normalized.text.find(phrase, start + 1)
        return tuple(proposals)

    def _fuzzy_proposals(
        self, normalized: _NormalizedQuestion, covered: tuple[_Proposal, ...]
    ) -> tuple[_Proposal, ...]:
        proposals: list[_Proposal] = []
        for window in self._uncovered_windows(normalized, covered):
            scores: dict[str, float] = {}
            for phrase, target_ids in self._corpus.phrase_targets.items():
                if phrase in _COMMON_QUERY_WORDS:
                    continue
                score = ratio(window.text, phrase) / 100.0
                if score < _FUZZY_CUTOFF:
                    continue
                for target_id in target_ids:
                    scores[target_id] = max(scores.get(target_id, 0.0), score)
            ranked = self._rank_accepted_scores(scores, _FUZZY_CUTOFF)
            if ranked:
                target_ids, confidences = ranked
                proposals.append(
                    _Proposal(
                        window.source_start,
                        window.source_end,
                        target_ids,
                        "fuzzy",
                        confidences[0],
                        confidences,
                    )
                )
        return tuple(proposals)

    def _embedding_proposals(
        self, normalized: _NormalizedQuestion, covered: tuple[_Proposal, ...]
    ) -> tuple[_Proposal, ...]:
        windows = self._uncovered_windows(normalized, covered)
        if not windows:
            return ()
        sentences = [window.text for window in windows]
        try:
            encoder = self._encoder.encode  # type: ignore[attr-defined]
        except AttributeError as exc:
            raise EntityLinkerError("entity encoder must provide encode") from exc
        if not callable(encoder):
            raise EntityLinkerError("entity encoder must provide encode")
        try:
            raw_embeddings = encoder(sentences, normalize_embeddings=True)
        except (ImportError, OSError) as exc:
            raise EntityEncoderUnavailableError(
                f"entity linker encoder unavailable: {exc}"
            ) from exc
        except EntityLinkerError:
            raise
        except Exception as exc:
            raise EntityLinkerError(f"entity encoder failed: {exc}") from exc
        embeddings = self._validated_query_embeddings(
            raw_embeddings, len(windows), self._target_embeddings.shape[1]
        )
        all_scores = embeddings @ self._target_embeddings.T
        proposals: list[_Proposal] = []
        for window, row in zip(windows, all_scores, strict=True):
            scores = {
                target.target_id: min(1.0, float(score))
                for target, score in zip(self._corpus.targets, row, strict=True)
                if float(score) >= _SEMANTIC_CUTOFF
            }
            ranked = self._rank_accepted_scores(scores, _SEMANTIC_CUTOFF)
            if ranked:
                target_ids, confidences = ranked
                proposals.append(
                    _Proposal(
                        window.source_start,
                        window.source_end,
                        target_ids,
                        "embedding",
                        confidences[0],
                        confidences,
                    )
                )
        return tuple(proposals)

    @staticmethod
    def _rank_accepted_scores(
        scores: dict[str, float], cutoff: float
    ) -> tuple[tuple[str, ...], tuple[float, ...]] | None:
        ranked = tuple(sorted(scores.items(), key=lambda item: (-item[1], item[0])))
        if not ranked or ranked[0][1] < cutoff:
            return None
        accepted = [ranked[0]]
        for target_id, score in ranked[1:]:
            if accepted[0][1] - score < _DIFFERENT_TARGET_MARGIN:
                accepted.append((target_id, score))
            else:
                break
        return tuple(target_id for target_id, _ in accepted[:3]), tuple(
            score for _, score in accepted[:3]
        )

    def _uncovered_windows(
        self, normalized: _NormalizedQuestion, covered: tuple[_Proposal, ...]
    ) -> tuple[_Window, ...]:
        tokens = tuple(
            _Token(
                token.start(),
                token.end(),
                normalized.starts[token.start()],
                normalized.ends[token.end() - 1],
            )
            for token in _TOKEN_RE.finditer(normalized.text)
        )
        windows: list[_Window] = []
        for start_index in range(len(tokens)):
            for size in range(1, min(5, len(tokens) - start_index) + 1):
                first = tokens[start_index]
                last = tokens[start_index + size - 1]
                if any(
                    first.source_start < match.end and match.start < last.source_end
                    for match in covered
                ):
                    continue
                text = normalized.text[first.normalized_start : last.normalized_end]
                words = tuple(token.group() for token in _TOKEN_RE.finditer(text))
                if not any(any(character.isalpha() for character in word) for word in words):
                    continue
                if words and all(word in _COMMON_QUERY_WORDS for word in words):
                    continue
                windows.append(_Window(text, first.source_start, last.source_end))
        return tuple(windows)

    @staticmethod
    def _validated_query_embeddings(raw: object, count: int, dimension: int) -> np.ndarray:
        try:
            array = np.asarray(raw)
        except (TypeError, ValueError) as exc:
            raise EntityLinkerError(
                "entity encoder output must be numeric and rectangular"
            ) from exc
        if array.ndim != 2:
            raise EntityLinkerError("entity encoder output rank is invalid")
        if array.shape[0] != count:
            raise EntityLinkerError("entity encoder output row count is invalid")
        if array.shape[1] != dimension:
            raise EntityLinkerError("entity encoder output dimension is invalid")
        try:
            array = np.asarray(array, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise EntityLinkerError("entity encoder output must be numeric") from exc
        if not np.isfinite(array).all():
            raise EntityLinkerError("entity encoder output must be finite")
        if not np.allclose(np.linalg.norm(array, axis=1), 1.0, rtol=0.0, atol=1e-5):
            raise EntityLinkerError("entity encoder output must be normalized")
        return array

    @staticmethod
    def _select_non_overlapping(proposals: tuple[_Proposal, ...]) -> tuple[_Proposal, ...]:
        ordered = sorted(
            proposals,
            key=lambda item: (
                0 if item.stage == "address" else 1,
                -(item.end - item.start),
                item.start,
                item.target_ids[0],
            ),
        )
        selected: list[_Proposal] = []
        for proposal in ordered:
            if any(proposal.start < item.end and item.start < proposal.end for item in selected):
                continue
            selected.append(proposal)
        return tuple(
            sorted(
                selected,
                key=lambda item: (item.start, -(item.end - item.start), item.target_ids[0]),
            )
        )

    def _match(self, question: str, proposal: _Proposal) -> EntityMatch:
        target_id = proposal.target_ids[0]
        if target_id.startswith("address:"):
            address = target_id.removeprefix("address:")
            return EntityMatch(
                span=question[proposal.start : proposal.end],
                span_offset=(proposal.start, proposal.end),
                target_id=target_id,
                target_kind="address",
                owner=None,
                addresses=(address,),
                categories=(),
                concept_classes=(),
                stage=proposal.stage,
                confidence=proposal.confidence,
                alternatives=(),
                target_sha256=hashlib.sha256(target_id.encode()).hexdigest(),
            )
        target = self._corpus.targets_by_id[target_id]
        alternative_confidences = proposal.alternative_confidences or tuple(
            proposal.confidence for _ in proposal.target_ids
        )
        alternatives = tuple(
            EntityAlternative(
                target_id=alternative_id,
                target_kind=self._corpus.targets_by_id[alternative_id].target_kind,
                confidence=confidence,
            )
            for alternative_id, confidence in zip(
                proposal.target_ids, alternative_confidences, strict=True
            )
        )
        return self._target_match(question, proposal, target, alternatives)

    @staticmethod
    def _target_match(
        question: str,
        proposal: _Proposal,
        target: EntityTarget,
        alternatives: tuple[EntityAlternative, ...],
    ) -> EntityMatch:
        ambiguous = len(alternatives) > 1
        return EntityMatch(
            span=question[proposal.start : proposal.end],
            span_offset=(proposal.start, proposal.end),
            target_id=target.target_id,
            target_kind=target.target_kind,
            owner=target.owner,
            addresses=target.addresses,
            categories=target.categories,
            concept_classes=target.concept_classes,
            stage="ambiguous" if ambiguous else proposal.stage,
            confidence=proposal.confidence,
            alternatives=alternatives if ambiguous else (),
            target_sha256=target.document_sha256,
        )
