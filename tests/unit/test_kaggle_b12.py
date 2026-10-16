"""Kaggle preparation must ship data and orchestration without changing baselines."""

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_cli_has_data_only_preparation_commands():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/25_kaggle_b12.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "bundle" in result.stdout
    assert "preflight" in result.stdout


@pytest.fixture(scope="module")
def shipped(tmp_path_factory):
    from nl2sparql.kaggle.bundle import build_bundle, extract_bundle

    folder = tmp_path_factory.mktemp("kaggle-shipped")
    first, second = folder / "one.tar.gz", folder / "two.tar.gz"
    first_manifest = build_bundle(ROOT, first)
    assert build_bundle(ROOT, second) == first_manifest
    assert first.read_bytes() == second.read_bytes()
    extracted = folder / "input"
    extract_bundle(first, extracted, hashlib.sha256(first.read_bytes()).hexdigest())
    return extracted, first_manifest, first


def test_bundle_is_deterministic_and_contains_only_explicit_inputs(shipped):
    root, manifest, archive = shipped
    names = set(manifest["files"])
    assert "data/dataset/processed/b2-training.jsonl" in names
    assert "data/dataset/test/test-100-vi.jsonl" in names
    assert "data/dataset/test/manifest.json" in names
    assert "scripts/17_small_llm_baselines.py" in names
    assert not any(
        ".env" in name or "/fixtures/" in name or "__pycache__" in name for name in names
    )
    assert not any(name.startswith((".git/", "tests/", "artifacts/")) for name in names)
    assert manifest["execution_languages"] == ["en", "vi"]
    assert (root / "kaggle-bundle.json").is_file()
    with tarfile.open(archive) as handle:
        assert all(member.isfile() and member.mtime == 0 for member in handle.getmembers())


@pytest.mark.parametrize("change", ["tamper", "missing", "extra", "symlink"])
def test_modified_bundle_rejected_before_data_or_ml_loading(shipped, tmp_path, change):
    from nl2sparql.kaggle.bundle import PreparationError, verify_bundle

    root = tmp_path / "input"
    shutil.copytree(shipped[0], root)
    target = root / "data/dataset/test/test-100.jsonl"
    if change == "tamper":
        target.write_bytes(target.read_bytes() + b" ")
    elif change == "missing":
        target.unlink()
    elif change == "extra":
        (root / ".env").write_text("fixture-only extra file")
    else:
        payload = target.read_bytes()
        target.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(payload)
        target.symlink_to(outside)
    with pytest.raises(PreparationError):
        verify_bundle(root)


def test_archive_bad_digest_or_traversal_never_extracts(shipped, tmp_path):
    import io

    from nl2sparql.kaggle.bundle import PreparationError, extract_bundle

    with pytest.raises(PreparationError, match="SHA-256"):
        extract_bundle(shipped[2], tmp_path / "bad", "0" * 64)
    attack = tmp_path / "attack.tar.gz"
    with tarfile.open(attack, "w:gz") as handle:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        handle.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(PreparationError):
        extract_bundle(attack, tmp_path / "unpack", hashlib.sha256(attack.read_bytes()).hexdigest())
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "unpack").exists()


def test_actual_data_preflight_preserves_train_and_paired_provenance(shipped):
    from nl2sparql.kaggle.bundle import preflight_data

    result = preflight_data(shipped[0])
    assert result["training_records"] == 7208
    assert result["english_records"] == 100
    assert result["vietnamese_records"] == 100
    assert result["execution_languages"] == ["en", "vi"]
    assert result["scientific_ready"] is False


def config_for(root):
    result = json.loads((root / "configs/kaggle-b12-run.template.json").read_bytes())
    result.update(
        campaign_id="test-campaign",
        model_revision="a" * 40,
        encoder_revision="b" * 40,
        hf_home="/nonexistent/test-only-hf-home",
        run_timeout_seconds=60,
    )
    return result


def test_plan_delegates_six_runs_to_unchanged_cli17(shipped, tmp_path):
    from nl2sparql.kaggle.runner import plan_runs

    root = shipped[0]
    plan = plan_runs(root, config_for(root), tmp_path / "outputs")
    assert len(plan) == 6
    assert len({item["run_id"] for item in plan}) == 6
    for item in plan:
        argv = item["argv"]
        assert argv[1:3] == [str(root / "scripts/17_small_llm_baselines.py"), "evaluate"]
        assert argv[argv.index("--test-set") + 1] == str(root / "data/dataset/test/test-100.jsonl")
        assert "--real-inference" in argv
        assert "--reviewed" not in argv and "--live-verified" not in argv
        assert str(root / "data/dataset/processed/b2-training.jsonl") in argv
        assert (
            argv[argv.index("--accepted-training-sha256") + 1]
            == "b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("language", "fr"),
        ("model_revision", None),
        ("model_revision", "main"),
        ("encoder_revision", None),
        ("campaign_id", "../escape"),
        ("model_id", "other/model"),
        ("replicates", 2),
        ("max_new_tokens", 1024),
    ],
)
def test_invalid_config_never_schedules_inference(shipped, tmp_path, field, value):
    from nl2sparql.kaggle.bundle import PreparationError
    from nl2sparql.kaggle.runner import plan_runs

    config = config_for(shipped[0])
    config[field] = value
    with pytest.raises(PreparationError):
        plan_runs(shipped[0], config, tmp_path / "outputs")


