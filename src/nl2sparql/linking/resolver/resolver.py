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
from nl2sparql.linking.schema_linker import LinkResult, SchemaMatch

MAX_QUESTION_CHARS = 2_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9]")
_FROM_CUE_RE = re.compile(r"\b(?:from|sent\s+by|out\s+of)\b", re.IGNORECASE)
_TO_CUE_RE = re.compile(r"\b(?:to|into|received\s+by)\b", re.IGNORECASE)
_CLASS_TRIGGER_RE = re.compile(r"\b(?:any|all|every|major)\s+$", re.IGNORECASE)


class ClassResolver:
    """Resolve T4.2 evidence into catalog-backed, non-executable constraints."""

    def __init__(self, catalog_path: Path, corpus: EntityCorpus) -> None:
        if not isinstance(corpus, EntityCorpus):
            raise ClassResolverError("resolver corpus must be an EntityCorpus")
        self._catalog = load_resolver_catalog(catalog_path)
        self._corpus = corpus
        owners_by_class: dict[str, list[EntityTarget]] = {}
        for target in corpus.targets:
            if target.target_kind != "owner" or not target.addresses:
                continue
            for concept_class in target.concept_classes:
                owners_by_class.setdefault(concept_class, []).append(target)
        self._owners_by_class = {
            key: tuple(values) for key, values in sorted(owners_by_class.items())
        }

    def resolve(
        self,
        question: str,
        matches: Sequence[EntityMatch],
        schema_links: LinkResult | None = None,
    ) -> ResolutionPlan:
        """Return a provenance-bound constraint plan without rendering SQL."""
        self._validate_question(question)
        linked_relations, linked_fields = self._validate_schema_links(schema_links)
        if isinstance(matches, (str, bytes)) or not isinstance(matches, Sequence):
            raise ClassResolverError("entity matches must be a sequence")
        ordered = tuple(matches)
        self._validate_match_order(question, ordered)

        warnings: list[str] = []
        entities: list[ResolvedEntity] = []
        for match in ordered:
            target = self._validated_target(match)
            resolved, match_warnings = self._resolve_match(
                question,
                match,
                target,
                linked_relations,
                linked_fields,
                schema_links is not None,
            )
            entities.append(resolved)
            warnings.extend(match_warnings)
            if resolved.direction == "unspecified" and resolved.resolution_kind != "unresolved":
                warnings.append(f"direction is unspecified for span {match.span!r}")
        if not entities:
            warnings.append("no entity evidence was supplied")

        direction_counts: dict[str, int] = {}
        for entity in entities:
            if entity.direction != "unspecified":
                direction_counts[entity.direction] = direction_counts.get(entity.direction, 0) + 1
        warnings.extend(
            f"multiple entities resolve to direction {direction!r}"
            for direction, count in direction_counts.items()
            if count > 1
        )

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
        if match.stage == "ambiguous":
            for alternative in match.alternatives:
                alternative_target = self._corpus.targets_by_id.get(alternative.target_id)
                if (
                    alternative_target is None
                    or alternative_target.target_kind != alternative.target_kind
                ):
                    raise ClassResolverError("ambiguous alternative is absent from the corpus")
        return target

    def _validate_schema_links(
        self, schema_links: LinkResult | None
    ) -> tuple[frozenset[str], frozenset[FieldCandidate]]:
        if schema_links is None:
            return frozenset(), frozenset()
        if not isinstance(schema_links, LinkResult):
            raise ClassResolverError("schema links must be a LinkResult")
        if not isinstance(schema_links.relations, tuple) or not isinstance(
            schema_links.fields, tuple
        ):
            raise ClassResolverError("schema link pools must be tuples")
        relations: set[str] = set()
        fields: set[FieldCandidate] = set()
        for match in schema_links.relations:
            if (
                not isinstance(match, SchemaMatch)
                or match.kind != "relation"
                or match.element_id not in self._catalog.all_relations
            ):
                raise ClassResolverError("schema link contains an unknown relation")
            relations.add(match.element_id)
        for match in schema_links.fields:
            if not isinstance(match, SchemaMatch) or match.kind != "field":
                raise ClassResolverError("schema link contains an invalid field match")
            parts = match.element_id.split(".")
            if len(parts) != 2:
                raise ClassResolverError("schema link field identity is malformed")
            candidate = FieldCandidate(*parts)
            if candidate not in self._catalog.all_fields:
                raise ClassResolverError("schema link contains an unknown field")
            fields.add(candidate)
        return frozenset(relations), frozenset(fields)

    def _resolve_match(
        self,
        question: str,
        match: EntityMatch,
        target: EntityTarget | None,
        linked_relations: frozenset[str],
        linked_fields: frozenset[FieldCandidate],
        has_schema_links: bool,
    ) -> tuple[ResolvedEntity, tuple[str, ...]]:
        direction = self._direction(question, match.span_offset[0])
        if direction == "unspecified":
            schema_directions = {
                candidate_direction
                for candidate_direction, candidates in self._catalog.fields_by_direction.items()
                if any(candidate in linked_fields for candidate in candidates)
            }
            if len(schema_directions) == 1:
                direction = next(iter(schema_directions))
        fields, field_warning = self._fields(
            direction, linked_relations, linked_fields, has_schema_links
        )
        warnings = (field_warning,) if field_warning is not None else ()

        if match.stage == "ambiguous":
            selected = self._triggered_concept(question, match)
            if selected is None:
                return (
                    self._unresolved(
                        match, "Ambiguous entity evidence requires explicit resolution."
                    ),
                    warnings,
                )
            concept, confidence = selected
            return self._resolved_concept(match, concept, confidence, direction, fields), warnings

        if match.target_kind in {"owner", "address"}:
            if not match.addresses:
                return (
                    self._unresolved(match, "Instance target has no verified addresses."),
                    warnings,
                )
            return (
                ResolvedEntity(
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
                ),
                warnings,
            )

        if target is None or len(target.concept_classes) != 1:
            return (
                self._unresolved(match, "Concept target lacks one canonical concept class."),
                warnings,
            )
        return self._resolved_concept(match, target, match.confidence, direction, fields), warnings

    def _resolved_concept(
        self,
        match: EntityMatch,
        target: EntityTarget,
        confidence: float,
        direction: str,
        fields: tuple[FieldCandidate, ...],
    ) -> ResolvedEntity:
        concept_class = target.concept_classes[0]
        supporters = self._owners_by_class.get(concept_class, ())
        if supporters:
            common_roles = set(self._catalog.allowed_roles)
            for supporter in supporters:
                common_roles.intersection_update(supporter.address_roles)
            required_role = next(iter(common_roles)) if len(common_roles) == 1 else None
            coverage_status = "supported"
            explanation = "Concept target resolved through the catalog entity-label lookup."
        else:
            required_role = None
            coverage_status = "coverage_gap"
            explanation = "Concept is representable but has no accepted address coverage."
        return ResolvedEntity(
            span=match.span,
            span_offset=match.span_offset,
            target_id=target.target_id,
            target_sha256=target.document_sha256,
            resolution_kind="concept",
            direction=direction,
            fields=fields,
            operator="equals",
            values=target.concept_classes,
            required_relation=self._catalog.entity_relation,
            required_join=self._catalog.entity_join,
            required_role=required_role,
            coverage_status=coverage_status,
            confidence=confidence,
            explanation=explanation,
        )

    def _triggered_concept(
        self, question: str, match: EntityMatch
    ) -> tuple[EntityTarget, float] | None:
        prefix = question[max(0, match.span_offset[0] - 20) : match.span_offset[0]]
        class_trigger = bool(_CLASS_TRIGGER_RE.search(prefix)) or match.span.casefold().endswith(
            "s"
        )
        if not class_trigger:
            return None
        concepts = [value for value in match.alternatives if value.target_kind == "concept"]
        if len(concepts) != 1:
            return None
        alternative = concepts[0]
        target = self._corpus.targets_by_id.get(alternative.target_id)
        if target is None or target.target_kind != "concept" or len(target.concept_classes) != 1:
            raise ClassResolverError("ambiguous concept alternative is absent from the corpus")
        return target, alternative.confidence

    @staticmethod
    def _direction(question: str, start: int) -> str:
        prefix = question[max(0, start - 40) : start]
        from_matches = tuple(_FROM_CUE_RE.finditer(prefix))
        to_matches = tuple(_TO_CUE_RE.finditer(prefix))
        if from_matches and to_matches:
            source = from_matches[-1]
            destination = to_matches[-1]
            earlier, later = sorted((source, destination), key=lambda value: value.start())
            bridge = prefix[earlier.end() : later.start()].casefold().strip()
            if bridge in {"and", "or", "and/or", "/"}:
                return "unspecified"
            return "from" if source.start() > destination.start() else "to"
        if from_matches:
            return "from"
        if to_matches:
            return "to"
        return "unspecified"

    def _fields(
        self,
        direction: str,
        linked_relations: frozenset[str],
        linked_fields: frozenset[FieldCandidate],
        has_schema_links: bool,
    ) -> tuple[tuple[FieldCandidate, ...], str | None]:
        if direction in self._catalog.fields_by_direction:
            base = self._catalog.fields_by_direction[direction]
        else:
            base = tuple(
                sorted(
                    {
                        field
                        for values in self._catalog.fields_by_direction.values()
                        for field in values
                    }
                )
            )
        if not has_schema_links:
            return base, None
        narrowed = tuple(
            field
            for field in base
            if (not linked_relations or field.relation in linked_relations)
            and (not linked_fields or field in linked_fields)
        )
        if narrowed:
            return narrowed, None
        return base, "schema links do not intersect catalog address candidates"

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
