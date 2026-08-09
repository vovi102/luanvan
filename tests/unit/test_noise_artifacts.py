"""Artifact, manifest, and CLI tests for deterministic Stage D publication."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from click.testing import CliRunner

import nl2sparql.dataset.noise.artifacts as noise_artifacts
from nl2sparql.dataset.noise.artifacts import (
    build_noise_manifest,
    file_sha256,
    jsonl_bytes,
    noise_artifact_lock,
    publish_noise_artifacts,
    validate_noise_manifest,
)
from nl2sparql.dataset.noise.contracts import NoiseConfig, NoiseValidationError
from nl2sparql.dataset.noise.pipeline import inject_noise, validate_stage_d_records
from nl2sparql.dataset.noise.transforms import (
    ABBREVIATIONS_PATH,
    load_abbreviations,
)
from nl2sparql.dataset.paraphrase.quality import normalize_question


def stage_c_records() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(3000):
        question = f"Show transaction number {index} between 2026-06-01 and 2026-06-02?"
        rows.append(
            {
                "id": f"stage-c-{index:04d}",
                "parent_id": f"stage-b-{index // 3:04d}",
                "nl": question,
                "nl_normalized": normalize_question(question),
                "sql": f"SELECT {index} AS row_id",
                "record_sha256": f"{index:064x}",
                "slot_values": {
                    "n": index,
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-02",
                },
                "entities_used": [],
                "stage_c": {"pairwise_distances": [0.4, 0.5, 0.6]},
            }
        )
    return rows


@pytest.fixture(scope="module")
def complete_records() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    source = stage_c_records()
    output = inject_noise(source, load_abbreviations(), {}, NoiseConfig())
    return source, output


def _manifest(
    tmp_path: Path,
    complete_records: tuple[list[dict[str, object]], list[dict[str, object]]],
) -> tuple[dict[str, object], Path, Path, bytes]:
    source, output = complete_records
    source_path = tmp_path / "stage-c.jsonl"
    output_path = tmp_path / "stage-d.jsonl"
    source_path.write_bytes(jsonl_bytes(source))
    output_payload = jsonl_bytes(output)
    stats = validate_stage_d_records(source, output, {}, NoiseConfig())
    manifest = build_noise_manifest(
        source_path=source_path,
        output_bytes=output_payload,
        abbreviations_path=ABBREVIATIONS_PATH,
        stage_c=source,
        stage_d=output,
        stats=stats,
        config=NoiseConfig(),
        generated_at="2026-08-09T00:00:00Z",
    )
    return manifest, source_path, output_path, output_payload


def test_manifest_records_hashes_counts_quotas_and_deterministic_audit_ids(
    tmp_path: Path,
    complete_records: tuple[list[dict[str, object]], list[dict[str, object]]],
) -> None:
    manifest, source_path, output_path, output_payload = _manifest(tmp_path, complete_records)
    publish_noise_artifacts(
        output_payload, manifest, output_path=output_path, manifest_path=tmp_path / "noise.json"
    )

    assert manifest["source"] == {
        "records": 3000,
        "sha256": file_sha256(source_path),
    }
    assert manifest["output"]["records"] == 3150
    assert manifest["output"]["sha256"] == file_sha256(output_path)
    assert manifest["config"]["quotas"] == {
        "typo": 38,
        "abbrev": 38,
        "fragment": 37,
        "mixed_case": 37,
    }
    assert len(manifest["selection"]["source_ids"]) == 150
    assert len(manifest["manual_audit"]["record_ids"]) == 30
    assert manifest["manual_audit"]["completed"] is False
    assert manifest["manual_audit"]["decipherable_count"] is None


def test_manifest_validation_accepts_passing_manual_audit_and_rejects_weak_one(
    tmp_path: Path,
    complete_records: tuple[list[dict[str, object]], list[dict[str, object]]],
) -> None:
    manifest, source_path, output_path, output_payload = _manifest(tmp_path, complete_records)
    manifest_path = tmp_path / "noise.json"
    publish_noise_artifacts(
        output_payload, manifest, output_path=output_path, manifest_path=manifest_path
    )
    source, output = complete_records
    passing = deepcopy(manifest)
    ids = passing["manual_audit"]["record_ids"]
    passing["manual_audit"].update(
        completed=True,
        decipherable_count=27,
        decisions=[
            {"id": record_id, "decipherable": index < 27, "notes": ""}
            for index, record_id in enumerate(ids)
        ],
    )

    validate_noise_manifest(
        passing,
        source_path=source_path,
        output_path=output_path,
        abbreviations_path=ABBREVIATIONS_PATH,
        stage_c=source,
        stage_d=output,
        stats=validate_stage_d_records(source, output, {}, NoiseConfig()),
        config=NoiseConfig(),
    )
    failing = deepcopy(passing)
    failing["manual_audit"]["decipherable_count"] = 26
    failing["manual_audit"]["decisions"][26]["decipherable"] = False
    with pytest.raises(NoiseValidationError, match="27"):
        validate_noise_manifest(
            failing,
            source_path=source_path,
            output_path=output_path,
            abbreviations_path=ABBREVIATIONS_PATH,
            stage_c=source,
            stage_d=output,
            stats=validate_stage_d_records(source, output, {}, NoiseConfig()),
            config=NoiseConfig(),
        )


def test_pair_publication_restores_both_existing_files_when_second_replace_fails(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "stage-d.jsonl"
    manifest_path = tmp_path / "noise.json"
    output_path.write_bytes(b"old-output\n")
    manifest_path.write_bytes(b"old-manifest\n")
    calls = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated manifest replace failure")
        source.replace(target)

    with pytest.raises(OSError, match="manifest replace"):
        publish_noise_artifacts(
            b"new-output\n",
            {"status": "new"},
            output_path=output_path,
            manifest_path=manifest_path,
            replace=fail_second_replace,
        )

    assert output_path.read_bytes() == b"old-output\n"
    assert manifest_path.read_bytes() == b"old-manifest\n"
    assert not list(tmp_path.glob(".*.tmp"))


def test_publication_lock_rejects_a_concurrent_nonblocking_writer(tmp_path: Path) -> None:
    output_path = tmp_path / "stage-d.jsonl"
    manifest_path = tmp_path / "noise.json"

    with noise_artifact_lock(output_path, manifest_path):
        with pytest.raises(BlockingIOError):
            with noise_artifact_lock(output_path, manifest_path, blocking=False):
                raise AssertionError("concurrent writer unexpectedly acquired lock")


def test_interrupted_pair_publication_is_recovered_before_next_read(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "stage-d.jsonl"
    manifest_path = tmp_path / "noise.json"
    output_path.write_bytes(b"old-output\n")
    manifest_path.write_bytes(b"old-manifest\n")
    calls = 0

    def interrupt_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        source.replace(target)

    with pytest.raises(KeyboardInterrupt):
        publish_noise_artifacts(
            b"new-output\n",
            {"status": "new"},
            output_path=output_path,
            manifest_path=manifest_path,
            replace=interrupt_second_replace,
        )

    with noise_artifact_lock(output_path, manifest_path):
        assert output_path.read_bytes() == b"old-output\n"
        assert manifest_path.read_bytes() == b"old-manifest\n"


def test_publication_uses_unique_staging_names(tmp_path: Path) -> None:
    output_path = tmp_path / "stage-d.jsonl"
    manifest_path = tmp_path / "noise.json"
    staging_names: list[str] = []

    def record_staging_name(source: Path, target: Path) -> None:
        staging_names.append(source.name)
        source.replace(target)

    for index in range(2):
        publish_noise_artifacts(
            f"output-{index}\n".encode(),
            {"generation": index},
            output_path=output_path,
            manifest_path=manifest_path,
            replace=record_staging_name,
        )

    assert len(staging_names) == 4
    assert len(set(staging_names)) == 4


def test_publication_rejects_relative_absolute_aliases_of_same_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("artifact.jsonl")

    with pytest.raises(NoiseValidationError, match="must differ"):
        publish_noise_artifacts(
            b"output\n",
            {"status": "new"},
            output_path=target,
            manifest_path=target.resolve(),
        )

    assert not target.exists()


def test_recovery_durably_writes_restore_temporaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "stage-d.jsonl"
    manifest_path = tmp_path / "noise.json"
    output_path.write_bytes(b"old-output\n")
    manifest_path.write_bytes(b"old-manifest\n")
    calls = 0

    def interrupt_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        source.replace(target)

    with pytest.raises(KeyboardInterrupt):
        publish_noise_artifacts(
            b"new-output\n",
            {"status": "new"},
            output_path=output_path,
            manifest_path=manifest_path,
            replace=interrupt_second_replace,
        )

    durable_writes: list[Path] = []
    original_write = noise_artifacts._write_bytes_durable

    def record_durable_write(path: Path, payload: bytes) -> None:
        durable_writes.append(path)
        original_write(path, payload)

    monkeypatch.setattr(noise_artifacts, "_write_bytes_durable", record_durable_write)
    with noise_artifact_lock(output_path, manifest_path):
        pass

    assert len([path for path in durable_writes if ".restore." in path.name]) == 2
    assert output_path.read_bytes() == b"old-output\n"
    assert manifest_path.read_bytes() == b"old-manifest\n"


def test_notebook_reads_and_hash_checks_artifact_pair_under_shared_lock() -> None:
    notebook = json.loads(Path("notebooks/10_noise_injection.ipynb").read_text())
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )

    assert "noise_artifact_lock" in source
    assert "with noise_artifact_lock(STAGE_D, MANIFEST):" in source
    assert source.index("with noise_artifact_lock(STAGE_D, MANIFEST):") < source.index(
        "if not MANIFEST.exists() or not STAGE_D.exists():"
    )
    assert "hashlib.sha256(stage_d_bytes).hexdigest()" in source
    assert 'manifest["output"]["sha256"]' in source


def load_script():
    path = Path("scripts/11_inject_noise.py").resolve()
    spec = importlib.util.spec_from_file_location("inject_noise_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_missing_source_fails_without_creating_outputs(tmp_path: Path) -> None:
    script = load_script()
    output = tmp_path / "stage-d.jsonl"
    manifest = tmp_path / "noise.json"

    result = CliRunner().invoke(
        script.main,
        [
            "--source",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
    )

    assert result.exit_code != 0
    assert "missing.jsonl" in result.output
    assert not output.exists()
    assert not manifest.exists()


def test_cli_generates_then_revalidates_complete_artifacts(
    tmp_path: Path,
    complete_records: tuple[list[dict[str, object]], list[dict[str, object]]],
) -> None:
    script = load_script()
    source, _ = complete_records
    source_path = tmp_path / "stage-c.jsonl"
    output_path = tmp_path / "stage-d.jsonl"
    manifest_path = tmp_path / "noise.json"
    source_path.write_bytes(jsonl_bytes(source))
    base_args = [
        "--source",
        str(source_path),
        "--output",
        str(output_path),
        "--manifest",
        str(manifest_path),
    ]

    generated = CliRunner().invoke(script.main, base_args)
    validated = CliRunner().invoke(script.main, ["--mode", "validate-output", *base_args])

    assert generated.exit_code == 0, generated.output
    assert json.loads(generated.output)["output_records"] == 3150
    assert output_path.exists()
    assert manifest_path.exists()
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["status"] == "valid"
