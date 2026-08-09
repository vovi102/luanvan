#!/usr/bin/env python
"""Validate or run the two-model T3.3 paraphrasing pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import click

from nl2sparql.dataset.generate import validate_stage_a_records
from nl2sparql.dataset.paraphrase.artifacts import (
    ParaphraseArtifactError,
    build_run_manifest,
    expand_stage_c_records,
    total_generation_cost,
    validate_stage_b_records,
    validate_stage_c_records,
    write_cost_log,
    write_json_atomic,
    write_jsonl_atomic,
)
from nl2sparql.dataset.paraphrase.contracts import load_entity_index
from nl2sparql.dataset.paraphrase.openrouter import (
    OpenRouterClient,
    OpenRouterConfigurationError,
)
from nl2sparql.dataset.paraphrase.runner import (
    ParaphraseRunError,
    run_stage_b,
    run_stage_c,
)
from nl2sparql.dataset.templates import load_templates

ROOT = Path(__file__).resolve().parents[1]
STAGE_A_PATH = ROOT / "data/dataset/raw/synthetic-stage-a.jsonl"
STAGE_B_PATH = ROOT / "data/dataset/raw/synthetic-stage-b.jsonl"
STAGE_C_PATH = ROOT / "data/dataset/raw/synthetic-stage-c.jsonl"
COST_LOG_PATH = ROOT / "data/dataset/raw/cost_log.csv"
CONFIG_PATH = ROOT / "data/dataset/raw/paraphrase-config.json"
CHECKPOINT_B_PATH = ROOT / "data/dataset/raw/.stage-b.checkpoint.jsonl"
CHECKPOINT_C_PATH = ROOT / "data/dataset/raw/.stage-c.checkpoint.jsonl"
EXPECTED_SOURCE_SHA256 = "a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709"


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@click.command()
@click.option(
    "--mode",
    type=click.Choice(["validate-only", "stage-b", "stage-c", "all"]),
    default="validate-only",
    show_default=True,
)
@click.option("--concurrency", type=click.IntRange(1, 20), default=10, show_default=True)
@click.option("--cost-cap", type=click.FloatRange(min=0.01), default=30.0, show_default=True)
def main(mode: str, concurrency: int, cost_cap: float) -> None:
    """Keep validation credential-free; construct OpenRouter only in live modes."""
    try:
        source_bytes = STAGE_A_PATH.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        stage_a = [json.loads(line) for line in source_bytes.splitlines()]
        validate_stage_a_records(stage_a, load_templates())
        if source_sha256 != EXPECTED_SOURCE_SHA256:
            raise ParaphraseArtifactError("Stage A source SHA-256 does not match contract")
        payload: dict[str, object] = {
            "mode": mode,
            "stage_a_records": len(stage_a),
            "source_sha256": source_sha256,
            "cost_cap_usd": cost_cap,
        }
        if mode != "validate-only":
            client = OpenRouterClient.from_env()
            entity_index = load_entity_index()
            stage_b_records = _load_jsonl(STAGE_B_PATH) if mode == "stage-c" else None
            spent = (
                total_generation_cost({"stage_b": stage_b_records})
                if stage_b_records is not None
                else 0.0
            )
            if spent > cost_cap:
                raise ParaphraseRunError("Stage B cost already exceeds the total cap")
            if mode in {"stage-b", "all"}:
                stage_b_report = asyncio.run(
                    run_stage_b(
                        stage_a,
                        client,
                        CHECKPOINT_B_PATH,
                        entity_index,
                        concurrency=concurrency,
                        cost_cap_usd=cost_cap,
                    )
                )
                stage_b_records = list(stage_b_report.records)
                validate_stage_b_records(stage_b_records)
                write_jsonl_atomic(stage_b_records, STAGE_B_PATH)
                spent += stage_b_report.total_cost_usd
                payload["stage_b_records"] = len(stage_b_records)
            if mode in {"stage-c", "all"}:
                if stage_b_records is None:
                    raise ParaphraseArtifactError("Stage B artifact is required")
                remaining = cost_cap - spent
                if remaining <= 0:
                    raise ParaphraseRunError("No cost budget remains for Stage C")
                stage_c_report = asyncio.run(
                    run_stage_c(
                        stage_b_records,
                        client,
                        CHECKPOINT_C_PATH,
                        entity_index,
                        concurrency=concurrency,
                        cost_cap_usd=remaining,
                    )
                )
                parents = list(stage_c_report.records)
                children = expand_stage_c_records(parents)
                validate_stage_c_records(children)
                write_jsonl_atomic(children, STAGE_C_PATH)
                spent += stage_c_report.total_cost_usd
                write_cost_log({"stage_b": stage_b_records, "stage_c": parents}, COST_LOG_PATH)
                actual_cost = total_generation_cost(
                    {"stage_b": stage_b_records, "stage_c": parents}
                )
                if actual_cost > cost_cap:
                    raise ParaphraseRunError("Total API cost exceeds the configured cap")
                manifest = build_run_manifest(
                    source_sha256=source_sha256,
                    stage_b_sha256=hashlib.sha256(STAGE_B_PATH.read_bytes()).hexdigest(),
                    stage_c_sha256=hashlib.sha256(STAGE_C_PATH.read_bytes()).hexdigest(),
                    stage_b_records=stage_b_records,
                    stage_c_records=children,
                    actual_cost_usd=actual_cost,
                    cost_cap_usd=cost_cap,
                    generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                )
                write_json_atomic(manifest, CONFIG_PATH)
                payload["stage_c_records"] = len(children)
                spent = actual_cost
            payload["actual_cost_usd"] = spent
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    except (
        OSError,
        json.JSONDecodeError,
        OpenRouterConfigurationError,
        ParaphraseArtifactError,
        ParaphraseRunError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
