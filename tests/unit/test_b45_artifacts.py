from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import nl2sparql.models.b45.artifacts as artifacts
from nl2sparql.models.b12 import EvaluationCase
from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import (
    BudgetLedger,
    LargeBaselineEvidence,
    LargeLLMConfig,
    LargeLLMError,
    ProviderPolicy,
)
from nl2sparql.models.b45.budget import BudgetReservation, BudgetSnapshot
from nl2sparql.models.b45.contracts import LargeLLMPrediction, RemoteCompletion
from nl2sparql.models.b45.evaluate import (
    EvaluationOutcome,
    LargeEvaluationMetrics,
    LargeEvaluationRun,
    evaluate_large_baseline,
)
from nl2sparql.models.b45.openrouter import ModelMetadataEvidence, OpenRouterTransport

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
INPUT_SHA256 = "f" * 64
CATALOG_SHA256 = "a" * 64
SUMMARY_SHA256 = "b" * 64
PROMPT_SHA256 = "c" * 64
METADATA_SHA256 = "e" * 64
V2_JOURNAL_FIXTURE = Path("tests/fixtures/b45/request-journal-v2-in-progress.jsonl")


def canonical_test_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def config(*, concurrency: int = 1) -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        concurrency=concurrency,
    )


def prediction(question: str, *, cost: Decimal = Decimal("0.0100")) -> LargeLLMPrediction:
    completion = RemoteCompletion.synthetic(
        raw_text=SAFE_SQL,
        generation_id=f"generation-{hashlib.sha256(question.encode()).hexdigest()[:8]}",
        model_id=config().model_id,
        provider_slug="deepinfra",
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=cost,
        upstream_cost_usd=Decimal("0.0080"),
        latency_ms=12.5,
        system_fingerprint="fp-test",
    )
    return LargeLLMPrediction(
        baseline="b4",
        question=question,
        raw_output=SAFE_SQL,
        sql=SAFE_SQL,
        extraction_status="ok",
        completion=completion,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        prompt_sha256=PROMPT_SHA256,
        config_sha256=config().sha256,
        latency_ms=12.5,
    )


def completed_outcome(
    case_id: str = "case-1",
    question: str = "List addresses",
    *,
    cost: Decimal = Decimal("0.0100"),
    budget_checkpoint: BudgetSnapshot | None = None,
) -> EvaluationOutcome:
    if budget_checkpoint is None:
        budget_checkpoint = BudgetSnapshot(
            cap_usd=Decimal("20.00"),
            spent_usd=cost,
            reserved_usd=Decimal("0"),
            remaining_usd=Decimal("20.00") - cost,
            unresolved_request_ids=(),
            stop_reason="pricing_violation",
        )
    return EvaluationOutcome(
        case_id=case_id,
        question_sha256=hashlib.sha256(question.encode()).hexdigest(),
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("entity_lookup",),
        status="completed",
        prediction=prediction(question, cost=cost),
        safe_error_code=None,
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
        source_synthetic=False,
        source_trusted=True,
        training_accepted=False,
        prompt_sha256=PROMPT_SHA256,
        attempt_count=1,
        budget_checkpoint=budget_checkpoint,
    )


def complete_synthetic_run(
    run_id: str = "run-1", *, cost: Decimal = Decimal("0.0100")
) -> LargeEvaluationRun:
    outcome = completed_outcome(cost=cost)
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
        charged_cost_usd=cost,
        cost_per_1k_queries_usd=cost * Decimal("1000"),
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
        generated_at_utc="2026-09-07T00:00:00Z",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        budget=outcome.budget_checkpoint,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )


def artifact_paths(tmp_path: Path, **overrides: Path) -> artifacts.ArtifactPaths:
    values = {
        "predictions": tmp_path / "predictions.jsonl",
        "request_log": tmp_path / "request.jsonl",
        "cost_csv": tmp_path / "cost.csv",
        "report": tmp_path / "report.json",
        **overrides,
    }
    return artifacts.ArtifactPaths(**values)


def test_publication_writes_report_last_and_rolls_back_every_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = artifact_paths(tmp_path)
    for path in paths.all_outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old\n")
    original = artifacts._atomic_write

    def fail_report(path: Path, payload: bytes) -> None:
        if path == paths.report:
            raise OSError("disk full")
        return original(path, payload)

    monkeypatch.setattr(artifacts, "_atomic_write", fail_report)
    with pytest.raises(LargeLLMError, match="unable to publish"):
        artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    assert all(path.read_bytes() == b"old\n" for path in paths.all_outputs)


def test_resume_rejects_changed_configuration(tmp_path: Path) -> None:
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    with pytest.raises(LargeLLMError, match="config fingerprint"):
        artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256="0" * 64,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )


