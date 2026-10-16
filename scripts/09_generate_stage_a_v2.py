#!/usr/bin/env python
"""Generate offline candidates or live-accepted Stage A v2 artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from nl2sparql.dataset.generate import DEFAULT_VALUE_POOLS_PATH, load_value_pools
from nl2sparql.dataset.stage_a.diagnostics import (
    DiagnosticError,
    DiagnosticRecorder,
    require_unbilled_project,
    validate_diagnostic_report,
    write_diagnostic_report,
)
from nl2sparql.dataset.stage_a.v2_artifacts import (
    DEFAULT_V2_ACCEPTED_CONFIG_PATH,
    DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
    DEFAULT_V2_ACCEPTED_STATS_PATH,
    DEFAULT_V2_CANDIDATE_CONFIG_PATH,
    DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
    DEFAULT_V2_CANDIDATE_STATS_PATH,
    StageAV2ArtifactError,
    has_evidence_backed_live_values,
    write_stage_a_v2_accepted_artifacts,
    write_stage_a_v2_candidate_artifacts,
)
from nl2sparql.dataset.stage_a_v2 import (
    StageAV2GenerationError,
    generate_stage_a_v2_records,
)
from nl2sparql.dataset.templates import load_templates
from nl2sparql.sql.constants import DEFAULT_LOCATION

DEFAULT_PROJECT = "nl2sparql-thesis"
DEFAULT_DIAGNOSTIC_REPORT_PATH = Path("docs/evidence/stage-a-v2-account-pair-diagnostic.json")


class StageAV2WorkflowError(ValueError):
    """Raised when the v2 workflow cannot produce truthful evidence."""


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _run_live(
    records: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    pools: dict[str, Any],
    *,
    project: str,
    location: str,
    output_path: Path,
    config_path: Path,
    stats_path: Path,
    billing_runner=None,
):
    try:
        if billing_runner is None:
            require_unbilled_project(project)
        else:
            require_unbilled_project(project, runner=billing_runner)
    except DiagnosticError as exc:
        raise StageAV2WorkflowError(str(exc)) from exc

    from google.api_core.exceptions import GoogleAPICallError
    from google.auth.exceptions import DefaultCredentialsError
    from google.cloud import bigquery

    from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries
    from nl2sparql.dataset.stage_a.verify import StageAVerificationError, verify_stage_a
    from nl2sparql.dataset.stage_a_v2 import validate_stage_a_v2_records

    try:
        client = bigquery.Client(project=project, location=location)
        report = verify_stage_a(
            client,
            records,
            templates,
            verified_at=_timestamp(),
            location=location,
            record_validator=validate_stage_a_v2_records,
            query_planner=build_stage_a_v2_witness_queries,
        )
        return write_stage_a_v2_accepted_artifacts(
            report,
            templates,
            pools,
            output_path=output_path,
            config_path=config_path,
            stats_path=stats_path,
        )
    except (DefaultCredentialsError, GoogleAPICallError, StageAVerificationError) as exc:
        raise StageAV2WorkflowError(str(exc)) from exc


def _run_diagnostic(
    records: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    *,
    project: str,
    location: str,
    report_path: Path,
    client: Any | None = None,
    billing_runner=None,
) -> dict[str, Any]:
    """Execute witnesses once and publish only diagnostic evidence."""
    verified_at = _timestamp()
    recorder = DiagnosticRecorder(
        project_id=project,
        records=records,
        verified_at=verified_at,
    )
    try:
        state = (
            require_unbilled_project(project)
            if billing_runner is None
            else require_unbilled_project(project, runner=billing_runner)
        )
        recorder.record_billing_state(state)
    except DiagnosticError as exc:
        recorder.record_failure("billing_guard", exc)
        write_diagnostic_report(report_path, recorder.failure_report())
        raise StageAV2WorkflowError(str(exc)) from exc

    try:
        from google.cloud import bigquery

        from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries
        from nl2sparql.dataset.stage_a.verify import verify_stage_a
        from nl2sparql.dataset.stage_a_v2 import validate_stage_a_v2_records

        active_client = client or bigquery.Client(project=project, location=location)
    except Exception as exc:
        recorder.record_failure("provider_initialization", exc)
        write_diagnostic_report(report_path, recorder.failure_report())
        raise StageAV2WorkflowError(str(exc)) from exc

    try:
        verify_stage_a(
            active_client,
            records,
            templates,
            verified_at=verified_at,
            location=location,
            record_validator=validate_stage_a_v2_records,
            query_planner=build_stage_a_v2_witness_queries,
            diagnostic_recorder=recorder,
        )
        report = recorder.complete()
        validate_diagnostic_report(report, records)
    except Exception as exc:
        recorder.record_failure("verification", exc)
        write_diagnostic_report(report_path, recorder.failure_report())
        raise StageAV2WorkflowError(str(exc)) from exc
    write_diagnostic_report(report_path, report)
    return {
        "mode": "diagnostic",
        "status": report["status"],
        **report["summary"],
        "diagnostic_report": str(report_path),
        "acceptance_authorized": False,
    }


def _run_preflight(
    records: list[dict[str, Any]],
    *,
    project: str,
    location: str,
    client: Any | None = None,
) -> dict[str, Any]:
    from google.api_core.exceptions import GoogleAPICallError
    from google.auth.exceptions import DefaultCredentialsError
    from google.cloud import bigquery

    from nl2sparql.dataset.stage_a.evidence import build_witness_groups
    from nl2sparql.dataset.stage_a.planning import build_stage_a_v2_witness_queries
    from nl2sparql.dataset.stage_a.verify import (
        TOTAL_WITNESS_BYTES_CAP,
        StageAVerificationError,
        dry_run_witnesses,
    )
    from nl2sparql.dataset.templates import PER_TEMPLATE_BYTES_CAP

    try:
        active_client = client or bigquery.Client(project=project, location=location)
        preflight = dry_run_witnesses(
            active_client,
            records,
            location=location,
            query_planner=build_stage_a_v2_witness_queries,
        )
    except (DefaultCredentialsError, GoogleAPICallError, StageAVerificationError) as exc:
        raise StageAV2WorkflowError(str(exc)) from exc
    per_template: dict[str, dict[str, int]] = {}
    for item in preflight.witnesses:
        totals = per_template.setdefault(
            item.template_id,
            {"physical_query_count": 0, "estimated_bytes": 0},
        )
        totals["physical_query_count"] += 1
        totals["estimated_bytes"] += item.estimated_bytes
    maximum = max(
        preflight.witnesses,
        key=lambda item: (item.estimated_bytes, item.query_id),
    )
    return {
        "mode": "preflight",
        "logical_witness_count": len(build_witness_groups(records)),
        "physical_query_count": len(preflight.witnesses),
        "total_estimated_bytes": preflight.total_estimated_bytes,
        "per_query_bytes_cap": PER_TEMPLATE_BYTES_CAP,
        "total_bytes_cap": TOTAL_WITNESS_BYTES_CAP,
        "maximum_query": {
            "query_id": maximum.query_id,
            "template_id": maximum.template_id,
            "estimated_bytes": maximum.estimated_bytes,
        },
        "per_template_totals": dict(sorted(per_template.items())),
    }


@click.command()
@click.option("--project", default=DEFAULT_PROJECT, show_default=True)
@click.option("--location", default=DEFAULT_LOCATION, show_default=True)
@click.option("--live", is_flag=True, help="Execute bounded BigQuery witnesses.")
@click.option("--preflight", is_flag=True, help="Dry-run bounded witnesses without writing.")
@click.option("--diagnostic", is_flag=True, help="Execute diagnostic-only witnesses.")
@click.option(
    "--diagnostic-report",
    type=click.Path(path_type=Path),
    default=DEFAULT_DIAGNOSTIC_REPORT_PATH,
    show_default=True,
)
@click.option(
    "--validate-diagnostic-report",
    "validate_diagnostic_report_path",
    type=click.Path(path_type=Path),
    default=None,
)
@click.option("--value-pools", type=click.Path(path_type=Path), default=DEFAULT_VALUE_POOLS_PATH)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--stats", "stats_path", type=click.Path(path_type=Path), default=None)
def main(
    project: str,
    location: str,
    live: bool,
    preflight: bool,
    diagnostic: bool,
    diagnostic_report: Path,
    validate_diagnostic_report_path: Path | None,
    value_pools: Path,
    output_path: Path | None,
    config_path: Path | None,
    stats_path: Path | None,
) -> None:
    """Write v2 outputs only after their candidate or live gates pass."""
    try:
        execution_modes = sum((preflight, live, diagnostic))
        if execution_modes > 1 or (validate_diagnostic_report_path is not None and execution_modes):
            raise StageAV2WorkflowError(
                "--preflight, --live, --diagnostic, and --validate-diagnostic-report "
                "are mutually exclusive"
            )
        templates = load_templates()
        pools = load_value_pools(value_pools)
        if (preflight or live or diagnostic) and not has_evidence_backed_live_values(pools):
            raise StageAV2WorkflowError(
                "Stage A v2 preflight/diagnostic/live requires evidence-backed block_number and "
                "transaction_hash pools plus account_pair relationships"
            )
        records = generate_stage_a_v2_records(templates, pools)
        if validate_diagnostic_report_path is not None:
            try:
                report = json.loads(validate_diagnostic_report_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise StageAV2WorkflowError(
                    f"Cannot read diagnostic report: {validate_diagnostic_report_path}"
                ) from exc
            if not isinstance(report, dict):
                raise StageAV2WorkflowError("Diagnostic report must be a JSON object")
            validate_diagnostic_report(report, records)
            click.echo(
                json.dumps(
                    {
                        "mode": "diagnostic_validation",
                        "status": report["status"],
                        "diagnostic_report": str(validate_diagnostic_report_path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        if preflight:
            click.echo(
                json.dumps(
                    _run_preflight(
                        records,
                        project=project,
                        location=location,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        if diagnostic:
            click.echo(
                json.dumps(
                    _run_diagnostic(
                        records,
                        templates,
                        project=project,
                        location=location,
                        report_path=diagnostic_report,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        if live:
            artifacts = _run_live(
                records,
                templates,
                pools,
                project=project,
                location=location,
                output_path=output_path or DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
                config_path=config_path or DEFAULT_V2_ACCEPTED_CONFIG_PATH,
                stats_path=stats_path or DEFAULT_V2_ACCEPTED_STATS_PATH,
            )
        else:
            artifacts = write_stage_a_v2_candidate_artifacts(
                records,
                templates,
                pools,
                output_path=output_path or DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
                config_path=config_path or DEFAULT_V2_CANDIDATE_CONFIG_PATH,
                stats_path=stats_path or DEFAULT_V2_CANDIDATE_STATS_PATH,
            )
        click.echo(
            json.dumps(
                {
                    "acceptance_eligible": artifacts.manifest["acceptance_eligible"],
                    "artifact_sha256": artifacts.artifact_sha256,
                    "lifecycle_state": artifacts.manifest["lifecycle_state"],
                    "record_count": artifacts.manifest["record_count"],
                    "represented_intent_count": artifacts.manifest["represented_intent_count"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    except (
        DiagnosticError,
        StageAV2ArtifactError,
        StageAV2GenerationError,
        StageAV2WorkflowError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
