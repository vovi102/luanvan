from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import LargeLLMConfig, LargeLLMError, ProviderPolicy
from nl2sparql.models.b45.budget import BudgetLedger, BudgetReservation, conservative_request_cost


def config(cap: str = "0.001") -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("1"),
            completion_price_per_million_usd=Decimal("1"),
        ),
        max_cost_usd=Decimal(cap),
    )


def test_conservative_cost_counts_utf8_bytes_and_maximum_output() -> None:
    messages = (ChatMessage("system", "\u0111"), ChatMessage("user", "x"))

    assert conservative_request_cost(messages, config()) == Decimal("0.000515")


def test_ledger_exposes_read_only_config_fingerprint() -> None:
    selected_config = config()
    ledger = BudgetLedger(selected_config)

    assert ledger.config_sha256 == selected_config.sha256
    with pytest.raises(AttributeError):
        ledger.config_sha256 = "0" * 64  # type: ignore[misc]


def test_reservation_reconciles_authoritative_cost() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.001"))
        messages = (ChatMessage("user", "x"),)
        reservation = await ledger.reserve("case-1", messages)
        assert reservation is not None
        snapshot = await ledger.reconcile(reservation, Decimal("0.0002"))
        assert snapshot.spent_usd == Decimal("0.0002")
        assert snapshot.reserved_usd == Decimal("0")
        assert snapshot.remaining_usd == Decimal("0.0008")
        assert snapshot.unresolved_request_ids == ()
        assert snapshot.spent_usd + snapshot.reserved_usd <= snapshot.cap_usd

    asyncio.run(scenario())


def test_concurrent_workers_cannot_oversubscribe_cap() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.0011"))
        messages = (ChatMessage("user", "x"),)
        reservations = await asyncio.gather(
            *(ledger.reserve(f"case-{index}", messages) for index in range(3))
        )
        accepted = [item for item in reservations if item is not None]
        snapshot = await ledger.snapshot()
        assert len(accepted) == 2
        assert snapshot.spent_usd + snapshot.reserved_usd <= snapshot.cap_usd
        assert snapshot.unresolved_request_ids == ("case-0", "case-1")

    asyncio.run(scenario())


def test_unknown_cost_holds_reservation_and_blocks_future_spend() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.001"))
        messages = (ChatMessage("user", "x"),)
        reservation = await ledger.reserve("case-1", messages)
        assert reservation is not None
        snapshot = await ledger.hold(reservation, "missing_usage_cost")
        assert snapshot.unresolved_request_ids == ("case-1",)
        assert await ledger.reserve("case-2", messages) is None

    asyncio.run(scenario())


def test_cancelled_waiter_does_not_corrupt_budget_state() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.0011"))
        messages = (ChatMessage("user", "x"),)
        await ledger._lock.acquire()
        waiting = asyncio.create_task(ledger.reserve("cancelled", messages))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        ledger._lock.release()

        reservation = await ledger.reserve("accepted", messages)
        assert reservation is not None
        snapshot = await ledger.snapshot()
        assert snapshot.unresolved_request_ids == ("accepted",)
        assert snapshot.spent_usd + snapshot.reserved_usd <= snapshot.cap_usd

    asyncio.run(scenario())


def test_duplicate_request_id_is_rejected() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config())
        messages = (ChatMessage("user", "x"),)
        assert await ledger.reserve("case-1", messages) is not None
        with pytest.raises(LargeLLMError, match="duplicate"):
            await ledger.reserve("case-1", messages)

    asyncio.run(scenario())


def test_reconciliation_rejects_finalized_or_foreign_reservations() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config())
        messages = (ChatMessage("user", "x"),)
        reservation = await ledger.reserve("case-1", messages)
        assert reservation is not None
        await ledger.reconcile(reservation, Decimal("0.0002"))
        with pytest.raises(LargeLLMError, match="active"):
            await ledger.reconcile(reservation, Decimal("0.0002"))
        forged = BudgetReservation("case-1", reservation.maximum_cost_usd)
        with pytest.raises(LargeLLMError, match="active"):
            await ledger.hold(forged, "missing_usage_cost")

    asyncio.run(scenario())


@pytest.mark.parametrize("cost", [Decimal("-0.0001"), Decimal("NaN"), Decimal("Infinity")])
def test_reconciliation_rejects_invalid_authoritative_cost(cost: Decimal) -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config())
        reservation = await ledger.reserve("case-1", (ChatMessage("user", "x"),))
        assert reservation is not None
        with pytest.raises(LargeLLMError, match="cost"):
            await ledger.reconcile(reservation, cost)

    asyncio.run(scenario())


def test_over_ceiling_cost_stops_all_future_reservations() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config())
        messages = (ChatMessage("user", "x"),)
        reservation = await ledger.reserve("case-1", messages)
        assert reservation is not None
        snapshot = await ledger.reconcile(reservation, Decimal("0.0006"))
        assert snapshot.spent_usd == Decimal("0.0006")
        assert snapshot.reserved_usd == Decimal("0")
        assert await ledger.reserve("case-2", messages) is None

    asyncio.run(scenario())
