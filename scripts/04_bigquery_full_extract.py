#!/usr/bin/env python
"""Run guarded BigQuery dry-run checks for the T2.3 full extraction."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.kg.extraction.full_extract import (
    DEFAULT_DICTIONARY_PATH,
    DEFAULT_OUTPUT_DIR,
    compute_full_extract_date_range,
    load_dictionary_addresses,
    run_full_extract_dry_run,
)


@click.command()
@click.option(
    "--output-dir",
    default=DEFAULT_OUTPUT_DIR,
    type=click.Path(file_okay=False, path_type=Path),
    show_default=True,
    help="Directory for full extraction outputs and manifest.",
)
@click.option(
    "--dictionary-path",
    default=DEFAULT_DICTIONARY_PATH,
    type=click.Path(dir_okay=False, path_type=Path),
    show_default=True,
    help="Entity dictionary JSON used to count interesting addresses.",
)
@click.option("--start-date", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--end-date", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option(
    "--labeled-table",
    required=True,
    help="BigQuery table containing lower-case labeled addresses.",
)
@click.option("--dry-run", is_flag=True, help="Estimate bytes processed without exporting CSVs.")
@click.option("--force", is_flag=True, help="Allow live extraction once export settings exist.")
def main(
    output_dir: Path,
    dictionary_path: Path,
    start_date,
    end_date,
    labeled_table: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Run dry-run estimates or reject unsafe live extraction."""
    if not dry_run and not force:
        raise click.ClickException("Live full extraction requires --force after dry-run review.")
    if not dry_run:
        raise click.ClickException(
            "Live full extraction is intentionally blocked until temp-table/export "
            "settings are configured for this environment."
        )

    if (start_date is None) != (end_date is None):
        raise click.ClickException("--start-date and --end-date must be provided together.")
    if start_date is None or end_date is None:
        period_start, period_end = compute_full_extract_date_range()
    else:
        period_start = date.fromisoformat(start_date.strftime("%Y-%m-%d"))
        period_end = date.fromisoformat(end_date.strftime("%Y-%m-%d"))

    try:
        client = bigquery.Client()
    except DefaultCredentialsError as exc:
        raise click.ClickException(f"BigQuery authentication failed: {exc}") from exc

    dictionary_count = len(load_dictionary_addresses(dictionary_path))
    manifest_path = run_full_extract_dry_run(
        client,
        output_dir=output_dir,
        start_date=period_start,
        end_date=period_end,
        labeled_table=labeled_table,
        dictionary_path=dictionary_path,
        dictionary_count=dictionary_count,
    )
    click.echo(f"manifest: {manifest_path}")
    click.echo(f"dictionary_addresses: {dictionary_count}")


if __name__ == "__main__":
    main()
