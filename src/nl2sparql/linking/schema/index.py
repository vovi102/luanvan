"""Safe build and load lifecycle for schema-linker embedding indexes."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import io
import json
import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from nl2sparql.linking.schema.contracts import (
    DOCUMENT_VERSION,
    INDEX_SCHEMA_VERSION,
    Encoder,
    SchemaCachePaths,
    SchemaElement,
    SchemaIndexError,
    SchemaLinkerError,
    ScoreWeights,
)


@dataclass(frozen=True)
class SchemaIndexMetadata:
    """Validated identity and ordered elements for one embedding index."""

    schema_version: int
    model_id: str
    document_version: str
    catalog_sha256: str
    matrices_sha256: str
    dimension: int
    weights: ScoreWeights
    relation_elements: tuple[SchemaElement, ...]
    field_elements: tuple[SchemaElement, ...]
    manifest_sha256: str


@dataclass(frozen=True)
class SchemaIndex:
    """Validated immutable relation and field embedding matrices."""

    metadata: SchemaIndexMetadata
    relation_embeddings: np.ndarray
    field_embeddings: np.ndarray


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
    label: str,
    expected_dimension: int | None = None,
    require_float32: bool = False,
) -> np.ndarray:
    array = np.asarray(raw)
    if array.ndim != 2 or array.shape[0] != expected_rows:
        raise SchemaIndexError(f"{label} encoder row count or rank is invalid")
    if array.shape[1] <= 0:
        raise SchemaIndexError(f"{label} encoder dimension must be positive")
    if expected_dimension is not None and array.shape[1] != expected_dimension:
        raise SchemaIndexError(f"{label} encoder dimension does not match the relation matrix")
    if require_float32 and array.dtype != np.float32:
        raise SchemaIndexError(f"{label} cache matrix must use float32")
    try:
        array = np.asarray(array, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise SchemaIndexError(f"{label} encoder output must be numeric") from exc
    if not np.isfinite(array).all():
        raise SchemaIndexError(f"{label} encoder output must be finite")
    norms = np.linalg.norm(array, axis=1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-5):
        raise SchemaIndexError(f"{label} encoder output must be normalized")
    array.setflags(write=False)
    return array


def _validate_elements(
    elements: Sequence[SchemaElement],
) -> tuple[tuple[SchemaElement, ...], tuple[SchemaElement, ...]]:
    if not elements:
        raise SchemaIndexError("at least one schema element is required")
    ids = [element.element_id for element in elements]
    if len(ids) != len(set(ids)):
        raise SchemaIndexError("schema index element IDs must be unique")
    for element in elements:
        if _sha256(element.document.encode()) != element.document_sha256:
            raise SchemaIndexError(f"schema element document hash mismatch: {element.element_id}")
    relations = tuple(
        sorted((row for row in elements if row.kind == "relation"), key=lambda row: row.element_id)
    )
    fields = tuple(
        sorted((row for row in elements if row.kind == "field"), key=lambda row: row.element_id)
    )
    if not relations or not fields:
        raise SchemaIndexError("schema index requires both relation and field elements")
    return relations, fields


def _manifest_body(
    *,
    model_id: str,
    document_version: str,
    catalog_sha256: str,
    matrices_sha256: str,
    dimension: int,
    weights: ScoreWeights,
    relations: tuple[SchemaElement, ...],
    fields: tuple[SchemaElement, ...],
) -> dict[str, Any]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "model_id": model_id,
        "document_version": document_version,
        "catalog_sha256": catalog_sha256,
        "matrices_sha256": matrices_sha256,
        "dimension": dimension,
        "weights": asdict(weights),
        "relation_elements": [asdict(row) for row in relations],
        "field_elements": [asdict(row) for row in fields],
    }


def _write_matrix_temp(
    paths: SchemaCachePaths,
    relation_embeddings: np.ndarray,
    field_embeddings: np.ndarray,
) -> tuple[Path, bytes]:
    handle, temporary = _temporary_file(paths.matrices.parent, ".schema-index.", ".npz.tmp")
    try:
        with handle:
            np.savez_compressed(
                handle,
                relation_embeddings=relation_embeddings,
                field_embeddings=field_embeddings,
            )
            handle.flush()
            os.fsync(handle.fileno())
        return temporary, temporary.read_bytes()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_manifest_temp(paths: SchemaCachePaths, payload: bytes) -> Path:
    handle, temporary = _temporary_file(paths.manifest.parent, ".schema-index.", ".json.tmp")
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _restore_artifact(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    handle, temporary = _temporary_file(path.parent, f".{path.name}.", ".restore.tmp")
    try:
        with handle:
            handle.write(previous)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _publish_pair(
    paths: SchemaCachePaths,
    matrix_temp: Path,
    manifest_temp: Path,
) -> None:
    with _index_lock(paths.lock):
        previous_matrix = paths.matrices.read_bytes() if paths.matrices.is_file() else None
        previous_manifest = paths.manifest.read_bytes() if paths.manifest.is_file() else None
        try:
            os.replace(matrix_temp, paths.matrices)
            _fsync_directory(paths.matrices.parent)
            os.replace(manifest_temp, paths.manifest)
            _fsync_directory(paths.manifest.parent)
        except OSError as exc:
            try:
                _restore_artifact(paths.matrices, previous_matrix)
                _restore_artifact(paths.manifest, previous_manifest)
                _fsync_directory(paths.manifest.parent)
            except OSError as rollback_exc:
                raise SchemaIndexError(
                    "schema index publication and rollback both failed"
                ) from rollback_exc
            raise SchemaIndexError("unable to publish schema index atomically") from exc


def build_index(
    elements: Sequence[SchemaElement],
    encoder: Encoder,
    model_id: str,
    catalog_bytes: bytes,
    paths: SchemaCachePaths,
    weights: ScoreWeights | None = None,
    *,
    document_version: str = DOCUMENT_VERSION,
) -> SchemaIndex:
    """Build, validate, and atomically publish a schema embedding index."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise SchemaIndexError("model ID must be non-empty")
    if not isinstance(document_version, str) or not document_version.strip():
        raise SchemaIndexError("document version must be non-empty")
    if not isinstance(catalog_bytes, bytes) or not catalog_bytes:
        raise SchemaIndexError("catalog bytes must be non-empty")
    weights = ScoreWeights() if weights is None else weights
    relations, fields = _validate_elements(elements)
    try:
        raw_relations = encoder.encode(
            [row.document for row in relations], normalize_embeddings=True
        )
        raw_fields = encoder.encode([row.document for row in fields], normalize_embeddings=True)
    except SchemaIndexError:
        raise
    except Exception as exc:
        raise SchemaIndexError(f"schema encoder failed: {exc}") from exc
    relation_embeddings = _validated_matrix(
        raw_relations, expected_rows=len(relations), label="relation"
    )
    field_embeddings = _validated_matrix(
        raw_fields,
        expected_rows=len(fields),
        label="field",
        expected_dimension=relation_embeddings.shape[1],
    )

    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    if paths.manifest.parent != paths.matrices.parent:
        raise SchemaIndexError("schema manifest and matrices must share one directory")
    matrix_temp: Path | None = None
    manifest_temp: Path | None = None
    try:
        matrix_temp, matrix_bytes = _write_matrix_temp(paths, relation_embeddings, field_embeddings)
        body = _manifest_body(
            model_id=model_id.strip(),
            document_version=document_version.strip(),
            catalog_sha256=_sha256(catalog_bytes),
            matrices_sha256=_sha256(matrix_bytes),
            dimension=relation_embeddings.shape[1],
            weights=weights,
            relations=relations,
            fields=fields,
        )
        manifest_payload = {**body, "manifest_sha256": _sha256(_canonical_json(body))}
        manifest_temp = _write_manifest_temp(paths, _canonical_json(manifest_payload))
        _publish_pair(paths, matrix_temp, manifest_temp)
        matrix_temp = None
        manifest_temp = None
    finally:
        if matrix_temp is not None:
            matrix_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)
    return load_index(
        paths,
        _sha256(catalog_bytes),
        model_id.strip(),
        document_version.strip(),
    )


