"""Offline-first command line interface for canonical NL2SQL evaluation artifacts."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import click

from nl2sparql.evaluation import adapt_baseline_artifacts
from nl2sparql.evaluation.adapters import B0AdaptRequest, B12AdaptRequest
from nl2sparql.evaluation.artifacts import (
    FileExecutionJournal,
    canonical_json,
    load_and_verify_artifact,
    publish_immutable,
    serialize_comparison_report,
    serialize_evaluation_report,
    serialize_execution_evidence,
    serialize_prediction_run,
    serialize_shared_execution_evidence,
    validate_new_artifact_path,
    verify_execution_evidence_journal,
)
from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CanonicalPredictionRun,
    EvaluationError,
    EvaluationReport,
    ExecutionEvidence,
    ExecutionPolicy,
    PricingPolicy,
    SharedExecutionEvidence,
)
from nl2sparql.evaluation.execution import execute_run
from nl2sparql.evaluation.executor import QueryExecutor
from nl2sparql.evaluation.failures import load_manual_failure_reviews
from nl2sparql.evaluation.reporting import build_report, compare_reports
from nl2sparql.evaluation.shared_config import load_shared_config, require_live_approval
from nl2sparql.evaluation.shared_execution import (
    execute_shared_campaign,
    verify_shared_execution_journal,
)

BigQueryExecutorFactory = Callable[..., QueryExecutor]


def _emit(payload: Mapping[str, object]) -> None:
    click.echo(canonical_json(payload).decode(), nl=False)


class _JsonGroup(click.Group):
    """Render non-help Click errors as one deterministic JSON object."""

    def main(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["standalone_mode"] = False
        try:
            result = super().main(*args, **kwargs)
            if isinstance(result, int):
                raise SystemExit(result)
            return result
        except click.ClickException as exc:
            _emit({"error": exc.format_message(), "status": "failed"})
            raise SystemExit(exc.exit_code) from None


def _publish(path: Path, payload: bytes, protected: Sequence[Path]) -> None:
    publish_immutable(path, payload, protected_paths=protected)


def _loaded(path: Path, expected: type[Any]) -> Any:
    artifact = load_and_verify_artifact(path)
    if not isinstance(artifact, expected):
        raise EvaluationError(f"{path} has an unexpected artifact type; expected {expected}")
    return artifact


def _verify_execution_journal(evidence, path):
    if isinstance(evidence, SharedExecutionEvidence):
        verify_shared_execution_journal(evidence, path)
    else:
        verify_execution_evidence_journal(evidence, path)


def _decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise click.UsageError(f"{field} must be a decimal") from exc
    if not parsed.is_finite():
        raise click.UsageError(f"{field} must be finite")
    return parsed


def create_cli(*, bigquery_executor_factory: BigQueryExecutorFactory | None = None) -> click.Group:
    """Create a dependency-injected CLI without credential or network side effects."""

    @click.group(cls=_JsonGroup)
    def cli() -> None:
        """Adapt, execute, report, compare and validate NL2SQL evidence."""

    @cli.group("adapt")
    def adapt_group() -> None:
        """Adapt baseline-native evidence to a canonical prediction run."""

    @adapt_group.command("b0")
    @click.option("--test-set", type=click.Path(path_type=Path), required=True)
    @click.option("--predictions", type=click.Path(path_type=Path), required=True)
    @click.option("--report", "report_path", type=click.Path(path_type=Path), required=True)
    @click.option("--run-id", required=True)
    @click.option("--privacy-review", type=click.Path(path_type=Path))
    @click.option("--synthetic", is_flag=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def adapt_b0_command(
        test_set: Path,
        predictions: Path,
        report_path: Path,
        run_id: str,
        privacy_review: Path | None,
        synthetic: bool,
        output: Path,
    ) -> None:
        """Adapt deterministic B0 artifacts."""
        try:
            run = adapt_baseline_artifacts(
                B0AdaptRequest(
                    test_set, predictions, report_path, run_id, privacy_review, synthetic
                )
            )
            protected = tuple(
                path
                for path in (test_set, predictions, report_path, privacy_review)
                if path is not None
            )
            _publish(output, serialize_prediction_run(run), protected)
            _emit({"artifact": str(output), "status": "complete"})
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @adapt_group.command("b12")
    @click.option("--language", type=click.Choice(["en", "vi"]), default="en")
    @click.option("--benchmark-root", type=click.Path(path_type=Path), default=None)
    @click.option("--test-set", type=click.Path(path_type=Path), required=True)
    @click.option("--predictions", type=click.Path(path_type=Path), required=True)
    @click.option("--log", "log_path", type=click.Path(path_type=Path), required=True)
    @click.option("--report", "report_path", type=click.Path(path_type=Path), required=True)
    @click.option("--privacy-review", type=click.Path(path_type=Path))
    @click.option("--synthetic", is_flag=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def adapt_b12_command(
        language: str,
        benchmark_root: Path | None,
        test_set: Path,
        predictions: Path,
        log_path: Path,
        report_path: Path,
        privacy_review: Path | None,
        synthetic: bool,
        output: Path,
    ) -> None:
        """Adapt B1/B2 artifacts."""
        try:
            run = adapt_baseline_artifacts(
                B12AdaptRequest(
                    test_set,
                    predictions,
                    log_path,
                    report_path,
                    privacy_review,
                    synthetic,
                    language=language,
                    **({"source_root": benchmark_root} if benchmark_root is not None else {}),
                )
            )
            protected = tuple(
                path
                for path in (test_set, predictions, log_path, report_path, privacy_review)
                if path is not None
            )
            _publish(output, serialize_prediction_run(run), protected)
            _emit({"artifact": str(output), "status": "complete"})
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @cli.command("execute")
    @click.option("--prediction-run", type=click.Path(path_type=Path), required=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    @click.option("--journal", type=click.Path(path_type=Path), required=True)
    @click.option("--execution-id", required=True)
    @click.option("--executor", type=click.Choice(["bigquery"]), required=True)
    @click.option("--allow-bigquery", is_flag=True)
    @click.option("--project", required=True)
    @click.option("--location", required=True)
    @click.option("--timeout-seconds", type=float, required=True)
    @click.option("--per-query-byte-cap", type=int, required=True)
    @click.option("--aggregate-byte-cap", type=int, required=True)
    @click.option("--aggregate-billed-byte-cap", type=int, required=True)
    @click.option("--estimated-cost-cap", required=True)
    @click.option("--pricing-id", required=True)
    @click.option("--price-per-tib", required=True)
    @click.option("--pricing-source-sha256", required=True)
    def execute_command(
        prediction_run: Path,
        output: Path,
        journal: Path,
        execution_id: str,
        executor: str,
        allow_bigquery: bool,
        project: str,
        location: str,
        timeout_seconds: float,
        per_query_byte_cap: int,
        aggregate_byte_cap: int,
        aggregate_billed_byte_cap: int,
        estimated_cost_cap: str,
        pricing_id: str,
        price_per_tib: str,
        pricing_source_sha256: str,
    ) -> None:
        """Execute with explicit live BigQuery opt-in and pinned guards."""
        del executor
        if not allow_bigquery:
            raise click.UsageError("BigQuery execution requires --allow-bigquery")
        try:
            policy = ExecutionPolicy(
                project,
                location,
                timeout_seconds,
                per_query_byte_cap,
                aggregate_byte_cap,
                _decimal(estimated_cost_cap, "estimated-cost-cap"),
                PricingPolicy(
                    pricing_id,
                    "USD",
                    _decimal(price_per_tib, "price-per-tib"),
                    pricing_source_sha256,
                ),
                aggregate_billed_byte_cap,
            )
            run = _loaded(prediction_run, CanonicalPredictionRun)
            validate_new_artifact_path(output, protected_paths=(prediction_run, journal))
            file_journal = FileExecutionJournal.create(
                journal,
                header={"execution_id": execution_id},
                protected_paths=(prediction_run, output),
            )
            factory = bigquery_executor_factory
            if factory is None:
                from nl2sparql.evaluation.bigquery import create_bigquery_executor

                factory = create_bigquery_executor
            live_executor = factory(policy, allow_bigquery=True)
            evidence = execute_run(
                run,
                execution_id=execution_id,
                policy=policy,
                executor=live_executor,
                journal=file_journal,
            )
            verify_execution_evidence_journal(evidence, journal)
            _publish(
                output,
                serialize_execution_evidence(evidence),
                (prediction_run, journal),
            )
            _emit({"artifact": str(output), "status": evidence.status})
            if evidence.status == "policy_breach" or any(
                query.status == "guard_blocked"
                for case in evidence.cases
                for query in (case.gold, case.prediction)
            ):
                raise click.exceptions.Exit(2)
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @cli.command("plan-shared")
    @click.option("--config", type=click.Path(path_type=Path), required=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def plan_shared_command(config: Path, output: Path) -> None:
        """Pin unique SQL and every logical use offline; perform no network requests."""
        try:
            _, _, _, scope, digest, protected = load_shared_config(config)
            _publish(
                output,
                canonical_json(
                    {
                        "kind": "shared_campaign_plan_not_execution_evidence",
                        "scope_sha256": digest,
                        "scope": scope,
                    }
                ),
                protected,
            )
            _emit({"artifact": str(output), "scope_sha256": digest, "status": "planned"})
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @cli.command("execute-shared")
    @click.option("--config", type=click.Path(path_type=Path), required=True)
    @click.option("--allow-bigquery", is_flag=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    @click.option("--journal", type=click.Path(path_type=Path), required=True)
    def execute_shared_command(
        config: Path, allow_bigquery: bool, output: Path, journal: Path
    ) -> None:
        """Execute an approved free-only campaign with one job per exact SQL."""
        if not allow_bigquery:
            raise click.UsageError("BigQuery execution requires --allow-bigquery")
        try:
            settings, runs, policy, _, digest, protected = load_shared_config(config)
            require_live_approval(settings, digest, policy)
            protected = (*protected, Path(settings["free_only"]["evidence"]["path"]))
            validate_new_artifact_path(output, protected_paths=(*protected, journal))
            file_journal = FileExecutionJournal.create(
                journal, header={"scope_sha256": digest}, protected_paths=(*protected, output)
            )
            factory = bigquery_executor_factory
            if factory is None:
                from nl2sparql.evaluation.bigquery import create_bigquery_executor

                factory = create_bigquery_executor
            live_executor = factory(policy, allow_bigquery=True)
            evidence = execute_shared_campaign(
                runs,
                campaign_id=settings["campaign_id"],
                source_context_sha256=settings["source_context"]["file_sha256"],
                policy=policy,
                executor=live_executor,
                journal=file_journal,
            )
            verify_shared_execution_journal(evidence, journal)
            _publish(output, serialize_shared_execution_evidence(evidence), (*protected, journal))
            _emit({"artifact": str(output), "status": evidence.status})
            if evidence.status != "complete":
                raise click.exceptions.Exit(2)
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @cli.command("report")
    @click.option("--primary-run", type=click.Path(path_type=Path), required=True)
    @click.option("--primary-evidence", type=click.Path(path_type=Path), required=True)
    @click.option("--primary-journal", type=click.Path(path_type=Path), required=True)
    @click.option("--replicate-run", type=click.Path(path_type=Path), multiple=True)
    @click.option("--replicate-evidence", type=click.Path(path_type=Path), multiple=True)
    @click.option("--replicate-journal", type=click.Path(path_type=Path), multiple=True)
    @click.option("--manual-failure-reviews", type=click.Path(path_type=Path))
    @click.option("--bootstrap-samples", type=int, default=10_000, show_default=True)
    @click.option("--bootstrap-seed", type=int, default=42, show_default=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def report_command(
        primary_run: Path,
        primary_evidence: Path,
        primary_journal: Path,
        replicate_run: tuple[Path, ...],
        replicate_evidence: tuple[Path, ...],
        replicate_journal: tuple[Path, ...],
        manual_failure_reviews: Path | None,
        bootstrap_samples: int,
        bootstrap_seed: int,
        output: Path,
    ) -> None:
        """Build an offline report from one explicit primary pair."""
        try:
            if not (len(replicate_run) == len(replicate_evidence) == len(replicate_journal)):
                raise EvaluationError(
                    "replicate run/evidence/journal options must have equal counts"
                )
            run = _loaded(primary_run, CanonicalPredictionRun)
            evidence = _loaded(primary_evidence, (ExecutionEvidence, SharedExecutionEvidence))
            _verify_execution_journal(evidence, primary_journal)
            replicates = tuple(
                (
                    _loaded(run_path, CanonicalPredictionRun),
                    _loaded(ev_path, (ExecutionEvidence, SharedExecutionEvidence)),
                )
                for run_path, ev_path in zip(replicate_run, replicate_evidence, strict=True)
            )
            for (_, replicate), journal_path in zip(replicates, replicate_journal, strict=True):
                _verify_execution_journal(replicate, journal_path)
            reviews = (
                load_manual_failure_reviews(manual_failure_reviews)
                if manual_failure_reviews is not None
                else ()
            )
            report = build_report(
                primary_run=run,
                primary_evidence=evidence,
                replicate_pairs=replicates,
                bootstrap_policy=BootstrapPolicy(bootstrap_samples, bootstrap_seed),
                manual_reviews=reviews,
            )
            protected = (
                primary_run,
                primary_evidence,
                primary_journal,
                *replicate_run,
                *replicate_evidence,
                *replicate_journal,
                *((manual_failure_reviews,) if manual_failure_reviews is not None else ()),
            )
            _publish(output, serialize_evaluation_report(report), protected)
            _emit(
                {
                    "artifact": str(output),
                    "implementation_status": report.readiness.implementation_status,
                    "scientific_status": report.readiness.scientific_status,
                    "status": "complete",
                }
            )
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @cli.command("compare")
    @click.option("--left", type=click.Path(path_type=Path), required=True)
    @click.option("--right", type=click.Path(path_type=Path), required=True)
    @click.option("--bootstrap-samples", type=int, default=10_000, show_default=True)
    @click.option("--bootstrap-seed", type=int, default=42, show_default=True)
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def compare_command(
        left: Path,
        right: Path,
        bootstrap_samples: int,
        bootstrap_seed: int,
        output: Path,
    ) -> None:
        """Build an offline paired left-minus-right comparison."""
        try:
            comparison = compare_reports(
                _loaded(left, EvaluationReport),
                _loaded(right, EvaluationReport),
                bootstrap_policy=BootstrapPolicy(bootstrap_samples, bootstrap_seed),
            )
            _publish(output, serialize_comparison_report(comparison), (left, right))
            _emit(
                {
                    "artifact": str(output),
                    "scientific_status": comparison.readiness.scientific_status,
                    "status": "complete",
                }
            )
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    @cli.command("validate")
    @click.option("--journal", "journals", type=click.Path(path_type=Path), multiple=True)
    @click.argument("paths", type=click.Path(path_type=Path), nargs=-1, required=True)
    def validate_command(paths: tuple[Path, ...], journals: tuple[Path, ...]) -> None:
        """Verify canonical local artifacts without network access."""
        try:
            artifacts = tuple(load_and_verify_artifact(path) for path in paths)
            execution_artifacts = tuple(
                artifact
                for artifact in artifacts
                if isinstance(artifact, (ExecutionEvidence, SharedExecutionEvidence))
            )
            if len(execution_artifacts) != len(journals):
                raise EvaluationError("every execution evidence artifact requires one --journal")
            for evidence, journal_path in zip(execution_artifacts, journals, strict=True):
                _verify_execution_journal(evidence, journal_path)
            types = tuple(type(artifact).__name__ for artifact in artifacts)
            _emit({"artifact_types": types, "count": len(paths), "status": "valid"})
        except (EvaluationError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc

    return cli


def main(args: Sequence[str] | None = None) -> int:
    """Run the CLI and return its process exit code."""
    effective = list(sys.argv[1:] if args is None else args)
    try:
        result = create_cli().main(args=effective, standalone_mode=False)
        return int(result or 0)
    except SystemExit as exc:
        return int(exc.code or 0)
    except click.ClickException as exc:
        _emit({"error": exc.format_message(), "status": "failed"})
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
