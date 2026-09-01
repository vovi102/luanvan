"""Credential-free evaluation for the deterministic B0 baseline."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlglot import parse_one
from sqlglot.errors import SqlglotError

from nl2sparql.dataset.testset import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.models.b0.contracts import B0Prediction

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DIFFICULTIES = frozenset({"easy", "medium", "hard"})
_FINAL_FIELDS = frozenset(
    {
        "ambiguity_flag",
        "categories",
        "cq_ids",
        "difficulty",
        "evidence_sha256",
        "expected_result_size",
        "id",
        "nl",
        "pool_b_writer",
        "pool_c_reviewers",
        "schema_elements",
        "source",
        "sql",
        "verified_at",
        "verified_executable",
    }
)


class B0EvaluationError(ValueError):
    """Raised when evaluation evidence or metric input is invalid."""


class _DuplicateKey(ValueError):
    pass


class _Baseline(Protocol):
    def predict_detailed(self, question: str) -> B0Prediction | None: ...


@dataclass(frozen=True)
class B0EvaluationCase:
    """Minimal trusted input required for one B0 comparison."""

    case_id: str
    question: str
    gold_sql: str
    difficulty: str

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _CASE_ID_RE.fullmatch(self.case_id):
            raise B0EvaluationError("case ID is invalid")
        if (
            not isinstance(self.question, str)
            or not self.question.strip()
            or _CONTROL_RE.search(self.question)
        ):
            raise B0EvaluationError("case question is invalid")
        if self.difficulty not in _DIFFICULTIES:
            raise B0EvaluationError("case difficulty is invalid")
        try:
            validate_sql_text(self.gold_sql)
        except (TestSetError, TypeError) as exc:
            raise B0EvaluationError(f"gold SQL is invalid: {exc}") from exc


@dataclass(frozen=True)
class B0CaseSet:
    """One fingerprinted collection with explicit synthetic provenance."""

    cases: tuple[B0EvaluationCase, ...]
    input_sha256: str
    synthetic: bool

    def __post_init__(self) -> None:
        if not isinstance(self.cases, tuple) or not self.cases:
            raise B0EvaluationError("evaluation cases must be a non-empty tuple")
        if any(not isinstance(case, B0EvaluationCase) for case in self.cases):
            raise B0EvaluationError("evaluation cases contain an invalid record")
        ids = tuple(case.case_id for case in self.cases)
        if len(ids) != len(set(ids)):
            raise B0EvaluationError("evaluation case IDs must be unique")
        if not isinstance(self.input_sha256, str) or not _DIGEST_RE.fullmatch(self.input_sha256):
            raise B0EvaluationError("evaluation input fingerprint is invalid")
        if not isinstance(self.synthetic, bool):
            raise B0EvaluationError("synthetic marker must be boolean")


@dataclass(frozen=True)
class B0CaseResult:
    """One prediction comparison and latency sample."""

    case_id: str
    predicted_sql: str | None
    template_id: str | None
    match_mode: str | None
    exact_match: bool
    structural_match: bool
    latency_ms: float
    rejection_reason: str | None


@dataclass(frozen=True)
class B0EvaluationReport:
    """Aggregate local evidence without inferred execution accuracy."""

    case_count: int
    matched_count: int
    coverage: float
    exact_match_accuracy: float
    structural_accuracy: float
    latency_p50_ms: float
    latency_p95_ms: float
    execution_accuracy: None
    local_status: str
    scientific_status: str
    input_sha256: str
    synthetic: bool
    match_mode_counts: tuple[tuple[str, int], ...]
    template_counts: tuple[tuple[str, int], ...]
    difficulty_counts: tuple[tuple[str, int], ...]
    rejection_counts: tuple[tuple[str, int], ...]
    template_sha256: str | None
    policy_sha256: str | None
    catalog_sha256: str | None
    entities_sha256: str | None
    aliases_sha256: str | None
    concepts_sha256: str | None


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _string_list(value: object, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise B0EvaluationError(f"{label} must be a string array")
    if nonempty and not value:
        raise B0EvaluationError(f"{label} must not be empty")
    if len(value) != len(set(value)):
        raise B0EvaluationError(f"{label} must be unique")
    return tuple(value)


def _parse_row(raw: object, row_number: int, *, synthetic: bool) -> B0EvaluationCase:
    if not isinstance(raw, Mapping) or set(raw) != _FINAL_FIELDS:
        raise B0EvaluationError(f"row {row_number} must use the finalized T3.5 fields")
    _string_list(raw["categories"], "categories", nonempty=True)
    _string_list(raw["cq_ids"], "CQ IDs", nonempty=True)
    _string_list(raw["schema_elements"], "schema elements", nonempty=True)
    _string_list(raw["pool_c_reviewers"], "Pool C reviewers", nonempty=True)
    for key in ("source", "pool_b_writer"):
        if not isinstance(raw[key], str) or not raw[key]:
            raise B0EvaluationError(f"row {row_number} {key} is invalid")
    if not isinstance(raw["ambiguity_flag"], bool):
        raise B0EvaluationError(f"row {row_number} ambiguity flag is invalid")
    verified = raw["verified_executable"]
    if not isinstance(verified, bool):
        raise B0EvaluationError(f"row {row_number} verified marker is invalid")
    if not synthetic and not verified:
        raise B0EvaluationError(f"row {row_number} must be verified executable")
    sql = raw["sql"]
    if not isinstance(sql, str):
        raise B0EvaluationError(f"row {row_number} SQL is invalid")
    if verified:
        evidence = raw["evidence_sha256"]
        if not isinstance(evidence, str) or evidence != hashlib.sha256(sql.encode()).hexdigest():
            raise B0EvaluationError(f"row {row_number} evidence fingerprint is invalid")
        if not isinstance(raw["verified_at"], str) or not raw["verified_at"].endswith("Z"):
            raise B0EvaluationError(f"row {row_number} verification timestamp is invalid")
        size = raw["expected_result_size"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise B0EvaluationError(f"row {row_number} result size is invalid")
    elif any(
        raw[key] is not None for key in ("evidence_sha256", "verified_at", "expected_result_size")
    ):
        raise B0EvaluationError(f"row {row_number} unverified evidence must be null")
    return B0EvaluationCase(
        case_id=raw["id"],
        question=raw["nl"],
        gold_sql=sql,
        difficulty=raw["difficulty"],
    )


def load_b0_cases(path: Path, *, synthetic: bool = False) -> B0CaseSet:
    """Load finalized T3.5-style JSONL without weakening scientific provenance.

    Args:
        path: Evaluation JSONL snapshot.
        synthetic: Whether the snapshot is explicitly synthetic.

    Returns:
        Validated immutable evaluation cases and input fingerprint.

    Raises:
        B0EvaluationError: If rows or independent review identities are invalid.
    """
    if not isinstance(path, Path):
        raise B0EvaluationError("evaluation path must be a Path")
    if not isinstance(synthetic, bool):
        raise B0EvaluationError("synthetic marker must be boolean")
    try:
        snapshot = path.read_bytes()
        text = snapshot.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise B0EvaluationError(f"unable to read evaluation input: {exc}") from exc
    cases: list[B0EvaluationCase] = []
    author_ids: set[str] = set()
    writer_ids: set[str] = set()
    reviewer_ids: set[str] = set()
    try:
        for row_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                raise B0EvaluationError(f"row {row_number} must not be blank")
            raw = json.loads(line, object_pairs_hook=_json_object)
            cases.append(_parse_row(raw, row_number, synthetic=synthetic))
            author_ids.add(str(raw["source"]))
            writer_ids.add(str(raw["pool_b_writer"]))
            reviewer_ids.update(raw["pool_c_reviewers"])
    except _DuplicateKey as exc:
        raise B0EvaluationError(f"duplicate JSON key {exc.args[0]!r}") from exc
    except json.JSONDecodeError as exc:
        raise B0EvaluationError(f"invalid evaluation JSONL: {exc}") from exc
    ids = tuple(case.case_id for case in cases)
    if len(ids) != len(set(ids)):
        raise B0EvaluationError("evaluation input contains duplicate case IDs")
    if author_ids & writer_ids or author_ids & reviewer_ids or writer_ids & reviewer_ids:
        raise B0EvaluationError("Pool A, Pool B, and Pool C identities must remain independent")
    return B0CaseSet(
        cases=tuple(cases),
        input_sha256=hashlib.sha256(snapshot).hexdigest(),
        synthetic=synthetic,
    )


def _canonical_sql(sql: str) -> str:
    try:
        return parse_one(sql, read="bigquery").sql(dialect="bigquery", pretty=False)
    except (SqlglotError, AttributeError) as exc:
        raise B0EvaluationError(f"unable to canonicalize SQL: {exc}") from exc


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _single_fingerprint(values: Sequence[str | None], label: str) -> str | None:
    present = {value for value in values if value is not None}
    if len(present) > 1:
        raise B0EvaluationError(f"predictions contain inconsistent {label} fingerprints")
    return next(iter(present)) if present else None


def _baseline_fingerprint(baseline: object, name: str) -> str | None:
    direct = getattr(baseline, name, None)
    if isinstance(direct, str):
        return direct
    provenance = getattr(baseline, "linking_provenance", None)
    value = getattr(provenance, name, None)
    return value if isinstance(value, str) else None


def evaluate_b0(
    baseline: _Baseline,
    case_set: B0CaseSet,
    *,
    clock: Callable[[], int] = time.perf_counter_ns,
) -> tuple[tuple[B0CaseResult, ...], B0EvaluationReport]:
    """Measure local B0 text accuracy, structural accuracy, coverage, and latency.

    Args:
        baseline: Predictor under evaluation.
        case_set: Validated B0 cases.
        clock: Monotonic nanosecond clock used for latency measurement.

    Returns:
        Per-case results and the aggregate evaluation report.

    Raises:
        B0EvaluationError: If predictions, fingerprints, or timing evidence are invalid.
    """
    if not isinstance(case_set, B0CaseSet):
        raise B0EvaluationError("case set is invalid")
    results: list[B0CaseResult] = []
    latencies: list[float] = []
    mode_counts: Counter[str] = Counter()
    template_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    difficulty_counts = Counter(case.difficulty for case in case_set.cases)
    observed_predictions: list[B0Prediction] = []
    for case in case_set.cases:
        baseline.predict_detailed(case.question)
        started = clock()
        prediction = baseline.predict_detailed(case.question)
        finished = clock()
        if (
            not isinstance(started, int)
            or isinstance(started, bool)
            or not isinstance(finished, int)
            or isinstance(finished, bool)
            or finished < started
        ):
            raise B0EvaluationError("latency clock must return monotonic integer nanoseconds")
        latency_ms = (finished - started) / 1_000_000.0
        latencies.append(latency_ms)
        if prediction is None:
            rejection_counts["unmatched"] += 1
            results.append(
                B0CaseResult(case.case_id, None, None, None, False, False, latency_ms, "unmatched")
            )
            continue
        if not isinstance(prediction, B0Prediction):
            raise B0EvaluationError("baseline returned an invalid prediction")
        exact = " ".join(prediction.sql.split()) == " ".join(case.gold_sql.split())
        structural = _canonical_sql(prediction.sql) == _canonical_sql(case.gold_sql)
        mode_counts[prediction.match_mode] += 1
        template_counts[prediction.template_id] += 1
        observed_predictions.append(prediction)
        results.append(
            B0CaseResult(
                case.case_id,
                prediction.sql,
                prediction.template_id,
                prediction.match_mode,
                exact,
                structural,
                latency_ms,
                None,
            )
        )
    matched = [result for result in results if result.predicted_sql is not None]
    matched_count = len(matched)
    coverage = matched_count / len(results)
    exact_accuracy = (
        sum(result.exact_match for result in matched) / matched_count if matched else 0.0
    )
    structural_accuracy = (
        sum(result.structural_match for result in matched) / matched_count if matched else 0.0
    )
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    local_ready = (
        not case_set.synthetic and coverage >= 0.40 and structural_accuracy >= 0.60 and p95 < 100.0
    )
    report = B0EvaluationReport(
        case_count=len(results),
        matched_count=matched_count,
        coverage=coverage,
        exact_match_accuracy=exact_accuracy,
        structural_accuracy=structural_accuracy,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        execution_accuracy=None,
        local_status="ready" if local_ready else "not_ready",
        scientific_status="not_ready",
        input_sha256=case_set.input_sha256,
        synthetic=case_set.synthetic,
        match_mode_counts=tuple(sorted(mode_counts.items())),
        template_counts=tuple(sorted(template_counts.items())),
        difficulty_counts=tuple(sorted(difficulty_counts.items())),
        rejection_counts=tuple(sorted(rejection_counts.items())),
        template_sha256=_single_fingerprint(
            [
                _baseline_fingerprint(baseline, "template_sha256"),
                *(prediction.template_sha256 for prediction in observed_predictions),
            ],
            "template",
        ),
        policy_sha256=_single_fingerprint(
            [
                _baseline_fingerprint(baseline, "policy_sha256"),
                *(prediction.policy_sha256 for prediction in observed_predictions),
            ],
            "policy",
        ),
        catalog_sha256=_single_fingerprint(
            [
                _baseline_fingerprint(baseline, "catalog_sha256"),
                *(prediction.catalog_sha256 for prediction in observed_predictions),
            ],
            "catalog",
        ),
        entities_sha256=_single_fingerprint(
            [
                _baseline_fingerprint(baseline, "entities_sha256"),
                *(prediction.entities_sha256 for prediction in observed_predictions),
            ],
            "entities",
        ),
        aliases_sha256=_single_fingerprint(
            [
                _baseline_fingerprint(baseline, "aliases_sha256"),
                *(prediction.aliases_sha256 for prediction in observed_predictions),
            ],
            "aliases",
        ),
        concepts_sha256=_single_fingerprint(
            [
                _baseline_fingerprint(baseline, "concepts_sha256"),
                *(prediction.concepts_sha256 for prediction in observed_predictions),
            ],
            "concepts",
        ),
    )
    return tuple(results), report
