#!/usr/bin/env python
"""Export or validate the lossless T3.3 train snapshot; no ML stack needed."""

from __future__ import annotations

import json
from pathlib import Path

import click

from nl2sparql.models.b12.canonical_training import EXPORT, ROOT, build_training_export
from nl2sparql.models.b12.contracts import SmallLLMError
from nl2sparql.models.b12.retrieval import validate_training_snapshot


@click.command()
@click.argument("mode", type=click.Choice(("export", "validate")))
@click.option("--output", type=click.Path(path_type=Path), default=ROOT / EXPORT)
@click.option("--accepted-training-sha256", required=True)
def main(mode: str, output: Path, accepted_training_sha256: str) -> None:
    """An explicit fingerprint binds the exact B2 bytes, not the 8000-row corpus."""
    try:
        payload, manifest = build_training_export()
        snapshot = payload if mode == "export" else output.read_bytes()
        if snapshot != payload:
            raise SmallLLMError("snapshot is not the accepted canonical train export")
        records, digest = validate_training_snapshot(
            snapshot,
            accepted_training_sha256=accepted_training_sha256,
        )
        if mode == "export":
            # Immutable, resumable publication: existing different bytes never replaced.
            targets = ((output, payload), (output.with_suffix(".manifest.json"), manifest))
            for path, content in targets:
                if path.exists() and path.read_bytes() != content:
                    raise SmallLLMError(f"refusing to replace different artifact: {path}")
            for path, content in targets:
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    with path.open("xb") as handle:
                        handle.write(content)
        click.echo(
            json.dumps(
                {
                    "records": len(records),
                    "training_sha256": digest,
                    "mode": mode,
                    "status": "valid",
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
