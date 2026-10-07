#!/usr/bin/env python
"""Offline-only bilingual paired evaluation and gate publication workflow."""

from __future__ import annotations

import json
from pathlib import Path

import click

from nl2sparql.evaluation.artifacts import (
    load_evaluation_report,
    publish_immutable,
    serialize_bilingual_evaluation_report,
    serialize_gate_decision,
)
from nl2sparql.evaluation.bilingual import compare_language_pairs, evaluate_bilingual_gates
from nl2sparql.evaluation.contracts import GatePolicy


@click.command()
@click.option(
    "--mode",
    type=click.Choice(("validate-only", "finalize")),
    default="validate-only",
    show_default=True,
)
@click.option("--english-reference", type=click.Path(path_type=Path), required=True)
@click.option("--english", type=click.Path(path_type=Path), required=True)
@click.option("--vietnamese", type=click.Path(path_type=Path), required=True)
@click.option("--vietnamese-unaccented", type=click.Path(path_type=Path), required=True)
@click.option("--translation", type=click.Path(path_type=Path), required=True)
@click.option("--reviewed-count", type=click.IntRange(min=0), required=True)
@click.option("--live-count", type=click.IntRange(min=0), required=True)
@click.option("--report-output", type=click.Path(path_type=Path))
@click.option("--decision-output", type=click.Path(path_type=Path))
def main(
    mode: str,
    english_reference: Path,
    english: Path,
    vietnamese: Path,
    vietnamese_unaccented: Path,
    translation: Path,
    reviewed_count: int,
    live_count: int,
    report_output: Path | None,
    decision_output: Path | None,
) -> None:
    """Validate five canonical reports and optionally publish report plus gates."""
    inputs = (
        english_reference,
        english,
        vietnamese,
        vietnamese_unaccented,
        translation,
    )
    try:
        reports = tuple(load_evaluation_report(path) for path in inputs)
        if any(report.bootstrap != reports[0].bootstrap for report in reports[1:]):
            raise ValueError("incompatible bootstrap policies")
        report = compare_language_pairs(
            english_reference=reports[0],
            english=reports[1],
            vietnamese=reports[2],
            vietnamese_unaccented=reports[3],
            translation=reports[4],
            reviewed_count=reviewed_count,
            live_verified_count=live_count,
            bootstrap_policy=reports[0].bootstrap,
        )
        decision = evaluate_bilingual_gates(report, GatePolicy())
        if mode == "finalize":
            if report_output is None or decision_output is None:
                raise ValueError("finalize requires report and decision outputs")
            publish_immutable(
                report_output,
                serialize_bilingual_evaluation_report(report),
                protected_paths=(*inputs, decision_output),
            )
            publish_immutable(
                decision_output,
                serialize_gate_decision(decision),
                protected_paths=(*inputs, report_output),
            )
        summary = {
            "failed_gates": decision.failed_gates,
            "genuine": not report.synthetic,
            "mode": mode,
            "pair_count": len(report.pair_ids),
            "passed": decision.passed,
            "status": "valid" if mode == "validate-only" else "finalized",
        }
        click.echo(json.dumps(summary, sort_keys=True))
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise click.ClickException("bilingual workflow input or output failed validation") from None


if __name__ == "__main__":
    main()
