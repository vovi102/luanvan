import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

from click.testing import CliRunner

from nl2sparql.evaluation.artifacts import (
    load_bilingual_evaluation_report,
    serialize_evaluation_report,
)
from nl2sparql.evaluation.contracts import (
    BootstrapPolicy,
    CaseEvaluation,
    CostEvidence,
    EvaluationReport,
    Readiness,
)
from nl2sparql.linking.encoder_selection import DevelopmentSets, EncoderCandidate

ROOT = Path(__file__).parents[2]
SHA_A = "a" * 64
SHA_B = "b" * 64
PAIR_IDS = tuple(f"pair-{index:03d}" for index in range(1, 101))


def _load_script(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _RejectExternalImports:
    PREFIXES = (
        "google.cloud.bigquery",
        "google.generativeai",
        "sentence_transformers",
        "transformers",
    )

    def find_spec(self, fullname: str, path: object, target: object = None):
        if fullname.startswith(self.PREFIXES):
            raise AssertionError(f"offline validation imported {fullname}")
        return None


def _encoder_input(path: Path, *, secret: str | None = None) -> None:
    development = DevelopmentSets(
        "data/dev/en.jsonl",
        SHA_A,
        "data/dev/vi.jsonl",
        SHA_B,
        "data/dev/vi-unaccented.jsonl",
        "c" * 64,
    )
    candidate = EncoderCandidate(
        model_id="encoder/test",
        revision="d" * 40,
        artifact_sha256="e" * 64,
        license="apache-2.0",
        dimension=384,
        normalization="l2",
        english_metric=0.80,
        vietnamese_metric=0.78,
        unaccented_metric=0.75,
        schema_recall_at_5_en=0.80,
        schema_recall_at_5_vi=0.78,
        schema_recall_at_10_en=0.88,
        schema_recall_at_10_vi=0.86,
        schema_mrr_en=0.76,
        schema_mrr_vi=0.74,
        entity_top1_en=0.82,
        entity_top1_vi=0.79,
        entity_f1_en=0.81,
        entity_f1_vi=0.78,
        latency_ms=12.0,
        memory_mb=240.0,
        cache_size_bytes=4096,
        english_baseline=0.81,
    )
    document = {
        "schema_version": 1,
        "synthetic": True,
        "development_sets": asdict(development),
        "candidates": [asdict(candidate)],
    }
    if secret is not None:
        document["api_key"] = secret
    path.write_text(json.dumps(document), encoding="utf-8")


def _case(pair_id: str, success: bool) -> CaseEvaluation:
    return CaseEvaluation(
        pair_id,
        "easy",
        ("paired",),
        success,
        success,
        success,
        None,
        10.0,
        1.0,
        CostEvidence("unmeasured", None, None, None),
        CostEvidence("unmeasured", None, None, None),
        () if success else ("no_output",),
    )


def _report(name: str, success_count: int) -> EvaluationReport:
    gold_hashes = tuple(
        (pair_id, hashlib.sha256(f"gold-{pair_id}".encode()).hexdigest()) for pair_id in PAIR_IDS
    )
    return EvaluationReport(
        baseline_id=name,
        primary_run_id=f"run-{name}",
        primary_prediction_sha256=hashlib.sha256(f"prediction-{name}".encode()).hexdigest(),
        primary_execution_sha256=hashlib.sha256(f"execution-{name}".encode()).hexdigest(),
        replicate_pairs=(),
        test_set_sha256=SHA_A,
        case_set_sha256=SHA_B,
        expected_case_count=100,
        represented_case_count=100,
        readiness=Readiness((), ("synthetic_input",)),
        bootstrap=BootstrapPolicy(samples=50),
        cases=tuple(
            _case(pair_id, index < success_count) for index, pair_id in enumerate(PAIR_IDS)
        ),
        dimensions=(("gold_sql_sha256s", gold_hashes),),
        breakdowns=(),
    )


def _evaluation_inputs(root: Path) -> dict[str, Path]:
    values = {
        "english-reference": _report("english-reference", 95),
        "english": _report("english", 94),
        "vietnamese": _report("vietnamese", 90),
        "vietnamese-unaccented": _report("vietnamese-unaccented", 85),
        "translation": _report("translation", 88),
    }
    paths: dict[str, Path] = {}
    for option, report in values.items():
        path = root / f"{option}.json"
        path.write_bytes(serialize_evaluation_report(report))
        paths[option] = path
    return paths


def test_encoder_validate_only_is_offline_and_rejects_secret_fields(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script("23_select_multilingual_encoder.py", "encoder_workflow_23")
    manifest = tmp_path / "encoder-input.json"
    _encoder_input(manifest)
    sentinel = "TOP-SECRET-VALUE"
    monkeypatch.setenv("GEMINI_API_KEY", sentinel)
    blocker = _RejectExternalImports()
    sys.meta_path.insert(0, blocker)
    try:
        result = CliRunner().invoke(
            module.main,
            ["--mode", "validate-only", "--input", str(manifest)],
        )
    finally:
        sys.meta_path.remove(blocker)

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "valid"
    assert payload["mode"] == "validate-only"
    assert payload["candidate_count"] == 1
    assert sentinel not in result.output

    _encoder_input(manifest, secret=sentinel)
    invalid = CliRunner().invoke(
        module.main,
        ["--mode", "validate-only", "--input", str(manifest)],
    )
    assert invalid.exit_code != 0
    assert sentinel not in invalid.output


def test_encoder_finalize_refuses_output_alias_and_marks_synthetic(tmp_path: Path) -> None:
    module = _load_script("23_select_multilingual_encoder.py", "encoder_workflow_23_finalize")
    manifest = tmp_path / "encoder-input.json"
    _encoder_input(manifest)

    alias = CliRunner().invoke(
        module.main,
        ["--mode", "finalize", "--input", str(manifest), "--output", str(manifest)],
    )
    assert alias.exit_code != 0

    output = tmp_path / "encoder-selection.json"
    finalized = CliRunner().invoke(
        module.main,
        ["--mode", "finalize", "--input", str(manifest), "--output", str(output)],
    )
    assert finalized.exit_code == 0
    document = json.loads(output.read_bytes())
    assert document["synthetic"] is True
    assert document["selection"]["winner_model_id"] == "encoder/test"


def test_bilingual_evaluation_validate_only_is_offline_and_secret_safe(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script("24_bilingual_evaluation.py", "bilingual_workflow_24")
    paths = _evaluation_inputs(tmp_path)
    sentinel = "TOP-SECRET-VALUE"
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", sentinel)
    args = ["--mode", "validate-only", "--reviewed-count", "100", "--live-count", "100"]
    for option, path in paths.items():
        args.extend((f"--{option}", str(path)))
    blocker = _RejectExternalImports()
    sys.meta_path.insert(0, blocker)
    try:
        result = CliRunner().invoke(module.main, args)
    finally:
        sys.meta_path.remove(blocker)

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "valid"
    assert payload["genuine"] is False
    assert sentinel not in result.output


def test_bilingual_evaluation_finalize_is_immutable_non_aliasing_and_synthetic(
    tmp_path: Path,
) -> None:
    module = _load_script("24_bilingual_evaluation.py", "bilingual_workflow_24_finalize")
    paths = _evaluation_inputs(tmp_path)
    common = ["--mode", "finalize", "--reviewed-count", "100", "--live-count", "100"]
    for option, path in paths.items():
        common.extend((f"--{option}", str(path)))

    alias = CliRunner().invoke(
        module.main,
        [
            *common,
            "--report-output",
            str(paths["english"]),
            "--decision-output",
            str(tmp_path / "gate.json"),
        ],
    )
    assert alias.exit_code != 0

    report_path = tmp_path / "bilingual.json"
    decision_path = tmp_path / "gate.json"
    result = CliRunner().invoke(
        module.main,
        [
            *common,
            "--report-output",
            str(report_path),
            "--decision-output",
            str(decision_path),
        ],
    )
    assert result.exit_code == 0
    report = load_bilingual_evaluation_report(report_path)
    assert report.synthetic is True
    assert json.loads(result.output)["genuine"] is False

    repeated = CliRunner().invoke(
        module.main,
        [
            *common,
            "--report-output",
            str(report_path),
            "--decision-output",
            str(decision_path),
        ],
    )
    assert repeated.exit_code == 0
