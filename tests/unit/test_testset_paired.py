from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.live import (
    LiveEvidence,
    LiveEvidenceRecord,
    SqlPolicy,
    reuse_paired_live_evidence,
)
from nl2sparql.dataset.testset.paired import (
    AUTHORSHIP_PROFILE,
    REVIEW_PROFILE,
    EnglishPairCase,
    PairedCandidate,
    PairedReviewDecision,
    author_paired_candidates,
    build_paired_manifest,
    derive_unaccented_cases,
    finalize_paired_cases,
    validate_paired_manifest,
    validate_pairing,
)

SAFE_SQL = (
    "SELECT transaction_hash AS transaction_hash FROM "
    "`nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
    "(DATE '2026-06-01', DATE '2026-06-02') LIMIT 1"
)


def _english(index: int) -> EnglishPairCase:
    return EnglishPairCase(
        id=f"t35-{index:03d}",
        question=f"English question {index}",
        sql=SAFE_SQL,
        expected_columns=("transaction_hash",),
        expected_result_size=1,
        difficulty="easy" if index <= 30 else "medium" if index <= 80 else "hard",
        categories=("simple_filter",),
        entity_kinds=("address_only",),
        schema_elements=("transaction_facts", "transaction_facts.transaction_hash"),
        cq_ids=("CQ01",),
    )


def _candidate(source: EnglishPairCase, *, question: str | None = None) -> PairedCandidate:
    return PairedCandidate(
        pair_id=f"pair-{source.id}",
        english_id=source.id,
        question=question or f"Liệt kê giao dịch Ethereum số {source.id[4:]}",
        sql=source.sql,
        expected_columns=source.expected_columns,
        expected_result_size=source.expected_result_size,
        difficulty=source.difficulty,
        categories=source.categories,
        entity_kinds=source.entity_kinds,
        schema_elements=source.schema_elements,
        cq_ids=source.cq_ids,
        english_case_sha256=source.sha256,
    )


def _decision(candidate: PairedCandidate, *, decision: str = "ACCEPT") -> PairedReviewDecision:
    return PairedReviewDecision(
        pair_id=candidate.pair_id,
        review_round=1,
        reviewer_role="user",
        decision=decision,
        naturalness=5,
        sql_faithfulness=5,
        terminology=5,
        ambiguity=1,
    )


def _hundred() -> tuple[
    tuple[EnglishPairCase, ...],
    tuple[PairedCandidate, ...],
    tuple[PairedReviewDecision, ...],
]:
    english = tuple(_english(index) for index in range(1, 101))
    candidates = tuple(_candidate(case) for case in english)
    decisions = tuple(_decision(candidate) for candidate in candidates)
    return english, candidates, decisions


def test_validate_pairing_requires_exact_100_unique_pairs_and_matching_semantics() -> None:
    english, candidates, _ = _hundred()

    report = validate_pairing(english, candidates)

    assert report.status == "paired_draft_valid"
    assert report.pair_count == 100
    assert report.authorship_profile == AUTHORSHIP_PROFILE == "agent-authored"
    assert report.review_profile == REVIEW_PROFILE == "single-human-reviewed"
    assert len(report.english_sha256) == 64
    assert len(report.candidate_sha256) == 64

    with pytest.raises(TestSetError, match="exactly 100"):
        validate_pairing(english[:-1], candidates[:-1])
    with pytest.raises(TestSetError, match="unique pair"):
        validate_pairing(english, candidates[:-1] + (candidates[0],))
    duplicate_question = replace(candidates[1], question=candidates[0].question)
    with pytest.raises(TestSetError, match="unique normalized Vietnamese"):
        validate_pairing(english, (candidates[0], duplicate_question, *candidates[2:]))


def test_agent_authorship_uses_sql_semantics_not_english_surface_text() -> None:
    source = replace(
        _english(1),
        sql=(
            "SELECT COUNT(*) AS transaction_count FROM "
            "`nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
            "(DATE '2026-06-01', DATE '2026-06-08')"
        ),
        expected_columns=("transaction_count",),
        question="An English phrase that must not be translated",
    )
    changed_surface = replace(source, question="Completely different English wording")

    first = author_paired_candidates((source,))[0]
    second = author_paired_candidates((changed_surface,))[0]

    assert first.question == second.question
    assert first.question == (
        "Có bao nhiêu giao dịch trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?"
    )
    assert first.english_case_sha256 != second.english_case_sha256


