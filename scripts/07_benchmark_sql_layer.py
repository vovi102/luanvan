#!/usr/bin/env python
"""Dry-run or execute the T2-SQL-3 live analytical benchmark."""

from __future__ import annotations

import json
from dataclasses import asdict

import click
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.sql.benchmark import (
    TOTAL_BENCHMARK_BYTES_CAP,
    BenchmarkError,
    dry_run_benchmark,
    execute_benchmark,
)
from nl2sparql.sql.label_layer import (
    DEFAULT_LOCATION,
    DEFAULT_MAXIMUM_BYTES_BILLED,
)


@click.command()
@click.option("--project", required=True, help="Google Cloud project and billing context.")
@click.option("--location", default=DEFAULT_LOCATION, show_default=True)
@click.option(
    "--execute",
    is_flag=True,
    help="Execute result queries after the complete dry-run preflight passes.",
)
def main(project: str, location: str, execute: bool) -> None:
    """Print deterministic JSON; default mode performs dry runs only."""
    try:
        client = bigquery.Client(project=project, location=location)
        if execute:
            report = execute_benchmark(client, location=location)
            payload = {
                "mode": "execute",
                "project": project,
                "location": location,
                "window": {"start_date": "2026-05-31", "end_date": "2026-07-01"},
                "per_case_bytes_cap": DEFAULT_MAXIMUM_BYTES_BILLED,
                "total_bytes_cap": TOTAL_BENCHMARK_BYTES_CAP,
                "total_estimated_bytes": report.preflight.total_estimated_bytes,
                "all_passed": report.all_passed,
                "cases": [asdict(case) for case in report.preflight.cases],
                "results": [asdict(result) for result in report.results],
            }
        else:
            preflight = dry_run_benchmark(client, location=location)
            payload = {
                "mode": "dry-run",
                "project": project,
                "location": location,
                "window": {"start_date": "2026-05-31", "end_date": "2026-07-01"},
                "per_case_bytes_cap": DEFAULT_MAXIMUM_BYTES_BILLED,
                "total_bytes_cap": TOTAL_BENCHMARK_BYTES_CAP,
                "total_estimated_bytes": preflight.total_estimated_bytes,
                "cases": [asdict(case) for case in preflight.cases],
            }
        click.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
    except (DefaultCredentialsError, GoogleAPICallError, BenchmarkError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
