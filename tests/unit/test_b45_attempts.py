import asyncio
import hashlib
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nl2sparql.models.b12 import CatalogSummary, EvaluationCase
from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b12.prompts import prompt_sha256
from nl2sparql.models.b45 import (
    AttemptEvidencePersistenceError,
    BaselineB4,
    BudgetLedger,
    BudgetReservation,
    BudgetSnapshot,
    LargeBaselineEvidence,
    LargeLLMConfig,
    LargeLLMError,
    ProviderPolicy,
    RequestJournal,
    load_resume_state,
    preview_b4_prompt,
    serialize_request_log,
)
from nl2sparql.models.b45.attempts import AttemptEvidence
from nl2sparql.models.b45.evaluate import EvaluationOutcome, evaluate_large_baseline
from nl2sparql.models.b45.openrouter import OpenRouterRequestError, OpenRouterTransport


def _config() -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        max_cost_usd=Decimal("1.00"),
    )


def _response() -> object:
    return SimpleNamespace(
        id="gen-1",
        model="meta-llama/llama-3.3-70b-instruct",
        provider="deepinfra",
        system_fingerprint="fp-1",
        choices=[
            SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="SELECT 1"))
        ],
        usage=SimpleNamespace(
            prompt_tokens=2,
            completion_tokens=1,
            cost="0.0002",
            cost_details=SimpleNamespace(upstream_inference_cost="0.0001"),
        ),
    )


def _journal(path, config: LargeLLMConfig) -> RequestJournal:
    return RequestJournal(
        path,
        run_id="run-1",
        baseline="b4",
        input_sha256="b" * 64,
        config_sha256=config.sha256,
        catalog_sha256="c" * 64,
        summary_sha256="d" * 64,
        training_sha256=None,
        model_id=config.model_id,
        provider_slug="deepinfra",
    )


async def _append_completed_prefix(
    journal: RequestJournal,
    config: LargeLLMConfig,
    *,
    case_id: str = "case-1",
    cost: Decimal = Decimal("0.0002"),
    messages: tuple[ChatMessage, ...] = (ChatMessage("user", "prompt"),),
) -> BudgetSnapshot:
    prompt = prompt_sha256(messages)
    ceiling = Decimal("0.000515")
    reserved = BudgetSnapshot(
        cap_usd=config.max_cost_usd,
        spent_usd=Decimal("0"),
        reserved_usd=ceiling,
        remaining_usd=config.max_cost_usd - ceiling,
        unresolved_request_ids=(f"{case_id}:attempt-1",),
        unresolved_reservations=(BudgetReservation(f"{case_id}:attempt-1", ceiling),),
    )
    completed = BudgetSnapshot(
        cap_usd=config.max_cost_usd,
        spent_usd=cost,
        reserved_usd=Decimal("0"),
        remaining_usd=config.max_cost_usd - cost,
        unresolved_request_ids=(),
        unresolved_reservations=(),
    )
    await journal.append_attempt(
        AttemptEvidence(
            case_id=case_id,
            request_id=case_id,
            reservation_id=f"{case_id}:attempt-1",
            attempt_number=1,
            status="reserved",
            prompt_sha256=prompt,
            reservation_ceiling_usd=ceiling,
            budget_checkpoint=reserved,
        )
    )
    await journal.append_attempt(
        AttemptEvidence(
            case_id=case_id,
            request_id=case_id,
            reservation_id=f"{case_id}:attempt-1",
            attempt_number=1,
            status="completed",
            prompt_sha256=prompt,
            reservation_ceiling_usd=ceiling,
            budget_checkpoint=completed,
            authoritative_cost_usd=cost,
        )
    )
    return completed


