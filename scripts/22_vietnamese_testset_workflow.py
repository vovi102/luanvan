#!/usr/bin/env python
"""Offline-first workflow for the paired Vietnamese T3.5 benchmark."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.live import (
    reuse_paired_live_evidence,
    verify_sql,
)
from nl2sparql.dataset.testset.paired import (
    EnglishPairCase,
    PairedCandidate,
    PairedFinalCase,
    PairedManifest,
    PairedReviewDecision,
    build_paired_manifest,
    derive_unaccented_cases,
    finalize_paired_cases,
    validate_paired_manifest,
    validate_pairing,
)
from nl2sparql.dataset.testset.reviewed_artifacts import read_reviewed_live_evidence
from nl2sparql.dataset.testset.reviewed_contracts import load_reviewed_selections

DEFAULT_ENGLISH = Path("data/dataset/test/test-100.jsonl")
DEFAULT_ENGLISH_EVIDENCE = Path("data/dataset/test/live-evidence.json")
DEFAULT_ENGLISH_SELECTION = Path(
    "data/review_drafts/t3_5_candidate_set_2026-09-27/final_selection.csv"
)
DEFAULT_DRAFT = Path("data/review_drafts/t3_5_vi_candidate_set_2026-10-04")
DEFAULT_FINAL = Path("data/dataset/test")


def create_bigquery_client(project: str):
    """Create BigQuery only at the explicitly authorized live boundary."""
    from google.cloud import bigquery

    return bigquery.Client(project=project)


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TestSetError(f"unable to read {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TestSetError(f"{path}:{line_number} contains a blank line")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TestSetError(f"{path}:{line_number} is invalid JSON") from exc
        if not isinstance(row, dict):
            raise TestSetError(f"{path}:{line_number} must be a JSON object")
        rows.append(row)
    return tuple(rows)


def _tuple(row: dict[str, Any], field: str) -> tuple[str, ...]:
    value = row.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TestSetError(f"{field} must be a string array")
    return tuple(value)


def _load_english(
    benchmark_path: Path,
    evidence_path: Path,
    selection_path: Path = DEFAULT_ENGLISH_SELECTION,
) -> tuple[tuple[EnglishPairCase, ...], object]:
    reviewed = read_reviewed_live_evidence(evidence_path)
    evidence_by_id = {record.question_id: record for record in reviewed.execution.records}
    selections = load_reviewed_selections(selection_path)
    selection_by_id = {selection.question_id: selection for selection in selections}
    if len(selections) != 100 or len(selection_by_id) != 100:
        raise TestSetError("English final selection must contain 100 unique rows")
    cases: list[EnglishPairCase] = []
    for row in _read_jsonl(benchmark_path):
        case_id = str(row.get("id", ""))
        evidence = evidence_by_id.get(case_id)
        selection = selection_by_id.get(case_id)
        if evidence is None or selection is None:
            raise TestSetError(f"missing English provenance for {case_id}")
        expected_metadata = {
            "difficulty": selection.final_difficulty,
            "categories": selection.categories,
            "schema_elements": selection.schema_elements,
            "cq_ids": selection.cq_ids,
        }
        for field, expected in expected_metadata.items():
            observed = row.get(field)
            if isinstance(observed, list):
                observed = tuple(observed)
            if observed != expected:
                raise TestSetError(f"English {field} differs from the bound final selection")
        cases.append(
            EnglishPairCase(
                id=case_id,
                question=str(row.get("nl", "")),
                sql=str(row.get("sql", "")),
                expected_columns=evidence.columns,
                expected_result_size=row.get("expected_result_size"),
                difficulty=str(row.get("difficulty", "")),
                categories=_tuple(row, "categories"),
                entity_kinds=selection.entity_kinds,
                schema_elements=_tuple(row, "schema_elements"),
                cq_ids=_tuple(row, "cq_ids"),
            )
        )
    return tuple(cases), reviewed


def _load_candidates(path: Path) -> tuple[PairedCandidate, ...]:
    return tuple(PairedCandidate.from_mapping(row) for row in _read_jsonl(path))


def _load_decisions(path: Path) -> tuple[PairedReviewDecision, ...]:
    return tuple(PairedReviewDecision.from_mapping(row) for row in _read_jsonl(path))


def _load_final(path: Path) -> tuple[PairedFinalCase, ...]:
    cases: list[PairedFinalCase] = []
    tuple_fields = {
        "expected_columns",
        "categories",
        "entity_kinds",
        "schema_elements",
        "cq_ids",
    }
    for row in _read_jsonl(path):
        converted = {
            key: tuple(value) if key in tuple_fields and isinstance(value, list) else value
            for key, value in row.items()
        }
        try:
            cases.append(PairedFinalCase(**converted))
        except TypeError as exc:
            raise TestSetError(f"paired final case schema mismatch: {exc}") from exc
    return tuple(cases)


def _manifest(path: Path) -> PairedManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError
        return PairedManifest(**value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise TestSetError(f"unable to read paired manifest {path}") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise TestSetError(f"refusing to overwrite byte-different artifact {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _write_cases(cases: tuple[PairedFinalCase, ...], path: Path) -> None:
    payload = b"".join((json.dumps(asdict(case), sort_keys=True) + "\n").encode() for case in cases)
    _atomic_write(path, payload)


def _write_manifest(manifest: PairedManifest, path: Path) -> None:
    _atomic_write(path, (json.dumps(asdict(manifest), sort_keys=True) + "\n").encode())


def _common_inputs(function: Callable[..., Any]) -> Callable[..., Any]:
    options = (
        click.option("--english", type=click.Path(path_type=Path), default=DEFAULT_ENGLISH),
        click.option(
            "--english-live-evidence",
            type=click.Path(path_type=Path),
            default=DEFAULT_ENGLISH_EVIDENCE,
        ),
        click.option(
            "--candidates",
            type=click.Path(path_type=Path),
            default=DEFAULT_DRAFT / "candidates.jsonl",
        ),
    )
    for option in reversed(options):
        function = option(function)
    return function


@click.group()
def main() -> None:
    """Build and validate the paired Vietnamese benchmark without implicit network use."""


@main.command("draft")
@_common_inputs
@click.option(
    "--review-events",
    type=click.Path(path_type=Path),
    default=DEFAULT_DRAFT / "review_events.jsonl",
)
def draft(
    english: Path,
    english_live_evidence: Path,
    candidates: Path,
    review_events: Path,
) -> None:
    """Validate an agent-authored draft and create an empty human review file."""
    source, _reviewed = _load_english(english, english_live_evidence)
    report = validate_pairing(source, _load_candidates(candidates))
    _atomic_write(review_events, b"")
    click.echo(json.dumps({"status": report.status, "pair_count": report.pair_count}))


@main.command("validate-draft")
@_common_inputs
def validate_draft(english: Path, english_live_evidence: Path, candidates: Path) -> None:
    """Validate all draft pairing and provenance constraints offline."""
    source, _reviewed = _load_english(english, english_live_evidence)
    report = validate_pairing(source, _load_candidates(candidates))
    click.echo(json.dumps(asdict(report), sort_keys=True))


@main.command("apply-review")
@_common_inputs
@click.option(
    "--review-events",
    type=click.Path(path_type=Path),
    default=DEFAULT_DRAFT / "review_events.jsonl",
)
@click.option(
    "--output", type=click.Path(path_type=Path), default=DEFAULT_FINAL / "test-100-vi.jsonl"
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_FINAL / "manifest-vi.json",
)
def apply_review(
    english: Path,
    english_live_evidence: Path,
    candidates: Path,
    review_events: Path,
    output: Path,
    manifest_path: Path,
) -> None:
    """Apply append-only user review events and finalize only at 100 accepts."""
    source, _reviewed = _load_english(english, english_live_evidence)
    final = finalize_paired_cases(
        source, _load_candidates(candidates), _load_decisions(review_events)
    )
    benchmark_sha256 = __import__("hashlib").sha256(english.read_bytes()).hexdigest()
    manifest = build_paired_manifest(final, english_benchmark_sha256=benchmark_sha256)
    _write_cases(final, output)
    _write_manifest(manifest, manifest_path)
    click.echo(json.dumps({"status": "finalized", "record_count": len(final)}))


@main.command("derive-unaccented")
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_FINAL / "test-100-vi.jsonl",
)
@click.option(
    "--parent-manifest", type=click.Path(path_type=Path), default=DEFAULT_FINAL / "manifest-vi.json"
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=DEFAULT_FINAL / "test-100-vi-unaccented.jsonl",
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_FINAL / "manifest-vi-unaccented.json",
)
def derive_unaccented(
    input_path: Path,
    parent_manifest: Path,
    output: Path,
    manifest_path: Path,
) -> None:
    """Derive and hash-bind the unaccented slice from accepted Vietnamese."""
    parent = _manifest(parent_manifest)
    final = derive_unaccented_cases(_load_final(input_path))
    manifest = build_paired_manifest(
        final,
        english_benchmark_sha256=parent.english_benchmark_sha256,
        parent_manifest_sha256=parent.manifest_sha256,
    )
    _write_cases(final, output)
    _write_manifest(manifest, manifest_path)
    click.echo(json.dumps({"status": "derived", "record_count": len(final)}))


@main.command("verify-live")
@click.option("--english", type=click.Path(path_type=Path), default=DEFAULT_ENGLISH)
@click.option(
    "--english-live-evidence", type=click.Path(path_type=Path), default=DEFAULT_ENGLISH_EVIDENCE
)
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_FINAL / "test-100-vi.jsonl",
)
@click.option(
    "--output", type=click.Path(path_type=Path), default=DEFAULT_FINAL / "live-evidence-vi.json"
)
@click.option("--allow-bigquery", is_flag=True)
@click.option("--project")
def verify_live(
    english: Path,
    english_live_evidence: Path,
    input_path: Path,
    output: Path,
    allow_bigquery: bool,
    project: str | None,
) -> None:
    """Reuse exact English evidence or explicitly run bounded BigQuery verification."""
    source, reviewed = _load_english(english, english_live_evidence)
    final = _load_final(input_path)
    try:
        evidence = reuse_paired_live_evidence(
            source,
            final,
            reviewed.execution,
            policy=reviewed.policy,
        )
    except TestSetError as exc:
        if not allow_bigquery or not project:
            raise click.ClickException(
                "evidence is not reusable; live verification requires "
                "--allow-bigquery and --project"
            ) from exc
        evidence = verify_sql(create_bigquery_client(project), final, policy=reviewed.policy)
    _atomic_write(output, (json.dumps(asdict(evidence), sort_keys=True) + "\n").encode())
    click.echo(json.dumps({"status": "live_ready", "record_count": len(evidence.records)}))


@main.command("validate-final")
@click.option("--input", "input_path", type=click.Path(path_type=Path), required=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path), required=True)
def validate_final(input_path: Path, manifest_path: Path) -> None:
    """Validate final local content and manifest without credentials or network."""
    cases = _load_final(input_path)
    manifest = _manifest(manifest_path)
    validate_paired_manifest(cases, manifest)
    click.echo(json.dumps({"status": "valid", "record_count": len(cases)}))


if __name__ == "__main__":
    main()
