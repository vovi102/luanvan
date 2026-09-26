import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from nl2sparql.evaluation.adapters.b45 import B45AdaptRequest, adapt_b45
from nl2sparql.evaluation.contracts import EvaluationError
from nl2sparql.models.b45 import (
    ArtifactPaths,
    LargeLLMConfig,
    ProviderPolicy,
    publish_large_run,
)
from nl2sparql.models.b45.budget import BudgetSnapshot
from nl2sparql.models.b45.contracts import LargeLLMPrediction, RemoteCompletion
from nl2sparql.models.b45.evaluate import (
    EvaluationOutcome,
    LargeEvaluationMetrics,
    LargeEvaluationRun,
)

SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
CATALOG_SHA = "a" * 64
SUMMARY_SHA = "b" * 64
PROMPT_SHA = "c" * 64
METADATA_SHA = "d" * 64


def _test_set(path: Path, question: str = "List addresses") -> tuple[Path, str]:
    row = {
        "ambiguity_flag": False,
        "categories": ["entity_lookup"],
        "cq_ids": ["CQ01"],
        "difficulty": "easy",
        "evidence_sha256": hashlib.sha256(SQL.encode()).hexdigest(),
        "expected_result_size": 1,
        "id": "q1",
        "nl": question,
        "pool_b_writer": "writer_1",
        "pool_c_reviewers": ["reviewer_1"],
        "schema_elements": ["entity_labels_v1.address"],
        "source": "author_1",
        "sql": SQL,
        "verified_at": "2026-09-26T00:00:00Z",
        "verified_executable": True,
    }
    payload = (json.dumps(row, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _config() -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        concurrency=1,
    )


def _run(input_sha: str, run_id: str = "run-1") -> LargeEvaluationRun:
    completion = RemoteCompletion.synthetic(
        raw_text=SQL,
        generation_id="generation-1",
        model_id=_config().model_id,
        provider_slug="deepinfra",
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=Decimal("0.0100"),
        upstream_cost_usd=Decimal("0.0080"),
        latency_ms=12.5,
        system_fingerprint="fp-test",
    )
    prediction = LargeLLMPrediction(
        baseline="b4",
        question="List addresses",
        raw_output=SQL,
        sql=SQL,
        extraction_status="ok",
        completion=completion,
        catalog_sha256=CATALOG_SHA,
        summary_sha256=SUMMARY_SHA,
        prompt_sha256=PROMPT_SHA,
        config_sha256=_config().sha256,
        latency_ms=12.5,
    )
    budget = BudgetSnapshot(
        cap_usd=Decimal("20"),
        spent_usd=Decimal("0.0100"),
        reserved_usd=Decimal("0"),
        remaining_usd=Decimal("19.9900"),
        unresolved_request_ids=(),
        stop_reason="pricing_violation",
    )
    outcome = EvaluationOutcome(
        case_id="q1",
        question_sha256=hashlib.sha256(b"List addresses").hexdigest(),
        gold_sql=SQL,
        difficulty="easy",
        categories=("entity_lookup",),
        status="completed",
        prediction=prediction,
        safe_error_code=None,
        baseline="b4",
        input_sha256=input_sha,
        config_sha256=_config().sha256,
        catalog_sha256=CATALOG_SHA,
        summary_sha256=SUMMARY_SHA,
        training_sha256=None,
        model_id=_config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA,
        source_synthetic=False,
        source_trusted=True,
        training_accepted=False,
        prompt_sha256=PROMPT_SHA,
        attempt_count=1,
        budget_checkpoint=budget,
    )
    metrics = LargeEvaluationMetrics(
        total=1,
        completed=1,
        extraction_failed=0,
        request_failed=0,
        budget_blocked=0,
        cost_unresolved=0,
        p50_latency_ms=12.5,
        p95_latency_ms=12.5,
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=Decimal("0.0100"),
        cost_per_1k_queries_usd=Decimal("10"),
        extraction_status_counts=(("ok", 1),),
        difficulty_counts=(("easy", 1),),
        category_counts=(("entity_lookup", 1),),
    )
    return LargeEvaluationRun(
        run_id=run_id,
        baseline="b4",
        outcomes=(outcome,),
        metrics=metrics,
        scientific_ready=False,
        blockers=(
            "expected_100_cases",
            "non_three_run_evidence",
            "pricing_violation",
            "synthetic_backend",
        ),
        seed=42,
        generated_at_utc="2026-09-26T12:00:00Z",
        input_sha256=input_sha,
        config_sha256=_config().sha256,
        budget=budget,
        catalog_sha256=CATALOG_SHA,
        summary_sha256=SUMMARY_SHA,
        training_sha256=None,
        model_id=_config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA,
    )


def _publish(tmp_path: Path, run: LargeEvaluationRun, suffix: str = "") -> ArtifactPaths:
    paths = ArtifactPaths(
        predictions=tmp_path / f"predictions{suffix}.jsonl",
        request_log=tmp_path / f"request{suffix}.jsonl",
        cost_csv=tmp_path / f"cost{suffix}.csv",
        report=tmp_path / f"report{suffix}.json",
    )
    publish_large_run(run, paths=paths)
    return paths


def test_b45_uses_native_loader_and_preserves_provider_cost_and_provenance(tmp_path: Path) -> None:
    test_set, input_sha = _test_set(tmp_path / "test.jsonl")
    paths = _publish(tmp_path, _run(input_sha))

    run = adapt_b45(B45AdaptRequest(test_set, paths.report, paths.request_log, synthetic=True))

    assert run.baseline_id == "b4"
    assert run.cases[0].prediction_status == "ok"
    assert run.cases[0].inference.cost.amount == Decimal("0.0100")
    assert run.cases[0].inference.cost.source == "provider:deepinfra"
    assert dict(run.provenance.fingerprints)["provider"] == "deepinfra"
    assert run.cases[0].privacy.documentation_status == "undocumented"
    assert {ref.role for ref in run.source_artifacts} == {"report", "request_log", "test_set"}


def test_b45_rejects_another_test_snapshot_and_report_journal_run_mismatch(
    tmp_path: Path,
) -> None:
    test_set, input_sha = _test_set(tmp_path / "test.jsonl")
    paths1 = _publish(tmp_path, _run(input_sha, "run-1"), "-1")
    paths2 = _publish(tmp_path, _run(input_sha, "run-2"), "-2")
    other_test, _ = _test_set(tmp_path / "other.jsonl", "Different question")

    with pytest.raises(EvaluationError, match="test-set hash"):
        adapt_b45(B45AdaptRequest(other_test, paths1.report, paths1.request_log, synthetic=True))
    with pytest.raises(EvaluationError, match="native B4/B5 artifacts"):
        adapt_b45(B45AdaptRequest(test_set, paths1.report, paths2.request_log, synthetic=True))


def test_b45_rejects_tampered_journal_terminal(tmp_path: Path) -> None:
    test_set, input_sha = _test_set(tmp_path / "test.jsonl")
    paths = _publish(tmp_path, _run(input_sha))
    payload = paths.request_log.read_bytes().replace(
        b'"record_type":"terminal"', b'"record_type":"changed"'
    )
    paths.request_log.write_bytes(payload)

    with pytest.raises(EvaluationError, match="native B4/B5 artifacts"):
        adapt_b45(B45AdaptRequest(test_set, paths.report, paths.request_log, synthetic=True))