def test_output_inside_input_is_rejected(shipped):
    from nl2sparql.kaggle.bundle import PreparationError
    from nl2sparql.kaggle.runner import plan_runs

    with pytest.raises(PreparationError, match="output"):
        plan_runs(shipped[0], config_for(shipped[0]), shipped[0] / "outputs")


def test_run_without_opt_in_never_imports_models(shipped, tmp_path, monkeypatch):
    from nl2sparql.kaggle.bundle import PreparationError
    from nl2sparql.kaggle.runner import run_campaign

    def forbidden(*args, **kwargs):
        raise AssertionError("must not load hardware/model or start child")

    monkeypatch.setattr("nl2sparql.kaggle.runner.probe_hardware", forbidden)
    monkeypatch.setattr("nl2sparql.kaggle.runner.subprocess.run", forbidden)
    with pytest.raises(PreparationError, match="real-inference"):
        run_campaign(shipped[0], config_for(shipped[0]), tmp_path / "output", real_inference=False)
    assert not (tmp_path / "output").exists()


def test_runtime_preflight_blocks_incomplete_snapshot_without_ml(shipped, tmp_path):
    from nl2sparql.kaggle.runner import preflight_runtime

    result = preflight_runtime(shipped[0], config_for(shipped[0]), tmp_path / "output")
    assert result["status"] == "blocked"
    assert any("snapshot" in blocker for blocker in result["blockers"])
    assert result["scientific_ready"] is False


def test_failed_native_process_retains_evidence_and_stops(shipped, tmp_path, monkeypatch):
    from nl2sparql.kaggle import runner
    from nl2sparql.kaggle.bundle import PreparationError

    monkeypatch.setattr(runner, "preflight_runtime", lambda *a, **k: {"status": "ready"})
    monkeypatch.setattr(runner, "probe_hardware", lambda: {"gpu_names": ["TEST-ONLY T4"]})
    calls = []

    def failure(argv, **kwargs):
        calls.append(argv)
        kwargs["stdout"].write("test-only native output\n")
        kwargs["stderr"].write("test-only OOM\n")
        return subprocess.CompletedProcess(argv, 9)

    monkeypatch.setattr(runner.subprocess, "run", failure)
    output = tmp_path / "output"
    with pytest.raises(PreparationError, match="native"):
        runner.run_campaign(shipped[0], config_for(shipped[0]), output, real_inference=True)
    assert len(calls) == 1
    folder = output / "test-campaign-b1-en-r01"
    assert (folder / "stderr.log").read_text() == "test-only OOM\n"
    assert json.loads((folder / "run.json").read_bytes())["status"] == "failed"
    assert not (output / "test-campaign-b1-en-r02").exists()
    with pytest.raises(PreparationError, match="existing"):
        runner.run_campaign(shipped[0], config_for(shipped[0]), output, real_inference=True)
    assert len(calls) == 1


def test_notebook_is_valid_python_and_disabled_by_default():
    notebook = json.loads((ROOT / "notebooks/14_kaggle_b12.ipynb").read_bytes())
    assert notebook["nbformat"] == 4
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            compile(source, "kaggle-cell", "exec")
            assert cell["outputs"] == []
    settings = {}
    cell = next(c for c in notebook["cells"] if c.get("id") == "settings")
    exec("".join(cell["source"]), settings)
    assert settings["ALLOW_REAL_INFERENCE"] is False
    assert settings["MODEL_REVISION"] is None
    assert settings["ENCODER_REVISION"] is None


