#!/usr/bin/env python
"""Offline-first multilingual encoder selection workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path

import click

from nl2sparql.evaluation.artifacts import canonical_json, publish_immutable
from nl2sparql.linking.encoder_selection import (
    DevelopmentSets,
    EncoderCandidate,
    evaluate_encoder_candidate,
    select_encoder,
)

_DOCUMENT_FIELDS = {"schema_version", "synthetic", "development_sets", "candidates"}


def _exact_dataclass(value: object, cls: type):
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(cls)}:
        raise ValueError(f"invalid {cls.__name__} field set")
    return cls(**value)


def _load_input(path: Path):
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict) or set(document) != _DOCUMENT_FIELDS:
        raise ValueError("invalid encoder input field set")
    if document["schema_version"] != 1 or not isinstance(document["synthetic"], bool):
        raise ValueError("unsupported encoder input schema")
    development = _exact_dataclass(document["development_sets"], DevelopmentSets)
    raw_candidates = document["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("encoder candidates must be a non-empty array")
    candidates = tuple(_exact_dataclass(value, EncoderCandidate) for value in raw_candidates)
    scores = tuple(evaluate_encoder_candidate(candidate, development) for candidate in candidates)
    selection = select_encoder(scores)
    return document, scores, selection


def _final_payload(*, input_path: Path, document: dict, scores: tuple, selection: object) -> bytes:
    body = {
        "schema_version": 1,
        "synthetic": document["synthetic"],
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "scores": tuple(asdict(score) for score in scores),
        "selection": asdict(selection),
    }
    return canonical_json(
        body | {"artifact_sha256": hashlib.sha256(canonical_json(body)).hexdigest()}
    )


@click.command()
@click.option(
    "--mode",
    type=click.Choice(("validate-only", "finalize")),
    default="validate-only",
    show_default=True,
)
@click.option("--input", "input_path", type=click.Path(path_type=Path), required=True)
@click.option("--output", "output_path", type=click.Path(path_type=Path))
def main(mode: str, input_path: Path, output_path: Path | None) -> None:
    """Validate measured development evidence and optionally freeze selection."""
    try:
        document, scores, selection = _load_input(input_path)
        if mode == "finalize":
            if output_path is None:
                raise ValueError("finalize requires output")
            publish_immutable(
                output_path,
                _final_payload(
                    input_path=input_path,
                    document=document,
                    scores=scores,
                    selection=selection,
                ),
                protected_paths=(input_path,),
            )
        summary = {
            "candidate_count": len(scores),
            "genuine": not document["synthetic"],
            "mode": mode,
            "status": "valid" if mode == "validate-only" else "finalized",
            "winner_model_id": selection.winner_model_id,
        }
        click.echo(json.dumps(summary, sort_keys=True))
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise click.ClickException("encoder workflow input or output failed validation") from None


if __name__ == "__main__":
    main()
