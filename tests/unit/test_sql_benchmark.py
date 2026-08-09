from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from nl2sparql.sql.benchmark import (
    BENCHMARK_CASES,
    TOTAL_BENCHMARK_BYTES_CAP,
    BenchmarkError,
    BenchmarkPreflight,
    dry_run_benchmark,
    execute_benchmark,
    validate_benchmark_cases,
)
from nl2sparql.sql.label_layer import DEFAULT_MAXIMUM_BYTES_BILLED

EXPECTED_CASE_IDS = (
    "label_contract",
    "transaction_count",
    "block_count",
    "contract_dimension_contract",
    "labeled_transaction_cardinality",
    "labeled_token_transfer_contract",
)


def test_committed_benchmark_has_six_stable_machine_assertions() -> None:
    validate_benchmark_cases()

    assert tuple(case.case_id for case in BENCHMARK_CASES) == EXPECTED_CASE_IDS
    assert len({case.description for case in BENCHMARK_CASES}) == 6
    assert {case.difficulty for case in BENCHMARK_CASES} == {
        "small",
        "simple",
        "complex",
    }
    for case in BENCHMARK_CASES:
        assert case.sql.lstrip().upper().startswith(("SELECT", "WITH"))
        assert re.search(r"\bpassed\b", case.sql, re.IGNORECASE)
        assert (
            re.search(
                r"\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE)\b", case.sql, re.IGNORECASE
            )
            is None
        )


def test_fact_cases_pin_the_approved_half_open_window() -> None:
    for case in BENCHMARK_CASES[1:]:
        assert "DATE '2026-07-01'" in case.sql
    for case in (
        BENCHMARK_CASES[1],
        BENCHMARK_CASES[2],
        BENCHMARK_CASES[4],
        BENCHMARK_CASES[5],
    ):
        assert "DATE '2026-05-31'" in case.sql


def test_cases_use_only_fully_qualified_managed_interfaces() -> None:
    sql = "\n".join(case.sql for case in BENCHMARK_CASES)

    for object_name in (
        "entity_labels_v1",
        "transaction_facts",
        "block_facts",
        "contract_dimension",
        "labeled_transactions",
        "labeled_token_transfers",
    ):
        assert f"`nl2sparql-thesis.nl2sparql_analytics.{object_name}`" in sql
    assert "`bigquery-public-data." not in sql


def test_cases_encode_historical_counts_and_precision_invariants() -> None:
    cases = {case.case_id: case.sql for case in BENCHMARK_CASES}

    assert "5135" in cases["label_contract"]
    assert "14" in cases["label_contract"]
    assert "5091" in cases["label_contract"]
    assert "30" in cases["label_contract"]
    assert "65621456" in cases["transaction_count"]
    assert "222310" in cases["block_count"]
    assert "COUNT(DISTINCT address)" in cases["contract_dimension_contract"]
    assert "65621456" in cases["labeled_transaction_cardinality"]
    token_sql = cases["labeled_token_transfer_contract"]
    assert "125320919" in token_sql
    assert "value_cast_valid IS NOT TRUE" in token_sql
    assert "is_erc20 IS NOT TRUE" in token_sql
    assert "COALESCE(is_erc721, FALSE) IS NOT FALSE" in token_sql
    assert "token_decimals NOT BETWEEN 0 AND 38" in token_sql


