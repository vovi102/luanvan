#!/usr/bin/env python
"""Offline-first workflow for T5.3 B4/B5 GoogleSQL baselines."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict, is_dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import click

from nl2sparql.models.b12 import FewShotRetriever, SmallLLMError, compile_catalog_summary
from nl2sparql.models.b12.contracts import validate_question
from nl2sparql.models.b45 import (
    ArtifactPaths,
    BaselineB4,
    BaselineB5,
    BudgetLedger,
    LargeEvaluationRun,
    LargeLLMConfig,
    LargeLLMError,
    ProviderPolicy,
    RequestJournal,
    evaluate_large_baseline,
    load_evaluation_cases,
    load_large_run_artifacts,
    load_resume_state,
    publish_large_run,
    summarize_large_runs,
    validate_artifact_paths,
)
from nl2sparql.models.b45.openrouter import validate_model_metadata
from nl2sparql.sql.schema import CATALOG_PATH

DEFAULT_TEST_SET = Path("data/eval/test-100.jsonl")
DEFAULT_TRAINING_SET = Path("data/dataset/final/train.jsonl")
DEFAULT_CACHE = Path("data/eval/cache/b5-few-shot.npz")
DEFAULT_B4_PREDICTIONS = Path("data/eval/predictions/b4_test.jsonl")
DEFAULT_B5_PREDICTIONS = Path("data/eval/predictions/b5_test.jsonl")
DEFAULT_B4_LOG = Path("data/eval/logs/b4_openrouter.jsonl")
DEFAULT_B5_LOG = Path("data/eval/logs/b5_openrouter.jsonl")
DEFAULT_COST_LOG = Path("data/eval/logs/openrouter_cost.csv")
DEFAULT_B4_REPORT = Path("reports/b4_inference.json")
DEFAULT_B5_REPORT = Path("reports/b5_inference.json")
DEFAULT_ENCODER_ID = "sentence-transformers/all-MiniLM-L6-v2"
_B12_PROTECTED_PATHS = (
    Path("data/eval/predictions/b1_test.jsonl"),
    Path("data/eval/predictions/b2_test.jsonl"),
    Path("data/eval/logs/b1_run.jsonl"),
    Path("data/eval/logs/b2_run.jsonl"),
    Path("reports/b1_inference.json"),
    Path("reports/b2_inference.json"),
    Path("data/dataset/raw/generation-config.json"),
)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _emit(payload: dict[str, object]) -> None:
    click.echo(json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":")), nl=False)


def _stop(error: Exception | str, *, status: str = "blocked") -> None:
    _emit({"status": status, "error": str(error)})
    raise SystemExit(2)


def _decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise LargeLLMError(f"{label} must be a Decimal") from error
    if not parsed.is_finite():
        raise LargeLLMError(f"{label} must be finite")
    return parsed


def _config(provider: str, max_cost_usd: str) -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug=provider,
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        max_cost_usd=_decimal(max_cost_usd, "max cost"),
    )


def _require_network(allow_network: bool) -> None:
    if not allow_network:
        raise LargeLLMError("network access requires --allow-network")


def _require_api_key() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise LargeLLMError("OPENROUTER_API_KEY is required for live operations")


def _require_metadata_sha(value: str | None) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LargeLLMError("accepted model metadata fingerprint must be a lowercase SHA-256")
    return value


def _validate_primitives(options: dict[str, Any], *, evaluation: bool) -> LargeLLMConfig:
    """Validate all non-filesystem command inputs before local preflight.

    Args:
        options: Parsed Click option values for one command invocation.
        evaluation: Whether a stable evaluation run identifier is required.

    Returns:
        Pinned large-model configuration derived solely from primitive options.

    Raises:
        LargeLLMError: If a primitive value is malformed or scientifically invalid.
    """
    config = _config(options["provider"], options["max_cost_usd"])
    if evaluation and _RUN_ID_RE.fullmatch(options["run_id"]) is None:
        raise LargeLLMError("evaluation run ID is invalid")
    accepted_metadata = options.get("accepted_model_metadata_sha256")
    if accepted_metadata is not None:
        _require_metadata_sha(accepted_metadata)
    if evaluation and accepted_metadata is None:
        raise LargeLLMError("evaluate requires --accepted-model-metadata-sha256")
    if options["baseline_name"] == "b5":
        accepted_training = options["accepted_training_sha256"]
        if (
            not isinstance(accepted_training, str)
            or _SHA256_RE.fullmatch(accepted_training) is None
        ):
            raise LargeLLMError("B5 requires --accepted-training-sha256")
        revision = options["encoder_revision"]
        if not isinstance(revision, str) or _REVISION_RE.fullmatch(revision) is None:
            raise LargeLLMError("B5 requires a pinned --encoder-revision")
    return config


def load_sentence_encoder(encoder_id: str, encoder_revision: str) -> Any:
    """Load the pinned encoder only after local and live metadata preflight.

    Args:
        encoder_id: Pinned SentenceTransformers model identifier.
        encoder_revision: Pinned immutable encoder revision.

    Returns:
        A local SentenceTransformers-compatible encoder instance.

    Raises:
        LargeLLMError: If the pinned local encoder cannot be initialized.
    """
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(encoder_id, revision=encoder_revision, local_files_only=True)
    except Exception as error:
        raise LargeLLMError("unable to load pinned sentence encoder") from error


def load_openrouter_transport(config: LargeLLMConfig, ledger: BudgetLedger) -> Any:
    """Lazily construct the live OpenRouter transport after all preflight checks.

    Args:
        config: Validated pinned large-model configuration.
        ledger: Matching hard-cap budget ledger.

    Returns:
        A live, budget-aware OpenRouter completion transport.
    """
    from nl2sparql.models.b45.openrouter import OpenRouterTransport

    return OpenRouterTransport.from_env(config, ledger)


def load_model_metadata(config: LargeLLMConfig) -> object:
    """Fetch exact model metadata only for opted-in live runs.

    Args:
        config: Validated pinned model and timeout configuration.

    Returns:
        The raw decoded OpenRouter metadata response.

    Raises:
        LargeLLMError: If the metadata request cannot be completed safely.
    """
    from urllib.request import Request, urlopen

    request = Request(
        f"https://openrouter.ai/api/v1/models/{config.model_id}",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
    )
    try:
        with urlopen(request, timeout=float(config.timeout_seconds)) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise LargeLLMError("unable to load OpenRouter model metadata") from error


def _b5_cache_preflight(
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str | None,
    accepted_training_sha256: str | None,
) -> FewShotRetriever | None:
    """Validate B5 training/cache evidence without constructing an encoder.

    Args:
        training_path: Exact local B5 training snapshot.
        cache_path: Local few-shot embedding cache.
        encoder_id: Pinned sentence-encoder identifier.
        encoder_revision: Pinned sentence-encoder revision.
        accepted_training_sha256: Required accepted training snapshot digest.

    Returns:
        A cache-backed retriever when the cache is valid, otherwise ``None`` to
        signal that a post-metadata encoder rebuild is required.

    Raises:
        LargeLLMError: If training provenance or local cache evidence is invalid.
    """
    if encoder_revision is None:
        raise LargeLLMError("B5 requires --encoder-revision")
    try:
        return FewShotRetriever.from_snapshot(
            training_path,
            encoder=None,
            encoder_id=encoder_id,
            encoder_revision=encoder_revision,
            cache_path=cache_path,
            accepted_training_sha256=accepted_training_sha256,
        )
    except SmallLLMError as error:
        if "few-shot cache is invalid and encoder unavailable" in str(error):
            return None
        raise LargeLLMError(str(error)) from error


def _b5_retriever(
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str,
    accepted_training_sha256: str | None,
    cached_retriever: FewShotRetriever | None,
) -> FewShotRetriever:
    """Return a validated B5 retriever, rebuilding only stale/absent caches.

    Args:
        training_path: Exact local B5 training snapshot.
        cache_path: Local embedding cache to use or rebuild.
        encoder_id: Pinned encoder identifier.
        encoder_revision: Pinned encoder revision.
        accepted_training_sha256: Accepted training snapshot digest.
        cached_retriever: Cache-backed retriever from local preflight, if valid.

    Returns:
        A B2-compatible retriever with accepted training provenance.
    """
    if cached_retriever is not None:
        return cached_retriever
    encoder = load_sentence_encoder(encoder_id, encoder_revision)
    try:
        return FewShotRetriever.from_snapshot(
            training_path,
            encoder=encoder,
            encoder_id=encoder_id,
            encoder_revision=encoder_revision,
            cache_path=cache_path,
            accepted_training_sha256=accepted_training_sha256,
        )
    except SmallLLMError as error:
        raise LargeLLMError(str(error)) from error


def build_large_baseline(
    baseline_name: str,
    *,
    summary: object,
    config: LargeLLMConfig,
    transport: object,
    training_path: Path,
    cache_path: Path,
    encoder_id: str,
    encoder_revision: str | None,
    accepted_training_sha256: str | None,
    cached_retriever: FewShotRetriever | None = None,
) -> BaselineB4 | BaselineB5:
    """Build one B4/B5 baseline after every local and live dependency is ready.

    Args:
        baseline_name: Requested baseline, either ``"b4"`` or ``"b5"``.
        summary: Validated catalog prompt summary.
        config: Pinned generation configuration.
        transport: Live completion transport created after preflight.
        training_path: Exact B5 training snapshot.
        cache_path: Local B5 retrieval cache.
        encoder_id: Pinned B5 encoder identifier.
        encoder_revision: Pinned B5 encoder revision.
        accepted_training_sha256: Accepted B5 training snapshot digest.
        cached_retriever: Cache-backed B5 retriever from local preflight.

    Returns:
        An immutable B4 or B5 baseline ready for asynchronous generation.

    Raises:
        LargeLLMError: If the baseline selection or B5 prerequisites are invalid.
    """
    if baseline_name == "b4":
        return BaselineB4(summary, config, transport)
    if baseline_name != "b5" or encoder_revision is None:
        raise LargeLLMError("baseline must be b4 or B5 requires --encoder-revision")
    return BaselineB5(
        summary,
        config,
        transport,
        _b5_retriever(
            training_path,
            cache_path,
            encoder_id,
            encoder_revision,
            accepted_training_sha256,
            cached_retriever,
        ),
    )


def _metadata_evidence(config: LargeLLMConfig, prompt_bytes: int, accepted_sha: str | None):
    _require_metadata_sha(accepted_sha)
    evidence = validate_model_metadata(
        load_model_metadata(config), config, prompt_bytes=prompt_bytes
    )
    if evidence.metadata_sha256 != accepted_sha:
        raise LargeLLMError("accepted model metadata fingerprint does not match live metadata")
    return evidence


def _artifact_paths(
    baseline_name: str,
    predictions: Path | None,
    request_log: Path | None,
    cost_log: Path | None,
    report: Path | None,
) -> ArtifactPaths:
    return ArtifactPaths(
        predictions=predictions
        or (DEFAULT_B4_PREDICTIONS if baseline_name == "b4" else DEFAULT_B5_PREDICTIONS),
        request_log=request_log or (DEFAULT_B4_LOG if baseline_name == "b4" else DEFAULT_B5_LOG),
        cost_csv=cost_log or DEFAULT_COST_LOG,
        report=report or (DEFAULT_B4_REPORT if baseline_name == "b4" else DEFAULT_B5_REPORT),
    )


def _protected_paths(options: dict[str, Any]) -> tuple[Path, ...]:
    """Return all input, cache-sidecar, and prior-baseline evidence paths.

    Args:
        options: Parsed command options carrying input and cache paths.

    Returns:
        Paths that B4/B5 publication must never overwrite or alias.
    """
    cache_path = options["cache_path"]
    return (
        options["test_set"],
        options["catalog_path"],
        options["training_path"],
        cache_path,
        cache_path.with_suffix(cache_path.suffix + ".json"),
        cache_path.with_suffix(cache_path.suffix + ".lock"),
        *_B12_PROTECTED_PATHS,
    )


class _JsonGroup(click.Group):
    """Emit compact JSON for every non-help Click parse or usage failure."""

    def main(self, *args: Any, **kwargs: Any) -> Any:
        """Run Click without its text error renderer.

        Args:
            *args: Positional arguments accepted by :meth:`click.Command.main`.
            **kwargs: Keyword arguments accepted by :meth:`click.Command.main`.

        Returns:
            The selected callback result for a successful invocation.

        Raises:
            SystemExit: With the normalized command exit status.
        """
        kwargs["standalone_mode"] = False
        try:
            result = super().main(*args, **kwargs)
            if isinstance(result, int):
                raise SystemExit(result)
            return result
        except click.ClickException as error:
            _emit({"status": "failed", "error": error.format_message()})
            raise SystemExit(error.exit_code) from None


@click.group(cls=_JsonGroup)
def cli() -> None:
    """Validate or run B4/B5 GoogleSQL large-LLM baselines."""


def _common_options(command):
    command = click.option("--provider", required=True)(command)
    command = click.option("--max-cost-usd", default="20")(command)
    command = click.option(
        "--catalog", "catalog_path", type=click.Path(path_type=Path), default=CATALOG_PATH
    )(command)
    command = click.option(
        "--training", "training_path", type=click.Path(path_type=Path), default=DEFAULT_TRAINING_SET
    )(command)
    command = click.option(
        "--cache", "cache_path", type=click.Path(path_type=Path), default=DEFAULT_CACHE
    )(command)
    command = click.option("--encoder-id", default=DEFAULT_ENCODER_ID)(command)
    command = click.option("--encoder-revision", default=None)(command)
    command = click.option("--accepted-training-sha256", default=None)(command)
    return command


@cli.command("validate")
@click.option("--baseline", "baseline_name", type=click.Choice(["b4", "b5"]), required=True)
@_common_options
def validate_command(**options: Any) -> None:
    """Validate local catalog and B5 cache evidence without network access."""
    try:
        config = _validate_primitives(options, evaluation=False)
        summary = compile_catalog_summary(options["catalog_path"])
        if options["baseline_name"] == "b5":
            _b5_cache_preflight(
                options["training_path"],
                options["cache_path"],
                options["encoder_id"],
                options["encoder_revision"],
                options["accepted_training_sha256"],
            )
        _emit(
            {
                "status": "ready",
                "baseline": options["baseline_name"],
                "catalog_sha256": summary.catalog_sha256,
                "summary_sha256": summary.summary_sha256,
                "config_sha256": config.sha256,
            }
        )
    except (LargeLLMError, SmallLLMError) as error:
        _stop(error)


@cli.command("predict")
@click.option("--baseline", "baseline_name", type=click.Choice(["b4", "b5"]), required=True)
@click.option("--question", required=True)
@click.option("--target-id", default=None)
@click.option("--allow-network", is_flag=True, default=False)
@click.option("--accepted-model-metadata-sha256", default=None)
@_common_options
def predict_command(**options: Any) -> None:
    """Run one explicitly opted-in live B4/B5 prediction without artifacts."""
    try:
        config = _validate_primitives(options, evaluation=False)
        validate_question(options["question"])
        summary = compile_catalog_summary(options["catalog_path"])
        cached_retriever = None
        if options["baseline_name"] == "b5":
            cached_retriever = _b5_cache_preflight(
                options["training_path"],
                options["cache_path"],
                options["encoder_id"],
                options["encoder_revision"],
                options["accepted_training_sha256"],
            )
        _require_network(options["allow_network"])
        _require_api_key()
        metadata = _metadata_evidence(
            config,
            len(summary.text.encode("utf-8")) + len(options["question"].encode("utf-8")),
            options["accepted_model_metadata_sha256"],
        )
        ledger = BudgetLedger(config)
        transport = load_openrouter_transport(config, ledger)
        baseline = build_large_baseline(
            options["baseline_name"],
            summary=summary,
            config=config,
            transport=transport,
            training_path=options["training_path"],
            cache_path=options["cache_path"],
            encoder_id=options["encoder_id"],
            encoder_revision=options["encoder_revision"],
            accepted_training_sha256=options["accepted_training_sha256"],
            cached_retriever=cached_retriever,
        )
        if options["baseline_name"] == "b5":
            prediction = asyncio.run(
                baseline.predict_detailed(
                    options["question"], request_id="predict", target_id=options["target_id"]
                )
            )
        else:
            prediction = asyncio.run(
                baseline.predict_detailed(options["question"], request_id="predict")
            )
        _emit(
            {
                "status": "ready",
                "prediction": prediction,
                "model_metadata_sha256": metadata.metadata_sha256,
            }
        )
    except (LargeLLMError, SmallLLMError) as error:
        _stop(error)


@cli.command("evaluate")
@click.option("--baseline", "baseline_name", type=click.Choice(["b4", "b5"]), required=True)
@click.option("--test-set", type=click.Path(path_type=Path), default=DEFAULT_TEST_SET)
@click.option("--run-id", required=True)
@click.option("--predictions", type=click.Path(path_type=Path), default=None)
@click.option("--request-log", type=click.Path(path_type=Path), default=None)
@click.option("--cost-log", type=click.Path(path_type=Path), default=None)
@click.option("--report", type=click.Path(path_type=Path), default=None)
@click.option("--resume", is_flag=True, default=False)
@click.option("--allow-network", is_flag=True, default=False)
@click.option("--accepted-model-metadata-sha256", default=None)
@_common_options
def evaluate_command(**options: Any) -> None:
    """Run and atomically publish one opted-in B4/B5 evaluation."""
    try:
        config = _validate_primitives(options, evaluation=True)
        paths = _artifact_paths(
            options["baseline_name"],
            options["predictions"],
            options["request_log"],
            options["cost_log"],
            options["report"],
        )
        protected = _protected_paths(options)
        # An unsafe destination is rejected before parsing it as an input, so a
        # malformed snapshot can never mask a destructive output alias.
        validate_artifact_paths(paths, protected_paths=protected)
        cases = load_evaluation_cases(options["test_set"])
        summary = compile_catalog_summary(options["catalog_path"])
        cached_retriever = None
        if options["baseline_name"] == "b5":
            cached_retriever = _b5_cache_preflight(
                options["training_path"],
                options["cache_path"],
                options["encoder_id"],
                options["encoder_revision"],
                options["accepted_training_sha256"],
            )
        completed_outcomes = ()
        ledger = BudgetLedger(config)
        if options["resume"]:
            expected_metadata_sha = _require_metadata_sha(options["accepted_model_metadata_sha256"])
            input_sha = cases[0].input_sha256
            if input_sha is None:
                raise LargeLLMError("evaluation snapshot fingerprint is missing")
            resume = load_resume_state(
                paths.request_log,
                expected_input_sha256=input_sha,
                expected_config_sha256=config.sha256,
                expected_run_id=options["run_id"],
                expected_model_metadata_sha256=expected_metadata_sha,
            )
            ledger = BudgetLedger.from_checkpoint(config, resume.budget_checkpoint)
            completed_outcomes = resume.completed_outcomes
        _require_network(options["allow_network"])
        _require_api_key()
        metadata = _metadata_evidence(
            config,
            len(summary.text.encode("utf-8")) + 2000,
            options["accepted_model_metadata_sha256"],
        )
        transport = load_openrouter_transport(config, ledger)
        baseline = build_large_baseline(
            options["baseline_name"],
            summary=summary,
            config=config,
            transport=transport,
            training_path=options["training_path"],
            cache_path=options["cache_path"],
            encoder_id=options["encoder_id"],
            encoder_revision=options["encoder_revision"],
            accepted_training_sha256=options["accepted_training_sha256"],
            cached_retriever=cached_retriever,
        )
        evidence = baseline.evaluation_evidence
        journal = RequestJournal(
            paths.request_log,
            run_id=options["run_id"],
            baseline=options["baseline_name"],
            input_sha256=cases[0].input_sha256,
            config_sha256=config.sha256,
            catalog_sha256=evidence.catalog_sha256,
            summary_sha256=evidence.summary_sha256,
            training_sha256=evidence.training_sha256,
            model_id=evidence.model_id,
            provider_slug=evidence.provider_slug,
            model_metadata_sha256=metadata.metadata_sha256,
        )
        run = asyncio.run(
            evaluate_large_baseline(
                cases,
                baseline,
                run_id=options["run_id"],
                concurrency=config.concurrency,
                model_metadata=metadata,
                journal=journal,
                completed_outcomes=completed_outcomes,
            )
        )
        publish_large_run(run, paths=paths, protected_paths=protected)
        _emit(
            {
                "status": "ready",
                "scientific_ready": run.scientific_ready,
                "blockers": run.blockers,
                "predictions": paths.predictions,
                "request_log": paths.request_log,
                "cost_log": paths.cost_csv,
                "report": paths.report,
            }
        )
    except (LargeLLMError, SmallLLMError) as error:
        _stop(error)


def load_large_run_report(report_path: Path, request_log_path: Path) -> LargeEvaluationRun:
    """Load one locally published, typed large-evaluation run.

    Args:
        report_path: Canonical JSON report for the run.
        request_log_path: Canonical durable request journal for the same run.

    Returns:
        Validated immutable run evidence suitable for reproducibility summaries.
    """
    return load_large_run_artifacts(report_path, request_log_path)


@cli.command("summarize")
@click.option("--report", "reports", type=click.Path(path_type=Path), multiple=True, required=True)
@click.option(
    "--request-log", "request_logs", type=click.Path(path_type=Path), multiple=True, required=True
)
def summarize_command(reports: tuple[Path, ...], request_logs: tuple[Path, ...]) -> None:
    """Summarize exactly three local report/run sets without network access."""
    try:
        if len(reports) != 3 or len(request_logs) != 3:
            raise LargeLLMError("summarize requires exactly three report/run sets")
        runs = tuple(
            load_large_run_report(report_path, request_log_path)
            for report_path, request_log_path in zip(reports, request_logs, strict=True)
        )
        payload = summarize_large_runs(runs)
        _emit({"status": "ready", **payload})
    except LargeLLMError as error:
        _stop(error)


def main() -> int:
    """Run the JSON-emitting Click CLI and return its process status.

    Returns:
        Zero for a successful command. Failures raise ``SystemExit`` with a
        compact JSON payload already emitted by the command boundary.
    """
    cli.main(standalone_mode=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
