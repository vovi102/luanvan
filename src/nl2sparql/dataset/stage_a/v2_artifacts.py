"""Candidate-only artifact serialization for Stage A v2."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nl2sparql.dataset.generate import GENERATION_SEED, PROJECT_ROOT
from nl2sparql.dataset.stage_a.evidence import (
    StageAVerificationReport,
    WitnessDryRun,
    WitnessEvidenceError,
    WitnessExecution,
    WitnessPreflight,
    build_witness_groups,
)
from nl2sparql.dataset.stage_a_v2 import (
    V2_DIFFICULTY_ALLOCATION,
    V2_TEMPLATE_ALLOCATION,
    StageAV2GenerationError,
    canonicalize_stage_a_v2_pools,
    generate_stage_a_v2_records,
    serialize_stage_a_v2_records,
    validate_stage_a_v2_records,
)

RAW_DATA_DIR = PROJECT_ROOT / "data/dataset/raw"
DEFAULT_V2_CANDIDATE_OUTPUT_PATH = RAW_DATA_DIR / "synthetic-stage-a-v2-candidate.jsonl"
DEFAULT_V2_CANDIDATE_CONFIG_PATH = RAW_DATA_DIR / "generation-config-v2-candidate.json"
DEFAULT_V2_CANDIDATE_STATS_PATH = RAW_DATA_DIR / "stats-v2-candidate.md"
DEFAULT_V2_ACCEPTED_OUTPUT_PATH = RAW_DATA_DIR / "synthetic-stage-a-v2.jsonl"
DEFAULT_V2_ACCEPTED_CONFIG_PATH = RAW_DATA_DIR / "generation-config-v2.json"
DEFAULT_V2_ACCEPTED_STATS_PATH = RAW_DATA_DIR / "stats-v2.md"
V1_OUTPUT_PATH = RAW_DATA_DIR / "synthetic-stage-a.jsonl"
V1_CONFIG_PATH = RAW_DATA_DIR / "generation-config.json"
V1_STATS_PATH = RAW_DATA_DIR / "stats.md"

_SHA256_LENGTH = 64
_LIVE_VERIFICATION_FIELDS = frozenset(
    {
        "mode",
        "non_empty",
        "witness_group_id",
        "witness_record_id",
        "witness_row_count",
        "estimated_bytes",
        "processed_bytes",
        "billed_bytes",
        "wall_latency_ms",
        "server_latency_ms",
        "slot_millis",
        "cache_hit",
        "verified_at",
    }
)
_CANDIDATE_MANIFEST_FIELDS = frozenset(
    {
        "version",
        "lifecycle_state",
        "acceptance_eligible",
        "verification_mode",
        "record_count",
        "represented_intent_count",
        "generation_seed",
        "difficulty_allocation",
        "template_allocation",
        "artifact_sha256",
        "template_library_sha256",
        "value_pools_sha256",
        "candidate_value_derivation",
        "supersedes",
    }
)
_ACCEPTED_MANIFEST_FIELDS = frozenset(
    {
        "version",
        "lifecycle_state",
        "acceptance_eligible",
        "verification_mode",
        "verified_at",
        "record_count",
        "verified_record_count",
        "represented_intent_count",
        "generation_seed",
        "difficulty_allocation",
        "template_allocation",
        "artifact_sha256",
        "template_library_sha256",
        "value_pools_sha256",
        "witness_count",
        "total_estimated_bytes",
        "total_processed_bytes",
        "total_billed_bytes",
        "total_wall_latency_ms",
        "cache_hit_count",
        "supersedes",
    }
)


class StageAV2ArtifactError(ValueError):
    """Raised when a Stage A v2 artifact would misrepresent its evidence."""


@dataclass(frozen=True)
class StageAV2CandidateArtifacts:
    output_path: Path
    config_path: Path
    stats_path: Path
    artifact_sha256: str
    manifest: dict[str, Any]


@dataclass(frozen=True)
class _LiveEvidenceSummary:
    witness_count: int
    verified_at: str
    total_processed_bytes: int
    total_billed_bytes: int
    total_wall_latency_ms: float
    cache_hit_count: int


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_templates(templates: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(templates, key=lambda template: str(template["id"]))


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_nonnegative_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _validate_verified_at(value: object) -> str:
    if not isinstance(value, str):
        raise StageAV2ArtifactError("Accepted Stage A v2 verified_at must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StageAV2ArtifactError(
            "Accepted Stage A v2 verified_at must be an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise StageAV2ArtifactError("Accepted Stage A v2 verified_at requires a timezone")
    return value


def _validate_live_records(
    records: Sequence[dict[str, Any]], templates: Sequence[dict[str, Any]]
) -> _LiveEvidenceSummary:
    try:
        validate_stage_a_v2_records(records, templates)
    except StageAV2GenerationError as exc:
        raise StageAV2ArtifactError(str(exc)) from exc
    try:
        groups = build_witness_groups(records)
    except WitnessEvidenceError as exc:
        raise StageAV2ArtifactError(str(exc)) from exc
    records_by_id = {str(record["id"]): record for record in records}
    verified_at_values: set[str] = set()
    processed = 0
    billed = 0
    wall = 0.0
    cache_hits = 0
    for group in groups:
        shared_evidence: dict[str, Any] | None = None
        for record_id in group.member_record_ids:
            verification = records_by_id[record_id].get("verification")
            if not isinstance(verification, dict) or set(verification) != _LIVE_VERIFICATION_FIELDS:
                raise StageAV2ArtifactError(
                    "Accepted Stage A v2 records require complete live verification evidence"
                )
            expected_mode = (
                "live_exact" if record_id == group.witness_record_id else "live_limit_monotonic"
            )
            if verification["mode"] != expected_mode:
                raise StageAV2ArtifactError("Accepted Stage A v2 proof mode is inconsistent")
            if (
                verification["non_empty"] is not True
                or verification["cache_hit"] is not False
                or verification["witness_group_id"] != group.group_id
                or verification["witness_record_id"] != group.witness_record_id
                or not _is_nonnegative_int(verification["estimated_bytes"])
                or not _is_nonnegative_int(verification["processed_bytes"])
                or not _is_nonnegative_int(verification["billed_bytes"])
                or not _is_nonnegative_int(verification["slot_millis"])
                or not _is_nonnegative_number(verification["wall_latency_ms"])
                or not _is_nonnegative_int(verification["witness_row_count"])
                or verification["witness_row_count"] == 0
            ):
                raise StageAV2ArtifactError(
                    "Accepted Stage A v2 live verification values are invalid"
                )
            server_latency = verification["server_latency_ms"]
            if server_latency is not None and not _is_nonnegative_number(server_latency):
                raise StageAV2ArtifactError(
                    "Accepted Stage A v2 server latency evidence is invalid"
                )
            verified_at_values.add(_validate_verified_at(verification["verified_at"]))
            comparable = {key: value for key, value in verification.items() if key != "mode"}
            if shared_evidence is None:
                shared_evidence = comparable
            elif comparable != shared_evidence:
                raise StageAV2ArtifactError(
                    "Accepted Stage A v2 witness members require identical execution evidence"
                )
        assert shared_evidence is not None
        processed += int(shared_evidence["processed_bytes"])
        billed += int(shared_evidence["billed_bytes"])
        wall += float(shared_evidence["wall_latency_ms"])
        cache_hits += int(bool(shared_evidence["cache_hit"]))
    if len(verified_at_values) != 1:
        raise StageAV2ArtifactError("Accepted Stage A v2 requires one live verification timestamp")
    return _LiveEvidenceSummary(
        witness_count=len(groups),
        verified_at=next(iter(verified_at_values)),
        total_processed_bytes=processed,
        total_billed_bytes=billed,
        total_wall_latency_ms=wall,
        cache_hit_count=cache_hits,
    )


def _validate_report(
    report: object,
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _LiveEvidenceSummary]:
    if not isinstance(report, StageAVerificationReport):
        raise StageAV2ArtifactError("Accepted Stage A v2 requires a StageAVerificationReport")
    records = list(report.records)
    summary = _validate_live_records(records, templates)
    expected_candidates = generate_stage_a_v2_records(templates, pools)
    unverified_records = []
    for record in records:
        candidate = dict(record)
        candidate["verification"] = None
        unverified_records.append(candidate)
    if unverified_records != expected_candidates:
        raise StageAV2ArtifactError(
            "Accepted Stage A v2 records do not match their evidence-backed input pools"
        )
    try:
        groups = build_witness_groups(records)
    except WitnessEvidenceError as exc:
        raise StageAV2ArtifactError(str(exc)) from exc
    groups_by_id = {group.group_id: group for group in groups}
    expected_ids = set(groups_by_id)
    if not isinstance(report.preflight, WitnessPreflight) or any(
        not isinstance(item, WitnessDryRun) for item in report.preflight.witnesses
    ):
        raise StageAV2ArtifactError("Accepted Stage A v2 requires complete preflight evidence")
    preflight_by_id = {item.group_id: item for item in report.preflight.witnesses}
    if (
        len(preflight_by_id) != len(report.preflight.witnesses)
        or set(preflight_by_id) != expected_ids
        or report.preflight.total_estimated_bytes
        != sum(item.estimated_bytes for item in report.preflight.witnesses)
    ):
        raise StageAV2ArtifactError("Accepted Stage A v2 requires complete witness evidence")
    if any(
        item.template_id != groups_by_id[item.group_id].template_id
        or item.witness_record_id != groups_by_id[item.group_id].witness_record_id
        or not _is_nonnegative_int(item.estimated_bytes)
        for item in report.preflight.witnesses
    ):
        raise StageAV2ArtifactError("Accepted Stage A v2 preflight evidence is inconsistent")
    if any(not isinstance(item, WitnessExecution) for item in report.witnesses):
        raise StageAV2ArtifactError("Accepted Stage A v2 requires typed witness executions")
    executions_by_id = {item.group_id: item for item in report.witnesses}
    if len(executions_by_id) != len(report.witnesses) or set(executions_by_id) != expected_ids:
        raise StageAV2ArtifactError("Accepted Stage A v2 requires complete witness evidence")
    templates_by_id = {str(template["id"]): template for template in templates}
    for execution in report.witnesses:
        group = groups_by_id[execution.group_id]
        if (
            execution.template_id != group.template_id
            or execution.witness_record_id != group.witness_record_id
            or execution.columns != tuple(templates_by_id[group.template_id]["expected_columns"])
            or not _is_nonnegative_int(execution.row_count)
            or execution.row_count == 0
            or not _is_nonnegative_int(execution.estimated_bytes)
            or not _is_nonnegative_int(execution.processed_bytes)
            or not _is_nonnegative_int(execution.billed_bytes)
            or not _is_nonnegative_int(execution.slot_millis)
            or not _is_nonnegative_number(execution.wall_latency_ms)
            or execution.cache_hit is not False
        ):
            raise StageAV2ArtifactError("Accepted Stage A v2 witness execution is invalid")
        if execution.server_latency_ms is not None and not _is_nonnegative_number(
            execution.server_latency_ms
        ):
            raise StageAV2ArtifactError("Accepted Stage A v2 witness execution is invalid")
    for record in records:
        verification = record["verification"]
        execution = executions_by_id[str(record["witness_group_id"])]
        if (
            any(
                verification[key] != getattr(execution, key)
                for key in (
                    "witness_record_id",
                    "row_count",
                    "estimated_bytes",
                    "processed_bytes",
                    "billed_bytes",
                    "wall_latency_ms",
                    "server_latency_ms",
                    "slot_millis",
                    "cache_hit",
                )
                if key != "row_count"
            )
            or verification["witness_row_count"] != execution.row_count
        ):
            raise StageAV2ArtifactError(
                "Accepted Stage A v2 record evidence does not match witness execution"
            )
    return records, summary


def build_stage_a_v2_candidate_manifest(
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a hash-bound manifest that is categorically ineligible for acceptance."""
    if any(record.get("verification") is not None for record in records):
        raise StageAV2ArtifactError("Stage A v2 candidate records must remain unverified")
    validate_stage_a_v2_records(records, templates)
    payload = serialize_stage_a_v2_records(records)
    return {
        "version": 2,
        "lifecycle_state": "candidate",
        "acceptance_eligible": False,
        "verification_mode": "offline_candidates",
        "record_count": len(records),
        "represented_intent_count": len({record["template_id"] for record in records}),
        "generation_seed": GENERATION_SEED,
        "difficulty_allocation": V2_DIFFICULTY_ALLOCATION,
        "template_allocation": V2_TEMPLATE_ALLOCATION,
        "artifact_sha256": _sha256(payload),
        "template_library_sha256": _sha256(_canonical_json(_canonical_templates(templates))),
        "value_pools_sha256": _sha256(_canonical_json(canonicalize_stage_a_v2_pools(pools))),
        "candidate_value_derivation": {
            "block_number": "deterministic_offset_unverified",
            "transaction_hash": "sha256_syntax_only_unverified",
        },
        "supersedes": {
            "path": str(V1_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
            "artifact_sha256": _sha256(V1_OUTPUT_PATH.read_bytes()),
            "preserved": True,
        },
    }


def has_evidence_backed_live_values(pools: Mapping[str, Any]) -> bool:
    """Return whether data-bound v2 slots have enough unique sourced values."""
    for slot_type in ("block_number", "transaction_hash"):
        entries = pools.get(slot_type)
        if not isinstance(entries, list) or len(entries) < 45:
            return False
        values: list[object] = []
        for entry in entries:
            if (
                not isinstance(entry, Mapping)
                or set(entry) != {"value", "source", "evidence"}
                or not entry["source"]
                or not entry["evidence"]
            ):
                return False
            values.append(entry["value"])
        if len({_canonical_json(value) for value in values}) != len(values):
            return False
    return True


def _v1_supersession() -> dict[str, object]:
    return {
        "path": str(V1_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "artifact_sha256": _sha256(V1_OUTPUT_PATH.read_bytes()),
        "preserved": True,
    }


def _validate_supersession(value: object) -> None:
    if value != _v1_supersession():
        raise StageAV2ArtifactError("Stage A v2 supersession evidence is invalid")


def validate_stage_a_v2_source_evidence(
    stage_a_bytes: bytes,
    manifest: Mapping[str, Any],
    templates: Sequence[dict[str, Any]],
) -> None:
    """Validate candidate or accepted evidence against the bound Stage A rows."""
    try:
        records = [json.loads(line) for line in stage_a_bytes.splitlines() if line]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StageAV2ArtifactError("Stage A v2 artifact is not valid JSONL") from exc
    if any(not isinstance(record, dict) for record in records):
        raise StageAV2ArtifactError("Stage A v2 artifact rows must be JSON objects")
    try:
        validate_stage_a_v2_records(records, templates)
    except StageAV2GenerationError as exc:
        raise StageAV2ArtifactError(str(exc)) from exc
    lifecycle = manifest.get("lifecycle_state")
    expected_fields = (
        _CANDIDATE_MANIFEST_FIELDS if lifecycle == "candidate" else _ACCEPTED_MANIFEST_FIELDS
    )
    if lifecycle not in {"candidate", "accepted"} or set(manifest) != expected_fields:
        raise StageAV2ArtifactError("Stage A v2 manifest schema is invalid for its lifecycle")
    if manifest.get("artifact_sha256") != _sha256(stage_a_bytes):
        raise StageAV2ArtifactError("Stage A v2 source artifact digest does not match")
    if (
        manifest.get("version") != 2
        or manifest.get("record_count") != len(records)
        or manifest.get("represented_intent_count")
        != len({record["template_id"] for record in records})
        or manifest.get("generation_seed") != GENERATION_SEED
        or manifest.get("difficulty_allocation") != V2_DIFFICULTY_ALLOCATION
        or manifest.get("template_allocation") != V2_TEMPLATE_ALLOCATION
        or manifest.get("template_library_sha256")
        != _sha256(_canonical_json(_canonical_templates(templates)))
    ):
        raise StageAV2ArtifactError("Stage A v2 manifest does not match its source records")
    pool_digest = manifest.get("value_pools_sha256")
    if (
        not isinstance(pool_digest, str)
        or len(pool_digest) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in pool_digest)
    ):
        raise StageAV2ArtifactError("Stage A v2 value-pool digest is invalid")
    _validate_supersession(manifest.get("supersedes"))
    if lifecycle == "candidate":
        if (
            manifest.get("acceptance_eligible") is not False
            or manifest.get("verification_mode") != "offline_candidates"
            or manifest.get("candidate_value_derivation")
            != {
                "block_number": "deterministic_offset_unverified",
                "transaction_hash": "sha256_syntax_only_unverified",
            }
            or any(record.get("verification") is not None for record in records)
        ):
            raise StageAV2ArtifactError("Stage A v2 candidate evidence is inconsistent")
        return
    summary = _validate_live_records(records, templates)
    if (
        manifest.get("acceptance_eligible") is not True
        or manifest.get("verification_mode") != "live_witness"
        or manifest.get("verified_record_count") != len(records)
        or manifest.get("verified_at") != summary.verified_at
        or manifest.get("witness_count") != summary.witness_count
        or not _is_nonnegative_int(manifest.get("total_estimated_bytes"))
        or manifest.get("total_processed_bytes") != summary.total_processed_bytes
        or manifest.get("total_billed_bytes") != summary.total_billed_bytes
        or manifest.get("total_wall_latency_ms") != summary.total_wall_latency_ms
        or manifest.get("cache_hit_count") != summary.cache_hit_count
        or summary.cache_hit_count != 0
    ):
        raise StageAV2ArtifactError("Accepted Stage A v2 manifest evidence is inconsistent")


def build_stage_a_v2_accepted_manifest(
    report: StageAVerificationReport,
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an accepted manifest only from complete live witness evidence."""
    if not has_evidence_backed_live_values(pools):
        raise StageAV2ArtifactError(
            "Accepted Stage A v2 requires evidence-backed block and transaction values"
        )
    records, summary = _validate_report(report, templates, pools)
    payload = serialize_stage_a_v2_records(records)
    preflight = report.preflight
    return {
        "version": 2,
        "lifecycle_state": "accepted",
        "acceptance_eligible": True,
        "verification_mode": "live_witness",
        "verified_at": summary.verified_at,
        "record_count": len(records),
        "verified_record_count": len(records),
        "represented_intent_count": len({record["template_id"] for record in records}),
        "generation_seed": GENERATION_SEED,
        "difficulty_allocation": V2_DIFFICULTY_ALLOCATION,
        "template_allocation": V2_TEMPLATE_ALLOCATION,
        "artifact_sha256": _sha256(payload),
        "template_library_sha256": _sha256(_canonical_json(_canonical_templates(templates))),
        "value_pools_sha256": _sha256(_canonical_json(canonicalize_stage_a_v2_pools(pools))),
        "witness_count": summary.witness_count,
        "total_estimated_bytes": preflight.total_estimated_bytes,
        "total_processed_bytes": summary.total_processed_bytes,
        "total_billed_bytes": summary.total_billed_bytes,
        "total_wall_latency_ms": summary.total_wall_latency_ms,
        "cache_hit_count": summary.cache_hit_count,
        "supersedes": _v1_supersession(),
    }


def render_stage_a_v2_candidate_stats(records: Sequence[Mapping[str, Any]]) -> str:
    """Render deterministic human-readable candidate statistics."""
    difficulties = Counter(str(record["difficulty"]) for record in records)
    templates = Counter(str(record["template_id"]) for record in records)
    entities = Counter(entity["value"] for record in records for entity in record["entities_used"])
    lines = [
        "# GoogleSQL Stage A v2 Candidate Stats",
        "",
        f"Records: {len(records)}",
        "Lifecycle state: candidate",
        "Acceptance eligible: false",
        f"Represented intents: {len(templates)}",
        f"Unique SQL: {len({record['sql'] for record in records})}",
        f"Maximum template frequency: {max(templates.values())}",
        f"Maximum entity frequency: {max(entities.values(), default=0)}",
        "",
        "## Difficulty",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(difficulties.items()))
    lines.extend(["", "## Templates", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(templates.items()))
    return "\n".join(lines) + "\n"


def _write_temp(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    return temporary


def _validate_artifact_paths(
    paths: tuple[Path, Path, Path],
    allowed_defaults: tuple[Path, Path, Path],
) -> None:
    resolved = tuple(path.resolve() for path in paths)
    if len(set(resolved)) != len(resolved):
        raise StageAV2ArtifactError("Stage A v2 lifecycle output paths must be distinct")
    protected = {
        path.resolve()
        for path in (
            V1_OUTPUT_PATH,
            V1_CONFIG_PATH,
            V1_STATS_PATH,
            DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
            DEFAULT_V2_CANDIDATE_CONFIG_PATH,
            DEFAULT_V2_CANDIDATE_STATS_PATH,
            DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
            DEFAULT_V2_ACCEPTED_CONFIG_PATH,
            DEFAULT_V2_ACCEPTED_STATS_PATH,
        )
    }
    for path, allowed in zip(resolved, allowed_defaults, strict=True):
        if path in protected and path != allowed.resolve():
            raise StageAV2ArtifactError(
                "Stage A v2 lifecycle output paths cannot overwrite another artifact"
            )


def write_stage_a_v2_candidate_artifacts(
    records: Sequence[dict[str, Any]],
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    *,
    output_path: Path = DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
    config_path: Path = DEFAULT_V2_CANDIDATE_CONFIG_PATH,
    stats_path: Path = DEFAULT_V2_CANDIDATE_STATS_PATH,
) -> StageAV2CandidateArtifacts:
    """Atomically replace the three separate Stage A v2 candidate outputs."""
    _validate_artifact_paths(
        (output_path, config_path, stats_path),
        (
            DEFAULT_V2_CANDIDATE_OUTPUT_PATH,
            DEFAULT_V2_CANDIDATE_CONFIG_PATH,
            DEFAULT_V2_CANDIDATE_STATS_PATH,
        ),
    )
    manifest = build_stage_a_v2_candidate_manifest(records, templates, pools)
    contents = (
        serialize_stage_a_v2_records(records),
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        render_stage_a_v2_candidate_stats(records).encode(),
    )
    temporary_paths: list[Path] = []
    try:
        for path, content in zip((output_path, config_path, stats_path), contents, strict=True):
            temporary_paths.append(_write_temp(path, content))
        for temporary, path in zip(
            temporary_paths, (output_path, config_path, stats_path), strict=True
        ):
            temporary.replace(path)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    return StageAV2CandidateArtifacts(
        output_path=output_path,
        config_path=config_path,
        stats_path=stats_path,
        artifact_sha256=str(manifest["artifact_sha256"]),
        manifest=manifest,
    )


def write_stage_a_v2_accepted_artifacts(
    report: StageAVerificationReport,
    templates: Sequence[dict[str, Any]],
    pools: Mapping[str, Any],
    *,
    output_path: Path = DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
    config_path: Path = DEFAULT_V2_ACCEPTED_CONFIG_PATH,
    stats_path: Path = DEFAULT_V2_ACCEPTED_STATS_PATH,
) -> StageAV2CandidateArtifacts:
    """Atomically publish accepted outputs after all live gates pass."""
    _validate_artifact_paths(
        (output_path, config_path, stats_path),
        (
            DEFAULT_V2_ACCEPTED_OUTPUT_PATH,
            DEFAULT_V2_ACCEPTED_CONFIG_PATH,
            DEFAULT_V2_ACCEPTED_STATS_PATH,
        ),
    )
    manifest = build_stage_a_v2_accepted_manifest(report, templates, pools)
    records = list(report.records)
    accepted_stats = (
        render_stage_a_v2_candidate_stats(records)
        .replace(
            "# GoogleSQL Stage A v2 Candidate Stats\n",
            "# GoogleSQL Stage A v2 Accepted Stats\n",
            1,
        )
        .replace(
            "Lifecycle state: candidate\nAcceptance eligible: false",
            "Lifecycle state: accepted\nAcceptance eligible: true",
        )
    )
    contents = (
        serialize_stage_a_v2_records(records),
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        accepted_stats.encode(),
    )
    temporary_paths: list[Path] = []
    try:
        for path, content in zip((output_path, config_path, stats_path), contents, strict=True):
            temporary_paths.append(_write_temp(path, content))
        for temporary, path in zip(
            temporary_paths, (output_path, config_path, stats_path), strict=True
        ):
            temporary.replace(path)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    return StageAV2CandidateArtifacts(
        output_path=output_path,
        config_path=config_path,
        stats_path=stats_path,
        artifact_sha256=str(manifest["artifact_sha256"]),
        manifest=manifest,
    )
