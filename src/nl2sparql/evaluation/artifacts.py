"""Canonical codecs, immutable publication and hash-chained journals."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import tempfile
import types
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from nl2sparql.evaluation.contracts import (
    AnswerScores,
    ArtifactRef,
    BootstrapPolicy,
    CanonicalArtifact,
    CanonicalPredictionRun,
    CaseEvaluation,
    ComparisonReport,
    ConfidenceInterval,
    CostEvidence,
    DistributionMetric,
    DryRunEvidence,
    EvaluationError,
    EvaluationReport,
    ExecutionCaseEvidence,
    ExecutionEvidence,
    ExecutionPolicy,
    ExecutorProvenance,
    InferenceEvidence,
    ManualFailureReview,
    MetricDelta,
    PredictionCase,
    PricingPolicy,
    PrivacyEvidence,
    PrivacyReview,
    QueryExecution,
    QueryResultEvidence,
    RatioMetric,
    Readiness,
    ResultField,
    RunProvenance,
)

SCHEMA_VERSION = 1
_ENVELOPE_FIELDS = {"artifact_type", "schema_version", "body", "artifact_sha256"}
_JOURNAL_FIELDS = {"record_type", "body", "previous_sha256", "record_sha256"}
_ZERO_DIGEST = "0" * 64

_ARTIFACT_TYPES: dict[str, type[Any]] = {
    "nl2sql_prediction_run": CanonicalPredictionRun,
    "nl2sql_execution_evidence": ExecutionEvidence,
    "nl2sql_evaluation_report": EvaluationReport,
    "nl2sql_comparison_report": ComparisonReport,
    "nl2sql_privacy_review": PrivacyReview,
}
_CLASS_TO_ARTIFACT = {value: key for key, value in _ARTIFACT_TYPES.items()}
_KNOWN_DATACLASSES = {
    cls
    for cls in (
        AnswerScores,
        ArtifactRef,
        BootstrapPolicy,
        CanonicalPredictionRun,
        CaseEvaluation,
        ComparisonReport,
        ConfidenceInterval,
        CostEvidence,
        DistributionMetric,
        DryRunEvidence,
        EvaluationReport,
        ExecutionCaseEvidence,
        ExecutionEvidence,
        ExecutionPolicy,
        ExecutorProvenance,
        InferenceEvidence,
        ManualFailureReview,
        MetricDelta,
        PredictionCase,
        PricingPolicy,
        PrivacyEvidence,
        PrivacyReview,
        QueryExecution,
        QueryResultEvidence,
        RatioMetric,
        Readiness,
        ResultField,
        RunProvenance,
    )
}


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise EvaluationError("canonical JSON rejects non-finite Decimal values")
        return str(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise EvaluationError("canonical JSON object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise EvaluationError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: object) -> bytes:
    """Return compact, sorted, finite-only UTF-8 JSON ending in one newline."""
    try:
        text = json.dumps(
            _json_value(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise EvaluationError(f"value is not canonical JSON: {exc}") from exc
    return (text + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _serialize(artifact: CanonicalArtifact) -> bytes:
    artifact_type = _CLASS_TO_ARTIFACT.get(type(artifact))
    if artifact_type is None:
        raise EvaluationError(f"unsupported canonical artifact: {type(artifact).__name__}")
    if (
        isinstance(artifact, ExecutionEvidence)
        and artifact.policy is not None
        and artifact.policy_sha256 != _digest(artifact.policy)
    ):
        raise EvaluationError("execution evidence policy hash mismatch")
    base = {
        "artifact_type": artifact_type,
        "schema_version": SCHEMA_VERSION,
        "body": _json_value(artifact),
    }
    return canonical_json(base | {"artifact_sha256": _digest(base)})


def serialize_prediction_run(run: CanonicalPredictionRun) -> bytes:
    return _serialize(run)


def serialize_execution_evidence(evidence: ExecutionEvidence) -> bytes:
    return _serialize(evidence)


def serialize_evaluation_report(report: EvaluationReport) -> bytes:
    return _serialize(report)


def serialize_comparison_report(report: ComparisonReport) -> bytes:
    return _serialize(report)


def serialize_privacy_review(review: PrivacyReview) -> bytes:
    return _serialize(review)


def _decode_any(value: object) -> object:
    if isinstance(value, list):
        return tuple(_decode_any(item) for item in value)
    if isinstance(value, dict):
        field_set = set(value)
        for cls in sorted(_KNOWN_DATACLASSES, key=lambda item: item.__name__):
            if field_set == {field.name for field in fields(cls)}:
                return _decode_dataclass(value, cls)
        return {key: _decode_any(item) for key, item in value.items()}
    return value


def _decode(value: object, annotation: object) -> object:
    if annotation is Any:
        return _decode_any(value)
    if annotation is datetime:
        if not isinstance(value, str):
            raise EvaluationError("datetime field must be a string")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvaluationError("invalid canonical datetime") from exc
        return parsed
    if annotation is Decimal:
        if not isinstance(value, str):
            raise EvaluationError("Decimal field must be a string")
        try:
            return Decimal(value)
        except ValueError as exc:
            raise EvaluationError("invalid canonical Decimal") from exc
    if isinstance(annotation, type) and annotation in _KNOWN_DATACLASSES:
        return _decode_dataclass(value, annotation)

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is tuple:
        if not isinstance(value, list):
            raise EvaluationError("tuple field must be a JSON array")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_decode(item, arguments[0]) for item in value)
        if len(value) != len(arguments):
            raise EvaluationError("fixed tuple has wrong length")
        return tuple(
            _decode(item, item_type) for item, item_type in zip(value, arguments, strict=True)
        )
    if origin in (Union, types.UnionType):
        if value is None and type(None) in arguments:
            return None
        candidates = tuple(candidate for candidate in arguments if candidate is not type(None))
        errors: list[Exception] = []
        for candidate in candidates:
            try:
                return _decode(value, candidate)
            except (EvaluationError, TypeError, ValueError) as exc:
                errors.append(exc)
        raise EvaluationError("value does not match any allowed union member") from errors[-1]
    if origin is Literal:
        if value not in arguments:
            raise EvaluationError("unknown literal value")
        return value
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EvaluationError("expected float")
        return float(value)
    if annotation in (str, int, bool):
        if not isinstance(value, annotation) or (annotation is int and isinstance(value, bool)):
            raise EvaluationError(f"expected {annotation.__name__}")
        return value
    return value


def _decode_dataclass(value: object, cls: type[Any]) -> Any:
    if not isinstance(value, dict):
        raise EvaluationError(f"{cls.__name__} body must be an object")
    expected = {field.name for field in fields(cls)}
    if set(value) != expected:
        raise EvaluationError(f"{cls.__name__} body has an invalid exact field set")
    hints = get_type_hints(cls)
    decoded = {name: _decode(value[name], hints[name]) for name in expected}
    try:
        return cls(**decoded)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, EvaluationError):
            raise
        raise EvaluationError(f"invalid {cls.__name__}: {exc}") from exc


def _load(path: Path, expected_type: str | None = None) -> CanonicalArtifact:
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read canonical artifact: {exc}") from exc
    if not isinstance(document, dict) or set(document) != _ENVELOPE_FIELDS:
        raise EvaluationError("artifact envelope has an invalid exact field set")
    artifact_type = document["artifact_type"]
    if expected_type is not None and artifact_type != expected_type:
        raise EvaluationError(f"expected artifact type {expected_type}")
    cls = _ARTIFACT_TYPES.get(artifact_type)
    if cls is None:
        raise EvaluationError("unknown artifact type")
    if document["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("unknown artifact schema version")
    supplied_digest = document["artifact_sha256"]
    if not isinstance(supplied_digest, str):
        raise EvaluationError("artifact self-hash must be text")
    base = {key: document[key] for key in ("artifact_type", "schema_version", "body")}
    if not hmac.compare_digest(supplied_digest, _digest(base)):
        raise EvaluationError("artifact self-hash mismatch")
    artifact = _decode_dataclass(document["body"], cls)
    canonical = _serialize(artifact)
    if payload != canonical:
        raise EvaluationError("artifact bytes are not canonical")
    return artifact


def load_prediction_run(path: Path) -> CanonicalPredictionRun:
    artifact = _load(path, "nl2sql_prediction_run")
    assert isinstance(artifact, CanonicalPredictionRun)
    return artifact


def load_execution_evidence(path: Path) -> ExecutionEvidence:
    artifact = _load(path, "nl2sql_execution_evidence")
    assert isinstance(artifact, ExecutionEvidence)
    return artifact


def load_evaluation_report(path: Path) -> EvaluationReport:
    artifact = _load(path, "nl2sql_evaluation_report")
    assert isinstance(artifact, EvaluationReport)
    return artifact


def load_comparison_report(path: Path) -> ComparisonReport:
    artifact = _load(path, "nl2sql_comparison_report")
    assert isinstance(artifact, ComparisonReport)
    return artifact


def load_privacy_review(path: Path) -> PrivacyReview:
    artifact = _load(path, "nl2sql_privacy_review")
    assert isinstance(artifact, PrivacyReview)
    return artifact


def load_and_verify_artifact(path: Path) -> CanonicalArtifact:
    """Load any known version-one artifact and verify all canonical bindings."""
    return _load(path)


def _reject_alias(path: Path, protected_paths: Sequence[Path]) -> None:
    protected = tuple(item.resolve(strict=False) for item in protected_paths)
    if path.is_symlink() or path.resolve(strict=False) in protected:
        raise EvaluationError("publication target is an alias of a protected input")
    if not path.exists():
        return
    for item in protected_paths:
        if item.exists() and os.path.samefile(path, item):
            raise EvaluationError("publication target is a hardlink alias of a protected input")


def publish_immutable(path: Path, payload: bytes, *, protected_paths: Sequence[Path] = ()) -> None:
    """Atomically publish bytes once; byte-identical retries are idempotent."""
    if not isinstance(payload, bytes):
        raise EvaluationError("published payload must be bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_alias(path, protected_paths)
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise EvaluationError("immutable destination already contains different content")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            if path.read_bytes() == payload:
                return
            raise EvaluationError(
                "immutable destination already contains different content"
            ) from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_new_artifact_path(path: Path, *, protected_paths: Sequence[Path] = ()) -> None:
    """Fail before expensive work unless a publication target is new and unaliased."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_alias(path, protected_paths)
    if path.exists():
        raise EvaluationError("artifact destination already exists")


