"""Manifest evidence and recoverable publication for Stage D."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from pathlib import Path
from typing import Any

from nl2sparql.dataset.noise.contracts import NoiseConfig, NoiseValidationError
from nl2sparql.dataset.noise.pipeline import NoiseStats
from nl2sparql.dataset.noise.transforms import ABBREVIATIONS_PATH
from nl2sparql.dataset.paraphrase.artifacts import deterministic_audit_ids


def jsonl_bytes(records: Sequence[dict[str, Any]]) -> bytes:
    """Serialize records using the repository's canonical sorted-key JSONL form."""
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in records).encode()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stats_payload(stats: NoiseStats) -> dict[str, Any]:
    return {
        "original_count": stats.original_count,
        "noisy_count": stats.noisy_count,
        "output_count": stats.output_count,
        "type_counts": dict(stats.type_counts),
        "unique_raw_questions": stats.unique_raw_questions,
        "unique_normalized_questions": stats.unique_normalized_questions,
        "mean_nonzero_distance": stats.mean_nonzero_distance,
        "max_distance": stats.max_distance,
    }


def build_noise_manifest(
    *,
    source_path: Path,
    output_bytes: bytes,
    abbreviations_path: Path = ABBREVIATIONS_PATH,
    stage_c: Sequence[dict[str, Any]],
    stage_d: Sequence[dict[str, Any]],
    stats: NoiseStats,
    config: NoiseConfig,
    generated_at: str,
) -> dict[str, Any]:
    """Build complete hash, selection, quality, and audit evidence for Stage D."""
    if source_path.read_bytes() != jsonl_bytes(stage_c):
        raise NoiseValidationError("Stage C records do not match source file bytes")
    if output_bytes != jsonl_bytes(stage_d):
        raise NoiseValidationError("Stage D records do not match output bytes")
    noisy_rows = [record for record in stage_d if "noise_type" in record]
    if len(noisy_rows) != 150:
        raise NoiseValidationError("noise manifest requires exactly 150 noisy rows")
    return {
        "schema_version": 1,
        "status": "generated",
        "generated_at": generated_at,
        "source": {
            "records": len(stage_c),
            "sha256": file_sha256(source_path),
        },
        "output": {
            "records": len(stage_d),
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
        },
        "abbreviation_dictionary": {
            "sha256": file_sha256(abbreviations_path),
        },
        "config": {
            "seed": config.seed,
            "quotas": {noise_type.value: count for noise_type, count in config.quotas.items()},
        },
        "quality": _stats_payload(stats),
        "selection": {"source_ids": [str(record["noise_parent_id"]) for record in noisy_rows]},
        "manual_audit": {
            "seed": 42,
            "record_ids": deterministic_audit_ids(noisy_rows, 30, seed=42),
            "completed": False,
            "decipherable_count": None,
            "decisions": [],
        },
    }


def _validate_manual_audit(audit: object, expected_ids: list[str]) -> None:
    if not isinstance(audit, dict):
        raise NoiseValidationError("manual audit must be an object")
    if audit.get("seed") != 42 or audit.get("record_ids") != expected_ids:
        raise NoiseValidationError("manual audit IDs do not match seed-42 selection")
    if audit.get("completed") is False:
        if audit.get("decipherable_count") is not None or audit.get("decisions") != []:
            raise NoiseValidationError("incomplete manual audit cannot contain decisions")
        return
    if audit.get("completed") is not True:
        raise NoiseValidationError("manual audit completed flag must be boolean")
    decisions = audit.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 30:
        raise NoiseValidationError("completed manual audit requires exactly 30 decisions")
    decision_ids: list[str] = []
    decipherable_count = 0
    for decision in decisions:
        if not isinstance(decision, dict):
            raise NoiseValidationError("manual audit decisions must be objects")
        record_id = decision.get("id")
        decipherable = decision.get("decipherable")
        notes = decision.get("notes")
        if not isinstance(record_id, str) or not isinstance(decipherable, bool):
            raise NoiseValidationError("manual audit decision fields are invalid")
        if not isinstance(notes, str):
            raise NoiseValidationError("manual audit notes must be strings")
        decision_ids.append(record_id)
        decipherable_count += int(decipherable)
    if sorted(decision_ids) != sorted(expected_ids) or len(set(decision_ids)) != 30:
        raise NoiseValidationError("manual audit decisions do not match selected IDs")
    if audit.get("decipherable_count") != decipherable_count:
        raise NoiseValidationError("manual audit decipherable count does not match decisions")
    if decipherable_count < 27:
        raise NoiseValidationError("manual audit requires at least 27 decipherable records")


