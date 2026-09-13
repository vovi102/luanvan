from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from decimal import Decimal

import pytest

import nl2sparql.models.b45.evaluate as evaluate_module
from nl2sparql.models.b12 import EvaluationCase
from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import (
    BudgetLedger,
    LargeLLMConfig,
    LocalVerificationEvidence,
    ProviderPolicy,
)
from nl2sparql.models.b45.budget import BudgetReservation, BudgetSnapshot
from nl2sparql.models.b45.contracts import (
    LargeBaselineEvidence,
    LargeLLMPrediction,
    RemoteCompletion,
)
from nl2sparql.models.b45.evaluate import (
    EvaluationOutcome,
    LargeEvaluationMetrics,
    LargeEvaluationRun,
    compare_large_reproducibility,
    evaluate_large_baseline,
)
from nl2sparql.models.b45.openrouter import ModelMetadataEvidence, OpenRouterRequestError

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


def config(*, concurrency: int = 2) -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        concurrency=concurrency,
    )


def two_synthetic_cases() -> tuple[EvaluationCase, ...]:
    return (
        EvaluationCase(
            case_id="case-1",
            question="List known addresses",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("entity_lookup",),
        ),
        EvaluationCase(
            case_id="case-2",
            question="List known addresses again",
            gold_sql=SAFE_SQL,
            difficulty="medium",
            categories=("entity_lookup", "ranking"),
        ),
    )


def prediction_for(
    question: str,
    *,
    raw_sql: str = SAFE_SQL,
    latency_ms: float = 1.0,
    cost: Decimal = Decimal("0"),
    provider_slug: str = "deepinfra",
) -> LargeLLMPrediction:
    completion = RemoteCompletion.synthetic(
        raw_text=raw_sql,
        model_id="meta-llama/llama-3.3-70b-instruct",
        provider_slug=provider_slug,
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=cost,
        latency_ms=latency_ms,
    )
    return LargeLLMPrediction(
        baseline="b4",
        question=question,
        raw_output=raw_sql,
        sql=raw_sql,
        extraction_status="ok",
        completion=completion,
        catalog_sha256="a" * 64,
        summary_sha256="b" * 64,
        prompt_sha256="c" * 64,
        config_sha256=config().sha256,
        latency_ms=latency_ms,
    )


class DelayedBaseline:
    def __init__(self, delays: dict[str, float]) -> None:
        self.config = config()
        self.budget_ledger = BudgetLedger(self.config)
        self.evaluation_evidence = LargeBaselineEvidence(
            baseline="b4",
            catalog_sha256="a" * 64,
            summary_sha256="b" * 64,
            config_sha256=self.config.sha256,
            training_sha256=None,
            training_accepted=False,
            model_id=self.config.model_id,
            provider_slug=self.config.provider.provider_slug,
        )
        self.delays = delays
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls: list[str] = []
        self.cancelled: list[str] = []

    async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
        self.calls.append(request_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delays[request_id])
            return prediction_for(question)
        except asyncio.CancelledError:
            self.cancelled.append(request_id)
            raise
        finally:
            self.in_flight -= 1


class FailingSecondBaseline(DelayedBaseline):
    def __init__(self) -> None:
        super().__init__({"case-1": 0.0, "case-2": 0.0})

    async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
        if request_id == "case-2":
            raise OpenRouterRequestError(
                "rate_limit_exhausted",
                attempt_count=3,
                prompt_sha256="c" * 64,
            )
        return await super().predict_detailed(question, request_id=request_id)


def metadata() -> ModelMetadataEvidence:
    selected = config()
    return ModelMetadataEvidence(
        model_id=selected.model_id,
        provider_slug=selected.provider.provider_slug,
        context_length=131_072,
        supported_parameters=("max_tokens", "seed", "temperature"),
        prompt_price_per_million_usd=selected.provider.prompt_price_per_million_usd,
        completion_price_per_million_usd=(selected.provider.completion_price_per_million_usd),
        metadata_sha256="e" * 64,
    )