def test_benchmark_caps_are_stricter_in_aggregate_than_six_query_caps() -> None:
    assert DEFAULT_MAXIMUM_BYTES_BILLED == 53_687_091_200
    assert TOTAL_BENCHMARK_BYTES_CAP == 107_374_182_400
    assert TOTAL_BENCHMARK_BYTES_CAP < len(BENCHMARK_CASES) * DEFAULT_MAXIMUM_BYTES_BILLED


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "duplicate"),
        ("unbounded", "approved date bounds"),
        ("mutation", "read-only"),
        ("no_assertion", "passed"),
    ],
)
def test_case_validation_fails_closed(mutation: str, message: str) -> None:
    cases = list(BENCHMARK_CASES)
    if mutation == "duplicate":
        cases[1] = cases[0]
    elif mutation == "unbounded":
        cases[1] = cases[1].__class__(
            case_id=cases[1].case_id,
            description=cases[1].description,
            difficulty=cases[1].difficulty,
            sql="SELECT TRUE AS passed",
            requires_window=True,
        )
    elif mutation == "mutation":
        cases[0] = cases[0].__class__(
            case_id=cases[0].case_id,
            description=cases[0].description,
            difficulty=cases[0].difficulty,
            sql="DELETE FROM `p.d.t` WHERE TRUE; SELECT TRUE AS passed",
            requires_window=False,
        )
    else:
        cases[0] = cases[0].__class__(
            case_id=cases[0].case_id,
            description=cases[0].description,
            difficulty=cases[0].difficulty,
            sql="SELECT TRUE AS ok",
            requires_window=False,
        )

    with pytest.raises(BenchmarkError, match=message):
        validate_benchmark_cases(tuple(cases))


class FakeBenchmarkJob:
    def __init__(
        self,
        *,
        estimated_bytes: int = 0,
        rows=(),
        processed_bytes: int = 0,
        billed_bytes: int = 0,
        slot_millis: int = 0,
        cache_hit: bool = False,
    ) -> None:
        self.total_bytes_processed = estimated_bytes or processed_bytes
        self.total_bytes_billed = billed_bytes
        self.slot_millis = slot_millis
        self.cache_hit = cache_hit
        self.started = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        self.ended = self.started + timedelta(milliseconds=125)
        self._rows = rows

    def result(self):
        return self._rows


class FakeBenchmarkClient:
    def __init__(
        self,
        *,
        estimates: dict[str, int] | None = None,
        result_overrides: dict[str, list[SimpleNamespace]] | None = None,
    ) -> None:
        self.estimates = estimates or {
            case.case_id: (index + 1) * 1_000_000 for index, case in enumerate(BENCHMARK_CASES)
        }
        self.result_overrides = result_overrides or {}
        self.calls: list[tuple[str, object]] = []

    def query(self, sql: str, *, job_config, location: str):
        case = next(case for case in BENCHMARK_CASES if case.sql == sql)
        mode = "dry_run" if job_config.dry_run else "execute"
        self.calls.append((mode, job_config))
        if job_config.dry_run:
            return FakeBenchmarkJob(estimated_bytes=self.estimates[case.case_id])
        rows = self.result_overrides.get(
            case.case_id,
            [SimpleNamespace(passed=True, observed_count=42)],
        )
        return FakeBenchmarkJob(
            rows=rows,
            processed_bytes=self.estimates[case.case_id],
            billed_bytes=self.estimates[case.case_id],
            slot_millis=250,
        )


def test_dry_run_preflight_enforces_configs_and_sums_estimates() -> None:
    client = FakeBenchmarkClient()

    preflight = dry_run_benchmark(client)

    assert isinstance(preflight, BenchmarkPreflight)
    assert tuple(result.case_id for result in preflight.cases) == EXPECTED_CASE_IDS
    assert preflight.total_estimated_bytes == 21_000_000
    assert len(client.calls) == 6
    for mode, config in client.calls:
        assert mode == "dry_run"
        assert config.dry_run is True
        assert config.use_query_cache is False
        assert config.use_legacy_sql is False
        assert config.maximum_bytes_billed == DEFAULT_MAXIMUM_BYTES_BILLED


def test_preflight_rejects_per_case_overflow() -> None:
    estimates = {case.case_id: 1 for case in BENCHMARK_CASES}
    estimates["contract_dimension_contract"] = DEFAULT_MAXIMUM_BYTES_BILLED + 1
    client = FakeBenchmarkClient(estimates=estimates)

    with pytest.raises(BenchmarkError, match="contract_dimension_contract.*50 GiB"):
        dry_run_benchmark(client)


