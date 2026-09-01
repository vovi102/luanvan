"""Deterministic template selection and safe GoogleSQL rendering for B0."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

from nl2sparql.dataset.templates import TemplateValidationError, render_template
from nl2sparql.dataset.testset import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.linking.resolver import ResolutionPlan
from nl2sparql.linking.schema_linker import LinkResult
from nl2sparql.models.b0.contracts import (
    B0Error,
    B0Policy,
    B0Prediction,
    LinkingProvenance,
)
from nl2sparql.models.b0.slots import extract_seed_slots, extract_structural_slots, slot_mapping
from nl2sparql.models.b0.templates import CompiledTemplate, compile_template_snapshot

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MASK_RE = re.compile(
    r"(?<!\w)0x[0-9a-f]{40,64}(?!\w)|(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)|"
    r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])",
    re.IGNORECASE,
)
_DEFAULT_POLICY = B0Policy()


def validate_b0_question(question: object) -> str:
    """Validate one public B0 question before loading expensive dependencies.

    Args:
        question: Candidate natural-language question.

    Returns:
        The validated question unchanged.

    Raises:
        B0Error: If the question is malformed or outside the accepted bounds.
    """
    if (
        not isinstance(question, str)
        or not question.strip()
        or len(question) > 2_000
        or _CONTROL_RE.search(question)
        or not _TOKEN_RE.search(unicodedata.normalize("NFKC", question).casefold())
    ):
        raise B0Error("question must contain text, be control-free, and at most 2000 chars")
    return question


class _SchemaLinker(Protocol):
    def link(self, question: str) -> LinkResult: ...


class _EntityLinker(Protocol):
    def link(self, question: str) -> tuple[Any, ...]: ...


class _ClassResolver(Protocol):
    def resolve(
        self,
        question: str,
        matches: tuple[Any, ...],
        schema_links: LinkResult | None = None,
    ) -> ResolutionPlan: ...


def _normalized_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(_TOKEN_RE.findall(normalized))


def _normalized_seed(value: str) -> tuple[str, dict[int, int]]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    boundaries: dict[int, int] = {}
    for original_offset in range(len(value) + 1):
        prefix = unicodedata.normalize("NFKC", value[:original_offset]).casefold()
        boundaries[len(prefix)] = original_offset
    return normalized, boundaries


def _token_f1(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    if not left or not right:
        return 0.0
    left_counts = Counter(left)
    right_counts = Counter(right)
    overlap = sum((left_counts & right_counts).values())
    precision = overlap / sum(left_counts.values())
    recall = overlap / sum(right_counts.values())
    return 2.0 * precision * recall / (precision + recall) if overlap else 0.0


class BaselineB0:
    """Select, fill, and validate one accepted GoogleSQL template or abstain.

    Args:
        templates_path: Accepted template-library snapshot.
        schema_linker: Optional schema evidence provider for ambiguity resolution.
        entity_linker: Optional entity evidence provider for linked slots.
        class_resolver: Optional resolver for entity constraints.
        linking_provenance: Expected fingerprints for all linking evidence.
        policy: Deterministic matching and abstention policy.

    Raises:
        B0Error: If policy or provenance inputs are invalid.
    """

    def __init__(
        self,
        templates_path: Path,
        *,
        schema_linker: _SchemaLinker | None = None,
        entity_linker: _EntityLinker | None = None,
        class_resolver: _ClassResolver | None = None,
        linking_provenance: LinkingProvenance | None = None,
        policy: B0Policy = _DEFAULT_POLICY,
    ) -> None:
        if not isinstance(policy, B0Policy):
            raise B0Error("B0 policy is invalid")
        if linking_provenance is not None and not isinstance(linking_provenance, LinkingProvenance):
            raise B0Error("linking provenance is invalid")
        self._templates = compile_template_snapshot(templates_path, policy)
        self._schema_linker = schema_linker
        self._entity_linker = entity_linker
        self._class_resolver = class_resolver
        self._linking_provenance = linking_provenance
        self._policy = policy

    @property
    def template_sha256(self) -> str:
        """Return the exact template snapshot fingerprint.

        Returns:
            Lowercase SHA-256 digest of the template snapshot.
        """
        return self._templates[0].template_sha256

    @property
    def policy_sha256(self) -> str:
        """Return the effective matching-policy fingerprint.

        Returns:
            Lowercase SHA-256 digest of the effective policy.
        """
        return self._policy.sha256

    @property
    def linking_provenance(self) -> LinkingProvenance | None:
        """Return expected resolver provenance when linking is configured.

        Returns:
            Bound linking fingerprints, or ``None`` when linking is not configured.
        """
        return self._linking_provenance

    def predict(self, nl: str) -> str | None:
        """Return one safe GoogleSQL prediction or abstain.

        Args:
            nl: Natural-language question.

        Returns:
            Validated GoogleSQL text, or ``None`` when the baseline abstains.

        Raises:
            B0Error: If the question is invalid.
        """
        prediction = self.predict_detailed(nl)
        return prediction.sql if prediction is not None else None

    def predict_detailed(self, nl: str) -> B0Prediction | None:
        """Return a provenance-bound prediction or abstain on uncertainty.

        Args:
            nl: Natural-language question.

        Returns:
            Detailed validated prediction, or ``None`` when the baseline abstains.

        Raises:
            B0Error: If the question is invalid.
        """
        self._validate_question(nl)
        seed_question, source_boundaries = _normalized_seed(nl)
        seed_predictions: list[B0Prediction] = []
        for template in self._templates:
            match = template.seed_pattern.fullmatch(seed_question)
            if match is None:
                continue
            try:
                source_offsets = {
                    name: (
                        source_boundaries[match.start(name)],
                        source_boundaries[match.end(name)],
                    )
                    for name in template.slot_order
                }
            except KeyError:
                continue
            plan: ResolutionPlan | None = None
            if self._requires_resolution(template):
                _, plan, valid = self._entity_evidence(nl)
                if not valid:
                    continue
            slots = extract_seed_slots(
                template,
                nl,
                match,
                plan,
                expected_provenance=self._linking_provenance,
                source_offsets=source_offsets,
            )
            prediction = self._render(template, slots, "seed", 1.0, plan)
            if prediction is not None:
                seed_predictions.append(prediction)
        if seed_predictions:
            specificity = max(
                self._template(prediction.template_id).literal_token_count
                for prediction in seed_predictions
            )
            winners = [
                prediction
                for prediction in seed_predictions
                if self._template(prediction.template_id).literal_token_count == specificity
            ]
            return winners[0] if len(winners) == 1 else None
        return self._structural_prediction(nl)

    @staticmethod
    def _validate_question(question: object) -> None:
        validate_b0_question(question)

    def _template(self, template_id: str) -> CompiledTemplate:
        return next(template for template in self._templates if template.template_id == template_id)

    @staticmethod
    def _requires_resolution(template: CompiledTemplate) -> bool:
        slots = template.raw["slots"]
        return any(
            slots[name]["type"] in {"concept_class", "entity_owner", "entity_category"}
            for name in template.slot_order
        )

    def _entity_evidence(
        self,
        question: str,
    ) -> tuple[tuple[Any, ...], ResolutionPlan | None, bool]:
        if self._entity_linker is None:
            return (), None, True
        try:
            matches = self._entity_linker.link(question)
            if not isinstance(matches, tuple):
                return (), None, False
            if not matches:
                return (), None, True
            if self._class_resolver is None:
                return matches, None, False
            plan = self._class_resolver.resolve(question, matches)
            return matches, plan, True
        except (OSError, RuntimeError, TypeError, ValueError):
            return (), None, False

    def _structural_prediction(self, question: str) -> B0Prediction | None:
        matches, plan, valid = self._entity_evidence(question)
        if not valid:
            return None
        masked = list(question)
        spans = [match.span() for match in _MASK_RE.finditer(question)]
        spans.extend(
            match.span_offset
            for match in matches
            if hasattr(match, "span_offset")
            and isinstance(match.span_offset, tuple)
            and len(match.span_offset) == 2
        )
        for start, end in spans:
            if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(masked):
                masked[start:end] = " " * (end - start)
        question_tokens = _normalized_tokens("".join(masked))
        candidates: list[tuple[float, CompiledTemplate, B0Prediction]] = []
        for template in self._templates:
            score = _token_f1(question_tokens, template.literal_tokens)
            if score < self._policy.structural_threshold:
                continue
            slots = extract_structural_slots(
                template,
                question,
                plan,
                expected_provenance=self._linking_provenance,
            )
            prediction = self._render(template, slots, "structural", score, plan)
            if prediction is not None:
                candidates.append((score, template, prediction))
        if not candidates:
            return None
        candidates.sort(key=lambda row: (-row[0], row[1].template_id))
        best_score = candidates[0][0]
        tied = [row for row in candidates if best_score - row[0] <= self._policy.ambiguity_margin]
        if len(tied) == 1:
            return tied[0][2]
        return self._break_schema_tie(question, tied)

    def _break_schema_tie(
        self,
        question: str,
        tied: list[tuple[float, CompiledTemplate, B0Prediction]],
    ) -> B0Prediction | None:
        if self._schema_linker is None:
            return None
        try:
            links = self._schema_linker.link(question)
            if not isinstance(links, LinkResult):
                return None
            identities = {
                match.element_id
                for match in (*links.relations, *links.fields)
                if isinstance(match.element_id, str) and match.element_id
            }
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return None
        ranked = [
            (len(identities & set(template.schema_elements)), template.template_id, prediction)
            for _, template, prediction in tied
        ]
        best_overlap = max(row[0] for row in ranked)
        winners = [row for row in ranked if row[0] == best_overlap]
        return winners[0][2] if best_overlap > 0 and len(winners) == 1 else None

    def _render(
        self,
        template: CompiledTemplate,
        slots: tuple[Any, ...] | None,
        match_mode: str,
        score: float,
        plan: ResolutionPlan | None,
    ) -> B0Prediction | None:
        if slots is None or not math.isfinite(score):
            return None
        try:
            sql = render_template(template.raw, slot_mapping(slots))
            validate_sql_text(sql)
            provenance = self._linking_provenance
            return B0Prediction(
                sql=sql,
                template_id=template.template_id,
                match_mode=match_mode,
                score=float(score),
                slots=slots,
                template_sha256=template.template_sha256,
                policy_sha256=self._policy.sha256,
                catalog_sha256=(
                    plan.catalog_sha256
                    if plan is not None
                    else provenance.catalog_sha256
                    if provenance is not None
                    else None
                ),
                entities_sha256=(
                    plan.entities_sha256
                    if plan is not None
                    else provenance.entities_sha256
                    if provenance is not None
                    else None
                ),
                aliases_sha256=(
                    plan.aliases_sha256
                    if plan is not None
                    else provenance.aliases_sha256
                    if provenance is not None
                    else None
                ),
                concepts_sha256=(
                    plan.concepts_sha256
                    if plan is not None
                    else provenance.concepts_sha256
                    if provenance is not None
                    else None
                ),
                schema_elements=template.schema_elements,
                cq_ids=template.cq_ids,
                warnings=(),
            )
        except (B0Error, TemplateValidationError, TestSetError, TypeError, ValueError):
            return None