def test_transport_emits_ordered_secret_safe_evidence_for_retry_and_success() -> None:
    """Removing sink transitions would lose a durable remote-attempt history."""

    class Attempts:
        def __init__(self) -> None:
            self.items: list[AttemptEvidence] = []

        async def append_attempt(self, evidence: AttemptEvidence) -> None:
            self.items.append(evidence)

    class Completions:
        def __init__(self) -> None:
            self.items = iter([ConnectionError("secret raw provider error"), _response()])

        async def create(self, **_kwargs: object) -> object:
            value = next(self.items)
            if isinstance(value, BaseException):
                raise value
            return value

    async def no_wait(_delay: float) -> None:
        return None

    async def scenario() -> None:
        config = _config()
        attempts = Attempts()
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
            ledger=BudgetLedger(config),
            attempt_sink=attempts,
            sleep=no_wait,
            clock_ns=iter([0, 1_000_000]).__next__,
        )

        await transport.complete(
            (ChatMessage("user", "secret prompt"),), config, request_id="case-1"
        )

        assert [(item.attempt_number, item.status) for item in attempts.items] == [
            (1, "reserved"),
            (1, "retryable_failure"),
            (2, "reserved"),
            (2, "completed"),
        ]
        assert attempts.items[0].reservation_id == "case-1:attempt-1"
        assert attempts.items[-1].authoritative_cost_usd == Decimal("0.0002")
        assert all("secret" not in repr(item) for item in attempts.items)
        assert all(item.request_id == "case-1" for item in attempts.items)

    asyncio.run(scenario())


def test_completed_attempt_only_prefix_reissues_next_attempt_when_cap_admits(tmp_path) -> None:
    """Restarting at attempt 1 would collide with durable completed attempt evidence."""

    class Completions:
        def __init__(self, outcomes: list[object]) -> None:
            self.outcomes = iter(outcomes)

        async def create(self, **_kwargs: object) -> object:
            return next(self.outcomes)

    async def scenario() -> None:
        config = _config()
        journal = _journal(tmp_path / "completed-prefix.jsonl", config)
        checkpoint = await _append_completed_prefix(journal, config)
        resume = load_resume_state(
            tmp_path / "completed-prefix.jsonl",
            expected_input_sha256="b" * 64,
            expected_config_sha256=config.sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=None,
        )
        assert resume.completed_case_ids == ()
        assert resume.budget_checkpoint == checkpoint

        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions([_response()]))),
            ledger=BudgetLedger.from_checkpoint(config, resume.budget_checkpoint),
            attempt_sink=journal,
            clock_ns=iter([0, 1_000_000]).__next__,
        )
        result = await transport.complete(
            (ChatMessage("user", "prompt"),), config, request_id="case-1"
        )

        assert result.attempt_count == 2
        assert [
            (item.attempt_number, item.status, item.reservation_id) for item in journal.attempts
        ] == [
            (1, "reserved", "case-1:attempt-1"),
            (1, "completed", "case-1:attempt-1"),
            (2, "reserved", "case-1:attempt-2"),
            (2, "completed", "case-1:attempt-2"),
        ]
        snapshot = await transport._ledger.snapshot()
        assert snapshot.cap_usd == config.max_cost_usd
        assert snapshot.spent_usd == Decimal("0.0004")
        assert snapshot.reserved_usd == Decimal("0")
        assert journal.attempts[-1].budget_checkpoint == snapshot

    asyncio.run(scenario())


def test_completed_attempt_only_prefix_does_not_reissue_when_cap_blocks(tmp_path) -> None:
    """A blocked resume must not reuse attempt 1 or append a fabricated attempt 2."""

    class Completions:
        calls = 0

        async def create(self, **_kwargs: object) -> object:
            type(self).calls += 1
            return _response()

    async def scenario() -> None:
        config = LargeLLMConfig(
            provider=ProviderPolicy(
                provider_slug="deepinfra",
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
            ),
            max_cost_usd=Decimal("0.0006"),
        )
        journal = _journal(tmp_path / "completed-prefix-blocked.jsonl", config)
        checkpoint = await _append_completed_prefix(journal, config)
        before = (tmp_path / "completed-prefix-blocked.jsonl").read_bytes()
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
            ledger=BudgetLedger.from_checkpoint(config, checkpoint),
            attempt_sink=journal,
        )

        with pytest.raises(OpenRouterRequestError) as captured:
            await transport.complete((ChatMessage("user", "prompt"),), config, request_id="case-1")

        assert captured.value.code == "budget_blocked"
        assert captured.value.attempt_count == 1
        assert Completions.calls == 0
        assert [(item.attempt_number, item.status) for item in journal.attempts] == [
            (1, "reserved"),
            (1, "completed"),
        ]
        assert (tmp_path / "completed-prefix-blocked.jsonl").read_bytes() == before

    asyncio.run(scenario())


