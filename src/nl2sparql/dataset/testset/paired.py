"""Strict paired English–Vietnamese benchmark and review contracts."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Literal

from nl2sparql.dataset.testset.contracts import TestSetError, _text
from nl2sparql.dataset.testset.reviewed_contracts import (
    BILINGUAL_AUTHORSHIP_PROFILE,
    BILINGUAL_REVIEW_PROFILE,
)
from nl2sparql.dataset.testset.reviewed_validate import normalize_google_sql
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.language import normalize_input

AUTHORSHIP_PROFILE = BILINGUAL_AUTHORSHIP_PROFILE
REVIEW_PROFILE = BILINGUAL_REVIEW_PROFILE
PAIRED_SCHEMA_VERSION = "1.0.0"

_SHA256 = frozenset("0123456789abcdef")
_CANDIDATE_FIELDS = frozenset(
    {
        "pair_id",
        "english_id",
        "question",
        "sql",
        "expected_columns",
        "expected_result_size",
        "difficulty",
        "categories",
        "entity_kinds",
        "schema_elements",
        "cq_ids",
        "english_case_sha256",
        "authorship_profile",
        "review_profile",
    }
)
_DECISION_FIELDS = frozenset(
    {
        "pair_id",
        "review_round",
        "reviewer_role",
        "decision",
        "naturalness",
        "sql_faithfulness",
        "terminology",
        "ambiguity",
        "revised_question",
        "notes",
    }
)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256 for character in value)
    ):
        raise TestSetError(f"{field} must be a lower-case SHA-256 digest")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TestSetError(f"{field} must be an array")
    result = tuple(_text(item, field) for item in value)
    if len(result) != len(set(result)):
        raise TestSetError(f"{field} must be unique")
    return result


@dataclass(frozen=True, slots=True)
class EnglishPairCase:
    """Immutable English benchmark semantics used as the pairing authority."""

    id: str
    question: str
    sql: str
    expected_columns: tuple[str, ...]
    expected_result_size: int | None
    difficulty: str
    categories: tuple[str, ...]
    entity_kinds: tuple[str, ...]
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.id, "English case ID")
        _text(self.question, "English question")
        validate_sql_text(self.sql)
        if not self.expected_columns:
            raise TestSetError("English expected_columns must not be empty")
        if self.expected_result_size is not None and self.expected_result_size < 0:
            raise TestSetError("English expected_result_size must be non-negative")

    @property
    def sha256(self) -> str:
        """Return the canonical digest of the immutable English case."""
        return _sha256(asdict(self))


@dataclass(frozen=True, slots=True)
class PairedCandidate:
    """One agent-authored Vietnamese candidate paired to an English case."""

    pair_id: str
    english_id: str
    question: str
    sql: str
    expected_columns: tuple[str, ...]
    expected_result_size: int | None
    difficulty: str
    categories: tuple[str, ...]
    entity_kinds: tuple[str, ...]
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    english_case_sha256: str
    authorship_profile: str = AUTHORSHIP_PROFILE
    review_profile: str = REVIEW_PROFILE

    def __post_init__(self) -> None:
        _text(self.pair_id, "pair_id")
        _text(self.english_id, "english_id")
        normalize_input(self.question, language="vi")
        validate_sql_text(self.sql)
        _digest(self.english_case_sha256, "english_case_sha256")
        if self.authorship_profile != AUTHORSHIP_PROFILE:
            raise TestSetError(f"authorship_profile must be {AUTHORSHIP_PROFILE}")
        if self.review_profile != REVIEW_PROFILE:
            raise TestSetError(f"review_profile must be {REVIEW_PROFILE}")

    def to_mapping(self) -> dict[str, object]:
        """Serialize the exact candidate schema."""
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> PairedCandidate:
        """Decode a candidate while rejecting missing or inflated provenance."""
        if set(value) != _CANDIDATE_FIELDS:
            raise TestSetError("paired candidate fields mismatch")
        converted = dict(value)
        for field in (
            "expected_columns",
            "categories",
            "entity_kinds",
            "schema_elements",
            "cq_ids",
        ):
            converted[field] = _string_tuple(converted[field], field)
        try:
            return cls(**converted)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TestSetError("paired candidate schema mismatch") from exc

    @property
    def sha256(self) -> str:
        """Return the canonical digest of this draft candidate."""
        return _sha256(asdict(self))


@dataclass(frozen=True, slots=True)
class PairedReviewDecision:
    """One append-only decision made by the single real user reviewer."""

    pair_id: str
    review_round: int
    reviewer_role: Literal["user"]
    decision: Literal["ACCEPT", "REVISE", "REJECT"]
    naturalness: int
    sql_faithfulness: int
    terminology: int
    ambiguity: int
    revised_question: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        _text(self.pair_id, "pair_id")
        if not isinstance(self.review_round, int) or isinstance(self.review_round, bool):
            raise TestSetError("review_round must be an integer")
        if self.review_round < 1:
            raise TestSetError("review_round must start at 1")
        if self.reviewer_role != "user":
            raise TestSetError("reviewer_role must identify the actual user")
        if self.decision not in {"ACCEPT", "REVISE", "REJECT"}:
            raise TestSetError("unknown review decision")
        scores = (self.naturalness, self.sql_faithfulness, self.terminology, self.ambiguity)
        if any(
            not isinstance(score, int) or isinstance(score, bool) or score not in range(1, 6)
            for score in scores
        ):
            raise TestSetError("review scores must be integers from 1 to 5")
        revised = self.revised_question.strip()
        if self.decision == "REVISE" and not revised:
            raise TestSetError("REVISE requires revised_question")
        if self.decision != "REVISE" and revised:
            raise TestSetError(f"{self.decision} must not contain revised_question")
        object.__setattr__(self, "revised_question", revised)
        object.__setattr__(self, "notes", self.notes.strip())

    def to_mapping(self) -> dict[str, object]:
        """Serialize the exact non-inflated review schema."""
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> PairedReviewDecision:
        """Decode a decision while rejecting fabricated provenance fields."""
        if set(value) != _DECISION_FIELDS:
            raise TestSetError("paired review decision fields mismatch")
        try:
            return cls(**value)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TestSetError("paired review decision schema mismatch") from exc


@dataclass(frozen=True, slots=True)
class PairingReport:
    """Hash-bound result of exact one-to-one semantic pairing."""

    status: str
    pair_count: int
    authorship_profile: str
    review_profile: str
    english_sha256: str
    candidate_sha256: str


@dataclass(frozen=True, slots=True)
class PairedFinalCase:
    """One accepted Vietnamese case with immutable source and pairing evidence."""

    id: str
    pair_id: str
    english_id: str
    question: str
    original_question: str
    nfc: str
    match: str
    accent_folded: str
    language: Literal["vi"]
    text_variant: Literal["canonical", "unaccented"]
    sql: str
    expected_columns: tuple[str, ...]
    expected_result_size: int | None
    difficulty: str
    categories: tuple[str, ...]
    entity_kinds: tuple[str, ...]
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    english_case_sha256: str
    candidate_sha256: str
    review_sha256: str
    authorship_profile: str
    review_profile: str
    accented_parent_id: str | None = None
    accented_parent_sha256: str | None = None

    @property
    def sha256(self) -> str:
        """Return the canonical digest of this finalized case."""
        return _sha256(asdict(self))


def validate_pairing(
    english: Sequence[EnglishPairCase],
    vietnamese: Sequence[PairedCandidate],
) -> PairingReport:
    """Validate exactly 100 one-to-one pairs against English semantics."""
    if len(english) != 100 or len(vietnamese) != 100:
        raise TestSetError("paired benchmark requires exactly 100 English and Vietnamese cases")
    english_ids = [case.id for case in english]
    pair_ids = [case.pair_id for case in vietnamese]
    if len(english_ids) != len(set(english_ids)) or len(pair_ids) != len(set(pair_ids)):
        raise TestSetError("paired benchmark requires unique pair and English IDs")
    english_by_id = {case.id: case for case in english}
    if {case.english_id for case in vietnamese} != set(english_ids):
        raise TestSetError("Vietnamese candidates must cover every English ID exactly once")

    comparable = (
        "expected_columns",
        "expected_result_size",
        "difficulty",
        "categories",
        "entity_kinds",
        "schema_elements",
        "cq_ids",
        "english_case_sha256",
    )
    for candidate in vietnamese:
        source = english_by_id[candidate.english_id]
        if normalize_google_sql(candidate.sql) != normalize_google_sql(source.sql):
            raise TestSetError(f"{candidate.pair_id} sql does not match its English pair")
        for field in comparable:
            expected = source.sha256 if field == "english_case_sha256" else getattr(source, field)
            if getattr(candidate, field) != expected:
                raise TestSetError(f"{candidate.pair_id} {field} does not match its English pair")
    return PairingReport(
        status="paired_draft_valid",
        pair_count=100,
        authorship_profile=AUTHORSHIP_PROFILE,
        review_profile=REVIEW_PROFILE,
        english_sha256=_sha256([asdict(case) for case in english]),
        candidate_sha256=_sha256([asdict(case) for case in vietnamese]),
    )


def _accepted_question(
    candidate: PairedCandidate,
    decisions: Sequence[PairedReviewDecision],
) -> tuple[str, str]:
    if not decisions:
        raise TestSetError(f"{candidate.pair_id} is pending without an explicit ACCEPT")
    rounds = [decision.review_round for decision in decisions]
    if rounds != list(range(1, len(decisions) + 1)):
        raise TestSetError(f"{candidate.pair_id} review rounds must be contiguous")
    question = candidate.question
    accepted = False
    for index, decision in enumerate(decisions):
        if accepted:
            raise TestSetError(f"{candidate.pair_id} has review events after ACCEPT")
        if decision.decision == "REJECT":
            raise TestSetError(f"{candidate.pair_id} was rejected")
        if decision.decision == "REVISE":
            question = decision.revised_question
            normalize_input(question, language="vi")
            continue
        if index != len(decisions) - 1:
            raise TestSetError(f"{candidate.pair_id} has review events after ACCEPT")
        if (
            decision.naturalness < 4
            or decision.sql_faithfulness < 4
            or decision.terminology < 4
            or decision.ambiguity > 2
        ):
            raise TestSetError(f"{candidate.pair_id} ACCEPT scores do not meet policy")
        accepted = True
    if not accepted:
        raise TestSetError(f"{candidate.pair_id} remains pending without a later ACCEPT")
    return question, _sha256([decision.to_mapping() for decision in decisions])


def finalize_paired_cases(
    english: Sequence[EnglishPairCase],
    candidates: Sequence[PairedCandidate],
    decisions: Sequence[PairedReviewDecision],
) -> tuple[PairedFinalCase, ...]:
    """Finalize only after the user explicitly accepts all 100 Vietnamese pairs."""
    validate_pairing(english, candidates)
    decisions_by_pair: defaultdict[str, list[PairedReviewDecision]] = defaultdict(list)
    known_pairs = {candidate.pair_id for candidate in candidates}
    for decision in decisions:
        if decision.pair_id not in known_pairs:
            raise TestSetError(f"unknown reviewed pair {decision.pair_id}")
        decisions_by_pair[decision.pair_id].append(decision)
    if set(decisions_by_pair) != known_pairs:
        raise TestSetError("finalization requires 100 explicit ACCEPT decisions")

    finalized: list[PairedFinalCase] = []
    for candidate in candidates:
        question, review_sha256 = _accepted_question(
            candidate, decisions_by_pair[candidate.pair_id]
        )
        normalized = normalize_input(question, language="vi")
        finalized.append(
            PairedFinalCase(
                id=f"vi-{candidate.english_id}",
                pair_id=candidate.pair_id,
                english_id=candidate.english_id,
                question=question,
                original_question=candidate.question,
                nfc=normalized.nfc,
                match=normalized.match,
                accent_folded=normalized.accent_folded,
                language="vi",
                text_variant="canonical",
                sql=candidate.sql,
                expected_columns=candidate.expected_columns,
                expected_result_size=candidate.expected_result_size,
                difficulty=candidate.difficulty,
                categories=candidate.categories,
                entity_kinds=candidate.entity_kinds,
                schema_elements=candidate.schema_elements,
                cq_ids=candidate.cq_ids,
                english_case_sha256=candidate.english_case_sha256,
                candidate_sha256=candidate.sha256,
                review_sha256=review_sha256,
                authorship_profile=AUTHORSHIP_PROFILE,
                review_profile=REVIEW_PROFILE,
            )
        )
    if len(finalized) != 100:
        raise TestSetError("finalization requires 100 explicit ACCEPT decisions")
    return tuple(finalized)


def _remove_vietnamese_accents(value: str) -> str:
    translated = value.translate(str.maketrans({"đ": "d", "Đ": "D"}))
    decomposed = unicodedata.normalize("NFD", translated)
    return unicodedata.normalize(
        "NFC",
        "".join(character for character in decomposed if unicodedata.category(character) != "Mn"),
    )


def derive_unaccented_cases(cases: Sequence[PairedFinalCase]) -> tuple[PairedFinalCase, ...]:
    """Derive an unaccented robustness slice while retaining parent evidence."""
    derived: list[PairedFinalCase] = []
    seen: set[str] = set()
    for case in cases:
        if case.text_variant != "canonical" or case.language != "vi":
            raise TestSetError("unaccented derivation requires canonical Vietnamese cases")
        question = _remove_vietnamese_accents(case.nfc)
        if question == case.nfc:
            raise TestSetError(f"{case.id} unaccented transformation is unchanged")
        normalized = normalize_input(question, language="vi")
        if normalized.match in seen:
            raise TestSetError("unaccented transformation creates a normalized collision")
        seen.add(normalized.match)
        derived.append(
            replace(
                case,
                id=f"{case.id}-unaccented",
                question=question,
                nfc=normalized.nfc,
                match=normalized.match,
                accent_folded=normalized.accent_folded,
                text_variant="unaccented",
                accented_parent_id=case.id,
                accented_parent_sha256=case.sha256,
            )
        )
    return tuple(derived)


@dataclass(frozen=True, slots=True)
class PairedManifest:
    """Content-addressed manifest for one accented or unaccented paired slice."""

    schema_version: str
    text_variant: str
    record_count: int
    output_sha256: str
    english_benchmark_sha256: str
    parent_manifest_sha256: str | None
    authorship_profile: str
    review_profile: str
    manifest_sha256: str


def _manifest_body(manifest: PairedManifest) -> dict[str, object]:
    return {key: value for key, value in asdict(manifest).items() if key != "manifest_sha256"}


def build_paired_manifest(
    cases: Sequence[PairedFinalCase],
    *,
    english_benchmark_sha256: str,
    parent_manifest_sha256: str | None = None,
) -> PairedManifest:
    """Build a manifest bound to English and, for unaccented data, its parent."""
    _digest(english_benchmark_sha256, "english_benchmark_sha256")
    if len(cases) != 100:
        raise TestSetError("paired manifest requires exactly 100 records")
    variants = {case.text_variant for case in cases}
    if len(variants) != 1:
        raise TestSetError("paired manifest records must share one text variant")
    variant = next(iter(variants))
    if variant == "unaccented":
        _digest(parent_manifest_sha256, "parent_manifest_sha256")
    elif parent_manifest_sha256 is not None:
        raise TestSetError("canonical manifest must not declare a parent manifest")
    body = {
        "schema_version": PAIRED_SCHEMA_VERSION,
        "text_variant": variant,
        "record_count": len(cases),
        "output_sha256": _sha256([asdict(case) for case in cases]),
        "english_benchmark_sha256": english_benchmark_sha256,
        "parent_manifest_sha256": parent_manifest_sha256,
        "authorship_profile": AUTHORSHIP_PROFILE,
        "review_profile": REVIEW_PROFILE,
    }
    return PairedManifest(**body, manifest_sha256=_sha256(body))


def validate_paired_manifest(cases: Sequence[PairedFinalCase], manifest: PairedManifest) -> None:
    """Fail closed when a paired manifest or its output binding was changed."""
    if manifest.manifest_sha256 != _sha256(_manifest_body(manifest)):
        raise TestSetError("paired manifest hash mismatch")
    if manifest.record_count != len(cases):
        raise TestSetError("paired output hash/count mismatch")
    if manifest.output_sha256 != _sha256([asdict(case) for case in cases]):
        raise TestSetError("paired output hash mismatch")
    if any(case.text_variant != manifest.text_variant for case in cases):
        raise TestSetError("paired manifest text variant mismatch")
