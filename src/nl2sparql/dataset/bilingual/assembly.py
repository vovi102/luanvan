"""Leakage, split, audit, manifest, and publication gates for bilingual data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from pathlib import Path
from typing import cast

from nl2sparql.dataset.bilingual.contracts import (
    AUDIT_SCHEMA_VERSION,
    EXCLUSION_SCHEMA_VERSION,
    STYLES,
    AuditEvent,
    AuditSummary,
    ExclusionIndex,
    ExpandedTrainingRecord,
    Language,
    SplitConfig,
)
from nl2sparql.dataset.paraphrase.quality import normalize_question

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXCLUSION_FIELDS = frozenset(
    {
        "schema_version",
        "ngram_size",
        "source_sha256s",
        "source_record_counts",
        "normalized_text_sha256s",
        "ngram_sha256s",
        "index_sha256",
    }
)


class AssemblyValidationError(ValueError):
    """Raised when assembly evidence or publication fails closed."""


@dataclass(frozen=True, slots=True)
class HeldOutSource:
    name: str
    source_sha256: str
    questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LeakageReport:
    checked_records: int
    full_text_matches: tuple[str, ...]
    ngram_matches: tuple[str, ...]
    exclusion_index_sha256: str
    passed: bool


@dataclass(frozen=True, slots=True)
class ValidationReport:
    record_count: int
    semantic_family_count: int
    output_sha256: str
    manifest_sha256: str
    passed: bool


@dataclass(frozen=True, slots=True)
class StageASourceEvidence:
    lifecycle_state: str
    acceptance_eligible: bool
    artifact_sha256: str


def validate_stage_a_source(
    stage_a_bytes: bytes,
    manifest_bytes: bytes,
    *,
    require_accepted: bool,
) -> StageASourceEvidence:
    """Bind Stage A bytes to their v2 lifecycle evidence."""
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyValidationError("Stage A source manifest is not valid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != 2:
        raise AssemblyValidationError("Stage A source manifest must use version 2")
    lifecycle_state = manifest.get("lifecycle_state")
    acceptance_eligible = manifest.get("acceptance_eligible")
    verification_mode = manifest.get("verification_mode")
    artifact_sha256 = manifest.get("artifact_sha256")
    if lifecycle_state not in {"candidate", "accepted"}:
        raise AssemblyValidationError("Stage A source lifecycle state is invalid")
    if type(acceptance_eligible) is not bool:  # noqa: E721 - integer is invalid evidence
        raise AssemblyValidationError("Stage A acceptance_eligible must be a boolean")
    if not isinstance(artifact_sha256, str) or not _SHA256_RE.fullmatch(artifact_sha256):
        raise AssemblyValidationError("Stage A source artifact digest is invalid")
    if artifact_sha256 != _sha256(stage_a_bytes):
        raise AssemblyValidationError("Stage A source artifact digest does not match")
    if manifest.get("record_count") != 1000 or manifest.get("represented_intent_count") != 25:
        raise AssemblyValidationError("Stage A v2 source must contain 1000 records and 25 intents")
    if lifecycle_state == "candidate" and (
        acceptance_eligible is not False or verification_mode != "offline_candidates"
    ):
        raise AssemblyValidationError("Stage A candidate lifecycle evidence is inconsistent")
    if lifecycle_state == "accepted" and (
        acceptance_eligible is not True
        or verification_mode != "live_witness"
        or manifest.get("verified_record_count") != 1000
        or manifest.get("cache_hit_count") != 0
    ):
        raise AssemblyValidationError("Accepted Stage A v2 live evidence is incomplete")
    if require_accepted and lifecycle_state != "accepted":
        raise AssemblyValidationError("operation requires accepted Stage A v2 evidence")
    return StageASourceEvidence(
        lifecycle_state=lifecycle_state,
        acceptance_eligible=acceptance_eligible,
        artifact_sha256=artifact_sha256,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ngram_digests(normalized: str, ngram_size: int) -> set[str]:
    tokens = normalized.split()
    return {
        _sha256("\0".join(tokens[index : index + ngram_size]).encode("utf-8"))
        for index in range(len(tokens) - ngram_size + 1)
    }


def _exclusion_body(index: ExclusionIndex) -> dict[str, object]:
    body = asdict(index)
    body.pop("index_sha256", None)
    return body


def build_exclusion_index(
    held_out_documents: tuple[HeldOutSource, ...] | list[HeldOutSource],
    *,
    ngram_size: int = 12,
) -> ExclusionIndex:
    """Derive an irreversible text comparison index from held-out sources."""
    if not held_out_documents:
        raise AssemblyValidationError("at least one held-out source is required")
    if ngram_size < 8:
        raise AssemblyValidationError("high-order ngram size must be at least 8")
    ordered = sorted(held_out_documents, key=lambda source: source.source_sha256)
    normalized_digests: set[str] = set()
    ngram_digests: set[str] = set()
    source_hashes: list[str] = []
    source_counts: list[int] = []
    for source in ordered:
        if not source.name or not _SHA256_RE.fullmatch(source.source_sha256):
            raise AssemblyValidationError("held-out source requires a valid SHA-256")
        if not source.questions:
            raise AssemblyValidationError("held-out source requires records")
        source_hashes.append(source.source_sha256)
        source_counts.append(len(source.questions))
        for question in source.questions:
            if not isinstance(question, str) or not question.strip():
                raise AssemblyValidationError("held-out questions must be non-empty strings")
            normalized = normalize_question(question)
            normalized_digests.add(_sha256(normalized.encode("utf-8")))
            ngram_digests.update(_ngram_digests(normalized, ngram_size))
    provisional = ExclusionIndex(
        schema_version=EXCLUSION_SCHEMA_VERSION,
        ngram_size=ngram_size,
        source_sha256s=tuple(source_hashes),
        source_record_counts=tuple(source_counts),
        normalized_text_sha256s=tuple(sorted(normalized_digests)),
        ngram_sha256s=tuple(sorted(ngram_digests)),
        index_sha256="",
    )
    digest = _sha256(_canonical_json(_exclusion_body(provisional)))
    return ExclusionIndex(**(_exclusion_body(provisional) | {"index_sha256": digest}))


def serialize_exclusion_index(index: ExclusionIndex) -> bytes:
    """Serialize the derived index without any recoverable held-out wording."""
    return _canonical_json(asdict(index)) + b"\n"


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AssemblyValidationError(f"exclusion index {field} must be a string array")
    return tuple(value)


def load_exclusion_index(payload: bytes) -> ExclusionIndex:
    """Load exact derived fields and verify their canonical digest."""
    try:
        document = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyValidationError("exclusion index is not valid JSON") from exc
    if not isinstance(document, dict) or set(document) != _EXCLUSION_FIELDS:
        raise AssemblyValidationError("exclusion index field set is invalid")
    if document.get("schema_version") != EXCLUSION_SCHEMA_VERSION:
        raise AssemblyValidationError("exclusion index schema version is unsupported")
    ngram_size = document.get("ngram_size")
    if not isinstance(ngram_size, int) or isinstance(ngram_size, bool) or ngram_size < 8:
        raise AssemblyValidationError("exclusion index ngram size is invalid")
    counts = document.get("source_record_counts")
    if (
        not isinstance(counts, list)
        or not counts
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count <= 0 for count in counts
        )
    ):
        raise AssemblyValidationError("exclusion index source counts are invalid")
    index = ExclusionIndex(
        schema_version=EXCLUSION_SCHEMA_VERSION,
        ngram_size=ngram_size,
        source_sha256s=_string_tuple(document.get("source_sha256s"), "source_sha256s"),
        source_record_counts=tuple(counts),
        normalized_text_sha256s=_string_tuple(
            document.get("normalized_text_sha256s"), "normalized_text_sha256s"
        ),
        ngram_sha256s=_string_tuple(document.get("ngram_sha256s"), "ngram_sha256s"),
        index_sha256=str(document.get("index_sha256")),
    )
    digest_fields = (
        *index.source_sha256s,
        *index.normalized_text_sha256s,
        *index.ngram_sha256s,
        index.index_sha256,
    )
    if any(not _SHA256_RE.fullmatch(value) for value in digest_fields):
        raise AssemblyValidationError("exclusion index contains an invalid SHA-256")
    if len(index.source_sha256s) != len(index.source_record_counts):
        raise AssemblyValidationError("exclusion index source hash/count lengths differ")
    if not index.normalized_text_sha256s:
        raise AssemblyValidationError("exclusion index contains no normalized records")
    expected_digest = _sha256(_canonical_json(_exclusion_body(index)))
    if index.index_sha256 != expected_digest:
        raise AssemblyValidationError("exclusion index digest does not match")
    return index


def validate_no_leakage(
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    index: ExclusionIndex,
) -> LeakageReport:
    """Reject normalized text or configured high-order n-gram overlap."""
    if not isinstance(index, ExclusionIndex):
        raise TypeError("validate_no_leakage requires a derived ExclusionIndex")
    full_digests = set(index.normalized_text_sha256s)
    ngram_digests = set(index.ngram_sha256s)
    full_matches: list[str] = []
    ngram_matches: list[str] = []
    for record in records:
        normalized = normalize_question(record.question)
        if record.normalized_question != normalized:
            raise AssemblyValidationError(f"{record.id} normalized question is stale")
        if _sha256(normalized.encode("utf-8")) in full_digests:
            full_matches.append(record.id)
        if _ngram_digests(normalized, index.ngram_size) & ngram_digests:
            ngram_matches.append(record.id)
    if full_matches:
        raise AssemblyValidationError(
            f"held-out normalized full-text leakage: {sorted(full_matches)[:10]}"
        )
    if ngram_matches:
        raise AssemblyValidationError(
            f"held-out {index.ngram_size}-token ngram leakage: {sorted(ngram_matches)[:10]}"
        )
    return LeakageReport(
        checked_records=len(records),
        full_text_matches=(),
        ngram_matches=(),
        exclusion_index_sha256=index.index_sha256,
        passed=True,
    )


def _family_split(family_id: str, config: SplitConfig) -> str:
    digest = _sha256(f"{config.seed}:{family_id}".encode())
    bucket = int(digest[:8], 16) % 100
    return "development" if bucket < config.development_percent else "train"


def assign_group_splits(
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    config: SplitConfig,
) -> tuple[ExpandedTrainingRecord, ...]:
    """Assign every member of a semantic family to one deterministic split."""
    if (
        not isinstance(config.seed, int)
        or isinstance(config.seed, bool)
        or config.seed < 0
        or not isinstance(config.development_percent, int)
        or isinstance(config.development_percent, bool)
        or not 1 <= config.development_percent <= 99
    ):
        raise AssemblyValidationError("split config requires a non-negative seed and 1..99 percent")
    result: list[ExpandedTrainingRecord] = []
    for record in sorted(records, key=lambda value: value.id):
        assigned = replace(record, split=_family_split(record.semantic_family_id, config))
        from nl2sparql.dataset.bilingual.rendering import expanded_record_digest

        result.append(replace(assigned, record_sha256=expanded_record_digest(assigned)))
    family_splits: dict[str, set[str]] = defaultdict(set)
    for record in result:
        family_splits[record.semantic_family_id].add(record.split)
    if any(len(splits) != 1 for splits in family_splits.values()):
        raise AssemblyValidationError("semantic family crossed split boundaries")
    return tuple(result)


def _template_id(record: ExpandedTrainingRecord) -> str:
    parts = record.catalog_entry_id.rsplit("__", 2)
    if len(parts) != 3:
        raise AssemblyValidationError(f"invalid catalog entry id: {record.catalog_entry_id}")
    return parts[0]


def select_audit_sample(
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    language: Language,
    *,
    seed: int = 42,
) -> tuple[str, ...]:
    """Select one deterministic row for every intent/style stratum."""
    if language not in ("en", "vi"):
        raise AssemblyValidationError(f"unsupported audit language: {language}")
    eligible = [record for record in records if record.language == language]
    template_ids = sorted({_template_id(record) for record in eligible})
    if len(template_ids) != 25:
        raise AssemblyValidationError(
            f"audit sample requires 25 intents for {language}, received {len(template_ids)}"
        )
    selected: list[str] = []
    for template_id in template_ids:
        for style in STYLES:
            candidates = [
                record
                for record in eligible
                if _template_id(record) == template_id and record.style == style
            ]
            if not candidates:
                raise AssemblyValidationError(
                    f"audit sample requires 25 intents and four styles; missing "
                    f"{template_id}/{language}/{style}"
                )
            chosen = min(
                candidates,
                key=lambda record: _sha256(
                    f"{seed}:{language}:{template_id}:{style}:{record.id}".encode()
                ),
            )
            selected.append(chosen.id)
    if len(selected) != 100 or len(set(selected)) != 100:
        raise AssemblyValidationError("audit sample must contain 100 unique record IDs")
    return tuple(sorted(selected))


def _event_timestamp(event: AuditEvent) -> datetime:
    try:
        parsed = datetime.fromisoformat(event.reviewed_at)
    except ValueError as exc:
        raise AssemblyValidationError("audit reviewed_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise AssemblyValidationError("audit reviewed_at must include a timezone")
    return parsed


def _validate_audit_event_contract(event: AuditEvent) -> None:
    string_fields = {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "record_id": event.record_id,
        "record_sha256": event.record_sha256,
        "decision": event.decision,
        "notes": event.notes,
        "reviewer_type": event.reviewer_type,
        "reviewed_at": event.reviewed_at,
    }
    if any(not isinstance(value, str) for value in string_fields.values()):
        raise AssemblyValidationError("audit string fields must be strings")
    for name in ("event_id", "record_id", "notes", "reviewed_at"):
        if not string_fields[name]:
            raise AssemblyValidationError(f"audit {name} must be non-empty")
    if not _SHA256_RE.fullmatch(event.record_sha256):
        raise AssemblyValidationError("audit record_sha256 must be a valid SHA-256")
    if type(event.faithful) is not bool:  # noqa: E721 - integers are invalid evidence
        raise AssemblyValidationError("audit faithful must be a boolean")
    if type(event.natural) is not bool:  # noqa: E721 - integers are invalid evidence
        raise AssemblyValidationError("audit natural must be a boolean")
    if event.supersedes_event_id is not None and (
        not isinstance(event.supersedes_event_id, str) or not event.supersedes_event_id
    ):
        raise AssemblyValidationError("audit supersedes_event_id must be null or non-empty")


def validate_audit(
    events: list[AuditEvent] | tuple[AuditEvent, ...],
    sample_ids: tuple[str, ...] | list[str],
    *,
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    language: Language,
) -> AuditSummary:
    """Validate an append-only agent audit and enforce score thresholds."""
    if len(sample_ids) != 100 or len(set(sample_ids)) != 100:
        raise AssemblyValidationError("audit requires exactly 100 unique sample IDs")
    record_index = {record.id: record for record in records}
    if any(record_id not in record_index for record_id in sample_ids):
        raise AssemblyValidationError("audit sample references an unknown record")
    if any(record_index[record_id].language != language for record_id in sample_ids):
        raise AssemblyValidationError("audit sample language does not match")
    event_ids: set[str] = set()
    latest: dict[str, AuditEvent] = {}
    previous_timestamp: datetime | None = None
    for event in events:
        _validate_audit_event_contract(event)
        if event.schema_version != AUDIT_SCHEMA_VERSION:
            raise AssemblyValidationError("audit schema version is unsupported")
        if event.event_id in event_ids:
            raise AssemblyValidationError("audit event IDs must be unique")
        event_ids.add(event.event_id)
        if event.record_id not in sample_ids:
            raise AssemblyValidationError("audit event is outside the deterministic sample")
        record = record_index[event.record_id]
        if event.record_sha256 != record.record_sha256:
            raise AssemblyValidationError("audit event record digest does not match")
        if event.reviewer_type != "agent":
            raise AssemblyValidationError("training audit requires reviewer_type=agent")
        if event.decision not in {"accept", "reject"}:
            raise AssemblyValidationError("audit decision must be accept or reject")
        timestamp = _event_timestamp(event)
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise AssemblyValidationError("audit events must be append-only chronological")
        previous_timestamp = timestamp
        prior = latest.get(event.record_id)
        if prior is None:
            if event.supersedes_event_id is not None:
                raise AssemblyValidationError("initial audit event must not supersede another")
        elif event.supersedes_event_id != prior.event_id:
            raise AssemblyValidationError(
                "later audit event supersedes_event_id must name the latest event"
            )
        latest[event.record_id] = event
    if set(latest) != set(sample_ids):
        missing = sorted(set(sample_ids) - set(latest))
        raise AssemblyValidationError(f"audit decisions are incomplete: {missing[:10]}")
    decisions = [latest[record_id] for record_id in sample_ids]
    faithful_count = sum(event.faithful for event in decisions)
    natural_count = sum(event.natural for event in decisions)
    accepted_count = sum(event.decision == "accept" for event in decisions)
    if faithful_count < 95:
        raise AssemblyValidationError(
            f"audit requires at least 95 faithful records, received {faithful_count}"
        )
    if natural_count < 90:
        raise AssemblyValidationError(
            f"audit requires at least 90 natural records, received {natural_count}"
        )
    return AuditSummary(
        language=cast(Language, language),
        sample_size=100,
        faithful_count=faithful_count,
        natural_count=natural_count,
        accepted_count=accepted_count,
        passed=True,
    )


def validate_audit_evidence(
    events: list[AuditEvent] | tuple[AuditEvent, ...],
    *,
    records: tuple[ExpandedTrainingRecord, ...] | list[ExpandedTrainingRecord],
    seed: int = 42,
) -> tuple[AuditSummary, ...]:
    """Validate the complete two-language event log without ignoring extra rows."""
    event_ids: set[str] = set()
    previous_timestamp: datetime | None = None
    for event in events:
        _validate_audit_event_contract(event)
        if event.event_id in event_ids:
            raise AssemblyValidationError("audit event IDs must be globally unique")
        event_ids.add(event.event_id)
        timestamp = _event_timestamp(event)
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise AssemblyValidationError("audit events must be globally chronological")
        previous_timestamp = timestamp
    samples = {
        language: select_audit_sample(records, cast(Language, language), seed=seed)
        for language in ("en", "vi")
    }
    allowed_ids = set(samples["en"]) | set(samples["vi"])
    if any(event.record_id not in allowed_ids for event in events):
        raise AssemblyValidationError("audit event is outside the deterministic samples")
    summaries: list[AuditSummary] = []
    for language in ("en", "vi"):
        sample_ids = samples[language]
        sample_set = set(sample_ids)
        language_events = tuple(event for event in events if event.record_id in sample_set)
        summaries.append(
            validate_audit(
                language_events,
                sample_ids,
                records=records,
                language=cast(Language, language),
            )
        )
    return tuple(summaries)


def serialize_audit_events(events: list[AuditEvent] | tuple[AuditEvent, ...]) -> bytes:
    """Preserve append order while serializing canonical audit event lines."""
    return b"".join(_canonical_json(asdict(event)) + b"\n" for event in events)


def _count_records(records: tuple[ExpandedTrainingRecord, ...]) -> dict[str, object]:
    return {
        "split": dict(sorted(Counter(record.split for record in records).items())),
        "language": dict(sorted(Counter(record.language for record in records).items())),
        "style": dict(sorted(Counter(record.style for record in records).items())),
        "intent": dict(sorted(Counter(_template_id(record) for record in records).items())),
        "semantic_families": len({record.semantic_family_id for record in records}),
    }


def _manifest_body(manifest: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in manifest.items() if key != "manifest_body_sha256"}


def build_manifest(
    records: tuple[ExpandedTrainingRecord, ...],
    *,
    output_bytes: bytes,
    stage_a_bytes: bytes,
    stage_a_manifest_bytes: bytes,
    catalog_bytes: bytes,
    split_config: SplitConfig,
    diversity: object,
    leakage: LeakageReport,
    audit_summaries: tuple[AuditSummary, ...],
    audit_bytes: bytes,
    exclusion_index: ExclusionIndex,
) -> dict[str, object]:
    """Build a deterministic manifest with honest zero-call provenance."""
    validate_stage_a_source(stage_a_bytes, stage_a_manifest_bytes, require_accepted=True)
    if len(records) != 8000:
        raise AssemblyValidationError("manifest requires exactly 8000 clean records")
    if {summary.language for summary in audit_summaries} != {"en", "vi"}:
        raise AssemblyValidationError("manifest requires English and Vietnamese audit summaries")
    if not leakage.passed or leakage.exclusion_index_sha256 != exclusion_index.index_sha256:
        raise AssemblyValidationError("manifest requires passing bound leakage evidence")
    if any(record.split == "unassigned" for record in records):
        raise AssemblyValidationError("manifest rejects unassigned split records")
    body: dict[str, object] = {
        "schema_version": 1,
        "status": "completed",
        "producer": {
            "producer_type": "deterministic_template_renderer",
            "author_type": "agent",
            "review_type": "agent-reviewed",
            "generation_model": None,
            "provider": None,
            "api_request_count": 0,
            "recorded_cost_usd": 0.0,
            "cost_note": (
                "Recorded cost is operational evidence, not a provider billing statement."
            ),
        },
        "versions": {
            "renderer": "deterministic-bilingual-renderer-v1",
            "validator": "deterministic-bilingual-validator-v1",
        },
        "sources": {
            "stage_a_sha256": _sha256(stage_a_bytes),
            "stage_a_manifest_sha256": _sha256(stage_a_manifest_bytes),
            "catalog_sha256": _sha256(catalog_bytes),
            "split_config_sha256": _sha256(_canonical_json(asdict(split_config))),
            "exclusion_index_sha256": exclusion_index.index_sha256,
            "exclusion_source_sha256s": list(exclusion_index.source_sha256s),
            "audit_sha256": _sha256(audit_bytes),
        },
        "output": {"records": len(records), "sha256": _sha256(output_bytes)},
        "counts": _count_records(records),
        "quality": {
            "diversity": asdict(diversity),
            "leakage": asdict(leakage),
            "audits": [
                asdict(summary)
                for summary in sorted(audit_summaries, key=lambda value: value.language)
            ],
        },
        "limitations": [
            "Training and paired benchmark templates share agent authorship.",
            "No independent human authorship or review is claimed for this training corpus.",
        ],
    }
    return body | {"manifest_body_sha256": _sha256(_canonical_json(body))}


def serialize_manifest(manifest: dict[str, object]) -> bytes:
    return _canonical_json(manifest) + b"\n"


def _load_json_lines(payload: bytes, owner: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    try:
        text = payload.decode("utf-8")
        lines = text.splitlines()
        if not lines:
            raise AssemblyValidationError(f"{owner} is empty")
        for line in lines:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AssemblyValidationError(f"{owner} rows must be JSON objects")
            result.append(value)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyValidationError(f"{owner} is not valid canonical JSONL") from exc
    return result


def _tuple_pairs(value: object, owner: str):
    if not isinstance(value, list):
        raise AssemblyValidationError(f"{owner} must be an array")
    result = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str):
            raise AssemblyValidationError(f"{owner} contains an invalid pair")
        result.append((pair[0], pair[1]))
    return tuple(result)


def _expanded_record(document: dict[str, object]) -> ExpandedTrainingRecord:
    expected = {field.name for field in fields(ExpandedTrainingRecord)}
    if set(document) != expected:
        raise AssemblyValidationError("expanded record field set is invalid")
    values = dict(document)
    for name in ("slot_values", "semantic_anchors"):
        values[name] = _tuple_pairs(values[name], name)
    entities = values["entities_used"]
    if not isinstance(entities, list):
        raise AssemblyValidationError("entities_used must be an array")
    values["entities_used"] = tuple(
        _tuple_pairs(entity, "entity annotation") for entity in entities
    )
    for name in ("expected_columns", "schema_elements"):
        value = values[name]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise AssemblyValidationError(f"{name} must be a string array")
        values[name] = tuple(value)
    try:
        return ExpandedTrainingRecord(**values)
    except TypeError as exc:
        raise AssemblyValidationError("expanded record types are invalid") from exc


def _audit_event(document: dict[str, object]) -> AuditEvent:
    expected = {field.name for field in fields(AuditEvent)}
    if set(document) != expected:
        raise AssemblyValidationError("audit event field set is invalid")
    try:
        return AuditEvent(**document)
    except TypeError as exc:
        raise AssemblyValidationError("audit event types are invalid") from exc


def _load_manifest(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyValidationError("manifest is not valid JSON") from exc
    expected = {
        "schema_version",
        "status",
        "producer",
        "versions",
        "sources",
        "output",
        "counts",
        "quality",
        "limitations",
        "manifest_body_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise AssemblyValidationError("manifest field set is invalid")
    if value.get("manifest_body_sha256") != _sha256(_canonical_json(_manifest_body(value))):
        raise AssemblyValidationError("manifest body digest does not match")
    return cast(dict[str, object], value)


def validate_artifacts(
    *,
    output_bytes: bytes,
    manifest_bytes: bytes,
    audit_bytes: bytes,
    exclusion_index_bytes: bytes,
    stage_a_bytes: bytes,
    stage_a_manifest_bytes: bytes,
    catalog_bytes: bytes,
    split_config: SplitConfig,
    expected_records: tuple[ExpandedTrainingRecord, ...],
) -> ValidationReport:
    """Recompute source equality, hashes, quality, split, leakage, and audit gates."""
    validate_stage_a_source(stage_a_bytes, stage_a_manifest_bytes, require_accepted=True)
    manifest = _load_manifest(manifest_bytes)
    exclusion = load_exclusion_index(exclusion_index_bytes)
    rows = _load_json_lines(output_bytes, "training artifact")
    records = tuple(_expanded_record(row) for row in rows)
    if len(records) != 8000:
        raise AssemblyValidationError("training artifact requires 8000 records")
    if records != expected_records:
        raise AssemblyValidationError(
            "training artifact does not match reconstructed source records"
        )
    from nl2sparql.dataset.bilingual.rendering import expanded_record_digest

    for record in records:
        if (
            record.producer_type != "deterministic_template_renderer"
            or record.author_type != "agent"
            or record.review_type != "agent-reviewed"
            or record.generation_model is not None
            or record.provider is not None
            or type(record.api_request_count) is not int
            or record.api_request_count != 0
            or type(record.recorded_cost_usd) is not float
            or record.recorded_cost_usd != 0.0
        ):
            raise AssemblyValidationError(f"record provenance is invalid: {record.id}")
        if record.record_sha256 != expanded_record_digest(record):
            raise AssemblyValidationError(f"record digest mismatch: {record.id}")
        if record.split != _family_split(record.semantic_family_id, split_config):
            raise AssemblyValidationError(f"record split mismatch: {record.id}")
    sources = cast(dict[str, object], manifest["sources"])
    expected_sources = {
        "stage_a_sha256": _sha256(stage_a_bytes),
        "stage_a_manifest_sha256": _sha256(stage_a_manifest_bytes),
        "catalog_sha256": _sha256(catalog_bytes),
        "split_config_sha256": _sha256(_canonical_json(asdict(split_config))),
        "exclusion_index_sha256": exclusion.index_sha256,
        "exclusion_source_sha256s": list(exclusion.source_sha256s),
        "audit_sha256": _sha256(audit_bytes),
    }
    if sources != expected_sources:
        raise AssemblyValidationError("manifest source hashes do not match")
    output = cast(dict[str, object], manifest["output"])
    if output != {"records": 8000, "sha256": _sha256(output_bytes)}:
        raise AssemblyValidationError("manifest output evidence does not match")
    if manifest["counts"] != _count_records(records):
        raise AssemblyValidationError("manifest counts do not match")
    expected_producer = {
        "producer_type": "deterministic_template_renderer",
        "author_type": "agent",
        "review_type": "agent-reviewed",
        "generation_model": None,
        "provider": None,
        "api_request_count": 0,
        "recorded_cost_usd": 0.0,
        "cost_note": "Recorded cost is operational evidence, not a provider billing statement.",
    }
    if manifest["producer"] != expected_producer:
        raise AssemblyValidationError("manifest producer provenance is invalid")
    leakage = validate_no_leakage(records, exclusion)
    quality = cast(dict[str, object], manifest["quality"])
    if _canonical_json(quality.get("leakage")) != _canonical_json(asdict(leakage)):
        raise AssemblyValidationError("manifest leakage evidence does not match")
    from nl2sparql.dataset.bilingual.rendering import diversity_report

    diversity = diversity_report(records)
    if _canonical_json(quality.get("diversity")) != _canonical_json(asdict(diversity)):
        raise AssemblyValidationError("manifest diversity evidence does not match")
    audit_documents = _load_json_lines(audit_bytes, "audit evidence")
    events = tuple(_audit_event(document) for document in audit_documents)
    summaries = validate_audit_evidence(events, records=records, seed=42)
    expected_audits = [asdict(summary) for summary in summaries]
    if quality.get("audits") != expected_audits:
        raise AssemblyValidationError("manifest audit summaries do not match")
    return ValidationReport(
        record_count=len(records),
        semantic_family_count=len({record.semantic_family_id for record in records}),
        output_sha256=_sha256(output_bytes),
        manifest_sha256=_sha256(manifest_bytes),
        passed=True,
    )


@dataclass(frozen=True, slots=True)
class _Transaction:
    lock: Path
    journal: Path
    backups: tuple[Path, Path, Path]


def _transaction(paths: tuple[Path, Path, Path]) -> _Transaction:
    parents = {path.parent.resolve() for path in paths}
    if len(parents) != 1:
        raise AssemblyValidationError("artifact paths must share one directory")
    digest = _sha256("\0".join(path.name for path in paths).encode())[:12]
    parent = paths[0].parent
    prefix = f".bilingual-publish-{digest}"
    return _Transaction(
        lock=parent / f"{prefix}.lock",
        journal=parent / f"{prefix}.journal.json",
        backups=tuple(parent / f"{prefix}.{index}.backup" for index in range(3)),
    )


def _unique_temp(path: Path, purpose: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.{purpose}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return Path(name)


def _write_durable(path: Path, payload: bytes) -> None:
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


def _backup(path: Path, backup: Path) -> bool:
    backup.unlink(missing_ok=True)
    if not path.exists():
        return False
    temporary = _unique_temp(backup, "backup")
    try:
        shutil.copyfile(path, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, backup)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _restore(path: Path, backup: Path, existed: bool) -> None:
    if not existed:
        path.unlink(missing_ok=True)
        return
    if not backup.exists():
        raise AssemblyValidationError(f"cannot recover missing backup for {path.name}")
    temporary = _unique_temp(path, "restore")
    try:
        _write_durable(temporary, backup.read_bytes())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _recover(paths: tuple[Path, Path, Path], transaction: _Transaction) -> None:
    if not transaction.journal.exists():
        return
    try:
        journal = json.loads(transaction.journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssemblyValidationError("publication journal is corrupt") from exc
    if (
        not isinstance(journal, dict)
        or journal.get("schema_version") != 1
        or journal.get("names") != [path.name for path in paths]
        or not isinstance(journal.get("existed"), list)
        or len(journal["existed"]) != 3
        or any(not isinstance(value, bool) for value in journal["existed"])
    ):
        raise AssemblyValidationError("publication journal does not match targets")
    for path, backup, existed in zip(paths, transaction.backups, journal["existed"], strict=True):
        _restore(path, backup, existed)
    _fsync_directory(paths[0].parent)
    transaction.journal.unlink()
    for backup in transaction.backups:
        backup.unlink(missing_ok=True)


@contextmanager
def artifact_lock(
    output_path: Path,
    manifest_path: Path,
    audit_path: Path,
    *,
    blocking: bool = True,
) -> Iterator[None]:
    paths = (output_path, manifest_path, audit_path)
    transaction = _transaction(paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.lock.touch(exist_ok=True)
    with transaction.lock.open("rb") as handle:
        operation = LOCK_EX if blocking else LOCK_EX | LOCK_NB
        flock(handle.fileno(), operation)
        try:
            _recover(paths, transaction)
            yield
        finally:
            flock(handle.fileno(), LOCK_UN)


def publish_artifacts(
    output_bytes: bytes,
    manifest_bytes: bytes,
    audit_bytes: bytes,
    *,
    output_path: Path,
    manifest_path: Path,
    audit_path: Path,
    replace_file: Callable[[Path, Path], None] = os.replace,
) -> None:
    """Publish output, manifest, and audit as one recoverable transaction."""
    paths = (output_path, manifest_path, audit_path)
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != 3:
        raise AssemblyValidationError("artifact paths must differ")
    for left_index, left in enumerate(paths):
        for right in paths[left_index + 1 :]:
            if left.exists() and right.exists() and left.samefile(right):
                raise AssemblyValidationError("artifact paths must differ")
    transaction = _transaction(paths)
    with artifact_lock(*paths):
        temporaries = tuple(_unique_temp(path, "publish") for path in paths)
        try:
            for temporary, payload in zip(
                temporaries, (output_bytes, manifest_bytes, audit_bytes), strict=True
            ):
                _write_durable(temporary, payload)
            existed = tuple(
                _backup(path, backup)
                for path, backup in zip(paths, transaction.backups, strict=True)
            )
            journal_payload = {
                "schema_version": 1,
                "names": [path.name for path in paths],
                "existed": list(existed),
            }
            journal_temp = _unique_temp(transaction.journal, "journal")
            try:
                _write_durable(journal_temp, _canonical_json(journal_payload) + b"\n")
                os.replace(journal_temp, transaction.journal)
                _fsync_directory(paths[0].parent)
            finally:
                journal_temp.unlink(missing_ok=True)
            try:
                for temporary, path in zip(temporaries, paths, strict=True):
                    replace_file(temporary, path)
                _fsync_directory(paths[0].parent)
            except Exception:
                _recover(paths, transaction)
                raise
            transaction.journal.unlink()
            _fsync_directory(paths[0].parent)
            for backup in transaction.backups:
                backup.unlink(missing_ok=True)
        finally:
            for temporary in temporaries:
                temporary.unlink(missing_ok=True)
            if not transaction.journal.exists():
                for backup in transaction.backups:
                    backup.unlink(missing_ok=True)