def outcome_identity(question: str, *, input_sha256: str | None = None) -> dict[str, object]:
    selected = config()
    return {
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "baseline": "b4",
        "input_sha256": input_sha256,
        "config_sha256": selected.sha256,
        "catalog_sha256": "a" * 64,
        "summary_sha256": "b" * 64,
        "training_sha256": None,
        "model_id": selected.model_id,
        "provider_slug": selected.provider.provider_slug,
    }


def budget_checkpoint(
    *,
    spent_usd: Decimal = Decimal("0"),
    reserved_usd: Decimal = Decimal("0"),
    unresolved_reservations: tuple[BudgetReservation, ...] = (),
    stop_reason: str | None = None,
) -> BudgetSnapshot:
    return BudgetSnapshot(
        cap_usd=Decimal("20.00"),
        spent_usd=spent_usd,
        reserved_usd=reserved_usd,
        remaining_usd=Decimal("20.00") - spent_usd - reserved_usd,
        unresolved_request_ids=tuple(
            reservation.request_id for reservation in unresolved_reservations
        ),
        stop_reason=stop_reason,
        unresolved_reservations=unresolved_reservations,
    )


def test_evaluation_preserves_case_order_under_concurrency() -> None:
    async def scenario() -> None:
        baseline = DelayedBaseline(delays={"case-1": 0.02, "case-2": 0.0})
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            baseline,
            run_id="run-1",
            concurrency=2,
            model_metadata=None,
        )
        assert [item.case_id for item in run.outcomes] == ["case-1", "case-2"]
        assert baseline.max_in_flight == 2
        assert run.scientific_ready is False
        assert "synthetic_backend" in run.blockers
        assert "synthetic_test_set" in run.blockers
        assert "missing_model_metadata" in run.blockers

    asyncio.run(scenario())


def test_heterogeneous_input_fingerprints_return_a_blocked_ordered_run() -> None:
    class Journal:
        def __init__(self) -> None:
            self.outcomes: list[EvaluationOutcome] = []

        def append(self, outcome: EvaluationOutcome) -> None:
            self.outcomes.append(outcome)

    async def scenario() -> None:
        first, second = two_synthetic_cases()
        cases = (
            replace(first, input_sha256="1" * 64),
            replace(second, input_sha256="2" * 64),
        )
        journal = Journal()
        run = await evaluate_large_baseline(
            cases,
            DelayedBaseline({"case-1": 0.0, "case-2": 0.0}),
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
            journal=journal,
        )

        assert run.input_sha256 is None
        assert "trusted_test_set_provenance_missing" in run.blockers
        assert [outcome.case_id for outcome in run.outcomes] == ["case-1", "case-2"]
        assert {outcome.input_sha256 for outcome in run.outcomes} == {"1" * 64, "2" * 64}
        assert len(journal.outcomes) == 2

    asyncio.run(scenario())


def test_request_failure_is_an_outcome_not_a_lost_case() -> None:
    async def scenario() -> None:
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            FailingSecondBaseline(),
            run_id="run-1",
            concurrency=2,
            model_metadata=None,
        )
        assert len(run.outcomes) == 2
        assert run.outcomes[1].status == "request_failed"
        assert run.outcomes[1].safe_error_code == "rate_limit_exhausted"
        assert (
            run.outcomes[1].question_sha256
            == hashlib.sha256(b"List known addresses again").hexdigest()
        )
        assert run.outcomes[1].baseline == "b4"
        assert run.outcomes[1].catalog_sha256 == "a" * 64
        assert run.outcomes[1].model_id == config().model_id
        assert run.outcomes[1].provider_slug == "deepinfra"
        assert run.metrics.request_failed == 1
        assert "incomplete_generation" in run.blockers

    asyncio.run(scenario())


def test_resumed_failure_must_match_source_question_identity() -> None:
    async def scenario() -> None:
        original_case = two_synthetic_cases()[1]
        first = await evaluate_large_baseline(
            (original_case,),
            FailingSecondBaseline(),
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
        )
        changed_case = EvaluationCase(
            case_id=original_case.case_id,
            question="A changed source question",
            gold_sql=original_case.gold_sql,
            difficulty=original_case.difficulty,
            categories=original_case.categories,
        )
        with pytest.raises(ValueError, match="source case"):
            await evaluate_large_baseline(
                (changed_case,),
                FailingSecondBaseline(),
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
                completed_outcomes=(first.outcomes[0],),
            )

    asyncio.run(scenario())


