"""Concurrent, hard-cap accounting for B4/B5 remote completions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

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

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request_id, str)
            or not self.request_id.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in self.request_id)
        ):
            raise LargeLLMError("budget reservation request ID is invalid")
        if (
            not isinstance(self.maximum_cost_usd, Decimal)
            or not self.maximum_cost_usd.is_finite()
            or self.maximum_cost_usd < _ZERO
        ):
            raise LargeLLMError("budget reservation ceiling must be a non-negative Decimal")


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
        stop_reason: Durable public reason that later reservations are disabled,
            or ``None`` while reservations remain eligible.
        unresolved_reservations: Exact unresolved per-request ceilings retained
            for durable resume accounting.
    """

    cap_usd: Decimal
    spent_usd: Decimal
    reserved_usd: Decimal
    remaining_usd: Decimal
    unresolved_request_ids: tuple[str, ...]
    stop_reason: Literal["pricing_violation"] | None = None
    unresolved_reservations: tuple[BudgetReservation, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("budget cap", self.cap_usd),
            ("budget spent", self.spent_usd),
            ("budget reserved", self.reserved_usd),
        ):
            if not isinstance(value, Decimal) or not value.is_finite() or value < _ZERO:
                raise LargeLLMError(f"{label} must be a finite non-negative Decimal")
        if self.cap_usd <= _ZERO:
            raise LargeLLMError("budget cap must be positive")
        if not isinstance(self.remaining_usd, Decimal) or not self.remaining_usd.is_finite():
            raise LargeLLMError("budget remaining must be a finite Decimal")
        if self.remaining_usd < _ZERO and self.stop_reason != "pricing_violation":
            raise LargeLLMError("negative budget remaining requires pricing violation")
        if (
            not isinstance(self.unresolved_request_ids, tuple)
            or self.unresolved_request_ids != tuple(sorted(set(self.unresolved_request_ids)))
            or any(
                not isinstance(request_id, str)
                or not request_id.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in request_id)
                for request_id in self.unresolved_request_ids
            )
        ):
            raise LargeLLMError("budget unresolved request IDs are invalid")
        if (
            not isinstance(self.unresolved_reservations, tuple)
            or any(
                not isinstance(reservation, BudgetReservation)
                for reservation in self.unresolved_reservations
            )
            or self.unresolved_reservations
            != tuple(
                sorted(
                    self.unresolved_reservations,
                    key=lambda reservation: reservation.request_id,
                )
            )
        ):
            raise LargeLLMError("budget unresolved reservations are invalid")
        reservation_ids = tuple(
            reservation.request_id for reservation in self.unresolved_reservations
        )
        if reservation_ids != self.unresolved_request_ids:
            raise LargeLLMError("budget unresolved reservations must match request IDs")
        reserved = sum(
            (reservation.maximum_cost_usd for reservation in self.unresolved_reservations),
            start=_ZERO,
        )
        if reserved != self.reserved_usd:
            raise LargeLLMError("budget reserved total must match unresolved reservations")
        if self.remaining_usd != self.cap_usd - self.spent_usd - self.reserved_usd:
            raise LargeLLMError("budget remaining must match spent and reserved totals")
        if self.stop_reason is not None and self.stop_reason != "pricing_violation":
            raise LargeLLMError("budget stop reason is invalid")


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

    @classmethod
    def from_checkpoint(cls, config: LargeLLMConfig, checkpoint: BudgetSnapshot) -> BudgetLedger:
        """Restore durable spend and unresolved reservations before resume.

        Args:
            config: Current generation configuration whose cap must match the
                checkpoint.
            checkpoint: Validated budget state loaded from a durable journal.

        Returns:
            A new ledger that enforces the original spent, held, and stopped
            state before accepting more reservations.

        Raises:
            LargeLLMError: If the config/checkpoint pair is invalid or stale.
        """
        if not isinstance(config, LargeLLMConfig):
            raise LargeLLMError("budget checkpoint requires a LargeLLMConfig")
        if not isinstance(checkpoint, BudgetSnapshot):
            raise LargeLLMError("budget checkpoint is invalid")
        if checkpoint.cap_usd != config.max_cost_usd:
            raise LargeLLMError("budget checkpoint cap does not match config")

        ledger = cls(config)
        ledger._spent_usd = checkpoint.spent_usd
        ledger._stop_reason = checkpoint.stop_reason
        ledger._reservations = {
            reservation.request_id: reservation
            for reservation in checkpoint.unresolved_reservations
        }
        ledger._request_ids = set(checkpoint.unresolved_request_ids)
        return ledger

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
            stop_reason=self._stop_reason,
            unresolved_reservations=tuple(
                sorted(
                    self._reservations.values(),
                    key=lambda reservation: reservation.request_id,
                )
            ),
        )