def test_preflight_rejects_aggregate_overflow_before_any_execution() -> None:
    estimates = {case.case_id: 20_000_000_000 for case in BENCHMARK_CASES}
    client = FakeBenchmarkClient(estimates=estimates)

    with pytest.raises(BenchmarkError, match="aggregate.*100 GiB"):
        execute_benchmark(client)

    assert all(mode == "dry_run" for mode, _ in client.calls)


def test_execution_redry_runs_each_case_and_captures_result_job_metrics() -> None:
    client = FakeBenchmarkClient()
    ticks = iter(index * 1_000_000 for index in range(12))

    report = execute_benchmark(client, clock_ns=lambda: next(ticks))

    assert report.all_passed is True
    assert report.preflight.total_estimated_bytes == 21_000_000
    assert len(report.results) == 6
    assert [mode for mode, _ in client.calls] == ["dry_run"] * 6 + [
        item for _ in BENCHMARK_CASES for item in ("dry_run", "execute")
    ]
    first = report.results[0]
    assert first.case_id == "label_contract"
    assert first.passed is True
    assert first.diagnostics == {"observed_count": 42}
    assert first.estimated_bytes == 1_000_000
    assert first.processed_bytes == 1_000_000
    assert first.billed_bytes == 1_000_000
    assert first.wall_latency_ms == 1.0
    assert first.server_latency_ms == 125.0
    assert first.slot_millis == 250
    assert first.cache_hit is False
    for mode, config in client.calls:
        assert config.use_query_cache is False
        assert config.maximum_bytes_billed == DEFAULT_MAXIMUM_BYTES_BILLED
        assert config.dry_run is (mode == "dry_run")


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([SimpleNamespace(passed=False, reason="wrong")], "assertion failed"),
        ([SimpleNamespace(passed=None)], "boolean passed"),
        ([], "exactly one row"),
        ([SimpleNamespace(passed=True), SimpleNamespace(passed=True)], "exactly one row"),
    ],
)
def test_execution_fails_closed_for_invalid_result_rows(rows, message: str) -> None:
    client = FakeBenchmarkClient(result_overrides={"label_contract": rows})

    with pytest.raises(BenchmarkError, match=message):
        execute_benchmark(client)


def load_benchmark_script():
    script_path = Path("scripts/07_benchmark_sql_layer.py").resolve()
    spec = importlib.util.spec_from_file_location("benchmark_sql_layer_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_cli_defaults_to_dry_run_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_benchmark_script()
    client = FakeBenchmarkClient()
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: client)

    result = CliRunner().invoke(script.main, ["--project", "nl2sparql-thesis"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "dry-run"
    assert payload["total_estimated_bytes"] == 21_000_000
    assert len(payload["cases"]) == 6
    assert all(mode == "dry_run" for mode, _ in client.calls)


def test_benchmark_cli_executes_only_with_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_benchmark_script()
    client = FakeBenchmarkClient()
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: client)

    result = CliRunner().invoke(
        script.main,
        ["--project", "nl2sparql-thesis", "--execute"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "execute"
    assert payload["all_passed"] is True
    assert len(payload["results"]) == 6
    assert sum(mode == "execute" for mode, _ in client.calls) == 6


def test_benchmark_cli_exits_nonzero_on_budget_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_benchmark_script()
    estimates = {case.case_id: 1 for case in BENCHMARK_CASES}
    estimates["contract_dimension_contract"] = DEFAULT_MAXIMUM_BYTES_BILLED + 1
    client = FakeBenchmarkClient(estimates=estimates)
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: client)

    result = CliRunner().invoke(script.main, ["--project", "nl2sparql-thesis"])

    assert result.exit_code != 0
    assert "contract_dimension_contract" in result.output
    assert "50 GiB" in result.output