def test_metrics_use_exact_prediction_accounting_and_sorted_counts() -> None:
    class AccountingBaseline(DelayedBaseline):
        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            values = {
                "case-1": (10.0, Decimal("0.0001")),
                "case-2": (30.0, Decimal("0.0002")),
            }
            latency, cost = values[request_id]
            reservation = await self.budget_ledger.reserve(
                request_id, (ChatMessage("user", question),)
            )
            assert reservation is not None
            await self.budget_ledger.reconcile(reservation, cost)
            return prediction_for(question, latency_ms=latency, cost=cost)

    async def scenario() -> None:
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            AccountingBaseline({"case-1": 0.0, "case-2": 0.0}),
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
        )
        assert run.metrics.completed == 2
        assert run.metrics.p50_latency_ms == 20.0
        assert run.metrics.p95_latency_ms == pytest.approx(29.0)
        assert run.metrics.input_tokens == 20
        assert run.metrics.output_tokens == 10
        assert run.metrics.charged_cost_usd == Decimal("0.0003")
        assert tuple(outcome.authoritative_cost_usd for outcome in run.outcomes) == (
            Decimal("0.0001"),
            Decimal("0.0002"),
        )
        assert run.metrics.cost_per_1k_queries_usd == Decimal("0.15")
        assert run.metrics.extraction_status_counts == (("ok", 2),)
        assert run.metrics.difficulty_counts == (("easy", 1), ("medium", 1))
        assert run.metrics.category_counts == (("entity_lookup", 2), ("ranking", 1))

    asyncio.run(scenario())


def test_synthetic_provider_drift_is_a_blocker_not_an_evaluation_crash() -> None:
    class DriftedProviderBaseline(DelayedBaseline):
        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            return prediction_for(question, provider_slug="scripted")

    async def scenario() -> None:
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            DriftedProviderBaseline({"case-1": 0.0, "case-2": 0.0}),
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
        )

        assert "provider_drift" in run.blockers

    asyncio.run(scenario())


def test_pricing_violation_blocker_comes_from_public_budget_checkpoint() -> None:
    class SnapshotOnlyLedger(BudgetLedger):
        async def snapshot(self) -> BudgetSnapshot:
            return BudgetSnapshot(
                cap_usd=Decimal("20"),
                spent_usd=Decimal("0"),
                reserved_usd=Decimal("0"),
                remaining_usd=Decimal("20"),
                unresolved_request_ids=(),
                stop_reason="pricing_violation",
            )

    async def scenario() -> None:
        baseline = DelayedBaseline({"case-1": 0.0, "case-2": 0.0})
        baseline.budget_ledger = SnapshotOnlyLedger(baseline.config)
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            baseline,
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
        )

        assert "pricing_violation" in run.blockers

    asyncio.run(scenario())


def test_completed_outcome_is_validated_and_not_scheduled() -> None:
    async def scenario() -> None:
        cases = two_synthetic_cases()
        completed = EvaluationOutcome(
            case_id="case-1",
            **outcome_identity(cases[0].question),
            gold_sql=cases[0].gold_sql,
            difficulty=cases[0].difficulty,
            categories=cases[0].categories,
            status="completed",
            prediction=prediction_for(cases[0].question),
            safe_error_code=None,
            model_metadata_sha256=metadata().metadata_sha256,
            source_synthetic=cases[0].synthetic,
            source_trusted=cases[0]._trusted_source,
            training_accepted=False,
            prompt_sha256="c" * 64,
            attempt_count=1,
            budget_checkpoint=budget_checkpoint(),
        )
        baseline = DelayedBaseline({"case-2": 0.0})
        run = await evaluate_large_baseline(
            cases,
            baseline,
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
            completed_outcomes=(completed,),
        )
        assert baseline.calls == ["case-2"]
        assert run.outcomes[0] is completed

        stale = EvaluationOutcome(
            case_id="case-1",
            **outcome_identity(cases[0].question),
            gold_sql="SELECT 1",
            difficulty="easy",
            categories=("entity_lookup",),
            status="completed",
            prediction=prediction_for(cases[0].question),
            safe_error_code=None,
            model_metadata_sha256=metadata().metadata_sha256,
            source_synthetic=cases[0].synthetic,
            source_trusted=cases[0]._trusted_source,
            training_accepted=False,
            prompt_sha256="c" * 64,
            attempt_count=1,
            budget_checkpoint=budget_checkpoint(),
        )
        with pytest.raises(ValueError, match="source case"):
            await evaluate_large_baseline(
                cases,
                DelayedBaseline({"case-2": 0.0}),
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
                completed_outcomes=(stale,),
            )

    asyncio.run(scenario())