def test_v2_in_progress_journal_resumes_scheduling_and_preserves_budget(
    tmp_path: Path,
) -> None:
    """Dropping the v2 resume reader would discard already billed durable work."""
    request_log = tmp_path / "request.jsonl"
    request_log.write_bytes(V2_JOURNAL_FIXTURE.read_bytes())
    selected_config = config()
    resume = artifacts.load_resume_state(
        request_log,
        expected_input_sha256=INPUT_SHA256,
        expected_config_sha256=selected_config.sha256,
        expected_run_id="run-v2",
        expected_model_metadata_sha256=METADATA_SHA256,
    )
    assert resume.prior_cost_usd == Decimal("0.01")
    assert resume.unattributed_spend_usd == Decimal("0.01")
    assert resume.budget_checkpoint.spent_usd == Decimal("0.02")
    assert resume.budget_checkpoint.cap_usd == Decimal("20")

    cases = (
        EvaluationCase(
            case_id="case-1",
            question="List addresses",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
            reviewed=True,
            live_verified=True,
            synthetic=False,
        ),
        EvaluationCase(
            case_id="case-2",
            question="List addresses again",
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
            reviewed=True,
            live_verified=True,
            synthetic=False,
        ),
    )
    for case in cases:
        object.__setattr__(case, "_trusted_source", True)

    class ResumedBaseline:
        def __init__(self) -> None:
            self.config = selected_config
            self.budget_ledger = BudgetLedger.from_checkpoint(
                selected_config, resume.budget_checkpoint
            )
            self.evaluation_evidence = LargeBaselineEvidence(
                baseline="b4",
                catalog_sha256=CATALOG_SHA256,
                summary_sha256=SUMMARY_SHA256,
                config_sha256=selected_config.sha256,
                training_sha256=None,
                training_accepted=False,
                model_id=selected_config.model_id,
                provider_slug="deepinfra",
            )
            self.calls: list[str] = []

        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            self.calls.append(request_id)
            reservation = await self.budget_ledger.reserve(
                request_id, (ChatMessage("user", question),)
            )
            assert reservation is not None
            result = prediction(question, cost=Decimal("0.01"))
            await self.budget_ledger.reconcile(reservation, result.completion.charged_cost_usd)
            return result

    journal = artifacts.RequestJournal(
        request_log,
        run_id="run-v2",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=selected_config.sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=selected_config.model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )
    migrated_rows = [json.loads(line) for line in request_log.read_text().splitlines()]
    assert migrated_rows[0]["schema_version"] == 3
    assert [row["record_type"] for row in migrated_rows] == ["header", "outcome"]
    assert "record_sha256" in migrated_rows[1]

    baseline = ResumedBaseline()
    run = asyncio.run(
        evaluate_large_baseline(
            cases,
            baseline,
            run_id="run-v2",
            concurrency=1,
            model_metadata=ModelMetadataEvidence(
                model_id=selected_config.model_id,
                provider_slug="deepinfra",
                context_length=131_072,
                supported_parameters=("max_tokens", "seed", "temperature"),
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
                metadata_sha256=METADATA_SHA256,
            ),
            journal=journal,
            completed_outcomes=resume.completed_outcomes,
            resume_budget_checkpoint=resume.budget_checkpoint,
        )
    )
    assert baseline.calls == ["case-2"]
    assert run.budget.spent_usd == Decimal("0.03")
    assert run.metrics.attributed_spend_usd == Decimal("0.02")
    assert run.metrics.unattributed_spend_usd == Decimal("0.01")
    assert run.metrics.total_spent_usd == Decimal("0.03")


def test_v2_resume_rejects_malformed_outcome_and_terminal_attempt(tmp_path: Path) -> None:
    """A compatibility reader must not broaden the exact terminal-free v2 shape."""
    rows = [json.loads(line) for line in V2_JOURNAL_FIXTURE.read_text().splitlines()]
    malformed = [dict(row) for row in rows]
    malformed[1].pop("budget_checkpoint")
    malformed_path = tmp_path / "malformed.jsonl"
    malformed_path.write_bytes(b"".join(canonical_test_json(row) for row in malformed))
    with pytest.raises(LargeLLMError, match="fields"):
        artifacts.load_resume_state(
            malformed_path,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-v2",
            expected_model_metadata_sha256=METADATA_SHA256,
        )

    identity_drift = [dict(row) for row in rows]
    identity_drift[1]["provider_slug"] = "other"
    identity_path = tmp_path / "identity.jsonl"
    identity_path.write_bytes(b"".join(canonical_test_json(row) for row in identity_drift))
    with pytest.raises(LargeLLMError, match="provider slug mismatch"):
        artifacts.load_resume_state(
            identity_path,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-v2",
            expected_model_metadata_sha256=METADATA_SHA256,
        )

    underfunded = [dict(row) for row in rows]
    underfunded_budget = underfunded[1]["budget_checkpoint"]
    assert isinstance(underfunded_budget, dict)
    underfunded[1]["budget_checkpoint"] = {
        **underfunded_budget,
        "spent_usd": "0",
        "remaining_usd": "20",
    }
    underfunded_path = tmp_path / "underfunded.jsonl"
    underfunded_path.write_bytes(b"".join(canonical_test_json(row) for row in underfunded))
    with pytest.raises(LargeLLMError, match="below accepted outcome costs"):
        artifacts.load_resume_state(
            underfunded_path,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-v2",
            expected_model_metadata_sha256=METADATA_SHA256,
        )
    with pytest.raises(LargeLLMError, match="below accepted outcome costs"):
        artifacts.RequestJournal(
            underfunded_path,
            run_id="run-v2",
            baseline="b4",
            input_sha256=INPUT_SHA256,
            config_sha256=config().sha256,
            catalog_sha256=CATALOG_SHA256,
            summary_sha256=SUMMARY_SHA256,
            training_sha256=None,
            model_id=config().model_id,
            provider_slug="deepinfra",
            model_metadata_sha256=METADATA_SHA256,
        )

    terminal_path = tmp_path / "terminal.jsonl"
    terminal_path.write_bytes(
        V2_JOURNAL_FIXTURE.read_bytes() + canonical_test_json({"record_type": "terminal"})
    )
    with pytest.raises(LargeLLMError, match="schema v2.*terminal"):
        artifacts.load_resume_state(
            terminal_path,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-v2",
            expected_model_metadata_sha256=METADATA_SHA256,
        )


