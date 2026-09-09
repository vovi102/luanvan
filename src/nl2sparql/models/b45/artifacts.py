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
from dataclasses import asdict, dataclass, replace
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
    LargeEvaluationMetrics,
    LargeEvaluationRun,
    _metrics,
    compare_large_reproducibility,
    prompt_set_sha256,
)

_SCHEMA_VERSION = 3
_LEGACY_RESUME_SCHEMA_VERSION = 2
_RESUME_SCHEMA_VERSIONS = frozenset({_LEGACY_RESUME_SCHEMA_VERSION, _SCHEMA_VERSION})
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
}
_LEGACY_OUTCOME_KEYS = _OUTCOME_KEYS - {
    "provider_policy_sha256",
    "privacy_sha256",
    "previous_record_sha256",
    "record_sha256",
    "prompt_set_sha256",
}
_LEGACY_V3_OUTCOME_KEYS = _OUTCOME_KEYS - {"prompt_set_sha256"}
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
            v2 is accepted only as an in-progress resume source; new and published
            journals use schema v3.
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
                outcomes.append(outcome)
            return tuple(outcomes)
        if self.schema_version != _SCHEMA_VERSION:
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
        )
        previous_record_sha256 = _header_sha256(header)
        outcomes: list[EvaluationOutcome] = []
        for line_number, record in enumerate(self.prior_records, start=2):
            _validate_record_chain(
                record,
                expected_previous=previous_record_sha256,
                line_number=line_number,
            )
            outcome = _outcome_from_record(record, line_number=None)
            if self.prompt_set_sha256 is not None:
                outcome = replace(outcome, prompt_set_sha256=self.prompt_set_sha256)
            outcomes.append(outcome)
            previous_record_sha256 = str(record["record_sha256"])
        return tuple(outcomes)

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
        "provider_policy_sha256": provider_policy_sha256,
        "privacy_sha256": privacy_sha256,
    }
    if prompt_set_sha256 is not None:
        header["prompt_set_sha256"] = prompt_set_sha256
    _validate_header(header)
    return header


def _outcome_record(
    outcome: EvaluationOutcome,
    *,
    run_id: str,
    model_metadata_sha256: str | None,
    provider_policy_sha256: str | None,
    privacy_sha256: str | None,
    previous_record_sha256: str,
) -> dict[str, object]:
    if not isinstance(outcome, EvaluationOutcome):
        raise LargeLLMError("request journal requires an EvaluationOutcome")
    body = {
        "record_type": "outcome",
        "run_id": run_id,
        "model_metadata_sha256": model_metadata_sha256,
        "provider_policy_sha256": provider_policy_sha256,
        "privacy_sha256": privacy_sha256,
        **_canonical_value(asdict(outcome)),
    }
    if outcome.prompt_set_sha256 is None:
        body.pop("prompt_set_sha256", None)
    if body["model_metadata_sha256"] != model_metadata_sha256:
        raise LargeLLMError("request journal model metadata fingerprint mismatch")
    if body["provider_policy_sha256"] != provider_policy_sha256:
        raise LargeLLMError("request journal provider policy fingerprint mismatch")
    if body["privacy_sha256"] != privacy_sha256:
        raise LargeLLMError("request journal privacy fingerprint mismatch")
    return _chained_record(body, previous_record_sha256=previous_record_sha256)


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
    record: Mapping[str, object],
    *,
    line_number: int | None,
    schema_version: int = _SCHEMA_VERSION,
) -> EvaluationOutcome:
    prefix = f"request journal line {line_number}" if line_number is not None else "resume record"
    try:
        if schema_version == _SCHEMA_VERSION:
            outcome_keys = (
                _OUTCOME_KEYS if "prompt_set_sha256" in record else _LEGACY_V3_OUTCOME_KEYS
            )
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
        return EvaluationOutcome(**values)  # type: ignore[arg-type]
    except (LargeLLMError, TypeError, KeyError) as error:
        raise LargeLLMError(f"{prefix} is invalid: {error}") from error