def test_resume_requires_rehydrated_budget_before_scheduling() -> None:
    class BudgetAwareBaseline(DelayedBaseline):
        async def predict_detailed(self, question: str, *, request_id: str) -> LargeLLMPrediction:
            reservation = await self.budget_ledger.reserve(
                request_id, (ChatMessage("user", question),)
            )
            if reservation is None:
                raise OpenRouterRequestError(
                    "budget_blocked",
                    attempt_count=0,
                    prompt_sha256="c" * 64,
                )
            self.calls.append(request_id)
            return prediction_for(question)

    async def scenario() -> None:
        cases = two_synthetic_cases()
        prior_checkpoint = BudgetSnapshot(
            cap_usd=config().max_cost_usd,
            spent_usd=Decimal("19.9990"),
            reserved_usd=Decimal("0.0005"),
            remaining_usd=Decimal("0.0005"),
            unresolved_request_ids=("case-x",),
            unresolved_reservations=(BudgetReservation("case-x", Decimal("0.0005")),),
        )
        completed = EvaluationOutcome(
            case_id="case-1",
            **outcome_identity(cases[0].question),
            gold_sql=cases[0].gold_sql,
            difficulty=cases[0].difficulty,
            categories=cases[0].categories,
            status="completed",
            prediction=prediction_for(cases[0].question, cost=Decimal("19.9990")),
            safe_error_code=None,
            model_metadata_sha256=metadata().metadata_sha256,
            source_synthetic=cases[0].synthetic,
            source_trusted=cases[0]._trusted_source,
            training_accepted=False,
            prompt_sha256="c" * 64,
            attempt_count=1,
            budget_checkpoint=prior_checkpoint,
        )

        stale_budget = BudgetAwareBaseline({"case-2": 0.0})
        with pytest.raises(ValueError, match="budget checkpoint"):
            await evaluate_large_baseline(
                cases,
                stale_budget,
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
                completed_outcomes=(completed,),
            )
        assert stale_budget.calls == []

        resumed = BudgetAwareBaseline({"case-2": 0.0})
        resumed.budget_ledger = BudgetLedger.from_checkpoint(resumed.config, prior_checkpoint)
        run = await evaluate_large_baseline(
            cases,
            resumed,
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
            completed_outcomes=(completed,),
        )
        assert resumed.calls == []
        assert run.outcomes[1].status == "budget_blocked"
        assert run.budget == prior_checkpoint

    asyncio.run(scenario())


def test_journal_receives_completion_order_and_failure_cancels_other_work() -> None:
    class Journal:
        def __init__(self, *, fail_on: str | None = None) -> None:
            self.ids: list[str] = []
            self.fail_on = fail_on

        def append(self, outcome: EvaluationOutcome) -> None:
            self.ids.append(outcome.case_id)
            if outcome.case_id == self.fail_on:
                raise OSError("disk details must not be swallowed")

    async def scenario() -> None:
        journal = Journal()
        baseline = DelayedBaseline({"case-1": 0.02, "case-2": 0.0})
        await evaluate_large_baseline(
            two_synthetic_cases(),
            baseline,
            run_id="run-1",
            concurrency=2,
            model_metadata=metadata(),
            journal=journal,
        )
        assert journal.ids == ["case-2", "case-1"]

        failing_journal = Journal(fail_on="case-2")
        slow_baseline = DelayedBaseline({"case-1": 60.0, "case-2": 0.0})
        with pytest.raises(OSError, match="disk details"):
            await evaluate_large_baseline(
                two_synthetic_cases(),
                slow_baseline,
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
                journal=failing_journal,
            )
        assert slow_baseline.cancelled == ["case-1"]
        assert slow_baseline.in_flight == 0

    asyncio.run(scenario())