def test_v2_journal_is_never_accepted_as_published_report_evidence(tmp_path: Path) -> None:
    """Allowing v2 in the publication loader would bypass the terminal boundary."""
    paths = artifact_paths(tmp_path)
    run = replace(complete_synthetic_run(), run_id="run-v2")
    paths.report.write_bytes(artifacts.serialize_report(run))
    paths.request_log.write_bytes(V2_JOURNAL_FIXTURE.read_bytes())

    with pytest.raises(LargeLLMError, match="version"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


def test_load_large_run_artifacts_reconstructs_typed_run(tmp_path: Path) -> None:
    """Dropping journal/report identity checks would make this loader unsafe."""
    paths = artifact_paths(tmp_path)
    expected = complete_synthetic_run()
    artifacts.publish_large_run(expected, paths=paths)

    loaded = artifacts.load_large_run_artifacts(paths.report, paths.request_log)

    assert loaded == expected


def test_load_large_run_artifacts_rejects_tampered_report(tmp_path: Path) -> None:
    """Ignoring the report body fingerprint would make this tampering pass."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    payload = json.loads(paths.report.read_text())
    payload["run_id"] = "tampered"
    paths.report.write_bytes(canonical_test_json(payload))

    with pytest.raises(LargeLLMError, match="fingerprint"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stop_reason", None),
    ],
)
def test_load_large_run_artifacts_binds_rehashed_budget_to_final_checkpoint(
    field: str, value: object, tmp_path: Path
) -> None:
    """Trusting a rehashed report budget would hide a journal/checkpoint split."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    payload = json.loads(paths.report.read_text())
    body = {key: item for key, item in payload.items() if key != "report_sha256"}
    body["budget"][field] = value
    payload = {
        **body,
        "report_sha256": hashlib.sha256(canonical_test_json(body)).hexdigest(),
    }
    paths.report.write_bytes(canonical_test_json(payload))

    with pytest.raises(LargeLLMError, match="final durable checkpoint"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


def test_load_large_run_artifacts_rejects_rehashed_unresolved_reservation(
    tmp_path: Path,
) -> None:
    """A report-only unresolved reservation must not replace the durable checkpoint."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    payload = json.loads(paths.report.read_text())
    body = {key: item for key, item in payload.items() if key != "report_sha256"}
    body["budget"].update(
        {
            "reserved_usd": "0.1",
            "remaining_usd": "19.89",
            "unresolved_request_ids": ["lost-request"],
            "unresolved_reservations": [{"request_id": "lost-request", "maximum_cost_usd": "0.1"}],
        }
    )
    payload = {
        **body,
        "report_sha256": hashlib.sha256(canonical_test_json(body)).hexdigest(),
    }
    paths.report.write_bytes(canonical_test_json(payload))

    with pytest.raises(LargeLLMError, match="final durable checkpoint"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


@pytest.mark.parametrize("field", ["unattributed_spend_usd", "total_spent_usd"])
def test_load_large_run_artifacts_rejects_rehashed_derived_totals(
    field: str, tmp_path: Path
) -> None:
    """Top-level report totals must derive from the final journal checkpoint."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    payload = json.loads(paths.report.read_text())
    body = {key: item for key, item in payload.items() if key != "report_sha256"}
    body[field] = "9.99"
    payload = {
        **body,
        "report_sha256": hashlib.sha256(canonical_test_json(body)).hexdigest(),
    }
    paths.report.write_bytes(canonical_test_json(payload))

    with pytest.raises(LargeLLMError, match="totals"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


def test_published_terminal_checkpoint_survives_concurrent_source_sorting_and_resume(
    tmp_path: Path,
) -> None:
    """Inferring the terminal budget from the last source row breaks this run."""
    selected_config = config(concurrency=2)
    cases = (
        EvaluationCase(
            case_id="case-1",
            question="First source case finishes last",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
        ),
        EvaluationCase(
            case_id="case-2",
            question="Last source case finishes first",
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
        ),
    )
    metadata = ModelMetadataEvidence(
        model_id=selected_config.model_id,
        provider_slug="deepinfra",
        context_length=131_072,
        supported_parameters=("max_tokens", "seed", "temperature"),
        prompt_price_per_million_usd=Decimal("0.50"),
        completion_price_per_million_usd=Decimal("1.00"),
        metadata_sha256=METADATA_SHA256,
    )

    class CompletionOrderedBaseline:
        def __init__(self) -> None:
            self.config = selected_config
            self.budget_ledger = BudgetLedger(selected_config)
            self.evaluation_evidence = LargeBaselineEvidence(
                baseline="b4",
                catalog_sha256=CATALOG_SHA256,
                summary_sha256=SUMMARY_SHA256,
                config_sha256=selected_config.sha256,
                training_sha256=None,
                training_accepted=False,
                model_id=selected_config.model_id,
                provider_slug="deepinfra",
            )
            self.case_two_reconciled = asyncio.Event()

        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            reservation = await self.budget_ledger.reserve(
                request_id, (ChatMessage("user", question),)
            )
            assert reservation is not None
            if request_id == "case-1":
                await self.case_two_reconciled.wait()
            await self.budget_ledger.reconcile(reservation, Decimal("0.0001"))
            if request_id == "case-2":
                self.case_two_reconciled.set()
            return replace(
                prediction(question, cost=Decimal("0.0001")),
                config_sha256=selected_config.sha256,
            )

    async def build_run(run_id: str) -> LargeEvaluationRun:
        return await evaluate_large_baseline(
            cases,
            CompletionOrderedBaseline(),
            run_id=run_id,
            concurrency=2,
            model_metadata=metadata,
        )

    loaded_runs = []
    for index in range(1, 4):
        run = asyncio.run(build_run(f"run-{index}"))
        assert [outcome.case_id for outcome in run.outcomes] == ["case-1", "case-2"]
        assert run.outcomes[0].budget_checkpoint.spent_usd == Decimal("0.0002")
        assert run.outcomes[-1].budget_checkpoint.spent_usd == Decimal("0.0001")
        paths = artifact_paths(
            tmp_path,
            predictions=tmp_path / f"predictions-{index}.jsonl",
            request_log=tmp_path / f"request-{index}.jsonl",
            cost_csv=tmp_path / f"cost-{index}.csv",
            report=tmp_path / f"report-{index}.json",
        )
        artifacts.publish_large_run(run, paths=paths)
        rows = [json.loads(line) for line in paths.request_log.read_text().splitlines()]
        assert [row["record_type"] for row in rows] == [
            "header",
            "outcome",
            "outcome",
            "terminal",
        ]
        assert rows[-1]["budget_checkpoint"]["spent_usd"] == "0.0002"
        resume = artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=selected_config.sha256,
            expected_run_id=f"run-{index}",
            expected_model_metadata_sha256=METADATA_SHA256,
        )
        assert resume.completed_case_ids == ("case-1", "case-2")
        assert resume.budget_checkpoint == run.budget
        resumed = CompletionOrderedBaseline()
        resumed.budget_ledger = BudgetLedger.from_checkpoint(
            selected_config, resume.budget_checkpoint
        )
        resumed_run = asyncio.run(
            evaluate_large_baseline(
                cases,
                resumed,
                run_id=f"run-{index}",
                concurrency=2,
                model_metadata=metadata,
                completed_outcomes=resume.completed_outcomes,
                resume_budget_checkpoint=resume.budget_checkpoint,
            )
        )
        assert resumed_run.budget == run.budget
        loaded_runs.append(artifacts.load_large_run_artifacts(paths.report, paths.request_log))

    summary = artifacts.summarize_large_runs(loaded_runs)
    assert summary["run_ids"] == ["run-1", "run-2", "run-3"]
    assert summary["total_spent_usd"] == "0.0006"


def test_self_rehashed_terminal_tampering_fails_closed(tmp_path: Path) -> None:
    """Rehashing a changed terminal must not detach it from its report."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    rows = [json.loads(line) for line in paths.request_log.read_text().splitlines()]
    terminal = rows[-1]
    terminal["budget_checkpoint"]["stop_reason"] = None
    terminal_body = {key: value for key, value in terminal.items() if key != "record_sha256"}
    terminal["record_sha256"] = hashlib.sha256(canonical_test_json(terminal_body)).hexdigest()
    paths.request_log.write_bytes(b"".join(canonical_test_json(row) for row in rows))

    with pytest.raises(LargeLLMError, match="terminal"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


def test_resume_rejects_self_rehashed_terminal_metric_tampering(tmp_path: Path) -> None:
    """A sealed log's terminal metrics must remain derived during resume."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    rows = [json.loads(line) for line in paths.request_log.read_text().splitlines()]
    terminal = rows[-1]
    terminal["metrics"]["p50_latency_ms"] = 99.0
    terminal_body = {key: value for key, value in terminal.items() if key != "record_sha256"}
    terminal["record_sha256"] = hashlib.sha256(canonical_test_json(terminal_body)).hexdigest()
    paths.request_log.write_bytes(b"".join(canonical_test_json(row) for row in rows))

    with pytest.raises(LargeLLMError, match="terminal metrics"):
        artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )


def test_self_rehashed_report_readiness_tampering_fails_closed(tmp_path: Path) -> None:
    """Rehashing changed report claims must still disagree with terminal evidence."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    report = json.loads(paths.report.read_text())
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    body["scientific_ready"] = True
    body["blockers"] = []
    report = {
        **body,
        "report_sha256": hashlib.sha256(canonical_test_json(body)).hexdigest(),
    }
    paths.report.write_bytes(canonical_test_json(report))

    with pytest.raises(LargeLLMError, match="terminal"):
        artifacts.load_large_run_artifacts(paths.report, paths.request_log)


def test_terminal_published_log_rejects_trailing_outcome(tmp_path: Path) -> None:
    """Allowing records after the terminal checkpoint would unseal published evidence."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    rows = [json.loads(line) for line in paths.request_log.read_text().splitlines()]
    trailing = dict(rows[1])
    trailing["case_id"] = "case-2"
    trailing["previous_record_sha256"] = rows[-1]["record_sha256"]
    trailing_body = {key: value for key, value in trailing.items() if key != "record_sha256"}
    trailing["record_sha256"] = hashlib.sha256(canonical_test_json(trailing_body)).hexdigest()
    paths.request_log.write_bytes(b"".join(canonical_test_json(row) for row in (*rows, trailing)))

    with pytest.raises(LargeLLMError, match="terminal"):
        artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )


def test_resume_completed_outcomes_rechecks_returned_record_chain(tmp_path: Path) -> None:
    """Mutating public resume records must invalidate typed reconstruction."""
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    resume = artifacts.load_resume_state(
        paths.request_log,
        expected_input_sha256=INPUT_SHA256,
        expected_config_sha256=config().sha256,
        expected_run_id="run-1",
        expected_model_metadata_sha256=METADATA_SHA256,
    )
    resume.prior_records[0]["gold_sql"] = "SELECT 1"

    with pytest.raises(LargeLLMError, match="fingerprint"):
        _ = resume.completed_outcomes


def test_resume_rejects_changed_model_metadata(tmp_path: Path) -> None:
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    with pytest.raises(LargeLLMError, match="model metadata fingerprint"):
        artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256="0" * 64,
        )


def test_outputs_cannot_alias_inputs_or_each_other(tmp_path: Path) -> None:
    source = tmp_path / "test.jsonl"
    source.write_text("{}\n")
    paths = artifact_paths(tmp_path, predictions=source)
    with pytest.raises(LargeLLMError, match="alias"):
        artifacts.publish_large_run(
            complete_synthetic_run(), paths=paths, protected_paths=(source,)
        )


def test_hard_link_and_symlink_outputs_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "test.jsonl"
    source.write_text("{}\n")
    hard_link = tmp_path / "hard-link.jsonl"
    os.link(source, hard_link)
    with pytest.raises(LargeLLMError, match="alias"):
        artifacts.publish_large_run(
            complete_synthetic_run(),
            paths=artifact_paths(tmp_path, predictions=hard_link),
            protected_paths=(source,),
        )

    symlink = tmp_path / "symlink.jsonl"
    symlink.symlink_to(source)
    with pytest.raises(LargeLLMError, match="alias"):
        artifacts.publish_large_run(
            complete_synthetic_run(),
            paths=artifact_paths(tmp_path, predictions=symlink),
            protected_paths=(source,),
        )


