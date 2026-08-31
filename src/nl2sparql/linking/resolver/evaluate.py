"""Strict offline evaluation for typed resolver plans."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from nl2sparql.linking.entity import (
    EntityAlternative,
    EntityCorpus,
    EntityLinkerError,
    EntityMatch,
    GitProvenance,
)
from nl2sparql.linking.resolver.contracts import (
    ClassResolverError,
    ResolutionPlan,
    ResolvedEntity,
)

_CASE_KEYS = frozenset({"id", "question", "matches", "expected", "expected_status"})
_MATCH_KEYS = frozenset(
    {
        "span",
        "span_offset",
        "target_id",
        "target_kind",
        "owner",
        "addresses",
        "categories",
        "concept_classes",
        "stage",
        "confidence",
        "alternatives",
        "target_sha256",
    }
)
_ALTERNATIVE_KEYS = frozenset({"target_id", "target_kind", "confidence"})
_EXPECTED_KEYS = frozenset(
    {"span_offset", "target_id", "resolution_kind", "direction", "coverage_status"}
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ResolverEvaluationError(ClassResolverError):
    """Raised when resolver evidence, metrics, or provenance is invalid."""


class _DuplicateJsonKey(ValueError):
    pass


def _required_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 10_000
        or _CONTROL_RE.search(value)
    ):
        raise ResolverEvaluationError(f"{label} must be non-empty and control-free")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ResolverEvaluationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _offset(value: object, label: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
        or value[0] < 0
        or value[1] <= value[0]
    ):
        raise ResolverEvaluationError(f"{label} must be a valid two-integer offset")
    return value[0], value[1]


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ResolverEvaluationError(f"{label} must be an array of strings")
    return tuple(value)


def _identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True)
class ResolverExpected:
    """Reviewed expected resolution for one supplied entity match."""

    span_offset: tuple[int, int]
    target_id: str
    resolution_kind: str
    direction: str
    coverage_status: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.span_offset, tuple)
            or len(self.span_offset) != 2
            or any(not isinstance(item, int) or isinstance(item, bool) for item in self.span_offset)
            or self.span_offset[0] < 0
            or self.span_offset[1] <= self.span_offset[0]
        ):
            raise ResolverEvaluationError("expected span_offset is invalid")
        _required_text(self.target_id, "expected target ID")
        if self.resolution_kind not in {"instance", "concept", "unresolved"}:
            raise ResolverEvaluationError("expected resolution kind is invalid")
        if self.direction not in {"from", "to", "token", "unspecified"}:
            raise ResolverEvaluationError("expected direction is invalid")
        if self.coverage_status not in {"supported", "coverage_gap", "unresolved"}:
            raise ResolverEvaluationError("expected coverage status is invalid")


@dataclass(frozen=True)
class ResolverGroundTruthCase:
    """One reviewed question with fixed T4.2 evidence and resolver labels."""

    id: str
    question: str
    matches: tuple[EntityMatch, ...]
    expected: tuple[ResolverExpected, ...]
    expected_status: str

    def __post_init__(self) -> None:
        _required_text(self.id, "case ID")
        _required_text(self.question, "case question")
        if not isinstance(self.matches, tuple) or not self.matches:
            raise ResolverEvaluationError("case matches must be a non-empty tuple")
        if any(not isinstance(value, EntityMatch) for value in self.matches):
            raise ResolverEvaluationError("case matches contain an invalid value")
        if not isinstance(self.expected, tuple) or len(self.expected) != len(self.matches):
            raise ResolverEvaluationError("case expected rows must align with matches")
        if any(not isinstance(value, ResolverExpected) for value in self.expected):
            raise ResolverEvaluationError("case expected rows contain an invalid value")
        match_offsets = tuple(value.span_offset for value in self.matches)
        expected_offsets = tuple(value.span_offset for value in self.expected)
        if match_offsets != expected_offsets:
            raise ResolverEvaluationError("case expected offsets must align with matches")
        if self.expected_status not in {"resolved", "partial", "unresolved"}:
            raise ResolverEvaluationError("expected plan status is invalid")


@dataclass(frozen=True)
class ResolverGroundTruth:
    """Exactly 50 reviewed cases bound to accepted JSONL and dictionary bytes."""

    cases: tuple[ResolverGroundTruthCase, ...]
    ground_truth_sha256: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.cases, tuple)
            or len(self.cases) != 50
            or any(not isinstance(value, ResolverGroundTruthCase) for value in self.cases)
        ):
            raise ResolverEvaluationError("resolver dataset must contain exactly 50 cases")
        for label, value in (
            ("ground-truth hash", self.ground_truth_sha256),
            ("entities hash", self.entities_sha256),
            ("aliases hash", self.aliases_sha256),
            ("concepts hash", self.concepts_sha256),
        ):
            _digest(value, label)


@dataclass(frozen=True)
class ResolverEvaluationReport:
    """Question-free aggregate resolver metrics and provenance."""

    case_count: int
    entity_count: int
    resolution_kind_accuracy: float
    direction_accuracy: float
    fully_resolved_plan_accuracy: float
    coverage_gap_count: int
    ready: bool
    catalog_sha256: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str
    ground_truth_sha256: str
    git_sha: str
    git_worktree_dirty: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.case_count, int)
            or isinstance(self.case_count, bool)
            or self.case_count <= 0
            or not isinstance(self.entity_count, int)
            or isinstance(self.entity_count, bool)
            or self.entity_count <= 0
            or not isinstance(self.coverage_gap_count, int)
            or isinstance(self.coverage_gap_count, bool)
            or self.coverage_gap_count < 0
        ):
            raise ResolverEvaluationError("report counts are invalid")
        for label, value in (
            ("resolution-kind accuracy", self.resolution_kind_accuracy),
            ("direction accuracy", self.direction_accuracy),
            ("fully resolved plan accuracy", self.fully_resolved_plan_accuracy),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ResolverEvaluationError(f"{label} must be finite in [0, 1]")
        expected_ready = self.case_count == 50 and self.fully_resolved_plan_accuracy >= 0.90
        if not isinstance(self.ready, bool) or self.ready != expected_ready:
            raise ResolverEvaluationError("ready must equal the 50-case 0.90 plan-accuracy gate")
        for label, value in (
            ("catalog hash", self.catalog_sha256),
            ("entities hash", self.entities_sha256),
            ("aliases hash", self.aliases_sha256),
            ("concepts hash", self.concepts_sha256),
            ("ground-truth hash", self.ground_truth_sha256),
        ):
            _digest(value, label)
        try:
            GitProvenance(self.git_sha, self.git_worktree_dirty)
        except EntityLinkerError as exc:
            raise ResolverEvaluationError(f"invalid git provenance: {exc}") from exc


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _parse_match(raw: object, question: str, corpus: EntityCorpus, line: int) -> EntityMatch:
    if not isinstance(raw, Mapping) or set(raw) != _MATCH_KEYS:
        raise ResolverEvaluationError(f"ground truth line {line}: match keys are invalid")
    raw_alternatives = raw["alternatives"]
    if not isinstance(raw_alternatives, list):
        raise ResolverEvaluationError(f"ground truth line {line}: alternatives must be an array")
    alternatives: list[EntityAlternative] = []
    for value in raw_alternatives:
        if not isinstance(value, Mapping) or set(value) != _ALTERNATIVE_KEYS:
            raise ResolverEvaluationError(f"ground truth line {line}: alternative keys are invalid")
        try:
            alternatives.append(
                EntityAlternative(
                    target_id=value["target_id"],
                    target_kind=value["target_kind"],
                    confidence=value["confidence"],
                )
            )
        except (EntityLinkerError, TypeError, ValueError) as exc:
            raise ResolverEvaluationError(
                f"ground truth line {line}: invalid alternative: {exc}"
            ) from exc
    try:
        match = EntityMatch(
            span=raw["span"],
            span_offset=_offset(raw["span_offset"], f"ground truth line {line}: span_offset"),
            target_id=raw["target_id"],
            target_kind=raw["target_kind"],
            owner=raw["owner"],
            addresses=_string_tuple(raw["addresses"], f"ground truth line {line}: addresses"),
            categories=_string_tuple(raw["categories"], f"ground truth line {line}: categories"),
            concept_classes=_string_tuple(
                raw["concept_classes"], f"ground truth line {line}: concept classes"
            ),
            stage=raw["stage"],
            confidence=raw["confidence"],
            alternatives=tuple(alternatives),
            target_sha256=raw["target_sha256"],
        )
    except (EntityLinkerError, TypeError, ValueError) as exc:
        raise ResolverEvaluationError(f"ground truth line {line}: invalid match: {exc}") from exc
    start, end = match.span_offset
    if end > len(question) or question[start:end] != match.span:
        raise ResolverEvaluationError(
            f"ground truth line {line}: match must equal the original question slice"
        )
    if match.target_kind == "address":
        expected = hashlib.sha256(match.target_id.encode()).hexdigest()
        if match.target_sha256 != expected:
            raise ResolverEvaluationError(
                f"ground truth line {line}: raw address fingerprint is invalid"
            )
    else:
        target = corpus.targets_by_id.get(match.target_id)
        if target is None or target.document_sha256 != match.target_sha256:
            raise ResolverEvaluationError(f"ground truth line {line}: target is unknown or stale")
    return match


def _parse_expected(raw: object, line: int) -> ResolverExpected:
    if not isinstance(raw, Mapping) or set(raw) != _EXPECTED_KEYS:
        raise ResolverEvaluationError(f"ground truth line {line}: expected keys are invalid")
    try:
        return ResolverExpected(
            span_offset=_offset(
                raw["span_offset"], f"ground truth line {line}: expected span_offset"
            ),
            target_id=raw["target_id"],
            resolution_kind=raw["resolution_kind"],
            direction=raw["direction"],
            coverage_status=raw["coverage_status"],
        )
    except (ResolverEvaluationError, TypeError, ValueError) as exc:
        raise ResolverEvaluationError(f"ground truth line {line}: {exc}") from exc


def load_resolver_ground_truth(path: Path, corpus: EntityCorpus) -> ResolverGroundTruth:
    """Load exactly 50 independently reviewed resolver cases from JSONL."""
    if not isinstance(corpus, EntityCorpus):
        raise ResolverEvaluationError("entity corpus is invalid")
    try:
        snapshot = path.read_bytes()
        lines = snapshot.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ResolverEvaluationError(f"unable to read resolver ground truth: {exc}") from exc
    cases: list[ResolverGroundTruthCase] = []
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line, object_pairs_hook=_json_object)
        except _DuplicateJsonKey as exc:
            raise ResolverEvaluationError(
                f"ground truth line {line_number}: duplicate JSON key {exc.args[0]!r}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ResolverEvaluationError(
                f"ground truth line {line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(raw, Mapping) or set(raw) != _CASE_KEYS:
            raise ResolverEvaluationError(f"ground truth line {line_number}: case keys are invalid")
        case_id = _required_text(raw["id"], f"ground truth line {line_number}: ID")
        question = _required_text(raw["question"], f"ground truth line {line_number}: question")
        identity = _identity(question)
        if case_id in seen_ids:
            raise ResolverEvaluationError(
                f"ground truth line {line_number}: duplicate ID {case_id!r}"
            )
        if identity in seen_questions:
            raise ResolverEvaluationError(
                f"ground truth line {line_number}: duplicate question {question!r}"
            )
        if not isinstance(raw["matches"], list) or not raw["matches"]:
            raise ResolverEvaluationError(
                f"ground truth line {line_number}: matches must be a non-empty array"
            )
        if not isinstance(raw["expected"], list) or not raw["expected"]:
            raise ResolverEvaluationError(
                f"ground truth line {line_number}: expected must be a non-empty array"
            )
        matches = tuple(
            _parse_match(value, question, corpus, line_number) for value in raw["matches"]
        )
        expected = tuple(_parse_expected(value, line_number) for value in raw["expected"])
        try:
            case = ResolverGroundTruthCase(
                case_id, question, matches, expected, raw["expected_status"]
            )
        except (ResolverEvaluationError, TypeError, ValueError) as exc:
            raise ResolverEvaluationError(f"ground truth line {line_number}: {exc}") from exc
        seen_ids.add(case_id)
        seen_questions.add(identity)
        cases.append(case)
    if len(cases) != 50:
        line_number = min(len(cases), 50) + 1
        raise ResolverEvaluationError(
            f"ground truth line {line_number}: expected exactly 50 rows, found {len(cases)}"
        )
    return ResolverGroundTruth(
        cases=tuple(cases),
        ground_truth_sha256=hashlib.sha256(snapshot).hexdigest(),
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
    )


def _plan_from(resolver: object, case: ResolverGroundTruthCase) -> ResolutionPlan:
    method = getattr(resolver, "resolve", None)
    if not callable(method):
        raise ResolverEvaluationError("resolver must provide resolve")
    try:
        plan = method(case.question, case.matches)
    except Exception as exc:
        if isinstance(exc, ResolverEvaluationError):
            raise
        raise ResolverEvaluationError(f"resolver failed: {exc}") from exc
    if not isinstance(plan, ResolutionPlan):
        raise ResolverEvaluationError("resolver must return a ResolutionPlan")
    if plan.question_sha256 != hashlib.sha256(case.question.encode()).hexdigest():
        raise ResolverEvaluationError("resolver returned the wrong question fingerprint")
    return plan


def _exact_entity(predicted: ResolvedEntity, expected: ResolverExpected) -> bool:
    return (
        predicted.span_offset == expected.span_offset
        and predicted.target_id == expected.target_id
        and predicted.resolution_kind == expected.resolution_kind
        and predicted.direction == expected.direction
        and predicted.coverage_status == expected.coverage_status
    )


def evaluate_resolver(
    resolver: object,
    dataset: ResolverGroundTruth,
    git_provenance: GitProvenance | None,
) -> ResolverEvaluationReport:
    """Evaluate one resolver over a strict 50-case offline artifact."""
    if not isinstance(dataset, ResolverGroundTruth):
        raise ResolverEvaluationError("dataset must be a ResolverGroundTruth")
    if not isinstance(git_provenance, GitProvenance):
        raise ResolverEvaluationError("explicit git provenance is required")

    entity_count = 0
    kind_hits = 0
    direction_hits = 0
    exact_plan_hits = 0
    coverage_gaps = 0
    catalog_sha256: str | None = None
    for case in dataset.cases:
        plan = _plan_from(resolver, case)
        for label, actual, expected_hash in (
            ("entities", plan.entities_sha256, dataset.entities_sha256),
            ("aliases", plan.aliases_sha256, dataset.aliases_sha256),
            ("concepts", plan.concepts_sha256, dataset.concepts_sha256),
        ):
            if actual != expected_hash:
                raise ResolverEvaluationError(f"resolver {label} provenance does not match dataset")
        if catalog_sha256 is None:
            catalog_sha256 = plan.catalog_sha256
        elif plan.catalog_sha256 != catalog_sha256:
            raise ResolverEvaluationError("resolver catalog provenance changed during evaluation")

        predictions = {value.span_offset: value for value in plan.entities}
        exact_entities = len(predictions) == len(case.expected)
        for expected in case.expected:
            entity_count += 1
            predicted = predictions.get(expected.span_offset)
            if predicted is None:
                exact_entities = False
                continue
            kind_hits += predicted.resolution_kind == expected.resolution_kind
            direction_hits += predicted.direction == expected.direction
            coverage_gaps += predicted.coverage_status == "coverage_gap"
            exact_entities = exact_entities and _exact_entity(predicted, expected)
        exact_plan_hits += plan.status == case.expected_status and exact_entities

    if entity_count <= 0 or catalog_sha256 is None:
        raise ResolverEvaluationError("dataset must contain expected resolver entities")
    plan_accuracy = exact_plan_hits / len(dataset.cases)
    return ResolverEvaluationReport(
        case_count=len(dataset.cases),
        entity_count=entity_count,
        resolution_kind_accuracy=kind_hits / entity_count,
        direction_accuracy=direction_hits / entity_count,
        fully_resolved_plan_accuracy=plan_accuracy,
        coverage_gap_count=coverage_gaps,
        ready=plan_accuracy >= 0.90,
        catalog_sha256=catalog_sha256,
        entities_sha256=dataset.entities_sha256,
        aliases_sha256=dataset.aliases_sha256,
        concepts_sha256=dataset.concepts_sha256,
        ground_truth_sha256=dataset.ground_truth_sha256,
        git_sha=git_provenance.git_sha,
        git_worktree_dirty=git_provenance.worktree_dirty,
    )
