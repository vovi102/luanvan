#!/usr/bin/env python
"""Predict and evaluate the GoogleSQL B0 baseline from local artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from nl2sparql.dataset.templates import TEMPLATES_PATH
from nl2sparql.linking import ClassResolverError
from nl2sparql.linking.class_resolver import ClassResolver
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import (
    DEFAULT_MODEL_ID,
    EntityCachePaths,
    EntityDocumentError,
    EntityIndexError,
    EntityLinker,
    build_entity_corpus,
)
from nl2sparql.linking.entity import (
    DOCUMENT_VERSION as ENTITY_DOCUMENT_VERSION,
)
from nl2sparql.linking.entity import (
    load_index as load_entity_index,
)
from nl2sparql.linking.schema import (
    DOCUMENT_VERSION as SCHEMA_DOCUMENT_VERSION,
)
from nl2sparql.linking.schema import (
    SchemaCachePaths,
    SchemaDocumentError,
    SchemaIndexError,
    SchemaLinker,
    build_schema_elements,
    load_synonyms,
)
from nl2sparql.linking.schema import (
    load_index as load_schema_index,
)
from nl2sparql.models.b0 import (
    B0Error,
    B0EvaluationError,
    BaselineB0,
    LinkingProvenance,
    evaluate_b0,
    load_b0_cases,
    validate_b0_question,
)
from nl2sparql.sql.schema import CATALOG_PATH, SchemaCatalogError, load_catalog

DEFAULT_CACHE_DIRECTORY = Path(__file__).resolve().parents[1] / "src/nl2sparql/linking/cache"
DEFAULT_SYNONYMS_PATH = (
    Path(__file__).resolve().parents[1] / "src/nl2sparql/linking/schema/synonyms.json"
)
DEFAULT_TEST_SET = Path("data/eval/test-100.jsonl")
DEFAULT_PREDICTIONS = Path("data/eval/predictions/b0_test.jsonl")
DEFAULT_REPORT = Path("reports/b0_evaluation.json")
DEFAULT_REPOSITORY = Path(__file__).resolve().parents[1]

BaselineFactory = Callable[[Path], BaselineB0]


class ExternalEvidenceUnavailableError(B0EvaluationError):
    """A required local artifact or model snapshot is unavailable."""


class ReportPublicationError(B0EvaluationError):
    """Evaluation artifacts could not be published safely."""


class ProvenanceError(B0EvaluationError):
    """Git provenance could not be established."""


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _required_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ExternalEvidenceUnavailableError(f"missing required {label}: {path}")


def _production_baseline(templates_path: Path) -> BaselineB0:
    """Construct B0 only from accepted local cache and model snapshots."""
    for label, path in (
        ("templates", templates_path),
        ("catalog", CATALOG_PATH),
        ("schema synonyms", DEFAULT_SYNONYMS_PATH),
    ):
        _required_file(path, label)
    schema_paths = SchemaCachePaths.from_directory(DEFAULT_CACHE_DIRECTORY)
    entity_paths = EntityCachePaths.from_directory(DEFAULT_CACHE_DIRECTORY)
    for label, path in (
        ("schema index manifest", schema_paths.manifest),
        ("schema index lock", schema_paths.lock),
        ("entity index manifest", entity_paths.manifest),
        ("entity index lock", entity_paths.lock),
    ):
        _required_file(path, label)
    try:
        catalog_bytes = CATALOG_PATH.read_bytes()
        synonyms_bytes = DEFAULT_SYNONYMS_PATH.read_bytes()
        catalog = load_catalog(CATALOG_PATH, snapshot=catalog_bytes)
        synonyms = load_synonyms(DEFAULT_SYNONYMS_PATH, snapshot=synonyms_bytes)
        schema_elements = build_schema_elements(catalog, synonyms)
        schema_index = load_schema_index(
            schema_paths,
            hashlib.sha256(catalog_bytes).hexdigest(),
            DEFAULT_MODEL_ID,
            SCHEMA_DOCUMENT_VERSION,
            schema_elements,
        )
        corpus = build_entity_corpus(DictionaryArtifacts())
        entity_index = load_entity_index(
            entity_paths,
            corpus,
            DEFAULT_MODEL_ID,
            document_version=ENTITY_DOCUMENT_VERSION,
        )
        class_resolver = ClassResolver(CATALOG_PATH, corpus)
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(DEFAULT_MODEL_ID, local_files_only=True)
    except (
        EntityDocumentError,
        EntityIndexError,
        ClassResolverError,
        ImportError,
        OSError,
        RuntimeError,
        SchemaCatalogError,
        SchemaDocumentError,
        SchemaIndexError,
    ) as exc:
        raise ExternalEvidenceUnavailableError(
            f"local linking evidence is unavailable: {exc}"
        ) from exc
    provenance = LinkingProvenance(
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
    )
    return BaselineB0(
        templates_path,
        schema_linker=SchemaLinker(schema_index, encoder, synonyms),
        entity_linker=EntityLinker(corpus, entity_index, encoder),
        class_resolver=class_resolver,
        linking_provenance=provenance,
    )


def _paths_alias(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except (OSError, RuntimeError) as exc:
        raise ReportPublicationError(f"unable to compare artifact paths: {exc}") from exc


def _protect_outputs(predictions: Path, report: Path, protected: Mapping[str, Path]) -> None:
    if _paths_alias(predictions, report):
        raise ReportPublicationError("predictions and report paths must be distinct")
    for label, path in protected.items():
        if _paths_alias(predictions, path) or _paths_alias(report, path):
            raise ReportPublicationError(f"output path must not overwrite {label}")


def _production_inputs(test_set: Path, templates_path: Path) -> dict[str, Path]:
    artifacts = DictionaryArtifacts()
    protected = {
        "test set": test_set,
        "templates": templates_path,
        "catalog": CATALOG_PATH,
        "schema synonyms": DEFAULT_SYNONYMS_PATH,
        "dictionary entities": artifacts.entities_path,
        "dictionary concepts": artifacts.concepts_path,
        "dictionary aliases": artifacts.aliases_path,
        "dictionary sources": artifacts.sources_path,
        "schema index manifest": SchemaCachePaths.from_directory(DEFAULT_CACHE_DIRECTORY).manifest,
        "schema index lock": SchemaCachePaths.from_directory(DEFAULT_CACHE_DIRECTORY).lock,
        "entity index manifest": EntityCachePaths.from_directory(DEFAULT_CACHE_DIRECTORY).manifest,
        "entity index lock": EntityCachePaths.from_directory(DEFAULT_CACHE_DIRECTORY).lock,
    }
    for index, path in enumerate(sorted(DEFAULT_CACHE_DIRECTORY.glob("*-index*.npz"))):
        protected[f"index matrix {index}"] = path
    return protected


def _existing_bytes(path: Path) -> bytes | None:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise ReportPublicationError(f"unsafe existing artifact: {path}")
        return path.read_bytes()
    except OSError as exc:
        raise ReportPublicationError(f"unable to inspect existing artifact: {exc}") from exc


def _atomic_replace(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _existing_bytes(path)
        parent = path.parent.resolve(strict=True)
        descriptor, raw_temporary = tempfile.mkstemp(dir=parent, prefix=f".{path.name}.")
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except ReportPublicationError:
        raise
    except OSError as exc:
        raise ReportPublicationError(f"unable to publish artifact: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_evaluation_artifacts(
    predictions_path: Path,
    report_path: Path,
    prediction_rows: Sequence[Mapping[str, Any]],
    report: Mapping[str, Any],
) -> None:
    """Publish predictions first and the acceptance report last, with rollback.

    Args:
        predictions_path: Destination JSONL path for per-case predictions.
        report_path: Destination JSON path for the aggregate report.
        prediction_rows: Serializable per-case prediction mappings.
        report: Serializable report body before its checksum is attached.

    Raises:
        ReportPublicationError: If atomic publication or rollback fails.
    """
    previous_predictions = _existing_bytes(predictions_path)
    prediction_payload = b"".join(_canonical_json(dict(row)) for row in prediction_rows)
    report_body = dict(report)
    report_payload = _canonical_json(
        {
            **report_body,
            "report_sha256": hashlib.sha256(_canonical_json(report_body)).hexdigest(),
        }
    )
    _atomic_replace(predictions_path, prediction_payload)
    try:
        _atomic_replace(report_path, report_payload)
    except ReportPublicationError:
        if previous_predictions is None:
            try:
                predictions_path.unlink(missing_ok=True)
            except OSError as exc:
                raise ReportPublicationError(
                    f"report publication failed and predictions rollback failed: {exc}"
                ) from exc
        else:
            _atomic_replace(predictions_path, previous_predictions)
        raise


def _git_provenance(repository: Path = DEFAULT_REPOSITORY) -> dict[str, object]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProvenanceError(f"unable to resolve Git provenance: {exc}") from exc
    if not len(sha) == 40 or any(character not in "0123456789abcdef" for character in sha):
        raise ProvenanceError("Git provenance must contain a full lowercase commit SHA")
    return {"git_sha": sha, "git_dirty": dirty}


def _emit(value: object) -> None:
    click.echo(_canonical_json(value).decode(), nl=False)


def _failure(command: str, error: Exception) -> int:
    if isinstance(error, ExternalEvidenceUnavailableError):
        status, cause, code = "blocked", "external_evidence_unavailable", 2
    elif isinstance(error, ReportPublicationError):
        status, cause, code = "failed", "publication_failure", 1
    elif isinstance(error, ProvenanceError):
        status, cause, code = "failed", "provenance_failure", 1
    elif isinstance(error, (B0Error, B0EvaluationError, ValueError)):
        status, cause, code = "failed", "invalid_input", 1
    else:
        status, cause, code = "failed", "internal_error", 1
    _emit({"status": status, "command": command, "cause": cause, "reason": str(error)})
    return code


def create_cli(*, baseline_factory: BaselineFactory = _production_baseline) -> click.Group:
    """Create the lazy B0 command group.

    Args:
        baseline_factory: Lazy constructor for the configured B0 baseline.

    Returns:
        Click command group with ``predict`` and ``evaluate`` commands.
    """

    @click.group()
    def cli() -> None:
        """Predict and evaluate the deterministic GoogleSQL B0 baseline."""

    @cli.command("predict")
    @click.option("--question", required=True)
    @click.option(
        "--templates",
        "templates_path",
        type=click.Path(path_type=Path),
        default=TEMPLATES_PATH,
        show_default=True,
    )
    def predict_command(question: str, templates_path: Path) -> None:
        """Predict one safe GoogleSQL query or emit an unmatched result."""
        try:
            _required_file(templates_path, "templates")
            validate_b0_question(question)
            prediction = baseline_factory(templates_path).predict_detailed(question)
            question_sha256 = hashlib.sha256(question.encode()).hexdigest()
            if prediction is None:
                _emit(
                    {
                        "status": "unmatched",
                        "command": "predict",
                        "question_sha256": question_sha256,
                    }
                )
            else:
                _emit(
                    {
                        "status": "ready",
                        "command": "predict",
                        "question_sha256": question_sha256,
                        "prediction": asdict(prediction),
                    }
                )
        except Exception as exc:
            raise click.exceptions.Exit(_failure("predict", exc)) from exc

    @cli.command("evaluate")
    @click.option(
        "--test-set", type=click.Path(path_type=Path), default=DEFAULT_TEST_SET, show_default=True
    )
    @click.option("--synthetic", is_flag=True, default=False)
    @click.option(
        "--predictions",
        "predictions_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_PREDICTIONS,
        show_default=True,
    )
    @click.option(
        "--report",
        "report_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_REPORT,
        show_default=True,
    )
    @click.option(
        "--templates",
        "templates_path",
        type=click.Path(path_type=Path),
        default=TEMPLATES_PATH,
        show_default=True,
    )
    def evaluate_command(
        test_set: Path,
        synthetic: bool,
        predictions_path: Path,
        report_path: Path,
        templates_path: Path,
    ) -> None:
        """Evaluate local B0 coverage, structural accuracy, and latency."""
        try:
            _required_file(test_set, "test set")
            _required_file(templates_path, "templates")
            _protect_outputs(
                predictions_path,
                report_path,
                _production_inputs(test_set, templates_path),
            )
            case_set = load_b0_cases(test_set, synthetic=synthetic)
            baseline = baseline_factory(templates_path)
            results, evaluation = evaluate_b0(baseline, case_set)
            report = {
                "schema_version": 1,
                "status": evaluation.local_status,
                **asdict(evaluation),
                **_git_provenance(),
            }
            publish_evaluation_artifacts(
                predictions_path,
                report_path,
                tuple(asdict(result) for result in results),
                report,
            )
            _emit(
                {
                    "status": evaluation.local_status,
                    "command": "evaluate",
                    "predictions": str(predictions_path),
                    "report": str(report_path),
                }
            )
        except Exception as exc:
            raise click.exceptions.Exit(_failure("evaluate", exc)) from exc

    return cli


def main() -> int:
    """Run the CLI with an integer exit code for the numbered wrapper.

    Returns:
        Process-style integer exit code.
    """
    try:
        create_cli().main(standalone_mode=False)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
