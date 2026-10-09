"""Workflow tests for offline-safe Stage A v2 generation."""

from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path

from click.testing import CliRunner


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
