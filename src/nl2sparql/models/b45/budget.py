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
    """The maximum amount reserved for one remote request.

    Attributes:
        request_id: Stable identifier for the remote request.
        maximum_cost_usd: Conservative Decimal ceiling held against the budget.
    """

    request_id: str
    maximum_cost_usd: Decimal


@dataclass(frozen=True)
class BudgetSnapshot:
    """An immutable view of ledger state after one accounting operation.

    Attributes:
        cap_usd: Configured maximum total spend in USD.
        spent_usd: Authoritative Decimal costs reconciled so far.
        reserved_usd: Decimal ceilings retained for unresolved requests.
        remaining_usd: Cap less spent and reserved amounts; can be negative only
            after an externally reported pricing violation.
        unresolved_request_ids: Sorted identifiers of requests without a final
            authoritative cost.
    """

    cap_usd: Decimal
    spent_usd: Decimal
    reserved_usd: Decimal
    remaining_usd: Decimal
    unresolved_request_ids: tuple[str, ...]


def conservative_request_cost(messages: tuple[ChatMessage, ...], config: LargeLLMConfig) -> Decimal:
    """Return the maximum billable price using UTF-8 prompt bytes and max output tokens.

    Args:
        messages: Validated chat messages whose UTF-8 content bytes form the
            prompt-cost estimate.
        config: Pinned provider prices and maximum completion-token count.

    Returns:
        The conservative Decimal cost ceiling that a reservation must hold.
    """
    prompt_bytes = sum(len(message.content.encode("utf-8")) for message in messages)
    prompt = Decimal(prompt_bytes) * config.provider.prompt_price_per_million_usd / MILLION
    output = Decimal(config.max_tokens) * config.provider.completion_price_per_million_usd / MILLION
    return prompt + output


class BudgetLedger:
    """Serialize remote-request accounting under a fixed, concurrent budget cap.

    Args:
        config: Validated configuration defining provider pricing and the maximum
            permitted cumulative cost.

    Accepted reservations always satisfy ``spent_usd + reserved_usd <= cap_usd``.
    """

    def __init__(self, config: LargeLLMConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._reservations: dict[str, BudgetReservation] = {}
        self._held_reasons: dict[str, str] = {}
        self._request_ids: set[str] = set()
        self._spent_usd = _ZERO
        self._stop_reason: str | None = None

    @property
    def config_sha256(self) -> str:
        """Return the canonical fingerprint of this ledger's configuration.

        Returns:
            The SHA-256 digest for every run-affecting setting used by this
            ledger's reservations.
        """
        return self._config.sha256

    async def reserve(
        self, request_id: str, messages: tuple[ChatMessage, ...]
    ) -> BudgetReservation | None:
        """Reserve a conservative maximum cost, or reject work that exceeds the cap.

        Args:
            request_id: Unique stable identifier for the remote request.
            messages: Validated prompt messages used to calculate the reservation.

        Returns:
            The accepted reservation, or ``None`` when the cap would be exceeded
            or a permanent pricing-violation stop is active.

        Raises:
            LargeLLMError: If ``request_id`` was already used by this ledger.
        """
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
        """Replace a reservation with the provider's authoritative cost.

        Args:
            reservation: The active reservation issued by this ledger.
            actual_cost_usd: Finite non-negative Decimal cost reported by the
                provider.

        Returns:
            A snapshot after removing the reservation and recording the actual
            cost.

        Raises:
            LargeLLMError: If the cost is invalid or the reservation is foreign or
                no longer active.

        If the actual cost exceeds its reserved ceiling, it is still recorded, and
        the ledger permanently stops later reservations for a pricing violation.
        """
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
        """Keep a request's full reservation when its authoritative cost is unknown.

        Args:
            reservation: The active reservation whose cost remains unresolved.
            reason: Diagnostic reason the provider's authoritative cost is absent.

        Returns:
            A snapshot retaining the reservation's full cost ceiling.

        Raises:
            LargeLLMError: If the reservation is foreign or no longer active.
        """
        async with self._lock:
            self._require_active_reservation(reservation)
            self._held_reasons[reservation.request_id] = reason
            return self._snapshot_unlocked()

    async def snapshot(self) -> BudgetSnapshot:
        """Return one lock-consistent view of the current budget state.

        Returns:
            The current immutable budget snapshot with sorted unresolved IDs.
        """
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
