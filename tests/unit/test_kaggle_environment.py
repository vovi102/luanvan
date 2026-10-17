"""Environment setup verifies bytes, never produces model/scientific readiness."""

import importlib.util
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/26_kaggle_environment.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("kaggle_environment", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_download_requires_opt_in_before_importing_hf_or_reading_stdin(tmp_path, monkeypatch):
    assert SCRIPT.is_file(), "missing cache preparation consumer"
    module = load_cli()
    result = CliRunner().invoke(
        module.cli,
        [
            "fetch-cache",
            "--pins",
            str(ROOT / "configs/kaggle-b12-model-pins.json"),
            "--hf-home",
            str(tmp_path),
            "--component",
            "encoder",
        ],
    )
    assert result.exit_code == 2 and "allow-downloads" in result.output
    assert not list(tmp_path.iterdir())


def test_real_pins_inspection_does_not_claim_download_or_model_readiness():
    assert SCRIPT.is_file(), "missing cache preparation consumer"
    module = load_cli()
    result = CliRunner().invoke(
        module.cli, ["inspect", "--pins", str(ROOT / "configs/kaggle-b12-model-pins.json")]
    )
    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["models"]["model"]["revision"] == "8afb486c1db24fe5011ec46dfbe5b5dccdb575c2"
    assert document["models"]["encoder"]["revision"] == "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    assert document["scientific_ready"] is False and document["model_loaded"] is False


@pytest.mark.parametrize("mutation", ["missing", "content", "escaping_link"])
def test_missing_or_corrupt_cache_fails_before_readiness(tmp_path, mutation):
    assert SCRIPT.is_file(), "missing cache preparation consumer"
    module = load_cli()
    pins = module.load_pins(ROOT / "configs/kaggle-b12-model-pins.json")
    folder = (
        tmp_path
        / "hub"
        / ("models--" + pins["models"]["encoder"]["repo_id"].replace("/", "--"))
        / "snapshots"
        / pins["models"]["encoder"]["revision"]
    )
    folder.mkdir(parents=True)
    if mutation != "missing":
        target = folder / "config.json"
        if mutation == "content":
            target.write_bytes(b"wrong bytes")
        else:
            other = tmp_path.parent / "TEST-ONLY-escaping-config"
            other.write_bytes(b"wrong bytes")
            target.symlink_to(other)
    result = CliRunner().invoke(
        module.cli,
        [
            "verify-cache",
            "--pins",
            str(ROOT / "configs/kaggle-b12-model-pins.json"),
            "--hf-home",
            str(tmp_path),
            "--component",
            "encoder",
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["scientific_ready"] is False


def test_setup_notebook_cannot_install_download_or_read_secrets_by_default():
    notebook = ROOT / "notebooks/15_kaggle_environment_cache.ipynb"
    assert notebook.is_file(), "missing environment-only notebook"
    document = json.loads(notebook.read_bytes())
    settings = {}
    for cell in document["cells"]:
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            compile(source, "setup-cell", "exec")
            assert cell["outputs"] == [] and cell["execution_count"] is None
            if cell.get("id") == "settings":
                exec(source, settings)
    assert settings["ALLOW_ENV_INSTALL"] is False
    assert settings["ALLOW_CACHE_DOWNLOADS"] is False
    assert settings["ALLOW_SECRET_ACCESS"] is False


def test_same_size_tampering_and_escaping_link_fail_hash_verification(tmp_path):
    module = load_cli()
    pins = module.load_pins(ROOT / "configs/kaggle-b12-model-pins.json")
    model = pins["models"]["encoder"]
    # TEST-ONLY known digest of literal abc, not model weights or scientific evidence.
    model["files"] = {
        "model.safetensors": {
            "bytes": 3,
            "algorithm": "sha256",
            "digest": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        }
    }
    folder = (
        tmp_path
        / "hub"
        / ("models--" + model["repo_id"].replace("/", "--"))
        / "snapshots"
        / model["revision"]
    )
    folder.mkdir(parents=True)
    target = folder / "model.safetensors"
    target.write_bytes(b"abc")
    value = module.verify_cache(pins, tmp_path, "encoder")
    assert value["status"] == "cache_bytes_verified"
    assert not value["model_loaded"] and not value["scientific_ready"]
    target.write_bytes(b"abd")
    with pytest.raises(module.SetupError, match="fingerprint"):
        module.verify_cache(pins, tmp_path, "encoder")
    target.unlink()
    outside = tmp_path.parent / "TEST-ONLY-outside-weights"
    outside.write_bytes(b"abc")
    target.symlink_to(outside)
    with pytest.raises(module.SetupError, match="escapes"):
        module.verify_cache(pins, tmp_path, "encoder")


def test_no_local_llama_download_or_token_read(tmp_path, monkeypatch):
    import sys

    module = load_cli()

    class ForbiddenInput:
        def read(self):
            raise AssertionError("must not read secret before Kaggle scope gate")

    monkeypatch.setattr(sys, "stdin", ForbiddenInput())
    pins = module.load_pins(ROOT / "configs/kaggle-b12-model-pins.json")
    with pytest.raises(module.SetupError, match="Kaggle|kaggle"):
        module.fetch_cache(pins, tmp_path, "model", allowed=True, token_stdin=True)


def test_all_default_notebook_cells_avoid_install_download_and_secret_access(monkeypatch):
    import builtins
    import socket
    import subprocess

    original = builtins.__import__

    def forbidden(*a, **k):
        raise AssertionError("setup must be disabled by default")

    def guarded_import(name, *a, **k):
        if name.split(".")[0] in {"kaggle_secrets", "torch", "transformers", "huggingface_hub"}:
            forbidden()
        return original(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    notebook = json.loads((ROOT / "notebooks/15_kaggle_environment_cache.ipynb").read_bytes())
    scope = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            exec("".join(cell["source"]), scope)


def test_setup_notebook_checks_current_payload_bytes():
    scope = {}
    notebook = json.loads((ROOT / "notebooks/15_kaggle_environment_cache.ipynb").read_bytes())
    for cell in notebook["cells"]:
        if cell.get("id") == "settings":
            exec("".join(cell["source"]), scope)
            scope["KIT_ROOT"] = str(ROOT)
        elif cell.get("id") == "verify-unpack":
            exec("".join(cell["source"]), scope)
    scope["check_setup_files"]()
