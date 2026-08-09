#!/usr/bin/env python
"""Validate T3.1 GoogleSQL templates offline, by dry run, or by execution."""

from __future__ import annotations

import json
from dataclasses import asdict

import click
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.dataset.templates.validate import (
    PER_TEMPLATE_BYTES_CAP,
    TOTAL_TEMPLATE_BYTES_CAP,
    TemplateValidationError,
    dry_run_templates,
    execute_templates,
    validate_template_library,
)
from nl2sparql.sql.label_layer import DEFAULT_LOCATION

DEFAULT_PROJECT = "nl2sparql-thesis"


@click.command()
@click.option("--project", default=DEFAULT_PROJECT, show_default=True)
@click.option("--location", default=DEFAULT_LOCATION, show_default=True)
@click.option(
    "--live",
    is_flag=True,
    help="Compile every rendered template with a BigQuery dry run.",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Execute each template after complete and immediate dry-run checks.",
)
def main(project: str, location: str, live: bool, execute: bool) -> None:
    """Print deterministic JSON; default mode is offline and credential-free."""
    try:
        if not live and not execute:
            summary = validate_template_library()
            payload = {"mode": "offline", **asdict(summary)}
        else:
            client = bigquery.Client(project=project, location=location)
            if execute:
                report = execute_templates(client, location=location)
                payload = {
                    "mode": "execute",
                    "project": project,
                    "location": location,
                    "per_template_bytes_cap": PER_TEMPLATE_BYTES_CAP,
                    "total_bytes_cap": TOTAL_TEMPLATE_BYTES_CAP,
                    "total_estimated_bytes": report.preflight.total_estimated_bytes,
                    "all_passed": report.all_passed,
                    "templates": [asdict(template) for template in report.preflight.templates],
                    "results": [asdict(result) for result in report.results],
                }
            else:
                preflight = dry_run_templates(client, location=location)
                payload = {
                    "mode": "dry-run",
                    "project": project,
                    "location": location,
                    "per_template_bytes_cap": PER_TEMPLATE_BYTES_CAP,
                    "total_bytes_cap": TOTAL_TEMPLATE_BYTES_CAP,
                    "total_estimated_bytes": preflight.total_estimated_bytes,
                    "templates": [asdict(template) for template in preflight.templates],
                }
        click.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
    except (DefaultCredentialsError, GoogleAPICallError, TemplateValidationError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
