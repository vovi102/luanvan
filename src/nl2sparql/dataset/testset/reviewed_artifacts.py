"""Artifacts and immutable finalization for the reviewed T3.5 profile."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from nl2sparql.dataset.testset.artifacts import _atomic_write
from nl2sparql.dataset.testset.contracts import FinalCase, TestSetError
from nl2sparql.dataset.testset.live import (
    LiveEvidence,
    LiveEvidenceRecord,
    SqlPolicy,
    evidence_input_sha256,
)
from nl2sparql.dataset.testset.reviewed_contracts import (
    AGENT_REVIEWED_PROFILE,
    AcceptedCandidate,
    ReviewedTestSetPaths,
)
from nl2sparql.dataset.testset.reviewed_validate import (
    ReviewBundleReport,
    ReviewedBundle,
    resolve_review_state,
    validate_reviewed_selection,
)

LIMITATIONS = (
    "agent_authored",
    "single_human_reviewer",
    "no_independent_authorship",
    "no_inter_rater_agreement",
    "no_kappa_claim",
)

_REVIEW_HEADER = (
    "question_id,review_round,reviewer_id,nl_quality,sql_faithfulness,"
    "difficulty,decision,revised_nl,revised_sql,notes\n"
)
_SELECTION_HEADER = (
    "question_id,final_difficulty,categories,entity_kinds,schema_elements,cq_ids,selection_note\n"
)
_REVIEW_GUIDE = """# T3.5 candidate review guide

The candidates are agent-authored. Record one append-only event per review round
in `review_events.csv` using a stable pseudonymous reviewer ID. `ACCEPT` requires
both scores to be at least 4. `REVISE` requires changed NL or SQL and a later
explicit `ACCEPT`; it never implies acceptance. `REJECT` is terminal.

