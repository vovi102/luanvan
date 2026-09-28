"""Shared authoritative test-set and native artifact helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sparql.evaluation.contracts import EvaluationError
from nl2sparql.models.b0.evaluate import B0EvaluationError, load_b0_cases


@dataclass(frozen=True)
class AuthoritativeCase:
    """One T3.5 case with all evaluation metadata retained."""

    case_id: str
    question: str
    gold_sql: str
    difficulty: str
    categories: tuple[str, ...]


@dataclass(frozen=True)
class AuthoritativeCaseSet:
    """Ordered finalized T3.5 snapshot and its review provenance."""

    cases: tuple[AuthoritativeCase, ...]
    sha256: str
    reviewed: bool
    live_verified: bool
    synthetic: bool
    provenance_profile: str


def sha256_file(path: Path) -> str:
    """Return the digest of exact file bytes."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvaluationError(f"cannot read source artifact {path}: {exc}") from exc


def require_distinct_files(*paths: Path) -> None:
    """Reject resolved-path, symlink and hardlink aliases among native inputs."""
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            try:
                alias = left.resolve(strict=False) == right.resolve(strict=False) or (
                    left.exists() and right.exists() and os.path.samefile(left, right)
                )
            except OSError as exc:
                raise EvaluationError(f"cannot inspect native input paths: {exc}") from exc
            if alias:
                raise EvaluationError("native artifacts must be distinct files")


def read_jsonl_objects(path: Path) -> tuple[dict[str, Any], ...]:
    """Read non-blank JSON object lines without weakening duplicate-ID checks."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"cannot read JSONL artifact {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line:
            raise EvaluationError(f"JSONL artifact {path} has blank line {number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"JSONL artifact {path} has invalid line {number}") from exc
        if not isinstance(row, dict):
            raise EvaluationError(f"JSONL artifact {path} line {number} must be an object")
        rows.append(row)
    return tuple(rows)


def load_authoritative_test_set(path: Path, *, synthetic: bool) -> AuthoritativeCaseSet:
    """Strictly load a finalized T3.5 snapshot while preserving its order."""
    try:
        validated = load_b0_cases(path, synthetic=synthetic)
    except B0EvaluationError as exc:
        raise EvaluationError(f"invalid authoritative test set: {exc}") from exc
    rows = read_jsonl_objects(path)
    cases = tuple(
        AuthoritativeCase(
            case_id=case.case_id,
            question=case.question,
            gold_sql=case.gold_sql,
            difficulty=case.difficulty,
            categories=tuple(sorted(set(rows[index]["categories"]))),
        )
        for index, case in enumerate(validated.cases)
    )
    return AuthoritativeCaseSet(
        cases=cases,
        sha256=validated.input_sha256,
        reviewed=all(bool(row["pool_c_reviewers"]) for row in rows),
        live_verified=all(row["verified_executable"] is True for row in rows),
        synthetic=synthetic,
        provenance_profile=validated.provenance_profile,
    )
