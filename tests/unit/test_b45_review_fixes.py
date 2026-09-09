from __future__ import annotations

import asyncio
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.models.b12 import EvaluationCase
from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import (
    BudgetLedger,
    LargeBaselineEvidence,
    LargeLLMConfig,
    PrivacyReviewEvidence,
    ProviderPolicy,
    RequestJournal,
    load_privacy_review,
    load_resume_state,
    serialize_privacy_review,
)
from nl2sparql.models.b45.evaluate import evaluate_large_baseline
from nl2sparql.models.b45.openrouter import (
    OpenRouterRequestError,
    OpenRouterTransport,
    _request_payload,
)

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


def _config(cap: str = "0.0011", *, concurrency: int = 5) -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("1"),
            completion_price_per_million_usd=Decimal("1"),
        ),
        max_cost_usd=Decimal(cap),
        max_attempts=3,
        concurrency=concurrency,
    )


class _Completions:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = iter(outcomes)
        self.calls = 0

    async def create(self, **_kwargs: object) -> object:
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _response() -> SimpleNamespace:
    return SimpleNamespace(
        id="generation-1",
        model="meta-llama/llama-3.3-70b-instruct",
        provider="deepinfra",
        system_fingerprint="fp-1",
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=SAFE_SQL))],
        usage=SimpleNamespace(
            prompt_tokens=2,
            completion_tokens=1,
            cost="0.0002",
            cost_details=SimpleNamespace(upstream_inference_cost="0.0001"),
        ),
    )


def test_retry_attempts_keep_distinct_unresolved_liabilities() -> None:
    async def scenario() -> None:
        config = _config()
        completions = _Completions([ConnectionError("transient"), _response()])
        sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        ledger = BudgetLedger(config)
        transport = OpenRouterTransport(
            sdk=sdk,
            ledger=ledger,
            sleep=lambda _delay: asyncio.sleep(0),
            clock_ns=iter([0, 2_000_000]).__next__,
        )

        result = await transport.complete(
            (ChatMessage("user", "List labels"),), config, request_id="case-1"
        )

        assert result.attempt_count == 2
        snapshot = await ledger.snapshot()
        assert snapshot.spent_usd == Decimal("0.0002")
        assert snapshot.unresolved_request_ids == ("case-1:attempt-1",)
        assert snapshot.unresolved_reservations[0].maximum_cost_usd == Decimal("0.000523")
        assert completions.calls == 2

    asyncio.run(scenario())


def test_retry_is_budget_blocked_without_releasing_prior_failure_liability() -> None:
    async def scenario() -> None:
        config = _config("0.0006")
        completions = _Completions([ConnectionError("transient"), _response()])
        sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        ledger = BudgetLedger(config)
        transport = OpenRouterTransport(
            sdk=sdk,
            ledger=ledger,
            sleep=lambda _delay: asyncio.sleep(0),
            clock_ns=iter([0, 2_000_000]).__next__,
        )

        with pytest.raises(OpenRouterRequestError) as captured:
            await transport.complete(
                (ChatMessage("user", "List labels"),), config, request_id="case-1"
            )

        assert captured.value.code == "budget_blocked"
        assert captured.value.attempt_count == 1
        assert completions.calls == 1
        snapshot = await ledger.snapshot()
        assert snapshot.unresolved_request_ids == ("case-1:attempt-1",)
        assert snapshot.reserved_usd == Decimal("0.000523")

    asyncio.run(scenario())


def test_repeated_retryable_failures_keep_each_ceiling_and_resume_cannot_oversubscribe() -> None:
    async def scenario() -> None:
        config = _config("0.002")
        completions = _Completions(
            [ConnectionError("one"), ConnectionError("two"), ConnectionError("three")]
        )
        sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        ledger = BudgetLedger(config)
        transport = OpenRouterTransport(
            sdk=sdk,
            ledger=ledger,
            sleep=lambda _delay: asyncio.sleep(0),
        )
        with pytest.raises(OpenRouterRequestError) as captured:
            await transport.complete(
                (ChatMessage("user", "List labels"),), config, request_id="case-1"
            )
        assert captured.value.code == "retry_exhausted"
        snapshot = await ledger.snapshot()
        assert snapshot.unresolved_request_ids == (
            "case-1:attempt-1",
            "case-1:attempt-2",
            "case-1:attempt-3",
        )
        assert snapshot.reserved_usd == Decimal("0.001569")

        # Restoring that checkpoint must preserve all three liabilities.  A
        # subsequent request may proceed only if a fourth ceiling still fits.
        resumed = BudgetLedger.from_checkpoint(config, snapshot)
        resumed_transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=_Completions([_response()]))),
            ledger=resumed,
            sleep=lambda _delay: asyncio.sleep(0),
            clock_ns=iter([0, 2_000_000]).__next__,
        )
        with pytest.raises(OpenRouterRequestError, match="budget blocked"):
            await resumed_transport.complete(
                (ChatMessage("user", "List labels"),), config, request_id="case-1"
            )
        assert (await resumed.snapshot()).unresolved_request_ids == snapshot.unresolved_request_ids

    asyncio.run(scenario())


