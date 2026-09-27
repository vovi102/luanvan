"""Offline validation for agent-authored T3.5 candidate packs."""

from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.reviewed_contracts import (
    AGENT_REVIEWED_PROFILE,
    CandidateRecord,
    load_candidates,
)
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.sql.schema import SchemaCatalogError, load_catalog, validate_catalog

_QUESTION_FIELDS = frozenset({"nl", "nl_seed", "question"})
_LEAKAGE_SUFFIXES = frozenset({".csv", ".json", ".jsonl"})
_DIFFICULTY_QUOTA = {"easy": 36, "medium": 60, "hard": 24}


@dataclass(frozen=True)
class LeakageSource:
    """One leakage corpus fingerprint and extracted-question count."""

    path: Path
    sha256: str
    question_count: int


@dataclass(frozen=True)
class CandidatePackReport:
    """Deterministic evidence that a 120-case candidate pack is review-ready."""

    status: str
    provenance_profile: str
    candidate_count: int
    difficulty_counts: tuple[tuple[str, int], ...]
    category_count: int
    entity_kind_count: int
    candidate_sha256: str
    catalog_sha256: str
    leakage_sources: tuple[LeakageSource, ...]
    source_commit: str


def _canonical_nl(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _is_excluded_leakage_path(path: Path, repo_root: Path) -> bool:
    relative = path.relative_to(repo_root)
    if relative.parts[:3] == ("data", "dataset", "test"):
        return True
    return any(part.startswith("t3_5_candidate_set") for part in relative.parts)


def canonical_leakage_paths(repo_root: Path) -> tuple[Path, ...]:
    """Return stable existing Stage A–D, evaluation, and T4 leakage inputs."""
    roots = (
        repo_root / "data" / "dataset",
        repo_root / "data" / "eval",
        repo_root / "data" / "review_drafts" / "t4_candidate_set_2026-09-24",
    )
    paths: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.casefold() in _LEAKAGE_SUFFIXES
                and not _is_excluded_leakage_path(path, repo_root)
            ):
                paths.add(path.resolve())
    return tuple(sorted(paths, key=lambda item: item.relative_to(repo_root.resolve()).as_posix()))


def _questions_from_json_value(value: object) -> list[str]:
    questions: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _QUESTION_FIELDS and isinstance(item, str) and item.strip():
                questions.append(item)
            elif isinstance(item, (dict, list)):
                questions.extend(_questions_from_json_value(item))
    elif isinstance(value, list):
        for item in value:
            questions.extend(_questions_from_json_value(item))
    return questions


def _read_json_questions(path: Path, *, lines: bool) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8")
        if lines:
            values: list[object] = []
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    raise TestSetError(f"malformed leakage file {path}: blank line {line_number}")
                try:
                    values.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise TestSetError(
                        f"malformed leakage file {path} at line {line_number}"
                    ) from exc
            value: object = values
        else:
            value = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TestSetError(f"malformed leakage file {path}: {exc}") from exc
    return tuple(_questions_from_json_value(value))


def _read_csv_questions(path: Path) -> tuple[str, ...]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                return ()
            indexes = [index for index, name in enumerate(header) if name in _QUESTION_FIELDS]
            questions: list[str] = []
            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise TestSetError(
                        f"malformed leakage file {path}: wrong columns at line {line_number}"
                    )
                questions.extend(row[index] for index in indexes if row[index].strip())
            return tuple(questions)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise TestSetError(f"malformed leakage file {path}: {exc}") from exc


def _read_leakage_questions(path: Path) -> tuple[str, ...]:
    if path.suffix.casefold() == ".csv":
        return _read_csv_questions(path)
    return _read_json_questions(path, lines=path.suffix.casefold() == ".jsonl")


def _catalog_ids(catalog_path: Path) -> tuple[frozenset[str], frozenset[str], str]:
    try:
        snapshot = catalog_path.read_bytes()
        catalog = load_catalog(catalog_path, snapshot=snapshot)
        validate_catalog(catalog)
        relations = cast(dict[str, Any], catalog["analytical_relations"])
        schema_ids = set(relations)
        schema_ids.update(
            f"{relation_id}.{field_id}"
            for relation_id, relation in relations.items()
            for field_id in cast(dict[str, Any], relation["fields"])
        )
        cq_ids = {
            str(question["id"])
            for question in cast(list[dict[str, Any]], catalog["competency_questions"])
        }
    except (OSError, KeyError, TypeError, SchemaCatalogError) as exc:
        raise TestSetError(f"unable to validate candidate catalog {catalog_path}: {exc}") from exc
    return frozenset(schema_ids), frozenset(cq_ids), hashlib.sha256(snapshot).hexdigest()


