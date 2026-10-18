"""Private notebook operations; unchanged immutable CLI25/CLI17 perform inference.

No execution on import. Default notebook settings authorize no side effects.
This file is embedded verbatim in notebook 16; it is outside the accepted bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

BUNDLE_SHA256 = "2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de"
MODEL_REVISION = "8afb486c1db24fe5011ec46dfbe5b5dccdb575c2"
ENCODER_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
INVENTORY_SHA256 = "ae3b7dc2361f151bcc59d68f4b2ddcdef74b99a5fe8374b041190bded84d84f1"
SETUP_HASHES = {
    "scripts/26_kaggle_environment.py": (
        "91be7869ae7223b93e7ff6c3c7a58589b241161ef7a782351f02e105e86d9218"
    ),
    "configs/kaggle-b12-model-pins.json": (
        "6f72c03fe03c379b1ed0844192ef17c94cb60e908c5269f0e49750a32f04998a"
    ),
    "configs/kaggle-b12-requirements.lock.txt": (
        "da3c09c04886fca688aa6a2e54aa1d7c46726be5a4c67b19bc2ba8b9ab36a5cd"
    ),
    "configs/kaggle-b12-bootstrap.lock.txt": (
        "021d7fd19573db49d3acd74056047912457790f20ceffb4d1196ebffa067a9c8"
    ),
}
PROCESS_CAP = 5400
SETUP_CAP = 1200
SESSION_CAP = 7200


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def discover_inputs(mount):
    archives = list(mount.rglob("input-bundle.bundle"))
    inventories = list(mount.rglob("b12-cache-inventory.json"))
    if len(archives) != 1 or len(inventories) != 1:
        raise ValueError("Exactly one accepted bundle and cache inventory required")
    archive, inventory = archives[0], inventories[0]
    kit, home = archive.parent, inventory.parent / "hf-home"
    for name, expected in SETUP_HASHES.items():
        path = kit / name
        if not path.resolve().is_relative_to(mount.resolve()) or digest(path) != expected:
            raise ValueError("Setup fingerprint mismatch: " + name)
    if digest(archive) != BUNDLE_SHA256 or digest(inventory) != INVENTORY_SHA256:
        raise ValueError("Accepted archive/cache-v5 inventory fingerprint mismatch")
    if not home.is_dir() or not home.resolve().is_relative_to(mount.resolve()):
        raise ValueError("Cache must stay mounted read-only under inputs")
    return archive, kit, inventory, home


def extract_inputs(archive, workspace):
    if digest(archive) != BUNDLE_SHA256:
        raise ValueError("Accepted bundle fingerprint mismatch")
    if workspace.exists() or workspace.is_symlink():
        raise ValueError("existing extraction destination")
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if (
            len(members) != 182
            or len({m.name for m in members}) != 182
            or sum(m.size for m in members) > 128 * 1024 * 1024
        ):
            raise ValueError("Bundle member count/size invalid")
        for m in members:
            p = PurePosixPath(m.name)
            if (
                not m.isfile()
                or p.is_absolute()
                or str(p) != m.name
                or any(x in {".", ".."} or x.startswith(".") for x in m.name.split("/"))
            ):
                raise ValueError("Unsafe bundle entry")
        bundle.extractall(workspace, filter="data")


def runtime_config(root, campaign, home, language):
    config = json.loads((root / "configs/kaggle-b12-run.template.json").read_bytes())
    config.update(
        campaign_id=campaign,
        language=language,
        hf_home=str(home),
        model_revision=MODEL_REVISION,
        encoder_revision=ENCODER_REVISION,
        run_timeout_seconds=PROCESS_CAP,
    )
    return config


def campaign_plan(root, campaign, home, output):
    from nl2sparql.kaggle.runner import plan_runs

    return [
        dict(item, config=config)
        for language in ("en", "vi")
        for config in [runtime_config(root, campaign, home, language)]
        for item in plan_runs(root, config, output)
    ]


def select_process(plan, baseline, language, replicate, prior_attempts=()):
    matches = [
        r
        for r in plan
        if (r["baseline"], r["language"], r["replicate"]) == (baseline, language, replicate)
    ]
    if len(matches) != 1:
        raise ValueError("Select exactly one planned process")
    item = matches[0]
    if item["run_id"] in prior_attempts:
        raise ValueError("existing campaign attempt; never resume or overwrite")
    if Path(item["folder"]).exists() or Path(item["folder"]).is_symlink():
        raise ValueError("existing run output must not be overwritten")
    return item


def run_logged(argv, env, log, timeout):
    """Kill the complete process group on timeout/interrupt, keeping streamed logs."""
    if timeout <= 0:
        raise TimeoutError("Session/setup budget exhausted")
    with log.open("x") as stream:
        process = subprocess.Popen(
            argv, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            # Native CLI17 is a grandchild when CLI25 is the immediate child.
            # Kill the group even if its leader exited while handling our signal.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
    if code:
        raise RuntimeError(f"Stage failed: exit={code}; inspect {log.name}")


def cleanup_scratch(scratch, working):
    if (
        scratch.is_symlink()
        or scratch.parent.resolve() != working.resolve()
        or scratch == working
        or not scratch.name.startswith("b12-scratch-")
    ):
        raise ValueError("Cleanup requires a notebook-owned scratch child")
    if scratch.exists():
        shutil.rmtree(scratch)  # shutil does not follow directory symlinks.


def check_complete(root, item):
    """Runtime/artifact completeness only. Do not gate on accuracy or SQL validity."""
    from nl2sparql.models.b12.evaluate import load_evaluation_cases

    language = item["language"]
    snapshot = root / (
        "data/dataset/test/test-100.jsonl"
        if language == "en"
        else "data/dataset/test/test-100-vi.jsonl"
    )
    cases = load_evaluation_cases(snapshot, language=language, source_root=root)
    expected = [case.case_id for case in cases]
    folder = Path(item["folder"])
    run = json.loads((folder / "run.json").read_bytes())
    report = json.loads((folder / "native-report.json").read_bytes())
    rows = [json.loads(line) for line in (folder / "predictions.jsonl").read_text().splitlines()]
    logs = [json.loads(line) for line in (folder / "native-log.jsonl").read_text().splitlines()]
    if (
        len(expected) != 100
        or [r["case_id"] for r in rows] != expected
        or [r["case_id"] for r in logs] != expected
        or report["prediction_count"] != 100
        or report["metrics"]["total"] != 100
        or run["status"] != "completed_native_inference"
    ):
        raise ValueError("Incomplete native process; preserve entire attempt")
    for obj in [run, report, *rows, *logs]:
        if obj["run_id"] != item["run_id"] or obj["language"] != language:
            raise ValueError("Native run/language mismatch")
    if any(obj["baseline"] != item["baseline"] for obj in (run, report)):
        raise ValueError("Native baseline mismatch")
    if set(run["native_outputs"]) != {
        "predictions.jsonl",
        "native-log.jsonl",
        "native-report.json",
    }:
        raise ValueError("Native output hash inventory incomplete")
    for row, log in zip(rows, logs, strict=True):
        prediction = row["prediction"]
        completion = prediction["completion"]
        if (
            prediction["baseline"] != item["baseline"]
            or completion["synthetic_backend"] is not False
            or log["synthetic_backend"] is not False
            or completion["model_revision"] != MODEL_REVISION
        ):
            raise ValueError("Native runtime provenance mismatch")
    for name, expected_hash in run["native_outputs"].items():
        if digest(folder / name) != expected_hash:
            raise ValueError("Native artifact digest mismatch")
    return {
        "status": "complete_100_native_cases",
        "language": language,
        "N": 100,
        "scientific_ready": False,
        "accuracy_assessed_by_driver": False,
    }


def worker(root, home, output, settings, evidence):
    # The runtime's PYTHONPATH points exclusively at immutable bundle source.
    if sys.version_info[:3] != (3, 11, 15):
        raise ValueError("Exact smoke Python 3.11.15 required")
    from nl2sparql.kaggle.bundle import preflight_data
    from nl2sparql.kaggle.runner import preflight_runtime, run_campaign

    plan = campaign_plan(root, settings["campaign_id"], home, output)
    write_new(evidence / "campaign-plan.json", plan)
    item = select_process(
        plan,
        settings["baseline"],
        settings["language"],
        settings["replicate"],
        settings["prior_attempts"],
    )
    config = item["config"]
    write_new(evidence / "run-config.json", config)
    data = preflight_data(root)
    runtime = preflight_runtime(root, config, output)
    write_new(evidence / "data-preflight.json", data)
    write_new(evidence / "runtime-preflight.json", runtime)
    if data["status"] != "data_ready" or runtime["status"] != "ready":
        raise ValueError("Data/runtime preflight blocked")
    if not settings["allow_real_inference"]:
        return "prepared_without_inference"
    # Reserve identity before any native process. Carry this ledger to next session.
    write_new(
        evidence / "campaign-ledger.json",
        {
            "campaign_id": settings["campaign_id"],
            "attempted_run_ids": [*settings["prior_attempts"], item["run_id"]],
            "scientific_ready": False,
        },
    )
    run_campaign(
        root,
        config,
        output,
        real_inference=True,
        baseline=item["baseline"],
        replicate=item["replicate"],
    )
    write_new(evidence / "completeness.json", check_complete(root, item))
    return "completed_native_process"


def prepare(
    settings, *, mount=Path("/kaggle/input"), working=Path("/kaggle/working"), driver_source=None
):
    if not settings["allow_preparation"]:
        print("BLOCKED: preparation/install/inference disabled")
        return
    if settings["allow_real_inference"] and not settings["allow_env_install"]:
        raise ValueError("Explicit install opt-in required for a fresh pinned runtime")
    for key in ("campaign_id", "session_id"):
        if not isinstance(settings[key], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", settings[key]
        ):
            raise ValueError("Set safe explicit " + key)
    if (
        settings["baseline"] not in ("b1", "b2")
        or settings["language"] not in ("en", "vi")
        or type(settings["replicate"]) is not int
        or settings["replicate"] not in (1, 2, 3)
    ):
        raise ValueError("Choose one baseline/language/replicate")
    prior = settings["prior_attempts"]
    valid_ids = {
        f"{settings['campaign_id']}-{b}-{lang}-r{rep:02d}"
        for b in ("b1", "b2")
        for lang in ("en", "vi")
        for rep in (1, 2, 3)
    }
    selected = (
        f"{settings['campaign_id']}-{settings['baseline']}-"
        f"{settings['language']}-r{settings['replicate']:02d}"
    )
    if (
        not isinstance(prior, list)
        or any(x not in valid_ids for x in prior)
        or len(set(prior)) != len(prior)
        or selected in prior
    ):
        raise ValueError("Supply prior attempted IDs from retained campaign ledger; no reuse")
    if not prior and (settings["baseline"], settings["language"], settings["replicate"]) != (
        "b1",
        "en",
        1,
    ):
        raise ValueError("First process must be full B1 EN r01; review completeness before more")
    if prior and settings.get("prior_completeness_reviewed") is not True:
        raise ValueError("Review prior runtime/artifact completeness before continuing")
    base = working / ("b12-benchmark-" + settings["campaign_id"])
    if base.is_symlink() or working.is_symlink():
        raise ValueError("Unsafe working output alias")
    base.mkdir(exist_ok=True)
    evidence = base / ("session-" + settings["session_id"])
    evidence.mkdir(exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix="b12-scratch-", dir=working))
    started = time.monotonic()
    summary = {
        "status": "failed",
        "scientific_ready": False,
        "settings": settings,
        "session_cap_seconds": SESSION_CAP,
        "process_cap_seconds": PROCESS_CAP,
    }
    stage = "input_discovery"
    try:
        archive, kit, inventory, home = discover_inputs(mount)
        workspace, runtime = scratch / "input", scratch / "runtime"
        bootstrap = scratch / "bootstrap"
        extract_inputs(archive, workspace)
        write_new(
            evidence / "input-provenance.json",
            {
                "bundle_sha256": BUNDLE_SHA256,
                "payload_files": 181,
                "tar_members": 182,
                "setup_hashes": SETUP_HASHES,
                "cache_inventory_sha256": digest(inventory),
                "cache_version": 5,
                "hf_home": str(home),
                "weights_copied": False,
            },
        )
        if not settings["allow_env_install"]:
            summary["status"] = "inputs_verified_install_disabled"
            return
        env = {
            k: os.environ[k]
            for k in ("PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "LANG", "LC_ALL")
            if k in os.environ
        }
        env.update(
            UV_CACHE_DIR=str(scratch / "uv-cache"),
            UV_PYTHON_INSTALL_DIR=str(scratch / "python"),
            HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
            HF_HUB_DISABLE_TELEMETRY="1",
            PYTHONDONTWRITEBYTECODE="1",
        )

        def setup(argv, name, custom_env=None):
            nonlocal stage
            stage = name
            run_logged(
                argv,
                custom_env or env,
                evidence / (name + ".log"),
                SETUP_CAP - (time.monotonic() - started),
            )

        setup(
            [
                sys.executable,
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-deps",
                "--require-hashes",
                "--target",
                str(bootstrap),
                "-r",
                str(kit / "configs/kaggle-b12-bootstrap.lock.txt"),
            ],
            "install_bootstrap",
        )
        uv = str(bootstrap / "bin/uv")
        setup(
            [uv, "--no-config", "venv", "--python", "3.11.15", "--managed-python", str(runtime)],
            "create_python311",
        )
        python = str(runtime / "bin/python")
        setup(
            [
                uv,
                "--no-config",
                "--no-cache",
                "pip",
                "sync",
                "--python",
                python,
                "--require-hashes",
                "--index-url",
                "https://pypi.org/simple",
                str(kit / "configs/kaggle-b12-requirements.lock.txt"),
            ],
            "install_locked_environment",
        )
        offline = dict(
            env,
            PYTHONPATH=str(workspace / "src"),
            HF_HOME=str(home),
            HF_HUB_CACHE=str(home / "hub"),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            TOKENIZERS_PARALLELISM="false",
        )
        setup(
            [
                python,
                str(kit / "scripts/26_kaggle_environment.py"),
                "verify-cache",
                "--pins",
                str(kit / "configs/kaggle-b12-model-pins.json"),
                "--hf-home",
                str(home),
                "--component",
                "all",
            ],
            "verify_mounted_cache",
            offline,
        )
        # Retain the exact operational source and settings, outside immutable bundle.
        source = evidence / "benchmark-driver.py"
        source.write_text(
            driver_source if driver_source is not None else Path(__file__).read_text()
        )
        write_new(evidence / "settings.json", settings)
        stage = "native_cli25"
        run_logged(
            [
                python,
                str(source),
                "--worker",
                "--root",
                str(workspace),
                "--home",
                str(home),
                "--output",
                str(base / "runs"),
                "--settings",
                str(evidence / "settings.json"),
                "--evidence",
                str(evidence),
            ],
            offline,
            evidence / "worker.log",
            min(PROCESS_CAP + 60, SESSION_CAP - 120 - (time.monotonic() - started)),
        )
        summary["status"] = (
            "completed_native_process"
            if settings["allow_real_inference"]
            else "prepared_without_inference"
        )
    except BaseException as exc:
        summary.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        summary.update(stage=stage, wall_seconds=time.monotonic() - started)
        try:
            cleanup_scratch(scratch, working)
            summary["scratch_removed"] = True
        finally:
            write_new(evidence / "driver-summary.json", summary)
            files = {
                str(p.relative_to(base)): {"bytes": p.stat().st_size, "sha256": digest(p)}
                for p in base.rglob("*")
                if p.is_file() and not p.is_symlink()
            }
            write_new(evidence / "artifacts-manifest.json", files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    for name in ("root", "home", "output", "settings", "evidence"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if not args.worker or any(
        getattr(args, n) is None for n in ("root", "home", "output", "settings", "evidence")
    ):
        parser.error("Operational worker requires all paths; use disabled notebook for preparation")
    settings = json.loads(args.settings.read_bytes())
    print(worker(args.root, args.home, args.output, settings, args.evidence), flush=True)


if __name__ == "__main__":
    main()