def test_publication_is_canonical_secret_safe_and_preserves_run_evidence(
    tmp_path: Path,
) -> None:
    paths = artifact_paths(tmp_path)
    run = complete_synthetic_run()
    artifacts.publish_large_run(run, paths=paths)

    assert all(path.read_bytes().endswith(b"\n") for path in paths.all_outputs)
    request_bytes = paths.request_log.read_bytes()
    assert b"authorization" not in request_bytes.lower()
    assert b"api_key" not in request_bytes.lower()
    assert b"messages" not in request_bytes.lower()
    assert PROMPT_SHA256.encode() in request_bytes
    request_rows = [json.loads(line) for line in request_bytes.splitlines()]
    assert request_rows[0]["model_metadata_sha256"] == METADATA_SHA256
    assert request_rows[1]["prediction"]["completion"]["synthetic_backend"] is True
    assert request_rows[1]["prediction"]["completion"]["charged_cost_usd"] == "0.01"

    report = json.loads(paths.report.read_text())
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    assert report["report_sha256"] == hashlib.sha256(canonical_test_json(body)).hexdigest()
    assert report["budget"]["stop_reason"] == "pricing_violation"
    assert report["authoritative_total_cost_usd"] == "0.01"
    assert report["scientific_ready"] is False
    assert "synthetic_backend" in report["blockers"]


def test_journal_rejects_duplicate_and_mismatched_outcomes(tmp_path: Path) -> None:
    journal = artifacts.RequestJournal(
        tmp_path / "journal.jsonl",
        run_id="run-1",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )
    journal.append(completed_outcome())
    with pytest.raises(LargeLLMError, match="duplicate"):
        journal.append(completed_outcome())
    drifted = completed_outcome("case-2")
    assert drifted.prediction is not None
    drifted = replace(
        drifted,
        catalog_sha256="0" * 64,
        prediction=replace(drifted.prediction, catalog_sha256="0" * 64),
    )
    with pytest.raises(LargeLLMError, match="catalog fingerprint"):
        journal.append(drifted)


def test_failed_request_journal_row_preserves_prompt_hash(tmp_path: Path) -> None:
    journal = artifacts.RequestJournal(
        tmp_path / "journal.jsonl",
        run_id="run-1",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )
    failed = EvaluationOutcome(
        case_id="case-1",
        question_sha256=hashlib.sha256(b"List addresses").hexdigest(),
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("entity_lookup",),
        status="request_failed",
        prediction=None,
        safe_error_code="rate_limit_exhausted",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
        source_synthetic=False,
        source_trusted=True,
        training_accepted=False,
        prompt_sha256=PROMPT_SHA256,
        attempt_count=3,
        budget_checkpoint=BudgetSnapshot(
            cap_usd=Decimal("20.00"),
            spent_usd=Decimal("0"),
            reserved_usd=Decimal("0.0005"),
            remaining_usd=Decimal("19.9995"),
            unresolved_request_ids=("case-1",),
            unresolved_reservations=(BudgetReservation("case-1", Decimal("0.0005")),),
        ),
    )

    journal.append(failed)

    row = json.loads((tmp_path / "journal.jsonl").read_text().splitlines()[1])
    assert row["prompt_sha256"] == PROMPT_SHA256
    assert row["attempt_count"] == 3
    assert "messages" not in row


def test_resume_rejects_non_outcome_journal_rows(tmp_path: Path) -> None:
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    lines = paths.request_log.read_text(encoding="utf-8").splitlines()
    outcome = json.loads(lines[1])
    outcome["record_type"] = "checkpoint"
    lines[1] = json.dumps(outcome, sort_keys=True, separators=(",", ":"))
    paths.request_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(LargeLLMError, match="record type"):
        artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )


def test_resume_state_returns_rehydratable_budget_checkpoint(tmp_path: Path) -> None:
    journal = artifacts.RequestJournal(
        tmp_path / "journal.jsonl",
        run_id="run-1",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )
    spent_checkpoint = BudgetSnapshot(
        cap_usd=Decimal("20.00"),
        spent_usd=Decimal("19.9990"),
        reserved_usd=Decimal("0"),
        remaining_usd=Decimal("0.0010"),
        unresolved_request_ids=(),
    )
    journal.append(
        completed_outcome(
            cost=Decimal("19.9990"),
            budget_checkpoint=spent_checkpoint,
        )
    )
    held_checkpoint = BudgetSnapshot(
        cap_usd=Decimal("20.00"),
        spent_usd=Decimal("19.9990"),
        reserved_usd=Decimal("0.0005"),
        remaining_usd=Decimal("0.0005"),
        unresolved_request_ids=("case-2",),
        unresolved_reservations=(BudgetReservation("case-2", Decimal("0.0005")),),
    )
    journal.append(
        EvaluationOutcome(
            case_id="case-2",
            question_sha256=hashlib.sha256(b"List addresses again").hexdigest(),
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup",),
            status="request_failed",
            prediction=None,
            safe_error_code="rate_limit_exhausted",
            baseline="b4",
            input_sha256=INPUT_SHA256,
            config_sha256=config().sha256,
            catalog_sha256=CATALOG_SHA256,
            summary_sha256=SUMMARY_SHA256,
            training_sha256=None,
            model_id=config().model_id,
            provider_slug="deepinfra",
            model_metadata_sha256=METADATA_SHA256,
            source_synthetic=False,
            source_trusted=True,
            training_accepted=False,
            prompt_sha256=PROMPT_SHA256,
            attempt_count=3,
            budget_checkpoint=held_checkpoint,
        )
    )

    resume = artifacts.load_resume_state(
        tmp_path / "journal.jsonl",
        expected_input_sha256=INPUT_SHA256,
        expected_config_sha256=config().sha256,
        expected_run_id="run-1",
        expected_model_metadata_sha256=METADATA_SHA256,
    )

    assert resume.prior_cost_usd == Decimal("19.999")
    assert resume.budget_checkpoint == held_checkpoint
    ledger = BudgetLedger.from_checkpoint(config(), resume.budget_checkpoint)
    assert asyncio.run(ledger.reserve("case-3", (ChatMessage("user", "x"),))) is None


