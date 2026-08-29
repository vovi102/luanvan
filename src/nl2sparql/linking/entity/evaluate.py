"""Strict offline evidence evaluation for the entity-linker cascade."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import MappingProxyType

from nl2sparql.linking.entity.contracts import EntityCorpus, EntityLinkerError, EntityMatch

_GROUND_TRUTH_KEYS = frozenset({"id", "question", "mentions"})
_MENTION_KEYS = frozenset({"span", "span_offset", "target_id"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class EntityEvaluationError(EntityLinkerError):
    """Raised when entity evidence, metrics, or provenance is invalid."""


class _DuplicateJsonKey(ValueError):
    """Internal signal from JSON object parsing."""


def _required_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 10_000
        or _CONTROL_RE.search(value)
    ):
        raise EntityEvaluationError(f"{label} must be non-empty, bounded, and control-free")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EntityEvaluationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _offset(value: object, label: str) -> tuple[int, int]:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
    ):
        raise EntityEvaluationError(f"{label} must be a two-integer tuple")
    start, end = value
    if start < 0 or end <= start:
        raise EntityEvaluationError(f"{label} must be a valid half-open interval")
    return value


def _identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True)
class GroundTruthMention:
    """One reviewed original-text mention bound to a stable corpus target ID."""

    span: str
    span_offset: tuple[int, int]
    target_id: str

    def __post_init__(self) -> None:
        _required_text(self.span, "mention span")
        _offset(self.span_offset, "mention span_offset")
        _required_text(self.target_id, "mention target ID")


def _validate_mentions(mentions: tuple[GroundTruthMention, ...]) -> None:
    if not mentions or any(not isinstance(mention, GroundTruthMention) for mention in mentions):
        raise EntityEvaluationError(
            "mentions must be a non-empty tuple of GroundTruthMention values"
        )
    ordered = sorted(mentions, key=lambda mention: (*mention.span_offset, mention.target_id))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.span_offset == previous.span_offset:
            raise EntityEvaluationError("mentions must not contain duplicate mention spans")
        if current.span_offset[0] < previous.span_offset[1]:
            raise EntityEvaluationError("mentions must not overlap")


@dataclass(frozen=True)
class GroundTruthCase:
    """One independently reviewed question and its entity mentions."""

    id: str
    question: str
    mentions: tuple[GroundTruthMention, ...]

    def __post_init__(self) -> None:
        _required_text(self.id, "case ID")
        _required_text(self.question, "question")
        if not isinstance(self.mentions, tuple):
            raise EntityEvaluationError("mentions must be a tuple")
        _validate_mentions(self.mentions)
        for mention in self.mentions:
            start, end = mention.span_offset
            if end > len(self.question) or self.question[start:end] != mention.span:
                raise EntityEvaluationError("mention must equal an original question slice")


@dataclass(frozen=True)
class GroundTruthDataset:
    """Validated cases bound to the exact JSONL bytes accepted by the loader."""

    cases: tuple[GroundTruthCase, ...]
    ground_truth_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.cases, tuple) or any(
            not isinstance(case, GroundTruthCase) for case in self.cases
        ):
            raise EntityEvaluationError("dataset cases must be a tuple of GroundTruthCase values")
        _digest(self.ground_truth_sha256, "ground-truth hash")


@dataclass(frozen=True)
class GitProvenance:
    """Explicit repository state supplied by the workflow at evaluation time."""

    git_sha: str
    worktree_dirty: bool

    def __post_init__(self) -> None:
        if not isinstance(self.git_sha, str) or not _GIT_SHA_RE.fullmatch(self.git_sha):
            raise EntityEvaluationError("git SHA must be a full lowercase 40-character SHA")
        if not isinstance(self.worktree_dirty, bool):
            raise EntityEvaluationError("git worktree dirty flag must be boolean")


@dataclass(frozen=True)
class StageCount:
    """One JSON-serializable immutable count of predictions from a linker stage."""

    stage: str
    count: int

    def __post_init__(self) -> None:
        _required_text(self.stage, "stage count key")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count <= 0:
            raise EntityEvaluationError("stage counts must be positive integers")


@dataclass(frozen=True)
class EntityEvaluationReport:
    """Aggregate, question-free evidence metrics and reproducibility identities."""

    case_count: int
    named_entity_count: int
    named_entity_top1_accuracy: float
    mention_precision: float
    mention_recall: float
    mention_f1: float
    stage_counts: tuple[StageCount, ...] | Mapping[str, int]
    warm_latency_p50_ms: float
    warm_latency_p95_ms: float
    ready: bool
    model_id: str
    model_id_sha256: str
    corpus_sha256: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str
    index_manifest_sha256: str
    index_matrices_sha256: str
    ground_truth_sha256: str
    git_sha: str
    git_worktree_dirty: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.case_count, int)
            or isinstance(self.case_count, bool)
            or self.case_count <= 0
            or not isinstance(self.named_entity_count, int)
            or isinstance(self.named_entity_count, bool)
            or self.named_entity_count <= 0
        ):
            raise EntityEvaluationError("report counts must be positive integers")
        for value, label in (
            (self.named_entity_top1_accuracy, "named-entity Top-1 accuracy"),
            (self.mention_precision, "mention precision"),
            (self.mention_recall, "mention recall"),
            (self.mention_f1, "mention F1"),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise EntityEvaluationError(f"{label} must be finite in [0, 1]")
        for value, label in (
            (self.warm_latency_p50_ms, "warm p50 latency"),
            (self.warm_latency_p95_ms, "warm p95 latency"),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise EntityEvaluationError(f"{label} must be a finite non-negative number")
        if isinstance(self.stage_counts, Mapping):
            stage_counts = tuple(
                StageCount(stage, count) for stage, count in sorted(self.stage_counts.items())
            )
        elif isinstance(self.stage_counts, tuple) and all(
            isinstance(entry, StageCount) for entry in self.stage_counts
        ):
            stage_counts = self.stage_counts
        else:
            raise EntityEvaluationError(
                "stage counts must be a mapping or tuple of StageCount values"
            )
        if tuple(sorted(stage_counts, key=lambda entry: entry.stage)) != stage_counts:
            raise EntityEvaluationError("stage counts must be sorted by stage")
        if len({entry.stage for entry in stage_counts}) != len(stage_counts):
            raise EntityEvaluationError("stage counts must not contain duplicate stages")
        if not isinstance(self.ready, bool):
            raise EntityEvaluationError("ready must be boolean")
        expected_ready = (
            self.case_count == 100
            and self.named_entity_top1_accuracy >= 0.85
            and self.warm_latency_p95_ms < 200.0
        )
        if self.ready != expected_ready:
            raise EntityEvaluationError("ready must equal the 100-case Top-1 and p95 gate")
        _required_text(self.model_id, "model ID")
        for value, label in (
            (self.model_id_sha256, "model ID hash"),
            (self.corpus_sha256, "corpus hash"),
            (self.entities_sha256, "entities hash"),
            (self.aliases_sha256, "aliases hash"),
            (self.concepts_sha256, "concepts hash"),
            (self.index_manifest_sha256, "index manifest hash"),
            (self.index_matrices_sha256, "index matrices hash"),
            (self.ground_truth_sha256, "ground-truth hash"),
        ):
            _digest(value, label)
        GitProvenance(self.git_sha, self.git_worktree_dirty)
        object.__setattr__(self, "stage_counts", stage_counts)

    @property
    def stage_count_map(self) -> Mapping[str, int]:
        """Return a newly derived read-only mapping for convenient stage lookup."""
        return MappingProxyType({entry.stage: entry.count for entry in self.stage_counts})


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _parse_mention(
    raw: object, *, question: str, corpus: EntityCorpus, line_number: int
) -> GroundTruthMention:
    if not isinstance(raw, Mapping) or set(raw) != _MENTION_KEYS:
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention must contain exact keys "
            "span, span_offset, target_id"
        )
    span = _required_text(raw["span"], f"ground truth line {line_number}: mention span")
    target_id = _required_text(
        raw["target_id"], f"ground truth line {line_number}: mention target ID"
    )
    raw_offset = raw["span_offset"]
    if (
        not isinstance(raw_offset, list)
        or len(raw_offset) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in raw_offset)
    ):
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention span_offset must be two integers"
        )
    offset = (raw_offset[0], raw_offset[1])
    try:
        mention = GroundTruthMention(span, offset, target_id)
    except EntityEvaluationError as exc:
        raise EntityEvaluationError(f"ground truth line {line_number}: {exc}") from exc
    start, end = mention.span_offset
    if end > len(question) or question[start:end] != mention.span:
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention must equal the original question slice"
        )
    if target_id not in corpus.targets_by_id:
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention has unknown target {target_id!r}"
        )
    return mention


def load_ground_truth(path: Path, corpus: EntityCorpus) -> GroundTruthDataset:
    """Strictly load the independently reviewed 100-row entity JSONL artifact."""
    if not isinstance(corpus, EntityCorpus):
        raise EntityEvaluationError("entity corpus is invalid")
    snapshot = path.read_bytes()
    try:
        lines = snapshot.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise EntityEvaluationError("ground truth line 1: invalid UTF-8") from exc
    cases: list[GroundTruthCase] = []
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        try:
            raw = json.loads(raw_line, object_pairs_hook=_json_object)
        except _DuplicateJsonKey as exc:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: duplicate JSON key {exc.args[0]!r}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(raw, Mapping):
            raise EntityEvaluationError(
                f"ground truth line {line_number}: record must be an object"
            )
        if set(raw) != _GROUND_TRUTH_KEYS:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: record must contain exact keys "
                "id, question, mentions"
            )
        case_id = _required_text(raw["id"], f"ground truth line {line_number}: ID")
        question = _required_text(raw["question"], f"ground truth line {line_number}: question")
        identity = _identity(question)
        if case_id in seen_ids:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: duplicate ID {case_id!r}"
            )
        if identity in seen_questions:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: duplicate question {question!r}"
            )
        if not isinstance(raw["mentions"], list) or not raw["mentions"]:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: mentions must be a non-empty array"
            )
        mentions = tuple(
            _parse_mention(mention, question=question, corpus=corpus, line_number=line_number)
            for mention in raw["mentions"]
        )
        try:
            case = GroundTruthCase(case_id, question, mentions)
        except EntityEvaluationError as exc:
            raise EntityEvaluationError(f"ground truth line {line_number}: {exc}") from exc
        has_owner_mention = any(
            corpus.targets_by_id[mention.target_id].target_kind == "owner"
            for mention in mentions
        )
        if not has_owner_mention:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: case must include a named-entity mention"
            )
        seen_ids.add(case_id)
        seen_questions.add(identity)
        cases.append(case)
    if len(cases) != 100:
        line_number = min(len(cases), 100) + 1
        raise EntityEvaluationError(
            f"ground truth line {line_number}: expected exactly 100 rows, found {len(cases)}"
        )
    return GroundTruthDataset(tuple(cases), hashlib.sha256(snapshot).hexdigest())


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values or any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for value in values
    ):
        raise EntityEvaluationError("percentile values must be non-empty finite numbers")
    if (
        not isinstance(percentile, (int, float))
        or isinstance(percentile, bool)
        or not 0.0 <= percentile <= 1.0
    ):
        raise EntityEvaluationError("percentile must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * float(percentile)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _corpus_from(linker: object) -> EntityCorpus:
    corpus = getattr(linker, "corpus", getattr(linker, "_corpus", None))
    if not isinstance(corpus, EntityCorpus):
        raise EntityEvaluationError("linker must expose a valid entity corpus")
    return corpus


def _index_hashes(linker: object) -> tuple[str, str]:
    metadata = getattr(getattr(linker, "_index", None), "metadata", None)
    manifest = getattr(linker, "index_manifest_sha256", None)
    matrices = getattr(linker, "index_matrices_sha256", None)
    if metadata is not None:
        manifest = getattr(metadata, "manifest_sha256", manifest)
        matrices = getattr(metadata, "matrices_sha256", matrices)
    return _digest(manifest, "index manifest hash"), _digest(matrices, "index matrices hash")


def _validate_index_provenance(linker: object, corpus: EntityCorpus, model_id: str) -> None:
    metadata = getattr(getattr(linker, "_index", None), "metadata", None)
    if metadata is None:
        return
    if getattr(metadata, "model_id", None) != model_id:
        raise EntityEvaluationError("index model ID does not match the evaluation model ID")
    for field_name, expected in (
        ("entities_sha256", corpus.entities_sha256),
        ("aliases_sha256", corpus.aliases_sha256),
        ("concepts_sha256", corpus.concepts_sha256),
    ):
        if _digest(getattr(metadata, field_name, None), f"index {field_name}") != expected:
            raise EntityEvaluationError(f"index {field_name} does not match the entity corpus")
    expected_target_ids = tuple(target.target_id for target in corpus.targets)
    if getattr(metadata, "target_ids", None) != expected_target_ids:
        raise EntityEvaluationError("index target_ids do not match the entity corpus")
    expected_document_hashes = tuple(target.document_sha256 for target in corpus.targets)
    if getattr(metadata, "target_document_sha256", None) != expected_document_hashes:
        raise EntityEvaluationError(
            "index target_document_sha256 do not match the entity corpus"
        )


def _corpus_sha256(corpus: EntityCorpus) -> str:
    payload = {
        "aliases_sha256": corpus.aliases_sha256,
        "concepts_sha256": corpus.concepts_sha256,
        "entities_sha256": corpus.entities_sha256,
        "target_ids": [target.target_id for target in corpus.targets],
        "target_document_sha256": [target.document_sha256 for target in corpus.targets],
    }
    return hashlib.sha256(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()


def _link(linker: object, question: str) -> tuple[EntityMatch, ...]:
    method = getattr(linker, "link", None)
    if not callable(method):
        raise EntityEvaluationError("linker must provide link(question)")
    try:
        linked = method(question)
    except Exception as exc:
        if isinstance(exc, EntityEvaluationError):
            raise
        raise EntityEvaluationError(f"linker failed: {exc}") from exc
    if not isinstance(linked, tuple) or any(not isinstance(match, EntityMatch) for match in linked):
        raise EntityEvaluationError("linker must return a tuple of EntityMatch values")
    ordered = sorted(linked, key=lambda match: (*match.span_offset, match.target_id))
    for match in ordered:
        start, end = _offset(match.span_offset, "linker prediction span_offset")
        if end > len(question) or question[start:end] != match.span:
            raise EntityEvaluationError("linker returned an invalid original span")
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.span_offset == previous.span_offset:
            raise EntityEvaluationError("linker returned a duplicate prediction span")
        if current.span_offset[0] < previous.span_offset[1]:
            raise EntityEvaluationError("linker returned overlapping prediction spans")
    return linked


def evaluate_linker(
    linker: object,
    dataset: GroundTruthDataset,
    *,
    model_id: str,
    git_provenance: GitProvenance | None = None,
) -> EntityEvaluationReport:
    """Warm once and measure a strict, hash-bound 100-case evaluation dataset."""
    if not isinstance(dataset, GroundTruthDataset):
        raise EntityEvaluationError("dataset must be a GroundTruthDataset")
    if len(dataset.cases) != 100:
        raise EntityEvaluationError("dataset must contain exactly 100 cases")
    if not isinstance(git_provenance, GitProvenance):
        raise EntityEvaluationError("explicit git provenance is required")
    corpus = _corpus_from(linker)
    model_id = _required_text(model_id, "model ID")
    _validate_index_provenance(linker, corpus, model_id)
    manifest_sha256, matrices_sha256 = _index_hashes(linker)
    rows = dataset.cases
    unique_ids = len({case.id for case in rows}) == len(rows)
    unique_questions = len({_identity(case.question) for case in rows}) == len(rows)
    if not unique_ids or not unique_questions:
        raise EntityEvaluationError("dataset cases must have unique IDs and questions")
    for case in rows:
        for mention in case.mentions:
            if mention.target_id not in corpus.targets_by_id:
                raise EntityEvaluationError(
                    f"case mention has unknown target {mention.target_id!r}"
                )
        has_owner_mention = any(
            corpus.targets_by_id[mention.target_id].target_kind == "owner"
            for mention in case.mentions
        )
        if not has_owner_mention:
            raise EntityEvaluationError("each case must include a named-entity mention")

    _link(linker, rows[0].question)
    latencies: list[float] = []
    stage_counts: Counter[str] = Counter()
    total_predictions = 0
    total_gold = 0
    mention_hits = 0
    named_total = 0
    named_hits = 0
    for case in rows:
        started = perf_counter()
        predictions = _link(linker, case.question)
        latencies.append((perf_counter() - started) * 1_000.0)
        stage_counts.update(match.stage for match in predictions)
        prediction_by_span = {match.span_offset: match for match in predictions}
        gold_spans = {mention.span_offset for mention in case.mentions}
        mention_hits += len(gold_spans & set(prediction_by_span))
        total_predictions += len(predictions)
        total_gold += len(gold_spans)
        for mention in case.mentions:
            if corpus.targets_by_id[mention.target_id].target_kind == "owner":
                named_total += 1
                primary = prediction_by_span.get(mention.span_offset)
                if primary is not None and primary.target_id == mention.target_id:
                    named_hits += 1
    precision = mention_hits / total_predictions if total_predictions else 0.0
    recall = mention_hits / total_gold
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    named_accuracy = named_hits / named_total
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    return EntityEvaluationReport(
        case_count=len(rows),
        named_entity_count=named_total,
        named_entity_top1_accuracy=named_accuracy,
        mention_precision=precision,
        mention_recall=recall,
        mention_f1=f1,
        stage_counts=dict(sorted(stage_counts.items())),
        warm_latency_p50_ms=p50,
        warm_latency_p95_ms=p95,
        ready=named_accuracy >= 0.85 and p95 < 200.0,
        model_id=model_id,
        model_id_sha256=hashlib.sha256(model_id.encode("utf-8")).hexdigest(),
        corpus_sha256=_corpus_sha256(corpus),
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
        index_manifest_sha256=manifest_sha256,
        index_matrices_sha256=matrices_sha256,
        ground_truth_sha256=dataset.ground_truth_sha256,
        git_sha=git_provenance.git_sha,
        git_worktree_dirty=git_provenance.worktree_dirty,
    )
