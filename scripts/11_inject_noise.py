#!/usr/bin/env python
"""Generate or revalidate the deterministic T3.4 Stage D artifact."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import click

from nl2sparql.dataset.noise.artifacts import (
    build_noise_manifest,
    jsonl_bytes,
    publish_noise_artifacts,
    validate_noise_manifest,
)
from nl2sparql.dataset.noise.contracts import NoiseConfig, NoiseValidationError
from nl2sparql.dataset.noise.pipeline import inject_noise, validate_stage_d_records
from nl2sparql.dataset.noise.transforms import (
    ABBREVIATIONS_PATH,
    load_abbreviations,
)
from nl2sparql.dataset.paraphrase.contracts import (
    ParaphraseValidationError,
    load_entity_index,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/dataset/raw/synthetic-stage-c.jsonl"
DEFAULT_OUTPUT = ROOT / "data/dataset/raw/synthetic-stage-d.jsonl"
DEFAULT_MANIFEST = ROOT / "data/dataset/raw/noise-config.json"


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@click.command()
@click.option(
    "--mode",
    type=click.Choice(["generate", "validate-output"]),
    default="generate",
    show_default=True,
)
@click.option("--source", type=click.Path(path_type=Path), default=DEFAULT_SOURCE)
@click.option("--output", type=click.Path(path_type=Path), default=DEFAULT_OUTPUT)
@click.option(
    "--manifest", "manifest_path", type=click.Path(path_type=Path), default=DEFAULT_MANIFEST
)
@click.option(
    "--abbreviations",
    "abbreviations_path",
    type=click.Path(path_type=Path),
    default=ABBREVIATIONS_PATH,
)
def main(
    mode: str,
    source: Path,
    output: Path,
    manifest_path: Path,
    abbreviations_path: Path,
) -> None:
    """Generate exact Stage D quotas or revalidate published evidence."""
    try:
        stage_c = _load_jsonl(source)
        abbreviations = load_abbreviations(abbreviations_path)
        entity_index = load_entity_index()
        config = NoiseConfig()
        if mode == "generate":
            stage_d = inject_noise(stage_c, abbreviations, entity_index, config)
            stats = validate_stage_d_records(stage_c, stage_d, entity_index, config)
            output_payload = jsonl_bytes(stage_d)
            manifest = build_noise_manifest(
                source_path=source,
                output_bytes=output_payload,
                abbreviations_path=abbreviations_path,
                stage_c=stage_c,
                stage_d=stage_d,
                stats=stats,
                config=config,
                generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            )
            publish_noise_artifacts(
                output_payload,
                manifest,
                output_path=output,
                manifest_path=manifest_path,
            )
            payload = {
                "status": "generated",
                "source_records": len(stage_c),
                "output_records": len(stage_d),
                "noisy_records": stats.noisy_count,
                "output_sha256": manifest["output"]["sha256"],
            }
        else:
            stage_d = _load_jsonl(output)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stats = validate_stage_d_records(stage_c, stage_d, entity_index, config)
            validate_noise_manifest(
                manifest,
                source_path=source,
                output_path=output,
                abbreviations_path=abbreviations_path,
                stage_c=stage_c,
                stage_d=stage_d,
                stats=stats,
                config=config,
            )
            payload = {
                "status": "valid",
                "source_records": len(stage_c),
                "output_records": len(stage_d),
                "noisy_records": stats.noisy_count,
                "output_sha256": manifest["output"]["sha256"],
            }
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    except (
        OSError,
        json.JSONDecodeError,
        NoiseValidationError,
        ParaphraseValidationError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
