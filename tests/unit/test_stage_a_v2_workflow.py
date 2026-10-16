"""Workflow tests for offline-safe Stage A v2 generation."""

from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from nl2sparql.dataset.generate import load_value_pools
from nl2sparql.dataset.stage_a_v2 import generate_stage_a_v2_records
from nl2sparql.dataset.templates import load_templates


def _load_script():
    path = Path("scripts/09_generate_stage_a_v2.py").resolve()
    spec = importlib.util.spec_from_file_location("generate_stage_a_v2_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_cli_never_imports_google_or_constructs_a_provider(
    tmp_path: Path, monkeypatch
) -> None:
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "google" or name.startswith("google."):
            raise AssertionError("offline Stage A v2 must not import Google provider modules")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    script = _load_script()
    targets = tuple(tmp_path / name for name in ("candidate.jsonl", "manifest.json", "stats.md"))
    result = CliRunner().invoke(
        script.main,
        [
            "--value-pools",
            "data/dataset/raw/stage-a-v2-evidence-pools.json",
            "--output",
            str(targets[0]),
            "--config",
            str(targets[1]),
            "--stats",
            str(targets[2]),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["lifecycle_state"] == "candidate"
    assert summary["acceptance_eligible"] is False
    assert summary["record_count"] == 1000
    assert summary["represented_intent_count"] == 25
    assert all(path.exists() for path in targets)


def test_offline_cli_requires_explicit_relationship_evidence_before_writing(
    tmp_path: Path,
) -> None:
    script = _load_script()
    targets = tuple(tmp_path / name for name in ("candidate.jsonl", "manifest.json", "stats.md"))

    result = CliRunner().invoke(
        script.main,
        [
            "--output",
            str(targets[0]),
            "--config",
            str(targets[1]),
            "--stats",
            str(targets[2]),
        ],
    )

    assert result.exit_code != 0
    assert "account_pair" in result.output
    assert not any(path.exists() for path in targets)


def test_live_cli_rejects_default_candidate_values_before_provider_import(monkeypatch) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_run_live",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider must not initialize without evidence-backed values")
        ),
    )

    result = CliRunner().invoke(script.main, ["--live"])

    assert result.exit_code != 0
    assert "evidence-backed" in result.output


def test_offline_cli_blocks_google_imports_in_a_fresh_process(tmp_path: Path) -> None:
    targets = tuple(tmp_path / name for name in ("candidate.jsonl", "manifest.json", "stats.md"))
    guard = """
import importlib.abc
import runpy
import sys

class BlockGoogle(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'google' or fullname.startswith('google.'):
            raise AssertionError(f'offline import: {fullname}')
        return None

sys.meta_path.insert(0, BlockGoogle())
sys.argv = [
    'scripts/09_generate_stage_a_v2.py',
    '--value-pools', 'data/dataset/raw/stage-a-v2-evidence-pools.json',
    '--output', sys.argv[1],
    '--config', sys.argv[2],
    '--stats', sys.argv[3],
]
runpy.run_path('scripts/09_generate_stage_a_v2.py', run_name='__main__')
"""

    result = subprocess.run(
        [sys.executable, "-c", guard, *(str(path) for path in targets)],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert all(path.exists() for path in targets)


class _DryRunClient:
    def __init__(self, estimated_bytes: int = 1) -> None:
        self.estimated_bytes = estimated_bytes
        self.calls: list[tuple[str, object, str]] = []

    def query(self, sql: str, *, job_config, location: str):
        assert job_config.dry_run is True
        self.calls.append((sql, job_config, location))
        return SimpleNamespace(
            total_bytes_processed=self.estimated_bytes,
            job_id=f"dry-{len(self.calls)}",
            location=location,
        )


def test_preflight_uses_126_dry_runs_and_writes_nothing(tmp_path: Path) -> None:
    script = _load_script()
    templates = load_templates()
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    records = generate_stage_a_v2_records(templates, pools)
    client = _DryRunClient()

    first = script._run_preflight(
        records,
        project="nl2sparql-thesis",
        location="US",
        client=client,
    )
    second = script._run_preflight(
        records,
        project="nl2sparql-thesis",
        location="US",
        client=_DryRunClient(),
    )

    assert first == second
    assert first["mode"] == "preflight"
    assert first["logical_witness_count"] == 206
    assert first["physical_query_count"] == len(client.calls) == 126
    assert first["total_estimated_bytes"] == 126
    assert first["per_query_bytes_cap"] == 20 * 2**30
    assert first["total_bytes_cap"] == 96 * 2**30
    assert not list(tmp_path.iterdir())


def test_preflight_and_live_are_mutually_exclusive_before_provider_use(monkeypatch) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_run_preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider initialized")),
    )
    monkeypatch.setattr(
        script,
        "_run_live",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider initialized")),
    )

    result = CliRunner().invoke(script.main, ["--preflight", "--live"])

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


@pytest.mark.parametrize(
    "flags",
    [
        ["--preflight", "--live"],
        ["--preflight", "--diagnostic"],
        ["--live", "--diagnostic"],
        ["--preflight", "--live", "--diagnostic"],
    ],
)
def test_execution_modes_are_mutually_exclusive_before_billing_or_provider_use(
    monkeypatch, flags: list[str]
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "require_unbilled_project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("billing queried")),
        raising=False,
    )

    result = CliRunner().invoke(script.main, flags)

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def _unbilled_runner(command, **_kwargs):
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(
            {
                "projectId": "nl2sparql-thesis",
                "billingEnabled": False,
                "billingAccountName": "",
            }
        ),
        stderr="",
    )