def test_extra_directory_symlink_rejected(shipped, tmp_path):
    from nl2sparql.kaggle.bundle import PreparationError, verify_bundle

    root = tmp_path / "input"
    shutil.copytree(shipped[0], root)
    (root / "unlisted-link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PreparationError):
        verify_bundle(root)


def test_cache_symlink_rejected_before_model_loading(shipped, tmp_path):
    from nl2sparql.kaggle.bundle import PreparationError
    from nl2sparql.kaggle.runner import preflight_runtime

    output = tmp_path / "outputs"
    output.mkdir()
    (output / "cache").symlink_to(shipped[0] / "data", target_is_directory=True)
    with pytest.raises(PreparationError, match="cache|output"):
        preflight_runtime(shipped[0], config_for(shipped[0]), output)


def test_malformed_archive_preserves_destination(tmp_path):
    from nl2sparql.kaggle.bundle import PreparationError, extract_bundle

    archive = tmp_path / "invalid.tar.gz"
    archive.write_bytes(b"not an archive")
    with pytest.raises(PreparationError):
        extract_bundle(
            archive, tmp_path / "input", hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    assert not (tmp_path / "input").exists()


def test_timeout_retains_partial_native_output(shipped, tmp_path, monkeypatch):
    from nl2sparql.kaggle import runner
    from nl2sparql.kaggle.bundle import PreparationError

    monkeypatch.setattr(runner, "preflight_runtime", lambda *a, **k: {"status": "ready"})
    monkeypatch.setattr(runner, "preflight_data", lambda *a: {"status": "data_ready"})
    monkeypatch.setattr(runner, "probe_hardware", lambda: {"gpu_names": ["TEST-ONLY T4"]})

    def timeout(argv, **kwargs):
        assert kwargs["timeout"] == 60
        kwargs["stdout"].write("test-only partial output\n")
        raise subprocess.TimeoutExpired(argv, 60)

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    output = tmp_path / "output"
    with pytest.raises(PreparationError, match="native"):
        runner.run_campaign(shipped[0], config_for(shipped[0]), output, real_inference=True)
    folder = output / "test-campaign-b1-en-r01"
    assert (folder / "stdout.log").read_text() == "test-only partial output\n"
    assert json.loads((folder / "run.json").read_bytes())["status"] == "failed"


def test_completed_processes_keep_native_readiness_and_offline_environment(
    shipped, tmp_path, monkeypatch
):
    from nl2sparql.kaggle import runner

    monkeypatch.setattr(runner, "preflight_runtime", lambda *a, **k: {"status": "ready"})
    monkeypatch.setattr(runner, "preflight_data", lambda *a: {"status": "data_ready"})
    monkeypatch.setattr(runner, "probe_hardware", lambda: {"gpu_names": ["TEST-ONLY T4"]})
    monkeypatch.setenv("HF_TOKEN", "TEST-ONLY-not-a-credential")
    calls = []

    def completed(argv, **kwargs):
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
        assert "HF_TOKEN" not in kwargs["env"]
        assert kwargs["timeout"] == 60
        calls.append(argv)
        for flag in ("--predictions", "--log"):
            Path(argv[argv.index(flag) + 1]).write_text("test-only synthetic output\n")
        Path(argv[argv.index("--report") + 1]).write_text('{"scientific_ready": false}\n')
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(runner.subprocess, "run", completed)
    output = tmp_path / "output"
    runs = runner.run_campaign(shipped[0], config_for(shipped[0]), output, real_inference=True)
    assert len(calls) == len(runs) == 6
    assert all(
        r["status"] == "completed_native_inference" and r["scientific_status"] == "not_assessed"
        for r in runs
    )
    for run in runs:
        folder = Path(run["folder"])
        assert json.loads((folder / "native-report.json").read_bytes()) == {
            "scientific_ready": False
        }
        assert len(run["native_outputs"]) == 3


def test_missing_weight_shard_blocks_local_snapshot(tmp_path):
    from nl2sparql.kaggle.runner import MODEL_ID, snapshot_blockers

    revision = "a" * 40
    folder = tmp_path / "hub" / ("models--" + MODEL_ID.replace("/", "--")) / "snapshots" / revision
    folder.mkdir(parents=True)
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json"):
        (folder / name).write_text("{}")
    (folder / "model.safetensors.index.json").write_text(
        '{"weight_map":{"weight":"missing-shard.safetensors"}}'
    )
    blockers = snapshot_blockers(tmp_path, MODEL_ID, revision, model=True)
    assert any("missing weight shard" in blocker for blocker in blockers)


def test_interrupted_process_is_not_left_as_started(shipped, tmp_path, monkeypatch):
    from nl2sparql.kaggle import runner

    monkeypatch.setattr(runner, "preflight_runtime", lambda *a, **k: {"status": "ready"})
    monkeypatch.setattr(runner, "preflight_data", lambda *a: {"status": "data_ready"})
    monkeypatch.setattr(runner, "probe_hardware", lambda: {"gpu_names": ["TEST-ONLY T4"]})

    def interrupt(argv, **kwargs):
        kwargs["stderr"].write("test-only interrupt\n")
        raise KeyboardInterrupt

    monkeypatch.setattr(runner.subprocess, "run", interrupt)
    output = tmp_path / "output"
    with pytest.raises(KeyboardInterrupt):
        runner.run_campaign(shipped[0], config_for(shipped[0]), output, real_inference=True)
    record = json.loads((output / "test-campaign-b1-en-r01/run.json").read_bytes())
    assert record["status"] == "interrupted"
    assert "finished_at_utc" in record
    assert not (output / "test-campaign-b1-en-r02").exists()
