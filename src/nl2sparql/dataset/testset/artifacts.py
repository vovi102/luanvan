"""Scaffold, report, and final artifact publication for the test set."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.live import LiveEvidence
from nl2sparql.dataset.testset.validate import Bundle, validate_bundle, validate_selection


@dataclass(frozen=True)
class ScaffoldReport:
    """Files created by a scaffold operation."""

    created_count: int
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class FinalizationReport:
    """Evidence emitted after final JSONL publication."""

    status: str
    record_count: int
    output_sha256: str


_HEADERS: dict[str, str] = {
    "raw_pool_a.csv": "question_id,author_id,nl,persona,source_batch\n",
    "sql_pool_b.csv": "question_id,writer_id,sql,expected_empty,ambiguity_flag,notes\n",
    "review_pool_c.csv": (
        "question_id,reviewer_id,nl_quality,faithfulness,difficulty,decision,notes\n"
    ),
    "final_selection.csv": "question_id,final_difficulty,categories,entity_kinds,selection_note\n",
}
_PROCESS = """# T3.5 three-pool collection process

Pool A authors write natural English questions without seeing the schema. Pool B
authors independently write read-only GoogleSQL and record ambiguity. Pool C
reviewers score quality, faithfulness, difficulty, and decision. Use pseudonyms
only; keep consent records separate from benchmark rows.

Run `python scripts/12_test_set_workflow.py validate` before sharing a bundle.
Live verification requires configured BigQuery credentials and the approved
20 GiB/query, 64 GiB aggregate policy.
"""
_CONSENT = """# T3.5 consent checklist

Before collecting a submission, record a pseudonymous participant ID, consent to
research use and publication, withdrawal contact/process, and compensation terms
in a private channel. Do not put email addresses, names, or signatures in the
public CSV artifacts. Publish only rows covered by explicit consent.
"""


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode()


def write_scaffold(root: Path, force: bool = False) -> ScaffoldReport:
    """Create collaborator headers and handoff documents without unsafe overwrite."""
    root.mkdir(parents=True, exist_ok=True)
    contents: dict[Path, str] = {
        **{root / name: header for name, header in _HEADERS.items()},
        root / "PROCESS.md": _PROCESS,
        root / "CONSENT.md": _CONSENT,
    }
    created: list[Path] = []
    for path, content in contents.items():
        if path.exists() and path.stat().st_size and not force:
            raise TestSetError(f"refusing to overwrite non-empty file {path}")
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return ScaffoldReport(created_count=len(created), paths=tuple(created))


def write_report(report: Mapping[str, Any] | object, path: Path) -> None:
    """Write canonical report data with a self-contained SHA-256 digest."""
    if is_dataclass(report):
        payload = asdict(report)
    elif isinstance(report, Mapping):
        payload = dict(report)
    else:
        raise TestSetError("report must be a dataclass or mapping")
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    output = {**payload, "report_sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(output))


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def finalize_bundle(
    bundle: Bundle,
    evidence: LiveEvidence | None,
    selection_path: Path,
    output_path: Path,
) -> FinalizationReport:
    """Publish exactly 100 SQL-native cases only after every gate passes."""
    if evidence is None:
        raise TestSetError("live evidence is required before finalization")
    if not selection_path.exists():
        raise TestSetError("final selection evidence is missing")
    validate_bundle(bundle)
    validate_selection(bundle)
    pool_a = {record.question_id: record for record in bundle.pool_a}
    pool_b = {record.question_id: record for record in bundle.pool_b}
    reviews = {
        question_id: tuple(
            review.reviewer_id for review in bundle.reviews if review.question_id == question_id
        )
        for question_id in pool_a
    }
    live_by_id = {record.question_id: record for record in evidence.records}
    final_rows: list[dict[str, Any]] = []
    for selection in bundle.selections:
        question_id = selection.question_id
        source = pool_a[question_id]
        gold = pool_b[question_id]
        live = live_by_id.get(question_id)
        if live is None:
            raise TestSetError(f"live evidence missing {question_id}")
        expected_sha = hashlib.sha256(gold.sql.encode()).hexdigest()
        if live.sql_sha256 != expected_sha:
            raise TestSetError(f"live evidence SQL hash mismatch for {question_id}")
        final_rows.append(
            {
                "ambiguity_flag": gold.ambiguity_flag,
                "categories": list(selection.categories),
                "cq_ids": [],
                "difficulty": selection.final_difficulty,
                "evidence_sha256": live.sql_sha256,
                "expected_result_size": live.row_count,
                "id": question_id,
                "nl": source.nl,
                "pool_b_writer": gold.writer_id,
                "pool_c_reviewers": list(reviews[question_id]),
                "schema_elements": [],
                "source": source.author_id,
                "sql": gold.sql,
                "verified_at": evidence.generated_at,
                "verified_executable": True,
            }
        )
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in final_rows).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output_path, payload)
    return FinalizationReport(
        status="generated",
        record_count=len(final_rows),
        output_sha256=hashlib.sha256(payload).hexdigest(),
    )