def test_caller_cancellation_cancels_all_workers() -> None:
    async def scenario() -> None:
        baseline = DelayedBaseline({"case-1": 60.0, "case-2": 60.0})
        task = asyncio.create_task(
            evaluate_large_baseline(
                two_synthetic_cases(),
                baseline,
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
            )
        )
        while baseline.in_flight < 2:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sorted(baseline.cancelled) == ["case-1", "case-2"]
        assert baseline.in_flight == 0

    asyncio.run(scenario())


def test_evaluation_rejects_config_concurrency_drift_and_duplicate_cases() -> None:
    async def scenario() -> None:
        with pytest.raises(ValueError, match="ordered"):
            await evaluate_large_baseline(
                set(two_synthetic_cases()),
                DelayedBaseline({"case-1": 0.0, "case-2": 0.0}),
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
            )
        with pytest.raises(ValueError, match="concurrency"):
            await evaluate_large_baseline(
                two_synthetic_cases(),
                DelayedBaseline({"case-1": 0.0, "case-2": 0.0}),
                run_id="run-1",
                concurrency=1,
                model_metadata=metadata(),
            )
        with pytest.raises(ValueError, match="duplicate"):
            await evaluate_large_baseline(
                (two_synthetic_cases()[0], two_synthetic_cases()[0]),
                DelayedBaseline({"case-1": 0.0}),
                run_id="run-1",
                concurrency=2,
                model_metadata=metadata(),
            )

    asyncio.run(scenario())


def empty_budget() -> BudgetSnapshot:
    return BudgetSnapshot(
        cap_usd=Decimal("20"),
        spent_usd=Decimal("0"),
        reserved_usd=Decimal("0"),
        remaining_usd=Decimal("20"),
        unresolved_request_ids=(),
    )


def empty_metrics() -> LargeEvaluationMetrics:
    return LargeEvaluationMetrics(
        total=1,
        completed=1,
        extraction_failed=0,
        request_failed=0,
        budget_blocked=0,
        cost_unresolved=0,
        p50_latency_ms=1.0,
        p95_latency_ms=1.0,
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=Decimal("0"),
        cost_per_1k_queries_usd=Decimal("0"),
        extraction_status_counts=(("ok", 1),),
        difficulty_counts=(("easy", 1),),
        category_counts=(("entity_lookup", 1),),
    )


def run_with_sql(
    run_id: str, sql: str, *, input_sha256: str | None = "f" * 64
) -> LargeEvaluationRun:
    checkpoint = empty_budget()
    outcome = EvaluationOutcome(
        case_id="case-1",
        **outcome_identity("List known addresses", input_sha256=input_sha256),
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("entity_lookup",),
        status="completed",
        prediction=prediction_for("List known addresses", raw_sql=sql),
        safe_error_code=None,
        model_metadata_sha256="e" * 64,
        source_synthetic=False,
        source_trusted=input_sha256 is not None,
        training_accepted=False,
        prompt_sha256="c" * 64,
        attempt_count=1,
        budget_checkpoint=checkpoint,
    )
    blockers = ["expected_100_cases", "non_three_run_evidence", "synthetic_backend"]
    if input_sha256 is None:
        blockers.append("trusted_test_set_provenance_missing")
    return LargeEvaluationRun(
        run_id=run_id,
        baseline="b4",
        outcomes=(outcome,),
        metrics=empty_metrics(),
        scientific_ready=False,
        blockers=tuple(sorted(blockers)),
        seed=42,
        generated_at_utc="2026-09-07T00:00:00Z",
        input_sha256=input_sha256,
        config_sha256=config().sha256,
        budget=checkpoint,
        catalog_sha256="a" * 64,
        summary_sha256="b" * 64,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256="e" * 64,
    )