def validate_noise_manifest(
    manifest: dict[str, Any],
    *,
    source_path: Path,
    output_path: Path,
    abbreviations_path: Path = ABBREVIATIONS_PATH,
    stage_c: Sequence[dict[str, Any]],
    stage_d: Sequence[dict[str, Any]],
    stats: NoiseStats,
    config: NoiseConfig,
) -> None:
    """Recompute and validate every machine-verifiable manifest field."""
    generated_at = manifest.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        raise NoiseValidationError("noise manifest requires generated_at")
    output_bytes = output_path.read_bytes()
    expected = build_noise_manifest(
        source_path=source_path,
        output_bytes=output_bytes,
        abbreviations_path=abbreviations_path,
        stage_c=stage_c,
        stage_d=stage_d,
        stats=stats,
        config=config,
        generated_at=generated_at,
    )
    for key in (
        "schema_version",
        "status",
        "generated_at",
        "source",
        "output",
        "abbreviation_dictionary",
        "config",
        "quality",
        "selection",
    ):
        if manifest.get(key) != expected[key]:
            raise NoiseValidationError(f"noise manifest {key} evidence does not match")
    _validate_manual_audit(manifest.get("manual_audit"), expected["manual_audit"]["record_ids"])


@dataclass(frozen=True)
class _TransactionPaths:
    lock: Path
    journal: Path
    output_backup: Path
    manifest_backup: Path


def _transaction_paths(output_path: Path, manifest_path: Path) -> _TransactionPaths:
    output_parent = output_path.parent.resolve()
    manifest_parent = manifest_path.parent.resolve()
    if output_parent != manifest_parent:
        raise NoiseValidationError("output and manifest must share one directory")
    digest = hashlib.sha256(f"{output_path.name}\0{manifest_path.name}".encode()).hexdigest()[:12]
    prefix = f".noise-publish-{digest}"
    return _TransactionPaths(
        lock=output_path.parent / f"{prefix}.lock",
        journal=output_path.parent / f"{prefix}.journal.json",
        output_backup=output_path.parent / f"{prefix}.output.backup",
        manifest_backup=output_path.parent / f"{prefix}.manifest.backup",
    )


