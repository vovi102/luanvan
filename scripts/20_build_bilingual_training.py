#!/usr/bin/env python
"""Build deterministic bilingual training artifacts with fail-closed gates."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import click

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE_A = ROOT / "data/dataset/raw/synthetic-stage-a.jsonl"
DEFAULT_CATALOG = ROOT / "src/nl2sparql/dataset/bilingual/templates.json"
PRODUCTION_TEMPLATES = ROOT / "src/nl2sparql/dataset/templates/templates.json"


def _load_production_templates() -> list[dict[str, Any]]:
    try:
        value = json.loads(PRODUCTION_TEMPLATES.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise click.ClickException("production templates are not valid JSON") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise click.ClickException("production templates must be a JSON array of objects")
    return value


def _load_jsonl(path: Path, owner: str) -> tuple[bytes, list[dict[str, Any]]]:
    try:
        payload = path.read_bytes()
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"{owner} is not valid JSONL") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise click.ClickException(f"{owner} requires JSON object rows")
    return payload, rows


def _audit_events(rows: list[dict[str, Any]]) -> tuple[Any, ...]:
    from nl2sparql.dataset.bilingual.contracts import AuditEvent

    expected = {field.name for field in fields(AuditEvent)}
    if any(set(row) != expected for row in rows):
        raise click.ClickException("audit event field set is invalid")
    try:
        return tuple(AuditEvent(**row) for row in rows)
    except TypeError as exc:
        raise click.ClickException("audit event types are invalid") from exc


def _assert_safe_targets(
    *,
    inputs: tuple[Path, ...],
    output: Path,
    manifest: Path,
    audit: Path,
) -> None:
    protected = {path.resolve() for path in inputs}
    targets = (output.resolve(), manifest.resolve(), audit.resolve())
    if any(target in protected for target in targets):
        raise click.ClickException("artifact target aliases a protected input")
    if len(set(targets)) != len(targets):
        raise click.ClickException("artifact targets must differ")


def _emit(value: dict[str, Any]) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _sample_rows(records: tuple[Any, ...], sample_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    selected = set(sample_ids)
    return [asdict(record) for record in records if record.id in selected]


@click.command()
@click.option(
    "--mode",
    type=click.Choice(("validate-only", "audit-sample", "build")),
    required=True,
)
@click.option("--stage-a", type=click.Path(path_type=Path), default=DEFAULT_STAGE_A)
@click.option("--catalog", type=click.Path(path_type=Path), default=DEFAULT_CATALOG)
@click.option("--exclusion-index", type=click.Path(path_type=Path), required=True)
@click.option("--audit", type=click.Path(path_type=Path))
@click.option("--audit-sample-output", type=click.Path(path_type=Path))
@click.option("--output", type=click.Path(path_type=Path))
@click.option("--manifest", type=click.Path(path_type=Path))
def main(
    mode: str,
    stage_a: Path,
    catalog: Path,
    exclusion_index: Path,
    audit: Path | None,
    audit_sample_output: Path | None,
    output: Path | None,
    manifest: Path | None,
) -> None:
    """Validate inputs, prepare audit strata, or publish final artifacts."""
    try:
        from nl2sparql.dataset.bilingual.assembly import (
            assign_group_splits,
            build_manifest,
            load_exclusion_index,
            publish_artifacts,
            select_audit_sample,
            serialize_audit_events,
            serialize_manifest,
            validate_artifacts,
            validate_audit,
            validate_no_leakage,
        )
        from nl2sparql.dataset.bilingual.contracts import SplitConfig, load_catalog
        from nl2sparql.dataset.bilingual.rendering import (
            diversity_report,
            expand_stage_a,
            serialize_records,
        )

        if mode == "build":
            if output is None or manifest is None or audit is None:
                raise click.ClickException("build requires output, manifest, and audit")
            _assert_safe_targets(
                inputs=(stage_a, catalog, exclusion_index),
                output=output,
                manifest=manifest,
                audit=audit,
            )

        stage_a_bytes, source_rows = _load_jsonl(stage_a, "Stage A")
        templates = _load_production_templates()
        loaded_catalog = load_catalog(catalog, templates)
        exclusion_bytes = exclusion_index.read_bytes()
        exclusion = load_exclusion_index(exclusion_bytes)
        records = expand_stage_a(source_rows, loaded_catalog, templates)
        leakage = validate_no_leakage(records, exclusion)
        diversity = diversity_report(records)

        if mode == "validate-only":
            _emit(
                {
                    "api_request_count": 0,
                    "catalog_intents": len({entry.template_id for entry in loaded_catalog.entries}),
                    "expanded_records": len(records),
                    "generation_model": None,
                    "mode": mode,
                    "provider": None,
                    "recorded_cost_usd": 0.0,
                    "represented_intents": len({str(row["template_id"]) for row in source_rows}),
                    "stage_a_records": len(source_rows),
                    "status": "valid",
                }
            )
            return

        samples = {
            language: select_audit_sample(records, language, seed=42) for language in ("en", "vi")
        }
        if mode == "audit-sample":
            if audit_sample_output is None:
                raise click.ClickException("audit-sample requires --audit-sample-output")
            sample_rows = [
                row for language in ("en", "vi") for row in _sample_rows(records, samples[language])
            ]
            payload = b"".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                for row in sample_rows
            )
            audit_sample_output.parent.mkdir(parents=True, exist_ok=True)
            audit_sample_output.write_bytes(payload)
            _emit({"mode": mode, "sample_records": len(sample_rows), "status": "created"})
            return

        assert output is not None and manifest is not None and audit is not None
        audit_bytes, audit_rows = _load_jsonl(audit, "audit evidence")
        events = _audit_events(audit_rows)
        summaries = tuple(
            validate_audit(
                tuple(event for event in events if event.record_id in set(samples[language])),
                samples[language],
                records=records,
                language=language,
            )
            for language in ("en", "vi")
        )
        split_config = SplitConfig(seed=42, development_percent=10)
        assigned = assign_group_splits(records, split_config)
        output_bytes = serialize_records(assigned)
        canonical_audit = serialize_audit_events(events)
        manifest_document = build_manifest(
            assigned,
            output_bytes=output_bytes,
            stage_a_bytes=stage_a_bytes,
            catalog_bytes=catalog.read_bytes(),
            split_config=split_config,
            diversity=diversity,
            leakage=leakage,
            audit_summaries=summaries,
            audit_bytes=canonical_audit,
            exclusion_index=exclusion,
        )
        manifest_bytes = serialize_manifest(manifest_document)
        validate_artifacts(
            output_bytes=output_bytes,
            manifest_bytes=manifest_bytes,
            audit_bytes=canonical_audit,
            exclusion_index_bytes=exclusion_bytes,
            stage_a_bytes=stage_a_bytes,
            catalog_bytes=catalog.read_bytes(),
            split_config=split_config,
        )
        publish_artifacts(
            output_bytes,
            manifest_bytes,
            canonical_audit,
            output_path=output,
            manifest_path=manifest,
            audit_path=audit,
        )
        _emit({"mode": mode, "records": len(assigned), "status": "published"})
    except click.ClickException:
        raise
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