def test_resume_accepts_unrecorded_inflight_reservation_checkpoint(tmp_path: Path) -> None:
    journal = artifacts.RequestJournal(
        tmp_path / "journal.jsonl",
        run_id="run-1",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )
    checkpoint = BudgetSnapshot(
        cap_usd=Decimal("20.00"),
        spent_usd=Decimal("19.9990"),
        reserved_usd=Decimal("0.0005"),
        remaining_usd=Decimal("0.0005"),
        unresolved_request_ids=("case-2",),
        unresolved_reservations=(BudgetReservation("case-2", Decimal("0.0005")),),
    )
    journal.append(
        completed_outcome(
            cost=Decimal("19.9990"),
            budget_checkpoint=checkpoint,
        )
    )

    resume = artifacts.load_resume_state(
        tmp_path / "journal.jsonl",
        expected_input_sha256=INPUT_SHA256,
        expected_config_sha256=config().sha256,
        expected_run_id="run-1",
        expected_model_metadata_sha256=METADATA_SHA256,
    )

    assert resume.completed_case_ids == ("case-1",)
    assert resume.unresolved_request_ids == ("case-2",)
    ledger = BudgetLedger.from_checkpoint(config(), resume.budget_checkpoint)
    assert asyncio.run(ledger.reserve("case-3", (ChatMessage("user", "x"),))) is None


def test_resume_preserves_unattributed_concurrent_spend_and_schedules_missing_case(
    tmp_path: Path,
) -> None:
    limited_config = replace(
        config(concurrency=2),
        provider=replace(
            config().provider,
            prompt_price_per_million_usd=Decimal("0"),
            completion_price_per_million_usd=Decimal("19.53125"),
        ),
        max_cost_usd=Decimal("0.0300"),
    )
    cases = (
        EvaluationCase(
            case_id="case-1",
            question="List addresses",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
            reviewed=True,
            live_verified=True,
            synthetic=False,
        ),
        EvaluationCase(
            case_id="case-2",
            question="List addresses again",
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
            reviewed=True,
            live_verified=True,
            synthetic=False,
        ),
    )
    for case in cases:
        object.__setattr__(case, "_trusted_source", True)

    def configured_prediction(question: str) -> LargeLLMPrediction:
        return replace(
            prediction(question, cost=Decimal("0.0100")), config_sha256=limited_config.sha256
        )

    metadata = ModelMetadataEvidence(
        model_id=limited_config.model_id,
        provider_slug="deepinfra",
        context_length=131_072,
        supported_parameters=("max_tokens", "seed", "temperature"),
        prompt_price_per_million_usd=Decimal("0"),
        completion_price_per_million_usd=Decimal("19.53125"),
        metadata_sha256=METADATA_SHA256,
    )

    class InterleavingBaseline:
        def __init__(self) -> None:
            self.config = limited_config
            self.budget_ledger = BudgetLedger(self.config)
            self.evaluation_evidence = LargeBaselineEvidence(
                baseline="b4",
                catalog_sha256=CATALOG_SHA256,
                summary_sha256=SUMMARY_SHA256,
                config_sha256=self.config.sha256,
                training_sha256=None,
                training_accepted=False,
                model_id=self.config.model_id,
                provider_slug="deepinfra",
            )
            self.calls: list[str] = []
            self.first_reconciled = asyncio.Event()
            self.second_reconciled = asyncio.Event()
            self.first_journaled = asyncio.Event()

        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            self.calls.append(request_id)
            if request_id == "case-1":
                reservation = await self.budget_ledger.reserve(
                    request_id, (ChatMessage("user", question),)
                )
                assert reservation is not None
                await self.budget_ledger.reconcile(reservation, Decimal("0.0100"))
                self.first_reconciled.set()
                await self.second_reconciled.wait()
                return configured_prediction(question)

            await self.first_reconciled.wait()
            reservation = await self.budget_ledger.reserve(
                request_id, (ChatMessage("user", question),)
            )
            assert reservation is not None
            await self.budget_ledger.reconcile(reservation, Decimal("0.0100"))
            self.second_reconciled.set()
            await self.first_journaled.wait()
            return configured_prediction(question)

    async def scenario() -> None:
        baseline = InterleavingBaseline()
        journal = artifacts.RequestJournal(
            tmp_path / "journal.jsonl",
            run_id="run-1",
            baseline="b4",
            input_sha256=INPUT_SHA256,
            config_sha256=limited_config.sha256,
            catalog_sha256=CATALOG_SHA256,
            summary_sha256=SUMMARY_SHA256,
            training_sha256=None,
            model_id=limited_config.model_id,
            provider_slug="deepinfra",
            model_metadata_sha256=METADATA_SHA256,
        )

        class CrashJournal:
            def append(self, outcome: EvaluationOutcome) -> None:
                if outcome.case_id == "case-1":
                    journal.append(outcome)
                    baseline.first_journaled.set()
                    return
                raise RuntimeError("simulated interruption before second journal append")

        with pytest.raises(RuntimeError, match="simulated interruption"):
            await evaluate_large_baseline(
                cases,
                baseline,
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata,
                journal=CrashJournal(),
            )

        assert baseline.calls == ["case-1", "case-2"]
        journal_lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(journal_lines) == 2
        persisted = json.loads(journal_lines[1])
        assert persisted["case_id"] == "case-1"
        assert persisted["budget_checkpoint"]["spent_usd"] == "0.02"

        resume = artifacts.load_resume_state(
            tmp_path / "journal.jsonl",
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=limited_config.sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )
        checkpoint = resume.budget_checkpoint
        assert resume.prior_cost_usd == Decimal("0.0100")
        assert resume.attributed_spend_usd == Decimal("0.0100")
        assert resume.unattributed_spend_usd == Decimal("0.0100")
        assert resume.total_spent_usd == Decimal("0.0200")
        assert checkpoint.cap_usd == Decimal("0.0300")
        assert checkpoint.spent_usd == Decimal("0.0200")
        assert checkpoint.reserved_usd == Decimal("0")
        assert checkpoint.remaining_usd == Decimal("0.0100")
        assert checkpoint.unresolved_request_ids == ()
        assert checkpoint.unresolved_reservations == ()
        assert checkpoint.stop_reason is None

        rehydrated = BudgetLedger.from_checkpoint(limited_config, checkpoint)
        assert await rehydrated.snapshot() == checkpoint

        class ResumedBaseline:
            def __init__(self) -> None:
                self.config = limited_config
                self.budget_ledger = BudgetLedger.from_checkpoint(self.config, checkpoint)
                self.evaluation_evidence = LargeBaselineEvidence(
                    baseline="b4",
                    catalog_sha256=CATALOG_SHA256,
                    summary_sha256=SUMMARY_SHA256,
                    config_sha256=self.config.sha256,
                    training_sha256=None,
                    training_accepted=False,
                    model_id=self.config.model_id,
                    provider_slug="deepinfra",
                )
                self.calls: list[str] = []

            async def predict_detailed(
                self, question: str, *, request_id: str
            ) -> LargeLLMPrediction:
                self.calls.append(request_id)
                result = configured_prediction(question)
                reservation = await self.budget_ledger.reserve(
                    request_id, (ChatMessage("user", question),)
                )
                assert reservation is not None
                await self.budget_ledger.reconcile(reservation, result.completion.charged_cost_usd)
                return result

        resumed = ResumedBaseline()
        run = await evaluate_large_baseline(
            cases,
            resumed,
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata,
            completed_outcomes=resume.completed_outcomes,
        )
        assert resumed.calls == ["case-2"]
        assert run.budget.cap_usd == Decimal("0.0300")
        assert run.budget.spent_usd == Decimal("0.0300")
        assert run.budget.remaining_usd == Decimal("0")
        assert run.metrics.attributed_spend_usd == Decimal("0.0200")
        assert run.metrics.unattributed_spend_usd == Decimal("0.0100")
        assert run.metrics.total_spent_usd == Decimal("0.0300")
        assert "unattributed_spend" in run.blockers

        paths = artifact_paths(tmp_path)
        artifacts.publish_large_run(run, paths=paths)
        report = json.loads(paths.report.read_text(encoding="utf-8"))
        assert report["attributed_spend_usd"] == "0.02"
        assert report["unattributed_spend_usd"] == "0.01"
        assert report["total_spent_usd"] == "0.03"
        assert "unattributed_spend_usd" in paths.cost_csv.read_text(encoding="utf-8")

    asyncio.run(scenario())


