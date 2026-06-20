#!/usr/bin/env python
"""Extract the T1.2 BigQuery Ethereum pilot CSV files."""

from __future__ import annotations

from pathlib import Path

import click
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.kg.extraction.pilot_extract import (
    DEFAULT_OUTPUT_DIR,
    PILOT_DATE,
    estimate_pilot_query_bytes,
    run_pilot_extraction,
)


@click.command()
@click.option(
    "--output-dir",
    default=DEFAULT_OUTPUT_DIR,
    type=click.Path(file_okay=False, path_type=Path),
    show_default=True,
    help="Directory for pilot CSV outputs.",
)
@click.option("--pilot-date", default=PILOT_DATE, show_default=True, help="Date slice to query.")
@click.option("--force", is_flag=True, help="Overwrite existing pilot CSV files.")
@click.option("--dry-run", is_flag=True, help="Estimate bytes processed without exporting CSVs.")
def main(output_dir: Path, pilot_date: str, force: bool, dry_run: bool) -> None:
    """Run dry-run estimates or export the pilot CSV files."""
    try:
        client = bigquery.Client()
    except DefaultCredentialsError as exc:
        raise click.ClickException(f"BigQuery authentication failed: {exc}") from exc

    if dry_run:
        estimates = estimate_pilot_query_bytes(client, pilot_date=pilot_date)
        total_bytes = sum(estimates.values())
        for filename, bytes_processed in estimates.items():
            click.echo(f"{filename}: {bytes_processed} bytes")
        click.echo(f"total_gib={total_bytes / (1024**3):.2f}")
        return

    outputs = run_pilot_extraction(
        client,
        output_dir=output_dir,
        pilot_date=pilot_date,
        force=force,
    )
    for filename, output_path in outputs.items():
        click.echo(f"{filename}: {output_path}")


if __name__ == "__main__":
    main()