def _terminal_evidence(
    record: Mapping[str, object], *, line_number: int | None
) -> tuple[BudgetSnapshot, LargeEvaluationMetrics]:
    prefix = f"request journal line {line_number}" if line_number is not None else "terminal record"
    try:
        terminal_keys = (
            _TERMINAL_KEYS
            if "prompt_set_sha256" in record
            else _TERMINAL_KEYS - {"prompt_set_sha256"}
        )
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
    allowed_versions: frozenset[int] = frozenset({_SCHEMA_VERSION}),
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
            _terminal_evidence(record, line_number=line_number)
            _validate_record_chain(
                record,
                expected_previous=previous_record_sha256,
                line_number=line_number,
            )
            if record["run_id"] != header["run_id"]:
                raise LargeLLMError("request journal terminal run ID mismatch")
            if record["outcome_count"] != len(records):
                raise LargeLLMError("request journal terminal outcome count mismatch")
            for key in ("provider_policy_sha256", "privacy_sha256"):
                if record[key] != header.get(key):
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal terminal {label} mismatch")
            if "prompt_set_sha256" in record and record["prompt_set_sha256"] != header.get(
                "prompt_set_sha256"
            ):
                raise LargeLLMError("request journal terminal prompt-set fingerprint mismatch")
            terminal = record
            previous_record_sha256 = str(record["record_sha256"])
            continue
        if record_type != "outcome":
            raise LargeLLMError(f"request journal line {line_number} record type is invalid")
        outcome = _outcome_from_record(
            record,
            line_number=line_number,
            schema_version=schema_version,
        )
        if schema_version == _SCHEMA_VERSION:
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
        records.append(record)
        if schema_version == _SCHEMA_VERSION:
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
        "schema_version": _SCHEMA_VERSION,
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
    _validate_header(upgraded_header)
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
        )
        upgraded_records.append(upgraded)
        previous_record_sha256 = str(upgraded["record_sha256"])
        assert outcome.authoritative_cost_usd is not None
        attributed_spend += outcome.authoritative_cost_usd
        budget_checkpoint = outcome.budget_checkpoint
    if budget_checkpoint is not None and budget_checkpoint.spent_usd < attributed_spend:
        raise LargeLLMError("request journal budget spent is below accepted outcome costs")
    return b"".join(_canonical_json(record) for record in (upgraded_header, *upgraded_records))


