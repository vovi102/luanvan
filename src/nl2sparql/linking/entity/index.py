"""Safe build and load lifecycle for entity-linker embedding indexes."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import io
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from nl2sparql.linking.entity.contracts import (
    DOCUMENT_VERSION,
    INDEX_SCHEMA_VERSION,
    Encoder,
    EntityCachePaths,
    EntityCorpus,
    EntityEncoderUnavailableError,
    EntityIndexError,
    EntityLinkerError,
    validate_digest,
)


@dataclass(frozen=True)
class EntityIndexMetadata:
    """Validated identity and ordered target fingerprints for one entity index."""

    schema_version: int
    model_id: str
    document_version: str
    entities_sha256: str
    aliases_sha256: str
    concepts_sha256: str
    matrices_sha256: str
    dimension: int
    target_ids: tuple[str, ...]
    target_document_sha256: tuple[str, ...]
    manifest_sha256: str
    manifest_file_sha256: str = ""
    matrices_file: str = ""


@dataclass(frozen=True)
class EntityIndex:
    """Validated immutable entity-target embedding matrix."""

    metadata: EntityIndexMetadata
    target_embeddings: np.ndarray


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@contextmanager
def _index_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _temporary_file(parent: Path, prefix: str, suffix: str) -> tuple[BinaryIO, Path]:
    descriptor, raw_path = tempfile.mkstemp(dir=parent, prefix=prefix, suffix=suffix)
    return os.fdopen(descriptor, "w+b"), Path(raw_path)


def _validated_matrix(
    raw: object,
    *,
    expected_rows: int,
    expected_dimension: int | None = None,
    require_float32: bool = False,
) -> np.ndarray:
    array = np.asarray(raw)
    if array.ndim != 2 or array.shape[0] != expected_rows:
        raise EntityIndexError("entity encoder row count or rank is invalid")
    if array.shape[1] <= 0:
        raise EntityIndexError("entity encoder dimension must be positive")
    if expected_dimension is not None and array.shape[1] != expected_dimension:
        raise EntityIndexError("entity encoder dimension does not match the manifest")
    if require_float32 and array.dtype != np.float32:
        raise EntityIndexError("entity cache matrix must use float32")
    try:
        array = np.asarray(array, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise EntityIndexError("entity encoder output must be numeric") from exc
    if not np.isfinite(array).all():
        raise EntityIndexError("entity encoder output must be finite")
    norms = np.linalg.norm(array, axis=1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-5):
        raise EntityIndexError("entity encoder output must be normalized")
    array.setflags(write=False)
    return array


def _manifest_body(
    *,
    corpus: EntityCorpus,
    model_id: str,
    document_version: str,
    matrices_sha256: str,
    matrices_file: str,
    dimension: int,
) -> dict[str, Any]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "model_id": model_id,
        "document_version": document_version,
        "entities_sha256": corpus.entities_sha256,
        "aliases_sha256": corpus.aliases_sha256,
        "concepts_sha256": corpus.concepts_sha256,
        "matrices_sha256": matrices_sha256,
        "matrices_file": matrices_file,
        "dimension": dimension,
        "target_ids": [target.target_id for target in corpus.targets],
        "target_document_sha256": [target.document_sha256 for target in corpus.targets],
    }


def _write_matrix_temp(paths: EntityCachePaths, embeddings: np.ndarray) -> tuple[Path, bytes]:
    handle, temporary = _temporary_file(paths.matrices.parent, ".entity-index.", ".npz.tmp")
    try:
        with handle:
            np.savez_compressed(handle, target_embeddings=embeddings)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary, temporary.read_bytes()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_manifest_temp(paths: EntityCachePaths, payload: bytes) -> Path:
    handle, temporary = _temporary_file(paths.manifest.parent, ".entity-index.", ".json.tmp")
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _publication_checkpoint(point: str) -> None:
    """No-op hook used to simulate process death at durable boundaries in tests."""


def _read_matrix_generation(path: Path) -> bytes:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise EntityIndexError("entity index matrix generation is an unsafe alias")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            after = os.fstat(descriptor)
            if (
                not stat.S_ISREG(after.st_mode)
                or after.st_nlink != 1
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            ):
                raise EntityIndexError("entity index matrix generation is an unsafe alias")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(descriptor)
    except EntityIndexError:
        raise
    except OSError as exc:
        raise EntityIndexError(f"unable to read entity index matrix generation: {exc}") from exc


def _publish_generation(
    paths: EntityCachePaths,
    matrix_temp: Path,
    generation_path: Path,
    matrices_sha256: str,
    manifest_temp: Path,
) -> None:
    with _index_lock(paths.lock):
        try:
            if generation_path.exists() or generation_path.is_symlink():
                existing = _read_matrix_generation(generation_path)
                if _sha256(existing) != matrices_sha256:
                    raise EntityIndexError("entity index matrix generation digest collision")
                matrix_temp.unlink(missing_ok=True)
            else:
                os.replace(matrix_temp, generation_path)
            _fsync_directory(generation_path.parent)
            _publication_checkpoint("matrix_generation_durable")
            os.replace(manifest_temp, paths.manifest)
            _fsync_directory(paths.manifest.parent)
            _publication_checkpoint("manifest_durable")
        except EntityIndexError:
            raise
        except OSError as exc:
            raise EntityIndexError("unable to publish entity index manifest switch") from exc


def _validate_build_arguments(
    corpus: EntityCorpus,
    model_id: str,
    document_version: str,
) -> tuple[str, str]:
    if not isinstance(corpus, EntityCorpus):
        raise EntityIndexError("entity corpus is invalid")
    if not isinstance(model_id, str) or not model_id.strip():
        raise EntityIndexError("model ID must be non-empty")
    if not isinstance(document_version, str) or not document_version.strip():
        raise EntityIndexError("document version must be non-empty")
    return model_id.strip(), document_version.strip()


def build_index(
    corpus: EntityCorpus,
    encoder: Encoder,
    paths: EntityCachePaths,
    model_id: str,
    *,
    document_version: str = DOCUMENT_VERSION,
) -> EntityIndex:
    """Encode ordered corpus documents once, then atomically publish an entity index."""
    model_id, document_version = _validate_build_arguments(corpus, model_id, document_version)
    if paths.manifest.parent != paths.matrices.parent:
        raise EntityIndexError("entity manifest and matrices must share one directory")
    try:
        raw_embeddings = encoder.encode(
            [target.document for target in corpus.targets], normalize_embeddings=True
        )
    except (ImportError, OSError) as exc:
        raise EntityEncoderUnavailableError(f"entity index encoder unavailable: {exc}") from exc
    except EntityIndexError:
        raise
    except Exception as exc:
        raise EntityIndexError(f"entity encoder failed: {exc}") from exc
    embeddings = _validated_matrix(raw_embeddings, expected_rows=len(corpus.targets))

    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    matrix_temp: Path | None = None
    manifest_temp: Path | None = None
    try:
        matrix_temp, matrix_bytes = _write_matrix_temp(paths, embeddings)
        matrices_sha256 = _sha256(matrix_bytes)
        generation_path = paths.matrix_generation(matrices_sha256)
        body = _manifest_body(
            corpus=corpus,
            model_id=model_id,
            document_version=document_version,
            matrices_sha256=matrices_sha256,
            matrices_file=generation_path.name,
            dimension=embeddings.shape[1],
        )
        manifest_payload = {**body, "manifest_sha256": _sha256(_canonical_json(body))}
        manifest_temp = _write_manifest_temp(paths, _canonical_json(manifest_payload))
        _publish_generation(
            paths,
            matrix_temp,
            generation_path,
            matrices_sha256,
            manifest_temp,
        )
    finally:
        if matrix_temp is not None:
            matrix_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)
    return load_index(paths, corpus, model_id, document_version=document_version)


_MATRIX_FILENAME_RE = re.compile(r"^entity-index-([0-9a-f]{64})\.npz$")
_MANIFEST_KEYS = {
    "schema_version",
    "model_id",
    "document_version",
    "entities_sha256",
    "aliases_sha256",
    "concepts_sha256",
    "matrices_sha256",
    "matrices_file",
    "dimension",
    "target_ids",
    "target_document_sha256",
}


def _parse_manifest(raw: bytes) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EntityIndexError(f"entity index manifest is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise EntityIndexError("entity index manifest must contain a JSON object")
    supplied = payload.pop("manifest_sha256", None)
    if set(payload) != _MANIFEST_KEYS:
        raise EntityIndexError("entity index manifest fields are invalid")
    expected = _sha256(_canonical_json(payload))
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        raise EntityIndexError("entity index manifest digest mismatch")
    return payload, supplied


def _matrix_filename(body: dict[str, Any]) -> str:
    filename = body.get("matrices_file")
    matrices_sha256 = body.get("matrices_sha256")
    if not isinstance(filename, str) or not isinstance(matrices_sha256, str):
        raise EntityIndexError("entity index matrix filename is invalid")
    match = _MATRIX_FILENAME_RE.fullmatch(filename)
    if match is None or match.group(1) != matrices_sha256:
        raise EntityIndexError("entity index matrix filename and digest do not match")
    return filename


def _targets_from_manifest(body: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ids = body.get("target_ids")
    fingerprints = body.get("target_document_sha256")
    if (
        not isinstance(ids, list)
        or not isinstance(fingerprints, list)
        or len(ids) != len(fingerprints)
    ):
        raise EntityIndexError("entity index target metadata is invalid")
    if not ids or any(not isinstance(target_id, str) or not target_id for target_id in ids):
        raise EntityIndexError("entity index target IDs are invalid")
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise EntityIndexError("entity index target IDs are not ordered and unique")
    try:
        for fingerprint in fingerprints:
            validate_digest(fingerprint, "entity target document fingerprint")
    except EntityLinkerError as exc:
        raise EntityIndexError(str(exc)) from exc
    return tuple(zip(ids, fingerprints, strict=True))


def _load_matrix(raw: bytes) -> np.ndarray:
    try:
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            if set(archive.files) != {"target_embeddings"}:
                raise EntityIndexError("entity index NPZ keys are invalid")
            return archive["target_embeddings"].copy()
    except EntityIndexError:
        raise
    except Exception as exc:
        raise EntityIndexError(f"unable to load entity index NPZ: {exc}") from exc


def _validate_manifest_identity(
    body: dict[str, Any], corpus: EntityCorpus, model_id: str, document_version: str
) -> None:
    schema_version = body.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != INDEX_SCHEMA_VERSION
    ):
        raise EntityIndexError("entity index schema version mismatch")
    if body.get("model_id") != model_id:
        raise EntityIndexError("entity index model identity mismatch")
    if body.get("document_version") != document_version:
        raise EntityIndexError("entity index document version mismatch")
    if (
        body.get("entities_sha256") != corpus.entities_sha256
        or body.get("aliases_sha256") != corpus.aliases_sha256
        or body.get("concepts_sha256") != corpus.concepts_sha256
    ):
        raise EntityIndexError("entity index dictionary fingerprint mismatch")


def load_index(
    paths: EntityCachePaths,
    corpus: EntityCorpus,
    model_id: str,
    *,
    document_version: str = DOCUMENT_VERSION,
) -> EntityIndex:
    """Load an entity index only after identity and integrity checks pass."""
    model_id, document_version = _validate_build_arguments(corpus, model_id, document_version)
    try:
        with _index_lock(paths.lock):
            manifest_bytes = paths.manifest.read_bytes()
            body, manifest_sha256 = _parse_manifest(manifest_bytes)
            _validate_manifest_identity(body, corpus, model_id, document_version)
            matrices_file = _matrix_filename(body)
            matrix_bytes = _read_matrix_generation(paths.manifest.parent / matrices_file)
    except OSError as exc:
        raise EntityIndexError(f"unable to read entity index: {exc}") from exc
    if body.get("matrices_sha256") != _sha256(matrix_bytes):
        raise EntityIndexError("entity index matrix digest mismatch")
    raw_dimension = body.get("dimension")
    if not isinstance(raw_dimension, int) or isinstance(raw_dimension, bool) or raw_dimension <= 0:
        raise EntityIndexError("entity index dimension must be a positive integer")
    manifest_targets = _targets_from_manifest(body)
    current_targets = tuple(
        (target.target_id, target.document_sha256) for target in corpus.targets
    )
    if manifest_targets != current_targets:
        raise EntityIndexError("entity index current document fingerprints do not match")
    embeddings = _validated_matrix(
        _load_matrix(matrix_bytes),
        expected_rows=len(manifest_targets),
        expected_dimension=raw_dimension,
        require_float32=True,
    )
    metadata = EntityIndexMetadata(
        schema_version=INDEX_SCHEMA_VERSION,
        model_id=model_id,
        document_version=document_version,
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
        matrices_sha256=str(body["matrices_sha256"]),
        dimension=raw_dimension,
        target_ids=tuple(target_id for target_id, _ in manifest_targets),
        target_document_sha256=tuple(fingerprint for _, fingerprint in manifest_targets),
        manifest_sha256=manifest_sha256,
        manifest_file_sha256=_sha256(manifest_bytes),
        matrices_file=matrices_file,
    )
    return EntityIndex(metadata, embeddings)
