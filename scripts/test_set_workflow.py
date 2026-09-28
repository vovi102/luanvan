#!/usr/bin/env python
"""Orchestrate historical three-pool and active reviewed T3.5 workflows."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click
from google.api_core.exceptions import BadRequest, GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.dataset.testset.artifacts import (
    finalize_bundle,
    read_report,
    write_report,
    write_reports,
    write_scaffold,
)
from nl2sparql.dataset.testset.contracts import FinalCase, TestSetError, TestSetPaths
from nl2sparql.dataset.testset.live import LiveEvidence, LiveEvidenceRecord, SqlPolicy, verify_sql
from nl2sparql.dataset.testset.reviewed_artifacts import (
    LIMITATIONS,
    bind_reviewed_live_evidence,
    build_live_cases,
    finalize_reviewed_bundle,
    read_reviewed_live_evidence,
    write_review_scaffold,
    write_reviewed_live_evidence,
)
from nl2sparql.dataset.testset.reviewed_contracts import ReviewedTestSetPaths
from nl2sparql.dataset.testset.reviewed_validate import (
    load_reviewed_bundle,
    resolve_review_state,
    validate_candidate_pack,
    validate_reviewed_selection,
)
from nl2sparql.dataset.testset.validate import (
    Bundle,
    load_bundle,
    validate_bundle,
    validate_selection,
)

DEFAULT_ROOT = Path("data/dataset/test")
DEFAULT_REVIEWED_DRAFT_ROOT = Path("data/review_drafts/t3_5_candidate_set_2026-09-27")
DEFAULT_REVIEWED_FINAL_ROOT = Path("data/dataset/test")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPOSITORY_ROOT / "src/nl2sparql/sql/catalog/ethereum_analytics.json"
CATALOG_REPORT_PATH = Path("src/nl2sparql/sql/catalog/ethereum_analytics.json")
REVIEWED_POLICY = SqlPolicy(
    per_query_bytes=20 * 2**30,
    total_bytes=64 * 2**30,
    location="US",
)


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
            schema_elements=selection.schema_elements,
            cq_ids=selection.cq_ids,
            expected_result_size=(None if pool_b[selection.question_id].expected_empty else 1),
            expected_columns=pool_b[selection.question_id].expected_columns,
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


@main.group()
def reviewed() -> None:
    """Run the agent-authored, human-reviewed T3.5 workflow."""


def _reviewed_paths(draft_root: Path, final_root: Path) -> ReviewedTestSetPaths:
    return ReviewedTestSetPaths.from_roots(draft_root, final_root)


def _reviewed_inputs(paths: ReviewedTestSetPaths) -> tuple[Path, ...]:
    return (paths.candidates, paths.review_events, paths.final_selection)


def _reviewed_failure(
    paths: ReviewedTestSetPaths,
    *,
    command: str,
    status: str,
    error: Exception,
) -> None:
    write_report(
        {"status": status, "command": command, "reason": str(error)},
        paths.validation_report,
        input_paths=_reviewed_inputs(paths),
        policy=REVIEWED_POLICY,
    )


def _incomplete_review(error: Exception) -> bool:
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "human review",
            "requires at least one",
            "requires exactly 100",
            "missing required input",
            "unable to read",
        )
    )


def _candidate_payload(report: object) -> dict[str, object]:
    payload = asdict(report)  # type: ignore[arg-type]
    payload["limitations"] = list(LIMITATIONS)
    return payload


def _draft_root_option(function):
    return click.option(
        "--draft-root",
        type=click.Path(path_type=Path),
        default=DEFAULT_REVIEWED_DRAFT_ROOT,
        show_default=True,
    )(function)


def _final_root_option(function):
    return click.option(
        "--final-root",
        type=click.Path(path_type=Path),
        default=DEFAULT_REVIEWED_FINAL_ROOT,
        show_default=True,
    )(function)


@reviewed.command("scaffold")
@_draft_root_option
@_final_root_option
def reviewed_scaffold(draft_root: Path, final_root: Path) -> None:
    """Create only the human review headers and review guide."""
    paths = _reviewed_paths(draft_root, final_root)
    try:
        created = write_review_scaffold(paths)
        click.echo(json.dumps({"status": "ready", "created_count": len(created)}))
    except TestSetError as exc:
        raise click.ClickException(str(exc)) from exc


@reviewed.command("validate-candidates")
@_draft_root_option
@_final_root_option
@click.option("--check-only", is_flag=True, help="Validate without writing reports.")
def reviewed_validate_candidates(
    draft_root: Path,
    final_root: Path,
    check_only: bool,
) -> None:
    """Validate the complete 120-case candidate source without credentials."""
    paths = _reviewed_paths(draft_root, final_root)
    try:
        report = validate_candidate_pack(
            paths.candidates,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        payload = _candidate_payload(report)
        if not check_only:
            write_reports(
                payload,
                (paths.validation_report, paths.candidate_manifest),
                input_paths=(paths.candidates, CATALOG_REPORT_PATH),
                policy=REVIEWED_POLICY,
            )
        click.echo(json.dumps({"status": report.status, "candidate_count": 120}))
    except OSError as exc:
        if not check_only:
            _reviewed_failure(paths, command="validate-candidates", status="blocked", error=exc)
        raise click.ClickException(str(exc)) from exc
    except (ValueError, TestSetError) as exc:
        if not check_only:
            _reviewed_failure(paths, command="validate-candidates", status="failed", error=exc)
        raise click.ClickException(str(exc)) from exc


@reviewed.command("validate-review")
@_draft_root_option
@_final_root_option
def reviewed_validate_review(draft_root: Path, final_root: Path) -> None:
    """Validate explicit human decisions and the final 100-case selection."""
    paths = _reviewed_paths(draft_root, final_root)
    try:
        validate_candidate_pack(
            paths.candidates,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        bundle = load_reviewed_bundle(paths)
        report = validate_reviewed_selection(
            bundle,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        write_report(
            report,
            paths.validation_report,
            input_paths=_reviewed_inputs(paths),
            policy=REVIEWED_POLICY,
        )
        click.echo(json.dumps({"status": report.status, "selected_count": 100}))
    except (OSError, ValueError, TestSetError) as exc:
        status = "blocked" if isinstance(exc, OSError) or _incomplete_review(exc) else "failed"
        _reviewed_failure(paths, command="validate-review", status=status, error=exc)
        raise click.ClickException(str(exc)) from exc


@reviewed.command("verify-live")
@_draft_root_option
@_final_root_option
@click.option("--allow-bigquery", is_flag=True, help="Explicitly authorize live BigQuery use.")
@click.option("--project", help="Explicit Google Cloud project for live verification.")
def reviewed_verify_live(
    draft_root: Path,
    final_root: Path,
    allow_bigquery: bool,
    project: str | None,
) -> None:
    """Verify a review-ready selection with bounded live BigQuery execution."""
    paths = _reviewed_paths(draft_root, final_root)
    if not allow_bigquery:
        error = TestSetError("live verification requires --allow-bigquery")
        _reviewed_failure(paths, command="verify-live", status="blocked", error=error)
        raise click.ClickException(str(error))
    if not project:
        error = TestSetError("live verification requires an explicit --project")
        _reviewed_failure(paths, command="verify-live", status="blocked", error=error)
        raise click.ClickException(str(error))
    try:
        validate_candidate_pack(
            paths.candidates,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        bundle = load_reviewed_bundle(paths)
        review_report = validate_reviewed_selection(
            bundle,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        accepted = resolve_review_state(
            bundle,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        cases = build_live_cases(bundle, accepted)
        client = bigquery.Client(project=project)
        execution = verify_sql(client, cases, policy=REVIEWED_POLICY)
        evidence = bind_reviewed_live_evidence(
            review_report,
            execution,
            project=project,
            policy=REVIEWED_POLICY,
        )
        write_reviewed_live_evidence(evidence, paths.live_evidence)
        click.echo(json.dumps({"status": "live_ready", "records": len(cases)}))
    except BadRequest as exc:
        _reviewed_failure(paths, command="verify-live", status="failed", error=exc)
        raise click.ClickException(str(exc)) from exc
    except (DefaultCredentialsError, GoogleAPIError, OSError) as exc:
        _reviewed_failure(paths, command="verify-live", status="blocked", error=exc)
        raise click.ClickException(str(exc)) from exc
    except (ValueError, TestSetError) as exc:
        status = "blocked" if _incomplete_review(exc) else "failed"
        _reviewed_failure(paths, command="verify-live", status=status, error=exc)
        raise click.ClickException(str(exc)) from exc


@reviewed.command("finalize")
@_draft_root_option
@_final_root_option
def reviewed_finalize(draft_root: Path, final_root: Path) -> None:
    """Publish immutable final artifacts from review and current live evidence."""
    paths = _reviewed_paths(draft_root, final_root)
    try:
        if not paths.live_evidence.is_file():
            raise FileNotFoundError(f"missing reviewed live evidence: {paths.live_evidence}")
        validate_candidate_pack(
            paths.candidates,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        bundle = load_reviewed_bundle(paths)
        evidence = read_reviewed_live_evidence(paths.live_evidence)
        report = finalize_reviewed_bundle(
            bundle,
            evidence,
            output_path=paths.final_jsonl,
            manifest_path=paths.final_manifest,
            repo_root=REPOSITORY_ROOT,
            catalog_path=CATALOG_PATH,
        )
        click.echo(json.dumps({"status": report.status, "records": report.record_count}))
    except OSError as exc:
        _reviewed_failure(paths, command="finalize", status="blocked", error=exc)
        raise click.ClickException(str(exc)) from exc
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, TestSetError) as exc:
        _reviewed_failure(paths, command="finalize", status="failed", error=exc)
        raise click.ClickException(str(exc)) from exc


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
    except BadRequest as exc:
        _failure_report(
            paths.live_evidence,
            command="verify-live",
            status="failed",
            error=exc,
            input_paths=_input_paths(paths),
        )
        raise click.ClickException(str(exc)) from exc
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