def _read_journal(path: Path) -> tuple[list[dict[str, object]], str, bool]:
    try:
        lines = path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise EvaluationError(f"cannot read journal: {exc}") from exc
    if not lines:
        raise EvaluationError("journal is empty")
    previous = _ZERO_DIGEST
    records: list[dict[str, object]] = []
    sealed = False
    for index, raw_line in enumerate(lines, start=1):
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvaluationError(f"journal record {index} is invalid JSON") from exc
        if not isinstance(record, dict) or set(record) != _JOURNAL_FIELDS:
            raise EvaluationError(f"journal record {index} has invalid field set")
        if raw_line != canonical_json(record):
            raise EvaluationError(f"journal record {index} is not canonical")
        if record["previous_sha256"] != previous:
            raise EvaluationError(f"journal record {index} has broken previous digest")
        base = {key: record[key] for key in ("record_type", "body", "previous_sha256")}
        expected = _digest(base)
        supplied = record["record_sha256"]
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
            raise EvaluationError(f"journal record {index} digest mismatch")
        if sealed:
            raise EvaluationError("journal contains records after terminal seal")
        sealed = record["record_type"] == "terminal_seal"
        previous = expected
        records.append(record)
    return records, previous, sealed


class HashChainJournal:
    """Append-only canonical JSONL journal with a terminal hash-chain seal."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record_type: str, body: Mapping[str, object]) -> str:
        if not record_type:
            raise EvaluationError("journal record_type must be non-empty")
        if self.path.exists() and self.path.stat().st_size:
            _, previous, sealed = _read_journal(self.path)
            if sealed:
                raise EvaluationError("sealed journal cannot be appended")
        else:
            previous = _ZERO_DIGEST
        base = {
            "record_type": record_type,
            "body": dict(body),
            "previous_sha256": previous,
        }
        digest = _digest(base)
        payload = canonical_json(base | {"record_sha256": digest})
        with self.path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return digest

    def seal(self, body: Mapping[str, object]) -> str:
        """Append the terminal record and return its digest."""
        return self.append("terminal_seal", body)


def verify_sealed_journal(path: Path) -> str:
    """Verify every journal link and return the terminal digest."""
    _, terminal, sealed = _read_journal(path)
    if not sealed:
        raise EvaluationError("journal is unsealed")
    return terminal


class FileExecutionJournal:
    """Create-once, fsync-before-return execution journal with no resume API."""

    def __init__(self, path: Path, *, _created: bool = False) -> None:
        if not _created:
            raise EvaluationError("file execution journals must be created with create()")
        self.path = path
        self._sealed = False

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        header: Mapping[str, object],
        protected_paths: Sequence[Path],
    ) -> FileExecutionJournal:
        path.parent.mkdir(parents=True, exist_ok=True)
        _reject_alias(path, protected_paths)
        try:
            with path.open("xb") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                cls._append_to_locked(handle, "journal_created", header, _ZERO_DIGEST)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except FileExistsError as exc:
            raise EvaluationError("execution journal already exists; resume is forbidden") from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return cls(path, _created=True)

    @staticmethod
    def _append_to_locked(
        handle: Any,
        record_type: str,
        body: Mapping[str, object],
        previous: str,
    ) -> str:
        base = {
            "record_type": record_type,
            "body": dict(body),
            "previous_sha256": previous,
        }
        digest = _digest(base)
        handle.seek(0, os.SEEK_END)
        handle.write(canonical_json(base | {"record_sha256": digest}))
        handle.flush()
        os.fsync(handle.fileno())
        return digest

    def append(self, record_type: str, body: Mapping[str, object]) -> str:
        if not record_type:
            raise EvaluationError("journal record_type must be non-empty")
        if self._sealed:
            raise EvaluationError("sealed journal cannot be appended")
        with self.path.open("r+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _, previous, sealed = _read_journal(self.path)
            if sealed:
                raise EvaluationError("sealed journal cannot be appended")
            digest = self._append_to_locked(handle, record_type, body, previous)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return digest

    def seal(self, body: Mapping[str, object]) -> str:
        terminal = self.append("terminal_seal", body)
        if verify_sealed_journal(self.path) != terminal:
            raise EvaluationError("journal terminal verification failed")
        self._sealed = True
        return terminal


def verify_execution_evidence_journal(evidence: ExecutionEvidence, path: Path) -> None:
    """Verify a sealed journal and its terminal binding to execution evidence."""
    records, terminal, sealed = _read_journal(path)
    if not sealed:
        raise EvaluationError("journal is unsealed")
    if not hmac.compare_digest(terminal, evidence.journal_terminal_sha256):
        raise EvaluationError("execution evidence journal terminal mismatch")
    headers = [record for record in records if record["record_type"] == "header"]
    if len(headers) != 1:
        raise EvaluationError("execution journal requires exactly one bound header")
    expected_header = {
        "execution_id": evidence.execution_id,
        "prediction_run_sha256": evidence.prediction_run_sha256,
        "policy_sha256": evidence.policy_sha256,
        "executor": _json_value(evidence.executor),
    }
    if headers[0]["body"] != expected_header:
        raise EvaluationError("execution journal header binding mismatch")
    terminal_body = records[-1]["body"]
    if terminal_body != {"case_count": len(evidence.cases)}:
        raise EvaluationError("execution journal terminal body mismatch")
