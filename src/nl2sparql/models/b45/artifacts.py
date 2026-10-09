"""Atomic, resumable evidence artifacts for B4/B5 evaluation runs."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from nl2sparql.models.b12.contracts import SelectedExample, SmallLLMError
from nl2sparql.models.b45.attempts import AttemptEvidence
from nl2sparql.models.b45.budget import BudgetReservation, BudgetSnapshot
from nl2sparql.models.b45.contracts import (
    _LIVE_COMPLETION_MARKER,
    LargeLLMError,
    LargeLLMPrediction,
    RemoteCompletion,
    _money_difference,
    _money_sum,
    _openrouter_completion,
    canonical_money,
)
from nl2sparql.models.b45.evaluate import (
    EvaluationOutcome,
    LargeEvaluationMetrics,
    LargeEvaluationRun,
    _metrics,
    compare_large_reproducibility,
    prompt_set_sha256,
)

_SCHEMA_VERSION = 4
_LEGACY_RESUME_SCHEMA_VERSION = 2
_LEGACY_CHAINED_SCHEMA_VERSION = 3
_RESUME_SCHEMA_VERSIONS = frozenset(
    {_LEGACY_RESUME_SCHEMA_VERSION, _LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEADER_KEYS = {
    "schema_version",
    "record_type",
    "run_id",
    "baseline",
    "input_sha256",
    "config_sha256",
    "catalog_sha256",
    "summary_sha256",
    "training_sha256",
    "model_id",
    "provider_slug",
    "model_metadata_sha256",
    "provider_policy_sha256",
    "privacy_sha256",
    "prompt_set_sha256",
}
_LEGACY_HEADER_KEYS = _HEADER_KEYS - {
    "provider_policy_sha256",
    "privacy_sha256",
    "prompt_set_sha256",
}
_OUTCOME_KEYS = {
    "record_type",
    "run_id",
    "case_id",
    "question_sha256",
    "gold_sql",
    "difficulty",
    "categories",
    "status",
    "prediction",
    "safe_error_code",
    "baseline",
    "input_sha256",
    "config_sha256",
    "catalog_sha256",
    "summary_sha256",
    "training_sha256",
    "model_id",
    "provider_slug",
    "model_metadata_sha256",
    "source_synthetic",
    "source_trusted",
    "training_accepted",
    "prompt_sha256",
    "attempt_count",
    "budget_checkpoint",
    "authoritative_cost_usd",
    "provider_policy_sha256",
    "privacy_sha256",
    "previous_record_sha256",
    "record_sha256",
    "prompt_set_sha256",
    "retrieval_sha256",
    "attempt_set_count",
    "attempt_set_sha256",
}
_LEGACY_OUTCOME_KEYS = _OUTCOME_KEYS - {
    "provider_policy_sha256",
    "privacy_sha256",
    "previous_record_sha256",
    "record_sha256",
    "prompt_set_sha256",
    "retrieval_sha256",
    "attempt_set_count",
    "attempt_set_sha256",
}
_LEGACY_V3_OUTCOME_KEYS = _OUTCOME_KEYS - {
    "prompt_set_sha256",
    "retrieval_sha256",
    "attempt_set_count",
    "attempt_set_sha256",
}
_LEGACY_PROMPT_OUTCOME_KEYS = _OUTCOME_KEYS - {
    "retrieval_sha256",
    "attempt_set_count",
    "attempt_set_sha256",
}
_TERMINAL_KEYS = {
    "record_type",
    "run_id",
    "outcome_count",
    "budget_checkpoint",
    "metrics",
    "scientific_ready",
    "blockers",
    "local_implementation_ready",
    "provider_policy_sha256",
    "privacy_sha256",
    "report_body_sha256",
    "previous_record_sha256",
    "record_sha256",
    "prompt_set_sha256",
    "attempt_set_count",
    "attempt_set_sha256",
}
_ATTEMPT_KEYS = {
    "record_type",
    "run_id",
    "case_id",
    "request_id",
    "reservation_id",
    "attempt_number",
    "status",
    "prompt_sha256",
    "reservation_ceiling_usd",
    "budget_checkpoint",
    "authoritative_cost_usd",
    "previous_record_sha256",
    "record_sha256",
}
_PREDICTION_KEYS = {
    "baseline",
    "question",
    "raw_output",
    "sql",
    "extraction_status",
    "completion",
    "catalog_sha256",
    "summary_sha256",
    "prompt_sha256",
    "config_sha256",
    "latency_ms",
    "training_sha256",
    "encoder_id",
    "encoder_revision",
    "training_accepted",
    "selected_examples",
}
_COMPLETION_KEYS = {
    "raw_text",
    "generation_id",
    "model_id",
    "provider_slug",
    "input_tokens",
    "output_tokens",
    "charged_cost_usd",
    "upstream_cost_usd",
    "latency_ms",
    "attempt_count",
    "finish_reason",
    "system_fingerprint",
    "synthetic_backend",
}
_LEGACY_EXAMPLE_KEYS = {"record_id", "question", "sql", "score"}
_EXAMPLE_KEYS = _LEGACY_EXAMPLE_KEYS | {"language", "semantic_family_id"}
_BUDGET_KEYS = {
    "cap_usd",
    "spent_usd",
    "reserved_usd",
    "remaining_usd",
    "unresolved_request_ids",
    "stop_reason",
    "unresolved_reservations",
}
_RESERVATION_KEYS = {"request_id", "maximum_cost_usd"}
_METRICS_KEYS = {
    "total",
    "completed",
    "extraction_failed",
    "request_failed",
    "budget_blocked",
    "cost_unresolved",
    "p50_latency_ms",
    "p95_latency_ms",
    "input_tokens",
    "output_tokens",
    "charged_cost_usd",
    "cost_per_1k_queries_usd",
    "extraction_status_counts",
    "difficulty_counts",
    "category_counts",
    "unattributed_spend_usd",
}
_UNSET = object()


@dataclass(frozen=True)
class ArtifactPaths:
    """Destination paths for one complete B4/B5 publication.

    Attributes:
        predictions: Ordered prediction JSONL destination.
        request_log: Resumable request-journal JSONL destination.
        cost_csv: Derived request-cost CSV destination.
        report: Final report JSON destination and publication commit marker.
    """

    predictions: Path
    request_log: Path
    cost_csv: Path
    report: Path

    @property
    def all_outputs(self) -> tuple[Path, Path, Path, Path]:
        """Return outputs in publication order, with the report last."""
        return (self.predictions, self.request_log, self.cost_csv, self.report)


@dataclass(frozen=True)
class ResumeState:
    """Validated journal evidence accepted for a resumed evaluation.

    Attributes:
        completed_case_ids: Case IDs in durable journal acceptance order.
        prior_cost_usd: Authoritative cost attributed to all accepted outcomes.
        unattributed_spend_usd: Reconciled checkpoint spend without an accepted
            outcome row, such as a concurrent request lost before append.
        prior_records: Canonical validated journal outcome objects.
        budget_checkpoint: Last accepted durable budget checkpoint.
        run_id: Stable evaluation-run identifier.
        baseline: Baseline identity.
        input_sha256: Exact input snapshot fingerprint.
        config_sha256: Exact generation-configuration fingerprint.
        catalog_sha256: Exact catalog snapshot fingerprint.
        summary_sha256: Exact compiled catalog-summary fingerprint.
        training_sha256: Exact B5 training fingerprint, or ``None`` for B4.
        model_id: Exact configured model identifier.
        provider_slug: Exact configured provider.
        model_metadata_sha256: Accepted endpoint metadata fingerprint.
        schema_version: Journal schema used by the immutable prior records. Schema
            v2 is accepted only as an in-progress resume source; new publication
            uses schema v4, while sealed v3 remains readable for compatibility.
    """

    completed_case_ids: tuple[str, ...]
    prior_cost_usd: Decimal
    unattributed_spend_usd: Decimal
    prior_records: tuple[dict[str, object], ...]
    budget_checkpoint: BudgetSnapshot
    run_id: str
    baseline: str
    input_sha256: str | None
    config_sha256: str
    catalog_sha256: str
    summary_sha256: str
    training_sha256: str | None
    model_id: str
    provider_slug: str
    model_metadata_sha256: str | None
    schema_version: int
    provider_policy_sha256: str | None = None
    privacy_sha256: str | None = None
    prompt_set_sha256: str | None = None
    retrieval_sha256_by_case: Mapping[str, str] | None = None
    journal_prompt_set_sha256: str | None = None
    prior_journal_records: tuple[dict[str, object], ...] = ()
    attempt_records: tuple[AttemptEvidence, ...] = ()

    @property
    def completed_outcomes(self) -> tuple[EvaluationOutcome, ...]:
        """Reconstruct validated outcomes for ``evaluate_large_baseline`` resume.

        Returns:
            Immutable outcomes preserving synthetic/live provenance from each row.

        Raises:
            LargeLLMError: If a record is invalid or a schema v3 hash detects
                corruption. Legacy schema v2 has no record hashes and therefore
                receives typed validation only.
        """
        if self.schema_version == _LEGACY_RESUME_SCHEMA_VERSION:
            # The immediately preceding format had no record hashes. It is accepted
            # only for typed resume validation, then RequestJournal upgrades it.
            outcomes: list[EvaluationOutcome] = []
            for record in self.prior_records:
                outcome = _outcome_from_record(
                    record,
                    line_number=None,
                    schema_version=_LEGACY_RESUME_SCHEMA_VERSION,
                )
                # Schema v2 predates the provider-policy/privacy fields.  The
                # resume loader binds the current, independently validated local
                # identities to those legacy outcomes before the evaluator checks
                # its complete identity tuple.
                if self.provider_policy_sha256 is not None:
                    outcome = replace(
                        outcome,
                        provider_policy_sha256=self.provider_policy_sha256,
                    )
                if self.privacy_sha256 is not None:
                    outcome = replace(outcome, privacy_sha256=self.privacy_sha256)
                if self.prompt_set_sha256 is not None:
                    outcome = replace(outcome, prompt_set_sha256=self.prompt_set_sha256)
                if self.retrieval_sha256_by_case is not None:
                    outcome = replace(
                        outcome,
                        retrieval_sha256=self.retrieval_sha256_by_case[outcome.case_id],
                    )
                outcomes.append(outcome)
            return tuple(outcomes)
        if self.schema_version not in {_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}:
            raise LargeLLMError("resume journal schema version is invalid")
        header = _journal_header(
            run_id=self.run_id,
            baseline=self.baseline,
            input_sha256=self.input_sha256,
            config_sha256=self.config_sha256,
            catalog_sha256=self.catalog_sha256,
            summary_sha256=self.summary_sha256,
            training_sha256=self.training_sha256,
            model_id=self.model_id,
            provider_slug=self.provider_slug,
            model_metadata_sha256=self.model_metadata_sha256,
            provider_policy_sha256=self.provider_policy_sha256,
            privacy_sha256=self.privacy_sha256,
            prompt_set_sha256=self.journal_prompt_set_sha256,
            schema_version=self.schema_version,
        )
        previous_record_sha256 = _header_sha256(header)
        outcomes: list[EvaluationOutcome] = []
        chain_records = self.prior_journal_records or self.prior_records
        for line_number, record in enumerate(chain_records, start=2):
            _validate_record_chain(
                record,
                expected_previous=previous_record_sha256,
                line_number=line_number,
            )
            if record.get("record_type") == "attempt":
                _attempt_from_record(record, line_number=None)
                previous_record_sha256 = str(record["record_sha256"])
                continue
            outcome = _outcome_from_record(
                record,
                line_number=None,
                schema_version=self.schema_version,
            )
            if self.prompt_set_sha256 is not None:
                outcome = replace(outcome, prompt_set_sha256=self.prompt_set_sha256)
            if self.retrieval_sha256_by_case is not None:
                outcome = replace(
                    outcome,
                    retrieval_sha256=self.retrieval_sha256_by_case[outcome.case_id],
                )
            outcomes.append(outcome)
            previous_record_sha256 = str(record["record_sha256"])
        return tuple(outcomes)

    @property
    def attempts(self) -> tuple[AttemptEvidence, ...]:
        """Return validated attempt transitions retained by the resume prefix."""
        if self.attempt_records:
            return self.attempt_records
        return tuple(
            _attempt_from_record(record, line_number=None)
            for record in self.prior_journal_records
            if record.get("record_type") == "attempt"
        )

    @property
    def unresolved_request_ids(self) -> tuple[str, ...]:
        """Return sorted request IDs whose authoritative charge is unresolved."""
        return self.budget_checkpoint.unresolved_request_ids

    @property
    def attributed_spend_usd(self) -> Decimal:
        """Return spend attributed to accepted journal outcomes."""
        return self.prior_cost_usd

    @property
    def total_spent_usd(self) -> Decimal:
        """Return the exact checkpoint spend retained for resume."""
        return self.budget_checkpoint.spent_usd


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        return canonical_money(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_json(value: object) -> bytes:
    """Serialize one compact sorted JSON value with exactly one trailing newline."""
    return (
        json.dumps(
            _canonical_value(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _record_sha256(record: Mapping[str, object]) -> str:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _chained_record(
    body: Mapping[str, object], *, previous_record_sha256: str
) -> dict[str, object]:
    _validate_digest(previous_record_sha256, "previous request journal record fingerprint")
    record = {**body, "previous_record_sha256": previous_record_sha256}
    return {**record, "record_sha256": _record_sha256(record)}


def _header_sha256(header: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(header)).hexdigest()


def _paths_alias(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except (OSError, RuntimeError) as error:
        raise LargeLLMError(f"unable to compare artifact paths: {error}") from error


def _journal_lock_path(path: Path) -> Path:
    """Return the private sibling lock path for one request journal."""
    return path.with_name(f".{path.name}.lock")


@contextmanager
def request_journal_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive, alias-safe POSIX lock for a complete journal run.

    Args:
        path: Request-journal path whose accepting/resuming writer is serialized.

    Yields:
        ``None`` while the calling process exclusively owns the journal lock.

    Raises:
        LargeLLMError: If the journal or private lock path is unsafe or unavailable.
    """
    if not isinstance(path, Path):
        raise LargeLLMError("request journal path must be a pathlib.Path")
    lock_path = _journal_lock_path(path)
    if _paths_alias(path, lock_path):
        raise LargeLLMError("request journal lock path must not alias its journal")
    descriptor: int | None = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        _existing_bytes(lock_path)
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        details = os.fstat(descriptor)
        named = lock_path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or (details.st_dev, details.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise LargeLLMError(f"unsafe request journal lock alias: {lock_path}")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except LargeLLMError:
        raise
    except OSError as error:
        raise LargeLLMError(f"unable to acquire request journal lock: {error}") from error
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _existing_bytes(path: Path) -> bytes | None:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise LargeLLMError(f"unsafe existing artifact alias: {path}")
        return path.read_bytes()
    except LargeLLMError:
        raise
    except OSError as error:
        raise LargeLLMError(f"unable to inspect existing artifact {path}: {error}") from error


def _fsync_directory(parent: Path) -> None:
    descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _existing_bytes(path)
        parent = path.parent.resolve(strict=True)
        descriptor, raw_temporary = tempfile.mkstemp(dir=parent, prefix=f".{path.name}.")
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _quarantine_name(path: Path, *, label: str) -> Path:
    descriptor, raw_quarantined = tempfile.mkstemp(
        dir=path.parent.resolve(strict=True), prefix=f".{path.name}.{label}."
    )
    os.close(descriptor)
    quarantined = Path(raw_quarantined)
    quarantined.unlink()
    return quarantined


def _same_file_as_fd(path: Path, owned_descriptor: int) -> bool:
    current = path.stat(follow_symlinks=False)
    owned = os.fstat(owned_descriptor)
    return (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino)


def _open_current_file(path: Path, current: bytes) -> int:
    """Open the exact regular file represented by a preflight byte snapshot."""
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise LargeLLMError(f"unsafe existing artifact alias: {path}")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            if handle.read() != current or not _same_file_as_fd(path, descriptor):
                raise LargeLLMError(f"artifact changed after publication preflight: {path}")
        result = descriptor
        descriptor = None
        return result
    except LargeLLMError:
        raise
    except OSError as error:
        raise LargeLLMError(f"unable to inspect existing artifact {path}: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _remove_if_same_file(path: Path, owned_descriptor: int) -> None:
    """Remove the current path only when it is the inode held by owned_descriptor."""
    quarantined = _quarantine_name(path, label="rollback")
    os.rename(path, quarantined)
    if _same_file_as_fd(quarantined, owned_descriptor):
        quarantined.unlink()
        return
    _restore_quarantined(path, quarantined)


def _atomic_create_owned(path: Path, payload: bytes) -> int:
    """Durably create without clobbering and return an open ownership descriptor."""
    temporary: Path | None = None
    owned_descriptor: int | None = None
    linked = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        parent = path.parent.resolve(strict=True)
        descriptor, raw_temporary = tempfile.mkstemp(dir=parent, prefix=f".{path.name}.")
        temporary = Path(raw_temporary)
        owned_descriptor = descriptor
        with os.fdopen(os.dup(descriptor), "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # DECISION: hard-link the staged inode so creation is no-clobber and the
        # retained staging link is an ownership token until directory fsync succeeds.
        os.link(temporary, path)
        linked = True
        _fsync_directory(parent)
        temporary.unlink()
        temporary = None
        result = owned_descriptor
        owned_descriptor = None
        return result
    except Exception:
        if linked and owned_descriptor is not None:
            _remove_if_same_file(path, owned_descriptor)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if owned_descriptor is not None:
            os.close(owned_descriptor)


def _atomic_create(path: Path, payload: bytes) -> None:
    """Durably create one file without replacing a racing destination."""
    owned_descriptor = _atomic_create_owned(path, payload)
    os.close(owned_descriptor)


def _restore_quarantined(path: Path, quarantined: Path) -> None:
    """Restore a quarantined path without replacing a racing destination."""
    os.link(quarantined, path, follow_symlinks=False)
    quarantined.unlink()
    _fsync_directory(path.parent.resolve(strict=True))


def _restore_replaced_file(path: Path, owned_descriptor: int, previous_quarantine: Path) -> None:
    """Recover the exact previous inode without overwriting a racing path."""
    replacement_quarantine = _quarantine_name(path, label="failed")
    try:
        os.rename(path, replacement_quarantine)
    except Exception as quarantine_error:
        try:
            _remove_if_same_file(path, owned_descriptor)
            if path.exists() or path.is_symlink():
                raise LargeLLMError("journal replacement changed before fallback recovery")
            _restore_quarantined(path, previous_quarantine)
        except Exception as fallback_error:
            raise LargeLLMError(
                f"unable to quarantine journal replacement: {quarantine_error}; "
                f"fallback recovery failed: {fallback_error}"
            ) from quarantine_error
        raise LargeLLMError(
            f"unable to quarantine journal replacement: {quarantine_error}; "
            "exact preflight journal restored"
        ) from quarantine_error
    try:
        if not _same_file_as_fd(replacement_quarantine, owned_descriptor):
            _restore_quarantined(path, replacement_quarantine)
            raise LargeLLMError("journal replacement ownership changed during recovery")
        _restore_quarantined(path, previous_quarantine)
        replacement_quarantine.unlink()
        _fsync_directory(path.parent.resolve(strict=True))
    except Exception:
        if replacement_quarantine.exists() or replacement_quarantine.is_symlink():
            if not path.exists() and not path.is_symlink():
                _restore_quarantined(path, replacement_quarantine)
        raise


def _atomic_write_if_current(
    path: Path, payload: bytes, current: bytes, current_descriptor: int
) -> int:
    """Replace the observed version and return an open ownership descriptor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    quarantined = _quarantine_name(path, label="old")
    os.rename(path, quarantined)
    owned_descriptor: int | None = None
    try:
        if not _same_file_as_fd(quarantined, current_descriptor) or (
            _existing_bytes(quarantined) != current
        ):
            _restore_quarantined(path, quarantined)
            raise LargeLLMError(f"artifact changed after publication preflight: {path}")
        try:
            owned_descriptor = _atomic_create_owned(path, payload)
        except Exception:
            if not path.exists() and not path.is_symlink():
                _restore_quarantined(path, quarantined)
            raise
        try:
            quarantined.unlink()
        except Exception as retirement_error:
            try:
                _restore_replaced_file(path, owned_descriptor, quarantined)
            except Exception as recovery_error:
                raise LargeLLMError(
                    f"unable to retire previous journal: {retirement_error}; "
                    f"recovery failed: {recovery_error}"
                ) from retirement_error
            raise LargeLLMError(
                f"unable to retire previous journal: {retirement_error}"
            ) from retirement_error
        result = owned_descriptor
        owned_descriptor = None
        return result
    except Exception:
        if quarantined.exists() or quarantined.is_symlink():
            if not path.exists() and not path.is_symlink():
                _restore_quarantined(path, quarantined)
        raise
    finally:
        if owned_descriptor is not None:
            os.close(owned_descriptor)


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is not None:
        _atomic_write(path, previous)
        return
    if path.exists() or path.is_symlink():
        path.unlink()
        _fsync_directory(path.parent.resolve(strict=True))


def _restore_if_current(path: Path, owned_descriptor: int, previous: bytes | None) -> None:
    """Roll back only the inode still owned by this publication."""
    if not path.exists() and not path.is_symlink():
        return
    quarantined = _quarantine_name(path, label="rollback")
    try:
        os.rename(path, quarantined)
    except FileNotFoundError:
        return
    try:
        if not _same_file_as_fd(quarantined, owned_descriptor):
            _restore_quarantined(path, quarantined)
            return
        if previous is not None:
            try:
                _atomic_create(path, previous)
            except Exception:
                if not path.exists() and not path.is_symlink():
                    _restore_quarantined(path, quarantined)
                raise
        quarantined.unlink()
        _fsync_directory(path.parent.resolve(strict=True))
    except Exception:
        if quarantined.exists() or quarantined.is_symlink():
            if not path.exists() and not path.is_symlink():
                _restore_quarantined(path, quarantined)
        raise


def validate_artifact_paths(paths: ArtifactPaths, *, protected_paths: Sequence[Path] = ()) -> None:
    """Validate output type, alias, symlink, and hard-link safety before execution.

    Args:
        paths: Four publication destinations.
        protected_paths: Input/evidence paths that outputs must not alias.

    Raises:
        LargeLLMError: If paths are invalid, unsafe, or alias one another.
    """
    if not isinstance(paths, ArtifactPaths):
        raise LargeLLMError("artifact paths must be an ArtifactPaths value")
    outputs = paths.all_outputs
    protected = tuple(protected_paths)
    if any(not isinstance(path, Path) for path in (*outputs, *protected)):
        raise LargeLLMError("artifact paths must be pathlib.Path values")
    for index, left in enumerate(outputs):
        _existing_bytes(left)
        for right in outputs[index + 1 :]:
            if _paths_alias(left, right):
                raise LargeLLMError(f"output paths must not alias: {left} and {right}")
        for source in protected:
            if _paths_alias(left, source):
                raise LargeLLMError(
                    f"output path must not alias protected input: {left} and {source}"
                )
    journal_lock = _journal_lock_path(paths.request_log)
    _existing_bytes(journal_lock)
    for path in (*outputs, *protected):
        if _paths_alias(journal_lock, path):
            raise LargeLLMError(
                "request journal lock path must not alias an artifact path: "
                f"{journal_lock} and {path}"
            )


def _validate_digest(value: object, label: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LargeLLMError(f"{label} is invalid")


def _validate_header(
    header: Mapping[str, object],
    *,
    allowed_versions: frozenset[int] = frozenset({_SCHEMA_VERSION}),
) -> int:
    raw_schema_version = header.get("schema_version")
    if raw_schema_version == _LEGACY_RESUME_SCHEMA_VERSION:
        expected_keys = _LEGACY_HEADER_KEYS
    elif "prompt_set_sha256" in header:
        expected_keys = _HEADER_KEYS
    else:
        expected_keys = _LEGACY_HEADER_KEYS | {"provider_policy_sha256", "privacy_sha256"}
    if set(header) != expected_keys:
        raise LargeLLMError("request journal header fields are invalid")
    schema_version = raw_schema_version
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version not in allowed_versions
        or header["record_type"] != "header"
    ):
        raise LargeLLMError("request journal header version is invalid")
    run_id = header["run_id"]
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise LargeLLMError("request journal run ID is invalid")
    baseline = header["baseline"]
    if baseline not in {"b4", "b5"}:
        raise LargeLLMError("request journal baseline is invalid")
    _validate_digest(header["input_sha256"], "request journal input fingerprint", optional=True)
    _validate_digest(header["config_sha256"], "request journal config fingerprint")
    _validate_digest(header["catalog_sha256"], "request journal catalog fingerprint")
    _validate_digest(header["summary_sha256"], "request journal summary fingerprint")
    _validate_digest(
        header["model_metadata_sha256"],
        "request journal model metadata fingerprint",
        optional=True,
    )
    if schema_version != _LEGACY_RESUME_SCHEMA_VERSION:
        _validate_digest(
            header["provider_policy_sha256"],
            "request journal provider policy fingerprint",
            optional=True,
        )
        _validate_digest(
            header["privacy_sha256"],
            "request journal privacy fingerprint",
            optional=True,
        )
        if "prompt_set_sha256" in header:
            _validate_digest(header["prompt_set_sha256"], "request journal prompt-set fingerprint")
    training = header["training_sha256"]
    if baseline == "b4" and training is not None:
        raise LargeLLMError("B4 request journal must not contain training provenance")
    if baseline == "b5":
        _validate_digest(training, "request journal training fingerprint")
    for key, label in (("model_id", "model ID"), ("provider_slug", "provider")):
        value = header[key]
        if not isinstance(value, str) or not value:
            raise LargeLLMError(f"request journal {label} is invalid")
    return schema_version


def _journal_header(
    *,
    run_id: str,
    baseline: str,
    input_sha256: str | None,
    config_sha256: str,
    catalog_sha256: str,
    summary_sha256: str,
    training_sha256: str | None,
    model_id: str,
    provider_slug: str,
    model_metadata_sha256: str | None,
    provider_policy_sha256: str | None = None,
    privacy_sha256: str | None = None,
    prompt_set_sha256: str | None = None,
    schema_version: int = _LEGACY_CHAINED_SCHEMA_VERSION,
) -> dict[str, object]:
    header: dict[str, object] = {
        "schema_version": schema_version,
        "record_type": "header",
        "run_id": run_id,
        "baseline": baseline,
        "input_sha256": input_sha256,
        "config_sha256": config_sha256,
        "catalog_sha256": catalog_sha256,
        "summary_sha256": summary_sha256,
        "training_sha256": training_sha256,
        "model_id": model_id,
        "provider_slug": provider_slug,
        "model_metadata_sha256": model_metadata_sha256,
        "provider_policy_sha256": provider_policy_sha256,
        "privacy_sha256": privacy_sha256,
    }
    if prompt_set_sha256 is not None:
        header["prompt_set_sha256"] = prompt_set_sha256
    _validate_header(
        header,
        allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
    )
    return header


def _outcome_record(
    outcome: EvaluationOutcome,
    *,
    run_id: str,
    model_metadata_sha256: str | None,
    provider_policy_sha256: str | None,
    privacy_sha256: str | None,
    previous_record_sha256: str,
    attempts: Sequence[AttemptEvidence] = (),
    schema_version: int = _SCHEMA_VERSION,
) -> dict[str, object]:
    if not isinstance(outcome, EvaluationOutcome):
        raise LargeLLMError("request journal requires an EvaluationOutcome")
    if schema_version not in {_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}:
        raise LargeLLMError("request journal schema version is invalid")
    if schema_version == _LEGACY_CHAINED_SCHEMA_VERSION and attempts:
        raise LargeLLMError("schema v3 request journal cannot contain attempt evidence")
    body = {
        "record_type": "outcome",
        "run_id": run_id,
        "model_metadata_sha256": model_metadata_sha256,
        "provider_policy_sha256": provider_policy_sha256,
        "privacy_sha256": privacy_sha256,
        **_canonical_value(asdict(outcome)),
    }
    if schema_version == _SCHEMA_VERSION:
        body["attempt_set_count"] = len(attempts)
        body["attempt_set_sha256"] = _attempt_set_sha256(attempts)
    if outcome.prompt_set_sha256 is None:
        body.pop("prompt_set_sha256", None)
    if outcome.retrieval_sha256 is None:
        body.pop("retrieval_sha256", None)
    if body["model_metadata_sha256"] != model_metadata_sha256:
        raise LargeLLMError("request journal model metadata fingerprint mismatch")
    if body["provider_policy_sha256"] != provider_policy_sha256:
        raise LargeLLMError("request journal provider policy fingerprint mismatch")
    if body["privacy_sha256"] != privacy_sha256:
        raise LargeLLMError("request journal privacy fingerprint mismatch")
    return _chained_record(body, previous_record_sha256=previous_record_sha256)


def _attempt_record(
    evidence: AttemptEvidence, *, run_id: str, previous_record_sha256: str
) -> dict[str, object]:
    """Return one chained, canonical attempt transition record."""
    if not isinstance(evidence, AttemptEvidence):
        raise LargeLLMError("request journal requires AttemptEvidence")
    return _chained_record(
        {
            "record_type": "attempt",
            "run_id": run_id,
            **_canonical_value(asdict(evidence)),
        },
        previous_record_sha256=previous_record_sha256,
    )


def _attempt_from_record(
    record: Mapping[str, object], *, line_number: int | None
) -> AttemptEvidence:
    prefix = f"request journal line {line_number}" if line_number is not None else "attempt record"
    raw = _require_mapping(record, prefix, _ATTEMPT_KEYS)
    if raw["record_type"] != "attempt":
        raise LargeLLMError(f"{prefix} record type is invalid")
    values = {
        key: value
        for key, value in raw.items()
        if key not in {"record_type", "run_id", "previous_record_sha256", "record_sha256"}
    }
    values["reservation_ceiling_usd"] = _money_from_json(
        values["reservation_ceiling_usd"], "attempt reservation ceiling"
    )
    values["authoritative_cost_usd"] = _money_from_json(
        values["authoritative_cost_usd"], "attempt authoritative cost", optional=True
    )
    values["budget_checkpoint"] = _budget_from_record(values["budget_checkpoint"])
    try:
        return AttemptEvidence(**values)  # type: ignore[arg-type]
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"{prefix} is invalid: {error}") from error


def _attempt_set_sha256(attempts: Sequence[AttemptEvidence]) -> str:
    """Return a canonical digest that cannot be replaced by outcome metadata."""
    return hashlib.sha256(
        _canonical_json([_canonical_value(asdict(attempt)) for attempt in attempts])
    ).hexdigest()


def _money_from_json(value: object, label: str, *, optional: bool = False) -> Decimal | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise LargeLLMError(f"{label} must be a canonical Decimal string")
    try:
        accepted = Decimal(value)
    except InvalidOperation as error:
        raise LargeLLMError(f"{label} must be a canonical Decimal string") from error
    if not accepted.is_finite() or canonical_money(accepted) != value:
        raise LargeLLMError(f"{label} must be a canonical Decimal string")
    return accepted


def _reservation_from_record(value: object) -> BudgetReservation:
    raw = _require_mapping(value, "journal unresolved reservation", _RESERVATION_KEYS)
    maximum = _money_from_json(raw["maximum_cost_usd"], "journal unresolved reservation ceiling")
    assert maximum is not None
    try:
        return BudgetReservation(
            request_id=raw["request_id"],  # type: ignore[arg-type]
            maximum_cost_usd=maximum,
        )
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"journal unresolved reservation is invalid: {error}") from error


def _budget_from_record(value: object) -> BudgetSnapshot:
    raw = _require_mapping(value, "journal budget checkpoint", _BUDGET_KEYS)
    unresolved_ids = raw["unresolved_request_ids"]
    if not isinstance(unresolved_ids, list) or any(
        not isinstance(request_id, str) for request_id in unresolved_ids
    ):
        raise LargeLLMError("journal budget unresolved request IDs are invalid")
    reservations = raw["unresolved_reservations"]
    if not isinstance(reservations, list):
        raise LargeLLMError("journal budget unresolved reservations are invalid")
    cap = _money_from_json(raw["cap_usd"], "journal budget cap")
    spent = _money_from_json(raw["spent_usd"], "journal budget spent")
    reserved = _money_from_json(raw["reserved_usd"], "journal budget reserved")
    remaining = _money_from_json(raw["remaining_usd"], "journal budget remaining")
    assert cap is not None
    assert spent is not None
    assert reserved is not None
    assert remaining is not None
    try:
        return BudgetSnapshot(
            cap_usd=cap,
            spent_usd=spent,
            reserved_usd=reserved,
            remaining_usd=remaining,
            unresolved_request_ids=tuple(unresolved_ids),
            stop_reason=raw["stop_reason"],  # type: ignore[arg-type]
            unresolved_reservations=tuple(
                _reservation_from_record(reservation) for reservation in reservations
            ),
        )
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"journal budget checkpoint is invalid: {error}") from error


def _metrics_from_record(value: object) -> LargeEvaluationMetrics:
    raw = _require_mapping(value, "journal terminal metrics", _METRICS_KEYS)
    values = dict(raw)
    for key, label in (
        ("charged_cost_usd", "journal terminal charged cost"),
        ("cost_per_1k_queries_usd", "journal terminal scaled cost"),
        ("unattributed_spend_usd", "journal terminal unattributed spend"),
    ):
        values[key] = _money_from_json(values[key], label)
    for key in ("extraction_status_counts", "difficulty_counts", "category_counts"):
        grouped = values[key]
        if not isinstance(grouped, list) or any(
            not isinstance(item, list) or len(item) != 2 for item in grouped
        ):
            raise LargeLLMError("journal terminal grouped metrics are invalid")
        values[key] = tuple((item[0], item[1]) for item in grouped)
    try:
        return LargeEvaluationMetrics(**values)  # type: ignore[arg-type]
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"journal terminal metrics are invalid: {error}") from error


def _require_mapping(value: object, label: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise LargeLLMError(f"{label} fields are invalid")
    return value


def _prediction_from_record(value: object) -> LargeLLMPrediction | None:
    if value is None:
        return None
    raw = _require_mapping(value, "journal prediction", _PREDICTION_KEYS)
    completion_raw = _require_mapping(raw["completion"], "journal completion", _COMPLETION_KEYS)
    synthetic = completion_raw["synthetic_backend"]
    if not isinstance(synthetic, bool):
        raise LargeLLMError("journal synthetic provenance is invalid")
    completion_values = {
        key: item for key, item in completion_raw.items() if key != "synthetic_backend"
    }
    completion_values["charged_cost_usd"] = _money_from_json(
        completion_values["charged_cost_usd"], "journal charged cost"
    )
    completion_values["upstream_cost_usd"] = _money_from_json(
        completion_values["upstream_cost_usd"], "journal upstream cost", optional=True
    )
    if synthetic:
        completion = RemoteCompletion(**completion_values)  # type: ignore[arg-type]
    else:
        completion = _openrouter_completion(completion_values, _LIVE_COMPLETION_MARKER)

    examples_raw = raw["selected_examples"]
    if not isinstance(examples_raw, list):
        raise LargeLLMError("journal selected examples are invalid")
    examples: list[SelectedExample] = []
    for item in examples_raw:
        if not isinstance(item, dict) or frozenset(item) not in {
            frozenset(_LEGACY_EXAMPLE_KEYS),
            frozenset(_EXAMPLE_KEYS),
        }:
            raise LargeLLMError("journal selected example fields are invalid")
        accepted = dict(item)
        try:
            examples.append(SelectedExample(**accepted))  # type: ignore[arg-type]
        except (SmallLLMError, TypeError) as error:
            raise LargeLLMError(f"journal selected example is invalid: {error}") from error
    prediction_values = dict(raw)
    prediction_values["completion"] = completion
    prediction_values["selected_examples"] = tuple(examples)
    try:
        return LargeLLMPrediction(**prediction_values)  # type: ignore[arg-type]
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"journal prediction is invalid: {error}") from error


def _outcome_from_record(
    record: Mapping[str, object],
    *,
    line_number: int | None,
    schema_version: int = _SCHEMA_VERSION,
) -> EvaluationOutcome:
    prefix = f"request journal line {line_number}" if line_number is not None else "resume record"
    try:
        if schema_version == _SCHEMA_VERSION:
            outcome_keys = set(_OUTCOME_KEYS)
            if "retrieval_sha256" not in record:
                outcome_keys.discard("retrieval_sha256")
            if "prompt_set_sha256" not in record:
                outcome_keys.discard("prompt_set_sha256")
        elif schema_version == _LEGACY_CHAINED_SCHEMA_VERSION:
            outcome_keys = set(_LEGACY_V3_OUTCOME_KEYS)
            if "retrieval_sha256" in record:
                outcome_keys.add("retrieval_sha256")
                outcome_keys.add("prompt_set_sha256")
            elif "prompt_set_sha256" in record:
                outcome_keys.add("prompt_set_sha256")
        elif schema_version == _LEGACY_RESUME_SCHEMA_VERSION:
            outcome_keys = _LEGACY_OUTCOME_KEYS
        else:
            raise LargeLLMError("journal outcome schema version is invalid")
        raw = _require_mapping(record, prefix, outcome_keys)
        if raw["record_type"] != "outcome":
            raise LargeLLMError("journal outcome record type is invalid")
        values = {
            key: item
            for key, item in raw.items()
            if key
            not in {
                "record_type",
                "run_id",
                "previous_record_sha256",
                "record_sha256",
            }
        }
        categories = values["categories"]
        if not isinstance(categories, list):
            raise LargeLLMError("journal outcome categories are invalid")
        values["categories"] = tuple(categories)
        values["prediction"] = _prediction_from_record(values["prediction"])
        values["authoritative_cost_usd"] = _money_from_json(
            values["authoritative_cost_usd"], "journal authoritative cost"
        )
        values["budget_checkpoint"] = _budget_from_record(values["budget_checkpoint"])
        values.setdefault("prompt_set_sha256", None)
        values.setdefault("retrieval_sha256", None)
        values.pop("attempt_set_count", None)
        values.pop("attempt_set_sha256", None)
        return EvaluationOutcome(**values)  # type: ignore[arg-type]
    except (LargeLLMError, TypeError, KeyError) as error:
        raise LargeLLMError(f"{prefix} is invalid: {error}") from error


def _terminal_evidence(
    record: Mapping[str, object],
    *,
    line_number: int | None,
    schema_version: int = _SCHEMA_VERSION,
) -> tuple[BudgetSnapshot, LargeEvaluationMetrics]:
    prefix = f"request journal line {line_number}" if line_number is not None else "terminal record"
    try:
        terminal_keys = set(_TERMINAL_KEYS)
        if schema_version != _SCHEMA_VERSION:
            terminal_keys -= {"attempt_set_count", "attempt_set_sha256"}
        elif "attempt_set_sha256" not in record:
            raise LargeLLMError("journal terminal attempt evidence is missing")
        if "prompt_set_sha256" not in record:
            terminal_keys = terminal_keys - {"prompt_set_sha256"}
        raw = _require_mapping(record, prefix, terminal_keys)
        if raw["record_type"] != "terminal":
            raise LargeLLMError("journal terminal record type is invalid")
        run_id = raw["run_id"]
        if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
            raise LargeLLMError("journal terminal run ID is invalid")
        outcome_count = raw["outcome_count"]
        if (
            not isinstance(outcome_count, int)
            or isinstance(outcome_count, bool)
            or outcome_count <= 0
        ):
            raise LargeLLMError("journal terminal outcome count is invalid")
        blockers = raw["blockers"]
        if (
            not isinstance(blockers, list)
            or blockers != sorted(set(blockers))
            or any(not isinstance(blocker, str) or not blocker for blocker in blockers)
        ):
            raise LargeLLMError("journal terminal blockers are invalid")
        if not isinstance(raw["scientific_ready"], bool) or raw["scientific_ready"] == bool(
            blockers
        ):
            raise LargeLLMError("journal terminal readiness is invalid")
        if not isinstance(raw["local_implementation_ready"], bool):
            raise LargeLLMError("journal terminal local readiness is invalid")
        _validate_digest(
            raw["provider_policy_sha256"],
            "journal terminal provider policy fingerprint",
            optional=True,
        )
        _validate_digest(
            raw["privacy_sha256"],
            "journal terminal privacy fingerprint",
            optional=True,
        )
        if "prompt_set_sha256" in raw:
            _validate_digest(raw["prompt_set_sha256"], "journal terminal prompt-set fingerprint")
        if schema_version == _SCHEMA_VERSION:
            count = raw["attempt_set_count"]
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise LargeLLMError("journal terminal attempt count is invalid")
            _validate_digest(raw["attempt_set_sha256"], "journal terminal attempt fingerprint")
        _validate_digest(raw["report_body_sha256"], "journal terminal report fingerprint")
        return _budget_from_record(raw["budget_checkpoint"]), _metrics_from_record(raw["metrics"])
    except (LargeLLMError, TypeError) as error:
        raise LargeLLMError(f"{prefix} is invalid: {error}") from error


def _validate_record_chain(
    record: Mapping[str, object], *, expected_previous: str, line_number: int
) -> None:
    previous = record.get("previous_record_sha256")
    current = record.get("record_sha256")
    _validate_digest(previous, f"request journal line {line_number} previous fingerprint")
    _validate_digest(current, f"request journal line {line_number} record fingerprint")
    if previous != expected_previous:
        raise LargeLLMError(f"request journal line {line_number} chain is invalid")
    if current != _record_sha256(record):
        raise LargeLLMError(f"request journal line {line_number} fingerprint is invalid")


_ATTEMPT_TERMINAL_STATUSES = frozenset(
    {"retryable_failure", "completed", "terminal_failure", "cancelled"}
)


def _validate_attempt_transition(
    prior: Sequence[AttemptEvidence], attempt: AttemptEvidence
) -> None:
    """Validate one case's append-only attempt state machine."""
    if not prior:
        if (
            attempt.attempt_number != 1
            or attempt.status != "reserved"
            or attempt.reservation_id != f"{attempt.request_id}:attempt-1"
        ):
            raise LargeLLMError("request journal attempt transition ordering is invalid")
        if attempt.budget_checkpoint.stop_reason is not None:
            raise LargeLLMError("request journal attempt checkpoint is already stopped")
        return
    previous = prior[-1]
    if attempt.attempt_number == previous.attempt_number:
        # A resumed worker can replay an unresolved first reservation with a
        # fresh ``:resume-N`` ID.  This is the only legal repeated number.
        if (
            attempt.status == "reserved"
            and attempt.reservation_id != previous.reservation_id
            and ":resume-" in attempt.reservation_id
            and previous.status in _ATTEMPT_TERMINAL_STATUSES | {"reserved"}
        ):
            _validate_attempt_checkpoint_transition(previous, attempt, resumed=True)
            if attempt.budget_checkpoint.stop_reason is not None:
                raise LargeLLMError("request journal attempt checkpoint is already stopped")
            return
        if (
            previous.status != "reserved"
            or attempt.reservation_id != previous.reservation_id
            or attempt.status not in _ATTEMPT_TERMINAL_STATUSES
        ):
            raise LargeLLMError("request journal attempt transition ordering is invalid")
        _validate_attempt_checkpoint_transition(previous, attempt, resumed=False)
        return
    if (
        attempt.attempt_number != previous.attempt_number + 1
        or previous.status not in _ATTEMPT_TERMINAL_STATUSES
        or attempt.status != "reserved"
    ):
        raise LargeLLMError("request journal attempt transition ordering is invalid")
    _validate_attempt_checkpoint_transition(previous, attempt, resumed=True)
    if attempt.budget_checkpoint.stop_reason is not None:
        raise LargeLLMError("request journal attempt checkpoint is already stopped")


def _validate_attempt_checkpoint_transition(
    previous: AttemptEvidence,
    current: AttemptEvidence,
    *,
    resumed: bool,
) -> None:
    """Require accounting checkpoints to move in the only safe direction.

    A checkpoint can include activity from other concurrent cases between two
    rows for this case.  The validator therefore checks monotonic spend and
    exact reservation membership rather than requiring byte-for-byte snapshots.
    """
    previous_snapshot = previous.budget_checkpoint
    current_snapshot = current.budget_checkpoint
    if current_snapshot.cap_usd != previous_snapshot.cap_usd:
        raise LargeLLMError("request journal attempt budget cap changed")
    if current_snapshot.spent_usd < previous_snapshot.spent_usd:
        raise LargeLLMError("request journal attempt spend moved backwards")
    previous_reservations = {
        item.request_id: item.maximum_cost_usd for item in previous_snapshot.unresolved_reservations
    }
    current_reservations = {
        item.request_id: item.maximum_cost_usd for item in current_snapshot.unresolved_reservations
    }
    previous_held = previous_reservations.get(previous.reservation_id)
    if previous.authoritative_cost_usd is None and (
        previous_held != previous.reservation_ceiling_usd
    ):
        # AttemptEvidence validates this itself, but keeping the check here
        # makes the transition invariant explicit and future-proof.
        raise LargeLLMError("request journal prior attempt reservation is not held exactly")

    if not resumed:
        # This is the terminal row for the reservation just started.  Unknown
        # cost must retain the full ceiling; known cost must remove that
        # reservation and add at least the authoritative spend.
        if current.authoritative_cost_usd is None:
            if current_reservations.get(current.reservation_id) != current.reservation_ceiling_usd:
                raise LargeLLMError("request journal unresolved attempt ceiling changed")
        else:
            if current.reservation_id in current_reservations:
                raise LargeLLMError("request journal reconciled attempt remains reserved")
            if current_snapshot.spent_usd < _money_sum(
                (previous_snapshot.spent_usd, current.authoritative_cost_usd)
            ):
                raise LargeLLMError("request journal reconciled spend is missing")
        return

    # A retry or resumed replay receives a fresh reservation.  Every prior
    # unresolved liability remains held while the new request is reserved.
    if previous.authoritative_cost_usd is None and (
        current_reservations.get(previous.reservation_id) != previous.reservation_ceiling_usd
    ):
        raise LargeLLMError("request journal retry released prior unresolved ceiling")
    if current_reservations.get(current.reservation_id) != current.reservation_ceiling_usd:
        raise LargeLLMError("request journal next attempt ceiling is not held exactly")


def _decode_json_line(raw_line: bytes, line_number: int) -> dict[str, object]:
    if not raw_line.endswith(b"\n") or raw_line == b"\n":
        raise LargeLLMError(f"request journal line {line_number} is not canonical")
    try:
        value = json.loads(raw_line)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LargeLLMError(f"request journal line {line_number} is invalid JSON") from error
    if not isinstance(value, dict) or _canonical_json(value) != raw_line:
        raise LargeLLMError(f"request journal line {line_number} is not canonical")
    return value


def _parse_request_log(
    payload: bytes,
    *,
    allowed_versions: frozenset[int] = frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
) -> tuple[
    dict[str, object],
    tuple[dict[str, object], ...],
    dict[str, object] | None,
]:
    if not payload:
        raise LargeLLMError("request journal must not be empty")
    lines = payload.splitlines(keepends=True)
    header = _decode_json_line(lines[0], 1)
    schema_version = _validate_header(header, allowed_versions=allowed_versions)
    records: list[dict[str, object]] = []
    identifiers: set[str] = set()
    attempt_records: list[AttemptEvidence] = []
    attempts_by_case: dict[str, list[AttemptEvidence]] = {}
    terminal: dict[str, object] | None = None
    previous_record_sha256 = _header_sha256(header)
    identity_keys = (
        "run_id",
        "baseline",
        "input_sha256",
        "config_sha256",
        "catalog_sha256",
        "summary_sha256",
        "training_sha256",
        "model_id",
        "provider_slug",
        "model_metadata_sha256",
        "provider_policy_sha256",
        "privacy_sha256",
        "prompt_set_sha256",
    )
    for line_number, raw_line in enumerate(lines[1:], start=2):
        record = _decode_json_line(raw_line, line_number)
        if terminal is not None:
            raise LargeLLMError("request journal contains a record after its terminal checkpoint")
        record_type = record.get("record_type")
        if record_type == "terminal":
            if schema_version == _LEGACY_RESUME_SCHEMA_VERSION:
                raise LargeLLMError("request journal schema v2 must not contain terminal records")
            _terminal_evidence(
                record,
                line_number=line_number,
                schema_version=schema_version,
            )
            _validate_record_chain(
                record,
                expected_previous=previous_record_sha256,
                line_number=line_number,
            )
            if record["run_id"] != header["run_id"]:
                raise LargeLLMError("request journal terminal run ID mismatch")
            outcome_count = sum(item.get("record_type") == "outcome" for item in records)
            if record["outcome_count"] != outcome_count:
                raise LargeLLMError("request journal terminal outcome count mismatch")
            for key in ("provider_policy_sha256", "privacy_sha256"):
                if record[key] != header.get(key):
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal terminal {label} mismatch")
            if "prompt_set_sha256" in record and record["prompt_set_sha256"] != header.get(
                "prompt_set_sha256"
            ):
                raise LargeLLMError("request journal terminal prompt-set fingerprint mismatch")
            if schema_version == _SCHEMA_VERSION and (
                record["attempt_set_count"] != len(attempt_records)
                or record["attempt_set_sha256"] != _attempt_set_sha256(attempt_records)
            ):
                raise LargeLLMError("request journal terminal attempt evidence mismatch")
            terminal = record
            previous_record_sha256 = str(record["record_sha256"])
            continue
        if record_type == "attempt":
            if schema_version != _SCHEMA_VERSION:
                raise LargeLLMError("legacy request journal cannot contain attempt records")
            case_id = record.get("case_id")
            if isinstance(case_id, str) and case_id in identifiers:
                raise LargeLLMError("request journal attempt transition occurs after its outcome")
            _validate_record_chain(
                record,
                expected_previous=previous_record_sha256,
                line_number=line_number,
            )
            attempt = _attempt_from_record(record, line_number=line_number)
            if record["run_id"] != header["run_id"]:
                raise LargeLLMError("request journal attempt run ID mismatch")
            prior = attempts_by_case.setdefault(attempt.case_id, [])
            if any(
                item.reservation_id == attempt.reservation_id and item.status == attempt.status
                for item in prior
            ):
                raise LargeLLMError("request journal contains duplicate attempt transition")
            _validate_attempt_transition(prior, attempt)
            prior.append(attempt)
            attempt_records.append(attempt)
            records.append(record)
            previous_record_sha256 = str(record["record_sha256"])
            continue
        if record_type != "outcome":
            raise LargeLLMError(f"request journal line {line_number} record type is invalid")
        outcome = _outcome_from_record(
            record,
            line_number=line_number,
            schema_version=schema_version,
        )
        if schema_version in {_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}:
            _validate_record_chain(
                record,
                expected_previous=previous_record_sha256,
                line_number=line_number,
            )
        for key in identity_keys:
            actual = record[key] if key in record else getattr(outcome, key, None)
            if key == "prompt_set_sha256" and key not in header:
                continue
            if actual != header.get(key):
                label = key.replace("_sha256", " fingerprint").replace("_", " ")
                raise LargeLLMError(f"request journal {label} mismatch")
        if outcome.case_id in identifiers:
            raise LargeLLMError(f"request journal contains duplicate case ID: {outcome.case_id}")
        identifiers.add(outcome.case_id)
        if schema_version == _SCHEMA_VERSION:
            case_attempts = attempts_by_case.get(outcome.case_id, [])
            if record["attempt_set_count"] != len(case_attempts) or record[
                "attempt_set_sha256"
            ] != _attempt_set_sha256(case_attempts):
                raise LargeLLMError("request journal outcome attempt evidence mismatch")
            if case_attempts and any(
                attempt.prompt_sha256 != outcome.prompt_sha256 for attempt in case_attempts
            ):
                raise LargeLLMError("request journal attempt prompt fingerprint mismatch")
            synthetic = (
                outcome.prediction is not None and outcome.prediction.completion.synthetic_backend
            )
            if not synthetic and outcome.attempt_count != len(
                {item.attempt_number for item in case_attempts}
            ):
                raise LargeLLMError("request journal outcome attempt count mismatch")
            if case_attempts:
                latest = case_attempts[-1]
                if latest.authoritative_cost_usd is None:
                    # A case can be durably represented by a budget-blocked,
                    # request-failed, or unresolved-cost outcome while its
                    # latest attempt still retains an unresolved ceiling.  The
                    # ceiling is the blocker and must not be mistaken for
                    # spend; only a zero-cost failure outcome is admissible.
                    if outcome.status not in {
                        "budget_blocked",
                        "request_failed",
                        "cost_unresolved",
                    } or outcome.authoritative_cost_usd != Decimal("0"):
                        raise LargeLLMError(
                            "request journal outcome cost does not match attempt evidence"
                        )
                elif latest.status not in {"completed", "terminal_failure"}:
                    raise LargeLLMError(
                        "request journal outcome cost does not match attempt evidence"
                    )
                elif latest.authoritative_cost_usd != outcome.authoritative_cost_usd and not (
                    outcome.status == "budget_blocked"
                    and outcome.authoritative_cost_usd == Decimal("0")
                    and latest.status == "completed"
                ):
                    raise LargeLLMError(
                        "request journal outcome cost does not match attempt evidence"
                    )
        records.append(record)
        if schema_version in {_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}:
            previous_record_sha256 = str(record["record_sha256"])
    return header, tuple(records), terminal


def _prompt_set_from_records(records: Sequence[Mapping[str, object]]) -> str | None:
    """Derive a prompt-set digest from legacy records when every hash exists."""
    pairs = []
    for record in records:
        prompt = record.get("prompt_sha256")
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not isinstance(prompt, str):
            return None
        pairs.append((case_id, prompt))
    if not pairs:
        return None
    try:
        return prompt_set_sha256(tuple(pairs))
    except LargeLLMError:
        return None


def _upgrade_legacy_resume_log(
    header: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
    *,
    provider_policy_sha256: str | None = None,
    privacy_sha256: str | None = None,
    prompt_set_sha256: str | None = None,
    source_schema_version: int = _LEGACY_RESUME_SCHEMA_VERSION,
) -> bytes:
    """Return a terminal-free v3 journal from a validated legacy v2 resume log.

    Schema v2 is deliberately a read-only compatibility boundary. Its records are
    unchained, so their values receive full typed validation before this one-way
    migration; the v3 hash chain detects later corruption but is not authentication.
    """
    upgraded_header = {
        **header,
        "schema_version": _LEGACY_CHAINED_SCHEMA_VERSION,
        "provider_policy_sha256": (
            provider_policy_sha256
            if provider_policy_sha256 is not None
            else header.get("provider_policy_sha256")
        ),
        "privacy_sha256": privacy_sha256
        if privacy_sha256 is not None
        else header.get("privacy_sha256"),
    }
    if prompt_set_sha256 is None:
        prompt_set_sha256 = _prompt_set_from_records(records)
    if prompt_set_sha256 is not None:
        upgraded_header["prompt_set_sha256"] = prompt_set_sha256
    _validate_header(
        upgraded_header,
        allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
    )
    previous_record_sha256 = _header_sha256(upgraded_header)
    upgraded_records: list[dict[str, object]] = []
    attributed_spend = Decimal("0")
    budget_checkpoint: BudgetSnapshot | None = None
    for record in records:
        outcome = _outcome_from_record(
            record,
            line_number=None,
            schema_version=source_schema_version,
        )
        if upgraded_header["provider_policy_sha256"] is not None:
            outcome = replace(
                outcome,
                provider_policy_sha256=upgraded_header["provider_policy_sha256"],
            )
        if upgraded_header["privacy_sha256"] is not None:
            outcome = replace(outcome, privacy_sha256=upgraded_header["privacy_sha256"])
        if prompt_set_sha256 is not None:
            outcome = replace(outcome, prompt_set_sha256=prompt_set_sha256)
        upgraded = _outcome_record(
            outcome,
            run_id=str(upgraded_header["run_id"]),
            model_metadata_sha256=upgraded_header["model_metadata_sha256"],
            provider_policy_sha256=upgraded_header.get("provider_policy_sha256"),
            privacy_sha256=upgraded_header.get("privacy_sha256"),  # type: ignore[arg-type]
            previous_record_sha256=previous_record_sha256,
            schema_version=_LEGACY_CHAINED_SCHEMA_VERSION,
        )
        upgraded_records.append(upgraded)
        previous_record_sha256 = str(upgraded["record_sha256"])
        assert outcome.authoritative_cost_usd is not None
        attributed_spend = _money_sum((attributed_spend, outcome.authoritative_cost_usd))
        budget_checkpoint = outcome.budget_checkpoint
    if budget_checkpoint is not None and budget_checkpoint.spent_usd < attributed_spend:
        raise LargeLLMError("request journal budget spent is below accepted outcome costs")
    return b"".join(_canonical_json(record) for record in (upgraded_header, *upgraded_records))


def _upgrade_chained_attempt_log(
    header: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
    *,
    prompt_set_sha256: str | None = None,
) -> bytes:
    """Upgrade an in-progress schema-v3 log before its first attempt row.

    Existing in-progress schema-v3 journals can have no attempt evidence. Once
    a live transport needs to persist an attempt, their chained outcome rows
    are re-emitted with the schema-v4 attempt-set fields and a new chain root.
    The upgrade is written together with the first attempt row by
    :meth:`RequestJournal.append_attempt`, so a crash cannot expose a partially
    migrated chain.
    """
    if header.get("schema_version") not in {
        _LEGACY_CHAINED_SCHEMA_VERSION,
        _SCHEMA_VERSION,
    }:
        raise LargeLLMError("request journal is not a chained journal")
    upgraded_header = {**header, "schema_version": _SCHEMA_VERSION}
    if prompt_set_sha256 is not None:
        upgraded_header["prompt_set_sha256"] = prompt_set_sha256
    _validate_header(upgraded_header)
    previous_record_sha256 = _header_sha256(upgraded_header)
    upgraded_records: list[dict[str, object]] = []
    attempts_by_case: dict[str, list[AttemptEvidence]] = {}
    source_schema_version = int(header["schema_version"])
    for record in records:
        if record.get("record_type") == "attempt":
            attempt = _attempt_from_record(record, line_number=None)
            attempts_by_case.setdefault(attempt.case_id, []).append(attempt)
            upgraded = _attempt_record(
                attempt,
                run_id=str(upgraded_header["run_id"]),
                previous_record_sha256=previous_record_sha256,
            )
        elif record.get("record_type") == "outcome":
            outcome = _outcome_from_record(
                record,
                line_number=None,
                schema_version=source_schema_version,
            )
            if prompt_set_sha256 is not None:
                outcome = replace(outcome, prompt_set_sha256=prompt_set_sha256)
            upgraded = _outcome_record(
                outcome,
                run_id=str(upgraded_header["run_id"]),
                model_metadata_sha256=upgraded_header["model_metadata_sha256"],
                provider_policy_sha256=upgraded_header.get("provider_policy_sha256"),
                privacy_sha256=upgraded_header.get("privacy_sha256"),  # type: ignore[arg-type]
                previous_record_sha256=previous_record_sha256,
                attempts=tuple(attempts_by_case.get(outcome.case_id, ())),
                schema_version=_SCHEMA_VERSION,
            )
        else:
            raise LargeLLMError("chained request journal has an invalid record")
        upgraded_records.append(upgraded)
        previous_record_sha256 = str(upgraded["record_sha256"])
    return b"".join(_canonical_json(record) for record in (upgraded_header, *upgraded_records))


class RequestJournal:
    """Atomic v3/v4 journal, upgrading a valid terminal-free v2 resume log."""

    def __init__(
        self,
        path: Path,
        *,
        allow_legacy_resume: bool = False,
        fresh: bool = False,
        run_id: str,
        baseline: str,
        input_sha256: str | None,
        config_sha256: str,
        catalog_sha256: str,
        summary_sha256: str,
        training_sha256: str | None,
        model_id: str,
        provider_slug: str,
        model_metadata_sha256: str | None = None,
        provider_policy_sha256: str | None = None,
        privacy_sha256: str | None = None,
        prompt_set_sha256: str | None = None,
    ) -> None:
        """Create or validate the durable journal header.

        Args:
            path: Journal JSONL path.
            allow_legacy_resume: Explicit authority to accept and atomically
                migrate a validated terminal-free schema v2 resume journal.
            fresh: Explicit authority requiring atomic no-clobber creation of a
                new journal rather than acceptance of an existing journal.
            run_id: Stable evaluation-run identifier.
            baseline: ``b4`` or ``b5``.
            input_sha256: Exact input snapshot fingerprint, if available.
            config_sha256: Exact generation-configuration fingerprint.
            catalog_sha256: Exact catalog snapshot fingerprint.
            summary_sha256: Exact compiled catalog-summary fingerprint.
            training_sha256: Exact B5 training fingerprint, or ``None`` for B4.
            model_id: Exact configured model identifier.
            provider_slug: Exact configured provider.
            model_metadata_sha256: Accepted endpoint-metadata fingerprint, if any.

        Raises:
            LargeLLMError: If the path/header is unsafe, invalid, or mismatched.
        """
        if not isinstance(path, Path):
            raise LargeLLMError("request journal path must be a pathlib.Path")
        if not isinstance(allow_legacy_resume, bool):
            raise LargeLLMError("legacy resume authority must be boolean")
        if not isinstance(fresh, bool):
            raise LargeLLMError("fresh journal authority must be boolean")
        if fresh and allow_legacy_resume:
            raise LargeLLMError("fresh journal cannot accept resume authority")
        header = _journal_header(
            run_id=run_id,
            baseline=baseline,
            input_sha256=input_sha256,
            config_sha256=config_sha256,
            catalog_sha256=catalog_sha256,
            summary_sha256=summary_sha256,
            training_sha256=training_sha256,
            model_id=model_id,
            provider_slug=provider_slug,
            model_metadata_sha256=model_metadata_sha256,
            provider_policy_sha256=provider_policy_sha256,
            privacy_sha256=privacy_sha256,
            prompt_set_sha256=prompt_set_sha256,
        )
        existing = _existing_bytes(path)
        if existing is None:
            try:
                writer = _atomic_create if fresh else _atomic_write
                writer(path, _canonical_json(header))
            except Exception as error:
                raise LargeLLMError(f"unable to initialize request journal: {error}") from error
        else:
            if fresh:
                raise LargeLLMError("unable to initialize request journal: path already exists")
            allowed_versions = (
                _RESUME_SCHEMA_VERSIONS if allow_legacy_resume else frozenset({_SCHEMA_VERSION})
            )
            if not allow_legacy_resume:
                allowed_versions = frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION})
            accepted, records, _terminal = _parse_request_log(
                existing, allowed_versions=allowed_versions
            )
            for key, expected in header.items():
                if key == "schema_version":
                    continue
                # Legacy v2 has no policy/privacy fields.  Their values are
                # supplied by the current, pre-network resume identity and are
                # bound while performing the one-way migration below.
                if accepted["schema_version"] == _LEGACY_RESUME_SCHEMA_VERSION and key in {
                    "provider_policy_sha256",
                    "privacy_sha256",
                }:
                    continue
                if key == "prompt_set_sha256" and (
                    key not in accepted
                    or (accepted.get("baseline") == "b4" and accepted.get(key) != expected)
                ):
                    continue
                if accepted.get(key) != expected:
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal {label} mismatch")
            accepted_schema = int(accepted["schema_version"])
            needs_v2_migration = accepted_schema == _LEGACY_RESUME_SCHEMA_VERSION
            needs_prompt_upgrade = (
                header.get("prompt_set_sha256") is not None
                and accepted.get("prompt_set_sha256") != header.get("prompt_set_sha256")
                and accepted_schema
                in {
                    _LEGACY_CHAINED_SCHEMA_VERSION,
                    _SCHEMA_VERSION,
                }
            )
            if needs_v2_migration or (
                needs_prompt_upgrade and accepted_schema == _LEGACY_CHAINED_SCHEMA_VERSION
            ):
                try:
                    migrated = _upgrade_legacy_resume_log(
                        accepted,
                        records,
                        provider_policy_sha256=header["provider_policy_sha256"],
                        privacy_sha256=header["privacy_sha256"],
                        prompt_set_sha256=header.get("prompt_set_sha256"),
                        source_schema_version=int(accepted["schema_version"]),
                    )
                    _atomic_write(path, migrated)
                    header = _decode_json_line(migrated.splitlines(keepends=True)[0], 1)
                except Exception as error:
                    raise LargeLLMError(
                        f"unable to upgrade schema v2 request journal: {error}"
                    ) from error
            elif needs_prompt_upgrade and accepted_schema == _SCHEMA_VERSION:
                try:
                    migrated = _upgrade_chained_attempt_log(
                        accepted,
                        records,
                        prompt_set_sha256=header.get("prompt_set_sha256"),  # type: ignore[arg-type]
                    )
                    _parse_request_log(
                        migrated,
                        allowed_versions=frozenset(
                            {_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}
                        ),
                    )
                    _atomic_write(path, migrated)
                    header = _decode_json_line(migrated.splitlines(keepends=True)[0], 1)
                except Exception as error:
                    raise LargeLLMError(
                        f"unable to upgrade schema v4 request journal: {error}"
                    ) from error
            else:
                # Keep the on-disk schema (including v4 attempt journals) as
                # the fixed header used by subsequent appends.
                header = accepted
        self._path = path
        self._header = header

    def append(self, outcome: EvaluationOutcome) -> None:
        """Durably append one validated outcome using atomic replacement.

        Args:
            outcome: Immutable completed case evidence matching the fixed header.

        Raises:
            LargeLLMError: If evidence mismatches, duplicates a case, or cannot be saved.
        """
        try:
            existing = _existing_bytes(self._path)
            if existing is None:
                raise LargeLLMError("request journal disappeared before append")
            header, records, terminal = _parse_request_log(
                existing,
                allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
            )
            if header != self._header:
                raise LargeLLMError("request journal header changed before append")
            if terminal is not None:
                raise LargeLLMError("request journal terminal checkpoint forbids append")
            previous_record_sha256 = (
                str(records[-1]["record_sha256"]) if records else _header_sha256(header)
            )
            schema_version = int(header["schema_version"])
            case_attempts = tuple(
                _attempt_from_record(record, line_number=None)
                for record in records
                if record.get("record_type") == "attempt"
                and record.get("case_id") == outcome.case_id
            )
            record = _outcome_record(
                replace(
                    outcome,
                    prompt_set_sha256=header.get("prompt_set_sha256", outcome.prompt_set_sha256),
                ),
                run_id=str(self._header["run_id"]),
                model_metadata_sha256=self._header["model_metadata_sha256"],
                provider_policy_sha256=self._header.get("provider_policy_sha256"),
                privacy_sha256=self._header["privacy_sha256"],  # type: ignore[arg-type]
                previous_record_sha256=previous_record_sha256,
                attempts=case_attempts,
                schema_version=schema_version,
            )
            _outcome_from_record(
                record,
                line_number=None,
                schema_version=schema_version,
            )
            for key in (
                "baseline",
                "input_sha256",
                "config_sha256",
                "catalog_sha256",
                "summary_sha256",
                "training_sha256",
                "model_id",
                "provider_slug",
                "model_metadata_sha256",
                "provider_policy_sha256",
                "privacy_sha256",
            ):
                if record[key] != header[key]:
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal {label} mismatch")
            if (
                "prompt_set_sha256" in header
                and record.get("prompt_set_sha256") != header["prompt_set_sha256"]
            ):
                raise LargeLLMError("request journal prompt-set fingerprint mismatch")
            if any(
                record["case_id"] == prior["case_id"]
                for prior in records
                if prior.get("record_type") == "outcome"
            ):
                raise LargeLLMError(
                    f"request journal contains duplicate case ID: {record['case_id']}"
                )
            updated = existing + _canonical_json(record)
            _parse_request_log(
                updated,
                allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
            )
            _atomic_write(self._path, updated)
        except LargeLLMError:
            raise
        except Exception as error:
            raise LargeLLMError(f"unable to append request journal: {error}") from error

    async def append_attempt(self, evidence: AttemptEvidence) -> None:
        """Durably append one live attempt accounting transition.

        The transport invokes this after every reserve, hold, and reconciliation
        checkpoint.  Atomic replacement makes the exact final checkpoint survive
        cooperative cancellation.
        """
        try:
            existing = _existing_bytes(self._path)
            if existing is None:
                raise LargeLLMError("request journal disappeared before attempt append")
            header, records, terminal = _parse_request_log(
                existing,
                allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
            )
            if header != self._header:
                raise LargeLLMError("request journal header changed before attempt append")
            if terminal is not None:
                raise LargeLLMError("request journal terminal checkpoint forbids append")
            pending_header = header
            if int(header["schema_version"]) == _LEGACY_CHAINED_SCHEMA_VERSION:
                existing = _upgrade_chained_attempt_log(header, records)
                header, records, terminal = _parse_request_log(
                    existing,
                    allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
                )
                pending_header = header
            previous = str(records[-1]["record_sha256"]) if records else _header_sha256(header)
            record = _attempt_record(
                evidence, run_id=str(header["run_id"]), previous_record_sha256=previous
            )
            _attempt_from_record(record, line_number=None)
            updated = existing + _canonical_json(record)
            _parse_request_log(
                updated,
                allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
            )
            _atomic_write(self._path, updated)
            self._header = pending_header
        except LargeLLMError:
            raise
        except Exception as error:
            raise LargeLLMError(f"unable to append request journal attempt: {error}") from error

    def next_attempt_number(self, request_id: str) -> int:
        """Return one above the largest durable attempt number for a case."""
        if not isinstance(request_id, str):
            raise LargeLLMError("request journal attempt request ID is invalid")
        return (
            max(
                (item.attempt_number for item in self.attempts if item.request_id == request_id),
                default=0,
            )
            + 1
        )

    @property
    def attempts(self) -> tuple[AttemptEvidence, ...]:
        """Return the canonical attempt evidence currently retained by this journal."""
        payload = _existing_bytes(self._path)
        if payload is None:
            raise LargeLLMError("request journal disappeared before attempt load")
        _header, records, _terminal = _parse_request_log(
            payload,
            allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
        )
        return tuple(
            _attempt_from_record(record, line_number=None)
            for record in records
            if record.get("record_type") == "attempt"
        )


def load_resume_state(
    request_log: Path,
    *,
    expected_input_sha256: str,
    expected_config_sha256: str,
    expected_run_id: str,
    expected_model_metadata_sha256: str | None,
    expected_catalog_sha256: str | object = _UNSET,
    expected_summary_sha256: str | object = _UNSET,
    expected_training_sha256: str | None | object = _UNSET,
    expected_model_id: str | object = _UNSET,
    expected_provider_slug: str | object = _UNSET,
    expected_provider_policy_sha256: str | None | object = _UNSET,
    expected_privacy_sha256: str | None | object = _UNSET,
    expected_baseline: str | object = _UNSET,
    expected_prompt_sha256_by_case: Mapping[str, str] | object = _UNSET,
    expected_retrieval_sha256_by_case: Mapping[str, str] | object = _UNSET,
    expected_prompt_set_sha256: str | object = _UNSET,
) -> ResumeState:
    """Load a journal only after every row and requested identity validates.

    Args:
        request_log: Existing journal JSONL path.
        expected_input_sha256: Exact current input snapshot fingerprint.
        expected_config_sha256: Exact current generation-config fingerprint.
        expected_run_id: Exact current run identifier.
        expected_model_metadata_sha256: Exact accepted endpoint-metadata fingerprint.
        expected_catalog_sha256: Exact current catalog fingerprint.
        expected_summary_sha256: Exact current compiled-summary fingerprint.
        expected_training_sha256: Exact accepted B5 training fingerprint, or ``None``.
        expected_model_id: Exact configured remote model identifier.
        expected_provider_slug: Exact configured provider identity.
        expected_provider_policy_sha256: Exact provider policy fingerprint.
        expected_privacy_sha256: Exact accepted local privacy-review fingerprint.
        expected_baseline: Exact B4/B5 baseline identity.
        expected_prompt_sha256_by_case: Exact current prompt hash per case.
        expected_retrieval_sha256_by_case: Exact current retrieval evidence hash per case.
        expected_prompt_set_sha256: Canonical digest over the ordered prompt set.

    Returns:
        Validated completed IDs, prior authoritative cost, and immutable records.

    Raises:
        LargeLLMError: If the journal is missing, malformed, duplicate, or stale.
    """
    if not isinstance(request_log, Path):
        raise LargeLLMError("request journal path must be a pathlib.Path")
    _validate_digest(expected_input_sha256, "expected input fingerprint")
    _validate_digest(expected_config_sha256, "expected config fingerprint")
    _validate_digest(
        expected_model_metadata_sha256,
        "expected model metadata fingerprint",
        optional=True,
    )
    for expected, label in (
        (expected_catalog_sha256, "expected catalog fingerprint"),
        (expected_summary_sha256, "expected summary fingerprint"),
        (expected_provider_policy_sha256, "expected provider policy fingerprint"),
        (expected_privacy_sha256, "expected privacy fingerprint"),
    ):
        if expected is not _UNSET:
            _validate_digest(expected, label, optional=True)
    if expected_training_sha256 is not _UNSET:
        _validate_digest(expected_training_sha256, "expected training fingerprint", optional=True)
    for expected, label in (
        (expected_model_id, "expected model ID"),
        (expected_provider_slug, "expected provider"),
    ):
        if expected is not _UNSET and (not isinstance(expected, str) or not expected):
            raise LargeLLMError(f"{label} is invalid")
    if expected_baseline is not _UNSET and expected_baseline not in {"b4", "b5"}:
        raise LargeLLMError("expected baseline is invalid")
    if expected_prompt_sha256_by_case is not _UNSET:
        if not isinstance(expected_prompt_sha256_by_case, Mapping):
            raise LargeLLMError("expected prompt hashes must be a mapping")
        for case_id, prompt_hash in expected_prompt_sha256_by_case.items():
            if not isinstance(case_id, str):
                raise LargeLLMError("expected prompt case ID is invalid")
            _validate_digest(prompt_hash, "expected prompt fingerprint")
    if expected_retrieval_sha256_by_case is not _UNSET:
        if not isinstance(expected_retrieval_sha256_by_case, Mapping):
            raise LargeLLMError("expected retrieval hashes must be a mapping")
        if expected_prompt_sha256_by_case is _UNSET:
            raise LargeLLMError("expected retrieval hashes require expected prompt hashes")
        for case_id, retrieval_hash in expected_retrieval_sha256_by_case.items():
            if not isinstance(case_id, str):
                raise LargeLLMError("expected retrieval case ID is invalid")
            _validate_digest(retrieval_hash, "expected retrieval fingerprint")
    if expected_prompt_set_sha256 is not _UNSET:
        _validate_digest(expected_prompt_set_sha256, "expected prompt-set fingerprint")
    if not isinstance(expected_run_id, str) or _RUN_ID_RE.fullmatch(expected_run_id) is None:
        raise LargeLLMError("expected run ID is invalid")
    payload = _existing_bytes(request_log)
    if payload is None:
        raise LargeLLMError("request journal does not exist")
    # Only resume accepts the immediately preceding, terminal-free v2 format.
    # Publication loaders intentionally retain the parser's v3-only default.
    header, records, terminal = _parse_request_log(
        payload,
        allowed_versions=_RESUME_SCHEMA_VERSIONS,
    )
    outcome_records = tuple(record for record in records if record.get("record_type") == "outcome")
    schema_version = int(header["schema_version"])
    for key, expected, label in (
        ("input_sha256", expected_input_sha256, "input fingerprint"),
        ("config_sha256", expected_config_sha256, "config fingerprint"),
        ("run_id", expected_run_id, "run ID"),
        (
            "model_metadata_sha256",
            expected_model_metadata_sha256,
            "model metadata fingerprint",
        ),
    ):
        if header[key] != expected:
            raise LargeLLMError(f"request journal {label} mismatch")
    optional_identity = (
        ("catalog_sha256", expected_catalog_sha256, "catalog fingerprint"),
        ("summary_sha256", expected_summary_sha256, "summary fingerprint"),
        ("training_sha256", expected_training_sha256, "training fingerprint"),
        ("model_id", expected_model_id, "model ID"),
        ("provider_slug", expected_provider_slug, "provider"),
        ("provider_policy_sha256", expected_provider_policy_sha256, "provider policy fingerprint"),
        ("privacy_sha256", expected_privacy_sha256, "privacy fingerprint"),
        ("baseline", expected_baseline, "baseline"),
    )
    for key, expected, label in optional_identity:
        legacy_identity_gap = (
            schema_version == _LEGACY_RESUME_SCHEMA_VERSION
            and key in {"provider_policy_sha256", "privacy_sha256"}
            and key not in header
        )
        if expected is not _UNSET and not legacy_identity_gap and header.get(key) != expected:
            raise LargeLLMError(f"request journal {label} mismatch")
    if not records:
        raise LargeLLMError("request journal has no resumable records")
    cost = Decimal("0")
    budget_checkpoint: BudgetSnapshot | None = None
    terminal_metrics: LargeEvaluationMetrics | None = None
    attempt_records: list[AttemptEvidence] = []
    for record in records:
        if record.get("record_type") == "attempt":
            attempt_records.append(_attempt_from_record(record, line_number=None))
            budget_checkpoint = attempt_records[-1].budget_checkpoint
            continue
        outcome = _outcome_from_record(
            record,
            line_number=None,
            schema_version=schema_version,
        )
        budget_checkpoint = outcome.budget_checkpoint
        assert outcome.authoritative_cost_usd is not None
        cost = _money_sum((cost, outcome.authoritative_cost_usd))
    if expected_prompt_sha256_by_case is not _UNSET:
        actual_prompt_hashes = {
            str(record["case_id"]): record.get("prompt_sha256") for record in outcome_records
        }
        expected_prompt_hashes = dict(expected_prompt_sha256_by_case)
        if any(
            case_id not in expected_prompt_hashes or prompt != expected_prompt_hashes[case_id]
            for case_id, prompt in actual_prompt_hashes.items()
        ):
            raise LargeLLMError("request journal prompt fingerprint mismatch")
        if any(
            attempt.case_id not in expected_prompt_hashes
            or attempt.prompt_sha256 != expected_prompt_hashes[attempt.case_id]
            for attempt in attempt_records
        ):
            raise LargeLLMError("request journal attempt prompt fingerprint mismatch")
        derived_values: tuple[tuple[str, object], ...]
        if expected_retrieval_sha256_by_case is not _UNSET:
            expected_retrieval_hashes = dict(expected_retrieval_sha256_by_case)
            if set(expected_retrieval_hashes) != set(expected_prompt_hashes):
                raise LargeLLMError("expected retrieval evidence must cover every prompt case")
            actual_retrieval_hashes = {
                str(record["case_id"]): record.get("retrieval_sha256") for record in outcome_records
            }
            if any(
                case_id not in expected_retrieval_hashes
                or (retrieval is not None and retrieval != expected_retrieval_hashes[case_id])
                or (retrieval is None and header.get("baseline") != "b4")
                for case_id, retrieval in actual_retrieval_hashes.items()
            ):
                raise LargeLLMError("request journal retrieval fingerprint mismatch")
            derived_values = tuple(
                (
                    case_id,
                    (prompt_hash, expected_retrieval_hashes[case_id]),
                )
                for case_id, prompt_hash in expected_prompt_hashes.items()
            )
        else:
            derived_values = tuple(expected_prompt_hashes.items())
        derived_prompt_set = prompt_set_sha256(derived_values)
        if (
            expected_prompt_set_sha256 is not _UNSET
            and derived_prompt_set != expected_prompt_set_sha256
        ):
            raise LargeLLMError("request journal prompt-set fingerprint mismatch")
        if "prompt_set_sha256" in header and header["prompt_set_sha256"] != derived_prompt_set:
            legacy_prompt_set = prompt_set_sha256(tuple(expected_prompt_hashes.items()))
            if not (
                header.get("baseline") == "b4" and header["prompt_set_sha256"] == legacy_prompt_set
            ):
                raise LargeLLMError("request journal prompt-set fingerprint mismatch")
    elif (
        expected_prompt_set_sha256 is not _UNSET
        and schema_version != _LEGACY_RESUME_SCHEMA_VERSION
        and header.get("prompt_set_sha256") != expected_prompt_set_sha256
    ):
        raise LargeLLMError("request journal prompt-set fingerprint mismatch")
    if terminal is not None:
        budget_checkpoint, terminal_metrics = _terminal_evidence(
            terminal,
            line_number=None,
            schema_version=schema_version,
        )
    assert budget_checkpoint is not None
    unattributed_spend = _money_difference(budget_checkpoint.spent_usd, cost)
    if unattributed_spend < Decimal("0"):
        raise LargeLLMError("request journal budget spent is below accepted outcome costs")
    if terminal_metrics is not None:
        outcomes = tuple(
            _outcome_from_record(
                record,
                line_number=None,
                schema_version=schema_version,
            )
            for record in outcome_records
        )
        if terminal_metrics != _metrics(outcomes, unattributed_spend_usd=unattributed_spend):
            raise LargeLLMError("request journal terminal metrics are not derived")
    provider_policy_sha256 = header.get("provider_policy_sha256")
    if provider_policy_sha256 is None and expected_provider_policy_sha256 is not _UNSET:
        provider_policy_sha256 = expected_provider_policy_sha256
    privacy_sha256 = header.get("privacy_sha256")
    if privacy_sha256 is None and expected_privacy_sha256 is not _UNSET:
        privacy_sha256 = expected_privacy_sha256
    return ResumeState(
        completed_case_ids=tuple(str(record["case_id"]) for record in outcome_records),
        prior_cost_usd=cost,
        unattributed_spend_usd=unattributed_spend,
        prior_records=outcome_records,
        budget_checkpoint=budget_checkpoint,
        run_id=str(header["run_id"]),
        baseline=str(header["baseline"]),
        input_sha256=header["input_sha256"],  # type: ignore[arg-type]
        config_sha256=str(header["config_sha256"]),
        catalog_sha256=str(header["catalog_sha256"]),
        summary_sha256=str(header["summary_sha256"]),
        training_sha256=header["training_sha256"],  # type: ignore[arg-type]
        model_id=str(header["model_id"]),
        provider_slug=str(header["provider_slug"]),
        model_metadata_sha256=header["model_metadata_sha256"],  # type: ignore[arg-type]
        schema_version=schema_version,
        provider_policy_sha256=provider_policy_sha256,  # type: ignore[arg-type]
        privacy_sha256=privacy_sha256,  # type: ignore[arg-type]
        prompt_set_sha256=(
            expected_prompt_set_sha256
            if expected_prompt_set_sha256 is not _UNSET
            else header.get("prompt_set_sha256")
        ),
        retrieval_sha256_by_case=(
            dict(expected_retrieval_sha256_by_case)
            if expected_retrieval_sha256_by_case is not _UNSET
            else None
        ),
        journal_prompt_set_sha256=header.get("prompt_set_sha256"),
        prior_journal_records=records,
        attempt_records=tuple(attempt_records),
    )


def serialize_predictions(run: LargeEvaluationRun) -> bytes:
    """Return deterministic ordered prediction/outcome JSONL for one run.

    Args:
        run: Validated immutable evaluation run to serialize.

    Returns:
        Canonical UTF-8 JSONL prediction rows.

    Raises:
        LargeLLMError: If the run cannot produce internally consistent evidence.
    """
    rows = (
        {
            "run_id": run.run_id,
            "seed": run.seed,
            "generated_at_utc": run.generated_at_utc,
            "model_metadata_sha256": run.model_metadata_sha256,
            **_canonical_value(
                asdict(
                    replace(
                        outcome,
                        prompt_set_sha256=(outcome.prompt_set_sha256 or run.prompt_set_sha256),
                    )
                )
            ),
        }
        for outcome in run.outcomes
    )
    return b"".join(_canonical_json(row) for row in rows)


def _request_log_parts(
    run: LargeEvaluationRun,
) -> tuple[dict[str, object], tuple[dict[str, object], ...], dict[str, object]]:
    schema_version = _SCHEMA_VERSION
    header = _journal_header(
        run_id=run.run_id,
        baseline=run.baseline,
        input_sha256=run.input_sha256,
        config_sha256=run.config_sha256,
        catalog_sha256=run.catalog_sha256,
        summary_sha256=run.summary_sha256,
        training_sha256=run.training_sha256,
        model_id=run.model_id,
        provider_slug=run.provider_slug,
        model_metadata_sha256=run.model_metadata_sha256,
        provider_policy_sha256=run.provider_policy_sha256,
        privacy_sha256=run.privacy_sha256,
        prompt_set_sha256=run.prompt_set_sha256,
        schema_version=schema_version,
    )
    previous_record_sha256 = _header_sha256(header)
    records: list[dict[str, object]] = []
    attempts_by_case: dict[str, list[AttemptEvidence]] = {}
    for attempt in run.attempts:
        prior = attempts_by_case.setdefault(attempt.case_id, [])
        if any(
            item.reservation_id == attempt.reservation_id and item.status == attempt.status
            for item in prior
        ):
            raise LargeLLMError("run attempt evidence contains duplicate transitions")
        _validate_attempt_transition(prior, attempt)
        prior.append(attempt)
        attempt_record = _attempt_record(
            attempt,
            run_id=run.run_id,
            previous_record_sha256=previous_record_sha256,
        )
        records.append(attempt_record)
        previous_record_sha256 = str(attempt_record["record_sha256"])
    for outcome in run.outcomes:
        case_attempts = tuple(attempts_by_case.pop(outcome.case_id, ()))
        if outcome.prompt_set_sha256 is None and run.prompt_set_sha256 is not None:
            outcome = replace(outcome, prompt_set_sha256=run.prompt_set_sha256)
        record = _outcome_record(
            outcome,
            run_id=run.run_id,
            model_metadata_sha256=run.model_metadata_sha256,
            provider_policy_sha256=run.provider_policy_sha256,
            privacy_sha256=run.privacy_sha256,
            previous_record_sha256=previous_record_sha256,
            attempts=case_attempts,
            schema_version=schema_version,
        )
        records.append(record)
        previous_record_sha256 = str(record["record_sha256"])
    if attempts_by_case:
        raise LargeLLMError("run attempt evidence does not belong to an outcome")
    report_body = _report_body(run)
    terminal_body: dict[str, object] = {
        "record_type": "terminal",
        "run_id": run.run_id,
        "outcome_count": len(run.outcomes),
        "budget_checkpoint": _canonical_value(asdict(run.budget)),
        "metrics": _canonical_value(asdict(run.metrics)),
        "scientific_ready": run.scientific_ready,
        "blockers": list(run.blockers),
        "local_implementation_ready": run.local_implementation_ready,
        "provider_policy_sha256": run.provider_policy_sha256,
        "privacy_sha256": run.privacy_sha256,
        "report_body_sha256": hashlib.sha256(_canonical_json(report_body)).hexdigest(),
    }
    terminal_body["attempt_set_count"] = len(run.attempts)
    terminal_body["attempt_set_sha256"] = _attempt_set_sha256(run.attempts)
    terminal = _chained_record(
        terminal_body,
        previous_record_sha256=previous_record_sha256,
    )
    if run.prompt_set_sha256 is not None:
        terminal["prompt_set_sha256"] = run.prompt_set_sha256
        terminal["record_sha256"] = _record_sha256(
            {key: value for key, value in terminal.items() if key != "record_sha256"}
        )
    _terminal_evidence(
        terminal,
        line_number=None,
        schema_version=_SCHEMA_VERSION,
    )
    _parse_request_log(
        b"".join(_canonical_json(record) for record in (header, *records, terminal)),
        allowed_versions=frozenset({_LEGACY_CHAINED_SCHEMA_VERSION, _SCHEMA_VERSION}),
    )
    return header, tuple(records), terminal


def serialize_request_log(run: LargeEvaluationRun) -> bytes:
    """Return a deterministic journal sealed by a terminal checkpoint.

    Args:
        run: Validated immutable evaluation run to serialize.

    Returns:
        Canonical UTF-8 JSONL bytes with a hash-chained terminal row.

    Raises:
        LargeLLMError: If the run's journal evidence is invalid or inconsistent.
    """
    header, records, terminal = _request_log_parts(run)
    return b"".join(_canonical_json(record) for record in (header, *records, terminal))


def serialize_cost_csv(run: LargeEvaluationRun) -> bytes:
    """Return deterministic cost rows derived solely from immutable outcomes.

    Args:
        run: Validated immutable evaluation run to serialize.

    Returns:
        Canonical UTF-8 CSV rows including derived totals.

    Raises:
        LargeLLMError: If the run's cost evidence is invalid or inconsistent.
    """
    output = io.StringIO(newline="")
    fieldnames = (
        "row_type",
        "baseline",
        "run_id",
        "case_id",
        "status",
        "generation_id",
        "input_tokens",
        "output_tokens",
        "charged_cost_usd",
        "upstream_cost_usd",
        "attributed_spend_usd",
        "unattributed_spend_usd",
        "total_spent_usd",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    total = Decimal("0")
    for outcome in run.outcomes:
        prediction = outcome.prediction
        if prediction is None and outcome.status == "budget_blocked":
            continue
        completion = prediction.completion if prediction is not None else None
        charged = outcome.authoritative_cost_usd
        assert charged is not None
        total = _money_sum((total, charged))
        writer.writerow(
            {
                "row_type": "request",
                "baseline": run.baseline,
                "run_id": run.run_id,
                "case_id": outcome.case_id,
                "status": outcome.status,
                "generation_id": completion.generation_id if completion is not None else "",
                "input_tokens": completion.input_tokens if completion is not None else "",
                "output_tokens": completion.output_tokens if completion is not None else "",
                "charged_cost_usd": canonical_money(charged),
                "upstream_cost_usd": (
                    canonical_money(completion.upstream_cost_usd)
                    if completion is not None and completion.upstream_cost_usd is not None
                    else ""
                ),
                "attributed_spend_usd": canonical_money(charged),
                "unattributed_spend_usd": "",
                "total_spent_usd": "",
            }
        )
    writer.writerow(
        {
            "row_type": "total",
            "baseline": run.baseline,
            "run_id": run.run_id,
            "case_id": "",
            "status": "total",
            "generation_id": "",
            "input_tokens": run.metrics.input_tokens,
            "output_tokens": run.metrics.output_tokens,
            "charged_cost_usd": canonical_money(total),
            "upstream_cost_usd": "",
            "attributed_spend_usd": canonical_money(run.metrics.attributed_spend_usd),
            "unattributed_spend_usd": canonical_money(run.metrics.unattributed_spend_usd),
            "total_spent_usd": canonical_money(run.metrics.total_spent_usd),
        }
    )
    return output.getvalue().encode("utf-8")


def _report_body(run: LargeEvaluationRun) -> dict[str, object]:
    counts = {
        "completed": run.metrics.completed,
        "extraction_failed": run.metrics.extraction_failed,
        "request_failed": run.metrics.request_failed,
        "budget_blocked": run.metrics.budget_blocked,
        "cost_unresolved": run.metrics.cost_unresolved,
    }
    return _canonical_value(
        {
            "run_id": run.run_id,
            "baseline": run.baseline,
            "seed": run.seed,
            "generated_at_utc": run.generated_at_utc,
            "input_sha256": run.input_sha256,
            "config_sha256": run.config_sha256,
            "catalog_sha256": run.catalog_sha256,
            "summary_sha256": run.summary_sha256,
            "training_sha256": run.training_sha256,
            "model_id": run.model_id,
            "provider_slug": run.provider_slug,
            "model_metadata_sha256": run.model_metadata_sha256,
            "provider_policy_sha256": run.provider_policy_sha256,
            "privacy_sha256": run.privacy_sha256,
            "prompt_set_sha256": run.prompt_set_sha256,
            "attempt_set_count": len(run.attempts),
            "attempt_set_sha256": _attempt_set_sha256(run.attempts),
            "local_implementation_ready": run.local_implementation_ready,
            "scientific_ready": run.scientific_ready,
            "blockers": run.blockers,
            "outcome_count": len(run.outcomes),
            "outcome_counts": counts,
            "authoritative_total_cost_usd": _money_sum(
                outcome.authoritative_cost_usd for outcome in run.outcomes
            ),
            "attributed_spend_usd": run.metrics.attributed_spend_usd,
            "unattributed_spend_usd": run.metrics.unattributed_spend_usd,
            "total_spent_usd": run.metrics.total_spent_usd,
            "metrics": asdict(run.metrics),
            "budget": asdict(run.budget),
        }
    )  # type: ignore[return-value]


def serialize_report(run: LargeEvaluationRun) -> bytes:
    """Return a deterministic report cross-bound to the terminal journal record.

    Args:
        run: Validated immutable evaluation run to serialize.

    Returns:
        Canonical UTF-8 JSON report bytes with its self-hash and terminal binding.

    Raises:
        LargeLLMError: If the run cannot produce a valid terminal report.
    """
    body = _report_body(run)
    _header, _records, terminal = _request_log_parts(run)
    linked_body = {
        **body,
        "request_log_terminal_sha256": terminal["record_sha256"],
    }
    return _canonical_json(
        {
            **linked_body,
            "report_sha256": hashlib.sha256(_canonical_json(linked_body)).hexdigest(),
        }
    )


def _validate_publication_run(run: LargeEvaluationRun) -> None:
    try:
        run.__post_init__()
    except LargeLLMError as error:
        raise LargeLLMError(f"publication evidence is not derived: {error}") from error


def publish_large_run(
    run: LargeEvaluationRun,
    *,
    paths: ArtifactPaths,
    protected_paths: Sequence[Path] = (),
    fresh: bool = False,
) -> None:
    """Publish all artifacts atomically in order and the report last.

    Args:
        run: Validated immutable evaluation run.
        paths: Four output destinations.
        protected_paths: Input/evidence paths that must never be overwritten.
        fresh: Require no-clobber creation for new-run publication outputs.

    Raises:
        LargeLLMError: If paths/evidence are invalid or any write/rollback fails.
    """
    if not isinstance(run, LargeEvaluationRun):
        raise LargeLLMError("publication requires a LargeEvaluationRun")
    if not isinstance(fresh, bool):
        raise LargeLLMError("fresh publication authority must be boolean")
    _validate_publication_run(run)
    validate_artifact_paths(paths, protected_paths=protected_paths)
    previous = {path: _existing_bytes(path) for path in paths.all_outputs}
    current_journal_descriptor: int | None = None
    if fresh:
        existing_output = next(
            (
                path
                for path in (paths.predictions, paths.cost_csv, paths.report)
                if previous[path] is not None
            ),
            None,
        )
        if existing_output is not None:
            raise LargeLLMError(
                f"unable to publish large-run artifacts: path already exists: {existing_output}"
            )
        if previous[paths.request_log] is None:
            raise LargeLLMError(
                "unable to publish large-run artifacts: fresh request journal is missing"
            )
        current_journal_descriptor = _open_current_file(
            paths.request_log, previous[paths.request_log]
        )
    written: dict[Path, int] = {}
    try:
        payloads = (
            serialize_predictions(run),
            serialize_request_log(run),
            serialize_cost_csv(run),
            serialize_report(run),
        )
        try:
            for path, payload in zip(paths.all_outputs, payloads, strict=True):
                if fresh and path != paths.request_log:
                    owned_descriptor = _atomic_create_owned(path, payload)
                elif fresh:
                    assert previous[path] is not None
                    assert current_journal_descriptor is not None
                    owned_descriptor = _atomic_write_if_current(
                        path,
                        payload,
                        previous[path],
                        current_journal_descriptor,
                    )
                else:
                    _atomic_write(path, payload)
                    continue
                written[path] = owned_descriptor
        except Exception as error:
            rollback_errors: list[str] = []
            rollback_paths = tuple(reversed(tuple(written))) if fresh else paths.all_outputs
            for path in rollback_paths:
                try:
                    if fresh:
                        _restore_if_current(path, written[path], previous[path])
                    else:
                        _restore(path, previous[path])
                except Exception as rollback_error:
                    rollback_errors.append(f"{path}: {rollback_error}")
            suffix = f"; rollback failed: {rollback_errors}" if rollback_errors else ""
            raise LargeLLMError(
                f"unable to publish large-run artifacts: {error}{suffix}"
            ) from error
    finally:
        for owned_descriptor in written.values():
            os.close(owned_descriptor)
        if current_journal_descriptor is not None:
            os.close(current_journal_descriptor)


def load_large_run_artifacts(report_path: Path, request_log_path: Path) -> LargeEvaluationRun:
    """Load one typed run only when its report and durable journal agree.

    Args:
        report_path: Canonical JSON report written by :func:`publish_large_run`.
        request_log_path: Canonical request journal written for the same run.

    Returns:
        A fully validated immutable evaluation run suitable for local summaries.

    Raises:
        LargeLLMError: If either artifact is missing, non-canonical, tampered, or
            disagrees with the run derived from durable outcome evidence.
    """
    if not isinstance(report_path, Path) or not isinstance(request_log_path, Path):
        raise LargeLLMError("large-run artifact paths must be pathlib.Path values")
    report_bytes = _existing_bytes(report_path)
    if report_bytes is None:
        raise LargeLLMError("large-run report does not exist")
    try:
        report = json.loads(report_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LargeLLMError("large-run report is invalid JSON") from error
    if not isinstance(report, dict) or "report_sha256" not in report:
        raise LargeLLMError("large-run report fields are invalid")
    reported_sha = report.pop("report_sha256")
    if not isinstance(reported_sha, str) or _SHA256_RE.fullmatch(reported_sha) is None:
        raise LargeLLMError("large-run report fingerprint is invalid")
    canonical_body = _canonical_json(report)
    if report_bytes != _canonical_json({**report, "report_sha256": reported_sha}):
        raise LargeLLMError("large-run report is not canonical")
    if hashlib.sha256(canonical_body).hexdigest() != reported_sha:
        raise LargeLLMError("large-run report fingerprint does not match body")

    terminal_sha = report.get("request_log_terminal_sha256")
    _validate_digest(terminal_sha, "large-run report terminal fingerprint")
    report_body = {
        key: value for key, value in report.items() if key != "request_log_terminal_sha256"
    }
    header, records, terminal = _parse_request_log(_existing_bytes(request_log_path) or b"")
    if terminal is None:
        raise LargeLLMError("large-run request journal has no terminal checkpoint")
    if terminal["record_sha256"] != terminal_sha:
        raise LargeLLMError("large-run report terminal fingerprint mismatch")
    if terminal["report_body_sha256"] != hashlib.sha256(_canonical_json(report_body)).hexdigest():
        raise LargeLLMError(
            "large-run report budget/metrics/totals disagree with final durable "
            "checkpoint terminal evidence"
        )
    outcome_records = tuple(record for record in records if record.get("record_type") == "outcome")
    attempts = tuple(
        _attempt_from_record(record, line_number=None)
        for record in records
        if record.get("record_type") == "attempt"
    )
    if int(header["schema_version"]) == _SCHEMA_VERSION:
        if report.get("attempt_set_count") != len(attempts):
            raise LargeLLMError("large-run report attempt count disagrees with request journal")
        if report.get("attempt_set_sha256") != _attempt_set_sha256(attempts):
            raise LargeLLMError(
                "large-run report attempt fingerprint disagrees with request journal"
            )
    outcomes = tuple(
        _outcome_from_record(
            record,
            line_number=None,
            schema_version=int(header["schema_version"]),
        )
        for record in outcome_records
    )
    if not outcomes:
        raise LargeLLMError("large-run request journal has no outcomes")
    budget, terminal_metrics = _terminal_evidence(
        terminal,
        line_number=None,
        schema_version=int(header["schema_version"]),
    )
    if report.get("budget") != terminal["budget_checkpoint"]:
        raise LargeLLMError("large-run report budget disagrees with terminal checkpoint")
    attributed = _money_sum(outcome.authoritative_cost_usd for outcome in outcomes)
    unattributed = _money_difference(budget.spent_usd, attributed)
    if unattributed < Decimal("0"):
        raise LargeLLMError("large-run budget spent is below outcome costs")
    metrics = _metrics(outcomes, unattributed_spend_usd=unattributed)
    if terminal_metrics != metrics:
        raise LargeLLMError("large-run terminal metrics are not derived from terminal budget")
    for key in (
        "run_id",
        "baseline",
        "input_sha256",
        "config_sha256",
        "catalog_sha256",
        "summary_sha256",
        "training_sha256",
        "model_id",
        "provider_slug",
        "model_metadata_sha256",
        "provider_policy_sha256",
        "privacy_sha256",
    ):
        if report.get(key) != header.get(key):
            raise LargeLLMError(f"large-run report {key} disagrees with request journal")
    if (
        "prompt_set_sha256" in header
        and report.get("prompt_set_sha256") != header["prompt_set_sha256"]
    ):
        raise LargeLLMError(
            "large-run report prompt-set fingerprint disagrees with request journal"
        )
    if report.get("metrics") != terminal["metrics"]:
        raise LargeLLMError("large-run report metrics disagree with terminal checkpoint")
    if report.get("budget") != _canonical_value(asdict(budget)):
        raise LargeLLMError("large-run report budget is invalid")
    if (
        report.get("scientific_ready") != terminal["scientific_ready"]
        or report.get("blockers") != terminal["blockers"]
        or report.get("local_implementation_ready") != terminal["local_implementation_ready"]
    ):
        raise LargeLLMError("large-run report readiness disagrees with terminal checkpoint")
    expected_totals = {
        "outcome_count": len(outcomes),
        "authoritative_total_cost_usd": _canonical_value(attributed),
        "attributed_spend_usd": _canonical_value(metrics.attributed_spend_usd),
        "unattributed_spend_usd": _canonical_value(metrics.unattributed_spend_usd),
        "total_spent_usd": _canonical_value(metrics.total_spent_usd),
    }
    if any(report.get(key) != value for key, value in expected_totals.items()):
        raise LargeLLMError("large-run report totals are not derived from terminal checkpoint")
    expected_counts = {
        "completed": metrics.completed,
        "extraction_failed": metrics.extraction_failed,
        "request_failed": metrics.request_failed,
        "budget_blocked": metrics.budget_blocked,
        "cost_unresolved": metrics.cost_unresolved,
    }
    if report.get("outcome_counts") != expected_counts:
        raise LargeLLMError("large-run report outcome counts disagree with terminal checkpoint")
    try:
        return LargeEvaluationRun(
            run_id=header["run_id"],  # type: ignore[arg-type]
            baseline=header["baseline"],  # type: ignore[arg-type]
            outcomes=outcomes,
            metrics=metrics,
            scientific_ready=terminal["scientific_ready"],  # type: ignore[arg-type]
            blockers=tuple(terminal["blockers"]),  # type: ignore[arg-type]
            seed=report["seed"],  # type: ignore[arg-type]
            generated_at_utc=report["generated_at_utc"],  # type: ignore[arg-type]
            input_sha256=header["input_sha256"],  # type: ignore[arg-type]
            config_sha256=header["config_sha256"],  # type: ignore[arg-type]
            budget=budget,
            catalog_sha256=header["catalog_sha256"],  # type: ignore[arg-type]
            summary_sha256=header["summary_sha256"],  # type: ignore[arg-type]
            training_sha256=header["training_sha256"],  # type: ignore[arg-type]
            model_id=header["model_id"],  # type: ignore[arg-type]
            provider_slug=header["provider_slug"],  # type: ignore[arg-type]
            model_metadata_sha256=header["model_metadata_sha256"],  # type: ignore[arg-type]
            provider_policy_sha256=header.get("provider_policy_sha256"),  # type: ignore[arg-type]
            privacy_sha256=header.get("privacy_sha256"),  # type: ignore[arg-type]
            prompt_set_sha256=header.get("prompt_set_sha256"),  # type: ignore[arg-type]
            attempts=attempts,
        )
    except (KeyError, TypeError, LargeLLMError) as error:
        raise LargeLLMError("large-run report is invalid") from error


def summarize_large_runs(runs: Sequence[LargeEvaluationRun]) -> dict[str, object]:
    """Build a three-run local summary without contacting a remote provider.

    Args:
        runs: Exactly three strictly comparable large-evaluation runs.

    Returns:
        Canonical-ready identity, agreement, cost, blocker, and readiness fields.

    Raises:
        LargeLLMError: If the runs are not strictly comparable.
    """
    accepted = tuple(runs)
    reproducibility = compare_large_reproducibility(accepted)
    blockers = {blocker for run in accepted for blocker in run.blockers}
    blockers.discard("non_three_run_evidence")
    # A three-run summary is evidence for only one baseline.  It must not be
    # mistaken for the combined B4/B5 scientific comparison or USD 20 envelope.
    blockers.update({"counterpart_baseline_missing", "combined_budget_unverified"})
    if any(run.budget.stop_reason == "pricing_violation" for run in accepted):
        blockers.add("pricing_violation")
    if any(
        outcome.prediction is not None and outcome.prediction.completion.synthetic_backend
        for run in accepted
        for outcome in run.outcomes
    ):
        blockers.add("synthetic_backend")
    attributed_cost = _money_sum(
        outcome.authoritative_cost_usd for run in accepted for outcome in run.outcomes
    )
    unattributed_cost = _money_sum(run.metrics.unattributed_spend_usd for run in accepted)
    total_cost = _money_sum((attributed_cost, unattributed_cost))
    if total_cost > accepted[0].budget.cap_usd:
        blockers.add("cost_over_cap")
    reference = accepted[0]
    return _canonical_value(
        {
            "baseline": reference.baseline,
            "run_ids": [run.run_id for run in accepted],
            "input_sha256": reference.input_sha256,
            "config_sha256": reference.config_sha256,
            "catalog_sha256": reference.catalog_sha256,
            "summary_sha256": reference.summary_sha256,
            "training_sha256": reference.training_sha256,
            "model_id": reference.model_id,
            "provider_slug": reference.provider_slug,
            "model_metadata_sha256": reference.model_metadata_sha256,
            "provider_policy_sha256": reference.provider_policy_sha256,
            "privacy_sha256": reference.privacy_sha256,
            "reproducibility": asdict(reproducibility),
            "authoritative_total_cost_usd": attributed_cost,
            "attributed_spend_usd": attributed_cost,
            "unattributed_spend_usd": unattributed_cost,
            "total_spent_usd": total_cost,
            "local_implementation_ready": all(run.local_implementation_ready for run in accepted),
            "scientific_ready": False,
            "blockers": sorted(blockers),
        }
    )  # type: ignore[return-value]


__all__ = [
    "ArtifactPaths",
    "RequestJournal",
    "ResumeState",
    "load_large_run_artifacts",
    "load_resume_state",
    "publish_large_run",
    "request_journal_lock",
    "serialize_cost_csv",
    "serialize_predictions",
    "serialize_report",
    "serialize_request_log",
    "summarize_large_runs",
    "validate_artifact_paths",
]
