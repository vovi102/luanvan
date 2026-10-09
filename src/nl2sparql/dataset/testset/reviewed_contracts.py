"""Contracts for the agent-authored, human-reviewed T3.5 benchmark."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from nl2sparql.dataset.testset.contracts import (
    _CATEGORIES,
    _ENTITY_KINDS,
    ReviewRecord,
    SelectionRecord,
    TestSetError,
    _identifier,
    _normalized_annotations,
    _normalized_labels,
    _text,
    load_csv,
)

AGENT_REVIEWED_PROFILE = "agent_authored_human_reviewed_v1"
BILINGUAL_AUTHORSHIP_PROFILE = "agent-authored"
BILINGUAL_REVIEW_PROFILE = "single-human-reviewed"
CANDIDATE_SCHEMA_VERSION = "1.0.0"

_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "provenance_profile",
        "question_id",
        "author_type",
        "nl",
        "sql",
        "expected_columns",
        "expected_empty",
        "ambiguity_flag",
        "difficulty",
        "categories",
        "entity_kinds",
        "schema_elements",
        "cq_ids",
        "rationale",
        "generation_batch",
        "catalog_sha256",
        "source_commit",
    }
)

_REVIEW_HEADER = (
    "question_id",
    "review_round",
    "reviewer_id",
    "nl_quality",
    "sql_faithfulness",
    "difficulty",
    "decision",
    "revised_nl",
    "revised_sql",
    "notes",
)

_SELECTION_HEADER = (
    "question_id",
    "final_difficulty",
    "categories",
    "entity_kinds",
    "schema_elements",
    "cq_ids",
    "selection_note",
)


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TestSetError(f"{field} must be a JSON array")
    return tuple(_text(item, field) for item in value)


def _required_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise TestSetError(f"{field} must be a boolean")
    return value


def _required_digest(value: object, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise TestSetError(f"{field} has an invalid digest")
    return value


@dataclass(frozen=True)
class CandidateRecord:
    """One agent-authored NL–GoogleSQL candidate awaiting human review."""

    schema_version: str
    provenance_profile: str
    question_id: str
    author_type: str
    nl: str
    sql: str
    expected_columns: tuple[str, ...]
    expected_empty: bool
    ambiguity_flag: bool
    difficulty: str
    categories: tuple[str, ...]
    entity_kinds: tuple[str, ...]
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    rationale: str
    generation_batch: str
    catalog_sha256: str
    source_commit: str

    @classmethod
    def from_mapping(cls, row: dict[str, object]) -> CandidateRecord:
        """Decode one candidate from an exact JSON object."""
        if set(row) != _CANDIDATE_FIELDS:
            missing = sorted(_CANDIDATE_FIELDS - set(row))
            extra = sorted(set(row) - _CANDIDATE_FIELDS)
            raise TestSetError(f"candidate fields mismatch: missing={missing}, extra={extra}")
        if row["schema_version"] != CANDIDATE_SCHEMA_VERSION:
            raise TestSetError("schema_version must be 1.0.0")
        if row["provenance_profile"] != AGENT_REVIEWED_PROFILE:
            raise TestSetError(f"provenance_profile must be {AGENT_REVIEWED_PROFILE}")
        if row["author_type"] != "agent":
            raise TestSetError("author_type must be agent")
        expected_columns = _string_tuple(row["expected_columns"], "expected_columns")
        if (
            not expected_columns
            or len(expected_columns) != len(set(expected_columns))
            or any(not _COLUMN_RE.fullmatch(column) for column in expected_columns)
        ):
            raise TestSetError("expected_columns must contain unique explicit aliases")
        difficulty = _text(row["difficulty"], "difficulty")
        if difficulty not in ReviewRecord.DIFFICULTIES:
            raise TestSetError(f"invalid difficulty: {difficulty!r}")
        return cls(
            schema_version=CANDIDATE_SCHEMA_VERSION,
            provenance_profile=AGENT_REVIEWED_PROFILE,
            question_id=_identifier(row["question_id"], "question_id"),
            author_type="agent",
            nl=_text(row["nl"], "nl"),
            sql=_text(row["sql"], "sql"),
            expected_columns=expected_columns,
            expected_empty=_required_bool(row["expected_empty"], "expected_empty"),
            ambiguity_flag=_required_bool(row["ambiguity_flag"], "ambiguity_flag"),
            difficulty=difficulty,
            categories=_normalized_labels(
                _string_tuple(row["categories"], "categories"), "category", _CATEGORIES
            ),
            entity_kinds=_normalized_labels(
                _string_tuple(row["entity_kinds"], "entity_kinds"),
                "entity kind",
                _ENTITY_KINDS,
            ),
            schema_elements=_normalized_annotations(
                _string_tuple(row["schema_elements"], "schema_elements"),
                "schema element",
            ),
            cq_ids=_normalized_annotations(
                _string_tuple(row["cq_ids"], "cq_ids"), "CQ ID", uppercase=True
            ),
            rationale=_text(row["rationale"], "rationale"),
            generation_batch=_identifier(row["generation_batch"], "generation_batch"),
            catalog_sha256=_required_digest(row["catalog_sha256"], "catalog_sha256", _SHA256_RE),
            source_commit=_required_digest(row["source_commit"], "source_commit", _COMMIT_RE),
        )


@dataclass(frozen=True)
class ReviewEvent:
    """One append-only human review event for a candidate."""

    question_id: str
    review_round: int
    reviewer_id: str
    nl_quality: int
    sql_faithfulness: int
    difficulty: str
    decision: str
    revised_nl: str = ""
    revised_sql: str = ""
    notes: str = ""

    DECISIONS: ClassVar[frozenset[str]] = frozenset({"ACCEPT", "REVISE", "REJECT"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _identifier(self.question_id, "question_id"))
        object.__setattr__(self, "reviewer_id", _identifier(self.reviewer_id, "reviewer_id"))
        if not isinstance(self.review_round, int) or isinstance(self.review_round, bool):
            raise TestSetError("review round must be an integer")
        if self.review_round < 1:
            raise TestSetError("review round must start at 1")
        if any(
            not isinstance(score, int) or isinstance(score, bool) or score not in range(1, 6)
            for score in (self.nl_quality, self.sql_faithfulness)
        ):
            raise TestSetError("review scores must be integers from 1 to 5")
        if self.difficulty not in ReviewRecord.DIFFICULTIES:
            raise TestSetError(f"invalid review difficulty: {self.difficulty!r}")
        if self.decision not in self.DECISIONS:
            raise TestSetError(f"invalid review decision: {self.decision!r}")
        revised_nl = self.revised_nl.strip()
        revised_sql = self.revised_sql.strip()
        if self.decision == "REVISE" and not (revised_nl or revised_sql):
            raise TestSetError("REVISE requires at least one revision")
        if self.decision != "REVISE" and (revised_nl or revised_sql):
            raise TestSetError(f"{self.decision} must not contain revision content")
        object.__setattr__(self, "revised_nl", revised_nl)
        object.__setattr__(self, "revised_sql", revised_sql)
        object.__setattr__(self, "notes", self.notes.strip())


@dataclass(frozen=True)
class AcceptedCandidate:
    """Post-review candidate content bound to its reviewer and hashes."""

    question_id: str
    reviewer_id: str
    nl: str
    sql: str
    expected_columns: tuple[str, ...]
    expected_empty: bool
    ambiguity_flag: bool
    difficulty: str
    categories: tuple[str, ...]
    entity_kinds: tuple[str, ...]
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    candidate_sha256: str
    accepted_content_sha256: str


@dataclass(frozen=True)
class ReviewedTestSetPaths:
    """Filesystem paths for draft review inputs and immutable final outputs."""

    candidates: Path
    review_events: Path
    final_selection: Path
    review_guide: Path
    candidate_manifest: Path
    validation_report: Path
    live_evidence: Path
    final_jsonl: Path
    final_manifest: Path

    @classmethod
    def from_roots(cls, draft_root: Path, final_root: Path) -> ReviewedTestSetPaths:
        """Derive the reviewed workflow's separated draft and final paths."""
        return cls(
            candidates=draft_root / "candidates.jsonl",
            review_events=draft_root / "review_events.csv",
            final_selection=draft_root / "final_selection.csv",
            review_guide=draft_root / "REVIEW_GUIDE.md",
            candidate_manifest=draft_root / "manifest.json",
            validation_report=draft_root / "validation-report.json",
            live_evidence=final_root / "live-evidence.json",
            final_jsonl=final_root / "test-100.jsonl",
            final_manifest=final_root / "manifest.json",
        )


