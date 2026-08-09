"""Tests for bounded BigQuery witness verification of Stage A records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from nl2sparql.dataset.generate import (
    generate_stage_a_records,
    load_value_pools,
    validate_stage_a_records,
)
from nl2sparql.dataset.stage_a.verify import (
    TOTAL_WITNESS_BYTES_CAP,
    StageAVerificationError,
    StageAVerificationReport,
    WitnessPreflight,
    build_witness_groups,
    dry_run_witnesses,
    verify_stage_a,
)
from nl2sparql.dataset.templates import PER_TEMPLATE_BYTES_CAP, load_templates


@pytest.fixture(scope="module")
def templates() -> list[dict[str, object]]:
    return load_templates()


@pytest.fixture(scope="module")
def records(templates: list[dict[str, object]]) -> list[dict[str, object]]:
    return generate_stage_a_records(templates, load_value_pools())


class FakeRows(list):
    def __init__(self, rows: list[object], columns: list[str]) -> None:
        super().__init__(rows)
        self.schema = [SimpleNamespace(name=column) for column in columns]


class FakeJob:
    def __init__(
        self,
        *,
        estimated_bytes: int,
        rows: FakeRows | None = None,
        cache_hit: bool = False,
    ) -> None:
        self.total_bytes_processed = estimated_bytes
        self.total_bytes_billed = estimated_bytes
        self.slot_millis = 75
        self.cache_hit = cache_hit
        self.started = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        self.ended = self.started + timedelta(milliseconds=50)
        self._rows = rows

    def result(self) -> FakeRows:
        assert self._rows is not None
        return self._rows


class FakeWitnessClient:
    def __init__(
        self,
        records: list[dict[str, object]],
        templates: list[dict[str, object]],
        *,
        estimates: dict[str, int] | None = None,
        row_overrides: dict[str, FakeRows] | None = None,
        cache_hit_group: str | None = None,
    ) -> None:
        self.groups = build_witness_groups(records)
        self.groups_by_sql = {group.sql: group for group in self.groups}
        self.templates = {template["id"]: template for template in templates}
        self.estimates = estimates or {
            group.group_id: (index + 1) * 1_000_000 for index, group in enumerate(self.groups)
        }
        self.row_overrides = row_overrides or {}
        self.cache_hit_group = cache_hit_group
        self.calls: list[tuple[str, str, object, str]] = []

    def query(self, sql: str, *, job_config, location: str) -> FakeJob:
        group = self.groups_by_sql[sql]
        mode = "dry_run" if job_config.dry_run else "execute"
        self.calls.append((mode, group.group_id, job_config, location))
        estimate = self.estimates[group.group_id]
        if job_config.dry_run:
            return FakeJob(estimated_bytes=estimate)
        template = self.templates[group.template_id]
        columns = list(template["expected_columns"])
        values = {column: 1 for column in columns}
        rows = self.row_overrides.get(
            group.group_id,
            FakeRows([SimpleNamespace(**values)], columns),
        )
        return FakeJob(
            estimated_bytes=estimate,
            rows=rows,
            cache_hit=group.group_id == self.cache_hit_group,
        )


def test_witness_planner_uses_singletons_or_limit_monotonic_groups(
    records: list[dict[str, object]],
) -> None:
    groups = build_witness_groups(records)
    repeated = next(group for group in groups if group.template_id == "T_REPEATED_PAIR_FLOW")
    count_groups = [group for group in groups if group.template_id == "T_COUNT_TX_IN_RANGE"]

    assert repeated.proof_mode == "live_limit_monotonic"
    assert repeated.witness_record_id == next(
        record["id"]
        for record in records
        if record["template_id"] == "T_REPEATED_PAIR_FLOW" and record["slot_values"]["n"] == 1
    )
    assert len(repeated.member_record_ids) == 100
    assert len(count_groups) == 59
    assert all(group.proof_mode == "live_exact" for group in count_groups)
    assert all(len(group.member_record_ids) == 1 for group in count_groups)


def test_witness_planner_rejects_grouping_differences_beyond_limit(
    records: list[dict[str, object]],
) -> None:
    selected = [
        dict(record) for record in records if record["template_id"] == "T_REPEATED_PAIR_FLOW"
    ][:2]
    selected[1]["slot_values"] = dict(selected[1]["slot_values"])
    selected[1]["slot_values"]["start_date"] = "2026-06-14"
    selected[1]["witness_group_id"] = selected[0]["witness_group_id"]

    with pytest.raises(StageAVerificationError, match="only.*n"):
        build_witness_groups(selected)


def test_preflight_covers_every_group_with_strict_query_configs(
    records: list[dict[str, object]], templates: list[dict[str, object]]
) -> None:
    client = FakeWitnessClient(records, templates)

    preflight = dry_run_witnesses(client, records)

    assert isinstance(preflight, WitnessPreflight)
    assert len(preflight.witnesses) == len(build_witness_groups(records))
    assert preflight.total_estimated_bytes == sum(client.estimates.values())
    assert len(client.calls) == len(preflight.witnesses)
    for mode, _, config, location in client.calls:
        assert mode == "dry_run"
        assert location == "US"
        assert config.dry_run is True
        assert config.use_query_cache is False
        assert config.use_legacy_sql is False
        assert config.maximum_bytes_billed == PER_TEMPLATE_BYTES_CAP


def test_preflight_rejects_per_group_and_total_overflow(
    records: list[dict[str, object]], templates: list[dict[str, object]]
) -> None:
    groups = build_witness_groups(records)
    estimates = {group.group_id: 1 for group in groups}
    estimates[groups[2].group_id] = PER_TEMPLATE_BYTES_CAP + 1
    with pytest.raises(StageAVerificationError, match="20 GiB"):
        dry_run_witnesses(FakeWitnessClient(records, templates, estimates=estimates), records)

    aggregate_estimates = {group.group_id: 2_000_000_000 for group in groups}
    client = FakeWitnessClient(records, templates, estimates=aggregate_estimates)
    with pytest.raises(StageAVerificationError, match="aggregate.*96 GiB"):
        dry_run_witnesses(client, records)


def test_verification_preflights_all_then_redries_and_propagates_proofs(
    records: list[dict[str, object]], templates: list[dict[str, object]]
) -> None:
    client = FakeWitnessClient(records, templates)
    group_count = len(client.groups)
    ticks = iter(index * 1_000_000 for index in range(group_count * 2))

    report = verify_stage_a(
        client,
        records,
        templates,
        verified_at="2026-08-09T12:00:00+00:00",
        clock_ns=lambda: next(ticks),
    )

    assert isinstance(report, StageAVerificationReport)
    assert report.all_passed is True
    assert len(report.records) == 1000
    assert len(report.witnesses) == group_count
    assert [mode for mode, *_ in client.calls] == ["dry_run"] * group_count + [
        mode for _ in range(group_count) for mode in ("dry_run", "execute")
    ]
    assert all(record["verification"]["non_empty"] for record in report.records)
    assert {record["verification"]["mode"] for record in report.records} == {
        "live_exact",
        "live_limit_monotonic",
    }
    derived = next(
        record
        for record in report.records
        if record["verification"]["mode"] == "live_limit_monotonic"
    )
    assert derived["verification"]["witness_record_id"] != derived["id"]
    assert derived["verification"]["verified_at"] == "2026-08-09T12:00:00+00:00"
    first = report.witnesses[0]
    assert first.row_count == 1
    assert first.wall_latency_ms == 1.0
    assert first.server_latency_ms == 50.0
    assert first.slot_millis == 75
    assert first.cache_hit is False
    validate_stage_a_records(report.records, templates)


@pytest.mark.parametrize("failure", ["empty", "schema", "count", "cache"])
def test_verification_fails_closed_for_invalid_live_evidence(
    failure: str,
    records: list[dict[str, object]],
    templates: list[dict[str, object]],
) -> None:
    groups = build_witness_groups(records)
    if failure == "count":
        group = next(group for group in groups if group.template_id == "T_COUNT_TX_IN_RANGE")
        overrides = {
            group.group_id: FakeRows([SimpleNamespace(transaction_count=0)], ["transaction_count"])
        }
        message = "positive transaction_count"
        client = FakeWitnessClient(records, templates, row_overrides=overrides)
    else:
        group = groups[0]
        if failure == "empty":
            overrides = {group.group_id: FakeRows([], ["transaction_count"])}
            message = "non-empty"
            client = FakeWitnessClient(records, templates, row_overrides=overrides)
        elif failure == "schema":
            overrides = {group.group_id: FakeRows([SimpleNamespace(wrong=1)], ["wrong"])}
            message = "columns"
            client = FakeWitnessClient(records, templates, row_overrides=overrides)
        else:
            message = "cache hit"
            client = FakeWitnessClient(records, templates, cache_hit_group=group.group_id)

    with pytest.raises(StageAVerificationError, match=message):
        verify_stage_a(
            client,
            records,
            templates,
            verified_at="2026-08-09T12:00:00+00:00",
        )


def test_witness_budget_constant_is_exactly_96_gib() -> None:
    assert TOTAL_WITNESS_BYTES_CAP == 96 * 2**30