After all 120 candidates have terminal decisions, list exactly 100 accepted IDs
in `final_selection.csv` with 30 easy, 50 medium, and 20 hard cases. Do not edit
`candidates.jsonl`. BigQuery verification and final publication remain pending
until the review files pass offline validation.
"""


@dataclass(frozen=True)
class ReviewedLiveEvidence:
    """Live execution evidence bound to one reviewed selection snapshot."""

    provenance_profile: str
    reviewed_bundle_sha256: str
    project: str
    policy: SqlPolicy
    execution: LiveEvidence

    def __post_init__(self) -> None:
        if self.provenance_profile != AGENT_REVIEWED_PROFILE:
            raise TestSetError(f"provenance_profile must be {AGENT_REVIEWED_PROFILE}")
        if (
            not isinstance(self.reviewed_bundle_sha256, str)
            or len(self.reviewed_bundle_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.reviewed_bundle_sha256)
        ):
            raise TestSetError("reviewed_bundle_sha256 must be a lower-case SHA-256")
        if not isinstance(self.project, str) or not self.project.strip():
            raise TestSetError("reviewed live evidence project must be explicit")
        if not isinstance(self.policy, SqlPolicy):
            raise TestSetError("reviewed live evidence policy is invalid")


@dataclass(frozen=True)
class ReviewedFinalizationReport:
    """Digests emitted after immutable reviewed benchmark publication."""

    status: str
    record_count: int
    output_sha256: str
    manifest_sha256: str
    provenance_bundle_sha256: str


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _reviewed_bundle_sha256(report: ReviewBundleReport) -> str:
    return _canonical_sha256(
        {
            "accepted_content_sha256": report.accepted_content_sha256,
            "provenance_profile": report.provenance_profile,
            "review_sha256": report.review_sha256,
            "selection_sha256": report.selection_sha256,
        }
    )


def bind_reviewed_live_evidence(
    report: ReviewBundleReport,
    execution: LiveEvidence,
    *,
    project: str,
    policy: SqlPolicy,
) -> ReviewedLiveEvidence:
    """Bind a live executor result to the exact reviewed bundle report."""
    policy_sha256 = _canonical_sha256(asdict(policy))
    enriched = replace(
        execution,
        records=tuple(
            replace(
                record,
                project=project,
                location=policy.location,
                verified_at=execution.generated_at,
                policy_sha256=policy_sha256,
            )
            for record in execution.records
        ),
    )
    return ReviewedLiveEvidence(
        provenance_profile=AGENT_REVIEWED_PROFILE,
        reviewed_bundle_sha256=_reviewed_bundle_sha256(report),
        project=project,
        policy=policy,
        execution=enriched,
    )


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise TestSetError(f"unable to read existing artifact {path}: {exc}") from exc
        if current != payload:
            raise TestSetError(f"refusing to overwrite byte-different artifact {path}")
        return
    _atomic_write(path, payload)


def write_review_scaffold(paths: ReviewedTestSetPaths, *, force: bool = False) -> tuple[Path, ...]:
    """Create empty human-owned review files without inventing decisions."""
    del force
    contents = (
        (paths.review_events, _REVIEW_HEADER),
        (paths.final_selection, _SELECTION_HEADER),
        (paths.review_guide, _REVIEW_GUIDE),
    )
    for path, content in contents:
        if path.exists() and path.stat().st_size:
            raise TestSetError(f"refusing to overwrite non-empty file {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, content.encode())
    return tuple(path for path, _content in contents)


def build_live_cases(
    bundle: ReviewedBundle,
    accepted: tuple[AcceptedCandidate, ...],
) -> tuple[FinalCase, ...]:
    """Build guarded executor inputs from explicit accepted selection only."""
    accepted_by_id = {candidate.question_id: candidate for candidate in accepted}
    cases: list[FinalCase] = []
    for selection in bundle.selections:
        candidate = accepted_by_id.get(selection.question_id)
        if candidate is None:
            raise TestSetError(f"selection contains non-accepted ID {selection.question_id}")
        cases.append(
            FinalCase(
                id=candidate.question_id,
                source="agent",
                nl=candidate.nl,
                sql=candidate.sql,
                difficulty=selection.final_difficulty,
                categories=selection.categories,
                schema_elements=selection.schema_elements,
                cq_ids=selection.cq_ids,
                expected_result_size=(None if candidate.expected_empty else 1),
                ambiguity_flag=candidate.ambiguity_flag,
                pool_b_writer="agent",
                pool_c_reviewers=(candidate.reviewer_id,),
                verified_executable=False,
                verified_at=None,
                evidence_sha256=None,
                expected_columns=candidate.expected_columns,
            )
        )
    return tuple(cases)


def _evidence_body(evidence: ReviewedLiveEvidence) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "provenance_profile": evidence.provenance_profile,
        "reviewed_bundle_sha256": evidence.reviewed_bundle_sha256,
        "project": evidence.project,
        "policy": asdict(evidence.policy),
        "execution": asdict(evidence.execution),
    }


def write_reviewed_live_evidence(evidence: ReviewedLiveEvidence, path: Path) -> None:
    """Write canonical profile-bound live evidence with tamper detection."""
    body = _evidence_body(evidence)
    payload = {**body, "artifact_sha256": _canonical_sha256(body)}
    _write_immutable(path, _canonical_json(payload))


def read_reviewed_live_evidence(path: Path) -> ReviewedLiveEvidence:
    """Read reviewed live evidence only when schema, profile, and digest match."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TestSetError(f"unable to read reviewed live evidence {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TestSetError("reviewed live evidence must be a JSON object")
    supplied = raw.pop("artifact_sha256", None)
    if not isinstance(supplied, str) or supplied != _canonical_sha256(raw):
        raise TestSetError("reviewed live evidence digest mismatch")
    if (
        set(raw)
        != {
            "schema_version",
            "provenance_profile",
            "reviewed_bundle_sha256",
            "project",
            "policy",
            "execution",
        }
        or raw["schema_version"] != "1.0.0"
    ):
        raise TestSetError("reviewed live evidence schema mismatch")
    execution_raw = raw["execution"]
    if not isinstance(execution_raw, dict):
        raise TestSetError("reviewed live evidence execution must be an object")
    try:
        policy_raw = raw["policy"]
        if not isinstance(policy_raw, dict) or set(policy_raw) != {
            "per_query_bytes",
            "total_bytes",
            "location",
        }:
            raise TypeError
        policy = SqlPolicy(**policy_raw)
        records = tuple(
            LiveEvidenceRecord(**{**record, "columns": tuple(record["columns"])})
            for record in execution_raw["records"]
        )
        execution = LiveEvidence(
            status=execution_raw["status"],
            generated_at=execution_raw["generated_at"],
            records=records,
            total_processed_bytes=execution_raw["total_processed_bytes"],
            total_billed_bytes=execution_raw["total_billed_bytes"],
            input_sha256=execution_raw["input_sha256"],
        )
    except (KeyError, TypeError) as exc:
        raise TestSetError("reviewed live evidence execution schema mismatch") from exc
    return ReviewedLiveEvidence(
        provenance_profile=raw["provenance_profile"],
        reviewed_bundle_sha256=raw["reviewed_bundle_sha256"],
        project=raw["project"],
        policy=policy,
        execution=execution,
    )


def _validate_execution(
    accepted: tuple[AcceptedCandidate, ...],
    bundle: ReviewedBundle,
    evidence: ReviewedLiveEvidence,
    expected_policy: SqlPolicy,
) -> dict[str, LiveEvidenceRecord]:
    execution = evidence.execution
    if execution.status != "ready":
        raise TestSetError("live evidence must have ready status")
    try:
        generated = datetime.fromisoformat(execution.generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TestSetError("live evidence generated_at must be valid UTC") from exc
    if not execution.generated_at.endswith("Z") or generated.utcoffset() != timedelta(0):
        raise TestSetError("live evidence generated_at must be valid UTC")
    records = execution.records
    record_ids = tuple(record.question_id for record in records)
    if len(record_ids) != len(set(record_ids)):
        raise TestSetError("live evidence contains duplicate IDs")
    selected_ids = tuple(selection.question_id for selection in bundle.selections)
    if set(record_ids) != set(selected_ids):
        raise TestSetError("live evidence IDs must exactly match final selection IDs")
    if execution.total_processed_bytes != sum(record.processed_bytes for record in records):
        raise TestSetError("live evidence processed-byte total is inconsistent")
    if execution.total_billed_bytes != sum(record.billed_bytes for record in records):
        raise TestSetError("live evidence billed-byte total is inconsistent")
    policy = evidence.policy
    if policy != expected_policy:
        raise TestSetError("live evidence policy does not match the fixed reviewed policy")
    policy_sha256 = _canonical_sha256(asdict(policy))
    if (
        execution.total_processed_bytes > policy.total_bytes
        or execution.total_billed_bytes > policy.total_bytes
    ):
        raise TestSetError("live evidence exceeds aggregate policy")
    if any(
        record.cache_hit
        or record.processed_bytes < 0
        or record.billed_bytes < 0
        or record.processed_bytes > policy.per_query_bytes
        or record.billed_bytes > policy.per_query_bytes
        or record.row_count < 0
        or record.wall_latency_ms < 0
        or not record.job_id
        or record.project != evidence.project
        or record.location != policy.location
        or record.verified_at != execution.generated_at
        or record.policy_sha256 != policy_sha256
        for record in records
    ):
        raise TestSetError("live evidence violates per-query policy")
    expected_input = evidence_input_sha256(
        (record.question_id, record.sql_sha256) for record in records
    )
    if execution.input_sha256 != expected_input:
        raise TestSetError("live evidence input hash mismatch")

    accepted_by_id = {candidate.question_id: candidate for candidate in accepted}
    by_id = {record.question_id: record for record in records}
    for question_id in selected_ids:
        candidate = accepted_by_id[question_id]
        record = by_id[question_id]
        if record.sql_sha256 != hashlib.sha256(candidate.sql.encode()).hexdigest():
            raise TestSetError(f"live evidence SQL hash mismatch for {question_id}")
        if record.columns != candidate.expected_columns:
            raise TestSetError(f"live evidence columns mismatch for {question_id}")
        if candidate.expected_empty and record.row_count != 0:
            raise TestSetError(f"live evidence row policy mismatch for {question_id}")
        if not candidate.expected_empty and record.row_count <= 0:
            raise TestSetError(f"live evidence row policy mismatch for {question_id}")
    return by_id


def _preflight_immutable(path: Path, payload: bytes) -> None:
    if path.exists() and path.read_bytes() != payload:
        raise TestSetError(f"refusing to overwrite byte-different artifact {path}")


def finalize_reviewed_bundle(
    bundle: ReviewedBundle,
    evidence: ReviewedLiveEvidence,
    *,
    expected_policy: SqlPolicy,
    output_path: Path,
    manifest_path: Path,
    repo_root: Path,
    catalog_path: Path,
) -> ReviewedFinalizationReport:
    """Publish an immutable reviewed benchmark only after every gate passes."""
    review = validate_reviewed_selection(bundle, repo_root=repo_root, catalog_path=catalog_path)
    expected_bundle_sha256 = _reviewed_bundle_sha256(review)
    if evidence.provenance_profile != AGENT_REVIEWED_PROFILE:
        raise TestSetError("live evidence provenance profile mismatch")
    if evidence.reviewed_bundle_sha256 != expected_bundle_sha256:
        raise TestSetError("live evidence reviewed bundle digest mismatch")
    accepted = resolve_review_state(bundle, repo_root=repo_root, catalog_path=catalog_path)
    accepted_by_id = {candidate.question_id: candidate for candidate in accepted}
    live_by_id = _validate_execution(accepted, bundle, evidence, expected_policy)
    try:
        catalog_sha256 = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise TestSetError(f"unable to read catalog {catalog_path}: {exc}") from exc
    live_evidence_sha256 = _canonical_sha256(_evidence_body(evidence))
    provenance_bundle_sha256 = _canonical_sha256(
        {
            "accepted": [
                {
                    "accepted_content_sha256": candidate.accepted_content_sha256,
                    "candidate_sha256": candidate.candidate_sha256,
                    "question_id": candidate.question_id,
                }
                for candidate in accepted
            ],
            "catalog_sha256": catalog_sha256,
            "live_evidence_sha256": live_evidence_sha256,
            "selection_sha256": review.selection_sha256,
        }
    )

    rows: list[dict[str, Any]] = []
    for selection in bundle.selections:
        candidate = accepted_by_id[selection.question_id]
        live = live_by_id[selection.question_id]
        rows.append(
            {
                "accepted_content_sha256": candidate.accepted_content_sha256,
                "ambiguity_flag": candidate.ambiguity_flag,
                "candidate_sha256": candidate.candidate_sha256,
                "catalog_sha256": catalog_sha256,
                "categories": list(selection.categories),
                "cq_ids": list(selection.cq_ids),
                "difficulty": selection.final_difficulty,
                "evidence_sha256": live.sql_sha256,
                "expected_result_size": live.row_count,
                "id": candidate.question_id,
                "live_evidence_sha256": live_evidence_sha256,
                "nl": candidate.nl,
                "pool_b_writer": "agent",
                "pool_c_reviewers": [candidate.reviewer_id],
                "provenance_bundle_sha256": provenance_bundle_sha256,
                "provenance_profile": AGENT_REVIEWED_PROFILE,
                "review_provenance": "single_human_reviewer",
                "schema_elements": list(selection.schema_elements),
                "selection_sha256": review.selection_sha256,
                "source": "agent",
                "sql": candidate.sql,
                "verified_at": live.verified_at,
                "verified_executable": True,
            }
        )
    output_payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    output_sha256 = hashlib.sha256(output_payload).hexdigest()
    manifest = {
        "schema_version": "1.0.0",
        "provenance_profile": AGENT_REVIEWED_PROFILE,
        "review_provenance": "single_human_reviewer",
        "limitations": list(LIMITATIONS),
        "record_count": len(rows),
        "output_sha256": output_sha256,
        "provenance_bundle_sha256": provenance_bundle_sha256,
        "review_sha256": review.review_sha256,
        "selection_sha256": review.selection_sha256,
        "live_evidence_sha256": live_evidence_sha256,
        "catalog_sha256": catalog_sha256,
    }
    manifest_payload = _canonical_json(manifest)
    _preflight_immutable(output_path, output_payload)
    _preflight_immutable(manifest_path, manifest_payload)
    _write_immutable(output_path, output_payload)
    # Consumers treat the validated manifest as the readiness marker, so it is
    # published only after the complete content-addressed JSONL is durable.
    _write_immutable(manifest_path, manifest_payload)
    return ReviewedFinalizationReport(
        status="finalized",
        record_count=len(rows),
        output_sha256=output_sha256,
        manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
        provenance_bundle_sha256=provenance_bundle_sha256,
    )