def _parse_manifest(raw: bytes) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaIndexError(f"schema index manifest is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaIndexError("schema index manifest must contain a JSON object")
    supplied = payload.pop("manifest_sha256", None)
    expected = _sha256(_canonical_json(payload))
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        raise SchemaIndexError("schema index manifest digest mismatch")
    return payload, supplied


def _elements_from_manifest(raw: object, kind: str) -> tuple[SchemaElement, ...]:
    if not isinstance(raw, list):
        raise SchemaIndexError(f"schema index {kind} elements must be an array")
    try:
        rows = tuple(SchemaElement(**item) for item in raw)
    except (TypeError, SchemaLinkerError) as exc:
        raise SchemaIndexError(f"schema index {kind} elements are invalid: {exc}") from exc
    if any(row.kind != kind for row in rows):
        raise SchemaIndexError(f"schema index {kind} element kind mismatch")
    if list(rows) != sorted(rows, key=lambda row: row.element_id):
        raise SchemaIndexError(f"schema index {kind} elements are not sorted")
    return rows


def _load_matrices(raw: bytes) -> tuple[np.ndarray, np.ndarray]:
    try:
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            if set(archive.files) != {"relation_embeddings", "field_embeddings"}:
                raise SchemaIndexError("schema index NPZ keys are invalid")
            return archive["relation_embeddings"].copy(), archive["field_embeddings"].copy()
    except SchemaIndexError:
        raise
    except Exception as exc:
        raise SchemaIndexError(f"unable to load schema index NPZ: {exc}") from exc


def load_index(
    paths: SchemaCachePaths,
    expected_catalog_sha256: str,
    expected_model_id: str,
    expected_document_version: str,
) -> SchemaIndex:
    """Load a schema index only after all identity and integrity checks pass."""
    try:
        with _index_lock(paths.lock):
            manifest_bytes = paths.manifest.read_bytes()
            matrix_bytes = paths.matrices.read_bytes()
    except OSError as exc:
        raise SchemaIndexError(f"unable to read schema index: {exc}") from exc
    body, manifest_sha256 = _parse_manifest(manifest_bytes)
    schema_version = body.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != INDEX_SCHEMA_VERSION
    ):
        raise SchemaIndexError("schema index schema version mismatch")
    if body.get("catalog_sha256") != expected_catalog_sha256:
        raise SchemaIndexError("schema index catalog fingerprint mismatch")
    if body.get("model_id") != expected_model_id:
        raise SchemaIndexError("schema index model identity mismatch")
    if body.get("document_version") != expected_document_version:
        raise SchemaIndexError("schema index document version mismatch")
    if body.get("matrices_sha256") != _sha256(matrix_bytes):
        raise SchemaIndexError("schema index matrix digest mismatch")
    raw_dimension = body.get("dimension")
    if not isinstance(raw_dimension, int) or isinstance(raw_dimension, bool):
        raise SchemaIndexError("schema index dimension must be a positive integer")
    dimension = raw_dimension
    try:
        weights = ScoreWeights(**body["weights"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaIndexError(f"schema index metadata is invalid: {exc}") from exc
    if dimension <= 0:
        raise SchemaIndexError("schema index dimension must be positive")
    relations = _elements_from_manifest(body.get("relation_elements"), "relation")
    fields = _elements_from_manifest(body.get("field_elements"), "field")
    relations, fields = _validate_elements((*relations, *fields))
    relation_raw, field_raw = _load_matrices(matrix_bytes)
    relation_embeddings = _validated_matrix(
        relation_raw,
        expected_rows=len(relations),
        label="relation",
        expected_dimension=dimension,
        require_float32=True,
    )
    field_embeddings = _validated_matrix(
        field_raw,
        expected_rows=len(fields),
        label="field",
        expected_dimension=dimension,
        require_float32=True,
    )
    metadata = SchemaIndexMetadata(
        schema_version=INDEX_SCHEMA_VERSION,
        model_id=expected_model_id,
        document_version=expected_document_version,
        catalog_sha256=expected_catalog_sha256,
        matrices_sha256=str(body["matrices_sha256"]),
        dimension=dimension,
        weights=weights,
        relation_elements=relations,
        field_elements=fields,
        manifest_sha256=manifest_sha256,
    )
    return SchemaIndex(metadata, relation_embeddings, field_embeddings)
