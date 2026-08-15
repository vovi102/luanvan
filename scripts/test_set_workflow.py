#!/usr/bin/env python
"""Orchestrate the offline and live T3.5 three-pool workflow."""

from __future__ import annotations

import json
from pathlib import Path

import click
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.dataset.testset.artifacts import (
    finalize_bundle,
    read_report,
    write_report,
    write_scaffold,
)
from nl2sparql.dataset.testset.contracts import FinalCase, TestSetError, TestSetPaths
from nl2sparql.dataset.testset.live import LiveEvidence, LiveEvidenceRecord, verify_sql
from nl2sparql.dataset.testset.validate import (
    Bundle,
    load_bundle,
    validate_bundle,
    validate_selection,
)

DEFAULT_ROOT = Path("data/dataset/test")


def _input_paths(paths: TestSetPaths) -> tuple[Path, ...]:
    return (
        paths.raw_pool_a,
        paths.sql_pool_b,
        paths.review_pool_c,
        paths.final_selection,
    )


def _require_inputs(paths: TestSetPaths) -> None:
    missing = [path for path in _input_paths(paths) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing required input files: {', '.join(map(str, missing))}")


def _failure_report(
    path: Path,
    *,
    command: str,
    status: str,
    error: Exception,
    input_paths: tuple[Path, ...],
) -> None:
    write_report(
        {
            "status": status,
            "command": command,
            "reason": str(error),
        },
        path,
        input_paths=input_paths,
    )


def _cases_from_bundle(bundle: Bundle) -> tuple[FinalCase, ...]:
    """Build live cases while preserving Pool B's explicit-empty policy."""
    pool_a = {row.question_id: row for row in bundle.pool_a}
    pool_b = {row.question_id: row for row in bundle.pool_b}
    reviewers = {
        question_id: tuple(
            review.reviewer_id for review in bundle.reviews if review.question_id == question_id
        )
        for question_id in pool_a
    }
    return tuple(
        FinalCase(
            id=selection.question_id,
            source=pool_a[selection.question_id].author_id,
            nl=pool_a[selection.question_id].nl,
            sql=pool_b[selection.question_id].sql,
            difficulty=selection.final_difficulty,
            categories=selection.categories,
            schema_elements=(),
            cq_ids=(),
            expected_result_size=(None if pool_b[selection.question_id].expected_empty else 1),
            expected_columns=(),
            ambiguity_flag=pool_b[selection.question_id].ambiguity_flag,
            pool_b_writer=pool_b[selection.question_id].writer_id,
            pool_c_reviewers=reviewers[selection.question_id],
            verified_executable=False,
            verified_at=None,
            evidence_sha256=None,
        )
        for selection in bundle.selections
    )


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
    paths = TestSetPaths.from_root(root)
    try:
        _require_inputs(paths)
        bundle = load_bundle(paths)
        report = validate_bundle(bundle)
        validate_selection(bundle)
        write_report(report, paths.report_json, input_paths=_input_paths(paths))
        click.echo(json.dumps({"status": "ready", "report": str(paths.report_json)}))
    except OSError as exc:
        _failure_report(
            paths.report_json,
            command="validate",
            status="blocked",
            error=exc,
            input_paths=_input_paths(paths),
        )
        raise click.ClickException(str(exc)) from exc
    except (ValueError, TestSetError) as exc:
        _failure_report(
            paths.report_json,
            command="validate",
            status="failed",
            error=exc,
            input_paths=_input_paths(paths),
        )
        raise click.ClickException(str(exc)) from exc


@main.command("verify-live")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_ROOT, show_default=True)
@click.option("--project", default="nl2sparql-thesis", show_default=True)
def verify_live(root: Path, project: str) -> None:
    """Verify accepted SQL with BigQuery dry-run and execution evidence."""
    paths = TestSetPaths.from_root(root)
    try:
        _require_inputs(paths)
        bundle = load_bundle(paths)
        validate_bundle(bundle)
        validate_selection(bundle)
        client = bigquery.Client(project=project)
        cases = _cases_from_bundle(bundle)
        evidence = verify_sql(client, cases)
        write_report(evidence, paths.live_evidence, input_paths=_input_paths(paths))
        click.echo(json.dumps({"status": "ready", "evidence": str(paths.live_evidence)}))
    except (OSError, DefaultCredentialsError, GoogleAPIError) as exc:
        _failure_report(
            paths.live_evidence,
            command="verify-live",
            status="blocked",
            error=exc,
            input_paths=_input_paths(paths),
        )
        raise click.ClickException(str(exc)) from exc
    except (ValueError, TestSetError) as exc:
        _failure_report(
            paths.live_evidence,
            command="verify-live",
            status="failed",
            error=exc,
            input_paths=_input_paths(paths),
        )
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_ROOT, show_default=True)
def finalize(root: Path) -> None:
    """Publish the final JSONL only from validated bundle and live evidence."""
    paths = TestSetPaths.from_root(root)
    try:
        _require_inputs(paths)
        bundle = load_bundle(paths)
        raw = read_report(paths.live_evidence)
        evidence = LiveEvidence(
            status=raw["status"],
            generated_at=raw["generated_at"],
            records=tuple(
                LiveEvidenceRecord(**{**record, "columns": tuple(record["columns"])})
                for record in raw["records"]
            ),
            total_processed_bytes=int(raw["total_processed_bytes"]),
            total_billed_bytes=int(raw["total_billed_bytes"]),
            input_sha256=raw["input_sha256"],
        )
        report = finalize_bundle(bundle, evidence, paths.final_selection, paths.final_jsonl)
        write_report(
            report,
            paths.report_json,
            input_paths=(*_input_paths(paths), paths.live_evidence, paths.final_jsonl),
        )
        click.echo(json.dumps({"status": report.status, "records": report.record_count}))
    except OSError as exc:
        _failure_report(
            paths.report_json,
            command="finalize",
            status="blocked",
            error=exc,
            input_paths=(*_input_paths(paths), paths.live_evidence),
        )
        raise click.ClickException(str(exc)) from exc
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, TestSetError) as exc:
        _failure_report(
            paths.report_json,
            command="finalize",
            status="failed",
            error=exc,
            input_paths=(*_input_paths(paths), paths.live_evidence),
        )
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
