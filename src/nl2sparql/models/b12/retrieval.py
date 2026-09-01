"""Deterministic, provenance-bound nearest-neighbor retrieval for B2."""

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
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.models.b12.contracts import SelectedExample, SmallLLMError, validate_question

_ENCODER_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_CACHE_SCHEMA_VERSION = 1


class TextEncoder(Protocol):
    """SentenceTransformers-compatible encoding seam."""

    def encode(
        self,
        sentences: Sequence[str],
        *,
        normalize_embeddings: bool = True,
    ) -> object:
        """Encode ordered text into a numeric matrix."""


@dataclass(frozen=True)
class _TrainingRecord:
    record_id: str
    question: str
    normalized_question: str
    sql: str


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_question(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _validate_encoder_identity(encoder_id: object, encoder_revision: object) -> None:
    if not isinstance(encoder_id, str) or not encoder_id.strip():
        raise SmallLLMError("encoder ID must be non-empty")
    if not isinstance(encoder_revision, str) or not _ENCODER_REVISION_RE.fullmatch(
        encoder_revision
    ):
        raise SmallLLMError("encoder revision must be a pinned lowercase 40-hex revision")


def _load_records(snapshot: bytes) -> tuple[_TrainingRecord, ...]:
    try:
        text = snapshot.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SmallLLMError(f"training snapshot must be UTF-8: {exc}") from exc
    if not text.strip():
        raise SmallLLMError("training snapshot must not be empty")

    records: list[_TrainingRecord] = []
    ids: set[str] = set()
    questions: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise SmallLLMError(f"training snapshot line {line_number} must not be blank")
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SmallLLMError(
                f"training snapshot line {line_number} is invalid JSON: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise SmallLLMError(f"training snapshot line {line_number} must be an object")
        if raw.get("split") != "train":
            raise SmallLLMError(f"training snapshot line {line_number} must declare split=train")
        if raw.get("synthetic_fixture") is not False:
            raise SmallLLMError(
                f"training snapshot line {line_number} must not be a synthetic fixture"
            )
        record_id = raw.get("id")
        question = raw.get("nl")
        sql = raw.get("sql")
        try:
            candidate = SelectedExample(
                record_id=record_id,
                question=question,
                sql=sql,
                score=0.0,
            )
        except SmallLLMError as exc:
            raise SmallLLMError(f"training snapshot line {line_number} is invalid: {exc}") from exc
        if candidate.record_id in ids:
            raise SmallLLMError(f"training snapshot contains duplicate ID {candidate.record_id!r}")
        normalized = _normalize_question(candidate.question)
        if normalized in questions:
            raise SmallLLMError(
                f"training snapshot contains duplicate question at line {line_number}"
            )
        try:
            validate_sql_text(candidate.sql)
        except TestSetError as exc:
            raise SmallLLMError(
                f"training snapshot line {line_number} has invalid SQL: {exc}"
            ) from exc
        ids.add(candidate.record_id)
        questions.add(normalized)
        records.append(
            _TrainingRecord(
                record_id=candidate.record_id,
                question=candidate.question,
                normalized_question=normalized,
                sql=candidate.sql,
            )
        )
    if len(records) < 5:
        raise SmallLLMError("training snapshot requires at least five records")
    return tuple(records)


def _normalized_matrix(raw: object, *, rows: int, label: str) -> np.ndarray:
    array = np.asarray(raw)
    if array.ndim != 2:
        raise SmallLLMError(f"{label} embeddings must be two-dimensional")
    if array.shape[0] != rows:
        raise SmallLLMError(f"{label} embedding row count is invalid")
    if array.shape[1] <= 0:
        raise SmallLLMError(f"{label} embedding dimension must be positive")
    try:
        matrix = np.asarray(array, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise SmallLLMError(f"{label} embeddings must be numeric") from exc
    if not np.isfinite(matrix).all():
        raise SmallLLMError(f"{label} embeddings must be finite")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms <= 0.0):
        raise SmallLLMError(f"{label} embeddings must contain non-zero rows")
    matrix = matrix / norms[:, None]
    matrix.setflags(write=False)
    return matrix


def _paths_alias(left: Path, right: Path) -> bool:
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _validate_cache_paths(snapshot_path: Path, cache_path: Path) -> tuple[Path, Path]:
    metadata_path = cache_path.with_suffix(cache_path.suffix + ".json")
    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    paths = (snapshot_path, cache_path, metadata_path, lock_path)
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _paths_alias(left, right):
                raise SmallLLMError(f"training/cache paths must not alias: {left} and {right}")
    return metadata_path, lock_path


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_regular_single_link(path: Path, label: str) -> bytes:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise SmallLLMError(f"{label} is an unsafe alias")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            after = os.fstat(descriptor)
            if (
                not stat.S_ISREG(after.st_mode)
                or after.st_nlink != 1
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            ):
                raise SmallLLMError(f"{label} is an unsafe alias")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(descriptor)
    except SmallLLMError:
        raise
    except OSError as exc:
        raise SmallLLMError(f"unable to read {label}: {exc}") from exc


def _cache_body(
    *,
    training_sha256: str,
    encoder_id: str,
    encoder_revision: str,
    records: tuple[_TrainingRecord, ...],
    matrix: np.ndarray,
    matrix_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "training_sha256": training_sha256,
        "encoder_id": encoder_id,
        "encoder_revision": encoder_revision,
        "record_ids": [record.record_id for record in records],
        "shape": list(matrix.shape),
        "dtype": "float32",
        "matrix_sha256": matrix_sha256,
    }


def _load_cache(
    cache_path: Path,
    metadata_path: Path,
    *,
    training_sha256: str,
    encoder_id: str,
    encoder_revision: str,
    records: tuple[_TrainingRecord, ...],
) -> np.ndarray:
    metadata_bytes = _read_regular_single_link(metadata_path, "few-shot cache metadata")
    matrix_bytes = _read_regular_single_link(cache_path, "few-shot cache matrix")
    try:
        metadata = json.loads(metadata_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmallLLMError(f"few-shot cache metadata is invalid JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SmallLLMError("few-shot cache metadata must be an object")
    supplied_digest = metadata.pop("metadata_sha256", None)
    expected_digest = _sha256(_canonical_json(metadata))
    if not isinstance(supplied_digest, str) or not hmac.compare_digest(
        supplied_digest, expected_digest
    ):
        raise SmallLLMError("few-shot cache metadata digest mismatch")
    expected_identity = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "training_sha256": training_sha256,
        "encoder_id": encoder_id,
        "encoder_revision": encoder_revision,
        "record_ids": [record.record_id for record in records],
    }
    for key, expected in expected_identity.items():
        if metadata.get(key) != expected:
            raise SmallLLMError(f"few-shot cache {key} is stale")
    if metadata.get("matrix_sha256") != _sha256(matrix_bytes):
        raise SmallLLMError("few-shot cache matrix digest mismatch")
    try:
        with np.load(io.BytesIO(matrix_bytes), allow_pickle=False) as archive:
            if set(archive.files) != {"embeddings"}:
                raise SmallLLMError("few-shot cache archive members are invalid")
            matrix = _normalized_matrix(archive["embeddings"], rows=len(records), label="training")
    except (OSError, ValueError) as exc:
        raise SmallLLMError(f"few-shot cache matrix is invalid: {exc}") from exc
    if metadata.get("shape") != list(matrix.shape) or metadata.get("dtype") != "float32":
        raise SmallLLMError("few-shot cache matrix metadata is stale")
    return matrix


def _atomic_write(path: Path, payload: bytes, *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(dir=path.parent, prefix=prefix, suffix=".tmp")
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _publish_cache(
    cache_path: Path,
    metadata_path: Path,
    *,
    training_sha256: str,
    encoder_id: str,
    encoder_revision: str,
    records: tuple[_TrainingRecord, ...],
    matrix: np.ndarray,
) -> None:
    buffer = io.BytesIO()
    np.savez_compressed(buffer, embeddings=matrix)
    matrix_bytes = buffer.getvalue()
    body = _cache_body(
        training_sha256=training_sha256,
        encoder_id=encoder_id,
        encoder_revision=encoder_revision,
        records=records,
        matrix=matrix,
        matrix_sha256=_sha256(matrix_bytes),
    )
    metadata = {**body, "metadata_sha256": _sha256(_canonical_json(body))}
    _atomic_write(cache_path, matrix_bytes, prefix=".few-shot-matrix.")
    _atomic_write(metadata_path, _canonical_json(metadata), prefix=".few-shot-metadata.")


class FewShotRetriever:
    """Select five nearest safe training examples with deterministic ties."""

    def __init__(
        self,
        records: tuple[_TrainingRecord, ...],
        embeddings: np.ndarray,
        encoder: TextEncoder | None,
        *,
        training_sha256: str,
        encoder_id: str,
        encoder_revision: str,
    ) -> None:
        self._records = records
        self._embeddings = embeddings
        self._encoder = encoder
        self._training_sha256 = training_sha256
        self._encoder_id = encoder_id
        self._encoder_revision = encoder_revision

    @classmethod
    def from_snapshot(
        cls,
        path: Path,
        *,
        encoder: TextEncoder | None,
        encoder_id: str,
        encoder_revision: str,
        cache_path: Path | None = None,
    ) -> FewShotRetriever:
        """Load exact training bytes and build or validate their embedding index."""
        if not isinstance(path, Path):
            raise SmallLLMError("training snapshot path must be a pathlib.Path")
        _validate_encoder_identity(encoder_id, encoder_revision)
        try:
            snapshot = path.read_bytes()
        except OSError as exc:
            raise SmallLLMError(f"unable to read training snapshot {path}: {exc}") from exc
        records = _load_records(snapshot)
        training_sha256 = _sha256(snapshot)

        if cache_path is None:
            if encoder is None:
                raise SmallLLMError("training encoder unavailable and no cache was provided")
            embeddings = cls._encode_training(encoder, records)
        else:
            if not isinstance(cache_path, Path):
                raise SmallLLMError("cache path must be a pathlib.Path")
            metadata_path, lock_path = _validate_cache_paths(path, cache_path)
            with _lock(lock_path):
                try:
                    embeddings = _load_cache(
                        cache_path,
                        metadata_path,
                        training_sha256=training_sha256,
                        encoder_id=encoder_id,
                        encoder_revision=encoder_revision,
                        records=records,
                    )
                except SmallLLMError as cache_error:
                    if encoder is None:
                        raise SmallLLMError(
                            f"few-shot cache is invalid and encoder unavailable: {cache_error}"
                        ) from cache_error
                    embeddings = cls._encode_training(encoder, records)
                    _publish_cache(
                        cache_path,
                        metadata_path,
                        training_sha256=training_sha256,
                        encoder_id=encoder_id,
                        encoder_revision=encoder_revision,
                        records=records,
                        matrix=embeddings,
                    )

        return cls(
            records,
            embeddings,
            encoder,
            training_sha256=training_sha256,
            encoder_id=encoder_id,
            encoder_revision=encoder_revision,
        )

    @staticmethod
    def _encode_training(
        encoder: TextEncoder,
        records: tuple[_TrainingRecord, ...],
    ) -> np.ndarray:
        try:
            raw = encoder.encode(
                [record.question for record in records],
                normalize_embeddings=True,
            )
        except Exception as exc:
            raise SmallLLMError(f"training encoder failed: {exc}") from exc
        return _normalized_matrix(raw, rows=len(records), label="training")

    @property
    def training_sha256(self) -> str:
        return self._training_sha256

    @property
    def encoder_id(self) -> str:
        return self._encoder_id

    @property
    def encoder_revision(self) -> str:
        return self._encoder_revision

    def retrieve(
        self,
        question: str,
        *,
        target_id: str | None = None,
    ) -> tuple[SelectedExample, ...]:
        """Return five eligible examples ranked by cosine similarity then ID."""
        validate_question(question)
        if target_id is not None and (not isinstance(target_id, str) or not target_id):
            raise SmallLLMError("target_id must be a non-empty string when supplied")
        if self._encoder is None:
            raise SmallLLMError("query encoder unavailable")
        normalized_target = _normalize_question(question)
        eligible = [
            index
            for index, record in enumerate(self._records)
            if record.record_id != target_id and record.normalized_question != normalized_target
        ]
        if len(eligible) < 5:
            raise SmallLLMError("retrieval requires five eligible training examples")
        try:
            raw_query = self._encoder.encode([question], normalize_embeddings=True)
        except Exception as exc:
            raise SmallLLMError(f"query encoder failed: {exc}") from exc
        query = _normalized_matrix(raw_query, rows=1, label="query")
        if query.shape[1] != self._embeddings.shape[1]:
            raise SmallLLMError("query embedding dimension does not match training cache")
        scores = self._embeddings @ query[0]
        ranked = sorted(
            eligible,
            key=lambda index: (-float(scores[index]), self._records[index].record_id),
        )[:5]
        return tuple(
            SelectedExample(
                record_id=self._records[index].record_id,
                question=self._records[index].question,
                sql=self._records[index].sql,
                score=float(np.clip(scores[index], -1.0, 1.0)),
            )
            for index in ranked
        )