def _output_aliases(sql: str) -> tuple[str, ...]:
    try:
        query = parse_one(sql, read="bigquery")
    except SqlglotError as exc:
        raise TestSetError(f"invalid GoogleSQL: {exc}") from exc
    select = query if isinstance(query, exp.Select) else query.find(exp.Select)
    if select is None or not select.expressions:
        raise TestSetError("SQL must have an outer SELECT projection")
    aliases: list[str] = []
    for projection in select.expressions:
        if not isinstance(projection, exp.Alias) or not projection.alias:
            raise TestSetError("SQL output columns must use explicit aliases")
        aliases.append(projection.alias)
    if len(aliases) != len(set(aliases)):
        raise TestSetError("SQL output aliases must be unique")
    return tuple(aliases)


def _validate_candidate_content(
    candidate: CandidateRecord,
    *,
    schema_ids: frozenset[str],
    cq_ids: frozenset[str],
    catalog_sha256: str,
) -> None:
    validate_sql_text(candidate.sql)
    if _output_aliases(candidate.sql) != candidate.expected_columns:
        raise TestSetError(
            f"{candidate.question_id} expected_columns do not match explicit SQL aliases"
        )
    if candidate.catalog_sha256 != catalog_sha256:
        raise TestSetError(f"{candidate.question_id} catalog_sha256 does not match the catalog")
    unknown_schema = set(candidate.schema_elements) - schema_ids
    if unknown_schema:
        raise TestSetError(
            f"{candidate.question_id} has unknown schema annotations: {sorted(unknown_schema)}"
        )
    unknown_cqs = set(candidate.cq_ids) - cq_ids
    if unknown_cqs:
        raise TestSetError(
            f"{candidate.question_id} has unknown CQ annotations: {sorted(unknown_cqs)}"
        )


def validate_candidate_pack(
    candidate_path: Path,
    *,
    repo_root: Path,
    catalog_path: Path,
) -> CandidatePackReport:
    """Validate one complete review-ready candidate pack without cloud access."""
    candidates = load_candidates(candidate_path)
    if len(candidates) != 120:
        raise TestSetError(f"candidate pack requires exactly 120 rows, received {len(candidates)}")
    expected_ids = tuple(f"t35-{index:03d}" for index in range(1, 121))
    received_ids = tuple(candidate.question_id for candidate in candidates)
    if received_ids != expected_ids:
        raise TestSetError("candidate IDs must be the ordered sequence t35-001 through t35-120")
    normalized = tuple(_canonical_nl(candidate.nl) for candidate in candidates)
    if len(normalized) != len(set(normalized)):
        raise TestSetError("candidate normalized NL values must be unique")

    difficulty_counts = Counter(candidate.difficulty for candidate in candidates)
    if difficulty_counts != _DIFFICULTY_QUOTA:
        raise TestSetError(f"candidate difficulty quota mismatch: {dict(difficulty_counts)}")
    categories = {category for candidate in candidates for category in candidate.categories}
    if len(categories) < 6:
        raise TestSetError("candidate pack must cover at least six categories")
    entity_kinds = {kind for candidate in candidates for kind in candidate.entity_kinds}
    if entity_kinds != {"address_only", "concept_class", "named_entity"}:
        raise TestSetError("candidate pack must cover all three entity kinds")

    schema_ids, cq_ids, catalog_sha256 = _catalog_ids(catalog_path)
    for candidate in candidates:
        _validate_candidate_content(
            candidate,
            schema_ids=schema_ids,
            cq_ids=cq_ids,
            catalog_sha256=catalog_sha256,
        )
    source_commits = {candidate.source_commit for candidate in candidates}
    if len(source_commits) != 1:
        raise TestSetError("candidate source_commit must be identical across the pack")

    leakage_sources: list[LeakageSource] = []
    leaked_questions: set[str] = set()
    resolved_root = repo_root.resolve()
    for path in canonical_leakage_paths(resolved_root):
        questions = _read_leakage_questions(path)
        leaked_questions.update(_canonical_nl(question) for question in questions)
        leakage_sources.append(
            LeakageSource(
                path=path.relative_to(resolved_root),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                question_count=len(questions),
            )
        )
    collisions = sorted(set(normalized) & leaked_questions)
    if collisions:
        raise TestSetError(f"candidate pack has normalized leakage collisions: {collisions}")

    return CandidatePackReport(
        status="draft_ready",
        provenance_profile=AGENT_REVIEWED_PROFILE,
        candidate_count=len(candidates),
        difficulty_counts=tuple(sorted(difficulty_counts.items())),
        category_count=len(categories),
        entity_kind_count=len(entity_kinds),
        candidate_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        catalog_sha256=catalog_sha256,
        leakage_sources=tuple(leakage_sources),
        source_commit=next(iter(source_commits)),
    )