class _DuplicateKey(ValueError):
    pass


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def load_candidates(path: Path) -> tuple[CandidateRecord, ...]:
    """Load strict candidate JSONL without accepting profile confusion."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TestSetError(f"unable to read {path}: {exc}") from exc
    candidates: list[CandidateRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TestSetError(f"{path}:{line_number} contains a blank line")
        try:
            row = json.loads(line, object_pairs_hook=_json_object)
        except _DuplicateKey as exc:
            raise TestSetError(
                f"{path}:{line_number} has duplicate JSON key {exc.args[0]!r}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise TestSetError(f"{path}:{line_number} is invalid JSON") from exc
        if not isinstance(row, dict):
            raise TestSetError(f"{path}:{line_number} must be a JSON object")
        candidates.append(CandidateRecord.from_mapping(row))
    return tuple(candidates)


def load_review_events(path: Path) -> tuple[ReviewEvent, ...]:
    """Load the exact append-only human review event CSV."""
    rows = load_csv(
        path,
        _REVIEW_HEADER,
        required_values=(
            "question_id",
            "review_round",
            "reviewer_id",
            "nl_quality",
            "sql_faithfulness",
            "difficulty",
            "decision",
        ),
    )
    events: list[ReviewEvent] = []
    for row in rows:
        try:
            events.append(
                ReviewEvent(
                    question_id=row["question_id"],
                    review_round=int(row["review_round"]),
                    reviewer_id=row["reviewer_id"],
                    nl_quality=int(row["nl_quality"]),
                    sql_faithfulness=int(row["sql_faithfulness"]),
                    difficulty=row["difficulty"],
                    decision=row["decision"],
                    revised_nl=row["revised_nl"],
                    revised_sql=row["revised_sql"],
                    notes=row["notes"],
                )
            )
        except ValueError as exc:
            raise TestSetError(f"{path} contains a non-integer review field") from exc
    return tuple(events)


def load_reviewed_selections(path: Path) -> tuple[SelectionRecord, ...]:
    """Load explicit human final-selection rows for the reviewed profile."""
    rows = load_csv(
        path,
        _SELECTION_HEADER,
        required_values=(
            "question_id",
            "final_difficulty",
            "categories",
            "entity_kinds",
            "schema_elements",
            "cq_ids",
        ),
    )
    return tuple(
        SelectionRecord(
            question_id=row["question_id"],
            final_difficulty=row["final_difficulty"],
            categories=tuple(row["categories"].split("|")),
            entity_kinds=tuple(row["entity_kinds"].split("|")),
            schema_elements=tuple(row["schema_elements"].split("|")),
            cq_ids=tuple(row["cq_ids"].split("|")),
            selection_note=row["selection_note"],
        )
        for row in rows
    )