@pytest.mark.parametrize("cap_usd", [Decimal("0.0006"), Decimal("1.00")])
def test_completed_attempt_only_resume_attributes_only_the_new_outcome(
    tmp_path, cap_usd: Decimal
) -> None:
    """Orphan attempt spend remains unattributed whether resume blocks or completes."""

    class Completions:
        calls = 0

        async def create(self, **_kwargs: object) -> object:
            type(self).calls += 1
            response = _response()
            response.choices[
                0
            ].message.content = (
                "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
            )
            return response

    async def scenario() -> None:
        config = LargeLLMConfig(
            provider=ProviderPolicy(
                provider_slug="deepinfra",
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
            ),
            max_cost_usd=cap_usd,
        )
        summary_text = "GoogleSQL catalog\n"
        summary = CatalogSummary(
            text=summary_text,
            catalog_sha256="c" * 64,
            summary_sha256=hashlib.sha256(summary_text.encode()).hexdigest(),
        )
        journal_path = tmp_path / f"resume-{cap_usd}.jsonl"
        journal = RequestJournal(
            journal_path,
            run_id="run-1",
            baseline="b4",
            input_sha256="b" * 64,
            config_sha256=config.sha256,
            catalog_sha256=summary.catalog_sha256,
            summary_sha256=summary.summary_sha256,
            training_sha256=None,
            model_id=config.model_id,
            provider_slug="deepinfra",
            provider_policy_sha256=config.provider.sha256,
        )
        case = EvaluationCase(
            case_id="case-1",
            question="prompt",
            gold_sql=(
                "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
            ),
            difficulty="easy",
            categories=("lookup",),
            input_sha256="b" * 64,
        )
        preview = preview_b4_prompt(case.question, summary)
        checkpoint = await _append_completed_prefix(journal, config, messages=preview.messages)
        resume = load_resume_state(
            journal_path,
            expected_input_sha256="b" * 64,
            expected_config_sha256=config.sha256,
            expected_run_id="run-1",
            expected_model_metadata_sha256=None,
            expected_provider_policy_sha256=config.provider.sha256,
        )
        assert resume.completed_case_ids == ()
        assert resume.budget_checkpoint == checkpoint

        ledger = BudgetLedger.from_checkpoint(config, checkpoint)
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
            ledger=ledger,
            attempt_sink=journal,
            clock_ns=iter([0, 1_000_000]).__next__,
        )
        baseline = BaselineB4(summary, config, transport)
        run = await evaluate_large_baseline(
            (case,),
            baseline,
            run_id="run-1",
            concurrency=config.concurrency,
            model_metadata=None,
            journal=journal,
            resume_budget_checkpoint=resume.budget_checkpoint,
        )

        expected_new_cost = Decimal("0") if cap_usd < Decimal("1") else Decimal("0.0002")
        expected_status = "budget_blocked" if expected_new_cost == 0 else "completed"
        assert Completions.calls == (0 if expected_status == "budget_blocked" else 1)
        assert run.outcomes[0].status == expected_status
        assert run.outcomes[0].attempt_count == (1 if expected_status == "budget_blocked" else 2)
        assert run.outcomes[0].authoritative_cost_usd == expected_new_cost
        assert run.budget.spent_usd == Decimal("0.0002") + expected_new_cost
        assert run.budget.unresolved_request_ids == ()
        assert run.metrics.attributed_spend_usd == expected_new_cost
        assert run.metrics.unattributed_spend_usd == Decimal("0.0002")
        assert "unattributed_spend" in run.blockers
        assert [item.attempt_number for item in run.attempts] == (
            [1, 1] if expected_status == "budget_blocked" else [1, 1, 2, 2]
        )
        assert serialize_request_log(run).endswith(b"\n")

    asyncio.run(scenario())


