"""Ground-truth validation and offline metrics for schema retrieval."""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from nl2sparql.linking.schema.contracts import SchemaElement, SchemaLinkerError
from nl2sparql.linking.schema.linker import SchemaLinker

GROUND_TRUTH_KEYS = frozenset({"id", "nl", "gold_relations", "gold_fields"})


@dataclass(frozen=True)
class GroundTruthCase:
    """One reviewed natural-language question and its relevant schema elements."""

    id: str
    nl: str
    gold_relations: tuple[str, ...]
    gold_fields: tuple[str, ...]


@dataclass(frozen=True)
class CaseEvaluation:
    """Per-question rankings and metric contributions used for error inspection."""

    id: str
    nl: str
    gold_relations: tuple[str, ...]
    gold_fields: tuple[str, ...]
    retrieved_relations: tuple[str, ...]
    retrieved_fields: tuple[str, ...]
    relation_hits: int
    field_hits: int
    field_reciprocal_rank: float
    latency_ms: float


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregate retrieval metrics plus auditable per-case outcomes."""

    case_count: int
    relation_k: int
    field_k: int
    relation_recall_at_k: float
    field_recall_at_k: float
    field_mrr: float
    latency_p50_ms: float
    latency_p95_ms: float
    results: tuple[CaseEvaluation, ...]


def _normalized_identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _required_text(value: object, label: str, line_number: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaLinkerError(f"ground truth line {line_number}: {label} must be non-empty")
    return value.strip()


def _gold_ids(value: object, label: str, line_number: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise SchemaLinkerError(
            f"ground truth line {line_number}: {label} must be a non-empty array"
        )
    rows = tuple(_required_text(item, label, line_number) for item in value)
    if len(rows) != len(set(rows)):
        raise SchemaLinkerError(
            f"ground truth line {line_number}: {label} contains duplicate elements"
        )
    return rows


def load_ground_truth(
    path: Path,
    valid_elements: Sequence[SchemaElement],
    expected_count: int = 50,
) -> tuple[GroundTruthCase, ...]:
    """Load an exact, explicit JSONL ground truth against catalog element IDs."""
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count <= 0
    ):
        raise SchemaLinkerError("expected_count must be a positive integer")
    element_kinds = {element.element_id: element.kind for element in valid_elements}
    if len(element_kinds) != len(valid_elements):
        raise SchemaLinkerError("valid_elements must contain unique element IDs")
    relation_ids = {element_id for element_id, kind in element_kinds.items() if kind == "relation"}
    field_ids = {element_id for element_id, kind in element_kinds.items() if kind == "field"}

    cases: list[GroundTruthCase] = []
    seen_ids: set[str] = set()
    seen_nl: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            try:
                raw = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise SchemaLinkerError(
                    f"ground truth line {line_number}: invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(raw, dict) or set(raw) != GROUND_TRUTH_KEYS:
                raise SchemaLinkerError(
                    f"ground truth line {line_number}: record must contain exact keys "
                    "id, nl, gold_relations, gold_fields"
                )
            case_id = _required_text(raw["id"], "id", line_number)
            nl = _required_text(raw["nl"], "nl", line_number)
            normalized_nl = _normalized_identity(nl)
            if case_id in seen_ids:
                raise SchemaLinkerError(
                    f"ground truth line {line_number}: duplicate ID {case_id!r}"
                )
            if normalized_nl in seen_nl:
                raise SchemaLinkerError(f"ground truth line {line_number}: duplicate NL {nl!r}")
            gold_relations = _gold_ids(raw["gold_relations"], "gold_relations", line_number)
            gold_fields = _gold_ids(raw["gold_fields"], "gold_fields", line_number)
            unknown = (set(gold_relations) - relation_ids) | (set(gold_fields) - field_ids)
            if unknown:
                raise SchemaLinkerError(
                    f"ground truth line {line_number}: unknown schema elements: "
                    f"{', '.join(sorted(unknown))}"
                )
            field_relations = {field_id.split(".", 1)[0] for field_id in gold_fields}
            if not field_relations <= set(gold_relations):
                raise SchemaLinkerError(
                    f"ground truth line {line_number}: gold fields must be consistent with "
                    "gold relations"
                )
            seen_ids.add(case_id)
            seen_nl.add(normalized_nl)
            cases.append(GroundTruthCase(case_id, nl, gold_relations, gold_fields))
    if len(cases) != expected_count:
        line_number = min(len(cases) + 1, expected_count)
        raise SchemaLinkerError(
            f"ground truth line {line_number}: expected exactly {expected_count} rows, "
            f"found {len(cases)}"
        )
    return tuple(cases)


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _positive_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SchemaLinkerError(f"{label} must be a positive integer")
    return value


def evaluate_linker(
    linker: SchemaLinker,
    cases: Sequence[GroundTruthCase],
    field_k: int = 10,
    relation_k: int = 5,
) -> EvaluationReport:
    """Measure micro Recall@K, field MRR, and warm latency percentiles."""
    field_k = _positive_integer(field_k, "field_k")
    relation_k = _positive_integer(relation_k, "relation_k")
    if not cases:
        raise SchemaLinkerError("cases must be non-empty")
    case_rows = tuple(cases)
    if any(not isinstance(case, GroundTruthCase) for case in case_rows):
        raise SchemaLinkerError("cases must contain GroundTruthCase values")

    maximum_k = max(field_k, relation_k)
    linker.link(case_rows[0].nl, top_k=maximum_k)
    results: list[CaseEvaluation] = []
    relation_hits = 0
    relation_relevant = 0
    field_hits = 0
    field_relevant = 0
    reciprocal_rank_total = 0.0
    latencies: list[float] = []
    for case in case_rows:
        started = perf_counter()
        linked = linker.link(case.nl, top_k=maximum_k)
        latency_ms = (perf_counter() - started) * 1_000.0
        retrieved_relations = tuple(row.element_id for row in linked.relations[:relation_k])
        retrieved_fields = tuple(row.element_id for row in linked.fields[:field_k])
        case_relation_hits = len(set(retrieved_relations) & set(case.gold_relations))
        case_field_hits = len(set(retrieved_fields) & set(case.gold_fields))
        reciprocal_rank = next(
            (
                1.0 / rank
                for rank, element_id in enumerate(retrieved_fields, start=1)
                if element_id in set(case.gold_fields)
            ),
            0.0,
        )
        relation_hits += case_relation_hits
        relation_relevant += len(set(case.gold_relations))
        field_hits += case_field_hits
        field_relevant += len(set(case.gold_fields))
        reciprocal_rank_total += reciprocal_rank
        latencies.append(latency_ms)
        results.append(
            CaseEvaluation(
                id=case.id,
                nl=case.nl,
                gold_relations=case.gold_relations,
                gold_fields=case.gold_fields,
                retrieved_relations=retrieved_relations,
                retrieved_fields=retrieved_fields,
                relation_hits=case_relation_hits,
                field_hits=case_field_hits,
                field_reciprocal_rank=reciprocal_rank,
                latency_ms=latency_ms,
            )
        )
    if relation_relevant == 0 or field_relevant == 0:
        raise SchemaLinkerError("cases must contain non-empty gold relations and fields")
    return EvaluationReport(
        case_count=len(case_rows),
        relation_k=relation_k,
        field_k=field_k,
        relation_recall_at_k=relation_hits / relation_relevant,
        field_recall_at_k=field_hits / field_relevant,
        field_mrr=reciprocal_rank_total / len(case_rows),
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        results=tuple(results),
    )