def test_agent_authored_real_draft_is_complete_valid_and_review_empty(tmp_path: Path) -> None:
    module = _workflow()
    draft_root = tmp_path / "t3_5_vi_candidate_set"

    authored = CliRunner().invoke(
        module.main,
        ["author-draft", "--draft-root", str(draft_root)],
    )

    assert authored.exit_code == 0, authored.output
    payload = json.loads(authored.output)
    assert payload["authorship_profile"] == "agent-authored"
    assert payload["pair_count"] == 100
    assert payload["review_profile"] == "single-human-reviewed"
    assert payload["status"] == "paired_draft_valid"
    assert len(payload["candidate_sha256"]) == 64
    assert len(payload["english_sha256"]) == 64
    candidates = draft_root / "candidates.jsonl"
    review_events = draft_root / "review_events.jsonl"
    assert len(candidates.read_text(encoding="utf-8").splitlines()) == 100
    assert review_events.read_bytes() == b""
    assert (draft_root / "REVIEW_GUIDE.md").is_file()
    manifest = json.loads((draft_root / "manifest.json").read_bytes())
    validation = json.loads((draft_root / "validation-report.json").read_bytes())
    assert manifest["authorship_profile"] == "agent-authored"
    assert manifest["review_profile"] == "single-human-reviewed"
    assert manifest["candidate_count"] == 100
    assert validation["status"] == "paired_draft_valid"
    assert validation["candidate_sha256"] == manifest["candidate_sha256"]

    validated = CliRunner().invoke(
        module.main,
        ["validate-draft", "--candidates", str(candidates)],
    )
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["pair_count"] == 100


@pytest.mark.parametrize(
    "field",
    (
        "sql",
        "expected_columns",
        "difficulty",
        "categories",
        "entity_kinds",
        "schema_elements",
        "cq_ids",
        "english_case_sha256",
    ),
)
def test_validate_pairing_rejects_mismatched_pair_metadata(field: str) -> None:
    english, candidates, _ = _hundred()
    value: object = "f" * 64 if field == "english_case_sha256" else ("different",)
    if field == "sql":
        value = SAFE_SQL.replace("LIMIT 1", "LIMIT 2")
    elif field == "difficulty":
        value = "medium"
    mutated = replace(candidates[0], **{field: value})

    with pytest.raises(TestSetError, match=field):
        validate_pairing(english, (mutated, *candidates[1:]))


def test_review_contract_rejects_fabricated_or_inflated_provenance() -> None:
    candidate = _candidate(_english(1))
    row = _decision(candidate).to_mapping()

    for mutation in (
        {"reviewer_role": "human-review-01"},
        {"reviewer_role": "independent-reviewer"},
        {"independent_review": True},
        {"agreement": 1.0},
        {"second_reviewer": "someone"},
    ):
        with pytest.raises(TestSetError):
            PairedReviewDecision.from_mapping({**row, **mutation})

    candidate_row = candidate.to_mapping()
    for mutation in (
        {"review_profile": "human-review-01"},
        {"independent_review": True},
        {"second_reviewer": "someone"},
    ):
        with pytest.raises(TestSetError):
            PairedCandidate.from_mapping({**candidate_row, **mutation})


def test_finalization_requires_100_explicit_accepts_and_preserves_original_evidence() -> None:
    english, candidates, decisions = _hundred()

    finalized = finalize_paired_cases(english, candidates, decisions)

    assert len(finalized) == 100
    assert finalized[0].question == candidates[0].question
    assert finalized[0].original_question == candidates[0].question
    assert finalized[0].authorship_profile == AUTHORSHIP_PROFILE
    assert finalized[0].review_profile == REVIEW_PROFILE
    assert finalized[0].language == "vi"
    assert finalized[0].text_variant == "canonical"
    assert finalized[0].sql == english[0].sql

    with pytest.raises(TestSetError, match="100 explicit ACCEPT"):
        finalize_paired_cases(english, candidates, decisions[:-1])
    rejected = (replace(decisions[0], decision="REJECT"), *decisions[1:])
    with pytest.raises(TestSetError, match="rejected|ACCEPT"):
        finalize_paired_cases(english, candidates, rejected)


def test_revision_requires_a_later_explicit_acceptance() -> None:
    english, candidates, decisions = _hundred()
    revised_text = "Hãy liệt kê giao dịch Ethereum số 001"
    revision = replace(
        decisions[0],
        decision="REVISE",
        revised_question=revised_text,
    )

    with pytest.raises(TestSetError, match="pending|ACCEPT"):
        finalize_paired_cases(english, candidates, (revision, *decisions[1:]))

    acceptance = replace(
        decisions[0],
        review_round=2,
        decision="ACCEPT",
    )
    finalized = finalize_paired_cases(
        english,
        candidates,
        (revision, acceptance, *decisions[1:]),
    )
    assert finalized[0].question == revised_text


def test_derive_unaccented_preserves_parent_identity_hashes_and_protected_tokens() -> None:
    english, candidates, decisions = _hundred()
    candidates = (
        replace(
            candidates[0],
            question=("Liệt kê 1,250.50 USDT từ 0xAbC123 ngày 2026-10-04 của Đồng"),
        ),
        *candidates[1:],
    )
    finalized = finalize_paired_cases(english, candidates, decisions)

    unaccented = derive_unaccented_cases(finalized)

    first = unaccented[0]
    assert first.question == "Liet ke 1,250.50 USDT tu 0xAbC123 ngay 2026-10-04 cua Dong"
    assert first.original_question == candidates[0].question
    assert first.text_variant == "unaccented"
    assert first.accented_parent_id == finalized[0].id
    assert first.accented_parent_sha256 == finalized[0].sha256
    for token in ("1,250.50", "USDT", "0xAbC123", "2026-10-04"):
        assert token in first.question