def test_attempt_only_prefix_restores_latest_checkpoint_without_completing_case(tmp_path) -> None:
    """Treating an attempt row as a completed outcome would skip unsafe work on resume."""
    config = _config()
    prompt = "a" * 64
    ceiling = Decimal("0.000523")
    held = BudgetSnapshot(
        cap_usd=Decimal("1.00"),
        spent_usd=Decimal("0"),
        reserved_usd=ceiling,
        remaining_usd=Decimal("1.00") - ceiling,
        unresolved_request_ids=("case-1:attempt-1",),
        unresolved_reservations=(BudgetReservation("case-1:attempt-1", ceiling),),
    )
    journal_path = tmp_path / "attempt-prefix.jsonl"
    journal = RequestJournal(
        journal_path,
        run_id="run-1",
        baseline="b4",
        input_sha256="b" * 64,
        config_sha256=config.sha256,
        catalog_sha256="c" * 64,
        summary_sha256="d" * 64,
        training_sha256=None,
        model_id=config.model_id,
        provider_slug="deepinfra",
    )

    reserved = AttemptEvidence(
        case_id="case-1",
        request_id="case-1",
        reservation_id="case-1:attempt-1",
        attempt_number=1,
        status="reserved",
        prompt_sha256=prompt,
        reservation_ceiling_usd=ceiling,
        budget_checkpoint=held,
    )

    async def append() -> None:
        await journal.append_attempt(reserved)
        await journal.append_attempt(
            AttemptEvidence(**{**reserved.__dict__, "status": "retryable_failure"})
        )

    asyncio.run(append())
    resume = load_resume_state(
        journal_path,
        expected_input_sha256="b" * 64,
        expected_config_sha256=config.sha256,
        expected_run_id="run-1",
        expected_model_metadata_sha256=None,
    )
    assert resume.completed_case_ids == ()
    assert resume.budget_checkpoint == held
    resumed = BudgetLedger.from_checkpoint(config, resume.budget_checkpoint)
    assert asyncio.run(resumed.reserve("case-2:attempt-1", (ChatMessage("user", "x"),))) is not None

    # A duplicate transition must be rejected even if an attacker rewrites the
    # outer JSON line canonically; the chain/order validator remains fail-closed.
    with pytest.raises(Exception, match="duplicate"):
        asyncio.run(journal.append_attempt(reserved))