def _unique_temp(path: Path, purpose: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.{purpose}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return Path(name)


def _write_bytes_durable(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _backup(path: Path, backup_path: Path) -> bool:
    backup_path.unlink(missing_ok=True)
    if not path.exists():
        return False
    temporary = _unique_temp(backup_path, "backup")
    try:
        shutil.copyfile(path, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, backup_path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _write_journal(
    transaction: _TransactionPaths,
    *,
    output_path: Path,
    manifest_path: Path,
    output_existed: bool,
    manifest_existed: bool,
) -> None:
    payload = {
        "schema_version": 1,
        "output_name": output_path.name,
        "manifest_name": manifest_path.name,
        "output_existed": output_existed,
        "manifest_existed": manifest_existed,
    }
    temporary = _unique_temp(transaction.journal, "journal")
    try:
        _write_bytes_durable(temporary, (json.dumps(payload, sort_keys=True) + "\n").encode())
        os.replace(temporary, transaction.journal)
        _fsync_directory(output_path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _restore_target(path: Path, backup_path: Path, existed: bool) -> None:
    if not existed:
        path.unlink(missing_ok=True)
        return
    if not backup_path.exists():
        raise NoiseValidationError(f"cannot recover missing backup for {path.name}")
    temporary = _unique_temp(path, "restore")
    try:
        _write_bytes_durable(temporary, backup_path.read_bytes())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _recover_unlocked(
    output_path: Path, manifest_path: Path, transaction: _TransactionPaths
) -> None:
    if not transaction.journal.exists():
        return
    try:
        journal = json.loads(transaction.journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoiseValidationError("noise publication journal is corrupt") from exc
    if (
        journal.get("schema_version") != 1
        or journal.get("output_name") != output_path.name
        or journal.get("manifest_name") != manifest_path.name
        or not isinstance(journal.get("output_existed"), bool)
        or not isinstance(journal.get("manifest_existed"), bool)
    ):
        raise NoiseValidationError("noise publication journal does not match targets")
    _restore_target(output_path, transaction.output_backup, journal["output_existed"])
    _restore_target(manifest_path, transaction.manifest_backup, journal["manifest_existed"])
    _fsync_directory(output_path.parent)
    transaction.journal.unlink()
    _fsync_directory(output_path.parent)
    transaction.output_backup.unlink(missing_ok=True)
    transaction.manifest_backup.unlink(missing_ok=True)


@contextmanager
def noise_artifact_lock(
    output_path: Path, manifest_path: Path, *, blocking: bool = True
) -> Iterator[None]:
    """Lock the artifact pair and recover any interrupted prior publication."""
    transaction = _transaction_paths(output_path, manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.lock.touch(exist_ok=True)
    with transaction.lock.open("rb") as handle:
        operation = LOCK_EX if blocking else LOCK_EX | LOCK_NB
        flock(handle.fileno(), operation)
        try:
            _recover_unlocked(output_path, manifest_path, transaction)
            yield
        finally:
            flock(handle.fileno(), LOCK_UN)


def publish_noise_artifacts(
    output_bytes: bytes,
    manifest: dict[str, Any],
    *,
    output_path: Path,
    manifest_path: Path,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    """Publish a recoverable, concurrency-locked output/manifest transaction."""
    resolved_output = output_path.resolve()
    resolved_manifest = manifest_path.resolve()
    same_existing_file = False
    if output_path.exists() and manifest_path.exists():
        try:
            same_existing_file = output_path.samefile(manifest_path)
        except OSError:
            same_existing_file = False
    if resolved_output == resolved_manifest or same_existing_file:
        raise NoiseValidationError("output and manifest paths must differ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    transaction = _transaction_paths(output_path, manifest_path)
    with noise_artifact_lock(output_path, manifest_path):
        output_temp = _unique_temp(output_path, "output")
        manifest_temp = _unique_temp(manifest_path, "manifest")
        try:
            _write_bytes_durable(output_temp, output_bytes)
            _write_bytes_durable(
                manifest_temp,
                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
            )
            output_existed = _backup(output_path, transaction.output_backup)
            manifest_existed = _backup(manifest_path, transaction.manifest_backup)
            _write_journal(
                transaction,
                output_path=output_path,
                manifest_path=manifest_path,
                output_existed=output_existed,
                manifest_existed=manifest_existed,
            )
            try:
                replace(output_temp, output_path)
                replace(manifest_temp, manifest_path)
                _fsync_directory(output_path.parent)
            except Exception:
                _recover_unlocked(output_path, manifest_path, transaction)
                raise
            transaction.journal.unlink()
            _fsync_directory(output_path.parent)
            transaction.output_backup.unlink(missing_ok=True)
            transaction.manifest_backup.unlink(missing_ok=True)
        finally:
            output_temp.unlink(missing_ok=True)
            manifest_temp.unlink(missing_ok=True)
            if not transaction.journal.exists():
                transaction.output_backup.unlink(missing_ok=True)
                transaction.manifest_backup.unlink(missing_ok=True)