@pytest.mark.parametrize("mode", ["diagnostic", "live"])
def test_execution_billing_failure_happens_before_google_import_or_client_construction(
    tmp_path: Path, monkeypatch, mode: str
) -> None:
    script = _load_script()
    templates = load_templates()
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    records = generate_stage_a_v2_records(templates, pools)
    monkeypatch.setattr(
        script,
        "require_unbilled_project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            script.DiagnosticError("billing is enabled")
        ),
        raising=False,
    )
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "google" or name.startswith("google."):
            raise AssertionError("Google imported before the billing gate")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    if mode == "diagnostic":
        report_path = tmp_path / "diagnostic.json"
        with pytest.raises(script.StageAV2WorkflowError, match="billing"):
            script._run_diagnostic(
                records,
                templates,
                project="nl2sparql-thesis",
                location="US",
                report_path=report_path,
            )
        assert json.loads(report_path.read_text())["failure"]["gate"] == "billing_guard"
    else:
        with pytest.raises(script.StageAV2WorkflowError, match="billing"):
            script._run_live(
                records,
                templates,
                pools,
                project="nl2sparql-thesis",
                location="US",
                output_path=tmp_path / "accepted.jsonl",
                config_path=tmp_path / "accepted.json",
                stats_path=tmp_path / "accepted.md",
            )


def test_diagnostic_failure_writes_only_canonical_failure_report(
    tmp_path: Path, monkeypatch
) -> None:
    script = _load_script()
    templates = load_templates()
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    records = generate_stage_a_v2_records(templates, pools)
    report_path = tmp_path / "diagnostic.json"
    accepted = tuple(tmp_path / name for name in ("accepted.jsonl", "accepted.json", "accepted.md"))

    class FailingClient:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("quota exhausted")

    monkeypatch.setattr(
        script,
        "write_stage_a_v2_accepted_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("accepted writer called")),
    )
    monkeypatch.setattr(
        script,
        "write_stage_a_v2_candidate_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("candidate writer called")),
    )

    with pytest.raises(script.StageAV2WorkflowError, match="quota exhausted"):
        script._run_diagnostic(
            records,
            templates,
            project="nl2sparql-thesis",
            location="US",
            report_path=report_path,
            client=FailingClient(),
            billing_runner=_unbilled_runner,
        )

    report = json.loads(report_path.read_text())
    assert report["status"] == "failed"
    assert report["failure"]["gate"] == "initial_preflight"
    assert not any(path.exists() for path in accepted)


def test_diagnostic_provider_failure_is_recorded_before_client_construction(
    tmp_path: Path, monkeypatch
) -> None:
    script = _load_script()
    templates = load_templates()
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    records = generate_stage_a_v2_records(templates, pools)
    report_path = tmp_path / "diagnostic.json"
    real_import = builtins.__import__

    def failing_provider_import(name, *args, **kwargs):
        if name == "google.cloud" or name.startswith("google.cloud."):
            raise RuntimeError("provider unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_provider_import)

    with pytest.raises(script.StageAV2WorkflowError, match="provider unavailable"):
        script._run_diagnostic(
            records,
            templates,
            project="nl2sparql-thesis",
            location="US",
            report_path=report_path,
            billing_runner=_unbilled_runner,
        )

    report = json.loads(report_path.read_text())
    assert report["status"] == "failed"
    assert report["failure"]["gate"] == "provider_initialization"


def test_validate_diagnostic_report_mode_is_provider_free(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "diagnostic.json"
    report_path.write_text(json.dumps({"mode": "diagnostic"}))
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "google" or name.startswith("google."):
            raise AssertionError("validation must not import Google provider modules")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    script = _load_script()
    result = CliRunner().invoke(
        script.main,
        [
            "--validate-diagnostic-report",
            str(report_path),
            "--value-pools",
            "data/dataset/raw/stage-a-v2-evidence-pools.json",
        ],
    )

    assert result.exit_code != 0
    assert "schema" in result.output


def test_preflight_requires_evidence_backed_values_before_provider_use(monkeypatch) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_run_preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider initialized")),
    )

    result = CliRunner().invoke(script.main, ["--preflight"])

    assert result.exit_code != 0
    assert "evidence-backed" in result.output


def test_preflight_cap_failure_never_calls_artifact_writers(monkeypatch) -> None:
    script = _load_script()
    templates = load_templates()
    pools = load_value_pools(Path("data/dataset/raw/stage-a-v2-evidence-pools.json"))
    records = generate_stage_a_v2_records(templates, pools)
    monkeypatch.setattr(
        script,
        "write_stage_a_v2_accepted_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("accepted writer called")),
    )
    monkeypatch.setattr(
        script,
        "write_stage_a_v2_candidate_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("candidate writer called")),
    )

    with pytest.raises(script.StageAV2WorkflowError, match="20 GiB"):
        script._run_preflight(
            records,
            project="nl2sparql-thesis",
            location="US",
            client=_DryRunClient(estimated_bytes=20 * 2**30 + 1),
        )
