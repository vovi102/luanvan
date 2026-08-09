#!/usr/bin/env python
"""Generate deterministic or live witness-verified GoogleSQL Stage A artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import click
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.dataset.generate import (
    DEFAULT_OUTPUT_PATH,
    StageAGenerationError,
    generate_stage_a_records,
    load_value_pools,
)
from nl2sparql.dataset.stage_a.artifacts import (
    StageAArtifactError,
    write_stage_a_artifacts,
)
from nl2sparql.dataset.stage_a.verify import (
    StageAVerificationError,
    verify_stage_a,
)
from nl2sparql.dataset.templates import load_templates
from nl2sparql.sql.label_layer import DEFAULT_LOCATION

DEFAULT_PROJECT = "nl2sparql-thesis"
DEFAULT_CONFIG_PATH = DEFAULT_OUTPUT_PATH.with_name("generation-config.json")
DEFAULT_STATS_PATH = DEFAULT_OUTPUT_PATH.with_name("stats.md")


def current_utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@click.command()
@click.option("--project", default=DEFAULT_PROJECT, show_default=True)
@click.option("--location", default=DEFAULT_LOCATION, show_default=True)
@click.option("--live", is_flag=True, help="Execute bounded BigQuery witnesses.")
@click.option("--output", type=click.Path(path_type=Path), default=DEFAULT_OUTPUT_PATH)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_CONFIG_PATH,
)
@click.option("--stats", "stats_path", type=click.Path(path_type=Path), default=DEFAULT_STATS_PATH)
def main(
    project: str,
    location: str,
    live: bool,
    output: Path,
    config_path: Path,
    stats_path: Path,
) -> None:
    """Write all Stage A outputs only after generation and verification pass."""
    try:
        templates = load_templates()
        pools = load_value_pools()
        candidates = generate_stage_a_records(templates, pools)
        report = None
        records = candidates
        if live:
            client = bigquery.Client(project=project, location=location)
            report = verify_stage_a(
                client,
                candidates,
                templates,
                location=location,
                verified_at=current_utc_timestamp(),
            )
            records = list(report.records)
        artifacts = write_stage_a_artifacts(
            records,
            templates,
            pools,
            output_path=output,
            config_path=config_path,
            stats_path=stats_path,
            report=report,
        )
        payload = {
            "mode": artifacts.config["verification_mode"],
            "record_count": len(records),
            "artifact_sha256": artifacts.artifact_sha256,
            "output": str(output),
            "config": str(config_path),
            "stats": str(stats_path),
        }
        if report is not None:
            payload.update(
                witness_count=len(report.witnesses),
                total_estimated_bytes=report.preflight.total_estimated_bytes,
                all_passed=report.all_passed,
            )
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    except (
        DefaultCredentialsError,
        GoogleAPICallError,
        StageAGenerationError,
        StageAArtifactError,
        StageAVerificationError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
