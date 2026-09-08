"""Atomic, resumable evidence artifacts for B4/B5 evaluation runs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from nl2sparql.models.b12.contracts import SelectedExample, SmallLLMError
from nl2sparql.models.b45.budget import BudgetReservation, BudgetSnapshot
from nl2sparql.models.b45.contracts import (
    _LIVE_COMPLETION_MARKER,
    LargeLLMError,
    LargeLLMPrediction,
    RemoteCompletion,
    _openrouter_completion,
    canonical_money,
)
from nl2sparql.models.b45.evaluate import (
    EvaluationOutcome,
    LargeEvaluationRun,
    compare_large_reproducibility,
)

_SCHEMA_VERSION = 2
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
_EXAMPLE_KEYS = {"record_id", "question", "sql", "score"}
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

    @property
    def completed_outcomes(self) -> tuple[EvaluationOutcome, ...]:
        """Reconstruct validated outcomes for ``evaluate_large_baseline`` resume.

        Returns:
            Immutable outcomes preserving synthetic/live provenance from each row.

        Raises:
            LargeLLMError: If a previously returned record was mutated by the caller.
        """
        return tuple(
            _outcome_from_record(record, line_number=None) for record in self.prior_records
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


def _paths_alias(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except (OSError, RuntimeError) as error:
        raise LargeLLMError(f"unable to compare artifact paths: {error}") from error


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


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is not None:
        _atomic_write(path, previous)
        return
    if path.exists() or path.is_symlink():
        path.unlink()
        _fsync_directory(path.parent.resolve(strict=True))


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


def _validate_digest(value: object, label: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LargeLLMError(f"{label} is invalid")


def _validate_header(header: Mapping[str, object]) -> None:
    if set(header) != _HEADER_KEYS:
        raise LargeLLMError("request journal header fields are invalid")
    if header["schema_version"] != _SCHEMA_VERSION or header["record_type"] != "header":
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
    training = header["training_sha256"]
    if baseline == "b4" and training is not None:
        raise LargeLLMError("B4 request journal must not contain training provenance")
    if baseline == "b5":
        _validate_digest(training, "request journal training fingerprint")
    for key, label in (("model_id", "model ID"), ("provider_slug", "provider")):
        value = header[key]
        if not isinstance(value, str) or not value:
            raise LargeLLMError(f"request journal {label} is invalid")


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
) -> dict[str, object]:
    header: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
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
    }
    _validate_header(header)
    return header


def _outcome_record(
    outcome: EvaluationOutcome,
    *,
    run_id: str,
    model_metadata_sha256: str | None,
) -> dict[str, object]:
    if not isinstance(outcome, EvaluationOutcome):
        raise LargeLLMError("request journal requires an EvaluationOutcome")
    record = {
        "record_type": "outcome",
        "run_id": run_id,
        "model_metadata_sha256": model_metadata_sha256,
        **_canonical_value(asdict(outcome)),
    }
    if record["model_metadata_sha256"] != model_metadata_sha256:
        raise LargeLLMError("request journal model metadata fingerprint mismatch")
    return record


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
        accepted = _require_mapping(item, "journal selected example", _EXAMPLE_KEYS)
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
    record: Mapping[str, object], *, line_number: int | None
) -> EvaluationOutcome:
    prefix = f"request journal line {line_number}" if line_number is not None else "resume record"
    try:
        raw = _require_mapping(record, prefix, _OUTCOME_KEYS)
        if raw["record_type"] != "outcome":
            raise LargeLLMError("journal outcome record type is invalid")
        values = {key: item for key, item in raw.items() if key not in {"record_type", "run_id"}}
        categories = values["categories"]
        if not isinstance(categories, list):
            raise LargeLLMError("journal outcome categories are invalid")
        values["categories"] = tuple(categories)
        values["prediction"] = _prediction_from_record(values["prediction"])
        values["authoritative_cost_usd"] = _money_from_json(
            values["authoritative_cost_usd"], "journal authoritative cost"
        )
        values["budget_checkpoint"] = _budget_from_record(values["budget_checkpoint"])
        return EvaluationOutcome(**values)  # type: ignore[arg-type]
    except (LargeLLMError, TypeError, KeyError) as error:
        raise LargeLLMError(f"{prefix} is invalid: {error}") from error


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


def _parse_request_log(payload: bytes) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    if not payload:
        raise LargeLLMError("request journal must not be empty")
    lines = payload.splitlines(keepends=True)
    header = _decode_json_line(lines[0], 1)
    _validate_header(header)
    records: list[dict[str, object]] = []
    identifiers: set[str] = set()
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
    )
    for line_number, raw_line in enumerate(lines[1:], start=2):
        record = _decode_json_line(raw_line, line_number)
        outcome = _outcome_from_record(record, line_number=line_number)
        for key in identity_keys:
            actual = record[key] if key in record else getattr(outcome, key)
            if actual != header[key]:
                label = key.replace("_sha256", " fingerprint").replace("_", " ")
                raise LargeLLMError(f"request journal {label} mismatch")
        if outcome.case_id in identifiers:
            raise LargeLLMError(f"request journal contains duplicate case ID: {outcome.case_id}")
        identifiers.add(outcome.case_id)
        records.append(record)
    return header, tuple(records)


class RequestJournal:
    """Atomic per-case JSONL journal with a fixed validated run identity."""

    def __init__(
        self,
        path: Path,
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
        model_metadata_sha256: str | None = None,
    ) -> None:
        """Create or validate the durable journal header.

        Args:
            path: Journal JSONL path.
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
        )
        existing = _existing_bytes(path)
        if existing is None:
            try:
                _atomic_write(path, _canonical_json(header))
            except Exception as error:
                raise LargeLLMError(f"unable to initialize request journal: {error}") from error
        else:
            accepted, _records = _parse_request_log(existing)
            for key, expected in header.items():
                if accepted[key] != expected:
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal {label} mismatch")
        self._path = path
        self._header = header

    def append(self, outcome: EvaluationOutcome) -> None:
        """Durably append one validated outcome using atomic replacement.

        Args:
            outcome: Immutable completed case evidence matching the fixed header.

        Raises:
            LargeLLMError: If evidence mismatches, duplicates a case, or cannot be saved.
        """
        record = _outcome_record(
            outcome,
            run_id=str(self._header["run_id"]),
            model_metadata_sha256=self._header["model_metadata_sha256"],  # type: ignore[arg-type]
        )
        try:
            existing = _existing_bytes(self._path)
            if existing is None:
                raise LargeLLMError("request journal disappeared before append")
            header, records = _parse_request_log(existing)
            if header != self._header:
                raise LargeLLMError("request journal header changed before append")
            _outcome_from_record(record, line_number=None)
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
            ):
                if record[key] != header[key]:
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal {label} mismatch")
            if any(record["case_id"] == prior["case_id"] for prior in records):
                raise LargeLLMError(
                    f"request journal contains duplicate case ID: {record['case_id']}"
                )
            _atomic_write(self._path, existing + _canonical_json(record))
        except LargeLLMError:
            raise
        except Exception as error:
            raise LargeLLMError(f"unable to append request journal: {error}") from error