def test_privacy_review_is_canonical_and_bound_to_input(tmp_path: Path) -> None:
    input_sha = hashlib.sha256(b"test snapshot").hexdigest()
    evidence = PrivacyReviewEvidence(
        input_sha256=input_sha,
        reviewed=True,
        no_secrets=True,
        no_personal_data=True,
    )
    path = tmp_path / "test.jsonl.privacy.json"
    path.write_bytes(serialize_privacy_review(evidence))

    loaded = load_privacy_review(
        path,
        expected_input_sha256=input_sha,
        accepted_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )

    assert loaded == evidence
    assert loaded.privacy_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()

    tampered = json.loads(path.read_text())
    tampered["no_secrets"] = False
    path.write_text(json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="privacy"):
        load_privacy_review(
            path,
            expected_input_sha256=input_sha,
            accepted_sha256=loaded.privacy_sha256,
        )


def test_cancellation_durably_records_unresolved_reservation_before_propagating(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        config = _config("0.01", concurrency=1)
        case = EvaluationCase(
            case_id="case-1",
            question="List labels",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("lookup",),
            input_sha256="a" * 64,
        )
        started = asyncio.Event()

        class Baseline:
            def __init__(self) -> None:
                self.config = config
                self.budget_ledger = BudgetLedger(config)
                self.evaluation_evidence = LargeBaselineEvidence(
                    baseline="b4",
                    catalog_sha256="b" * 64,
                    summary_sha256="c" * 64,
                    config_sha256=config.sha256,
                    training_sha256=None,
                    training_accepted=False,
                    model_id=config.model_id,
                    provider_slug=config.provider.provider_slug,
                )

            async def predict_detailed(self, question: str, *, request_id: str):
                reservation = await self.budget_ledger.reserve(
                    request_id, (ChatMessage("user", question),)
                )
                assert reservation is not None
                started.set()
                await asyncio.Event().wait()

        journal_path = tmp_path / "cancel.jsonl"
        journal = RequestJournal(
            journal_path,
            run_id="run-cancel",
            baseline="b4",
            input_sha256=case.input_sha256,
            config_sha256=config.sha256,
            catalog_sha256="b" * 64,
            summary_sha256="c" * 64,
            training_sha256=None,
            model_id=config.model_id,
            provider_slug=config.provider.provider_slug,
        )
        baseline = Baseline()
        from nl2sparql.models.b45.evaluate import evaluate_large_baseline

        task = asyncio.create_task(
            evaluate_large_baseline(
                (case,),
                baseline,
                run_id="run-cancel",
                concurrency=1,
                model_metadata=None,
                journal=journal,
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        resume = load_resume_state(
            journal_path,
            expected_input_sha256=case.input_sha256,
            expected_config_sha256=config.sha256,
            expected_run_id="run-cancel",
            expected_model_metadata_sha256=None,
        )
        assert resume.completed_case_ids == ("case-1",)
        assert resume.completed_outcomes[0].safe_error_code == "request_cancelled"
        assert resume.budget_checkpoint.unresolved_request_ids == ("case-1",)
        assert (
            resume.completed_outcomes[0].prompt_sha256
            == hashlib.sha256(case.question.encode("utf-8")).hexdigest()
        )

    asyncio.run(scenario())


def test_transport_cancellation_holds_the_attempt_ceiling() -> None:
    async def scenario() -> None:
        config = _config("0.01", concurrency=1)
        started = asyncio.Event()

        class Completions:
            async def create(self, **_kwargs: object) -> object:
                started.set()
                await asyncio.Event().wait()

        sdk = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
        ledger = BudgetLedger(config)
        transport = OpenRouterTransport(sdk=sdk, ledger=ledger)
        task = asyncio.create_task(
            transport.complete((ChatMessage("user", "List labels"),), config, request_id="case-1")
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as captured:
            await task
        assert captured.value.prompt_sha256
        snapshot = await ledger.snapshot()
        assert snapshot.unresolved_request_ids == ("case-1:attempt-1",)
        assert snapshot.reserved_usd == Decimal("0.000523")

    asyncio.run(scenario())


def test_retry_cancellation_durably_records_the_failed_attempt_liability(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        config = _config("0.01", concurrency=1)
        case = EvaluationCase(
            case_id="case-1",
            question="List labels",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("lookup",),
            input_sha256="a" * 64,
        )
        retry_sleep_started = asyncio.Event()

        async def sleep(_delay: float) -> None:
            retry_sleep_started.set()
            await asyncio.Event().wait()

        completions = _Completions([ConnectionError("transient")])
        ledger = BudgetLedger(config)
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            ledger=ledger,
            sleep=sleep,
        )

        class Baseline:
            def __init__(self) -> None:
                self.config = config
                self.budget_ledger = ledger
                self.evaluation_evidence = LargeBaselineEvidence(
                    baseline="b4",
                    catalog_sha256="b" * 64,
                    summary_sha256="c" * 64,
                    config_sha256=config.sha256,
                    training_sha256=None,
                    training_accepted=False,
                    model_id=config.model_id,
                    provider_slug=config.provider.provider_slug,
                    provider_policy_sha256=config.provider.sha256,
                )

            async def predict_detailed(self, question: str, *, request_id: str) -> object:
                return await transport.complete(
                    (ChatMessage("user", question),), config, request_id=request_id
                )

        journal = RequestJournal(
            tmp_path / "retry-cancel.jsonl",
            run_id="run-retry-cancel",
            baseline="b4",
            input_sha256=case.input_sha256,
            config_sha256=config.sha256,
            catalog_sha256="b" * 64,
            summary_sha256="c" * 64,
            training_sha256=None,
            model_id=config.model_id,
            provider_slug=config.provider.provider_slug,
            provider_policy_sha256=config.provider.sha256,
        )
        task = asyncio.create_task(
            evaluate_large_baseline(
                (case,),
                Baseline(),
                run_id="run-retry-cancel",
                concurrency=1,
                model_metadata=None,
                journal=journal,
            )
        )
        await retry_sleep_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        resume = load_resume_state(
            tmp_path / "retry-cancel.jsonl",
            expected_input_sha256=case.input_sha256,
            expected_config_sha256=config.sha256,
            expected_run_id="run-retry-cancel",
            expected_model_metadata_sha256=None,
            expected_catalog_sha256="b" * 64,
            expected_summary_sha256="c" * 64,
            expected_training_sha256=None,
            expected_model_id=config.model_id,
            expected_provider_slug=config.provider.provider_slug,
            expected_provider_policy_sha256=config.provider.sha256,
            expected_privacy_sha256=None,
            expected_baseline="b4",
        )
        assert resume.completed_outcomes[0].safe_error_code == "request_cancelled"
        assert resume.budget_checkpoint.unresolved_request_ids == ("case-1:attempt-1",)
        assert resume.budget_checkpoint.reserved_usd == Decimal("0.000523")
        assert completions.calls == 1

    asyncio.run(scenario())


def test_reconcile_cancellation_records_exact_spend_before_propagating(tmp_path: Path) -> None:
    async def scenario() -> None:
        config = _config("0.01", concurrency=1)
        case = EvaluationCase(
            case_id="case-1",
            question="List labels",
            gold_sql=SAFE_SQL,
            difficulty="easy",
            categories=("lookup",),
            input_sha256="a" * 64,
        )
        reconcile_started = asyncio.Event()
        release_reconcile = asyncio.Event()
        ledger = BudgetLedger(config)
        original_reconcile = ledger.reconcile

        async def delayed_reconcile(reservation, actual_cost):
            reconcile_started.set()
            await release_reconcile.wait()
            return await original_reconcile(reservation, actual_cost)

        ledger.reconcile = delayed_reconcile  # type: ignore[method-assign]
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=_Completions([_response()]))),
            ledger=ledger,
            clock_ns=iter([0, 2_000_000]).__next__,
        )

        class Baseline:
            def __init__(self) -> None:
                self.config = config
                self.budget_ledger = ledger
                self.evaluation_evidence = LargeBaselineEvidence(
                    baseline="b4",
                    catalog_sha256="b" * 64,
                    summary_sha256="c" * 64,
                    config_sha256=config.sha256,
                    training_sha256=None,
                    training_accepted=False,
                    model_id=config.model_id,
                    provider_slug=config.provider.provider_slug,
                    provider_policy_sha256=config.provider.sha256,
                )

            async def predict_detailed(self, question: str, *, request_id: str) -> object:
                return await transport.complete(
                    (ChatMessage("user", question),), config, request_id=request_id
                )

        journal_path = tmp_path / "reconcile-cancel.jsonl"
        journal = RequestJournal(
            journal_path,
            run_id="run-reconcile-cancel",
            baseline="b4",
            input_sha256=case.input_sha256,
            config_sha256=config.sha256,
            catalog_sha256="b" * 64,
            summary_sha256="c" * 64,
            training_sha256=None,
            model_id=config.model_id,
            provider_slug=config.provider.provider_slug,
            provider_policy_sha256=config.provider.sha256,
        )
        task = asyncio.create_task(
            evaluate_large_baseline(
                (case,),
                Baseline(),
                run_id="run-reconcile-cancel",
                concurrency=1,
                model_metadata=None,
                journal=journal,
            )
        )
        await reconcile_started.wait()
        task.cancel()
        release_reconcile.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        resume = load_resume_state(
            journal_path,
            expected_input_sha256=case.input_sha256,
            expected_config_sha256=config.sha256,
            expected_run_id="run-reconcile-cancel",
            expected_model_metadata_sha256=None,
            expected_catalog_sha256="b" * 64,
            expected_summary_sha256="c" * 64,
            expected_training_sha256=None,
            expected_model_id=config.model_id,
            expected_provider_slug=config.provider.provider_slug,
            expected_provider_policy_sha256=config.provider.sha256,
            expected_privacy_sha256=None,
            expected_baseline="b4",
        )
        outcome = resume.completed_outcomes[0]
        assert outcome.safe_error_code == "request_cancelled"
        assert outcome.authoritative_cost_usd == Decimal("0.0002")
        assert resume.budget_checkpoint.spent_usd == Decimal("0.0002")
        assert resume.budget_checkpoint.unresolved_request_ids == ()

    asyncio.run(scenario())


def test_legacy_resume_migration_binds_new_policy_and_privacy_identity(tmp_path: Path) -> None:
    """Schema v2 remains resumable while v3 migration adds current identity gates."""
    import nl2sparql.models.b45.artifacts as artifacts

    request_log = tmp_path / "request.jsonl"
    request_log.write_bytes(
        Path("tests/fixtures/b45/request-journal-v2-in-progress.jsonl").read_bytes()
    )
    legacy_config = LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        concurrency=1,
    )
    policy_sha = legacy_config.provider.sha256
    privacy_sha = "d" * 64

    resume = load_resume_state(
        request_log,
        expected_input_sha256="f" * 64,
        expected_config_sha256=legacy_config.sha256,
        expected_run_id="run-v2",
        expected_model_metadata_sha256="e" * 64,
        expected_catalog_sha256="a" * 64,
        expected_summary_sha256="b" * 64,
        expected_training_sha256=None,
        expected_model_id=legacy_config.model_id,
        expected_provider_slug="deepinfra",
        expected_provider_policy_sha256=policy_sha,
        expected_privacy_sha256=privacy_sha,
        expected_baseline="b4",
    )
    assert resume.provider_policy_sha256 == policy_sha
    assert resume.privacy_sha256 == privacy_sha
    assert resume.completed_outcomes[0].provider_policy_sha256 == policy_sha
    assert resume.completed_outcomes[0].privacy_sha256 == privacy_sha

    journal = artifacts.RequestJournal(
        request_log,
        allow_legacy_resume=True,
        run_id="run-v2",
        baseline="b4",
        input_sha256="f" * 64,
        config_sha256=legacy_config.sha256,
        catalog_sha256="a" * 64,
        summary_sha256="b" * 64,
        training_sha256=None,
        model_id=legacy_config.model_id,
        provider_slug="deepinfra",
        model_metadata_sha256="e" * 64,
        provider_policy_sha256=policy_sha,
        privacy_sha256=privacy_sha,
    )
    assert journal
    migrated = [json.loads(line) for line in request_log.read_text().splitlines()]
    assert migrated[0]["schema_version"] == 3
    assert migrated[0]["provider_policy_sha256"] == policy_sha
    assert migrated[0]["privacy_sha256"] == privacy_sha
    assert migrated[1]["provider_policy_sha256"] == policy_sha
    assert migrated[1]["privacy_sha256"] == privacy_sha


def test_provider_max_price_json_numbers_never_round_above_decimal_policy() -> None:
    config = LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            # This value is intentionally not exactly representable as binary
            # floating point; an upward conversion would weaken the cap.
            prompt_price_per_million_usd=Decimal("0.10000000000000001"),
            completion_price_per_million_usd=Decimal("1.0000000000000001"),
        )
    )
    payload = _request_payload((ChatMessage("user", "List labels"),), config)
    prices = payload["provider"]["max_price"]  # type: ignore[index]
    assert Decimal.from_float(prices["prompt"]) <= config.provider.prompt_price_per_million_usd
    assert (
        Decimal.from_float(prices["completion"]) <= config.provider.completion_price_per_million_usd
    )
