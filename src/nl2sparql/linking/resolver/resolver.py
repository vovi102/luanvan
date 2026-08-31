"""Deterministic GoogleSQL entity-constraint resolver."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from nl2sparql.linking.entity import EntityCorpus, EntityMatch, EntityTarget
from nl2sparql.linking.resolver.catalog import load_resolver_catalog
from nl2sparql.linking.resolver.contracts import (
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)
from nl2sparql.linking.schema_linker import LinkResult

MAX_QUESTION_CHARS = 2_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9]")
_FROM_CUE_RE = re.compile(r"(?:\bfrom|\bsent\s+by|\bout\s+of)\s+(?:any\s+)?$", re.IGNORECASE)
_TO_CUE_RE = re.compile(r"(?:\bto|\binto|\breceived\s+by)\s+(?:any\s+)?$", re.IGNORECASE)


class ClassResolver:
    """Resolve T4.2 evidence into catalog-backed, non-executable constraints."""

    def __init__(self, catalog_path: Path, corpus: EntityCorpus) -> None:
        if not isinstance(corpus, EntityCorpus):
            raise ClassResolverError("resolver corpus must be an EntityCorpus")
        self._catalog = load_resolver_catalog(catalog_path)
        self._corpus = corpus

    def resolve(
        self,
        question: str,
        matches: Sequence[EntityMatch],
        schema_links: LinkResult | None = None,
    ) -> ResolutionPlan:
        """Return a provenance-bound constraint plan without rendering SQL."""
        self._validate_question(question)
        if schema_links is not None and not isinstance(schema_links, LinkResult):
            raise ClassResolverError("schema links must be a LinkResult")
        if isinstance(matches, (str, bytes)) or not isinstance(matches, Sequence):
            raise ClassResolverError("entity matches must be a sequence")
        ordered = tuple(matches)
        self._validate_match_order(question, ordered)

        warnings: list[str] = []
        entities: list[ResolvedEntity] = []
        for match in ordered:
            target = self._validated_target(match)
            resolved = self._resolve_match(question, match, target)
            entities.append(resolved)
            if resolved.direction == "unspecified" and resolved.resolution_kind != "unresolved":
                warnings.append(f"direction is unspecified for span {match.span!r}")
        if not entities:
            warnings.append("no entity evidence was supplied")

        frozen_warnings = tuple(sorted(set(warnings)))
        if not entities or all(value.resolution_kind == "unresolved" for value in entities):
            status = "unresolved"
        elif any(value.resolution_kind == "unresolved" for value in entities) or frozen_warnings:
            status = "partial"
        else:
            status = "resolved"
        return ResolutionPlan(
            question_sha256=hashlib.sha256(question.encode()).hexdigest(),
            entities=tuple(entities),
            catalog_sha256=self._catalog.catalog_sha256,
            entities_sha256=self._corpus.entities_sha256,
            aliases_sha256=self._corpus.aliases_sha256,
            concepts_sha256=self._corpus.concepts_sha256,
            status=status,
            warnings=frozen_warnings,
        )

    @staticmethod
    def _validate_question(question: object) -> None:
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question) > MAX_QUESTION_CHARS
            or _CONTROL_RE.search(question)
            or not _TEXT_TOKEN_RE.search(question)
        ):
            raise ClassResolverError(
                "question must contain text, be control-free, and at most "
                f"{MAX_QUESTION_CHARS} chars"
            )

    @staticmethod
    def _validate_match_order(question: str, matches: tuple[EntityMatch, ...]) -> None:
        previous_start = -1
        previous_end = -1
        for match in matches:
            if not isinstance(match, EntityMatch):
                raise ClassResolverError("entity matches must contain EntityMatch values")
            start, end = match.span_offset
            if start < previous_start:
                raise ClassResolverError("entity matches must be ordered by source offset")
            if start < previous_end:
                raise ClassResolverError("entity match spans must not overlap")
            if end > len(question) or question[start:end] != match.span:
                raise ClassResolverError("entity span must equal its original question slice")
            previous_start = start
            previous_end = end

    def _validated_target(self, match: EntityMatch) -> EntityTarget | None:
        if match.target_kind == "address":
            expected = hashlib.sha256(match.target_id.encode()).hexdigest()
            if match.target_sha256 != expected:
                raise ClassResolverError("raw address target fingerprint is invalid")
            return None
        target = self._corpus.targets_by_id.get(match.target_id)
        if target is None:
            raise ClassResolverError(f"unknown target in entity corpus: {match.target_id!r}")
        if match.target_sha256 != target.document_sha256:
            raise ClassResolverError("entity target fingerprint is stale")
        if (
            match.target_kind != target.target_kind
            or match.owner != target.owner
            or match.addresses != target.addresses
            or match.categories != target.categories
            or match.concept_classes != target.concept_classes
        ):
            raise ClassResolverError("entity match metadata disagrees with its corpus target")
        return target

    def _resolve_match(
        self,
        question: str,
        match: EntityMatch,
        target: EntityTarget | None,
    ) -> ResolvedEntity:
        direction = self._direction(question, match.span_offset[0])
        fields = self._fields(direction)
        if match.stage == "ambiguous":
            return self._unresolved(
                match, "Ambiguous entity evidence requires explicit resolution."
            )
        if match.target_kind in {"owner", "address"}:
            if not match.addresses:
                return self._unresolved(match, "Instance target has no verified addresses.")
            return ResolvedEntity(
                span=match.span,
                span_offset=match.span_offset,
                target_id=match.target_id,
                target_sha256=match.target_sha256,
                resolution_kind="instance",
                direction=direction,
                fields=fields,
                operator="in",
                values=match.addresses,
                required_relation=None,
                required_join=None,
                required_role=None,
                coverage_status="supported",
                confidence=match.confidence,
                explanation="Instance target resolved to verified canonical addresses.",
            )
        if target is None or len(target.concept_classes) != 1:
            return self._unresolved(match, "Concept target lacks one canonical concept class.")
        return ResolvedEntity(
            span=match.span,
            span_offset=match.span_offset,
            target_id=match.target_id,
            target_sha256=match.target_sha256,
            resolution_kind="concept",
            direction=direction,
            fields=fields,
            operator="equals",
            values=target.concept_classes,
            required_relation=self._catalog.entity_relation,
            required_join=self._catalog.entity_join,
            required_role=None,
            coverage_status="supported",
            confidence=match.confidence,
            explanation="Concept target resolved through the catalog entity-label lookup.",
        )

    @staticmethod
    def _direction(question: str, start: int) -> str:
        prefix = question[max(0, start - 40) : start]
        if _FROM_CUE_RE.search(prefix):
            return "from"
        if _TO_CUE_RE.search(prefix):
            return "to"
        return "unspecified"

    def _fields(self, direction: str) -> tuple[FieldCandidate, ...]:
        if direction in self._catalog.fields_by_direction:
            return self._catalog.fields_by_direction[direction]
        return tuple(
            sorted(
                {field for values in self._catalog.fields_by_direction.values() for field in values}
            )
        )

    @staticmethod
    def _unresolved(match: EntityMatch, explanation: str) -> ResolvedEntity:
        return ResolvedEntity(
            span=match.span,
            span_offset=match.span_offset,
            target_id=match.target_id,
            target_sha256=match.target_sha256,
            resolution_kind="unresolved",
            direction="unspecified",
            fields=(),
            operator="none",
            values=(),
            required_relation=None,
            required_join=None,
            required_role=None,
            coverage_status="unresolved",
            confidence=match.confidence,
            explanation=explanation,
        )
