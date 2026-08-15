#!/usr/bin/env python
"""Orchestrate the offline and live T3.5 three-pool workflow."""

from __future__ import annotations

import json
from pathlib import Path

import click
from google.cloud import bigquery

from nl2sparql.dataset.testset.artifacts import (
    finalize_bundle,
    write_report,
    write_scaffold,
)
from nl2sparql.dataset.testset.contracts import FinalCase, TestSetError, TestSetPaths
from nl2sparql.dataset.testset.live import LiveEvidence, LiveEvidenceRecord, verify_sql
from nl2sparql.dataset.testset.validate import load_bundle, validate_bundle, validate_selection

DEFAULT_ROOT = Path("data/dataset/test")


@click.group()
def main() -> None:
    """Validate and finalize the independent GoogleSQL test set."""


@main.command()
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_ROOT, show_default=True)
@click.option("--force", is_flag=True, help="Overwrite non-empty scaffold files.")
def scaffold(root: Path, force: bool) -> None:
    """Create CSV headers and human handoff documents."""
    try:
        report = write_scaffold(root, force=force)
        click.echo(json.dumps({"status": "ready", "created_count": report.created_count}))
    except TestSetError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_ROOT, show_default=True)
def validate(root: Path) -> None:
    """Run all credential-free bundle and review checks."""
    try:
        paths = TestSetPaths.from_root(root)
        bundle = load_bundle(paths)
        report = validate_bundle(bundle)
        validate_selection(bundle)
        write_report(report, paths.report_json)
        click.echo(json.dumps({"status": "ready", "report": str(paths.report_json)}))
    except (OSError, ValueError, TestSetError) as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("verify-live")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_ROOT, show_default=True)
@click.option("--project", default="nl2sparql-thesis", show_default=True)
def verify_live(root: Path, project: str) -> None:
    """Verify accepted SQL with BigQuery dry-run and execution evidence."""
    try:
        paths = TestSetPaths.from_root(root)
        bundle = load_bundle(paths)
        validate_bundle(bundle)
        validate_selection(bundle)
        client = bigquery.Client(project=project)
        cases = tuple(
            # Live verification only needs the fields populated by Pool B and
            # the final selection; finalization enriches the remaining fields.
            FinalCase(
                id=selection.question_id,
                source=next(
                    row.author_id
                    for row in bundle.pool_a
                    if row.question_id == selection.question_id
                ),
                nl=next(
                    row.nl for row in bundle.pool_a if row.question_id == selection.question_id
                ),
                sql=next(
                    row.sql for row in bundle.pool_b if row.question_id == selection.question_id
                ),
                difficulty=selection.final_difficulty,
                categories=selection.categories,
                schema_elements=(),
                cq_ids=(),
                expected_result_size=1,
                expected_columns=(),
                ambiguity_flag=False,
                pool_b_writer="unknown",
                pool_c_reviewers=(),
                verified_executable=False,
                verified_at=None,
                evidence_sha256=None,
            )
            for selection in bundle.selections
        )
        evidence = verify_sql(client, cases)
        write_report(evidence, paths.live_evidence)
        click.echo(json.dumps({"status": "ready", "evidence": str(paths.live_evidence)}))
    except (OSError, ValueError, TestSetError) as exc:
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_ROOT, show_default=True)
def finalize(root: Path) -> None:
    """Publish the final JSONL only from validated bundle and live evidence."""
    try:
        paths = TestSetPaths.from_root(root)
        bundle = load_bundle(paths)
        raw = json.loads(paths.live_evidence.read_text(encoding="utf-8"))
        evidence = LiveEvidence(
            status=raw["status"],
            generated_at=raw["generated_at"],
            records=tuple(LiveEvidenceRecord(**record) for record in raw["records"]),
            total_processed_bytes=int(raw["total_processed_bytes"]),
            total_billed_bytes=int(raw["total_billed_bytes"]),
            input_sha256=raw["input_sha256"],
        )
        report = finalize_bundle(bundle, evidence, paths.final_selection, paths.final_jsonl)
        click.echo(json.dumps({"status": report.status, "records": report.record_count}))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, TestSetError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
