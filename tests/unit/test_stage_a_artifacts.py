"""Tests for Stage A artifact serialization and CLI orchestration."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from nl2sparql.dataset.generate import generate_stage_a_records, load_value_pools
from nl2sparql.dataset.stage_a.artifacts import (
    StageAArtifactError,
    build_generation_config,
    render_stats,
    write_stage_a_artifacts,
)
from nl2sparql.dataset.stage_a.verify import StageAVerificationError
from nl2sparql.dataset.templates import load_templates


@pytest.fixture(scope="module")
def templates() -> list[dict[str, object]]:
    return load_templates()


@pytest.fixture(scope="module")
def pools() -> dict[str, object]:
    return load_value_pools()


@pytest.fixture(scope="module")
def candidates(
    templates: list[dict[str, object]], pools: dict[str, object]
) -> list[dict[str, object]]:
    return generate_stage_a_records(templates, pools)


def fake_live_report(candidates: list[dict[str, object]]):
    records = copy.deepcopy(candidates)
    for record in records:
        record["verification"] = {
            "mode": "live_exact",
            "non_empty": True,
            "witness_group_id": record["witness_group_id"],
            "witness_record_id": record["id"],
            "witness_row_count": 1,
            "estimated_bytes": 10,
            "processed_bytes": 10,
            "billed_bytes": 10,
            "wall_latency_ms": 1.0,
            "server_latency_ms": 0.5,
            "slot_millis": 1,
            "cache_hit": False,
            "verified_at": "2026-08-09T12:00:00+00:00",
        }
    witness = SimpleNamespace(
        processed_bytes=123,
        billed_bytes=124,
        wall_latency_ms=5.0,
        cache_hit=False,
    )
    return SimpleNamespace(
        all_passed=True,
        records=tuple(records),
        witnesses=(witness,),
        preflight=SimpleNamespace(total_estimated_bytes=120),
    )


def test_offline_config_and_stats_are_deterministic(
    candidates: list[dict[str, object]],
    templates: list[dict[str, object]],
    pools: dict[str, object],
) -> None:
    first = build_generation_config(candidates, templates, pools)
    second = build_generation_config(candidates, templates, pools)
    stats = render_stats(candidates)

    assert first == second
    assert first["version"] == 1
    assert first["record_count"] == 1000
    assert first["generation_seed"] == 42
    assert first["verification_mode"] == "offline_candidates"
    assert len(first["artifact_sha256"]) == 64
    assert len(first["template_library_sha256"]) == 64
    assert len(first["value_pools_sha256"]) == 64
    assert "GoogleSQL Stage A Stats" in stats
    assert "offline_candidates" in stats
    assert "hard: 200" in stats
    assert "Maximum entity frequency: 30" in stats


def test_live_config_records_witness_metrics_without_double_counting(
    candidates: list[dict[str, object]],
    templates: list[dict[str, object]],
    pools: dict[str, object],
) -> None:
    report = fake_live_report(candidates)
    config = build_generation_config(report.records, templates, pools, report=report)
    stats = render_stats(report.records, report=report)

    assert config["verification_mode"] == "live_witness"
    assert config["verified_record_count"] == 1000
    assert config["witness_count"] == 1
    assert config["total_estimated_bytes"] == 120
    assert config["total_processed_bytes"] == 123
    assert config["total_billed_bytes"] == 124
    assert "live_witness" in stats
    assert "Witnesses: 1" in stats
    assert "Cache hits: 0" in stats


def test_artifact_writer_round_trips_all_outputs_atomically(
    tmp_path: Path,
    candidates: list[dict[str, object]],
    templates: list[dict[str, object]],
    pools: dict[str, object],
) -> None:
    output = tmp_path / "synthetic-stage-a.jsonl"
    config_path = tmp_path / "generation-config.json"
    stats_path = tmp_path / "stats.md"

    artifacts = write_stage_a_artifacts(
        candidates,
        templates,
        pools,
        output_path=output,
        config_path=config_path,
        stats_path=stats_path,
    )

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    config = json.loads(config_path.read_text())
    assert rows == candidates
    assert config["artifact_sha256"] == artifacts.artifact_sha256
    assert config["record_count"] == 1000
    assert stats_path.read_text().startswith("# GoogleSQL Stage A Stats\n")
    assert not list(tmp_path.glob("*.tmp"))


def test_artifacts_reject_mixed_or_failed_verification(
    candidates: list[dict[str, object]],
    templates: list[dict[str, object]],
    pools: dict[str, object],
) -> None:
    mixed = copy.deepcopy(candidates)
    mixed[0]["verification"] = {"non_empty": True}
    with pytest.raises(StageAArtifactError, match="mixed verification"):
        build_generation_config(mixed, templates, pools)

    report = fake_live_report(candidates)
    report.records[0]["verification"]["non_empty"] = False
    with pytest.raises(StageAArtifactError, match="non-empty"):
        build_generation_config(report.records, templates, pools, report=report)


def load_stage_a_script():
    script_path = Path("scripts/09_generate_stage_a.py").resolve()
    spec = importlib.util.spec_from_file_location("generate_stage_a_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_defaults_to_offline_without_bigquery_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load_stage_a_script()

    class ForbiddenClient:
        def __init__(self, **_: object) -> None:
            raise AssertionError("offline mode must not construct BigQuery")

    monkeypatch.setattr(script.bigquery, "Client", ForbiddenClient)
    paths = [tmp_path / "stage-a.jsonl", tmp_path / "config.json", tmp_path / "stats.md"]
    result = CliRunner().invoke(
        script.main,
        ["--output", str(paths[0]), "--config", str(paths[1]), "--stats", str(paths[2])],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "offline_candidates"
    assert payload["record_count"] == 1000
    assert all(path.exists() for path in paths)


def test_cli_live_writes_only_after_verifier_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidates: list[dict[str, object]],
) -> None:
    script = load_stage_a_script()
    report = fake_live_report(candidates)
    monkeypatch.setattr(script.bigquery, "Client", lambda **_: object())
    monkeypatch.setattr(script, "verify_stage_a", lambda *_args, **_kwargs: report)
    monkeypatch.setattr(script, "current_utc_timestamp", lambda: "2026-08-09T12:00:00+00:00")
    paths = [tmp_path / "stage-a.jsonl", tmp_path / "config.json", tmp_path / "stats.md"]
    args = [
        "--live",
        "--output",
        str(paths[0]),
        "--config",
        str(paths[1]),
        "--stats",
        str(paths[2]),
    ]
    result = CliRunner().invoke(script.main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "live_witness"
    assert all(path.exists() for path in paths)

    for path in paths:
        path.unlink()
    monkeypatch.setattr(
        script,
        "verify_stage_a",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(StageAVerificationError("boom")),
    )
    result = CliRunner().invoke(script.main, args)
    assert result.exit_code != 0
    assert "boom" in result.output
    assert all(not path.exists() for path in paths)
