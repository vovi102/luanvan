"""Strict offline evidence evaluation for the entity-linker cascade."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from nl2sparql.linking.entity.contracts import EntityCorpus, EntityLinkerError, EntityMatch

_GROUND_TRUTH_KEYS = frozenset({"id", "question", "mentions"})
_MENTION_KEYS = frozenset({"span", "span_offset", "target_id"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class EntityEvaluationError(EntityLinkerError):
    """Raised when entity evidence, metrics, or provenance is invalid."""


@dataclass(frozen=True)
class GroundTruthMention:
    """One reviewed original-text mention bound to a stable corpus target ID."""

    span: str
    span_offset: tuple[int, int]
    target_id: str


@dataclass(frozen=True)
class GroundTruthCase:
    """One independently reviewed question and its entity mentions."""

    id: str
    question: str
    mentions: tuple[GroundTruthMention, ...]


@dataclass(frozen=True)
class EntityEvaluationReport:
    """Aggregate, question-free evidence metrics and reproducibility identities."""

    case_count: int
    named_entity_count: int
    named_entity_top1_accuracy: float
    mention_precision: float
    mention_recall: float
    mention_f1: float
    stage_counts: dict[str, int]
    warm_latency_p50_ms: float
    warm_latency_p95_ms: float
    ready: bool
    model_id: str
    model_sha256: str
    corpus_sha256: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str
    index_sha256: str
    ground_truth_sha256: str
    git_sha: str


def _required_text(value: object, label: str, line_number: int | None = None) -> str:
    prefix = f"ground truth line {line_number}: " if line_number is not None else ""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 10_000
        or _CONTROL_RE.search(value)
    ):
        raise EntityEvaluationError(f"{prefix}{label} must be non-empty, bounded, and control-free")
    return value


def _identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EntityEvaluationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _git_sha(value: object) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise EntityEvaluationError("git SHA must be a full lowercase 40-character SHA")
    return value


def _parse_mention(
    raw: object,
    *,
    question: str,
    corpus: EntityCorpus,
    line_number: int,
) -> GroundTruthMention:
    if not isinstance(raw, Mapping) or set(raw) != _MENTION_KEYS:
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention must contain exact keys "
            "span, span_offset, target_id"
        )
    span = _required_text(raw["span"], "mention span", line_number)
    target_id = _required_text(raw["target_id"], "mention target_id", line_number)
    raw_offset = raw["span_offset"]
    if (
        not isinstance(raw_offset, list)
        or len(raw_offset) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in raw_offset)
    ):
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention span_offset must be two integers"
        )
    start, end = raw_offset
    if start < 0 or end <= start or end > len(question):
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention span_offset is not a valid half-open slice"
        )
    if question[start:end] != span:
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention span must equal the original question slice"
        )
    if target_id not in corpus.targets_by_id:
        raise EntityEvaluationError(
            f"ground truth line {line_number}: mention has unknown target {target_id!r}"
        )
    return GroundTruthMention(span, (start, end), target_id)


def _validate_case(case: object, corpus: EntityCorpus) -> GroundTruthCase:
    if not isinstance(case, GroundTruthCase):
        raise EntityEvaluationError("cases must contain GroundTruthCase values")
    case_id = _required_text(case.id, "case ID")
    question = _required_text(case.question, "question")
    if not isinstance(case.mentions, tuple) or not case.mentions:
        raise EntityEvaluationError("case mentions must be a non-empty tuple")
    mentions: list[GroundTruthMention] = []
    for mention in case.mentions:
        if not isinstance(mention, GroundTruthMention):
            raise EntityEvaluationError("case mentions must contain GroundTruthMention values")
        start, end = mention.span_offset
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > len(question)
            or question[start:end] != mention.span
        ):
            raise EntityEvaluationError("case mention must equal a valid original half-open slice")
        _required_text(mention.span, "case mention span")
        _required_text(mention.target_id, "case mention target ID")
        if mention.target_id not in corpus.targets_by_id:
            raise EntityEvaluationError(f"case mention has unknown target {mention.target_id!r}")
        mentions.append(mention)
    _validate_mentions(mentions, corpus, None)
    return GroundTruthCase(case_id, question, tuple(mentions))


def _validate_mentions(
    mentions: Sequence[GroundTruthMention], corpus: EntityCorpus, line_number: int | None
) -> None:
    prefix = f"ground truth line {line_number}: " if line_number is not None else ""
    seen: set[tuple[int, int, str]] = set()
    ordered = sorted(mentions, key=lambda mention: (*mention.span_offset, mention.target_id))
    for mention in ordered:
        key = (*mention.span_offset, mention.target_id)
        if key in seen:
            raise EntityEvaluationError(f"{prefix}duplicate mention")
        seen.add(key)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.span_offset[0] < previous.span_offset[1]:
            raise EntityEvaluationError(f"{prefix}mentions must not overlap")
    has_owner_mention = any(
        corpus.targets_by_id[mention.target_id].target_kind == "owner" for mention in mentions
    )
    if not has_owner_mention:
        raise EntityEvaluationError(f"{prefix}case must include at least one named-entity mention")


def load_ground_truth(path: Path, corpus: EntityCorpus) -> tuple[GroundTruthCase, ...]:
    """Strictly load the independently reviewed 100-row entity JSONL artifact."""
    if not isinstance(corpus, EntityCorpus):
        raise EntityEvaluationError("entity corpus is invalid")
    try:
        lines = path.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise EntityEvaluationError("ground truth line 1: invalid UTF-8") from exc
    cases: list[GroundTruthCase] = []
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        try:
            raw = json.loads(raw_line)
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
        case_id = _required_text(raw["id"], "id", line_number)
        question = _required_text(raw["question"], "question", line_number)
        question_identity = _identity(question)
        if case_id in seen_ids:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: duplicate ID {case_id!r}"
            )
        if question_identity in seen_questions:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: duplicate question {question!r}"
            )
        if not isinstance(raw["mentions"], list) or not raw["mentions"]:
            raise EntityEvaluationError(
                f"ground truth line {line_number}: mentions must be a non-empty array"
            )
        mentions = tuple(
            _parse_mention(
                mention, question=question, corpus=corpus, line_number=line_number
            )
            for mention in raw["mentions"]
        )
        _validate_mentions(mentions, corpus, line_number)
        seen_ids.add(case_id)
        seen_questions.add(question_identity)
        cases.append(GroundTruthCase(case_id, question, mentions))
    if len(cases) != 100:
        line_number = min(len(cases), 100) + 1
        raise EntityEvaluationError(
            f"ground truth line {line_number}: expected exactly 100 rows, found {len(cases)}"
        )
    return tuple(cases)


def _percentile(values: Sequence[float], percentile: float) -> float:
    valid_values = values and all(
        isinstance(value, (int, float)) and math.isfinite(value) for value in values
    )
    if not valid_values:
        raise EntityEvaluationError("percentile values must be non-empty finite numbers")
    if not isinstance(percentile, (int, float)) or not 0.0 <= percentile <= 1.0:
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


def _index_sha256_from(linker: object) -> str:
    digest = getattr(linker, "index_sha256", None)
    if digest is None:
        index = getattr(linker, "_index", None)
        digest = getattr(getattr(index, "metadata", None), "manifest_sha256", None)
    return _digest(digest, "index hash")


def _validate_index_provenance(linker: object, corpus: EntityCorpus, model_id: str) -> None:
    """Reject a linker whose attached index identity differs from the report inputs."""
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
        actual = _digest(getattr(metadata, field_name, None), f"index {field_name}")
        if actual != expected:
            raise EntityEvaluationError(f"index {field_name} does not match the entity corpus")
    target_ids = getattr(metadata, "target_ids", None)
    expected_target_ids = tuple(target.target_id for target in corpus.targets)
    if target_ids is not None and tuple(target_ids) != expected_target_ids:
        raise EntityEvaluationError("index target IDs do not match the entity corpus")


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


def _ground_truth_sha256(cases: Sequence[GroundTruthCase]) -> str:
    payload = [
        {
            "id": case.id,
            "question": case.question,
            "mentions": [
                {
                    "span": mention.span,
                    "span_offset": list(mention.span_offset),
                    "target_id": mention.target_id,
                }
                for mention in case.mentions
            ],
        }
        for case in cases
    ]
    return hashlib.sha256(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()


def _current_git_sha() -> str:
    try:
        output = subprocess.run(
            ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EntityEvaluationError("unable to determine git SHA") from exc
    return _git_sha(output)


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
    for match in linked:
        start, end = match.span_offset
        if end > len(question) or question[start:end] != match.span:
            raise EntityEvaluationError("linker returned an invalid original span")
    return linked


def evaluate_linker(
    linker: object,
    cases: Sequence[GroundTruthCase],
    *,
    model_id: str,
    git_sha: str | None = None,
) -> EntityEvaluationReport:
    """Warm once and compute aggregate entity-linker evidence metrics.

    The report deliberately has no per-question results, so serializing it cannot
    persist the reviewed natural-language questions.
    """
    corpus = _corpus_from(linker)
    model_id = _required_text(model_id, "model ID")
    _validate_index_provenance(linker, corpus, model_id)
    index_sha256 = _index_sha256_from(linker)
    rows = tuple(_validate_case(case, corpus) for case in cases)
    if not rows:
        raise EntityEvaluationError("cases must be non-empty")
    if len({case.id for case in rows}) != len(rows):
        raise EntityEvaluationError("cases must have unique IDs")
    if len({_identity(case.question) for case in rows}) != len(rows):
        raise EntityEvaluationError("cases must have unique questions")

    _link(linker, rows[0].question)
    latencies: list[float] = []
    stage_counts: Counter[str] = Counter()
    total_predictions = 0
    total_gold = 0
    true_positives = 0
    named_total = 0
    named_hits = 0
    for case in rows:
        started = perf_counter()
        predictions = _link(linker, case.question)
        latencies.append((perf_counter() - started) * 1_000.0)
        stage_counts.update(match.stage for match in predictions)
        gold_keys = {
            (mention.span_offset[0], mention.span_offset[1], mention.target_id)
            for mention in case.mentions
        }
        unmatched = set(gold_keys)
        for match in predictions:
            key = (*match.span_offset, match.target_id)
            if key in unmatched:
                true_positives += 1
                unmatched.remove(key)
        total_predictions += len(predictions)
        total_gold += len(gold_keys)
        for mention in case.mentions:
            if corpus.targets_by_id[mention.target_id].target_kind == "owner":
                named_total += 1
                if (mention.span_offset[0], mention.span_offset[1], mention.target_id) in {
                    (*match.span_offset, match.target_id) for match in predictions
                }:
                    named_hits += 1
    precision = true_positives / total_predictions if total_predictions else 0.0
    recall = true_positives / total_gold if total_gold else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    named_accuracy = named_hits / named_total if named_total else 0.0
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    resolved_git_sha = _current_git_sha() if git_sha is None else _git_sha(git_sha)
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
        ready=(len(rows) == 100 and named_accuracy >= 0.85 and p95 < 200.0),
        model_id=model_id,
        model_sha256=hashlib.sha256(model_id.encode("utf-8")).hexdigest(),
        corpus_sha256=_corpus_sha256(corpus),
        entities_sha256=_digest(corpus.entities_sha256, "entities hash"),
        aliases_sha256=_digest(corpus.aliases_sha256, "aliases hash"),
        concepts_sha256=_digest(corpus.concepts_sha256, "concepts hash"),
        index_sha256=index_sha256,
        ground_truth_sha256=_ground_truth_sha256(rows),
        git_sha=resolved_git_sha,
    )
