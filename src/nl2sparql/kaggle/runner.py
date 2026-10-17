"""Fail-closed orchestration of the language-explicit CLI17 baseline contract."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from nl2sparql.kaggle.bundle import (
    ENGLISH,
    TRAINING,
    TRAINING_SHA256,
    VIETNAMESE,
    PreparationError,
    canonical,
    preflight_data,
    sha256,
    verify_bundle,
)

MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
ENCODER_ID = "sentence-transformers/all-MiniLM-L6-v2"
PACKAGES = (
    "torch",
    "transformers",
    "sentence-transformers",
    "accelerate",
    "bitsandbytes",
    "numpy",
    "sqlglot",
    "click",
    "google-cloud-bigquery",
    "pydantic",
    "rapidfuzz",
    "pyyaml",
    "huggingface-hub",
    "safetensors",
    "tokenizers",
)
FIXED = {
    "schema_version": 1,
    "model_id": MODEL_ID,
    "encoder_id": ENCODER_ID,
    "replicates": 3,
    "seed": 42,
    "max_new_tokens": 512,
    "batch_size": 1,
    "load_in_4bit": True,
    "do_sample": False,
}


def validate_config(config: dict, *, require_pins: bool = True) -> None:
    expected = set(FIXED) | {
        "campaign_id",
        "language",
        "model_revision",
        "encoder_revision",
        "hf_home",
        "run_timeout_seconds",
    }
    if not isinstance(config, dict) or set(config) != expected:
        raise PreparationError("run config field set mismatch")
    for name, value in FIXED.items():
        if config[name] != value or type(config[name]) is not type(value):
            raise PreparationError(f"research config cannot change {name}")
    if config["language"] not in ("en", "vi"):
        raise PreparationError("language must be explicitly en or vi")
    if require_pins:
        if type(config["run_timeout_seconds"]) is not int or config["run_timeout_seconds"] <= 0:
            raise PreparationError("run_timeout_seconds must be an explicit positive wall-time cap")
        for name in ("model_revision", "encoder_revision"):
            value = config[name]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise PreparationError(
                    f"{name} requires a genuine pinned lowercase 40-hex revision"
                )
        if not isinstance(config["campaign_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", config["campaign_id"]
        ):
            raise PreparationError("campaign_id must be a safe explicit run identity")
        if not isinstance(config["hf_home"], str) or not Path(config["hf_home"]).is_absolute():
            raise PreparationError("hf_home must identify an absolute local cache")


def output_boundary(root: Path, output: Path) -> None:
    if output.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(
        output.resolve()
    ):
        raise PreparationError("output must be separate from the immutable input bundle")
    for path in (output, *output.parents):
        if path.is_symlink():
            raise PreparationError("output must not traverse symlinks")
    for language in ("en", "vi"):
        for path in (output / language, output / language / "cache"):
            if path.is_symlink():
                raise PreparationError("language output cache must not traverse symlinks")
            if path.exists() and not path.is_dir():
                raise PreparationError("language output cache must be a directory")
        cache_file = output / language / "cache/b2-few-shot.npz"
        for path in (
            cache_file,
            cache_file.with_suffix(".npz.json"),
            cache_file.with_suffix(".npz.lock"),
        ):
            if path.is_symlink() or (
                path.exists() and (not path.is_file() or path.stat().st_nlink != 1)
            ):
                raise PreparationError("unsafe language cache alias")
    cache = output / "cache"
    for path in (
        cache,
        cache / "b2-few-shot.npz",
        cache / "b2-few-shot.npz.json",
        cache / "b2-few-shot.npz.lock",
    ):
        if path.is_symlink():
            raise PreparationError("output cache must not traverse symlinks")
        if path.exists() and path != cache and (not path.is_file() or path.stat().st_nlink != 1):
            raise PreparationError("output cache must contain only regular single-link files")
    if cache.exists() and not cache.is_dir():
        raise PreparationError("output cache must be a directory")
    if output.exists() and not output.is_dir():
        raise PreparationError("output must be a directory")


def plan_runs(root: Path, config: dict, output: Path) -> list[dict]:
    validate_config(config)
    root, output = root.resolve(), output.absolute()
    output_boundary(root, output)
    language = config["language"]
    runs = []
    for baseline in ("b1", "b2"):
        for replicate in range(1, 4):
            run_id = f"{config['campaign_id']}-{baseline}-{language}-r{replicate:02d}"
            folder = output / run_id
            argv = [
                sys.executable,
                str(root / "scripts/17_small_llm_baselines.py"),
                "evaluate",
                "--baseline",
                baseline,
                "--test-set",
                str(root / (ENGLISH if language == "en" else VIETNAMESE)),
                "--language",
                language,
                "--benchmark-root",
                str(root),
                "--model-revision",
                config["model_revision"],
                "--run-id",
                run_id,
                "--catalog",
                str(root / "src/nl2sparql/sql/catalog/ethereum_analytics.json"),
                "--training",
                str(root / TRAINING),
                "--cache",
                str(output / language / "cache/b2-few-shot.npz"),
                "--encoder-id",
                ENCODER_ID,
                "--encoder-revision",
                config["encoder_revision"],
                "--accepted-training-sha256",
                TRAINING_SHA256,
                "--predictions",
                str(folder / "predictions.jsonl"),
                "--log",
                str(folder / "native-log.jsonl"),
                "--report",
                str(folder / "native-report.json"),
                "--real-inference",
            ]
            runs.append(
                {
                    "run_id": run_id,
                    "baseline": baseline,
                    "language": language,
                    "replicate": replicate,
                    "folder": str(folder),
                    "argv": argv,
                }
            )
    return runs


def locked_versions(root: Path) -> dict[str, str]:
    packages = tomllib.loads((root / "uv.lock").read_text())["package"]
    versions = {p["name"]: p["version"] for p in packages}
    return {name: versions[name] for name in PACKAGES}


def snapshot_blockers(home: Path, identity: str, revision: str, *, model: bool) -> list[str]:
    """Inspect cache files only; never import HF, read tokens or download anything."""
    folder = home / "hub" / ("models--" + identity.replace("/", "--")) / "snapshots" / revision
    if not folder.is_dir():
        return [f"local snapshot missing: {identity}@{revision}"]
    # HF cache uses links into blobs: require every target to stay inside this cache.
    for path in folder.rglob("*"):
        if not path.resolve().is_relative_to(home.resolve()):
            return [f"local snapshot has escaping file: {identity}"]
    required = (
        ["config.json", "tokenizer_config.json", "tokenizer.json"]
        if model
        else ["modules.json", "config.json", "tokenizer_config.json"]
    )
    blockers = [
        f"local snapshot missing {name}: {identity}"
        for name in required
        if not (folder / name).is_file() or not (folder / name).stat().st_size
    ]
    index = folder / "model.safetensors.index.json"
    if model and index.is_file():
        try:
            weights = json.loads(index.read_bytes())["weight_map"]
            names = set(weights.values())
            if not names or any(not isinstance(n, str) or Path(n).name != n for n in names):
                raise ValueError("invalid shard names")
            blockers.extend(
                f"local snapshot missing weight shard: {identity}/{name}"
                for name in names
                if not (folder / name).is_file() or not (folder / name).stat().st_size
            )
        except (ValueError, KeyError, TypeError):
            blockers.append(f"local snapshot invalid weight index: {identity}")
    elif not any(
        (folder / name).is_file() and (folder / name).stat().st_size
        for name in ("model.safetensors", "pytorch_model.bin")
    ):
        blockers.append(f"local snapshot missing weights: {identity}")
    return blockers


def preflight_runtime(root: Path, config: dict, output: Path) -> dict:
    verify_bundle(root)
    output_boundary(root, output)
    blockers = []
    try:
        validate_config(config)
    except PreparationError as exc:
        blockers.append(str(exc))
    versions = locked_versions(root)
    actual = {}
    for name, version in versions.items():
        try:
            actual[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual[name] = None
        if actual[name] != version:
            blockers.append(f"package {name} requires {version}; installed {actual[name]}")
    if sys.version_info[:2] != (3, 11):
        blockers.append("Python 3.11 required by project contract")
    if not blockers or all("package " in b or "Python " in b for b in blockers):
        home = Path(config["hf_home"])
        blockers += snapshot_blockers(home, MODEL_ID, config["model_revision"], model=True)
        blockers += snapshot_blockers(home, ENCODER_ID, config["encoder_revision"], model=False)
    return {
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "expected_packages": versions,
        "installed_packages": actual,
        "hardware_checked": False,
        "scientific_ready": False,
    }


def probe_hardware() -> dict:
    """Only called after opt-in, data and runtime gates; never during preparation."""
    import torch

    if not torch.cuda.is_available():
        raise PreparationError("genuine run requires CUDA on Kaggle T4")
    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    if not names or any("T4" not in name for name in names):
        raise PreparationError("research run requires the approved Kaggle T4 hardware")
    return {
        "gpu_names": names,
        "compute_capability": [
            list(torch.cuda.get_device_capability(i)) for i in range(len(names))
        ],
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
    }


def offline_environment(root: Path, config: dict) -> dict[str, str]:
    # Never copy the ambient environment wholesale (tokens/credentials are not needed).
    permitted = ("PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "LANG", "LC_ALL")
    env = {name: os.environ[name] for name in permitted if name in os.environ}
    env.update(
        PYTHONPATH=str(root / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        HF_HOME=config["hf_home"],
        HF_HUB_CACHE=str(Path(config["hf_home"]) / "hub"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TOKENIZERS_PARALLELISM="false",
    )
    return env


def run_campaign(
    root: Path,
    config: dict,
    output: Path,
    *,
    real_inference: bool,
    baseline: str = "all",
    replicate: int | None = None,
) -> list[dict]:
    if not real_inference:
        raise PreparationError("execution requires explicit --real-inference")
    planned = plan_runs(root, config, output)
    chosen = [
        r
        for r in planned
        if (baseline == "all" or r["baseline"] == baseline)
        and (replicate is None or r["replicate"] == replicate)
    ]
    if not chosen:
        raise PreparationError("no valid run selected")
    for item in chosen:
        if Path(item["folder"]).exists() or Path(item["folder"]).is_symlink():
            raise PreparationError(f"existing run output must not be overwritten: {item['run_id']}")
    runtime = preflight_runtime(root, config, output)
    if runtime["status"] != "ready":
        raise PreparationError("runtime blocked: " + "; ".join(runtime["blockers"]))
    data = preflight_data(root)
    hardware = probe_hardware()
    manifest = verify_bundle(root)
    completed = []
    for item in chosen:
        folder = Path(item["folder"])
        folder.mkdir(parents=True, exist_ok=False)
        record = {
            **item,
            "status": "started",
            "config": config,
            "config_sha256": sha256(canonical(config)),
            "bundle_content_sha256": manifest["content_sha256"],
            "hardware": hardware,
            "runtime": runtime,
            "installed_inventory": {
                d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
            },
            "data": data,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "scientific_status": "not_assessed",
        }
        (folder / "run.json").write_bytes(canonical(record))
        try:
            with (
                (folder / "stdout.log").open("w") as stdout,
                (folder / "stderr.log").open("w") as stderr,
            ):
                process = subprocess.run(
                    item["argv"],
                    cwd=root,
                    env=offline_environment(root, config),
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    check=False,
                    timeout=config["run_timeout_seconds"],
                )
            record["returncode"] = process.returncode
            if process.returncode:
                raise PreparationError(
                    f"native process failed: {item['run_id']}, exit {process.returncode}"
                )
            for name in ("predictions.jsonl", "native-log.jsonl", "native-report.json"):
                if not (folder / name).is_file():
                    raise PreparationError(f"native output missing: {name}")
            record["native_outputs"] = {
                name: sha256((folder / name).read_bytes())
                for name in ("predictions.jsonl", "native-log.jsonl", "native-report.json")
            }
            record["status"] = "completed_native_inference"
        except (KeyboardInterrupt, SystemExit) as exc:
            record["status"], record["error"] = "interrupted", type(exc).__name__
            raise
        except Exception as exc:
            record["status"], record["error"] = "failed", str(exc)
            raise PreparationError(f"native run stopped; evidence preserved: {exc}") from exc
        finally:
            record["finished_at_utc"] = datetime.now(UTC).isoformat()
            (folder / "run.json").write_bytes(canonical(record))
        completed.append(record)
    return completed
