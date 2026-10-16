"""CLI for building inputs, planning and explicitly opting into future Kaggle runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nl2sparql.kaggle.bundle import (
    PreparationError,
    build_bundle,
    extract_bundle,
    preflight_data,
    sha256,
)
from nl2sparql.kaggle.runner import plan_runs, preflight_runtime, run_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bundle = sub.add_parser("bundle")
    bundle.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    bundle.add_argument("--output", type=Path, required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--archive", type=Path, required=True)
    unpack.add_argument("--output", type=Path, required=True)
    unpack.add_argument("--sha256", required=True)
    for name in ("preflight", "plan", "run"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--config", type=Path)
        command.add_argument("--output", type=Path, default=Path("/kaggle/working/b12-runs"))
        if name == "preflight":
            command.add_argument("--level", choices=("data", "runtime"), default="data")
        if name == "run":
            command.add_argument("--real-inference", action="store_true")
            command.add_argument("--baseline", choices=("all", "b1", "b2"), default="all")
            command.add_argument("--replicate", type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    try:
        if args.command == "bundle":
            manifest = build_bundle(args.root, args.output)
            result = {
                "status": "bundle_prepared",
                "files": len(manifest["files"]),
                "archive": str(args.output),
                "sha256": sha256(args.output.read_bytes()),
                "content_sha256": manifest["content_sha256"],
                "scientific_ready": False,
            }
        elif args.command == "unpack":
            extract_bundle(args.archive, args.output, args.sha256)
            result = {"status": "unpacked", "root": str(args.output)}
        elif args.command == "preflight" and args.level == "data":
            result = preflight_data(args.root)
        else:
            if args.config is None:
                raise PreparationError("an explicit --config is required")
            config = json.loads(args.config.read_bytes())
            if args.command == "preflight":
                result = preflight_runtime(args.root, config, args.output)
            elif args.command == "plan":
                result = {
                    "status": "planned_not_executed",
                    "runs": plan_runs(args.root, config, args.output),
                }
            else:
                result = {
                    "status": "native_runs_completed",
                    "runs": run_campaign(
                        args.root,
                        config,
                        args.output,
                        real_inference=args.real_inference,
                        baseline=args.baseline,
                        replicate=args.replicate,
                    ),
                }
        print(json.dumps(result, sort_keys=True))
        return 2 if result.get("status") == "blocked" else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc), "scientific_ready": False}))
        return 2
