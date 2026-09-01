"""Offline operational evaluation for B1/B2 prediction runs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.models.b0.evaluate import load_b0_cases
from nl2sparql.models.b12.baseline import BaselineB1, BaselineB2
from nl2sparql.models.b12.contracts import SmallLLMError, SmallLLMPrediction, validate_question

Difficulty = Literal["easy", "medium", "hard"]

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class EvaluationCase:
    """One validated GoogleSQL evaluation input."""

    case_id: str
    question: str
    gold_sql: str
    difficulty: Difficulty
    categories: tuple[str, ...]
    input_sha256: str | None = None
    reviewed: bool = False
    live_verified: bool = False
    synthetic: bool = True
    _trusted_source: bool = field(init=False, default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _CASE_ID_RE.fullmatch(self.case_id):
            raise SmallLLMError("evaluation case ID is invalid")
        validate_question(self.question)
        try:
            validate_sql_text(self.gold_sql)
        except (TestSetError, TypeError) as exc:
            raise SmallLLMError(f"evaluation gold SQL is invalid: {exc}") from exc
        if self.difficulty not in {"easy", "medium", "hard"}:
            raise SmallLLMError("evaluation difficulty must be easy, medium, or hard")
        if (
            not isinstance(self.categories, tuple)
            or not self.categories
            or any(
                not isinstance(category, str) or not _CATEGORY_RE.fullmatch(category)
                for category in self.categories
            )
            or len(self.categories) != len(set(self.categories))
            or self.categories != tuple(sorted(self.categories))
        ):
            raise SmallLLMError(
                "evaluation categories must be a sorted unique tuple of identifiers"
            )
        if any(
            not isinstance(value, bool)
            for value in (self.reviewed, self.live_verified, self.synthetic)
        ):
            raise SmallLLMError("evaluation provenance markers must be boolean")
        if self.input_sha256 is not None and (
            not isinstance(self.input_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.input_sha256)
        ):
            raise SmallLLMError("evaluation input fingerprint is invalid")
        if not self.synthetic and (
            self.input_sha256 is None or not self.reviewed or not self.live_verified
        ):
            raise SmallLLMError("non-synthetic evaluation cases require reviewed live provenance")


@dataclass(frozen=True)
class EvaluationPrediction:
    """A case identity joined to its model prediction and gold metadata."""

    case_id: str
    gold_sql: str
    difficulty: Difficulty
    categories: tuple[str, ...]
    prediction: SmallLLMPrediction


@dataclass(frozen=True)
class EvaluationMetrics:
    """Operational counts emitted for later T5.4 aggregation."""

    total: int
    generated: int
    extraction_ok: int
    extraction_failed: int
    p50_latency_ms: float
    p95_latency_ms: float
    input_tokens: int
    output_tokens: int
    status_counts: tuple[tuple[str, int], ...]
    difficulty_counts: tuple[tuple[str, int], ...]
    category_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class EvaluationRun:
    """One ordered B1/B2 run plus explicit scientific blockers."""

    run_id: str
    baseline: Literal["b1", "b2"]
    predictions: tuple[EvaluationPrediction, ...]
    metrics: EvaluationMetrics
    scientific_ready: bool
    blockers: tuple[str, ...]
    seed: int
    generated_at_utc: str
    input_sha256: str | None


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _counts(values: Sequence[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(values).items()))


def load_evaluation_cases(
    path: Path,
    *,
    synthetic: bool = False,
) -> tuple[EvaluationCase, ...]:
    """Load one exact UTF-8 JSONL snapshot into validated evaluation cases."""
    if not isinstance(path, Path):
        raise SmallLLMError("evaluation path must be a pathlib.Path")
    if not isinstance(synthetic, bool):
        raise SmallLLMError("synthetic marker must be boolean")
    try:
        snapshot = path.read_bytes()
        text = snapshot.decode("utf-8")
    except OSError as exc:
        raise SmallLLMError(f"unable to read evaluation snapshot {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SmallLLMError(f"evaluation snapshot must be UTF-8: {exc}") from exc
    if not text.strip():
        raise SmallLLMError("evaluation snapshot must not be empty")
    input_sha256 = hashlib.sha256(snapshot).hexdigest()
    trusted_cases = None
    if not synthetic:
        try:
            trusted = load_b0_cases(path, synthetic=False)
        except ValueError as exc:
            raise SmallLLMError(
                f"evaluation snapshot is not finalized T3.5 evidence: {exc}"
            ) from exc
        if trusted.input_sha256 != input_sha256:
            raise SmallLLMError("evaluation snapshot changed during provenance validation")
        trusted_cases = trusted.cases
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise SmallLLMError(f"evaluation snapshot line {line_number} must not be blank")
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SmallLLMError(
                f"evaluation snapshot line {line_number} is invalid JSON: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise SmallLLMError(f"evaluation snapshot line {line_number} must be an object")
        categories = raw.get("categories")
        if not isinstance(categories, list) or any(
            not isinstance(category, str) or not category.strip() for category in categories
        ):
            raise SmallLLMError(
                f"evaluation snapshot line {line_number} categories must be strings"
            )
        normalized_categories = tuple(
            sorted({"_".join(category.strip().casefold().split()) for category in categories})
        )
        try:
            cases.append(
                EvaluationCase(
                    case_id=raw.get("id"),
                    question=raw.get("nl"),
                    gold_sql=raw.get("sql"),
                    difficulty=raw.get("difficulty"),
                    categories=normalized_categories,
                    input_sha256=input_sha256,
                    reviewed=not synthetic,
                    live_verified=not synthetic,
                    synthetic=synthetic,
                )
            )
        except SmallLLMError as exc:
            raise SmallLLMError(
                f"evaluation snapshot line {line_number} is invalid: {exc}"
            ) from exc
    ids = tuple(case.case_id for case in cases)
    if len(ids) != len(set(ids)):
        raise SmallLLMError("evaluation snapshot contains duplicate case IDs")
    if trusted_cases is not None:
        trusted_identity = tuple(
            (case.case_id, case.question, case.gold_sql, case.difficulty) for case in trusted_cases
        )
        loaded_identity = tuple(
            (case.case_id, case.question, case.gold_sql, case.difficulty) for case in cases
        )
        if loaded_identity != trusted_identity:
            raise SmallLLMError("evaluation snapshot identity differs from trusted T3.5 parse")
    if trusted_cases is not None:
        for case in cases:
            object.__setattr__(case, "_trusted_source", True)
    return tuple(cases)


def evaluate_baseline(
    cases: Sequence[EvaluationCase],
    baseline: BaselineB1 | BaselineB2,
    *,
    run_id: str,
    reviewed: bool = False,
    live_verified: bool = False,
) -> EvaluationRun:
    """Run ordered cases and report operational evidence without execution accuracy."""
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise SmallLLMError("evaluation run ID is invalid")
    if not isinstance(reviewed, bool) or not isinstance(live_verified, bool):
        raise SmallLLMError("evaluation evidence flags must be boolean")
    if not isinstance(baseline, (BaselineB1, BaselineB2)):
        raise SmallLLMError("baseline must be BaselineB1 or BaselineB2")
    accepted = tuple(cases)
    if not accepted or any(not isinstance(case, EvaluationCase) for case in accepted):
        raise SmallLLMError("evaluation requires non-empty EvaluationCase values")
    ids = tuple(case.case_id for case in accepted)
    if len(ids) != len(set(ids)):
        raise SmallLLMError("evaluation case IDs must not contain duplicates")

    rows: list[EvaluationPrediction] = []
    for case in accepted:
        if isinstance(baseline, BaselineB2):
            prediction = baseline.predict_detailed(case.question, target_id=case.case_id)
        else:
            prediction = baseline.predict_detailed(case.question)
        rows.append(
            EvaluationPrediction(
                case_id=case.case_id,
                gold_sql=case.gold_sql,
                difficulty=case.difficulty,
                categories=case.categories,
                prediction=prediction,
            )
        )
    predictions = tuple(rows)
    latencies = [row.prediction.latency_ms for row in predictions]
    generated = sum(bool(row.prediction.raw_output.strip()) for row in predictions)
    extraction_ok = sum(row.prediction.extraction_status == "ok" for row in predictions)
    metrics = EvaluationMetrics(
        total=len(predictions),
        generated=generated,
        extraction_ok=extraction_ok,
        extraction_failed=len(predictions) - extraction_ok,
        p50_latency_ms=_quantile(latencies, 0.50),
        p95_latency_ms=_quantile(latencies, 0.95),
        input_tokens=sum(row.prediction.completion.input_tokens for row in predictions),
        output_tokens=sum(row.prediction.completion.output_tokens for row in predictions),
        status_counts=_counts([row.prediction.extraction_status for row in predictions]),
        difficulty_counts=_counts([row.difficulty for row in predictions]),
        category_counts=_counts([category for row in predictions for category in row.categories]),
    )

    blockers: list[str] = []
    if any(row.prediction.completion.synthetic_backend for row in predictions):
        blockers.append("synthetic_backend")
    if any(case.synthetic for case in accepted):
        blockers.append("synthetic_test_set")
    input_fingerprints = {case.input_sha256 for case in accepted}
    trusted_source = all(case._trusted_source for case in accepted)
    if None in input_fingerprints or len(input_fingerprints) != 1 or not trusted_source:
        blockers.append("trusted_test_set_provenance_missing")
    if not trusted_source or not reviewed or not all(case.reviewed for case in accepted):
        blockers.append("reviewed_test_set_missing")
    if not trusted_source or not live_verified or not all(case.live_verified for case in accepted):
        blockers.append("live_evidence_missing")
    if len(predictions) != 100:
        blockers.append("expected_100_cases")
    if generated != len(predictions):
        blockers.append("incomplete_generation")
    threshold = 5_000.0 if predictions[0].prediction.baseline == "b1" else 8_000.0
    if metrics.p95_latency_ms >= threshold:
        blockers.append("latency_gate_failed")
    if predictions[0].prediction.baseline == "b2":
        blockers.append("trusted_training_provenance_missing")
    blockers_tuple = tuple(sorted(blockers))
    return EvaluationRun(
        run_id=run_id,
        baseline=predictions[0].prediction.baseline,
        predictions=predictions,
        metrics=metrics,
        scientific_ready=not blockers_tuple,
        blockers=blockers_tuple,
        seed=42,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        input_sha256=(next(iter(input_fingerprints)) if len(input_fingerprints) == 1 else None),
    )


def compare_reproducibility(left: EvaluationRun, right: EvaluationRun) -> bool:
    """Compare ordered model-observable outputs while ignoring run timing and IDs."""
    if not isinstance(left, EvaluationRun) or not isinstance(right, EvaluationRun):
        raise SmallLLMError("reproducibility comparison requires EvaluationRun values")
    if left.baseline != right.baseline or len(left.predictions) != len(right.predictions):
        return False

    def observable(row: EvaluationPrediction) -> tuple[object, ...]:
        prediction = row.prediction
        return (
            row.case_id,
            prediction.raw_output,
            prediction.sql,
            prediction.extraction_status,
            prediction.completion.model_id,
            prediction.completion.model_revision,
            prediction.catalog_sha256,
            prediction.summary_sha256,
            prediction.prompt_sha256,
            prediction.config_sha256,
            prediction.training_sha256,
            tuple(example.record_id for example in prediction.selected_examples),
        )

    return all(
        observable(left_row) == observable(right_row)
        for left_row, right_row in zip(left.predictions, right.predictions, strict=True)
    )
