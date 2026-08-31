#!/usr/bin/env python
"""Resolve and evaluate typed GoogleSQL entity constraints entirely offline."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from nl2sparql.linking.dictionary import (
    ALIASES_PATH,
    CONCEPTS_PATH,
    ENTITIES_PATH,
    SOURCES_PATH,
)
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import EntityCorpus, GitProvenance, build_entity_corpus
from nl2sparql.linking.resolver import (
    ClassResolver,
    ClassResolverError,
    ResolverEvaluationError,
    evaluate_resolver,
    load_resolver_ground_truth,
)
from nl2sparql.linking.resolver.evaluate import parse_entity_match
from nl2sparql.sql.schema import CATALOG_PATH

DEFAULT_GROUND_TRUTH_PATH = Path("data/eval/class_resolver_groundtruth.jsonl")
DEFAULT_REPORT_PATH = Path("reports/class_resolver_evaluation.json")
DEFAULT_REPOSITORY = Path(__file__).resolve().parents[1]

CorpusBuilder = Callable[[DictionaryArtifacts], EntityCorpus]
GitProvenanceFactory = Callable[[Path], GitProvenance]


class ExternalEvidenceUnavailableError(ClassResolverError):
    """A required user-supplied local evidence file is absent."""


class ReportPublicationError(ClassResolverError):
    """A report could not be published while preserving the accepted file."""


class ProvenanceError(ClassResolverError):
    """Git provenance could not be established reproducibly."""


class _DuplicateJsonKey(ValueError):
    pass


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _dictionary_artifacts(
    entities: Path, aliases: Path, concepts: Path, sources: Path
) -> DictionaryArtifacts:
    for label, path in (
        ("dictionary entities", entities),
        ("dictionary aliases", aliases),
        ("dictionary concepts", concepts),
        ("dictionary sources", sources),
    ):
        if not path.is_file():
            raise ExternalEvidenceUnavailableError(f"missing required {label}: {path}")
    return DictionaryArtifacts(entities, concepts, aliases, sources)


def _read_json_object(path: Path) -> Mapping[str, Any]:
    try:
        snapshot = path.read_bytes()
        value = json.loads(snapshot, object_pairs_hook=_json_object)
    except _DuplicateJsonKey as exc:
        raise ClassResolverError(f"duplicate JSON key {exc.args[0]!r}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassResolverError(f"unable to read input JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ClassResolverError("input JSON must be an object")
    return value


def _parse_resolve_payload(path: Path, corpus: EntityCorpus) -> tuple[str, tuple[Any, ...]]:
    raw = _read_json_object(path)
    if set(raw) != {"question", "matches"}:
        raise ClassResolverError("input JSON must contain exact keys question and matches")
    question = raw["question"]
    if not isinstance(question, str):
        raise ClassResolverError("input question must be a string")
    raw_matches = raw["matches"]
    if not isinstance(raw_matches, list):
        raise ClassResolverError("input matches must be an array")
    matches = tuple(parse_entity_match(value, question, corpus, 1) for value in raw_matches)
    return question, matches


def _paths_alias(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except (OSError, RuntimeError) as exc:
        raise ClassResolverError(f"unable to compare path identity: {exc}") from exc


def _protect_report_path(report: Path, protected: Mapping[str, Path]) -> None:
    for label, path in protected.items():
        if _paths_alias(report, path):
            raise ClassResolverError(f"report path must not overwrite {label}")


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        parent = path.parent.resolve(strict=True)
        if path.exists() or path.is_symlink():
            details = path.lstat()
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                raise ReportPublicationError("existing report is an unsafe alias")
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
        raise ReportPublicationError(f"unable to publish report: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _git_provenance(repository: Path) -> GitProvenance:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        root = repository.resolve(strict=True)
        if not root.is_dir():
            raise ProvenanceError("repository must be a directory")
        top = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout.strip()
        ).resolve(strict=True)
        if top != root:
            raise ProvenanceError("repository must be the Git worktree root")
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout
        )
        return GitProvenance(sha, dirty)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        raise ProvenanceError(f"unable to resolve git provenance: {exc}") from exc


def _report_payload(report: object) -> bytes:
    body = {"schema_version": 1, "status": "ready", **asdict(report)}
    return _canonical_json(
        {**body, "report_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    )


def _emit(status: str, command: str, cause: str, reason: object) -> None:
    click.echo(
        _canonical_json(
            {"status": status, "command": command, "cause": cause, "reason": str(reason)}
        ).decode(),
        nl=False,
    )


def _failure(command: str, error: Exception) -> int:
    if isinstance(error, ExternalEvidenceUnavailableError):
        _emit("blocked", command, "external_evidence_unavailable", error)
        return 2
    if isinstance(error, ReportPublicationError):
        _emit("failed", command, "publication_failure", error)
        return 1
    if isinstance(error, ProvenanceError):
        _emit("failed", command, "provenance_failure", error)
        return 1
    if isinstance(error, (ClassResolverError, ResolverEvaluationError, ValueError)):
        _emit("failed", command, "invalid_input", error)
        return 1
    _emit("failed", command, "internal_error", error)
    return 1


def create_cli(
    *,
    corpus_builder: CorpusBuilder = build_entity_corpus,
    git_provenance_factory: GitProvenanceFactory = _git_provenance,
) -> click.Group:
    """Create a dependency-injectable CLI with no import-time side effects."""

    @click.group()
    def cli() -> None:
        """Resolve and evaluate GoogleSQL entity constraints offline."""

    def dictionary_options(command):
        command = click.option(
            "--entities", type=click.Path(path_type=Path), default=ENTITIES_PATH
        )(command)
        command = click.option("--aliases", type=click.Path(path_type=Path), default=ALIASES_PATH)(
            command
        )
        command = click.option(
            "--concepts", type=click.Path(path_type=Path), default=CONCEPTS_PATH
        )(command)
        return click.option("--sources", type=click.Path(path_type=Path), default=SOURCES_PATH)(
            command
        )

    @cli.command("resolve")
    @click.option("--input", "input_path", type=click.Path(path_type=Path), required=True)
    @click.option("--catalog", type=click.Path(path_type=Path), default=CATALOG_PATH)
    @dictionary_options
    def resolve_command(
        input_path: Path,
        catalog: Path,
        entities: Path,
        aliases: Path,
        concepts: Path,
        sources: Path,
    ) -> None:
        """Resolve one typed T4.2 match payload and print canonical JSON."""
        command = "resolve"
        try:
            corpus = corpus_builder(_dictionary_artifacts(entities, aliases, concepts, sources))
            question, matches = _parse_resolve_payload(input_path, corpus)
            plan = ClassResolver(catalog, corpus).resolve(question, matches)
            click.echo(
                _canonical_json(
                    {"status": "ready", "command": command, "plan": asdict(plan)}
                ).decode(),
                nl=False,
            )
        except Exception as exc:
            raise click.exceptions.Exit(_failure(command, exc)) from exc

    @cli.command("evaluate")
    @click.option(
        "--ground-truth", type=click.Path(path_type=Path), default=DEFAULT_GROUND_TRUTH_PATH
    )
    @click.option("--report", type=click.Path(path_type=Path), default=DEFAULT_REPORT_PATH)
    @click.option("--repository", type=click.Path(path_type=Path), default=DEFAULT_REPOSITORY)
    @click.option("--catalog", type=click.Path(path_type=Path), default=CATALOG_PATH)
    @dictionary_options
    def evaluate_command(
        ground_truth: Path,
        report: Path,
        repository: Path,
        catalog: Path,
        entities: Path,
        aliases: Path,
        concepts: Path,
        sources: Path,
    ) -> None:
        """Evaluate exactly 50 independently reviewed local cases."""
        command = "evaluate"
        try:
            _protect_report_path(
                report,
                {
                    "ground truth": ground_truth,
                    "analytical catalog": catalog,
                    "dictionary entities": entities,
                    "dictionary aliases": aliases,
                    "dictionary concepts": concepts,
                    "dictionary sources": sources,
                },
            )
            if not ground_truth.is_file():
                raise ExternalEvidenceUnavailableError(
                    f"missing required resolver ground truth: {ground_truth}"
                )
            corpus = corpus_builder(_dictionary_artifacts(entities, aliases, concepts, sources))
            dataset = load_resolver_ground_truth(ground_truth, corpus)
            evaluation = evaluate_resolver(
                ClassResolver(catalog, corpus),
                dataset,
                git_provenance_factory(repository),
            )
            _atomic_write(report, _report_payload(evaluation))
            click.echo(
                _canonical_json(
                    {"status": "ready", "command": command, "report": str(report)}
                ).decode(),
                nl=False,
            )
        except Exception as exc:
            raise click.exceptions.Exit(_failure(command, exc)) from exc

    return cli


def main(args: Sequence[str] | None = None) -> int:
    """Run the CLI programmatically and return its documented exit code."""
    effective = list(sys.argv[1:] if args is None else args)
    try:
        result = create_cli().main(args=effective, standalone_mode=False)
        return int(result or 0)
    except click.ClickException as exc:
        _emit("failed", effective[0] if effective else "cli", "invalid_input", exc)
        return 1
    except click.Abort as exc:
        _emit("failed", effective[0] if effective else "cli", "invalid_input", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