class RequestJournal:
    """Atomic v3 per-case journal, upgrading a valid terminal-free v2 resume log."""

    def __init__(
        self,
        path: Path,
        *,
        allow_legacy_resume: bool = False,
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
                _atomic_write(path, _canonical_json(header))
            except Exception as error:
                raise LargeLLMError(f"unable to initialize request journal: {error}") from error
        else:
            allowed_versions = (
                _RESUME_SCHEMA_VERSIONS if allow_legacy_resume else frozenset({_SCHEMA_VERSION})
            )
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
                if key == "prompt_set_sha256" and key not in accepted:
                    continue
                if accepted.get(key) != expected:
                    label = key.replace("_sha256", " fingerprint").replace("_", " ")
                    raise LargeLLMError(f"request journal {label} mismatch")
            if (
                accepted["schema_version"] == _LEGACY_RESUME_SCHEMA_VERSION
                or "prompt_set_sha256" not in accepted
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
            header, records, terminal = _parse_request_log(existing)
            if header != self._header:
                raise LargeLLMError("request journal header changed before append")
            if terminal is not None:
                raise LargeLLMError("request journal terminal checkpoint forbids append")
            previous_record_sha256 = (
                str(records[-1]["record_sha256"]) if records else _header_sha256(header)
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
            )
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
    expected_catalog_sha256: str | object = _UNSET,
    expected_summary_sha256: str | object = _UNSET,
    expected_training_sha256: str | None | object = _UNSET,
    expected_model_id: str | object = _UNSET,
    expected_provider_slug: str | object = _UNSET,
    expected_provider_policy_sha256: str | None | object = _UNSET,
    expected_privacy_sha256: str | None | object = _UNSET,
    expected_baseline: str | object = _UNSET,
    expected_prompt_sha256_by_case: Mapping[str, str] | object = _UNSET,
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
    for record in records:
        outcome = _outcome_from_record(
            record,
            line_number=None,
            schema_version=schema_version,
        )
        budget_checkpoint = outcome.budget_checkpoint
        assert outcome.authoritative_cost_usd is not None
        cost += outcome.authoritative_cost_usd
    if expected_prompt_sha256_by_case is not _UNSET:
        actual_prompt_hashes = {
            str(record["case_id"]): record.get("prompt_sha256") for record in records
        }
        expected_prompt_hashes = dict(expected_prompt_sha256_by_case)
        if any(
            case_id not in expected_prompt_hashes or prompt != expected_prompt_hashes[case_id]
            for case_id, prompt in actual_prompt_hashes.items()
        ):
            raise LargeLLMError("request journal prompt fingerprint mismatch")
        derived_prompt_set = prompt_set_sha256(tuple(expected_prompt_hashes.items()))
        if (
            expected_prompt_set_sha256 is not _UNSET
            and derived_prompt_set != expected_prompt_set_sha256
        ):
            raise LargeLLMError("request journal prompt-set fingerprint mismatch")
        if "prompt_set_sha256" in header and header["prompt_set_sha256"] != derived_prompt_set:
            raise LargeLLMError("request journal prompt-set fingerprint mismatch")
    if terminal is not None:
        budget_checkpoint, terminal_metrics = _terminal_evidence(terminal, line_number=None)
    assert budget_checkpoint is not None
    unattributed_spend = budget_checkpoint.spent_usd - cost
    if unattributed_spend < Decimal("0"):
        raise LargeLLMError("request journal budget spent is below accepted outcome costs")
    if terminal_metrics is not None:
        outcomes = tuple(
            _outcome_from_record(
                record,
                line_number=None,
                schema_version=schema_version,
            )
            for record in records
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
        schema_version=schema_version,
        provider_policy_sha256=provider_policy_sha256,  # type: ignore[arg-type]
        privacy_sha256=privacy_sha256,  # type: ignore[arg-type]
        prompt_set_sha256=(
            header.get("prompt_set_sha256")
            if header.get("prompt_set_sha256") is not None
            else (expected_prompt_set_sha256 if expected_prompt_set_sha256 is not _UNSET else None)
        ),
    )


def serialize_predictions(run: LargeEvaluationRun) -> bytes:
    """Return deterministic ordered prediction/outcome JSONL for one run."""
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
    )
    previous_record_sha256 = _header_sha256(header)
    records: list[dict[str, object]] = []
    for outcome in run.outcomes:
        if outcome.prompt_set_sha256 is None and run.prompt_set_sha256 is not None:
            outcome = replace(outcome, prompt_set_sha256=run.prompt_set_sha256)
        record = _outcome_record(
            outcome,
            run_id=run.run_id,
            model_metadata_sha256=run.model_metadata_sha256,
            provider_policy_sha256=run.provider_policy_sha256,
            privacy_sha256=run.privacy_sha256,
            previous_record_sha256=previous_record_sha256,
        )
        records.append(record)
        previous_record_sha256 = str(record["record_sha256"])
    report_body = _report_body(run)
    terminal = _chained_record(
        {
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
        },
        previous_record_sha256=previous_record_sha256,
    )
    if run.prompt_set_sha256 is not None:
        terminal["prompt_set_sha256"] = run.prompt_set_sha256
        terminal["record_sha256"] = _record_sha256(
            {key: value for key, value in terminal.items() if key != "record_sha256"}
        )
    _terminal_evidence(terminal, line_number=None)
    return header, tuple(records), terminal


def serialize_request_log(run: LargeEvaluationRun) -> bytes:
    """Return a deterministic, hash-chained journal sealed by a terminal checkpoint."""
    header, records, terminal = _request_log_parts(run)
    return b"".join(_canonical_json(record) for record in (header, *records, terminal))


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
            "provider_policy_sha256": run.provider_policy_sha256,
            "privacy_sha256": run.privacy_sha256,
            "prompt_set_sha256": run.prompt_set_sha256,
            "local_implementation_ready": run.local_implementation_ready,
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
    """Return a deterministic report cross-bound to the terminal journal record."""
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
    outcomes = tuple(_outcome_from_record(record, line_number=None) for record in records)
    if not outcomes:
        raise LargeLLMError("large-run request journal has no outcomes")
    budget, terminal_metrics = _terminal_evidence(terminal, line_number=None)
    if report.get("budget") != terminal["budget_checkpoint"]:
        raise LargeLLMError("large-run report budget disagrees with terminal checkpoint")
    attributed = sum((outcome.authoritative_cost_usd for outcome in outcomes), start=Decimal("0"))
    unattributed = budget.spent_usd - attributed
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
    "serialize_cost_csv",
    "serialize_predictions",
    "serialize_report",
    "serialize_request_log",
    "summarize_large_runs",
    "validate_artifact_paths",
]
