"""Scaffold, report, and final artifact publication for the test set."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nl2sparql.dataset.testset.contracts import SelectionRecord, TestSetError, load_csv
from nl2sparql.dataset.testset.live import (
    LiveEvidence,
    SqlPolicy,
    evidence_input_sha256,
)
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
    "sql_pool_b.csv": (
        "question_id,writer_id,sql,expected_columns,expected_empty,ambiguity_flag,notes\n"
    ),
    "review_pool_c.csv": (
        "question_id,reviewer_id,nl_quality,faithfulness,difficulty,decision,notes\n"
    ),
    "final_selection.csv": (
        "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,"
        "selection_note\n"
    ),
}
_PROCESS = """# T3.5 three-pool collection process

Pool A authors write natural English questions without seeing the schema. Pool B
authors independently write read-only GoogleSQL, list ordered result aliases in
`expected_columns` using `|`, and record ambiguity. Pool C reviewers score
quality, faithfulness, difficulty, and decision. Use pseudonyms only; keep
consent records separate from benchmark rows.

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


_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git_provenance() -> tuple[str, bool]:
    repository = Path(__file__).resolve().parents[4]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False
    return revision.stdout.strip() or "unknown", bool(status.stdout.strip())


def _input_digests(paths: tuple[Path, ...]) -> dict[str, str | None]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        for path in paths
    }


def write_report(
    report: Mapping[str, Any] | object,
    path: Path,
    *,
    input_paths: tuple[Path, ...] = (),
    policy: SqlPolicy | None = None,
) -> None:
    """Atomically write canonical report data and provenance metadata."""
    if is_dataclass(report):
        payload = asdict(report)
    elif isinstance(report, Mapping):
        payload = dict(report)
    else:
        raise TestSetError("report must be a dataclass or mapping")
    policy = SqlPolicy() if policy is None else policy
    payload.setdefault("status", "ready")
    payload.setdefault("generated_at", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    git_commit, git_worktree_dirty = _git_provenance()
    if payload["status"] == "ready" and not _GIT_SHA_RE.fullmatch(git_commit):
        raise TestSetError("ready report requires a valid full lowercase git commit SHA")
    body = {
        **payload,
        "schema_version": 1,
        "git_commit": git_commit,
        "git_worktree_dirty": git_worktree_dirty,
        "input_digests": _input_digests(input_paths),
        "policy_caps": asdict(policy),
    }
    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    output = {**body, "report_sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, _canonical_json(output))


def read_report(path: Path) -> dict[str, Any]:
    """Read a canonical report only when its embedded digest is intact."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TestSetError(f"unable to read report {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TestSetError(f"report {path} must contain a JSON object")
    payload = dict(raw)
    supplied = payload.pop("report_sha256", None)
    expected = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        raise TestSetError(f"report digest mismatch for {path}")
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _selection_rows(path: Path) -> tuple[SelectionRecord, ...]:
    rows = load_csv(
        path,
        (
            "question_id",
            "final_difficulty",
            "categories",
            "entity_kinds",
            "schema_elements",
            "cq_ids",
            "selection_note",
        ),
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


def finalize_bundle(
    bundle: Bundle,
    evidence: LiveEvidence | None,
    selection_path: Path,
    output_path: Path,
) -> FinalizationReport:
    """Publish exactly 100 SQL-native cases only after every gate passes."""
    if evidence is None:
        raise TestSetError("live evidence is required before finalization")
    if evidence.status != "ready":
        raise TestSetError("live evidence must have ready status before finalization")
    try:
        generated_at = datetime.fromisoformat(evidence.generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TestSetError("live evidence generated_at must be a valid UTC timestamp") from exc
    if not evidence.generated_at.endswith("Z") or generated_at.utcoffset() != timedelta(0):
        raise TestSetError("live evidence generated_at must be a valid UTC timestamp")
    if not selection_path.exists():
        raise TestSetError("final selection evidence is missing")
    if _selection_rows(selection_path) != bundle.selections:
        raise TestSetError("final selection file does not match the validated bundle")
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
    evidence_ids = tuple(record.question_id for record in evidence.records)
    selected_ids = tuple(selection.question_id for selection in bundle.selections)
    if len(evidence_ids) != len(set(evidence_ids)):
        raise TestSetError("live evidence contains duplicate question IDs")
    if set(evidence_ids) != set(selected_ids):
        raise TestSetError("live evidence IDs must exactly match the final selection")
    policy = SqlPolicy()
    if evidence.total_processed_bytes != sum(row.processed_bytes for row in evidence.records):
        raise TestSetError("live evidence processed-byte total is inconsistent")
    if evidence.total_billed_bytes != sum(row.billed_bytes for row in evidence.records):
        raise TestSetError("live evidence billed-byte total is inconsistent")
    if (
        evidence.total_processed_bytes < 0
        or evidence.total_billed_bytes < 0
        or evidence.total_processed_bytes > policy.total_bytes
        or evidence.total_billed_bytes > policy.total_bytes
    ):
        raise TestSetError("live evidence exceeds the aggregate byte policy")
    if any(
        record.cache_hit
        or record.row_count < 0
        or record.processed_bytes < 0
        or record.billed_bytes < 0
        or record.wall_latency_ms < 0
        or record.processed_bytes > policy.per_query_bytes
        or record.billed_bytes > policy.per_query_bytes
        or not record.job_id
        for record in evidence.records
    ):
        raise TestSetError("live evidence violates the per-query execution policy")
    expected_input_sha256 = evidence_input_sha256(
        (record.question_id, record.sql_sha256) for record in evidence.records
    )
    if evidence.input_sha256 != expected_input_sha256:
        raise TestSetError("live evidence input hash mismatch")
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
        if tuple(live.columns) != gold.expected_columns:
            raise TestSetError(f"live evidence columns mismatch for {question_id}")
        if gold.expected_empty and live.row_count != 0:
            raise TestSetError(f"live evidence row policy mismatch for {question_id}")
        if not gold.expected_empty and live.row_count <= 0:
            raise TestSetError(f"live evidence row policy mismatch for {question_id}")
        final_rows.append(
            {
                "ambiguity_flag": gold.ambiguity_flag,
                "categories": list(selection.categories),
                "cq_ids": list(selection.cq_ids),
                "difficulty": selection.final_difficulty,
                "evidence_sha256": live.sql_sha256,
                "expected_result_size": live.row_count,
                "id": question_id,
                "nl": source.nl,
                "pool_b_writer": gold.writer_id,
                "pool_c_reviewers": list(reviews[question_id]),
                "schema_elements": list(selection.schema_elements),
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
        status="ready",
        record_count=len(final_rows),
        output_sha256=hashlib.sha256(payload).hexdigest(),
    )
