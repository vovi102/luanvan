"""Tests for hash-bound reviewed T3.5 artifacts and finalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from nl2sparql.dataset.testset.contracts import SelectionRecord, TestSetError
from nl2sparql.dataset.testset.live import (
    LiveEvidence,
    LiveEvidenceRecord,
    SqlPolicy,
    evidence_input_sha256,
)
from nl2sparql.dataset.testset.reviewed_artifacts import (
    LIMITATIONS,
    bind_reviewed_live_evidence,
    build_live_cases,
    finalize_reviewed_bundle,
    read_reviewed_live_evidence,
    write_review_scaffold,
    write_reviewed_live_evidence,
)
from nl2sparql.dataset.testset.reviewed_contracts import (
    AGENT_REVIEWED_PROFILE,
    CandidateRecord,
    ReviewedTestSetPaths,
    ReviewEvent,
)
from nl2sparql.dataset.testset.reviewed_validate import (
    ReviewedBundle,
    resolve_review_state,
    validate_reviewed_selection,
)

CATALOG = Path("src/nl2sparql/sql/catalog/ethereum_analytics.json")
SQL = (
    "SELECT COUNT(*) AS transaction_count "
    "FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
    "(DATE '2026-06-01', DATE '2026-07-01')"
)
CATEGORIES = (
    "simple_filter",
    "time_range",
    "transaction_aggregation",
    "top_k",
    "comparison",
    "multi_hop",
)
KINDS = ("address_only", "concept_class", "named_entity")


def _candidate(index: int) -> CandidateRecord:
    difficulty = "easy" if index <= 36 else "medium" if index <= 96 else "hard"
    return CandidateRecord.from_mapping(
        {
            "schema_version": "1.0.0",
            "provenance_profile": AGENT_REVIEWED_PROFILE,
            "question_id": f"t35-{index:03d}",
            "author_type": "agent",
            "nl": f"Artifact fixture question {index:03d} about June activity?",
            "sql": SQL,
            "expected_columns": ["transaction_count"],
            "expected_empty": False,
            "ambiguity_flag": False,
            "difficulty": difficulty,
            "categories": [CATEGORIES[(index - 1) % len(CATEGORIES)]],
            "entity_kinds": [KINDS[(index - 1) % len(KINDS)]],
            "schema_elements": [
                "transaction_facts",
                "transaction_facts.transaction_hash",
            ],
            "cq_ids": ["CQ01"],
            "rationale": f"Artifact fixture rationale {index:03d}.",
            "generation_batch": "t35-agent-batch-01",
            "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
            "source_commit": "b" * 40,
        }
    )


def _bundle() -> ReviewedBundle:
    candidates = tuple(_candidate(index) for index in range(1, 121))
    events = tuple(
        ReviewEvent(
            row.question_id,
            1,
            "reviewer_01",
            4,
            4,
            row.difficulty,
            "ACCEPT",
        )
        for row in candidates
    )
    chosen = candidates[:30] + candidates[36:86] + candidates[96:116]
    selections = tuple(
        SelectionRecord(
            row.question_id,
            row.difficulty,
            row.categories,
            "selected",
            row.entity_kinds,
            row.schema_elements,
            row.cq_ids,
        )
        for row in chosen
    )
    return ReviewedBundle(candidates, events, selections)


def _execution(cases: tuple[object, ...]) -> LiveEvidence:
    records = tuple(
        LiveEvidenceRecord(
            question_id=case.id,
            sql_sha256=hashlib.sha256(case.sql.encode()).hexdigest(),
            row_count=1,
            columns=case.expected_columns,
            processed_bytes=1,
            billed_bytes=1,
            cache_hit=False,
            job_id=f"job-{case.id}",
            wall_latency_ms=1.0,
        )
        for case in cases
    )
    return LiveEvidence(
        status="ready",
        generated_at="2026-09-27T00:00:00Z",
        records=records,
        total_processed_bytes=len(records),
        total_billed_bytes=len(records),
        input_sha256=evidence_input_sha256(
            (record.question_id, record.sql_sha256) for record in records
        ),
    )


def _bound_evidence(
    tmp_path: Path,
    bundle: ReviewedBundle,
    *,
    policy: SqlPolicy | None = None,
):
    policy = policy or SqlPolicy(
        per_query_bytes=20 * 2**30,
        total_bytes=64 * 2**30,
        location="US",
    )
    report = validate_reviewed_selection(bundle, repo_root=tmp_path, catalog_path=CATALOG)
    accepted = resolve_review_state(bundle, repo_root=tmp_path, catalog_path=CATALOG)
    cases = build_live_cases(bundle, accepted)
    return bind_reviewed_live_evidence(
        report,
        _execution(cases),
        project="nl2sparql-thesis",
        policy=policy,
    )


def test_write_review_scaffold_never_invents_or_overwrites_decisions(tmp_path: Path) -> None:
    paths = ReviewedTestSetPaths.from_roots(tmp_path / "draft", tmp_path / "final")

    created = write_review_scaffold(paths)

    assert created == (paths.review_events, paths.final_selection, paths.review_guide)
    assert paths.review_events.read_text(encoding="utf-8").count("\n") == 1
    assert paths.final_selection.read_text(encoding="utf-8").count("\n") == 1
    assert not paths.candidates.exists()
    paths.review_events.write_text("human data", encoding="utf-8")
    with pytest.raises(TestSetError, match="overwrite"):
        write_review_scaffold(paths)
    with pytest.raises(TestSetError, match="overwrite"):
        write_review_scaffold(paths, force=True)


def test_build_live_cases_uses_truthful_agent_reviewed_provenance(tmp_path: Path) -> None:
    bundle = _bundle()
    accepted = resolve_review_state(bundle, repo_root=tmp_path, catalog_path=CATALOG)

    cases = build_live_cases(bundle, accepted)

    assert len(cases) == 100
    assert {case.source for case in cases} == {"agent"}
    assert {case.pool_b_writer for case in cases} == {"agent"}
    assert {case.pool_c_reviewers for case in cases} == {("reviewer_01",)}
    assert all(case.expected_columns == ("transaction_count",) for case in cases)


def test_reviewed_live_evidence_round_trips_and_detects_tampering(tmp_path: Path) -> None:
    bundle = _bundle()
    evidence = _bound_evidence(tmp_path, bundle)
    path = tmp_path / "live-evidence.json"

    write_reviewed_live_evidence(evidence, path)

    assert read_reviewed_live_evidence(path) == evidence
    assert evidence.project == "nl2sparql-thesis"
    assert evidence.policy.location == "US"
    assert {record.project for record in evidence.execution.records} == {"nl2sparql-thesis"}
    assert {record.location for record in evidence.execution.records} == {"US"}
    assert {record.verified_at for record in evidence.execution.records} == {
        evidence.execution.generated_at
    }
    assert all(record.policy_sha256 for record in evidence.execution.records)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["provenance_profile"] = "three_pool_v1"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TestSetError, match="digest|provenance"):
        read_reviewed_live_evidence(path)


@pytest.mark.parametrize("mutation", ("bundle", "missing", "duplicate", "sql", "selection"))
def test_finalize_reviewed_bundle_rejects_stale_or_partial_evidence(
    tmp_path: Path, mutation: str
) -> None:
    bundle = _bundle()
    evidence = _bound_evidence(tmp_path, bundle)
    if mutation == "bundle":
        evidence = replace(evidence, reviewed_bundle_sha256="0" * 64)
    elif mutation == "missing":
        execution = replace(evidence.execution, records=evidence.execution.records[:-1])
        evidence = replace(evidence, execution=execution)
    elif mutation == "duplicate":
        execution = replace(
            evidence.execution,
            records=(*evidence.execution.records[:-1], evidence.execution.records[0]),
        )
        evidence = replace(evidence, execution=execution)
    elif mutation == "sql":
        first = replace(evidence.execution.records[0], sql_sha256="0" * 64)
        execution = replace(evidence.execution, records=(first, *evidence.execution.records[1:]))
        evidence = replace(evidence, execution=execution)
    else:
        first_selection = replace(bundle.selections[0], selection_note="changed after evidence")
        bundle = replace(bundle, selections=(first_selection, *bundle.selections[1:]))

    with pytest.raises(TestSetError, match="bundle|IDs|duplicate|SQL|evidence"):
        finalize_reviewed_bundle(
            bundle,
            evidence,
            expected_policy=SqlPolicy(),
            output_path=tmp_path / "test-100.jsonl",
            manifest_path=tmp_path / "manifest.json",
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_finalize_reviewed_bundle_writes_non_circular_immutable_artifacts(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    evidence = _bound_evidence(tmp_path, bundle)
    output = tmp_path / "test-100.jsonl"
    manifest_path = tmp_path / "manifest.json"

    report = finalize_reviewed_bundle(
        bundle,
        evidence,
        expected_policy=SqlPolicy(),
        output_path=output,
        manifest_path=manifest_path,
        repo_root=tmp_path,
        catalog_path=CATALOG,
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert report.status == "finalized"
    assert report.record_count == 100
    assert len(rows) == 100
    assert set(rows[0]) == {
        "accepted_content_sha256",
        "ambiguity_flag",
        "candidate_sha256",
        "catalog_sha256",
        "categories",
        "cq_ids",
        "difficulty",
        "evidence_sha256",
        "expected_result_size",
        "id",
        "live_evidence_sha256",
        "nl",
        "pool_b_writer",
        "pool_c_reviewers",
        "provenance_bundle_sha256",
        "provenance_profile",
        "review_provenance",
        "schema_elements",
        "selection_sha256",
        "source",
        "sql",
        "verified_at",
        "verified_executable",
    }
    assert "manifest_sha256" not in rows[0]
    assert {row["provenance_bundle_sha256"] for row in rows} == {report.provenance_bundle_sha256}
    assert manifest["limitations"] == list(LIMITATIONS)
    assert manifest["output_sha256"] == report.output_sha256
    assert manifest["provenance_bundle_sha256"] == report.provenance_bundle_sha256
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == report.manifest_sha256

    assert (
        finalize_reviewed_bundle(
            bundle,
            evidence,
            expected_policy=SqlPolicy(),
            output_path=output,
            manifest_path=manifest_path,
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )
        == report
    )
    output.write_text("different bytes\n", encoding="utf-8")
    with pytest.raises(TestSetError, match="overwrite"):
        finalize_reviewed_bundle(
            bundle,
            evidence,
            expected_policy=SqlPolicy(),
            output_path=output,
            manifest_path=manifest_path,
            repo_root=tmp_path,
            catalog_path=CATALOG,
        )


def test_finalize_reviewed_bundle_accepts_explicit_authorized_policy(tmp_path: Path) -> None:
    bundle = _bundle()
    policy = SqlPolicy(
        per_query_bytes=24 * 2**30,
        total_bytes=600 * 2**30,
        location="US",
    )
    evidence = _bound_evidence(tmp_path, bundle, policy=policy)

    report = finalize_reviewed_bundle(
        bundle,
        evidence,
        expected_policy=policy,
        output_path=tmp_path / "test-100.jsonl",
        manifest_path=tmp_path / "manifest.json",
        repo_root=tmp_path,
        catalog_path=CATALOG,
    )

    assert report.status == "finalized"
