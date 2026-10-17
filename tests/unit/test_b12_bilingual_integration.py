"""Offline CLI25 -> native CLI17 -> typed authority with synthetic external seams.

No genuine encoder/model/hardware or scientific evidence is produced.
"""

import builtins
import importlib
import json
import socket
import subprocess
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

import scripts.small_llm_baselines_workflow as workflow
from nl2sparql.kaggle import runner
from nl2sparql.kaggle.bundle import TRAINING_SHA256, build_bundle, extract_bundle, sha256
from nl2sparql.models.b12 import Completion
from nl2sparql.models.b12.retrieval import _publish_cache, validate_training_snapshot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network, credential or real ML access forbidden")

    original_import = builtins.__import__
    original_module = importlib.import_module
    heavy = {"torch", "transformers", "sentence_transformers", "huggingface_hub"}

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in heavy:
            forbidden()
        return original_import(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        if name.split(".")[0] in heavy:
            forbidden()
        return original_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path.name in {".env", "kaggle.json", "token", "stored_tokens"} or (
            "application_default_credentials" in str(path) or "service-account" in str(path)
        ):
            forbidden()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    import os

    environment_type = type(os.environ)
    original_getitem = environment_type.__getitem__
    secrets = {
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "KAGGLE_KEY",
        "KAGGLE_API_TOKEN",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
    }

    def guarded_getitem(env, key):
        if key in secrets:
            forbidden()
        return original_getitem(env, key)

    monkeypatch.setattr(environment_type, "__getitem__", guarded_getitem)


class SyntheticBackend:
    def generate(self, messages, config):
        return Completion(
            raw_text="",
            model_id=config.model_id,
            model_revision=config.model_revision,
            input_tokens=1,
            output_tokens=0,
        )


class SyntheticQueryVectors:
    def encode(self, sentences, **kwargs):
        return np.ones((len(sentences), 1), dtype=np.float32)


def test_actual_bilingual_runner_and_native_consumer(tmp_path, monkeypatch, offline):
    archive = tmp_path / "input.tar.gz"
    build_bundle(ROOT, archive)
    extracted = tmp_path / "input"
    extract_bundle(archive, extracted, sha256(archive.read_bytes()))
    config = json.loads((ROOT / "configs/kaggle-b12-run.template.json").read_bytes())
    config.update(
        campaign_id="TEST-ONLY-plumbing",
        model_revision="a" * 40,
        encoder_revision="b" * 40,
        hf_home="/nonexistent",
        run_timeout_seconds=60,
    )
    output = tmp_path / "outputs"
    records, digest = validate_training_snapshot(
        (extracted / "data/dataset/processed/b2-training.jsonl").read_bytes(),
        accepted_training_sha256=TRAINING_SHA256,
    )
    assert len(records) == 7208
    # Pre-populate strictly temporary caches; no genuine encoder is loaded.
    for language in ("en", "vi"):
        cache = output / language / "cache/b2-few-shot.npz"
        cache.parent.mkdir(parents=True)
        _publish_cache(
            cache,
            cache.with_suffix(".npz.json"),
            training_sha256=digest,
            encoder_id=config["encoder_id"],
            encoder_revision=config["encoder_revision"],
            records=records,
            matrix=np.ones((7208, 1), dtype=np.float32),
            accepted_training_sha256=digest,
        )
    monkeypatch.setattr(workflow, "load_real_backend", lambda config: SyntheticBackend())
    monkeypatch.setattr(workflow, "load_sentence_encoder", lambda *a: SyntheticQueryVectors())
    # Hardware/runtime are external-only seams; data preflight and planning remain real.
    monkeypatch.setattr(
        runner, "preflight_runtime", lambda *a: {"status": "ready", "test_only": True}
    )
    monkeypatch.setattr(runner, "probe_hardware", lambda: {"test_only": True})

    def native_process(argv, **kwargs):
        result = CliRunner().invoke(workflow.cli, argv[2:])
        kwargs["stdout"].write(result.output)
        assert result.exit_code == 0, result.output
        return subprocess.CompletedProcess(argv, result.exit_code)

    monkeypatch.setattr(runner.subprocess, "run", native_process)
    all_runs = []
    for language in ("en", "vi"):
        config["language"] = language
        for baseline in ("b1", "b2"):
            runs = runner.run_campaign(
                extracted, dict(config), output, real_inference=True, baseline=baseline, replicate=1
            )
            assert len(runs) == 1
            run = runs[0]
            all_runs.append(run)
            folder = Path(run["folder"])
            report = json.loads((folder / "native-report.json").read_bytes())
            rows = [
                json.loads(line) for line in (folder / "predictions.jsonl").read_text().splitlines()
            ]
            assert report["language"] == language and report["metrics"]["total"] == 100
            assert not report["scientific_ready"]
            assert "synthetic_backend" in report["blockers"]
            assert all(row["language"] == language for row in rows)
            assert all(row["prediction"]["completion"]["synthetic_backend"] for row in rows)
            if baseline == "b2":
                assert all(row["prediction"]["training_sha256"] == TRAINING_SHA256 for row in rows)
                assert all(len(row["prediction"]["selected_examples"]) == 5 for row in rows)
                train_ids = {record.record_id for record in records}
                assert all(
                    example["record_id"] in train_ids
                    for row in rows
                    for example in row["prediction"]["selected_examples"]
                )
            if language == "vi":
                assert all(row["paired_source"]["case"]["language"] == "vi" for row in rows)
    assert len({run["folder"] for run in all_runs}) == 4
