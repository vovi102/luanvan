#!/usr/bin/env python
"""Build, query, and evaluate the production GoogleSQL entity linker.

The command layer is deliberately small: every dependency with network or model
side effects is initialized only after deterministic input and cache checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from nl2sparql.linking.dictionary import ALIASES_PATH, CONCEPTS_PATH, ENTITIES_PATH, SOURCES_PATH
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import (
    DEFAULT_MODEL_ID,
    DOCUMENT_VERSION,
    Encoder,
    EntityCachePaths,
    EntityDocumentError,
    EntityEncoderUnavailableError,
    EntityEvaluationError,
    EntityIndexError,
    EntityLinker,
    EntityLinkerError,
    GitProvenance,
    build_entity_corpus,
    build_index,
    evaluate_linker,
    load_ground_truth,
    load_index,
)
from nl2sparql.linking.entity.contracts import required_text

DEFAULT_CACHE_DIRECTORY = Path("src/nl2sparql/linking/cache")
DEFAULT_GROUND_TRUTH_PATH = Path("data/eval/entity_link_groundtruth.jsonl")
DEFAULT_REPORT_PATH = Path("reports/entity_linker_evaluation.json")
DEFAULT_REPOSITORY = Path(__file__).resolve().parents[1]

EncoderLoader = Callable[[str, bool], Encoder]
EncoderFactory = Callable[[str], Encoder]
CorpusBuilder = Callable[[DictionaryArtifacts], Any]
GitProvenanceFactory = Callable[[Path], GitProvenance]

_GENERATION_RE = re.compile(r"^entity-index-[0-9a-f]{64}\.npz$")


class ExternalDependencyError(RuntimeError):
    """An unavailable external model dependency, rather than a program defect."""


class ProvenanceError(EntityLinkerError):
    """Git provenance could not be established reproducibly."""


class ExternalEvidenceUnavailableError(EntityLinkerError):
    """A required user-supplied evidence artifact is unavailable."""


class ReportPublicationError(EntityLinkerError):
    """A report could not be published while preserving the accepted destination."""


class _ReportDestination:
    """A report filename pinned to an opened, validated parent directory."""

    def __init__(self, parent: Path, directory_fd: int, filename: str) -> None:
        self.parent = parent
        self.directory_fd = directory_fd
        self.filename = filename

    @property
    def path(self) -> Path:
        return self.parent / self.filename

    def close(self) -> None:
        os.close(self.directory_fd)


def load_encoder(model_id: str, local_files_only: bool = False) -> Encoder:
    """Initialize the SentenceTransformer only inside a command callback."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ExternalDependencyError(f"unable to import model runtime: {exc}") from exc
    try:
        import httpx
    except ImportError:
        unavailable_errors: tuple[type[BaseException], ...] = (
            ConnectionError,
            OSError,
            TimeoutError,
        )
    else:
        unavailable_errors = (
            ConnectionError,
            OSError,
            TimeoutError,
            httpx.ConnectError,
            httpx.TimeoutException,
        )
    try:
        return SentenceTransformer(model_id, local_files_only=local_files_only)
    except unavailable_errors as exc:
        mode = "local files" if local_files_only else "model files"
        raise ExternalDependencyError(
            f"unable to initialize {mode} for {model_id!r}: {exc}"
        ) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _utc_timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise EntityLinkerError("report clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _report_tempfile(destination: _ReportDestination, suffix: str) -> tuple[int, str]:
    descriptor, raw_temporary = tempfile.mkstemp(
        dir=f"/proc/self/fd/{destination.directory_fd}",
        prefix=f".{destination.filename}.",
        suffix=suffix,
    )
    return descriptor, Path(raw_temporary).name


def _unlink_at(destination: _ReportDestination, name: str) -> None:
    try:
        os.unlink(name, dir_fd=destination.directory_fd)
    except FileNotFoundError:
        pass


def _backup_report(destination: _ReportDestination) -> str | None:
    try:
        existing = os.stat(
            destination.filename,
            dir_fd=destination.directory_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1:
        raise ReportPublicationError("existing report destination is an unsafe alias")
    descriptor, backup = _report_tempfile(destination, ".backup")
    os.close(descriptor)
    _unlink_at(destination, backup)
    try:
        os.link(
            destination.filename,
            backup,
            src_dir_fd=destination.directory_fd,
            dst_dir_fd=destination.directory_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ReportPublicationError(f"unable to back up accepted report: {exc}") from exc
    return backup


def _restore_report(
    destination: _ReportDestination, backup: str | None, replaced: bool
) -> str | None:
    if not replaced:
        return backup
    try:
        if backup is None:
            _unlink_at(destination, destination.filename)
        else:
            os.replace(
                backup,
                destination.filename,
                src_dir_fd=destination.directory_fd,
                dst_dir_fd=destination.directory_fd,
            )
            backup = None
        os.fsync(destination.directory_fd)
    except OSError as exc:
        raise ReportPublicationError(
            f"unable to restore accepted report after publication failure: {exc}"
        ) from exc
    return backup


def _atomic_write(destination: _ReportDestination, payload: bytes) -> None:
    """Publish through a pinned directory FD, restoring a prior report on runtime failure.

    A process crash between replacement and directory fsync still has filesystem-dependent
    durability semantics; the backup makes ordinary reported publication failures reversible.
    """
    descriptor, temporary = _report_tempfile(destination, ".tmp")
    backup: str | None = None
    replaced = False
    rollback_incomplete = False
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        backup = _backup_report(destination)
        if backup is not None:
            os.fsync(destination.directory_fd)
        os.replace(
            temporary,
            destination.filename,
            src_dir_fd=destination.directory_fd,
            dst_dir_fd=destination.directory_fd,
        )
        temporary = ""
        replaced = True
        os.fsync(destination.directory_fd)
    except ReportPublicationError:
        raise
    except OSError as exc:
        try:
            backup = _restore_report(destination, backup, replaced)
        except ReportPublicationError as rollback_error:
            rollback_incomplete = True
            raise ReportPublicationError(
                f"report publication failed and rollback was incomplete: {rollback_error}"
            ) from exc
        raise ReportPublicationError(f"unable to publish report: {exc}") from exc
    finally:
        if temporary:
            _unlink_at(destination, temporary)
        if backup is not None and not rollback_incomplete:
            _unlink_at(destination, backup)


def _open_report_destination(report_path: Path) -> _ReportDestination:
    filename = report_path.name
    if not filename:
        raise EntityLinkerError("report path must name a file")
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        parent = report_path.parent.resolve(strict=True)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(parent, flags)
        details = os.fstat(descriptor)
        if not stat.S_ISDIR(details.st_mode):
            raise ReportPublicationError("report parent is not a directory")
        return _ReportDestination(parent=parent, directory_fd=descriptor, filename=filename)
    except (OSError, RuntimeError) as exc:
        raise ReportPublicationError(f"unable to open report parent securely: {exc}") from exc


def _paths_alias(left: Path, right: Path) -> bool:
    """Compare lexical, symlink-resolved, and existing inode identities."""
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except (OSError, RuntimeError) as exc:
        raise EntityLinkerError(f"unable to resolve report path identity: {exc}") from exc


def _protect_report_path(report_path: Path, protected: Mapping[str, Path]) -> None:
    for label, input_path in protected.items():
        if _paths_alias(report_path, input_path):
            raise EntityLinkerError(f"report path must not overwrite {label}")


def _protect_generation_namespace(report_path: Path, cache_dir: Path) -> None:
    if _GENERATION_RE.fullmatch(report_path.name) and _paths_alias(report_path.parent, cache_dir):
        raise EntityLinkerError("report path must not overwrite an entity cache matrix generation")


def _required_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ExternalEvidenceUnavailableError(f"missing required {label}: {path}")


def _validated_model_id(model_id: object) -> str:
    try:
        value = required_text(model_id, "model ID")
    except EntityLinkerError as exc:
        raise EntityLinkerError("model ID must be non-empty, trimmed, and control-free") from exc
    if value != model_id:
        raise EntityLinkerError("model ID must be non-empty, trimmed, and control-free")
    return value


def _dictionary_artifacts(
    *, entities: Path, aliases: Path, concepts: Path, sources: Path
) -> DictionaryArtifacts:
    for label, path in (
        ("dictionary entities", entities),
        ("dictionary aliases", aliases),
        ("dictionary concepts", concepts),
        ("dictionary sources", sources),
    ):
        _required_file(path, label)
    return DictionaryArtifacts(
        entities_path=entities,
        aliases_path=aliases,
        concepts_path=concepts,
        sources_path=sources,
    )


def _load_cached_index(cache_dir: Path, corpus: Any, model_id: str):
    paths = EntityCachePaths.from_directory(cache_dir)
    _required_file(paths.manifest, "entity cache manifest")
    _required_file(paths.lock, "entity cache lock")
    return paths, load_index(paths, corpus, model_id, document_version=DOCUMENT_VERSION)


def _git_provenance(repository: Path) -> GitProvenance:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        resolved_repository = repository.resolve(strict=True)
        if not resolved_repository.is_dir():
            raise ProvenanceError("--repository must be a directory")
        top_level = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=resolved_repository,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout.strip()
        ).resolve(strict=True)
        if top_level != resolved_repository:
            raise ProvenanceError("--repository must resolve to the Git work tree top level")
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=resolved_repository,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=resolved_repository,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout
        )
        return GitProvenance(sha, dirty)
    except (OSError, RuntimeError, subprocess.CalledProcessError, EntityEvaluationError) as exc:
        raise ProvenanceError(f"unable to resolve repository git provenance: {exc}") from exc


def _evaluation_payload(report: Any, generated_at: str) -> bytes:
    body = {
        "schema_version": 1,
        "status": "ready",
        "generated_at": generated_at,
        **asdict(report),
    }
    return _canonical_json({**body, "report_sha256": _sha256(_canonical_json(body))})


def _emit(*, status: str, command: str, cause: str, reason: Exception | str) -> None:
    click.echo(
        json.dumps(
            {"status": status, "command": command, "cause": cause, "reason": str(reason)},
            sort_keys=True,
        )
    )


def _failure(command: str, error: Exception) -> int:
    if isinstance(error, (ExternalDependencyError, EntityEncoderUnavailableError)):
        _emit(status="blocked", command=command, cause="external_model_unavailable", reason=error)
        return 2
    if isinstance(error, ExternalEvidenceUnavailableError):
        _emit(
            status="blocked", command=command, cause="external_evidence_unavailable", reason=error
        )
        return 2
    if isinstance(error, ReportPublicationError):
        _emit(status="failed", command=command, cause="publication_failure", reason=error)
        return 1
    if isinstance(error, EntityIndexError):
        _emit(status="failed", command=command, cause="cache_integrity_failure", reason=error)
        return 1
    if isinstance(error, ProvenanceError):
        _emit(status="failed", command=command, cause="provenance_failure", reason=error)
        return 1
    if isinstance(
        error, (EntityDocumentError, EntityEvaluationError, EntityLinkerError, ValueError)
    ):
        _emit(status="failed", command=command, cause="invalid_input", reason=error)
        return 1
    _emit(status="failed", command=command, cause="internal_error", reason=error)
    return 1


def _command_name(args: Sequence[str] | None) -> str:
    if args and args[0] in {"build-index", "query", "evaluate"}:
        return args[0]
    return "cli"


def create_cli(
    *,
    encoder_loader: EncoderLoader | None = None,
    encoder_factory: EncoderFactory | None = None,
    corpus_builder: CorpusBuilder = build_entity_corpus,
    git_provenance_factory: GitProvenanceFactory = _git_provenance,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> click.Group:
    """Create a dependency-injectable CLI without initializing a model."""
    if encoder_loader is not None and encoder_factory is not None:
        raise ValueError("supply encoder_loader or encoder_factory, not both")
    if encoder_factory is not None:
        def compatibility_encoder_loader(model_id: str, _local_files_only: bool) -> Encoder:
            return encoder_factory(model_id)

        encoder_loader = compatibility_encoder_loader
    encoder_loader = encoder_loader or load_encoder

    @click.group()
    def cli() -> None:
        """Build, query, and evaluate the GoogleSQL entity linker."""

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

    def model_options(command):
        command = click.option("--model-id", default=DEFAULT_MODEL_ID, show_default=True)(command)
        return click.option(
            "--local-files-only",
            is_flag=True,
            default=False,
            help="Forbid model downloads and use only locally cached model files.",
        )(command)

    @cli.command("build-index")
    @click.option("--cache-dir", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIRECTORY)
    @dictionary_options
    @model_options
    def build_index_command(
        cache_dir: Path,
        entities: Path,
        aliases: Path,
        concepts: Path,
        sources: Path,
        model_id: str,
        local_files_only: bool,
    ) -> None:
        """Build and atomically publish a fresh embedding index."""
        command = "build-index"
        try:
            model_id = _validated_model_id(model_id)
            corpus = corpus_builder(
                _dictionary_artifacts(
                    entities=entities, aliases=aliases, concepts=concepts, sources=sources
                )
            )
            index = build_index(
                corpus,
                encoder_loader(model_id, local_files_only),
                EntityCachePaths.from_directory(cache_dir),
                model_id,
                document_version=DOCUMENT_VERSION,
            )
            click.echo(
                json.dumps(
                    {
                        "status": "ready",
                        "command": command,
                        "cache_manifest_sha256": index.metadata.manifest_file_sha256,
                        "cache_matrices_sha256": index.metadata.matrices_sha256,
                        "model_id": index.metadata.model_id,
                    },
                    sort_keys=True,
                )
            )
        except Exception as exc:
            raise click.exceptions.Exit(_failure(command, exc)) from exc

    @cli.command("query")
    @click.option("--question", required=True)
    @click.option("--cache-dir", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIRECTORY)
    @dictionary_options
    @model_options
    def query_command(
        question: str,
        cache_dir: Path,
        entities: Path,
        aliases: Path,
        concepts: Path,
        sources: Path,
        model_id: str,
        local_files_only: bool,
    ) -> None:
        """Resolve entity mentions in one question using a strict cached index."""
        command = "query"
        try:
            model_id = _validated_model_id(model_id)
            required_text(question, "question")
            corpus = corpus_builder(
                _dictionary_artifacts(
                    entities=entities, aliases=aliases, concepts=concepts, sources=sources
                )
            )
            _, index = _load_cached_index(cache_dir, corpus, model_id)
            matches = EntityLinker(corpus, index, encoder_loader(model_id, local_files_only)).link(
                question
            )
            click.echo(
                json.dumps(
                    {
                        "status": "ready",
                        "command": command,
                        "matches": [asdict(row) for row in matches],
                    },
                    sort_keys=True,
                )
            )
        except Exception as exc:
            raise click.exceptions.Exit(_failure(command, exc)) from exc

    @cli.command("evaluate")
    @click.option(
        "--ground-truth", type=click.Path(path_type=Path), default=DEFAULT_GROUND_TRUTH_PATH
    )
    @click.option(
        "--report", "report_path", type=click.Path(path_type=Path), default=DEFAULT_REPORT_PATH
    )
    @click.option("--repository", type=click.Path(path_type=Path), default=DEFAULT_REPOSITORY)
    @click.option("--cache-dir", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIRECTORY)
    @dictionary_options
    @model_options
    def evaluate_command(
        ground_truth: Path,
        report_path: Path,
        repository: Path,
        cache_dir: Path,
        entities: Path,
        aliases: Path,
        concepts: Path,
        sources: Path,
        model_id: str,
        local_files_only: bool,
    ) -> None:
        """Evaluate the strict cached index on 100 reviewed questions."""
        command = "evaluate"
        destination: _ReportDestination | None = None
        try:
            model_id = _validated_model_id(model_id)
            destination = _open_report_destination(report_path)
            paths = EntityCachePaths.from_directory(cache_dir)
            _protect_generation_namespace(destination.path, paths.manifest.parent)
            protected = {
                "ground truth": ground_truth,
                "dictionary entities": entities,
                "dictionary aliases": aliases,
                "dictionary concepts": concepts,
                "dictionary sources": sources,
                "cache manifest": paths.manifest,
                "cache matrix base": paths.matrices,
                "cache lock": paths.lock,
                **{
                    f"cache matrix generation {path.name}": path
                    for path in paths.manifest.parent.glob("entity-index-*.npz")
                },
            }
            _protect_report_path(destination.path, protected)
            corpus = corpus_builder(
                _dictionary_artifacts(
                    entities=entities, aliases=aliases, concepts=concepts, sources=sources
                )
            )
            _required_file(ground_truth, "ground-truth evidence")
            dataset = load_ground_truth(ground_truth, corpus)
            _, index = _load_cached_index(cache_dir, corpus, model_id)
            provenance = git_provenance_factory(repository)
            evaluation = evaluate_linker(
                EntityLinker(corpus, index, encoder_loader(model_id, local_files_only)),
                dataset,
                model_id=model_id,
                git_provenance=provenance,
            )
            _atomic_write(destination, _evaluation_payload(evaluation, _utc_timestamp(clock)))
            click.echo(
                json.dumps(
                    {"status": "ready", "command": command, "report": str(report_path)},
                    sort_keys=True,
                )
            )
        except Exception as exc:
            raise click.exceptions.Exit(_failure(command, exc)) from exc
        finally:
            if destination is not None:
                destination.close()

    return cli


def main(args: Sequence[str] | None = None) -> int:
    """Run the CLI programmatically, always returning its documented exit code."""
    effective_args = list(sys.argv[1:] if args is None else args)
    try:
        result = create_cli().main(args=effective_args, standalone_mode=False)
        return int(result or 0)
    except click.ClickException as exc:
        _emit(
            status="failed",
            command=_command_name(effective_args),
            cause="invalid_input",
            reason=exc,
        )
        return 1
    except click.Abort as exc:
        _emit(
            status="failed",
            command=_command_name(effective_args),
            cause="invalid_input",
            reason=exc,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
