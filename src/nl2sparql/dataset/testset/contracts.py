"""Typed contracts and safe file loading for the three-pool test set."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


class TestSetError(ValueError):
    """Raised when a test-set input or invariant is invalid."""

    __test__ = False


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")
_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CATEGORIES = frozenset(
    {
        "class_level",
        "comparison",
        "entity_lookup",
        "multi_hop",
        "simple_filter",
        "temporal_pattern",
        "time_range",
        "token_specific",
        "top_k",
        "transaction_aggregation",
    }
)
_ENTITY_KINDS = frozenset({"address_only", "concept_class", "named_entity"})


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TestSetError(f"{field} must not be empty")
    if _CONTROL_RE.search(value):
        raise TestSetError(f"{field} contains control characters")
    return value.strip()


def _identifier(value: str, field: str) -> str:
    value = _text(value, field)
    if "@" in value or not _IDENTIFIER_RE.fullmatch(value):
        raise TestSetError(f"{field} must be a pseudonym")
    return value


def _normalized_labels(
    values: tuple[str, ...], field: str, accepted: frozenset[str]
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TestSetError(f"{field} must be a tuple")
    normalized: list[str] = []
    for value in values:
        label = _text(value, field).casefold()
        if label not in accepted:
            raise TestSetError(f"unknown {field} label: {value!r}")
        if label not in normalized:
            normalized.append(label)
    return tuple(normalized)


def _normalized_annotations(
    values: tuple[str, ...], field: str, *, uppercase: bool = False
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TestSetError(f"{field} must be a tuple")
    normalized: list[str] = []
    for value in values:
        annotation = _text(value, field)
        if uppercase:
            annotation = annotation.upper()
        if annotation not in normalized:
            normalized.append(annotation)
    return tuple(normalized)


def parse_bool(value: str) -> bool:
    """Parse an explicit lowercase-insensitive boolean token."""
    normalized = _text(value, "boolean").lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise TestSetError(f"boolean must be true or false, got {value!r}")


def load_csv(
    path: Path,
    required_columns: tuple[str, ...],
    *,
    required_values: tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    """Read a UTF-8 CSV with an exact header and non-empty required fields."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise TestSetError(f"{path} has no header") from exc
            if len(header) != len(set(header)):
                raise TestSetError(f"{path} has duplicate header columns")
            expected = list(required_columns)
            if header != expected:
                raise TestSetError(
                    f"{path} header mismatch: expected {expected}, received {header}"
                )
            values_to_check = set(required_values or required_columns)
            rows: list[dict[str, str]] = []
            for row_number, values in enumerate(reader, start=2):
                if len(values) != len(header):
                    raise TestSetError(f"{path}:{row_number} has the wrong column count")
                record = dict(zip(header, values, strict=True))
                for column in values_to_check:
                    _text(record[column], f"{path}:{row_number}:{column}")
                rows.append(record)
            return rows
    except OSError as exc:
        raise TestSetError(f"unable to read {path}: {exc}") from exc


@dataclass(frozen=True)
class TestSetPaths:
    """Filesystem locations for one three-pool bundle."""

    __test__ = False

    raw_pool_a: Path
    sql_pool_b: Path
    review_pool_c: Path
    final_selection: Path
    final_jsonl: Path
    report_json: Path
    live_evidence: Path

    @classmethod
    def from_root(cls, root: Path) -> TestSetPaths:
        """Derive stable artifact paths below ``root``."""
        return cls(
            raw_pool_a=root / "raw_pool_a.csv",
            sql_pool_b=root / "sql_pool_b.csv",
            review_pool_c=root / "review_pool_c.csv",
            final_selection=root / "final_selection.csv",
            final_jsonl=root / "test-100.jsonl",
            report_json=root / "validation-report.json",
            live_evidence=root / "live-evidence.json",
        )