def load_resume_state(
    request_log: Path,
    *,
    expected_input_sha256: str,
    expected_config_sha256: str,
    expected_run_id: str,
    expected_model_metadata_sha256: str | None,
) -> ResumeState:
    """Load a journal only after every row and requested identity validates.

    Args:
        request_log: Existing journal JSONL path.
        expected_input_sha256: Exact current input snapshot fingerprint.
        expected_config_sha256: Exact current generation-config fingerprint.
        expected_run_id: Exact current run identifier.
        expected_model_metadata_sha256: Exact accepted endpoint-metadata fingerprint.

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
    if not isinstance(expected_run_id, str) or _RUN_ID_RE.fullmatch(expected_run_id) is None:
        raise LargeLLMError("expected run ID is invalid")
    payload = _existing_bytes(request_log)
    if payload is None:
        raise LargeLLMError("request journal does not exist")
    header, records = _parse_request_log(payload)
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
    if not records:
        raise LargeLLMError("request journal has no resumable records")
    cost = Decimal("0")
    budget_checkpoint: BudgetSnapshot | None = None
    for record in records:
        outcome = _outcome_from_record(record, line_number=None)
        budget_checkpoint = outcome.budget_checkpoint
        assert outcome.authoritative_cost_usd is not None
        cost += outcome.authoritative_cost_usd
    assert budget_checkpoint is not None
    unattributed_spend = budget_checkpoint.spent_usd - cost
    if unattributed_spend < Decimal("0"):
        raise LargeLLMError("request journal budget spent is below accepted outcome costs")
    return ResumeState(
        completed_case_ids=tuple(str(record["case_id"]) for record in records),
        prior_cost_usd=cost,
        unattributed_spend_usd=unattributed_spend,
        prior_records=records,
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
    )


def serialize_predictions(run: LargeEvaluationRun) -> bytes:
    """Return deterministic ordered prediction/outcome JSONL for one run."""
    rows = (
        {
            "run_id": run.run_id,
            "seed": run.seed,
            "generated_at_utc": run.generated_at_utc,
            "model_metadata_sha256": run.model_metadata_sha256,
            **_canonical_value(asdict(outcome)),
        }
        for outcome in run.outcomes
    )
    return b"".join(_canonical_json(row) for row in rows)


def serialize_request_log(run: LargeEvaluationRun) -> bytes:
    """Return a deterministic resumable journal containing no prompt or credentials."""
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
    )
    return _canonical_json(header) + b"".join(
        _canonical_json(
            _outcome_record(
                outcome,
                run_id=run.run_id,
                model_metadata_sha256=run.model_metadata_sha256,
            )
        )
        for outcome in run.outcomes
    )


def serialize_cost_csv(run: LargeEvaluationRun) -> bytes:
    """Return deterministic cost rows derived solely from immutable outcomes."""
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
        total += charged
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
            "scientific_ready": run.scientific_ready,
            "blockers": run.blockers,
            "outcome_count": len(run.outcomes),
            "outcome_counts": counts,
            "authoritative_total_cost_usd": sum(
                (outcome.authoritative_cost_usd for outcome in run.outcomes),
                start=Decimal("0"),
            ),
            "attributed_spend_usd": run.metrics.attributed_spend_usd,
            "unattributed_spend_usd": run.metrics.unattributed_spend_usd,
            "total_spent_usd": run.metrics.total_spent_usd,
            "metrics": asdict(run.metrics),
            "budget": asdict(run.budget),
        }
    )  # type: ignore[return-value]


def serialize_report(run: LargeEvaluationRun) -> bytes:
    """Return deterministic report JSON with a SHA-256 over its canonical body."""
    body = _report_body(run)
    return _canonical_json(
        {**body, "report_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
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
) -> None:
    """Publish all artifacts atomically in order and the report last.

    Args:
        run: Validated immutable evaluation run.
        paths: Four output destinations.
        protected_paths: Input/evidence paths that must never be overwritten.

    Raises:
        LargeLLMError: If paths/evidence are invalid or any write/rollback fails.
    """
    if not isinstance(run, LargeEvaluationRun):
        raise LargeLLMError("publication requires a LargeEvaluationRun")
    _validate_publication_run(run)
    validate_artifact_paths(paths, protected_paths=protected_paths)
    previous = {path: _existing_bytes(path) for path in paths.all_outputs}
    payloads = (
        serialize_predictions(run),
        serialize_request_log(run),
        serialize_cost_csv(run),
        serialize_report(run),
    )
    try:
        for path, payload in zip(paths.all_outputs, payloads, strict=True):
            _atomic_write(path, payload)
    except Exception as error:
        rollback_errors: list[str] = []
        for path in paths.all_outputs:
            try:
                _restore(path, previous[path])
            except Exception as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
        suffix = f"; rollback failed: {rollback_errors}" if rollback_errors else ""
        raise LargeLLMError(f"unable to publish large-run artifacts: {error}{suffix}") from error


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
    if any(run.budget.stop_reason == "pricing_violation" for run in accepted):
        blockers.add("pricing_violation")
    if any(
        outcome.prediction is not None and outcome.prediction.completion.synthetic_backend
        for run in accepted
        for outcome in run.outcomes
    ):
        blockers.add("synthetic_backend")
    attributed_cost = sum(
        (outcome.authoritative_cost_usd for run in accepted for outcome in run.outcomes),
        start=Decimal("0"),
    )
    unattributed_cost = sum(
        (run.metrics.unattributed_spend_usd for run in accepted), start=Decimal("0")
    )
    total_cost = attributed_cost + unattributed_cost
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
            "reproducibility": asdict(reproducibility),
            "authoritative_total_cost_usd": attributed_cost,
            "attributed_spend_usd": attributed_cost,
            "unattributed_spend_usd": unattributed_cost,
            "total_spent_usd": total_cost,
            "scientific_ready": not blockers,
            "blockers": sorted(blockers),
        }
    )  # type: ignore[return-value]


__all__ = [
    "ArtifactPaths",
    "RequestJournal",
    "ResumeState",
    "load_resume_state",
    "publish_large_run",
    "serialize_cost_csv",
    "serialize_predictions",
    "serialize_report",
    "serialize_request_log",
    "summarize_large_runs",
    "validate_artifact_paths",
]
