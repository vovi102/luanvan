"""Operational tests only: no scientific readiness and no model/encoder calls."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/27_kaggle_b12_benchmark.py"


def driver():
    assert SCRIPT.is_file(), "benchmark driver missing"
    spec = importlib.util.spec_from_file_location("benchmark_driver", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_notebook_has_no_effects(tmp_path, monkeypatch):
    import builtins
    import socket

    original = builtins.__import__

    def forbidden(*args, **kwargs):
        raise AssertionError("default notebook attempted a side effect")

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {
            "torch",
            "transformers",
            "sentence_transformers",
            "huggingface_hub",
            "kaggle_secrets",
            "kaggle",
        }:
            forbidden()
        return original(name, *args, **kwargs)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    document = json.loads((ROOT / "notebooks/16_kaggle_b12_benchmark.ipynb").read_text())
    scope = {}
    for cell in document["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            exec(compile("".join(cell["source"]), "benchmark-cell", "exec"), scope)
    assert scope["ALLOW_PREPARATION"] is False
    assert scope["ALLOW_ENV_INSTALL"] is False
    assert scope["ALLOW_REAL_INFERENCE"] is False
    assert not list(tmp_path.iterdir())


def test_campaign_uses_native_planner_and_isolates_twelve_processes(tmp_path):
    m = driver()
    plan = m.campaign_plan(ROOT, "test-only", Path("/missing-cache"), tmp_path / "runs")
    assert len(plan) == 12
    assert len({r["run_id"] for r in plan}) == 12
    assert len({r["folder"] for r in plan}) == 12
    assert {(r["baseline"], r["language"], r["replicate"]) for r in plan} == {
        (b, lang, rep) for b in ("b1", "b2") for lang in ("en", "vi") for rep in (1, 2, 3)
    }
    for r in plan:
        a = r["argv"]
        assert a[2] == "evaluate"
        assert "--limit" not in a
        assert a[a.index("--language") + 1] == r["language"]
        assert a[a.index("--cache") + 1] == str(
            tmp_path / "runs" / r["language"] / "cache/b2-few-shot.npz"
        )
        assert r["config"]["run_timeout_seconds"] == 5400
    selected = m.select_process(plan, "b2", "vi", 3)
    assert selected["run_id"] == "test-only-b2-vi-r03"
    Path(selected["folder"]).mkdir(parents=True)
    with pytest.raises(ValueError, match="existing"):
        m.select_process(plan, "b2", "vi", 3)


def test_cleanup_only_removes_owned_scratch_and_never_follows_links(tmp_path):
    m = driver()
    mount = tmp_path / "input"
    mount.mkdir()
    (mount / "keep").write_text("immutable")
    scratch = tmp_path / "b12-scratch-test"
    scratch.mkdir()
    (scratch / "cache-link").symlink_to(mount, target_is_directory=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    m.cleanup_scratch(scratch, tmp_path)
    assert (mount / "keep").read_text() == "immutable"
    assert evidence.exists() and not scratch.exists()
    with pytest.raises(ValueError):
        m.cleanup_scratch(mount, mount)


def test_timeout_terminates_descendants_and_retains_logs(tmp_path):
    m = driver()
    marker = tmp_path / "should-not-appear"
    child = "import time,pathlib; time.sleep(1); pathlib.Path(" + repr(str(marker)) + ").touch()"
    code = (
        'import subprocess,sys,time; print("started",flush=True); '
        'subprocess.Popen([sys.executable,"-c",' + repr(child) + "]); time.sleep(30)"
    )
    log = tmp_path / "timeout.log"
    with pytest.raises(subprocess.TimeoutExpired):
        m.run_logged([sys.executable, "-c", code], os.environ.copy(), log, 0.2)
    assert "started" in log.read_text()
    # Waiting on an ordinary CPU child confirms the killed descendant cannot publish later.
    subprocess.run([sys.executable, "-c", "import time; time.sleep(1.1)"], check=True)
    assert not marker.exists()


def test_error_retains_log_and_stops(tmp_path):
    m = driver()
    log = tmp_path / "failure.log"
    with pytest.raises(RuntimeError, match="exit=7"):
        m.run_logged(
            [sys.executable, "-c", 'print("failure evidence"); exit(7)'], os.environ.copy(), log, 5
        )
    assert "failure evidence" in log.read_text()


def test_embedded_driver_matches_reviewed_source():
    notebook = json.loads((ROOT / "notebooks/16_kaggle_b12_benchmark.ipynb").read_bytes())
    scope = {}
    exec("".join(next(c for c in notebook["cells"] if c["id"] == "driver-source")["source"]), scope)
    assert scope["DRIVER_SOURCE"] == SCRIPT.read_text()
    import hashlib

    assert hashlib.sha256(scope["DRIVER_SOURCE"].encode()).hexdigest() == scope["DRIVER_SHA256"]


def test_preparation_failure_preserves_evidence_and_mount(tmp_path, monkeypatch):
    m = driver()
    mount, working = tmp_path / "mount", tmp_path / "working"
    mount.mkdir()
    working.mkdir()
    (mount / "keep").write_text("immutable")
    settings = dict(
        allow_preparation=True,
        allow_env_install=False,
        allow_real_inference=False,
        campaign_id="test-only",
        session_id="s01",
        baseline="b1",
        language="en",
        replicate=1,
        prior_attempts=[],
    )
    with pytest.raises(ValueError, match="Exactly one"):
        m.prepare(settings, mount=mount, working=working)
    base = working / "b12-benchmark-test-only"
    summary = json.loads((base / "session-s01/driver-summary.json").read_bytes())
    assert summary["status"] == "failed" and summary["scratch_removed"]
    assert (base / "session-s01/artifacts-manifest.json").is_file()
    assert (mount / "keep").read_text() == "immutable"
    assert not list(working.glob("b12-scratch-*"))
    with pytest.raises(FileExistsError):
        m.prepare(settings, mount=mount, working=working)


def test_native_bundle_integrity_and_data_preflight_offline(tmp_path, monkeypatch):
    from nl2sparql.kaggle.bundle import build_bundle, preflight_data, verify_bundle

    m = driver()
    archive = tmp_path / "input-bundle.bundle"
    build_bundle(ROOT, archive)
    # Current documentation differs from the immutable released archive.
    # TEST-ONLY transport fixture; accepted release is validated separately.
    monkeypatch.setattr(m, "BUNDLE_SHA256", m.digest(archive))
    extracted = tmp_path / "extracted"
    m.extract_inputs(archive, extracted)
    assert len(verify_bundle(extracted)["files"]) == 181
    data = preflight_data(extracted)
    assert data["training_records"] == 7208
    assert data["english_records"] == data["vietnamese_records"] == 100
    assert data["scientific_ready"] is False
    with pytest.raises(ValueError, match="existing"):
        m.extract_inputs(archive, extracted)
    archive.write_bytes(archive.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="fingerprint"):
        m.extract_inputs(archive, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_attempted_ids_and_unreviewed_prior_sessions_block_before_writes(tmp_path):
    m = driver()
    settings = dict(
        allow_preparation=True,
        allow_env_install=True,
        allow_real_inference=True,
        campaign_id="test-only",
        session_id="s02",
        baseline="b1",
        language="en",
        replicate=2,
        prior_attempts=["test-only-b1-en-r01"],
    )
    with pytest.raises(ValueError, match="Review prior"):
        m.prepare(settings, working=tmp_path)
    settings.update(prior_completeness_reviewed=True, replicate=1)
    with pytest.raises(ValueError, match="no reuse"):
        m.prepare(settings, working=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.fixture
def native_shape(tmp_path):
    """Handwritten TEST-ONLY shapes, never genuine provenance or scientific evidence."""
    from nl2sparql.models.b12.evaluate import load_evaluation_cases

    m = driver()
    folder = tmp_path / "TEST-ONLY-NOT-GENUINE"
    folder.mkdir()
    identity = dict(run_id="TEST-ONLY-NOT-GENUINE", language="en")
    item = dict(identity, baseline="b1", folder=str(folder))
    rows, logs = [], []
    for case in load_evaluation_cases(ROOT / "data/dataset/test/test-100.jsonl"):
        rows.append(
            dict(
                identity,
                case_id=case.case_id,
                prediction={
                    "baseline": "b1",
                    "extraction_status": "unsafe_sql",
                    "completion": {"synthetic_backend": False, "model_revision": m.MODEL_REVISION},
                },
            )
        )
        logs.append(dict(identity, case_id=case.case_id, synthetic_backend=False))
    report = dict(identity, baseline="b1", prediction_count=100, metrics={"total": 100})

    def publish():
        for name, values in [("predictions.jsonl", rows), ("native-log.jsonl", logs)]:
            (folder / name).write_text("".join(json.dumps(x) + "\n" for x in values))
        (folder / "native-report.json").write_text(json.dumps(report))
        run = dict(
            identity,
            baseline="b1",
            status="completed_native_inference",
            native_outputs={
                name: m.digest(folder / name)
                for name in ("predictions.jsonl", "native-log.jsonl", "native-report.json")
            },
        )
        (folder / "run.json").write_text(json.dumps(run))

    publish()
    return m, item, rows, logs, report, publish


def test_completeness_does_not_discard_unsafe_baseline_results(native_shape):
    m, item, *_ = native_shape
    result = m.check_complete(ROOT, item)
    assert result["N"] == 100 and result["scientific_ready"] is False
    assert result["accuracy_assessed_by_driver"] is False


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "language", "synthetic", "report_baseline", "tamper"]
)
def test_completeness_rejects_partial_mixed_or_corrupt_artifacts(native_shape, mutation):
    m, item, rows, logs, report, publish = native_shape
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        logs[-1]["case_id"] = logs[0]["case_id"]
    elif mutation == "language":
        rows[-1]["language"] = "vi"
    elif mutation == "synthetic":
        rows[0]["prediction"]["completion"]["synthetic_backend"] = True
    elif mutation == "report_baseline":
        report["baseline"] = "b2"
    publish()
    if mutation == "tamper":
        path = Path(item["folder"]) / "predictions.jsonl"
        path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError):
        m.check_complete(ROOT, item)
