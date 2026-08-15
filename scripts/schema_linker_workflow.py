#!/usr/bin/env python
"""Build, query, and evaluate the production Plan B schema linker."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from nl2sparql.linking.schema import (
    DEFAULT_MODEL_ID,
    DOCUMENT_VERSION,
    Encoder,
    SchemaCachePaths,
    SchemaIndex,
    SchemaIndexError,
    SchemaLinker,
    SchemaLinkerError,
    build_index,
    build_schema_elements,
    load_index,
    load_synonyms,
)
from nl2sparql.linking.schema.evaluate import evaluate_linker, load_ground_truth
from nl2sparql.sql.schema import CATALOG_PATH, SchemaCatalogError, load_catalog

DEFAULT_CACHE_DIRECTORY = Path("src/nl2sparql/linking/cache")
DEFAULT_GROUND_TRUTH_PATH = Path("data/dataset/test/schema_linker_ground_truth.jsonl")
DEFAULT_REPORT_PATH = Path("reports/schema_linker_evaluation.json")
DEFAULT_SYNONYMS_PATH = Path(__file__).parents[1] / "src/nl2sparql/linking/schema/synonyms.json"

EncoderFactory = Callable[[str], Encoder]


class ExternalDependencyError(RuntimeError):
    """A missing model, package, or network resource blocks a model command."""


def _default_encoder_factory(model_id: str) -> Encoder:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_id)
    except Exception as exc:
        raise ExternalDependencyError(f"unable to initialize model {model_id!r}: {exc}") from exc


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _required_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing required file: {path}")


def _catalog_inputs(catalog_path: Path, synonyms_path: Path):
    _required_file(catalog_path)
    _required_file(synonyms_path)
    catalog_bytes = catalog_path.read_bytes()
    catalog = load_catalog(catalog_path)
    synonyms = load_synonyms(synonyms_path)
    elements = build_schema_elements(catalog, synonyms)
    return catalog_bytes, synonyms, elements


def _load_cached_index(
    cache_dir: Path,
    catalog_bytes: bytes,
    model_id: str,
) -> tuple[SchemaCachePaths, SchemaIndex]:
    paths = SchemaCachePaths.from_directory(cache_dir)
    _required_file(paths.manifest)
    _required_file(paths.matrices)
    _required_file(paths.lock)
    index = load_index(paths, _sha256(catalog_bytes), model_id, DOCUMENT_VERSION)
    return paths, index


def _validate_cutoffs(field_k: int, relation_k: int) -> None:
    for label, value in (("field_k", field_k), ("relation_k", relation_k)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SchemaLinkerError(f"{label} must be a positive integer")


def _emit_failure(command: str, status: str, error: Exception) -> None:
    click.echo(
        json.dumps(
            {"status": status, "command": command, "reason": str(error)},
            sort_keys=True,
        )
    )


def _is_external_failure(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ExternalDependencyError, ImportError, OSError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _emit_contract_failure(command: str, error: Exception) -> None:
    _emit_failure(command, "blocked" if _is_external_failure(error) else "failed", error)


def _utc_timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchemaLinkerError("report clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _evaluation_payload(
    *,
    report,
    index: SchemaIndex,
    paths: SchemaCachePaths,
    catalog_bytes: bytes,
    ground_truth_bytes: bytes,
    generated_at: str,
    git_sha: str,
) -> bytes:
    metrics = asdict(report)
    results = metrics.pop("results")
    cache_bytes = paths.manifest.read_bytes() + paths.matrices.read_bytes()
    body = {
        "schema_version": 1,
        "status": "ready",
        "generated_at": generated_at,
        "git_sha": git_sha,
        "catalog_sha256": _sha256(catalog_bytes),
        "cache_sha256": _sha256(cache_bytes),
        "ground_truth_sha256": _sha256(ground_truth_bytes),
        "model_id": index.metadata.model_id,
        "weights": asdict(index.metadata.weights),
        "metrics": metrics,
        "results": results,
    }
    output = {**body, "report_sha256": _sha256(_canonical_json(body))}
    return _canonical_json(output)


def create_cli(
    *,
    encoder_factory: EncoderFactory = _default_encoder_factory,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    git_sha_factory: Callable[[], str] = _git_sha,
) -> click.Group:
    """Create the Click group with lazy, injectable external dependencies."""

    @click.group()
    def cli() -> None:
        """Build, query, and evaluate the Plan B schema linker."""

    @cli.command("build-index")
    @click.option(
        "--catalog",
        "catalog_path",
        type=click.Path(path_type=Path),
        default=CATALOG_PATH,
        show_default=True,
    )
    @click.option(
        "--synonyms",
        "synonyms_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_SYNONYMS_PATH,
        show_default=True,
    )
    @click.option(
        "--cache-dir",
        type=click.Path(path_type=Path),
        default=DEFAULT_CACHE_DIRECTORY,
        show_default=True,
    )
    @click.option("--model-id", default=DEFAULT_MODEL_ID, show_default=True)
    def build_index_command(
        catalog_path: Path, synonyms_path: Path, cache_dir: Path, model_id: str
    ) -> None:
        """Build and atomically publish the embedding index."""
        try:
            catalog_bytes, _, elements = _catalog_inputs(catalog_path, synonyms_path)
            encoder = encoder_factory(model_id)
            index = build_index(
                elements,
                encoder,
                model_id,
                catalog_bytes,
                SchemaCachePaths.from_directory(cache_dir),
            )
            click.echo(
                json.dumps(
                    {
                        "status": "ready",
                        "command": "build-index",
                        "manifest_sha256": index.metadata.manifest_sha256,
                    },
                    sort_keys=True,
                )
            )
        except (ImportError, OSError, ExternalDependencyError) as exc:
            _emit_failure("build-index", "blocked", exc)
            raise click.exceptions.Exit(1) from exc
        except (SchemaCatalogError, SchemaLinkerError, ValueError) as exc:
            _emit_contract_failure("build-index", exc)
            raise click.exceptions.Exit(1) from exc

    @cli.command("query")
    @click.option("--question", required=True)
    @click.option(
        "--catalog",
        "catalog_path",
        type=click.Path(path_type=Path),
        default=CATALOG_PATH,
        show_default=True,
    )
    @click.option(
        "--synonyms",
        "synonyms_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_SYNONYMS_PATH,
        show_default=True,
    )
    @click.option(
        "--cache-dir",
        type=click.Path(path_type=Path),
        default=DEFAULT_CACHE_DIRECTORY,
        show_default=True,
    )
    @click.option("--model-id", default=DEFAULT_MODEL_ID, show_default=True)
    @click.option("--field-k", type=int, default=10, show_default=True)
    @click.option("--relation-k", type=int, default=5, show_default=True)
    def query_command(
        question: str,
        catalog_path: Path,
        synonyms_path: Path,
        cache_dir: Path,
        model_id: str,
        field_k: int,
        relation_k: int,
    ) -> None:
        """Rank cached schema relations and fields for one question."""
        try:
            _validate_cutoffs(field_k, relation_k)
            catalog_bytes, synonyms, _ = _catalog_inputs(catalog_path, synonyms_path)
            _, index = _load_cached_index(cache_dir, catalog_bytes, model_id)
            encoder = encoder_factory(model_id)
            linked = SchemaLinker(index, encoder, synonyms).link(
                question, top_k=max(field_k, relation_k)
            )
            click.echo(
                json.dumps(
                    {
                        "status": "ready",
                        "relations": [asdict(row) for row in linked.relations[:relation_k]],
                        "fields": [asdict(row) for row in linked.fields[:field_k]],
                    },
                    sort_keys=True,
                )
            )
        except (ImportError, OSError, ExternalDependencyError) as exc:
            _emit_failure("query", "blocked", exc)
            raise click.exceptions.Exit(1) from exc
        except (SchemaCatalogError, SchemaIndexError, SchemaLinkerError, ValueError) as exc:
            _emit_contract_failure("query", exc)
            raise click.exceptions.Exit(1) from exc

    @cli.command("evaluate")
    @click.option(
        "--ground-truth",
        type=click.Path(path_type=Path),
        default=DEFAULT_GROUND_TRUTH_PATH,
        show_default=True,
    )
    @click.option(
        "--report",
        "report_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_REPORT_PATH,
        show_default=True,
    )
    @click.option(
        "--catalog",
        "catalog_path",
        type=click.Path(path_type=Path),
        default=CATALOG_PATH,
        show_default=True,
    )
    @click.option(
        "--synonyms",
        "synonyms_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_SYNONYMS_PATH,
        show_default=True,
    )
    @click.option(
        "--cache-dir",
        type=click.Path(path_type=Path),
        default=DEFAULT_CACHE_DIRECTORY,
        show_default=True,
    )
    @click.option("--model-id", default=DEFAULT_MODEL_ID, show_default=True)
    @click.option("--field-k", type=int, default=10, show_default=True)
    @click.option("--relation-k", type=int, default=5, show_default=True)
    def evaluate_command(
        ground_truth: Path,
        report_path: Path,
        catalog_path: Path,
        synonyms_path: Path,
        cache_dir: Path,
        model_id: str,
        field_k: int,
        relation_k: int,
    ) -> None:
        """Evaluate a cached index against exactly 50 reviewed questions."""
        try:
            _validate_cutoffs(field_k, relation_k)
            _required_file(ground_truth)
            if ground_truth.resolve() == report_path.resolve():
                raise SchemaLinkerError("report path must not overwrite ground truth")
            catalog_bytes, synonyms, elements = _catalog_inputs(catalog_path, synonyms_path)
            cases = load_ground_truth(ground_truth, elements)
            paths, index = _load_cached_index(cache_dir, catalog_bytes, model_id)
            encoder = encoder_factory(model_id)
            evaluation = evaluate_linker(
                SchemaLinker(index, encoder, synonyms),
                cases,
                field_k=field_k,
                relation_k=relation_k,
            )
            payload = _evaluation_payload(
                report=evaluation,
                index=index,
                paths=paths,
                catalog_bytes=catalog_bytes,
                ground_truth_bytes=ground_truth.read_bytes(),
                generated_at=_utc_timestamp(clock),
                git_sha=git_sha_factory(),
            )
            _atomic_write(report_path, payload)
            click.echo(
                json.dumps(
                    {"status": "ready", "command": "evaluate", "report": str(report_path)},
                    sort_keys=True,
                )
            )
        except (ImportError, OSError, ExternalDependencyError) as exc:
            _emit_failure("evaluate", "blocked", exc)
            raise click.exceptions.Exit(1) from exc
        except (SchemaCatalogError, SchemaIndexError, SchemaLinkerError, ValueError) as exc:
            _emit_contract_failure("evaluate", exc)
            raise click.exceptions.Exit(1) from exc

    return cli


main = create_cli()


if __name__ == "__main__":
    main()
