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
from nl2sparql.sql.label_layer import DEFAULT_LOCATION

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


@click.command()
@click.option("--project", default=DEFAULT_PROJECT, show_default=True)
@click.option("--location", default=DEFAULT_LOCATION, show_default=True)
@click.option("--live", is_flag=True, help="Execute bounded BigQuery witnesses.")
@click.option("--value-pools", type=click.Path(path_type=Path), default=DEFAULT_VALUE_POOLS_PATH)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--stats", "stats_path", type=click.Path(path_type=Path), default=None)
def main(
    project: str,
    location: str,
    live: bool,
    value_pools: Path,
    output_path: Path | None,
    config_path: Path | None,
    stats_path: Path | None,
) -> None:
    """Write v2 outputs only after their candidate or live gates pass."""
    try:
        templates = load_templates()
        pools = load_value_pools(value_pools)
        if live and not has_evidence_backed_live_values(pools):
            raise StageAV2WorkflowError(
                "Live Stage A v2 requires evidence-backed block_number and transaction_hash pools"
            )
        records = generate_stage_a_v2_records(templates, pools)
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
