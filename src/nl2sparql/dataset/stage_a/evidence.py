"""Provider-neutral witness evidence contracts and grouping rules."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class WitnessEvidenceError(ValueError):
    """Raised when records cannot form valid witness groups."""


@dataclass(frozen=True)
class WitnessGroup:
    group_id: str
    template_id: str
    witness_record_id: str
    member_record_ids: tuple[str, ...]
    sql: str
    proof_mode: str


@dataclass(frozen=True)
class WitnessDryRun:
    group_id: str
    template_id: str
    witness_record_id: str
    estimated_bytes: int


@dataclass(frozen=True)
class WitnessPreflight:
    witnesses: tuple[WitnessDryRun, ...]
    total_estimated_bytes: int


@dataclass(frozen=True)
class WitnessExecution:
    group_id: str
    template_id: str
    witness_record_id: str
    row_count: int
    columns: tuple[str, ...]
    estimated_bytes: int
    processed_bytes: int
    billed_bytes: int
    wall_latency_ms: float
    server_latency_ms: float | None
    slot_millis: int
    cache_hit: bool


@dataclass(frozen=True)
class StageAVerificationReport:
    preflight: WitnessPreflight
    witnesses: tuple[WitnessExecution, ...]
    records: tuple[dict[str, Any], ...]

    @property
    def all_passed(self) -> bool:
        return bool(self.records) and all(
            record.get("verification", {}).get("non_empty") is True for record in self.records
        )


def _grouped_slots(record: Mapping[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in record["slot_values"].items() if name != "n"}


def build_witness_groups(records: Sequence[Mapping[str, Any]]) -> tuple[WitnessGroup, ...]:
    """Group records only when their slots differ by a positive LIMIT value."""
    grouped: OrderedDict[str, list[Mapping[str, Any]]] = OrderedDict()
    for record in records:
        group_id = record.get("witness_group_id")
        if not isinstance(group_id, str) or not group_id:
            raise WitnessEvidenceError("Every record requires a witness_group_id")
        grouped.setdefault(group_id, []).append(record)
    groups: list[WitnessGroup] = []
    for group_id, members in grouped.items():
        template_ids = {member.get("template_id") for member in members}
        if len(template_ids) != 1:
            raise WitnessEvidenceError(f"Witness group {group_id} mixes templates")
        base_slots = _grouped_slots(members[0])
        if any(_grouped_slots(member) != base_slots for member in members[1:]):
            raise WitnessEvidenceError(f"Witness group {group_id} members may differ only by n")
        has_limit = all(
            isinstance(member["slot_values"].get("n"), int)
            and not isinstance(member["slot_values"].get("n"), bool)
            and member["slot_values"]["n"] > 0
            for member in members
        )
        if len(members) > 1 and not has_limit:
            raise WitnessEvidenceError(
                f"Witness group {group_id} members may differ only by positive n"
            )
        if has_limit:
            witness = min(members, key=lambda member: member["slot_values"]["n"])
            proof_mode = "live_limit_monotonic"
        else:
            witness = members[0]
            proof_mode = "live_exact"
        groups.append(
            WitnessGroup(
                group_id=group_id,
                template_id=str(witness["template_id"]),
                witness_record_id=str(witness["id"]),
                member_record_ids=tuple(str(member["id"]) for member in members),
                sql=str(witness["sql"]),
                proof_mode=proof_mode,
            )
        )
    return tuple(groups)