def run_with_failure(run_id: str) -> LargeEvaluationRun:
    checkpoint = empty_budget()
    outcome = EvaluationOutcome(
        case_id="case-1",
        **outcome_identity("List known addresses", input_sha256="f" * 64),
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("entity_lookup",),
        status="request_failed",
        prediction=None,
        safe_error_code="rate_limit_exhausted",
        model_metadata_sha256="e" * 64,
        source_synthetic=False,
        source_trusted=True,
        training_accepted=False,
        prompt_sha256="c" * 64,
        attempt_count=3,
        budget_checkpoint=checkpoint,
    )
    metrics = LargeEvaluationMetrics(
        total=1,
        completed=0,
        extraction_failed=0,
        request_failed=1,
        budget_blocked=0,
        cost_unresolved=0,
        p50_latency_ms=0.0,
        p95_latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
        charged_cost_usd=Decimal("0"),
        cost_per_1k_queries_usd=Decimal("0"),
        extraction_status_counts=(),
        difficulty_counts=(("easy", 1),),
        category_counts=(("entity_lookup", 1),),
    )
    return LargeEvaluationRun(
        run_id=run_id,
        baseline="b4",
        outcomes=(outcome,),
        metrics=metrics,
        scientific_ready=False,
        blockers=("expected_100_cases", "incomplete_generation", "non_three_run_evidence"),
        seed=42,
        generated_at_utc="2026-09-07T00:00:00Z",
        input_sha256="f" * 64,
        config_sha256=config().sha256,
        budget=checkpoint,
        catalog_sha256="a" * 64,
        summary_sha256="b" * 64,
        training_sha256=None,
        model_id=config().model_id,
        provider_slug="deepinfra",
        model_metadata_sha256="e" * 64,
    )


def test_run_local_readiness_is_derived_from_loader_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returning a constant true readiness value would fail this test."""
    monkeypatch.setattr(
        evaluate_module,
        "load_local_verification_evidence",
        lambda: LocalVerificationEvidence(
            ready=False,
            blockers=("local_verification_manifest_missing",),
        ),
        raising=False,
    )

    assert run_with_sql("run-1", SAFE_SQL).local_implementation_ready is False


def test_three_run_report_measures_raw_and_normalized_sql_agreement() -> None:
    report = compare_large_reproducibility(
        (
            run_with_sql("run-1", "SELECT  address FROM `p.d.t`"),
            run_with_sql("run-2", "select address from `p.d.t`"),
            run_with_sql("run-3", "SELECT address FROM `p.d.t`"),
        )
    )
    assert report.run_count == 3
    assert report.pair_count == 3
    assert report.normalized_sql_agreement == 1.0
    assert report.raw_output_agreement < 1.0


def test_three_run_report_requires_strict_comparability() -> None:
    with pytest.raises(ValueError, match="exactly three"):
        compare_large_reproducibility((run_with_sql("run-1", SAFE_SQL),))
    with pytest.raises(ValueError, match="distinct"):
        compare_large_reproducibility(
            (
                run_with_sql("run-1", SAFE_SQL),
                run_with_sql("run-1", SAFE_SQL),
                run_with_sql("run-3", SAFE_SQL),
            )
        )
    drifted = run_with_sql("run-3", SAFE_SQL)
    object.__setattr__(drifted, "input_sha256", "0" * 64)
    with pytest.raises(ValueError, match="input fingerprint"):
        compare_large_reproducibility(
            (run_with_sql("run-1", SAFE_SQL), run_with_sql("run-2", SAFE_SQL), drifted)
        )


def test_three_all_failure_runs_compare_from_run_level_identity() -> None:
    report = compare_large_reproducibility(
        (run_with_failure("run-1"), run_with_failure("run-2"), run_with_failure("run-3"))
    )

    assert report.raw_output_agreement == 1.0
    assert report.normalized_sql_agreement == 1.0


def test_reproducibility_rejects_missing_input_fingerprint() -> None:
    with pytest.raises(ValueError, match="input fingerprint"):
        compare_large_reproducibility(
            (
                run_with_sql("run-1", SAFE_SQL, input_sha256=None),
                run_with_sql("run-2", SAFE_SQL, input_sha256=None),
                run_with_sql("run-3", SAFE_SQL, input_sha256=None),
            )
        )
