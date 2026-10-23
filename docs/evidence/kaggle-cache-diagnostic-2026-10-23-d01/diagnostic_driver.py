"""ONE-OFF CPU diagnostic, outside benchmark/bundle; never inference or a cache bypass."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

CAP_SECONDS = 1620
SETUP_SHA = "91be7869ae7223b93e7ff6c3c7a58589b241161ef7a782351f02e105e86d9218"
PINS_SHA = "6f72c03fe03c379b1ed0844192ef17c94cb60e908c5269f0e49750a32f04998a"
INVENTORY_SHA = "ae3b7dc2361f151bcc59d68f4b2ddcdef74b99a5fe8374b041190bded84d84f1"
BUNDLE_SHA = "2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write("\n")


def load_native(script):
    if sha(script) != SETUP_SHA:
        raise ValueError("Accepted verifier fingerprint mismatch")
    spec = importlib.util.spec_from_file_location("accepted_cache_verifier", script)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def observe(native, pins, home, output, *, heartbeat_seconds=10):
    """Run exact accepted verify_cache while measuring its actual Path.open/read calls."""
    started = time.monotonic()
    original_open = Path.open
    old_trace = sys.gettrace()
    journal = output / "cache-progress.jsonl"
    journal.touch(exist_ok=False)
    lock = threading.RLock()
    state = dict(phase="starting", total_bytes_read=0, files_read_complete=0)
    stop = threading.Event()
    source = Path(native.verify_cache.__code__.co_filename).read_text()
    function = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name == "verify_cache"
    )
    assignment = next(
        n
        for n in ast.walk(function)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "path" for t in n.targets)
    )
    native_code = native.verify_cache.__code__

    def event(kind, **extra):
        with lock:
            now = time.monotonic()
            snapshot = {k: v for k, v in state.items() if not k.startswith("_")}
            if "_operation_started" in state:
                snapshot["current_operation_elapsed_seconds"] = now - state["_operation_started"]
            payload = dict(event=kind, elapsed_seconds=now - started, **snapshot, **extra)
            with original_open(journal, "a") as stream:
                stream.write(json.dumps(payload, sort_keys=True) + "\n")
                stream.flush()

    def heartbeat():
        while not stop.wait(heartbeat_seconds):
            event("heartbeat")

    def trace(frame, kind, arg):
        if frame.f_code is not native_code:
            return None
        if kind == "line" and frame.f_lineno == assignment.lineno:
            local = frame.f_locals
            with lock:
                state.update(
                    file=local["kind"] + "/" + local["name"],
                    expected_bytes=local["evidence"]["bytes"],
                    phase="path_and_size_checks",
                    file_bytes_read=0,
                    read_wall_seconds=0.0,
                    read_cpu_seconds=0.0,
                    hash_and_loop_wall_seconds=0.0,
                    _file_started=time.monotonic(),
                    _operation_started=time.monotonic(),
                )
                state.pop("_previous_read_finished", None)
                event("file_started")
        return trace

    class Reader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            result = self.handle.__exit__(*args)
            with lock:
                state["phase"] = "file_read_complete_hash_comparison_pending"
                if args[0] is None and state["file_bytes_read"] == state["expected_bytes"]:
                    state["files_read_complete"] += 1
                event(
                    "file_read_complete",
                    file_wall_seconds=time.monotonic() - state["_file_started"],
                )
            return result

        def read(self, size=-1):
            now = time.monotonic()
            with lock:
                if "_previous_read_finished" in state:
                    state["hash_and_loop_wall_seconds"] += now - state["_previous_read_finished"]
                state.update(phase="read", _operation_started=now)
            cpu = time.thread_time()
            block = self.handle.read(
                size
            )  # unchanged native request size and actual returned bytes
            cpu_elapsed = time.thread_time() - cpu
            finished = time.monotonic()
            with lock:
                state["read_wall_seconds"] += finished - now
                state["read_cpu_seconds"] += cpu_elapsed
                state["file_bytes_read"] += len(block)
                state["total_bytes_read"] += len(block)
                state.update(
                    phase="hash_and_loop",
                    _previous_read_finished=finished,
                    _operation_started=finished,
                )
            return block

    def observed_open(path, *args, **kwargs):
        # Only calls from the accepted verification function are measured.
        if sys._getframe(1).f_code is not native_code:
            return original_open(path, *args, **kwargs)
        with lock:
            state.update(phase="file_open", _operation_started=time.monotonic())
            event("file_open_started")
        handle = original_open(path, *args, **kwargs)
        with lock:
            event("file_open_finished")
        return Reader(handle)

    event(
        "verification_started",
        expected_files=sum(len(m["files"]) for m in pins["models"].values()),
        expected_total_bytes=sum(
            e["bytes"] for m in pins["models"].values() for e in m["files"].values()
        ),
    )
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        Path.open = observed_open
        sys.settrace(trace)
        receipt = native.verify_cache(pins, home, "all")
        with lock:
            state["phase"] = "all_native_hash_checks_passed"
            event("verification_completed")
        return receipt
    except BaseException as exc:
        event("verification_failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        sys.settrace(old_trace)
        Path.open = original_open
        stop.set()
        thread.join(timeout=2)


def worker(mount, output):
    archives = list(mount.rglob("input-bundle.bundle"))
    inventories = list(mount.rglob("b12-cache-inventory.json"))
    if len(archives) != 1 or len(inventories) != 1:
        raise ValueError("Require one accepted setup dataset and one cache-v5 inventory")
    archive, inventory = archives[0], inventories[0]
    kit = archive.parent
    script = kit / "scripts/26_kaggle_environment.py"
    pins_path = kit / "configs/kaggle-b12-model-pins.json"
    home = inventory.parent / "hf-home"
    for path, expected in [
        (archive, BUNDLE_SHA),
        (inventory, INVENTORY_SHA),
        (script, SETUP_SHA),
        (pins_path, PINS_SHA),
    ]:
        if not path.resolve().is_relative_to(mount.resolve()) or sha(path) != expected:
            raise ValueError("Diagnostic input fingerprint/path mismatch")
    if not home.resolve().is_relative_to(mount.resolve()):
        raise ValueError("Mounted cache escaped input boundary")
    native = load_native(script)
    pins = native.load_pins(pins_path)
    write_new(
        output / "diagnostic-provenance.json",
        dict(
            started_at_utc=datetime.now(UTC).isoformat(),
            script_sha256=sha(script),
            pins_sha256=sha(pins_path),
            bundle_sha256=sha(archive),
            inventory_sha256=sha(inventory),
            python=sys.version,
            platform=platform.platform(),
            logical_cpus=os.cpu_count(),
            comparison_limit="CPU host/default Python; differs from pinned T4 benchmark runtime",
            model_loaded=False,
            inference=False,
            network_enabled=False,
            weights_copied=False,
            scientific_ready=False,
            benchmark_attempt_reserved=False,
        ),
    )
    receipt = observe(native, pins, home, output)
    write_new(output / "native-cache-receipt.json", receipt)
    print("Complete accepted cache hash verification; no inference.", flush=True)


def run_session(mount, output, source):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write_new(
        output / "diagnostic-settings.json",
        dict(
            diagnostic_only=True,
            cpu_only=True,
            verification_cap_seconds=CAP_SECONDS,
            platform_cap_seconds=1800,
            model_loaded=False,
            inference=False,
            benchmark_attempt_reserved=False,
            scientific_ready=False,
            accepted_setup_sha256=SETUP_SHA,
        ),
    )
    script = output / "diagnostic-driver.py"
    script.write_text(source)
    summary = dict(
        status="failed",
        inference=False,
        model_loaded=False,
        scientific_ready=False,
        benchmark_attempt_reserved=False,
        diagnostic_only=True,
        verification_cap_seconds=CAP_SECONDS,
    )
    process = None
    try:
        env = {
            k: os.environ[k]
            for k in ("PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL")
            if k in os.environ
        }
        env.update(
            PYTHONDONTWRITEBYTECODE="1",
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        )
        with (output / "worker.log").open("x") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(script),
                    "--worker",
                    "--mount",
                    str(mount),
                    "--output",
                    str(output),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
            code = process.wait(timeout=max(0.0, CAP_SECONDS - (time.monotonic() - started)))
        summary["returncode"] = code
        if code:
            raise RuntimeError("Diagnostic worker failed; inspect retained worker.log")
        summary["status"] = "completed_cache_diagnostic"
    except BaseException as exc:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        summary.update(
            status="timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed",
            error_type=type(exc).__name__,
        )
        raise
    finally:
        summary.update(
            wall_seconds=time.monotonic() - started,
            finished_at_utc=datetime.now(UTC).isoformat(),
        )
        write_new(output / "diagnostic-summary.json", summary)
        write_new(
            output / "artifacts-manifest.json",
            {
                p.name: dict(bytes=p.stat().st_size, sha256=sha(p))
                for p in output.iterdir()
                if p.is_file()
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--mount", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.worker:
        parser.error("Only private notebook session orchestration or explicit diagnostic worker")
    worker(args.mount, args.output)