def test_publication_rejects_tampered_metrics_readiness_and_blockers(
    tmp_path: Path,
) -> None:
    paths = artifact_paths(tmp_path)
    run = complete_synthetic_run()
    object.__setattr__(run.metrics, "charged_cost_usd", Decimal("0"))
    object.__setattr__(run, "scientific_ready", True)
    object.__setattr__(run, "blockers", ())

    with pytest.raises(LargeLLMError, match="derived"):
        artifacts.publish_large_run(run, paths=paths)


def test_publication_rejects_tampered_budget_snapshot(tmp_path: Path) -> None:
    paths = artifact_paths(tmp_path)
    run = complete_synthetic_run()
    object.__setattr__(run.budget, "remaining_usd", Decimal("0"))

    with pytest.raises(LargeLLMError, match="derived"):
        artifacts.publish_large_run(run, paths=paths)


def test_interruption_resumes_without_scheduling_the_accepted_case(tmp_path: Path) -> None:
    cases = (
        EvaluationCase(
            case_id="case-1",
            question="List addresses",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
        ),
        EvaluationCase(
            case_id="case-2",
            question="List addresses again",
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
        ),
    )

    class Baseline:
        def __init__(self, *, block_case_two: bool = False) -> None:
            self.config = config()
            self.budget_ledger = BudgetLedger(self.config)
            self.evaluation_evidence = LargeBaselineEvidence(
                baseline="b4",
                catalog_sha256=CATALOG_SHA256,
                summary_sha256=SUMMARY_SHA256,
                config_sha256=self.config.sha256,
                training_sha256=None,
                training_accepted=False,
                model_id=self.config.model_id,
                provider_slug="deepinfra",
            )
            self.calls: list[str] = []
            self.block_case_two = block_case_two

        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            if self.block_case_two and request_id == "case-2":
                await asyncio.sleep(60)
            result = prediction(question, cost=Decimal("0.0001"))
            reservation = await self.budget_ledger.reserve(
                request_id, (ChatMessage("user", question),)
            )
            assert reservation is not None
            await self.budget_ledger.reconcile(reservation, result.completion.charged_cost_usd)
            self.calls.append(request_id)
            return result

    metadata = ModelMetadataEvidence(
        model_id=config().model_id,
        provider_slug="deepinfra",
        context_length=131_072,
        supported_parameters=("max_tokens", "seed", "temperature"),
        prompt_price_per_million_usd=Decimal("0.50"),
        completion_price_per_million_usd=Decimal("1.00"),
        metadata_sha256=METADATA_SHA256,
    )
    durable = artifacts.RequestJournal(
        tmp_path / "journal.jsonl",
        run_id="run-1",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )

    class InterruptAfterFirst:
        def append(self, outcome: EvaluationOutcome) -> None:
            durable.append(outcome)
            raise RuntimeError("interrupted")

    async def scenario() -> None:
        first = Baseline(block_case_two=True)
        with pytest.raises(RuntimeError, match="interrupted"):
            await evaluate_large_baseline(
                cases,
                first,
                run_id="run-1",
                concurrency=1,
                model_metadata=metadata,
                journal=InterruptAfterFirst(),
            )
        assert first.calls == ["case-1"]

        resume = artifacts.load_resume_state(
            tmp_path / "journal.jsonl",
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )
        second = Baseline()
        second.budget_ledger = BudgetLedger.from_checkpoint(second.config, resume.budget_checkpoint)
        run = await evaluate_large_baseline(
            cases,
            second,
            run_id="run-1",
            concurrency=1,
            model_metadata=metadata,
            completed_outcomes=resume.completed_outcomes,
        )
        assert resume.completed_case_ids == ("case-1",)
        assert resume.prior_cost_usd == Decimal("0.0001")
        assert second.calls == ["case-2"]
        assert [outcome.case_id for outcome in run.outcomes] == ["case-1", "case-2"]

    asyncio.run(scenario())