def test_derive_unaccented_rejects_unchanged_or_colliding_questions() -> None:
    english, candidates, decisions = _hundred()
    candidates = (
        replace(candidates[0], question="Liet ke giao dich Ethereum 001"),
        *candidates[1:],
    )
    finalized = finalize_paired_cases(english, candidates, decisions)
    with pytest.raises(TestSetError, match="unchanged"):
        derive_unaccented_cases(finalized)


def test_live_evidence_reuse_requires_exact_sql_result_contract_and_policy() -> None:
    english, candidates, decisions = _hundred()
    finalized = finalize_paired_cases(english, candidates, decisions)
    policy = SqlPolicy(per_query_bytes=10_000, total_bytes=1_000_000, location="US")
    policy_sha = hashlib.sha256(
        json.dumps(
            {
                "location": "US",
                "per_query_bytes": 10_000,
                "total_bytes": 1_000_000,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    ).hexdigest()
    records = tuple(
        LiveEvidenceRecord(
            question_id=case.id,
            sql_sha256=hashlib.sha256(case.sql.encode()).hexdigest(),
            row_count=1,
            columns=case.expected_columns,
            processed_bytes=10,
            billed_bytes=10,
            cache_hit=False,
            job_id=f"job-{case.id}",
            wall_latency_ms=1.0,
            project="project",
            location="US",
            verified_at="2026-10-02T00:00:00Z",
            policy_sha256=policy_sha,
        )
        for case in english
    )
    evidence = LiveEvidence(
        status="ready",
        generated_at="2026-10-02T00:00:00Z",
        records=records,
        total_processed_bytes=1_000,
        total_billed_bytes=1_000,
        input_sha256="a" * 64,
    )

    reused = reuse_paired_live_evidence(english, finalized, evidence, policy=policy)
    assert len(reused.records) == 100
    assert reused.records[0].question_id == finalized[0].id

    changed_sql = (replace(finalized[0], sql=finalized[0].sql + " "), *finalized[1:])
    with pytest.raises(TestSetError, match="SQL bytes"):
        reuse_paired_live_evidence(english, changed_sql, evidence, policy=policy)
    with pytest.raises(TestSetError, match="policy"):
        reuse_paired_live_evidence(
            english,
            finalized,
            evidence,
            policy=replace(policy, total_bytes=policy.total_bytes + 1),
        )


def test_manifests_bind_english_accented_and_unaccented_hashes() -> None:
    english, candidates, decisions = _hundred()
    accented = finalize_paired_cases(english, candidates, decisions)
    unaccented = derive_unaccented_cases(accented)
    english_sha = "a" * 64
    accented_manifest = build_paired_manifest(
        accented,
        english_benchmark_sha256=english_sha,
    )
    unaccented_manifest = build_paired_manifest(
        unaccented,
        english_benchmark_sha256=english_sha,
        parent_manifest_sha256=accented_manifest.manifest_sha256,
    )

    validate_paired_manifest(accented, accented_manifest)
    validate_paired_manifest(unaccented, unaccented_manifest)
    assert accented_manifest.english_benchmark_sha256 == english_sha
    assert unaccented_manifest.parent_manifest_sha256 == accented_manifest.manifest_sha256
    with pytest.raises(TestSetError, match="output hash"):
        validate_paired_manifest(unaccented[:-1], unaccented_manifest)


def _workflow():
    path = Path("scripts/22_vietnamese_testset_workflow.py").resolve()
    spec = importlib.util.spec_from_file_location("vietnamese_testset_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_exposes_offline_first_commands_without_initializing_bigquery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _workflow()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline command initialized BigQuery")

    monkeypatch.setattr(module, "create_bigquery_client", forbidden)
    runner = CliRunner()
    result = runner.invoke(module.main, ["--help"])

    assert result.exit_code == 0
    for command in (
        "draft",
        "validate-draft",
        "apply-review",
        "derive-unaccented",
        "verify-live",
        "validate-final",
    ):
        assert command in result.output

    for command in (
        "draft",
        "validate-draft",
        "apply-review",
        "derive-unaccented",
        "validate-final",
    ):
        command_help = runner.invoke(module.main, [command, "--help"])
        assert command_help.exit_code == 0


def test_cli_english_loader_restores_bound_entity_annotations() -> None:
    module = _workflow()

    cases, reviewed = module._load_english(
        Path("data/dataset/test/test-100.jsonl"),
        Path("data/dataset/test/live-evidence.json"),
    )

    assert len(cases) == len(reviewed.execution.records) == 100
    assert all(case.entity_kinds for case in cases)
