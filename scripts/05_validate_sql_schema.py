#!/usr/bin/env python
"""Validate the T2-SQL-1 analytical catalog offline or against live metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.sql.schema import (
    CATALOG_PATH,
    SchemaCatalogError,
    load_catalog,
    normalize_live_schema,
    validate_catalog,
    validate_live_schemas,
)


def collect_live_schemas(client: Any, catalog: dict[str, object]) -> dict[str, dict[str, object]]:
    """Read metadata for deployed sources without issuing data queries."""

    schemas: dict[str, dict[str, object]] = {}
    expected_location = catalog["location"]
    for source_id, source in catalog["physical_sources"].items():
        if source["deployment_status"] != "live":
            continue
        object_name = source["object"]
        table = client.get_table(object_name)
        if table.location != expected_location:
            raise SchemaCatalogError(
                f"Live source location mismatch for {source_id}: "
                f"expected {expected_location}, received {table.location}"
            )
        schemas[source_id] = normalize_live_schema(table)
    return schemas


@click.command()
@click.option(
    "--catalog",
    "catalog_path",
    default=CATALOG_PATH,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    show_default=True,
    help="Machine-readable analytical schema catalog.",
)
@click.option(
    "--live",
    is_flag=True,
    help="Read BigQuery table/view metadata and validate required fields.",
)
@click.option(
    "--project",
    help="Google Cloud project used for authentication and billing context.",
)
def main(catalog_path: Path, live: bool, project: str | None) -> None:
    """Validate the analytical catalog; live mode remains metadata-only."""

    try:
        catalog = load_catalog(catalog_path)
        summary = validate_catalog(catalog)
        click.echo(f"sources={summary.source_count}")
        click.echo(f"relations={summary.relation_count}")
        click.echo(f"joins={summary.join_count}")
        click.echo(f"semantic_mappings={summary.semantic_mapping_count}")
        click.echo(f"competency_questions={summary.competency_question_count}")

        if live:
            client = bigquery.Client(project=project)
            schemas = collect_live_schemas(client, catalog)
            live_summary = validate_live_schemas(catalog, schemas)
            click.echo(f"live_checked_sources={live_summary.checked_source_count}")
            click.echo(f"live_deferred_sources={live_summary.deferred_source_count}")
            click.echo(f"live_checked_fields={live_summary.checked_field_count}")
    except (DefaultCredentialsError, GoogleAPICallError, SchemaCatalogError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
