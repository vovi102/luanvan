"""Prepare retained B12 evidence offline; never constructs a query executor."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.evaluation.adapters.b12 import B12AdaptRequest, adapt_b12
from nl2sparql.evaluation.adapters.common import read_jsonl_objects, sha256_file
from nl2sparql.evaluation.artifacts import (
    canonical_json,
    publish_immutable,
    serialize_prediction_run,
    validate_new_artifact_path,
)
from nl2sparql.evaluation.contracts import EvaluationError
from nl2sparql.evaluation.sql_semantics import analyze_sql, exact_match, structural_match
from nl2sparql.models.b12.paired_snapshot import source_paths

MATRIX = "docs/evidence/kaggle-b12-generation-matrix-2026-10-23.json"
OUTPUT = "docs/evidence/t54-offline-2026-10-23"
FAILURES = (
    ("b12-envi-20261018-c01-b2-en-r03", "kaggle-b12-benchmark-b2-en-r03-2026-10-21"),
    (
        "b12-envi-20261018-c01-replacement01-b2-en-r03",
        "kaggle-b12-benchmark-b2-en-r03-replacement01-2026-10-23",
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationError(message)


def _source(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    _require(path.is_relative_to(root.resolve()), "source escapes benchmark root")
    return path


def prepare(root: Path, matrix_path: Path) -> tuple[dict[str, bytes], tuple[Path, ...]]:
    """Validate complete campaign before returning any bytes for publication."""
    matrix = json.loads(matrix_path.read_bytes())
    rows = matrix["rows"]
    slots = {(b, lang, rep) for b in ("b1", "b2") for lang in ("en", "vi") for rep in (1, 2, 3)}
    _require(len(rows) == 12, "campaign requires exactly twelve successful runs")
    _require(
        {(r["baseline"], r["language"], r["replicate"]) for r in rows} == slots,
        "campaign role coverage mismatch",
    )
    ids = {r["run_id"] for r in rows}
    _require(len(ids) == 12, "duplicate successful run ID")
    failures = {item["run_id"] for item in matrix["failed_attempts"]}
    _require(failures == {item[0] for item in FAILURES}, "failed-attempt identity mismatch")
    attempted = matrix["retained_native_ledger"]["attempted_run_ids"]
    _require(
        len(attempted) == len(set(attempted)) == 14 and set(attempted) == ids | failures,
        "retained ledger does not bind all fourteen attempted IDs",
    )
    protected = [matrix_path, Path(__file__).resolve(), *source_paths(root)]
    files = {}
    audits, traces, failed_audits = [], [], []
    groups = defaultdict(list)
    for run_id, folder in FAILURES:
        base = root / "docs/evidence" / folder
        manifest_path = base / "artifacts-manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        for relative, expected in manifest.items():
            path = _source(root, str((base / relative).relative_to(root)))
            _require(
                path.stat().st_size == expected["bytes"]
                and sha256_file(path) == expected["sha256"],
                "failed setup archive mismatch",
            )
            protected.append(path)
        protected.append(manifest_path)
        failed_audits.append(
            {
                "run_id": run_id,
                "native_inference_started": False,
                "canonical_run": None,
                "accuracy_denominator": None,
                "manifest_path": str(manifest_path.relative_to(root)),
                "manifest_sha256": sha256_file(manifest_path),
                "verified_files": len(manifest),
            }
        )

    for row in sorted(rows, key=lambda r: (r["baseline"], r["language"], r["replicate"])):
        run_path = _source(root, row["source_run_json"])
        native = json.loads(run_path.read_bytes())
        folder = run_path.parent
        report_path = folder / "native-report.json"
        _require(
            sha256_file(run_path) == row["source_run_sha256"]
            and sha256_file(report_path) == row["source_report_sha256"],
            "source hash mismatch",
        )
        _require(
            native["status"] == "completed_native_inference" and native["returncode"] == 0,
            "native completion missing",
        )
        _require(
            (native["run_id"], native["baseline"], native["language"], native["replicate"])
            == (row["run_id"], row["baseline"], row["language"], row["replicate"]),
            "native run identity mismatch",
        )
        for name, digest in native["native_outputs"].items():
            path = _source(root, str((folder / name).relative_to(root)))
            _require(sha256_file(path) == digest, "native output hash mismatch")
            protected.append(path)
        language = row["language"]
        snapshot = (
            root
            / "data/dataset/test"
            / ("test-100.jsonl" if language == "en" else "test-100-vi.jsonl")
        )
        predictions_path, log_path = folder / "predictions.jsonl", folder / "native-log.jsonl"
        run = adapt_b12(
            B12AdaptRequest(
                snapshot,
                predictions_path,
                log_path,
                report_path,
                language=language,
                source_root=root,
            )
        )
        _require(
            run.test_case_count == 100 and not run.provenance.synthetic,
            "campaign requires one hundred genuine cases per run",
        )
        _require(
            all(
                not r["prediction"]["completion"]["synthetic_backend"]
                for r in read_jsonl_objects(predictions_path)
            ),
            "synthetic completion",
        )
        report = json.loads(report_path.read_bytes())
        _require(
            report["scientific_ready"] is False and report["blockers"] == row["native_blockers"],
            "native blockers changed",
        )
        path = f"canonical/{run.run_id}.json"
        _require(Path(path).parent == Path("canonical"), "invalid run ID for output path")
        payload = serialize_prediction_run(run)
        files[path] = payload
        sources = {
            role: {"path": str(p.relative_to(root)), "sha256": sha256_file(p)}
            for role, p in (
                ("run", run_path),
                ("predictions", predictions_path),
                ("log", log_path),
                ("report", report_path),
                ("test_set", snapshot),
            )
        }
        protected.extend((run_path, snapshot, report_path, log_path, predictions_path))
        statuses = Counter()
        gold_ok = predicted_ok = exact = structural = 0
        for number, (case, original) in enumerate(
            zip(run.cases, read_jsonl_objects(predictions_path), strict=True), start=1
        ):
            prediction = original["prediction"]
            statuses[prediction["extraction_status"]] += 1
            validate_sql_text(case.gold_sql)
            analyze_sql(case.gold_sql)
            gold_ok += 1
            if case.prediction_status == "ok":
                validate_sql_text(case.predicted_sql)
                analyze_sql(case.predicted_sql)
                predicted_ok += 1
                exact += exact_match(case.predicted_sql, case.gold_sql)
                structural += structural_match(case.predicted_sql, case.gold_sql)
            traces.append(
                {
                    "run_id": run.run_id,
                    "case_id": case.case_id,
                    "language": language,
                    "baseline": run.baseline_id,
                    "replicate": row["replicate"],
                    "native_line_1based": number,
                    "test_set_sha256": run.test_set_sha256,
                    "native_predictions_sha256": sources["predictions"]["sha256"],
                    "native_case_object_sha256": hashlib.sha256(
                        canonical_json(original)
                    ).hexdigest(),
                    "canonical_path": path,
                    "raw_output_sha256": case.raw_output_sha256,
                    "native_status": prediction["extraction_status"],
                    "canonical_status": case.prediction_status,
                    "error_code": case.error_code,
                    "prompt_sha256": prediction["prompt_sha256"],
                    "selected_examples_sha256": prediction["selected_examples_sha256"],
                    "paired_source": original.get("paired_source"),
                }
            )
        _require(dict(statuses) == dict(row["status_counts"]), "status counts mismatch")
        audits.append(
            {
                "run_id": run.run_id,
                "baseline": run.baseline_id,
                "language": language,
                "replicate": row["replicate"],
                "N": 100,
                "canonical_path": path,
                "canonical_file_sha256": hashlib.sha256(payload).hexdigest(),
                "sources": sources,
                "native_status_counts": dict(statuses),
                "canonical_status_counts": dict(Counter(c.prediction_status for c in run.cases)),
                "native_scientific_ready": report["scientific_ready"],
                "native_blockers": report["blockers"],
                "canonical_provenance": asdict(run.provenance),
                "privacy_review_status": "undocumented",
                "inference_cost": "unmeasured",
                "gold_queries_static_ok": gold_ok,
                "predicted_queries_static_ok": predicted_ok,
                "exact_match_numerator": exact,
                "structural_match_numerator": structural,
                "execution_accuracy": None,
                "answer_metrics": None,
                "p50_generation_ms": report["metrics"]["p50_latency_ms"],
                "p95_generation_ms": report["metrics"]["p95_latency_ms"],
            }
        )
        groups[(run.baseline_id, language)].append(run)

    agreement = []
    for (baseline, language), runs in sorted(groups.items()):
        identities = {
            (
                r.seed,
                r.test_set_sha256,
                r.test_case_count,
                r.provenance.fingerprints,
                r.adapter_id,
                r.adapter_schema_version,
                tuple(c.case_id for c in r.cases),
            )
            for r in runs
        }
        _require(len(identities) == 1, "incompatible replicate identity")
        agreement.append(
            {
                "baseline": baseline,
                "language": language,
                "N_unique_cases": 100,
                "denominator": 100,
                "run_ids": [r.run_id for r in runs],
                "all_three_raw_output_hash_equal_cases": sum(
                    len({c.raw_output_sha256 for c in cases}) == 1
                    for cases in zip(*(r.cases for r in runs), strict=True)
                ),
                "all_three_canonical_observation_equal_cases": sum(
                    len(
                        {
                            (
                                c.prediction_status,
                                c.error_code,
                                analyze_sql(c.predicted_sql).canonical_sql
                                if c.prediction_status == "ok"
                                else None,
                            )
                            for c in cases
                        }
                    )
                    == 1
                    for cases in zip(*(r.cases for r in runs), strict=True)
                ),
            }
        )
    audit = {
        "schema_version": 1,
        "kind": "offline_reconciliation_not_execution_report",
        "matrix_sha256": sha256_file(matrix_path),
        "runs": audits,
        "failed_attempts": failed_audits,
        "attempted_ids": attempted,
        "agreement": agreement,
        "live_jobs_created": 0,
        "scientific_ready": False,
        "missing": [
            "T5.4 privacy review",
            "pricing and inference billing evidence",
            "separate BigQuery authorization",
            "genuine predicted/gold execution",
            "journal-bound evaluation reports and comparisons",
        ],
    }
    files["case-trace.jsonl"] = b"".join(canonical_json(t) for t in traces)
    files["audit.json"] = canonical_json(audit)
    files["manifest.json"] = canonical_json(
        {
            "schema_version": 1,
            "script_sha256": sha256_file(Path(__file__)),
            "matrix_sha256": sha256_file(matrix_path),
            "files": {
                name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in sorted(files.items())
            },
        }
    )
    return files, tuple(protected)


def publish(output: Path, files: dict[str, bytes], protected: tuple[Path, ...]) -> None:
    """Precheck all destinations; immutable per file, manifest published last."""
    for name in files:
        validate_new_artifact_path(output / name, protected_paths=protected)
    for name, payload in files.items():
        publish_immutable(output / name, payload, protected_paths=protected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    files, protected = prepare(root, root / MATRIX)
    publish(args.output or root / OUTPUT, files, protected)
    print("12 canonical runs, 1200 case traces, 2 retained setup failures; zero BigQuery jobs.")


if __name__ == "__main__":
    main()
