"""Operational tests only: no scientific readiness and no model/encoder calls."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/27_kaggle_b12_benchmark.py"


def driver():
    assert SCRIPT.is_file(), "benchmark driver missing"
    spec = importlib.util.spec_from_file_location("benchmark_driver", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def simulated_setup(tmp_path, monkeypatch):
    """TEST-ONLY subprocess timings; never install packages or create native evidence."""
    m = driver()
    mount, working = tmp_path / "mount", tmp_path / "working"
    mount.mkdir()
    working.mkdir()
    (mount / "keep").write_text("immutable")
    inventory = mount / "inventory.json"
    inventory.write_text("{}")
    clock = [0.0]
    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    # Transport/installation are external to this timing test; real integrity
    # and subprocess-group cleanup are covered by separate operational tests.
    monkeypatch.setattr(m, "discover_inputs", lambda _: (mount, mount, inventory, mount))
    monkeypatch.setattr(m, "extract_inputs", lambda _, target: target.mkdir())
    monkeypatch.setattr(m.os, "killpg", lambda *_: None)

    def execute(durations, exit_codes=None):
        pending = iter(zip(durations, exit_codes or [0] * len(durations), strict=True))

        class Process:
            pid = 99999999

            def __init__(self, argv, *, env, stdout, stderr, start_new_session):
                self.argv = argv
                self.duration, self.code = next(pending)
                self.stdout = stdout
                self.returncode = None

            def wait(self, timeout=None):
                if timeout is None:
                    self.returncode = -9
                    return self.returncode
                if self.duration > timeout:
                    clock[0] += timeout
                    self.stdout.write("TEST-ONLY subprocess output before timeout\n")
                    self.stdout.flush()
                    raise subprocess.TimeoutExpired(self.argv, timeout)
                clock[0] += self.duration
                self.stdout.write("TEST-ONLY subprocess completed\n")
                self.returncode = self.code
                return self.returncode

        monkeypatch.setattr(m.subprocess, "Popen", Process)
        settings = dict(
            allow_preparation=True,
            allow_env_install=True,
            allow_real_inference=False,
            campaign_id="test-only",
            session_id="timing-test",
            baseline="b1",
            language="en",
            replicate=1,
            prior_attempts=[],
        )
        m.prepare(settings, mount=mount, working=working)

    evidence = working / "b12-benchmark-test-only/session-timing-test"
    return execute, evidence, mount, working


def test_slow_setup_uses_headroom_without_exceeding_session_or_worker_caps(simulated_setup):
    # Reverting the setup allowance would time out before cache verification
    # completes. Removing worker/session clamping would violate the cleanup reserve.
    execute, evidence, _, _ = simulated_setup
    execute([60, 30, 480, 1050, 5460])
    summary = json.loads((evidence / "driver-summary.json").read_text())
    assert summary["status"] == "prepared_without_inference"
    assert summary["wall_seconds"] == 7080
    assert summary["process_cap_seconds"] == 5400
    assert summary["session_cap_seconds"] == 7200
    assert summary["setup_cap_seconds"] == 1620
    assert summary["cleanup_reserve_seconds"] == 120
    events = [
        json.loads(line) for line in (evidence / "stage-timings.jsonl").read_text().splitlines()
    ]
    starts = [e for e in events if e["event"] == "started"]
    assert [e["timeout_seconds"] for e in starts] == [1620, 1560, 1530, 1050, 5460]
    assert starts[-1]["stage"] == "native_cli25"
    assert events[-1]["outcome"] == "completed"
    assert events[-1]["budget_remaining_seconds"] == 0
    assert not (evidence.parent / "runs").exists()


def test_setup_timeout_retains_stage_timing_output_and_cleanup(simulated_setup):
    # Losing the finally record would hide the stage duration that caused the
    # real incident; launching worker after this timeout would violate fail-stop.
    execute, evidence, mount, working = simulated_setup
    with pytest.raises(subprocess.TimeoutExpired):
        execute([30, 30, 480, 2000])
    events = [
        json.loads(line) for line in (evidence / "stage-timings.jsonl").read_text().splitlines()
    ]
    assert events[-1] == dict(
        event="finished",
        stage="verify_mounted_cache",
        budget="setup",
        driver_elapsed_seconds=1620,
        elapsed_seconds=1080,
        timeout_seconds=1080,
        budget_remaining_seconds=0,
        outcome="timed_out",
        error_type="TimeoutExpired",
    )
    assert "before timeout" in (evidence / "verify_mounted_cache.log").read_text()
    summary = json.loads((evidence / "driver-summary.json").read_text())
    assert summary["status"] == "failed" and summary["scratch_removed"] is True
    assert not (evidence / "worker.log").exists()
    assert not list(working.glob("b12-scratch-*"))
    assert (mount / "keep").read_text() == "immutable"
    manifest = json.loads((evidence / "artifacts-manifest.json").read_text())
    assert "session-timing-test/stage-timings.jsonl" in manifest


def test_setup_error_retains_finished_event_without_logging_environment(
    simulated_setup, monkeypatch
):
    # Missing error telemetry or serializing command/env values would either
    # obscure failed installation or leak credentials into retained timing data.
    monkeypatch.setenv("PATH", "TEST-ONLY-PRIVATE-PATH")
    monkeypatch.setenv("HF_TOKEN", "TEST-ONLY-SECRET")
    execute, evidence, _, _ = simulated_setup
    with pytest.raises(RuntimeError, match="exit=7"):
        execute([10, 20, 30], [0, 0, 7])
    text = (evidence / "stage-timings.jsonl").read_text()
    events = [json.loads(line) for line in text.splitlines()]
    assert events[-1]["stage"] == "install_locked_environment"
    assert events[-1]["outcome"] == "failed"
    assert events[-1]["error_type"] == "RuntimeError"
    assert events[-1]["elapsed_seconds"] == 30
    assert events[-1]["budget_remaining_seconds"] == 1560
    assert "TEST-ONLY-SECRET" not in text and "TEST-ONLY-PRIVATE-PATH" not in text
    assert not (evidence / "verify_mounted_cache.log").exists()


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
def replacement_settings():
    parent = "test-only"
    return dict(
        allow_preparation=True,
        allow_env_install=True,
        allow_real_inference=True,
        campaign_id=parent + "-replacement01",
        session_id="s11-b2-en-r03-replacement01",
        baseline="b2",
        language="en",
        replicate=3,
        prior_attempts=[
            f"{parent}-{b}-{lang}-r{r:02d}"
            for b in ("b1", "b2")
            for lang in ("en", "vi")
            for r in (1, 2, 3)
        ],
        prior_completeness_reviewed=True,
        replacement_of=parent + "-b2-en-r03",
    )


@pytest.mark.parametrize("attempt", [1, 2])
def test_replacement_preserves_parent_attempts_and_gets_distinct_native_id(
    tmp_path, replacement_settings, attempt
):
    # Reusing the parent campaign would collide with the failed native identity.
    # Changing research arguments to implement replacement would invalidate this comparison.
    m = driver()
    settings = replacement_settings
    if attempt == 2:
        settings["campaign_id"] = "test-only-replacement02"
        settings["prior_attempts"].append("test-only-replacement01-b2-en-r03")
    provenance = m.validate_attempts(settings)
    assert provenance == dict(parent_campaign_id="test-only", replacement_of="test-only-b2-en-r03")
    output, home = tmp_path / "runs", Path("/missing-cache")
    plan = m.campaign_plan(ROOT, settings["campaign_id"], home, output)
    item = m.select_process(plan, "b2", "en", 3, settings["prior_attempts"])
    original = m.select_process(m.campaign_plan(ROOT, "test-only", home, output), "b2", "en", 3)
    assert item["run_id"] == f"test-only-replacement{attempt:02d}-b2-en-r03"
    assert item["folder"] != original["folder"]
    assert {k: v for k, v in item["config"].items() if k != "campaign_id"} == {
        k: v for k, v in original["config"].items() if k != "campaign_id"
    }
    assert [a.replace(item["run_id"], original["run_id"]) for a in item["argv"]] == original["argv"]
    assert "--limit" not in item["argv"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_parent",
        "reuse",
        "unreviewed",
        "wrong_slot",
        "wrong_campaign",
        "unsafe",
        "non_string",
    ],
)
def test_invalid_replacement_blocks_before_writes(tmp_path, replacement_settings, mutation):
    m = driver()
    settings = replacement_settings
    if mutation == "missing_parent":
        settings["prior_attempts"].remove(settings["replacement_of"])
    elif mutation == "reuse":
        settings["prior_attempts"].append(settings["campaign_id"] + "-b2-en-r03")
    elif mutation == "unreviewed":
        settings["prior_completeness_reviewed"] = False
    elif mutation == "wrong_slot":
        settings["language"] = "vi"
    elif mutation == "wrong_campaign":
        settings["campaign_id"] = "test-only"
    elif mutation == "non_string":
        settings["replacement_of"] = True
    else:
        settings["replacement_of"] = "../test-only-b2-en-r03"
    with pytest.raises(ValueError):
        m.prepare(settings, working=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("attempt", [1, 2])
def test_worker_retains_replacement_lineage_before_native_execution(
    tmp_path, monkeypatch, replacement_settings, attempt
):
    # External runtime/inference are stubbed; the planner and retained files are real.
    from nl2sparql.kaggle import bundle, runner

    m = driver()
    if attempt == 2:
        replacement_settings["campaign_id"] = "test-only-replacement02"
        replacement_settings["prior_attempts"].append("test-only-replacement01-b2-en-r03")
    monkeypatch.setattr(m.sys, "version_info", (3, 11, 15))
    monkeypatch.setattr(bundle, "preflight_data", lambda _: {"status": "data_ready"})
    monkeypatch.setattr(runner, "preflight_runtime", lambda *_: {"status": "ready"})
    evidence = tmp_path / "evidence"
    evidence.mkdir()

    def native_boundary(root, config, output, **kwargs):
        ledger = json.loads((evidence / "campaign-ledger.json").read_text())
        assert ledger["replacement_of"] in ledger["attempted_run_ids"]
        assert ledger["attempted_run_ids"][-1] == config["campaign_id"] + "-b2-en-r03"
        assert kwargs == dict(real_inference=True, baseline="b2", replicate=3)

    monkeypatch.setattr(runner, "run_campaign", native_boundary)
    monkeypatch.setattr(m, "check_complete", lambda *_: {"status": "TEST-ONLY"})
    m.worker(ROOT, Path("/missing-cache"), tmp_path / "runs", replacement_settings, evidence)
    ledger = json.loads((evidence / "campaign-ledger.json").read_text())
    assert ledger["parent_campaign_id"] == "test-only"
    assert ledger["replacement_of"] == "test-only-b2-en-r03"
    assert ledger["attempted_run_ids"][:-1] == replacement_settings["prior_attempts"]
    assert len(set(ledger["attempted_run_ids"])) == 12 + attempt
    assert ledger["scientific_ready"] is False


@pytest.mark.parametrize(
    "mutation", ["missing_first_replacement", "reuse_second", "third", "duplicate", "unreviewed"]
)
def test_second_replacement_requires_full_retained_history_before_writes(
    tmp_path, replacement_settings, mutation
):
    m = driver()
    settings = replacement_settings
    settings["campaign_id"] = "test-only-replacement02"
    settings["prior_attempts"].append("test-only-replacement01-b2-en-r03")
    if mutation == "missing_first_replacement":
        settings["prior_attempts"].pop()
    elif mutation == "reuse_second":
        settings["prior_attempts"].append("test-only-replacement02-b2-en-r03")
    elif mutation == "third":
        settings["campaign_id"] = "test-only-replacement03"
    elif mutation == "duplicate":
        settings["prior_attempts"].append(settings["prior_attempts"][-1])
    else:
        settings["prior_completeness_reviewed"] = False
    with pytest.raises(ValueError):
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
