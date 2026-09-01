#!/usr/bin/env python
"""Offline-first workflow for T5.2 B1/B2 GoogleSQL baselines."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from nl2sparql.models.b12 import (
    BaselineB1,
    BaselineB2,
    EvaluationRun,
    FewShotRetriever,
    GenerationConfig,
    SmallLLMError,
    compile_catalog_summary,
    evaluate_baseline,
    load_evaluation_cases,
    validate_question,
)
from nl2sparql.sql.schema import CATALOG_PATH

DEFAULT_TEST_SET = Path("data/eval/test-100.jsonl")
DEFAULT_TRAINING_SET = Path("data/dataset/final/train.jsonl")
DEFAULT_CACHE = Path("data/eval/cache/b2-few-shot.npz")
DEFAULT_B1_PREDICTIONS = Path("data/eval/predictions/b1_test.jsonl")
DEFAULT_B2_PREDICTIONS = Path("data/eval/predictions/b2_test.jsonl")
DEFAULT_B1_LOG = Path("data/eval/logs/b1_run.jsonl")
DEFAULT_B2_LOG = Path("data/eval/logs/b2_run.jsonl")
DEFAULT_B1_REPORT = Path("reports/b1_inference.json")
DEFAULT_B2_REPORT = Path("reports/b2_inference.json")
DEFAULT_ENCODER_ID = "sentence-transformers/all-MiniLM-L6-v2"


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _emit(payload: dict[str, object]) -> None:
    click.echo(_canonical_json(payload).decode("utf-8"), nl=False)


def _stop(status: str, error: str) -> None:
    _emit({"status": status, "error": error})
    raise click.exceptions.Exit(2)


def load_real_backend(config: GenerationConfig):
    """Import and load Transformers only after all workflow preflight checks."""
    from nl2sparql.models.b12.transformers_backend import TransformersBackend

    return TransformersBackend.load(config)


def load_sentence_encoder(encoder_id: str, encoder_revision: str):
    """Import SentenceTransformers only when B2 real inference is authorized."""
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(
            encoder_id,
            revision=encoder_revision,
            local_files_only=True,
        )
    except Exception as exc:
        raise SmallLLMError(f"unable to load pinned sentence encoder: {exc}") from exc


def _paths_alias(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except (OSError, RuntimeError) as exc:
        raise SmallLLMError(f"unable to compare artifact paths: {exc}") from exc


def _existing_bytes(path: Path) -> bytes | None:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise SmallLLMError(f"unsafe existing artifact alias: {path}")
        return path.read_bytes()
    except SmallLLMError:
        raise
    except OSError as exc:
        raise SmallLLMError(f"unable to inspect existing artifact {path}: {exc}") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _existing_bytes(path)
        parent = path.parent.resolve(strict=True)
        descriptor, raw_temporary = tempfile.mkstemp(dir=parent, prefix=f".{path.name}.")
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    _atomic_write(path, previous)


def _validate_publication_paths(
    outputs: tuple[Path, ...], protected_paths: tuple[Path, ...]
) -> None:
    for index, left in enumerate(outputs):
        for right in outputs[index + 1 :]:
            if _paths_alias(left, right):
                raise SmallLLMError(f"output paths must not alias: {left} and {right}")
        for protected in protected_paths:
            if _paths_alias(left, protected):
                raise SmallLLMError(
                    f"output path must not alias protected input: {left} and {protected}"
                )


def _prediction_rows(run: EvaluationRun) -> list[dict[str, Any]]:
    return [asdict(row) for row in run.predictions]


def _log_rows(run: EvaluationRun) -> list[dict[str, Any]]:
    return [
        {
            "run_id": run.run_id,
            "baseline": run.baseline,
            "case_id": row.case_id,
            "latency_ms": row.prediction.latency_ms,
            "input_tokens": row.prediction.completion.input_tokens,
            "output_tokens": row.prediction.completion.output_tokens,
            "extraction_status": row.prediction.extraction_status,
            "synthetic_backend": row.prediction.completion.synthetic_backend,
        }
        for row in run.predictions
    ]


def publish_evaluation_run(
    run: EvaluationRun,
    *,
    predictions_path: Path,
    log_path: Path,
    report_path: Path,
    protected_paths: tuple[Path, ...] = (),
) -> None:
    """Publish predictions/logs first and report last, rolling back all failures."""
    if not isinstance(run, EvaluationRun):
        raise SmallLLMError("publication requires an EvaluationRun")
    outputs = (predictions_path, log_path, report_path)
    if any(not isinstance(path, Path) for path in (*outputs, *protected_paths)):
        raise SmallLLMError("artifact paths must be pathlib.Path values")
    _validate_publication_paths(outputs, protected_paths)
    previous = {path: _existing_bytes(path) for path in outputs}
    prediction_payload = b"".join(_canonical_json(row) for row in _prediction_rows(run))
    log_payload = b"".join(_canonical_json(row) for row in _log_rows(run))
    report_body = {
        "run_id": run.run_id,
        "baseline": run.baseline,
        "metrics": asdict(run.metrics),
        "scientific_ready": run.scientific_ready,
        "blockers": run.blockers,
        "prediction_count": len(run.predictions),
    }
    report_payload = _canonical_json(
        {
            **report_body,
            "report_sha256": hashlib.sha256(_canonical_json(report_body)).hexdigest(),
        }
    )
    try:
        _atomic_write(predictions_path, prediction_payload)
        _atomic_write(log_path, log_payload)
        _atomic_write(report_path, report_payload)
    except Exception as exc:
        rollback_errors: list[str] = []
        for path in outputs:
            try:
                _restore(path, previous[path])
            except Exception as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        suffix = f"; rollback failed: {rollback_errors}" if rollback_errors else ""
        raise SmallLLMError(f"unable to publish evaluation artifacts: {exc}{suffix}") from exc


def _build_baseline(
    baseline_name: str,
    *,
    config: GenerationConfig,
    catalog_path: Path,
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str | None,
):
    summary = compile_catalog_summary(catalog_path)
    backend = load_real_backend(config)
    if baseline_name == "b1":
        return BaselineB1(summary, config, backend)
    if encoder_revision is None:
        raise SmallLLMError("B2 requires --encoder-revision")
    encoder = load_sentence_encoder(encoder_id, encoder_revision)
    retriever = FewShotRetriever.from_snapshot(
        training_path,
        encoder=encoder,
        encoder_id=encoder_id,
        encoder_revision=encoder_revision,
        cache_path=cache_path,
    )
    return BaselineB2(summary, config, backend, retriever)


@click.group()
def cli() -> None:
    """Validate or run B1/B2 GoogleSQL baselines."""


@cli.command("validate")
@click.option("--baseline", "baseline_name", type=click.Choice(["b1", "b2"]), required=True)
@click.option("--catalog", "catalog_path", type=click.Path(path_type=Path), default=CATALOG_PATH)
@click.option(
    "--training", "training_path", type=click.Path(path_type=Path), default=DEFAULT_TRAINING_SET
)
@click.option("--cache", "cache_path", type=click.Path(path_type=Path), default=DEFAULT_CACHE)
@click.option("--encoder-id", default=DEFAULT_ENCODER_ID)
@click.option("--encoder-revision", default=None)
def validate_command(
    baseline_name: str,
    catalog_path: Path,
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str | None,
) -> None:
    """Validate local prompt/catalog and optional B2 cached retrieval evidence."""
    try:
        summary = compile_catalog_summary(catalog_path)
        payload: dict[str, object] = {
            "status": "ready",
            "baseline": baseline_name,
            "catalog_sha256": summary.catalog_sha256,
            "summary_sha256": summary.summary_sha256,
        }
        if baseline_name == "b2":
            if encoder_revision is None:
                raise SmallLLMError("B2 requires --encoder-revision")
            retriever = FewShotRetriever.from_snapshot(
                training_path,
                encoder=None,
                encoder_id=encoder_id,
                encoder_revision=encoder_revision,
                cache_path=cache_path,
            )
            payload["training_sha256"] = retriever.training_sha256
        _emit(payload)
    except SmallLLMError as exc:
        _stop("blocked", str(exc))


@cli.command("predict")
@click.option("--baseline", "baseline_name", type=click.Choice(["b1", "b2"]), required=True)
@click.option("--question", required=True)
@click.option("--model-revision", required=True)
@click.option("--catalog", "catalog_path", type=click.Path(path_type=Path), default=CATALOG_PATH)
@click.option(
    "--training", "training_path", type=click.Path(path_type=Path), default=DEFAULT_TRAINING_SET
)
@click.option("--cache", "cache_path", type=click.Path(path_type=Path), default=DEFAULT_CACHE)
@click.option("--encoder-id", default=DEFAULT_ENCODER_ID)
@click.option("--encoder-revision", default=None)
@click.option("--target-id", default=None)
@click.option("--real-inference", is_flag=True, default=False)
def predict_command(
    baseline_name: str,
    question: str,
    model_revision: str,
    catalog_path: Path,
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str | None,
    target_id: str | None,
    real_inference: bool,
) -> None:
    """Run one explicitly authorized real B1/B2 prediction."""
    try:
        validate_question(question)
        config = GenerationConfig(model_revision)
    except SmallLLMError as exc:
        _stop("failed", str(exc))
    if not real_inference:
        _stop("blocked", "real inference requires explicit --real-inference opt-in")
    try:
        baseline = _build_baseline(
            baseline_name,
            config=config,
            catalog_path=catalog_path,
            training_path=training_path,
            cache_path=cache_path,
            encoder_id=encoder_id,
            encoder_revision=encoder_revision,
        )
        if isinstance(baseline, BaselineB2):
            prediction = baseline.predict_detailed(question, target_id=target_id)
        else:
            prediction = baseline.predict_detailed(question)
        _emit({"status": "ready", "prediction": asdict(prediction)})
    except SmallLLMError as exc:
        _stop("blocked", str(exc))


@cli.command("evaluate")
@click.option("--baseline", "baseline_name", type=click.Choice(["b1", "b2"]), required=True)
@click.option("--test-set", type=click.Path(path_type=Path), default=DEFAULT_TEST_SET)
@click.option("--model-revision", required=True)
@click.option("--run-id", required=True)
@click.option("--catalog", "catalog_path", type=click.Path(path_type=Path), default=CATALOG_PATH)
@click.option(
    "--training", "training_path", type=click.Path(path_type=Path), default=DEFAULT_TRAINING_SET
)
@click.option("--cache", "cache_path", type=click.Path(path_type=Path), default=DEFAULT_CACHE)
@click.option("--encoder-id", default=DEFAULT_ENCODER_ID)
@click.option("--encoder-revision", default=None)
@click.option("--predictions", "predictions_path", type=click.Path(path_type=Path), default=None)
@click.option("--log", "log_path", type=click.Path(path_type=Path), default=None)
@click.option("--report", "report_path", type=click.Path(path_type=Path), default=None)
@click.option("--reviewed", is_flag=True, default=False)
@click.option("--live-verified", is_flag=True, default=False)
@click.option("--real-inference", is_flag=True, default=False)
def evaluate_command(
    baseline_name: str,
    test_set: Path,
    model_revision: str,
    run_id: str,
    catalog_path: Path,
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str | None,
    predictions_path: Path | None,
    log_path: Path | None,
    report_path: Path | None,
    reviewed: bool,
    live_verified: bool,
    real_inference: bool,
) -> None:
    """Run an explicitly authorized evaluation and publish atomic evidence."""
    try:
        config = GenerationConfig(model_revision)
        cases = load_evaluation_cases(test_set)
    except SmallLLMError as exc:
        _stop("failed", str(exc))
    if not real_inference:
        _stop("blocked", "real inference requires explicit --real-inference opt-in")
    try:
        baseline = _build_baseline(
            baseline_name,
            config=config,
            catalog_path=catalog_path,
            training_path=training_path,
            cache_path=cache_path,
            encoder_id=encoder_id,
            encoder_revision=encoder_revision,
        )
        run = evaluate_baseline(
            cases,
            baseline,
            run_id=run_id,
            reviewed=reviewed,
            live_verified=live_verified,
        )
        predictions_path = predictions_path or (
            DEFAULT_B1_PREDICTIONS if baseline_name == "b1" else DEFAULT_B2_PREDICTIONS
        )
        log_path = log_path or (DEFAULT_B1_LOG if baseline_name == "b1" else DEFAULT_B2_LOG)
        report_path = report_path or (
            DEFAULT_B1_REPORT if baseline_name == "b1" else DEFAULT_B2_REPORT
        )
        protected = [test_set, catalog_path]
        if baseline_name == "b2":
            protected.extend(
                [
                    training_path,
                    cache_path,
                    cache_path.with_suffix(cache_path.suffix + ".json"),
                    cache_path.with_suffix(cache_path.suffix + ".lock"),
                ]
            )
        publish_evaluation_run(
            run,
            predictions_path=predictions_path,
            log_path=log_path,
            report_path=report_path,
            protected_paths=tuple(protected),
        )
        _emit(
            {
                "status": "ready",
                "scientific_ready": run.scientific_ready,
                "blockers": run.blockers,
                "predictions": str(predictions_path),
                "log": str(log_path),
                "report": str(report_path),
            }
        )
    except SmallLLMError as exc:
        _stop("blocked", str(exc))


def main() -> int:
    """Run the Click CLI and return its process status."""
    cli.main(standalone_mode=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
