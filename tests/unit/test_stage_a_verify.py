"""Tests for bounded BigQuery witness verification of Stage A records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.dataset.generate import (
    generate_stage_a_records,
    load_value_pools,
    validate_stage_a_records,
)
from nl2sparql.dataset.stage_a.diagnostics import (
    DiagnosticRecorder,
    ProjectBillingState,
    validate_diagnostic_report,
)
from nl2sparql.dataset.stage_a.planning import (
    build_single_witness_queries,
    build_stage_a_v2_witness_queries,
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
from nl2sparql.dataset.stage_a_v2 import (
    generate_stage_a_v2_records,
    validate_stage_a_v2_records,
)
from nl2sparql.dataset.templates import PER_TEMPLATE_BYTES_CAP, load_templates

V2_POOLS_PATH = Path("data/dataset/raw/stage-a-v2-evidence-pools.json")


def _v2_pools() -> dict[str, object]:
    return load_value_pools(V2_POOLS_PATH)


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
        self.job_id = "fake-job-id"
        self.location = "US"
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
        batch_rows: FakeRows | None = None,
        batch_cache_hit: bool = False,
        pair_batch_rows: FakeRows | None = None,
        pair_batch_cache_hit: bool = False,
    ) -> None:
        self.groups = build_witness_groups(records)
        self.groups_by_sql = {group.sql: group for group in self.groups}
        planned_queries = list(build_single_witness_queries(records))
        if any(record["template_id"] == "T_TX_BY_HASH" for record in records):
            planned_queries.extend(build_stage_a_v2_witness_queries(records))
        self.queries_by_sql = {query.sql: query for query in planned_queries}
        self.templates = {template["id"]: template for template in templates}
        self.estimates = estimates or {
            group.group_id: (index + 1) * 1_000_000 for index, group in enumerate(self.groups)
        }
        self.row_overrides = row_overrides or {}
        self.cache_hit_group = cache_hit_group
        self.batch_rows = batch_rows
        self.batch_cache_hit = batch_cache_hit
        self.pair_batch_rows = pair_batch_rows
        self.pair_batch_cache_hit = pair_batch_cache_hit
        self.records_by_id = {record["id"]: record for record in records}
        self.calls: list[tuple[str, str, object, str]] = []

    def query(self, sql: str, *, job_config, location: str) -> FakeJob:
        query = self.queries_by_sql[sql]
        group = self.groups_by_sql.get(sql)
        group_id = group.group_id if group is not None else query.group_ids[0]
        mode = "dry_run" if job_config.dry_run else "execute"
        self.calls.append((mode, group_id, job_config, location))
        estimate = self.estimates[group_id]
        if job_config.dry_run:
            return FakeJob(estimated_bytes=estimate)
        if query.proof_kind in {"tx_hash_batch", "account_pair_batch"}:
            columns = [
                "witness_group_id",
                *self.templates[query.template_id]["expected_columns"],
            ]
            rows = self.batch_rows if query.proof_kind == "tx_hash_batch" else self.pair_batch_rows
            if rows is None and query.proof_kind == "tx_hash_batch":
                groups_by_id = {item.group_id: item for item in self.groups}
                rows = FakeRows(
                    [
                        SimpleNamespace(
                            witness_group_id=group_id,
                            transaction_hash=self.records_by_id[
                                groups_by_id[group_id].witness_record_id
                            ]["slot_values"]["transaction_hash"],
                            block_timestamp=1,
                            from_address=1,
                            to_address=1,
                            value_wei=1,
                            is_success=True,
                        )
                        for group_id in reversed(query.group_ids)
                    ],
                    columns,
                )
            if rows is None:
                groups_by_id = {item.group_id: item for item in self.groups}
                rows = FakeRows(
                    [
                        SimpleNamespace(
                            witness_group_id=group_id,
                            transaction_hash="0x" + "1" * 64,
                            block_timestamp=1,
                            from_address=self.records_by_id[
                                groups_by_id[group_id].witness_record_id
                            ]["slot_values"]["account"],
                            to_address=self.records_by_id[groups_by_id[group_id].witness_record_id][
                                "slot_values"
                            ]["account_b"],
                            value_wei=1,
                        )
                        for group_id in reversed(query.group_ids)
                    ],
                    columns,
                )
            return FakeJob(
                estimated_bytes=estimate,
                rows=rows,
                cache_hit=(
                    self.batch_cache_hit
                    if query.proof_kind == "tx_hash_batch"
                    else self.pair_batch_cache_hit
                ),
            )
        assert group is not None
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


def test_batched_preflight_accounts_for_unique_physical_queries(
    templates: list[dict[str, object]],
) -> None:
    records = generate_stage_a_v2_records(templates, _v2_pools())
    estimates = {group.group_id: 800_000_000 for group in build_witness_groups(records)}
    default_client = FakeWitnessClient(records, templates, estimates=estimates)
    with pytest.raises(StageAVerificationError, match="aggregate.*96 GiB"):
        dry_run_witnesses(default_client, records)
    assert len(default_client.calls) == 206

    batched_client = FakeWitnessClient(records, templates, estimates=estimates)
    preflight = dry_run_witnesses(
        batched_client,
        records,
        query_planner=build_stage_a_v2_witness_queries,
    )

    assert len(preflight.witnesses) == 126
    assert len(batched_client.calls) == 126
    assert preflight.total_estimated_bytes == sum(
        item.estimated_bytes for item in preflight.witnesses
    )
    assert all(item.job_id and item.location == "US" for item in preflight.witnesses)


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
    recorder = DiagnosticRecorder(
        project_id="nl2sparql-thesis",
        records=records,
        verified_at="2026-08-09T12:00:00+00:00",
    )

    with pytest.raises(StageAVerificationError, match=message):
        verify_stage_a(
            client,
            records,
            templates,
            verified_at="2026-08-09T12:00:00+00:00",
            diagnostic_recorder=recorder,
        )
    assert recorder.failure_report()["failure"]["gate"] == "execution"


def test_witness_budget_constant_is_exactly_96_gib() -> None:
    assert TOTAL_WITNESS_BYTES_CAP == 96 * 2**30


def test_verifier_accepts_an_explicit_v2_validator_and_all_25_intents(
    templates: list[dict[str, object]],
) -> None:
    records = generate_stage_a_v2_records(templates, _v2_pools())
    client = FakeWitnessClient(records, templates)
    ticks = iter(index * 1_000_000 for index in range(len(client.groups) * 2))

    report = verify_stage_a(
        client,
        records,
        templates,
        verified_at="2026-10-09T12:00:00+00:00",
        record_validator=validate_stage_a_v2_records,
        clock_ns=lambda: next(ticks),
    )

    assert report.all_passed is True
    assert len({record["template_id"] for record in report.records}) == 25
    validate_stage_a_v2_records(report.records, templates)


def test_batched_verification_maps_shuffled_rows_to_all_logical_witnesses(
    templates: list[dict[str, object]],
) -> None:
    records = generate_stage_a_v2_records(templates, _v2_pools())
    client = FakeWitnessClient(records, templates)
    ticks = iter(index * 1_000_000 for index in range(126 * 2))

    report = verify_stage_a(
        client,
        records,
        templates,
        verified_at="2026-10-10T12:00:00+00:00",
        record_validator=validate_stage_a_v2_records,
        query_planner=build_stage_a_v2_witness_queries,
        clock_ns=lambda: next(ticks),
    )

    assert len(report.preflight.witnesses) == len(report.witnesses) == 126
    batch = next(item for item in report.witnesses if item.proof_kind == "tx_hash_batch")
    assert len(batch.group_ids) == len(batch.logical_results) == 45
    assert batch.immediate_dry_run is not None
    assert batch.immediate_dry_run.query_id == batch.query_id
    assert all(record["verification"]["non_empty"] is True for record in report.records)
    hash_records = [record for record in report.records if record["template_id"] == "T_TX_BY_HASH"]
    assert {record["verification"]["mode"] for record in hash_records} == {"live_exact"}
    assert all(
        record["verification"]["physical_query_id"] == batch.query_id for record in hash_records
    )
    pair_batches = [item for item in report.witnesses if item.proof_kind == "account_pair_batch"]
    assert len(pair_batches) == 4
    assert all(len(item.group_ids) == len(item.logical_results) == 10 for item in pair_batches)
    pair_records = [
        record for record in report.records if record["template_id"] == "T_TX_BETWEEN_ACCOUNTS"
    ]
    assert len({record["verification"]["physical_query_id"] for record in pair_records}) == 4


def test_verifier_emits_observational_diagnostic_events(
    templates: list[dict[str, object]],
) -> None:
    records = generate_stage_a_v2_records(templates, _v2_pools())
    client = FakeWitnessClient(records, templates)
    recorder = DiagnosticRecorder(
        project_id="nl2sparql-thesis",
        records=records,
        verified_at="2026-10-14T00:00:00+00:00",
    )
    recorder.record_billing_state(ProjectBillingState("nl2sparql-thesis", False, ""))
    ticks = iter(index * 1_000_000 for index in range(126 * 2))

    report = verify_stage_a(
        client,
        records,
        templates,
        verified_at="2026-10-14T00:00:00+00:00",
        clock_ns=lambda: next(ticks),
        record_validator=validate_stage_a_v2_records,
        query_planner=build_stage_a_v2_witness_queries,
        diagnostic_recorder=recorder,
    )
    diagnostic = recorder.complete()

    validate_diagnostic_report(diagnostic, records)
    assert len(report.witnesses) == diagnostic["summary"]["physical_query_count"] == 126
    assert diagnostic["summary"]["logical_witness_count"] == 206


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("missing", "membership"),
        ("duplicate", "duplicate"),
        ("unexpected", "unexpected"),
        ("wrong_hash", "transaction hash"),
        ("schema", "columns"),
        ("cache", "cache hit"),
    ],
)
def test_tx_hash_batch_fails_closed(
    templates: list[dict[str, object]], failure: str, message: str
) -> None:
    records = generate_stage_a_v2_records(templates, _v2_pools())
    groups = [
        group for group in build_witness_groups(records) if group.template_id == "T_TX_BY_HASH"
    ]
    columns = [
        "witness_group_id",
        "transaction_hash",
        "block_timestamp",
        "from_address",
        "to_address",
        "value_wei",
        "is_success",
    ]
    rows = [
        SimpleNamespace(
            witness_group_id=group.group_id,
            transaction_hash=next(
                record["slot_values"]["transaction_hash"]
                for record in records
                if record["id"] == group.witness_record_id
            ),
            block_timestamp=1,
            from_address=1,
            to_address=1,
            value_wei=1,
            is_success=True,
        )
        for group in groups
    ]
    schema = columns
    if failure == "missing":
        rows.pop()
    elif failure == "duplicate":
        rows.append(rows[0])
    elif failure == "unexpected":
        rows[0] = SimpleNamespace(**{**vars(rows[0]), "witness_group_id": "f" * 64})
    elif failure == "wrong_hash":
        rows[0] = SimpleNamespace(**{**vars(rows[0]), "transaction_hash": "0x" + "f" * 64})
    elif failure == "schema":
        schema = ["wrong"]
    client = FakeWitnessClient(
        records,
        templates,
        batch_rows=FakeRows(rows, schema),
        batch_cache_hit=failure == "cache",
    )

    with pytest.raises(StageAVerificationError, match=message):
        verify_stage_a(
            client,
            records,
            templates,
            verified_at="2026-10-10T12:00:00+00:00",
            record_validator=validate_stage_a_v2_records,
            query_planner=build_stage_a_v2_witness_queries,
        )


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("missing", "membership"),
        ("duplicate", "duplicate"),
        ("unexpected", "unexpected"),
        ("wrong_pair", "account pair"),
        ("schema", "columns"),
        ("cache", "cache hit"),
    ],
)
def test_account_pair_batch_fails_closed(
    templates: list[dict[str, object]], failure: str, message: str
) -> None:
    records = generate_stage_a_v2_records(templates, _v2_pools())
    queries = build_stage_a_v2_witness_queries(records)
    batch = next(query for query in queries if query.proof_kind == "account_pair_batch")
    groups_by_id = {group.group_id: group for group in build_witness_groups(records)}
    records_by_id = {record["id"]: record for record in records}
    columns = [
        "witness_group_id",
        "transaction_hash",
        "block_timestamp",
        "from_address",
        "to_address",
        "value_wei",
    ]
    rows = []
    for group_id in batch.group_ids:
        record = records_by_id[groups_by_id[group_id].witness_record_id]
        slots = record["slot_values"]
        rows.append(
            SimpleNamespace(
                witness_group_id=group_id,
                transaction_hash="0x" + "1" * 64,
                block_timestamp=1,
                from_address=slots["account"],
                to_address=slots["account_b"],
                value_wei=1,
            )
        )
    schema = columns
    if failure == "missing":
        rows.pop()
    elif failure == "duplicate":
        rows.append(rows[0])
    elif failure == "unexpected":
        rows[0] = SimpleNamespace(**{**vars(rows[0]), "witness_group_id": "f" * 64})
    elif failure == "wrong_pair":
        rows[0] = SimpleNamespace(
            **{
                **vars(rows[0]),
                "from_address": "0x" + "a" * 40,
                "to_address": "0x" + "b" * 40,
            }
        )
    elif failure == "schema":
        schema = ["wrong"]
    client = FakeWitnessClient(
        records,
        templates,
        pair_batch_rows=FakeRows(rows, schema),
        pair_batch_cache_hit=failure == "cache",
    )
    recorder = DiagnosticRecorder(
        project_id="nl2sparql-thesis",
        records=records,
        verified_at="2026-10-10T12:00:00+00:00",
    )

    with pytest.raises(StageAVerificationError, match=message):
        verify_stage_a(
            client,
            records,
            templates,
            verified_at="2026-10-10T12:00:00+00:00",
            record_validator=validate_stage_a_v2_records,
            query_planner=build_stage_a_v2_witness_queries,
            diagnostic_recorder=recorder,
        )
    assert recorder.failure_report()["failure"]["gate"] == "execution"
