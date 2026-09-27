import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from nl2sparql.evaluation.cli import create_cli


def test_all_help_paths_are_offline_and_never_construct_bigquery() -> None:
    calls = 0

    def forbidden_factory(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("BigQuery must remain lazy")

    cli = create_cli(bigquery_executor_factory=forbidden_factory)
    commands = (
        ["--help"],
        ["adapt", "--help"],
        ["adapt", "b0", "--help"],
        ["adapt", "b12", "--help"],
        ["adapt", "b45", "--help"],
        ["execute", "--help"],
        ["report", "--help"],
        ["compare", "--help"],
        ["validate", "--help"],
    )

    for args in commands:
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, (args, result.output)
    assert calls == 0


@pytest.mark.parametrize(
    "omitted",
    [
        "--allow-bigquery",
        "--executor",
        "--project",
        "--location",
        "--timeout-seconds",
        "--per-query-byte-cap",
        "--aggregate-byte-cap",
        "--aggregate-billed-byte-cap",
        "--estimated-cost-cap",
        "--pricing-id",
        "--price-per-tib",
        "--pricing-source-sha256",
    ],
)
def test_execute_rejects_missing_live_guard_as_stable_json_before_factory(
    tmp_path: Path, omitted: str
) -> None:
    called = False

    def forbidden_factory(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("must validate first")

    options = {
        "--prediction-run": str(tmp_path / "run.json"),
        "--output": str(tmp_path / "evidence.json"),
        "--journal": str(tmp_path / "journal.jsonl"),
        "--execution-id": "exec-1",
        "--executor": "bigquery",
        "--allow-bigquery": None,
        "--project": "project",
        "--location": "EU",
        "--timeout-seconds": "30",
        "--per-query-byte-cap": "1000",
        "--aggregate-byte-cap": "2000",
        "--aggregate-billed-byte-cap": "2000",
        "--estimated-cost-cap": "1",
        "--pricing-id": "2026-09",
        "--price-per-tib": "5",
        "--pricing-source-sha256": "a" * 64,
    }
    args = ["execute"]
    for option, value in options.items():
        if option == omitted:
            continue
        args.append(option)
        if value is not None:
            args.append(value)

    result = CliRunner().invoke(create_cli(bigquery_executor_factory=forbidden_factory), args)

    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "failed"
    assert called is False


def test_validate_is_offline_and_emits_canonical_status(tmp_path: Path) -> None:
    called = False

    def forbidden_factory(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("offline command accessed BigQuery")

    missing = tmp_path / "missing.json"
    result = CliRunner().invoke(
        create_cli(bigquery_executor_factory=forbidden_factory),
        ["validate", str(missing)],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "failed"
    assert called is False
