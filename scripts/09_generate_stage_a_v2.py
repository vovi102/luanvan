#!/usr/bin/env python
"""Generate offline candidates or live-accepted Stage A v2 artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from nl2sparql.dataset.generate import DEFAULT_VALUE_POOLS_PATH, load_value_pools
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
):
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
@click.option("--value-pools", type=click.Path(path_type=Path), default=DEFAULT_VALUE_POOLS_PATH)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--stats", "stats_path", type=click.Path(path_type=Path), default=None)
def main(
    project: str,
    location: str,
    live: bool,
    preflight: bool,
    value_pools: Path,
    output_path: Path | None,
    config_path: Path | None,
    stats_path: Path | None,
) -> None:
    """Write v2 outputs only after their candidate or live gates pass."""
    try:
        if preflight and live:
            raise StageAV2WorkflowError("--preflight and --live are mutually exclusive")
        templates = load_templates()
        pools = load_value_pools(value_pools)
        if (preflight or live) and not has_evidence_backed_live_values(pools):
            raise StageAV2WorkflowError(
                "Stage A v2 preflight/live requires evidence-backed block_number and "
                "transaction_hash pools"
            )
        records = generate_stage_a_v2_records(templates, pools)
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
    except (StageAV2ArtifactError, StageAV2GenerationError, StageAV2WorkflowError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