def test_backoff_cancellation_does_not_append_second_terminal_attempt() -> None:
    """Appending cancelled after retryable_failure double-counts one attempt."""

    class Attempts:
        def __init__(self) -> None:
            self.items: list[AttemptEvidence] = []

        async def append_attempt(self, evidence: AttemptEvidence) -> None:
            self.items.append(evidence)

    class Completions:
        async def create(self, **_kwargs: object) -> object:
            raise ConnectionError("transient provider detail")

    async def scenario() -> None:
        started = asyncio.Event()

        async def sleep(_delay: float) -> None:
            started.set()
            await asyncio.Event().wait()

        config = _config()
        attempts = Attempts()
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
            ledger=BudgetLedger(config),
            attempt_sink=attempts,
            sleep=sleep,
        )
        task = asyncio.create_task(
            transport.complete((ChatMessage("user", "prompt"),), config, request_id="case-1")
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert [(item.attempt_number, item.status) for item in attempts.items] == [
            (1, "reserved"),
            (1, "retryable_failure"),
        ]

    asyncio.run(scenario())


def test_invalid_retry_delay_records_one_terminal_transition() -> None:
    """A retry-delay validation failure must not first mark the attempt retryable."""

    class Attempts:
        def __init__(self) -> None:
            self.items: list[AttemptEvidence] = []

        async def append_attempt(self, evidence: AttemptEvidence) -> None:
            self.items.append(evidence)

    class Completions:
        async def create(self, **_kwargs: object) -> object:
            raise ConnectionError("transient provider detail")

    async def scenario() -> None:
        config = _config()
        attempts = Attempts()
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
            ledger=BudgetLedger(config),
            attempt_sink=attempts,
            jitter=lambda _attempt: float("nan"),
        )

        with pytest.raises(OpenRouterRequestError) as captured:
            await transport.complete((ChatMessage("user", "prompt"),), config, request_id="case-1")

        assert captured.value.code == "retry_delay_invalid"
        assert [(item.attempt_number, item.status) for item in attempts.items] == [
            (1, "reserved"),
            (1, "terminal_failure"),
        ]

    asyncio.run(scenario())


def test_attempt_sink_persistence_error_aborts_evaluation_without_outcome() -> None:
    """Converting attempt persistence failure to prediction_failed would publish bad evidence."""

    class FailingSink:
        def __init__(self) -> None:
            self.sibling_started = asyncio.Event()

        async def append_attempt(self, _evidence: AttemptEvidence) -> None:
            if _evidence.case_id == "case-1":
                await self.sibling_started.wait()
                raise LargeLLMError("raw secret persistence detail")

    class Completions:
        def __init__(self, sink: FailingSink) -> None:
            self.sink = sink
            self.sibling_cancelled = asyncio.Event()

        async def create(self, **_kwargs: object) -> object:
            self.sink.sibling_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.sibling_cancelled.set()
                raise

    class OutcomeCollector:
        def __init__(self) -> None:
            self.items: list[EvaluationOutcome] = []

        def append(self, outcome: EvaluationOutcome) -> None:
            self.items.append(outcome)

    async def scenario() -> None:
        config = LargeLLMConfig(
            provider=ProviderPolicy(
                provider_slug="deepinfra",
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
            ),
            max_cost_usd=Decimal("1.00"),
            concurrency=2,
        )
        ledger = BudgetLedger(config)
        sink = FailingSink()
        completions = Completions(sink)
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            ledger=ledger,
            attempt_sink=sink,
        )

        class Baseline:
            def __init__(self) -> None:
                self.config = config
                self.budget_ledger = ledger
                self.evaluation_evidence = LargeBaselineEvidence(
                    baseline="b4",
                    catalog_sha256="c" * 64,
                    summary_sha256="d" * 64,
                    config_sha256=config.sha256,
                    training_sha256=None,
                    training_accepted=False,
                    model_id=config.model_id,
                    provider_slug=config.provider.provider_slug,
                )

            async def predict_detailed(self, question: str, *, request_id: str) -> object:
                return await transport.complete(
                    (ChatMessage("user", question),), config, request_id=request_id
                )

        collector = OutcomeCollector()
        cases = tuple(
            EvaluationCase(
                case_id=f"case-{index}",
                question=f"prompt {index}",
                gold_sql=(
                    "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
                ),
                difficulty="easy",
                categories=("lookup",),
                input_sha256="b" * 64,
            )
            for index in (1, 2)
        )
        with pytest.raises(AttemptEvidencePersistenceError) as captured:
            await evaluate_large_baseline(
                cases,
                Baseline(),
                run_id="run-1",
                concurrency=config.concurrency,
                model_metadata=None,
                journal=collector,
            )

        assert "attempt evidence persistence" in str(captured.value)
        assert "secret" not in str(captured.value)
        assert completions.sibling_cancelled.is_set()
        assert collector.items == []

    asyncio.run(scenario())


