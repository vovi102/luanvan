from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).parents[2]
STAGE_A = ROOT / "data/dataset/raw/synthetic-stage-a.jsonl"
STAGE_A_V2_CANDIDATE = ROOT / "data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl"
STAGE_A_V2_CANDIDATE_MANIFEST = ROOT / "data/dataset/raw/generation-config-v2-candidate.json"
CATALOG = ROOT / "src/nl2sparql/dataset/bilingual/templates.json"


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
        "openai",
        "sentence_transformers",
        "transformers",
        "torch",
    )

    def find_spec(self, fullname: str, path: object, target: object = None):
        if fullname.startswith(self.PREFIXES):
            raise AssertionError(f"offline workflow imported {fullname}")
        return None


def _held_out_files(root: Path) -> tuple[Path, Path]:
    english = root / "english.jsonl"
    vietnamese = root / "vietnamese.jsonl"
    english.write_text(
        json.dumps(
            {
                "id": "held-en-1",
                "nl": (
                    "held out english wording with twelve wholly unrelated comparison tokens here"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    vietnamese.write_text(
        json.dumps(
            {
                "pair_id": "held-vi-1",
                "question": "câu tiếng việt giữ lại với nhiều từ hoàn toàn không liên quan ở đây",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return english, vietnamese


def _accepted_manifest(tmp_path: Path, stage_a: Path) -> Path:
    candidate = json.loads(STAGE_A_V2_CANDIDATE_MANIFEST.read_text(encoding="utf-8"))
    candidate.update(
        {
            "lifecycle_state": "accepted",
            "acceptance_eligible": True,
            "verification_mode": "live_witness",
            "verified_record_count": 1000,
            "cache_hit_count": 0,
        }
    )
    candidate["artifact_sha256"] = hashlib.sha256(stage_a.read_bytes()).hexdigest()
    output = tmp_path / "accepted-stage-a-manifest.json"
    output.write_text(json.dumps(candidate), encoding="utf-8")
    return output


def _exclusion_index(tmp_path: Path) -> Path:
    validator = _load_script(
        "21_validate_bilingual_training.py", f"bilingual_training_21_{tmp_path.name}"
    )
    english, vietnamese = _held_out_files(tmp_path)
    exclusion = tmp_path / "exclusion.json"
    result = CliRunner().invoke(
        validator.main,
        [
            "--mode",
            "index-exclusions",
            "--english-benchmark",
            str(english),
            "--vietnamese-draft",
            str(vietnamese),
            "--exclusion-index",
            str(exclusion),
        ],
    )
    assert result.exit_code == 0, result.output
    return exclusion


def test_candidate_validate_only_reports_lifecycle_but_cannot_create_audit_sample(
    tmp_path: Path,
) -> None:
    builder = _load_script("20_build_bilingual_training.py", "bilingual_training_20_candidate")
    exclusion = _exclusion_index(tmp_path)
    common = [
        "--stage-a",
        str(STAGE_A_V2_CANDIDATE),
        "--stage-a-manifest",
        str(STAGE_A_V2_CANDIDATE_MANIFEST),
        "--catalog",
        str(CATALOG),
        "--exclusion-index",
        str(exclusion),
    ]

    diagnostic = CliRunner().invoke(builder.main, ["--mode", "validate-only", *common])
    assert diagnostic.exit_code == 0, diagnostic.output
    summary = json.loads(diagnostic.output)
    assert summary["source_lifecycle_state"] == "candidate"
    assert summary["source_acceptance_eligible"] is False
    assert summary["represented_intents"] == 25

    sample_path = tmp_path / "candidate-audit-sample.jsonl"
    audit = CliRunner().invoke(
        builder.main,
        ["--mode", "audit-sample", *common, "--audit-sample-output", str(sample_path)],
    )
    assert audit.exit_code != 0
    assert "accepted Stage A v2" in audit.output
    assert not sample_path.exists()


def test_hand_edited_candidate_manifest_cannot_open_audit_gate(tmp_path: Path) -> None:
    builder = _load_script("20_build_bilingual_training.py", "bilingual_training_20_accepted")
    exclusion = _exclusion_index(tmp_path)
    accepted = _accepted_manifest(tmp_path, STAGE_A_V2_CANDIDATE)
    sample_path = tmp_path / "audit-sample.jsonl"

    result = CliRunner().invoke(
        builder.main,
        [
            "--mode",
            "audit-sample",
            "--stage-a",
            str(STAGE_A_V2_CANDIDATE),
            "--stage-a-manifest",
            str(accepted),
            "--catalog",
            str(CATALOG),
            "--exclusion-index",
            str(exclusion),
            "--audit-sample-output",
            str(sample_path),
        ],
    )

    assert result.exit_code != 0
    assert "manifest schema" in result.output
    assert not sample_path.exists()


def test_source_manifest_is_required_and_digest_bound_for_publication_modes(
    tmp_path: Path,
) -> None:
    builder = _load_script("20_build_bilingual_training.py", "bilingual_training_20_source_gate")
    exclusion = _exclusion_index(tmp_path)
    missing = CliRunner().invoke(
        builder.main,
        [
            "--mode",
            "audit-sample",
            "--stage-a",
            str(STAGE_A_V2_CANDIDATE),
            "--catalog",
            str(CATALOG),
            "--exclusion-index",
            str(exclusion),
            "--audit-sample-output",
            str(tmp_path / "missing.jsonl"),
        ],
    )
    assert missing.exit_code != 0
    assert "stage-a-manifest" in missing.output

    mismatched = json.loads(STAGE_A_V2_CANDIDATE_MANIFEST.read_text())
    mismatched["artifact_sha256"] = "0" * 64
    mismatched_path = tmp_path / "mismatched.json"
    mismatched_path.write_text(json.dumps(mismatched), encoding="utf-8")
    result = CliRunner().invoke(
        builder.main,
        [
            "--mode",
            "validate-only",
            "--stage-a",
            str(STAGE_A_V2_CANDIDATE),
            "--stage-a-manifest",
            str(mismatched_path),
            "--catalog",
            str(CATALOG),
            "--exclusion-index",
            str(exclusion),
        ],
    )
    assert result.exit_code != 0
    assert "digest" in result.output


def test_cli_help_and_catalog_validation_are_offline_and_secret_safe(
    monkeypatch,
) -> None:
    sentinel = "TOP-SECRET-PROVIDER-VALUE"
    for name in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.setenv(name, sentinel)
    blocker = _RejectExternalImports()
    sys.meta_path.insert(0, blocker)
    try:
        build = _load_script("20_build_bilingual_training.py", "bilingual_training_20")
        validate = _load_script("21_validate_bilingual_training.py", "bilingual_training_21")
        build_help = CliRunner().invoke(build.main, ["--help"])
        validate_help = CliRunner().invoke(validate.main, ["--help"])
        catalog_result = CliRunner().invoke(
            validate.main,
            ["--mode", "validate-catalog", "--catalog", str(CATALOG)],
        )
    finally:
        sys.meta_path.remove(blocker)

    assert build_help.exit_code == 0
    assert validate_help.exit_code == 0
    assert catalog_result.exit_code == 0
    summary = json.loads(catalog_result.output)
    assert summary == {
        "catalog_entries": 200,
        "intent_count": 25,
        "mode": "validate-catalog",
        "status": "valid",
    }
    assert sentinel not in build_help.output + validate_help.output + catalog_result.output


def test_exclusion_index_mode_emits_only_hashes_and_counts(tmp_path: Path, monkeypatch) -> None:
    module = _load_script("21_validate_bilingual_training.py", "bilingual_training_21_index")
    english, vietnamese = _held_out_files(tmp_path)
    output = tmp_path / "exclusion-index.json"
    sentinel = "TOP-SECRET-PROVIDER-VALUE"
    monkeypatch.setenv("GEMINI_API_KEY", sentinel)

    result = CliRunner().invoke(
        module.main,
        [
            "--mode",
            "index-exclusions",
            "--english-benchmark",
            str(english),
            "--vietnamese-draft",
            str(vietnamese),
            "--exclusion-index",
            str(output),
        ],
    )

    assert result.exit_code == 0
    summary = json.loads(result.output)
    assert summary["status"] == "indexed"
    assert summary["source_record_counts"] == [1, 1]
    assert summary["ngram_size"] == 12
    payload = output.read_text(encoding="utf-8")
    assert "held out english wording" not in payload
    assert "câu tiếng việt" not in payload
    assert "held-en-1" not in payload
    assert "held-vi-1" not in payload
    assert sentinel not in payload + result.output


def test_build_validate_only_is_offline_zero_call_and_reports_source_shape(
    tmp_path: Path, monkeypatch
) -> None:
    validator = _load_script("21_validate_bilingual_training.py", "bilingual_training_21_prep")
    builder = _load_script("20_build_bilingual_training.py", "bilingual_training_20_validate")
    english, vietnamese = _held_out_files(tmp_path)
    exclusion = tmp_path / "exclusion.json"
    indexed = CliRunner().invoke(
        validator.main,
        [
            "--mode",
            "index-exclusions",
            "--english-benchmark",
            str(english),
            "--vietnamese-draft",
            str(vietnamese),
            "--exclusion-index",
            str(exclusion),
        ],
    )
    assert indexed.exit_code == 0
    sentinel = "TOP-SECRET-PROVIDER-VALUE"
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)
    blocker = _RejectExternalImports()
    sys.meta_path.insert(0, blocker)
    try:
        result = CliRunner().invoke(
            builder.main,
            [
                "--mode",
                "validate-only",
                "--stage-a",
                str(STAGE_A),
                "--catalog",
                str(CATALOG),
                "--exclusion-index",
                str(exclusion),
            ],
        )
    finally:
        sys.meta_path.remove(blocker)

    assert result.exit_code == 0
    summary = json.loads(result.output)
    assert summary["status"] == "valid"
    assert summary["stage_a_records"] == 1000
    assert summary["represented_intents"] == 16
    assert summary["catalog_intents"] == 25
    assert summary["expanded_records"] == 8000
    assert summary["api_request_count"] == 0
    assert summary["recorded_cost_usd"] == 0.0
    assert summary["provider"] is None
    assert summary["generation_model"] is None
    assert sentinel not in result.output


def test_audit_sample_fails_closed_for_pinned_stage_a_missing_nine_intents(
    tmp_path: Path,
) -> None:
    validator = _load_script("21_validate_bilingual_training.py", "bilingual_training_21_audit")
    builder = _load_script("20_build_bilingual_training.py", "bilingual_training_20_audit")
    english, vietnamese = _held_out_files(tmp_path)
    exclusion = tmp_path / "exclusion.json"
    assert (
        CliRunner()
        .invoke(
            validator.main,
            [
                "--mode",
                "index-exclusions",
                "--english-benchmark",
                str(english),
                "--vietnamese-draft",
                str(vietnamese),
                "--exclusion-index",
                str(exclusion),
            ],
        )
        .exit_code
        == 0
    )

    result = CliRunner().invoke(
        builder.main,
        [
            "--mode",
            "audit-sample",
            "--stage-a",
            str(STAGE_A),
            "--catalog",
            str(CATALOG),
            "--exclusion-index",
            str(exclusion),
            "--audit-sample-output",
            str(tmp_path / "sample.jsonl"),
        ],
    )

    assert result.exit_code != 0
    assert "stage-a-manifest" in result.output
    assert not (tmp_path / "sample.jsonl").exists()


def test_build_rejects_input_output_alias_before_reading_audit(tmp_path: Path) -> None:
    module = _load_script("20_build_bilingual_training.py", "bilingual_training_20_alias")
    exclusion = tmp_path / "exclusion.json"
    exclusion.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        module.main,
        [
            "--mode",
            "build",
            "--stage-a",
            str(STAGE_A),
            "--catalog",
            str(CATALOG),
            "--exclusion-index",
            str(exclusion),
            "--audit",
            str(tmp_path / "missing-audit.jsonl"),
            "--output",
            str(STAGE_A),
            "--manifest",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code != 0
    assert "protected input" in result.output
