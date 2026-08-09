#!/usr/bin/env python
"""Plan or apply the durable BigQuery label-enriched analytical layer."""

from __future__ import annotations

from pathlib import Path

import click
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.linking.dictionary import ENTITIES_PATH
from nl2sparql.sql.label_layer import (
    DEFAULT_DATASET,
    DEFAULT_LOCATION,
    LabelLayerError,
    apply_deployment,
    build_deployment_plan,
)


@click.command()
@click.option("--project", required=True, help="Google Cloud project and billing context.")
@click.option("--dataset", default=DEFAULT_DATASET, show_default=True)
@click.option("--location", default=DEFAULT_LOCATION, show_default=True)
@click.option(
    "--entities",
    "entities_path",
    default=ENTITIES_PATH,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    show_default=True,
)
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Create or replace the planned BigQuery objects.",
)
@click.option(
    "--allow-sandbox-expiration",
    is_flag=True,
    help="Explicitly accept BigQuery Sandbox's enforced 60-day object expiration.",
)
def main(
    project: str,
    dataset: str,
    location: str,
    entities_path: Path,
    apply_changes: bool,
    allow_sandbox_expiration: bool,
) -> None:
    """Print a deterministic plan by default; --apply enables mutations."""
    try:
        plan = build_deployment_plan(
            project=project,
            dataset=dataset,
            location=location,
            entities_path=entities_path,
            allow_expiring_objects=allow_sandbox_expiration,
        )
        click.echo(f"mode={'apply' if apply_changes else 'plan'}")
        click.echo(f"dataset={plan.project}.{plan.dataset}")
        click.echo(f"location={plan.location}")
        click.echo(f"snapshot={plan.snapshot.table_name}")
        click.echo(f"dictionary_sha256={plan.snapshot.digest}")
        click.echo(f"entities={plan.snapshot.entity_count}")
        click.echo(f"objects={len(plan.sql_objects)}")
        click.echo(
            f"expiration_policy={'sandbox-60-day' if plan.allow_expiring_objects else 'durable'}"
        )
        for sql_object in plan.sql_objects:
            click.echo(f"object={sql_object.kind}:{sql_object.name}")

        if not apply_changes:
            return

        client = bigquery.Client(project=project, location=location)
        result = apply_deployment(plan, client)
        click.echo(f"created_dataset={str(result.created_dataset).lower()}")
        click.echo(f"snapshot_action={result.snapshot_action}")
        click.echo(f"dataset_default_expiration_ms={result.dataset_default_expiration_ms}")
        click.echo(
            "snapshot_expires="
            f"{result.snapshot_expires.date() if result.snapshot_expires else 'never'}"
        )
        click.echo(f"deployed_objects={len(result.deployed_objects)}")
    except (
        DefaultCredentialsError,
        GoogleAPICallError,
        LabelLayerError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