def test_attempt_evidence_rejects_authoritative_cost_on_retryable_failure() -> None:
    ceiling = Decimal("0.000523")
    held = BudgetSnapshot(
        cap_usd=Decimal("1.00"),
        spent_usd=Decimal("0"),
        reserved_usd=ceiling,
        remaining_usd=Decimal("1.00") - ceiling,
        unresolved_request_ids=("case-1:attempt-1",),
        unresolved_reservations=(BudgetReservation("case-1:attempt-1", ceiling),),
    )
    with pytest.raises(LargeLLMError, match="retryable"):
        AttemptEvidence(
            case_id="case-1",
            request_id="case-1",
            reservation_id="case-1:attempt-1",
            attempt_number=1,
            status="retryable_failure",
            prompt_sha256=hashlib.sha256(b"prompt").hexdigest(),
            reservation_ceiling_usd=ceiling,
            budget_checkpoint=held,
            authoritative_cost_usd=Decimal("0.01"),
        )


def test_journal_rejects_attempt_terminal_without_reserved_transition(tmp_path) -> None:
    config = _config()
    journal = RequestJournal(
        tmp_path / "attempt-prefix.jsonl",
        run_id="run-1",
        baseline="b4",
        input_sha256="b" * 64,
        config_sha256=config.sha256,
        catalog_sha256="c" * 64,
        summary_sha256="d" * 64,
        training_sha256=None,
        model_id=config.model_id,
        provider_slug="deepinfra",
    )
    ceiling = Decimal("0.000523")
    held = BudgetSnapshot(
        cap_usd=Decimal("1.00"),
        spent_usd=Decimal("0"),
        reserved_usd=ceiling,
        remaining_usd=Decimal("1.00") - ceiling,
        unresolved_request_ids=("case-1:attempt-1",),
        unresolved_reservations=(BudgetReservation("case-1:attempt-1", ceiling),),
    )
    terminal = AttemptEvidence(
        case_id="case-1",
        request_id="case-1",
        reservation_id="case-1:attempt-1",
        attempt_number=1,
        status="retryable_failure",
        prompt_sha256=hashlib.sha256(b"prompt").hexdigest(),
        reservation_ceiling_usd=ceiling,
        budget_checkpoint=held,
    )
    # A retryable row is valid as a value, but invalid as the first transition.
    with pytest.raises(LargeLLMError, match="transition"):
        asyncio.run(journal.append_attempt(terminal))


def test_transport_blocks_retry_when_prior_attempt_ceiling_fills_cap() -> None:
    class Attempts:
        def __init__(self) -> None:
            self.items: list[AttemptEvidence] = []

        async def append_attempt(self, evidence: AttemptEvidence) -> None:
            self.items.append(evidence)

    class Completions:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_kwargs: object) -> object:
            self.calls += 1
            raise ConnectionError("provider detail must not escape")

    async def no_wait(_delay: float) -> None:
        return None

    async def scenario() -> None:
        config = LargeLLMConfig(
            provider=ProviderPolicy(
                provider_slug="deepinfra",
                prompt_price_per_million_usd=Decimal("0.50"),
                completion_price_per_million_usd=Decimal("1.00"),
            ),
            max_cost_usd=Decimal("0.0008"),
        )
        attempts = Attempts()
        completions = Completions()
        transport = OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            ledger=BudgetLedger(config),
            attempt_sink=attempts,
            sleep=no_wait,
            clock_ns=iter([0, 1_000_000]).__next__,
        )
        with pytest.raises(OpenRouterRequestError, match="budget blocked"):
            await transport.complete((ChatMessage("user", "prompt"),), config, request_id="case-1")
        assert completions.calls == 1
        assert [(item.attempt_number, item.status) for item in attempts.items] == [
            (1, "reserved"),
            (1, "retryable_failure"),
        ]
        snapshot = await transport._ledger.snapshot()
        assert snapshot.unresolved_request_ids == ("case-1:attempt-1",)

    asyncio.run(scenario())
