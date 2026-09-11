import asyncio
import hashlib
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import (
    BudgetLedger,
    BudgetReservation,
    BudgetSnapshot,
    LargeLLMConfig,
    LargeLLMError,
    ProviderPolicy,
    RequestJournal,
    load_resume_state,
)
from nl2sparql.models.b45.attempts import AttemptEvidence
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