@dataclass(frozen=True)
class PoolARecord:
    """One natural-language question submitted by Pool A."""

    question_id: str
    author_id: str
    nl: str
    persona: str
    source_batch: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _identifier(self.question_id, "question_id"))
        object.__setattr__(self, "author_id", _identifier(self.author_id, "author_id"))
        object.__setattr__(self, "nl", _text(self.nl, "nl"))
        object.__setattr__(self, "persona", _text(self.persona, "persona"))
        object.__setattr__(self, "source_batch", _text(self.source_batch, "source_batch"))


@dataclass(frozen=True)
class PoolBRecord:
    """One canonical GoogleSQL answer authored by Pool B."""

    question_id: str
    writer_id: str
    sql: str
    expected_columns: tuple[str, ...]
    expected_empty: bool
    ambiguity_flag: bool
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _identifier(self.question_id, "question_id"))
        object.__setattr__(self, "writer_id", _identifier(self.writer_id, "writer_id"))
        object.__setattr__(self, "sql", _text(self.sql, "sql"))
        if (
            not isinstance(self.expected_columns, tuple)
            or not self.expected_columns
            or len(self.expected_columns) != len(set(self.expected_columns))
            or any(not _COLUMN_RE.fullmatch(column) for column in self.expected_columns)
        ):
            raise TestSetError(
                "expected_columns must contain unique explicit GoogleSQL column names"
            )
        object.__setattr__(self, "notes", self.notes.strip())


@dataclass(frozen=True)
class ReviewRecord:
    """One independent Pool C review decision."""

    question_id: str
    reviewer_id: str
    nl_quality: int
    faithfulness: int
    difficulty: str
    decision: str
    notes: str = ""

    DIFFICULTIES: ClassVar[frozenset[str]] = frozenset({"easy", "medium", "hard"})
    DECISIONS: ClassVar[frozenset[str]] = frozenset({"ACCEPT", "REVISE", "REJECT"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _identifier(self.question_id, "question_id"))
        object.__setattr__(self, "reviewer_id", _identifier(self.reviewer_id, "reviewer_id"))
        if self.nl_quality not in range(1, 6) or self.faithfulness not in range(1, 6):
            raise TestSetError("review scores must be integers from 1 to 5")
        if self.difficulty not in self.DIFFICULTIES:
            raise TestSetError(f"invalid review difficulty: {self.difficulty!r}")
        if self.decision not in self.DECISIONS:
            raise TestSetError(f"invalid review decision: {self.decision!r}")
        object.__setattr__(self, "notes", self.notes.strip())


@dataclass(frozen=True)
class SelectionRecord:
    """One lead-researcher choice for the final benchmark."""

    question_id: str
    final_difficulty: str
    categories: tuple[str, ...]
    selection_note: str
    entity_kinds: tuple[str, ...] = ()
    schema_elements: tuple[str, ...] = ()
    cq_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _identifier(self.question_id, "question_id"))
        if self.final_difficulty not in ReviewRecord.DIFFICULTIES:
            raise TestSetError(f"invalid final difficulty: {self.final_difficulty!r}")
        object.__setattr__(
            self,
            "categories",
            _normalized_labels(self.categories, "category", _CATEGORIES),
        )
        object.__setattr__(
            self,
            "entity_kinds",
            _normalized_labels(self.entity_kinds, "entity kind", _ENTITY_KINDS),
        )
        object.__setattr__(
            self,
            "schema_elements",
            _normalized_annotations(self.schema_elements, "schema element"),
        )
        object.__setattr__(
            self,
            "cq_ids",
            _normalized_annotations(self.cq_ids, "CQ ID", uppercase=True),
        )
        object.__setattr__(self, "selection_note", self.selection_note.strip())


@dataclass(frozen=True)
class FinalCase:
    """SQL-native final test-set record bound to live evidence."""

    id: str
    source: str
    nl: str
    sql: str
    difficulty: str
    categories: tuple[str, ...]
    schema_elements: tuple[str, ...]
    cq_ids: tuple[str, ...]
    expected_result_size: int | None
    ambiguity_flag: bool
    pool_b_writer: str
    pool_c_reviewers: tuple[str, ...]
    verified_executable: bool
    verified_at: str | None
    evidence_sha256: str | None
    expected_columns: tuple[str, ...] = ()
