"""Concurrent, hard-cap accounting for B4/B5 remote completions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45.contracts import LargeLLMConfig, LargeLLMError

MILLION = Decimal(1_000_000)
_ZERO = Decimal("0")


@dataclass(frozen=True)
class BudgetReservation:
    """The maximum amount reserved for one remote request."""

    request_id: str
    maximum_cost_usd: Decimal


@dataclass(frozen=True)
class BudgetSnapshot:
    """An immutable view of ledger state after one accounting operation."""

    cap_usd: Decimal
    spent_usd: Decimal
    reserved_usd: Decimal
    remaining_usd: Decimal
    unresolved_request_ids: tuple[str, ...]


def conservative_request_cost(
    messages: tuple[ChatMessage, ...], config: LargeLLMConfig
) -> Decimal:
    """Return the maximum billable price using UTF-8 prompt bytes and max output tokens."""
    prompt_bytes = sum(len(message.content.encode("utf-8")) for message in messages)
    prompt = Decimal(prompt_bytes) * config.provider.prompt_price_per_million_usd / MILLION
    output = Decimal(config.max_tokens) * config.provider.completion_price_per_million_usd / MILLION
    return prompt + output


class BudgetLedger:
    """Serialize reservations so concurrent requests cannot exceed a fixed budget cap."""

    def __init__(self, config: LargeLLMConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._reservations: dict[str, BudgetReservation] = {}
        self._held_reasons: dict[str, str] = {}
        self._request_ids: set[str] = set()
        self._spent_usd = _ZERO
        self._stop_reason: str | None = None

    async def reserve(
        self, request_id: str, messages: tuple[ChatMessage, ...]
    ) -> BudgetReservation | None:
        """Reserve a conservative maximum cost, or reject work that exceeds the cap."""
        async with self._lock:
            if self._stop_reason is not None:
                return None
            if request_id in self._request_ids:
                raise LargeLLMError(f"duplicate budget request ID: {request_id!r}")

            maximum_cost_usd = conservative_request_cost(messages, self._config)
            if (
                self._spent_usd + self._reserved_usd() + maximum_cost_usd
                > self._config.max_cost_usd
            ):
                return None

            reservation = BudgetReservation(request_id, maximum_cost_usd)
            self._request_ids.add(request_id)
            self._reservations[request_id] = reservation
            return reservation

    async def reconcile(
        self, reservation: BudgetReservation, actual_cost_usd: Decimal
    ) -> BudgetSnapshot:
        """Replace a reservation with the provider's authoritative, bounded cost."""
        if (
            not isinstance(actual_cost_usd, Decimal)
            or not actual_cost_usd.is_finite()
            or actual_cost_usd < _ZERO
        ):
            raise LargeLLMError("authoritative cost must be a finite non-negative Decimal")

        async with self._lock:
            self._require_active_reservation(reservation)
            del self._reservations[reservation.request_id]
            self._held_reasons.pop(reservation.request_id, None)
            self._spent_usd += actual_cost_usd
            if actual_cost_usd > reservation.maximum_cost_usd:
                self._stop_reason = "pricing_violation"
            return self._snapshot_unlocked()

    async def hold(self, reservation: BudgetReservation, reason: str) -> BudgetSnapshot:
        """Keep a request's full reservation when its authoritative cost is unknown."""
        async with self._lock:
            self._require_active_reservation(reservation)
            self._held_reasons[reservation.request_id] = reason
            return self._snapshot_unlocked()

    async def snapshot(self) -> BudgetSnapshot:
        """Return one lock-consistent view of the current budget state."""
        async with self._lock:
            return self._snapshot_unlocked()

    def _require_active_reservation(self, reservation: BudgetReservation) -> None:
        if not isinstance(reservation, BudgetReservation):
            raise LargeLLMError("budget reservation must be active")
        if self._reservations.get(reservation.request_id) is not reservation:
            raise LargeLLMError("budget reservation must be active")

    def _reserved_usd(self) -> Decimal:
        return sum(
            (reservation.maximum_cost_usd for reservation in self._reservations.values()),
            start=_ZERO,
        )

    def _snapshot_unlocked(self) -> BudgetSnapshot:
        reserved_usd = self._reserved_usd()
        return BudgetSnapshot(
            cap_usd=self._config.max_cost_usd,
            spent_usd=self._spent_usd,
            reserved_usd=reserved_usd,
            remaining_usd=self._config.max_cost_usd - self._spent_usd - reserved_usd,
            unresolved_request_ids=tuple(sorted(self._reservations)),
        )
