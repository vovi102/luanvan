"""Secret-safe, durable evidence for each live provider attempt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from nl2sparql.models.b45.budget import BudgetSnapshot
from nl2sparql.models.b45.contracts import LargeLLMError

AttemptStatus = Literal[
    "reserved",
    "retryable_failure",
    "completed",
    "terminal_failure",
    "cancelled",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class AttemptEvidence:
    """One immutable accounting transition for exactly one provider attempt.

    ``prompt_sha256`` is the only prompt-derived field.  The record deliberately
    has no raw provider error, request headers, response text, or credentials.
    """

    case_id: str
    request_id: str
    reservation_id: str
    attempt_number: int
    status: AttemptStatus
    prompt_sha256: str
    reservation_ceiling_usd: Decimal
    budget_checkpoint: BudgetSnapshot
    authoritative_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or _ID_RE.fullmatch(self.case_id) is None:
            raise LargeLLMError("attempt evidence case ID is invalid")
        if self.request_id != self.case_id:
            raise LargeLLMError("attempt evidence request ID must match its case ID")
        if (
            not isinstance(self.attempt_number, int)
            or isinstance(self.attempt_number, bool)
            or self.attempt_number <= 0
        ):
            raise LargeLLMError("attempt evidence number is invalid")
        prefix = f"{self.request_id}:attempt-{self.attempt_number}"
        if not isinstance(self.reservation_id, str) or not (
            self.reservation_id == prefix
            or re.fullmatch(re.escape(prefix) + r":resume-[1-9][0-9]*", self.reservation_id)
        ):
            raise LargeLLMError("attempt evidence reservation ID is invalid")
        if not isinstance(self.status, str) or self.status not in {
            "reserved",
            "retryable_failure",
            "completed",
            "terminal_failure",
            "cancelled",
        }:
            raise LargeLLMError("attempt evidence status is invalid")
        if (
            not isinstance(self.prompt_sha256, str)
            or _SHA256_RE.fullmatch(self.prompt_sha256) is None
        ):
            raise LargeLLMError("attempt evidence prompt fingerprint is invalid")
        if (
            not isinstance(self.reservation_ceiling_usd, Decimal)
            or not self.reservation_ceiling_usd.is_finite()
            or self.reservation_ceiling_usd < Decimal("0")
        ):
            raise LargeLLMError("attempt evidence reservation ceiling is invalid")
        if not isinstance(self.budget_checkpoint, BudgetSnapshot):
            raise LargeLLMError("attempt evidence budget checkpoint is invalid")
        if self.authoritative_cost_usd is not None and (
            not isinstance(self.authoritative_cost_usd, Decimal)
            or not self.authoritative_cost_usd.is_finite()
            or self.authoritative_cost_usd < Decimal("0")
        ):
            raise LargeLLMError("attempt evidence authoritative cost is invalid")
        unresolved = {
            reservation.request_id: reservation.maximum_cost_usd
            for reservation in self.budget_checkpoint.unresolved_reservations
        }
        is_held = unresolved.get(self.reservation_id) == self.reservation_ceiling_usd
        if self.status == "reserved":
            if (
                self.authoritative_cost_usd is not None
                or not is_held
                or self.budget_checkpoint.stop_reason is not None
            ):
                raise LargeLLMError("reserved attempt evidence must retain its exact ceiling")
        elif self.status in {"retryable_failure", "cancelled"}:
            if self.authoritative_cost_usd is not None:
                raise LargeLLMError(
                    f"{self.status} attempt evidence cannot claim authoritative cost"
                )
            if not is_held:
                raise LargeLLMError(f"{self.status} attempt evidence must retain its exact ceiling")
        elif self.status == "completed":
            if self.authoritative_cost_usd is None or self.reservation_id in unresolved:
                raise LargeLLMError("completed attempt evidence must reconcile its reservation")
        elif self.authoritative_cost_usd is None and not is_held:
            raise LargeLLMError("unresolved attempt evidence must retain its exact ceiling")
        elif self.authoritative_cost_usd is not None and self.reservation_id in unresolved:
            raise LargeLLMError("reconciled attempt evidence must not retain a reservation")
        if self.authoritative_cost_usd is not None:
            if self.budget_checkpoint.spent_usd < self.authoritative_cost_usd:
                raise LargeLLMError("attempt evidence cost exceeds checkpoint spend")
            if (
                self.authoritative_cost_usd > self.reservation_ceiling_usd
                and self.budget_checkpoint.stop_reason != "pricing_violation"
            ):
                raise LargeLLMError("attempt evidence cost exceeds its reservation ceiling")


class AttemptEvidenceSink(Protocol):
    """Durably receive each accounting transition before remote control advances."""

    def next_attempt_number(self, request_id: str) -> int:
        """Return the next 1-based attempt number for a base request ID."""

    async def append_attempt(self, evidence: AttemptEvidence) -> None:
        """Persist one validated attempt transition."""


class AttemptEvidencePersistenceError(RuntimeError):
    """Raised when durable attempt evidence cannot be persisted safely."""

    def __init__(self) -> None:
        super().__init__("attempt evidence persistence failed")
