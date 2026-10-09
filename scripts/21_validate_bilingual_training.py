#!/usr/bin/env python
"""Offline validation and held-out exclusion indexing for bilingual training."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "src/nl2sparql/dataset/bilingual/templates.json"
DEFAULT_STAGE_A = ROOT / "data/dataset/raw/synthetic-stage-a.jsonl"
PRODUCTION_TEMPLATES = ROOT / "src/nl2sparql/dataset/templates/templates.json"


def _load_production_templates() -> list[dict[str, Any]]:
    try:
        value = json.loads(PRODUCTION_TEMPLATES.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise click.ClickException("production templates are not valid JSON") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise click.ClickException("production templates must be a JSON array of objects")
    return value


def _jsonl(path: Path, field: str) -> tuple[bytes, tuple[str, ...]]:
    try:
        payload = path.read_bytes()
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise click.ClickException("held-out source is not valid JSONL") from exc
    if not rows:
        raise click.ClickException("held-out source is empty")
    questions: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise click.ClickException("held-out source rows must be JSON objects")
        question = row.get(field)
        if not isinstance(question, str) or not question.strip():
            raise click.ClickException(f"held-out source requires non-empty {field}")
        questions.append(question)
    return payload, tuple(questions)


def _object_jsonl(path: Path, owner: str) -> tuple[bytes, list[dict[str, Any]]]:
    try:
        payload = path.read_bytes()
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"{owner} is not valid JSONL") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise click.ClickException(f"{owner} requires JSON object rows")
    return payload, rows


def _write_derived(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise click.ClickException("refusing to replace a different exclusion index")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _emit(value: dict[str, Any]) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, sort_keys=True))


@click.command()
@click.option(
    "--mode",
    type=click.Choice(("index-exclusions", "validate-catalog", "validate-artifact")),
    required=True,
)
@click.option("--catalog", type=click.Path(path_type=Path), default=DEFAULT_CATALOG)
@click.option("--english-benchmark", type=click.Path(path_type=Path))
@click.option("--vietnamese-draft", type=click.Path(path_type=Path))
@click.option("--exclusion-index", type=click.Path(path_type=Path))
@click.option("--stage-a", type=click.Path(path_type=Path), default=DEFAULT_STAGE_A)
@click.option("--output", type=click.Path(path_type=Path))
@click.option("--manifest", type=click.Path(path_type=Path))
@click.option("--audit", type=click.Path(path_type=Path))
def main(
    mode: str,
    catalog: Path,
    english_benchmark: Path | None,
    vietnamese_draft: Path | None,
    exclusion_index: Path | None,
    stage_a: Path,
    output: Path | None,
    manifest: Path | None,
    audit: Path | None,
) -> None:
    """Run deterministic validation without model or network access."""
    try:
        if mode == "validate-catalog":
            from nl2sparql.dataset.bilingual.contracts import load_catalog

            templates = _load_production_templates()
            loaded = load_catalog(catalog, templates)
            _emit(
                {
                    "catalog_entries": len(loaded.entries),
                    "intent_count": len({entry.template_id for entry in loaded.entries}),
                    "mode": mode,
                    "status": "valid",
                }
            )
            return

        if mode == "index-exclusions":
            from nl2sparql.dataset.bilingual.assembly import (
                HeldOutSource,
                build_exclusion_index,
                serialize_exclusion_index,
            )

            if english_benchmark is None or vietnamese_draft is None or exclusion_index is None:
                raise click.ClickException(
                    "index-exclusions requires both sources and --exclusion-index"
                )
            english_bytes, english_questions = _jsonl(english_benchmark, "nl")
            vietnamese_bytes, vietnamese_questions = _jsonl(vietnamese_draft, "question")
            sources = (
                HeldOutSource(
                    name="english-benchmark",
                    source_sha256=hashlib.sha256(english_bytes).hexdigest(),
                    questions=english_questions,
                ),
                HeldOutSource(
                    name="vietnamese-draft",
                    source_sha256=hashlib.sha256(vietnamese_bytes).hexdigest(),
                    questions=vietnamese_questions,
                ),
            )
            index = build_exclusion_index(sources, ngram_size=12)
            _write_derived(exclusion_index, serialize_exclusion_index(index))
            _emit(
                {
                    "index_sha256": index.index_sha256,
                    "mode": mode,
                    "ngram_size": index.ngram_size,
                    "source_record_counts": list(index.source_record_counts),
                    "status": "indexed",
                }
            )
            return

        if None in (output, manifest, audit, exclusion_index):
            raise click.ClickException(
                "validate-artifact requires output, manifest, audit, and exclusion index"
            )
        from nl2sparql.dataset.bilingual.assembly import (
            assign_group_splits,
            validate_artifacts,
        )
        from nl2sparql.dataset.bilingual.contracts import SplitConfig, load_catalog
        from nl2sparql.dataset.bilingual.rendering import expand_stage_a

        templates = _load_production_templates()
        loaded_catalog = load_catalog(catalog, templates)
        stage_a_bytes, stage_a_rows = _object_jsonl(stage_a, "Stage A")
        split_config = SplitConfig(seed=42, development_percent=10)
        expected_records = assign_group_splits(
            expand_stage_a(stage_a_rows, loaded_catalog, templates), split_config
        )

        report = validate_artifacts(
            output_bytes=output.read_bytes(),
            manifest_bytes=manifest.read_bytes(),
            audit_bytes=audit.read_bytes(),
            exclusion_index_bytes=exclusion_index.read_bytes(),
            stage_a_bytes=stage_a_bytes,
            catalog_bytes=catalog.read_bytes(),
            split_config=split_config,
            expected_records=expected_records,
        )
        _emit(
            {
                "manifest_sha256": report.manifest_sha256,
                "mode": mode,
                "output_sha256": report.output_sha256,
                "record_count": report.record_count,
                "semantic_family_count": report.semantic_family_count,
                "status": "valid",
            }
        )
    except click.ClickException:
        raise
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