def test_billed_malformed_live_response_publishes_and_resumes_exact_spend(
    tmp_path: Path,
) -> None:
    cases = (
        EvaluationCase(
            case_id="case-1",
            question="List addresses",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
            input_sha256=INPUT_SHA256,
        ),
    )
    malformed_response = SimpleNamespace(
        id="gen-malformed",
        model=config().model_id,
        provider="deepinfra",
        system_fingerprint="fp-test",
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            cost="0.0100",
            cost_details=SimpleNamespace(upstream_inference_cost="0.0080"),
        ),
    )

    class FakeCompletions:
        async def create(self, **_kwargs: object) -> object:
            return malformed_response

    class LiveFailureBaseline:
        def __init__(self) -> None:
            self.config = config()
            self.budget_ledger = BudgetLedger(self.config)
            self.evaluation_evidence = LargeBaselineEvidence(
                baseline="b4",
                catalog_sha256=CATALOG_SHA256,
                summary_sha256=SUMMARY_SHA256,
                config_sha256=self.config.sha256,
                training_sha256=None,
                training_accepted=False,
                model_id=self.config.model_id,
                provider_slug="deepinfra",
            )
            sdk = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
            self.transport = OpenRouterTransport(
                sdk=sdk,
                ledger=self.budget_ledger,
                clock_ns=iter([0, 1_000_000]).__next__,
            )
            self.calls: list[str] = []

        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            self.calls.append(request_id)
            await self.transport.complete(
                (ChatMessage("user", question),), self.config, request_id=request_id
            )
            raise AssertionError("malformed response unexpectedly produced a prediction")

    paths = artifact_paths(tmp_path)
    journal = artifacts.RequestJournal(
        paths.request_log,
        run_id="run-1",
        baseline="b4",
        input_sha256=INPUT_SHA256,
        config_sha256=config().sha256,
        catalog_sha256=CATALOG_SHA256,
        summary_sha256=SUMMARY_SHA256,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256=METADATA_SHA256,
    )

    async def scenario() -> None:
        baseline = LiveFailureBaseline()
        run = await evaluate_large_baseline(
            cases,
            baseline,
            run_id="run-1",
            concurrency=1,
            model_metadata=ModelMetadataEvidence(
                model_id=config().model_id,
                provider_slug="deepinfra",
                context_length=131_072,
                supported_parameters=("max_tokens", "seed", "temperature"),
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
                metadata_sha256=METADATA_SHA256,
            ),
            journal=journal,
        )
        assert run.outcomes[0].status == "request_failed"
        assert run.outcomes[0].authoritative_cost_usd == Decimal("0.0100")
        assert run.metrics.charged_cost_usd == Decimal("0.0100")
        assert run.budget.spent_usd == Decimal("0.0100")

        artifacts.publish_large_run(run, paths=paths)
        row = json.loads(paths.request_log.read_text(encoding="utf-8").splitlines()[1])
        assert row["authoritative_cost_usd"] == "0.01"
        assert (
            b"request,b4,run-1,case-1,request_failed,,,,0.01,,0.01,,\n"
            in paths.cost_csv.read_bytes()
        )
        assert (
            json.loads(paths.report.read_text(encoding="utf-8"))["authoritative_total_cost_usd"]
            == "0.01"
        )
        resume = artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256=INPUT_SHA256,
            expected_config_sha256=config().sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=METADATA_SHA256,
        )
        assert resume.prior_cost_usd == Decimal("0.0100")
        assert resume.budget_checkpoint.spent_usd == Decimal("0.0100")

        resumed = LiveFailureBaseline()
        resumed.budget_ledger = BudgetLedger.from_checkpoint(
            resumed.config, resume.budget_checkpoint
        )
        resumed_run = await evaluate_large_baseline(
            cases,
            resumed,
            run_id="run-1",
            concurrency=1,
            model_metadata=ModelMetadataEvidence(
                model_id=config().model_id,
                provider_slug="deepinfra",
                context_length=131_072,
                supported_parameters=("max_tokens", "seed", "temperature"),
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
                metadata_sha256=METADATA_SHA256,
            ),
            completed_outcomes=resume.completed_outcomes,
        )
        assert resumed.calls == []
        assert resumed_run.budget.spent_usd == Decimal("0.0100")
        assert resumed_run.metrics.charged_cost_usd == Decimal("0.0100")

    asyncio.run(scenario())


def test_summarize_three_runs_keeps_synthetic_evidence_blocking() -> None:
    summary = artifacts.summarize_large_runs(
        tuple(complete_synthetic_run(f"run-{index}") for index in range(1, 4))
    )
    assert summary["scientific_ready"] is False
    assert summary["blockers"] == [
        "expected_100_cases",
        "pricing_violation",
        "synthetic_backend",
    ]
    assert summary["authoritative_total_cost_usd"] == "0.03"
    assert summary["reproducibility"]["run_count"] == 3
