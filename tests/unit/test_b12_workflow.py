from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.small_llm_baselines_workflow as workflow
from nl2sparql.models.b12 import CatalogSummary, Completion
from nl2sparql.sql.schema import CATALOG_PATH

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
REVISION = "b" * 40


class ScriptedBackend:
    def generate(self, messages, config):
        return Completion(
            raw_text=SAFE_SQL,
            model_id=config.model_id,
            model_revision=config.model_revision,
            input_tokens=10,
            output_tokens=5,
        )


def test_help_does_not_import_heavy_ml_stack() -> None:
    code = """
import sys
from click.testing import CliRunner
from scripts.small_llm_baselines_workflow import cli
result = CliRunner().invoke(cli, ["--help"])
assert result.exit_code == 0, result.output
loaded = (
    int("torch" in sys.modules),
    int("transformers" in sys.modules),
    int("sentence_transformers" in sys.modules),
)
print(*loaded)
"""

    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )

    assert result.stdout.strip().endswith("0 0 0")


def test_invalid_question_precedes_catalog_and_model_loading(tmp_path: Path, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("model loader must not be called")

    monkeypatch.setattr(workflow, "load_real_backend", fail_if_called)
    runner = CliRunner()

    result = runner.invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b1",
            "--question",
            "\x00",
            "--catalog",
            str(tmp_path / "missing.json"),
            "--model-revision",
            REVISION,
            "--real-inference",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert "question" in payload["error"]


def test_predict_requires_explicit_real_inference_opt_in(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("model loader must not be called")

    monkeypatch.setattr(workflow, "load_real_backend", fail_if_called)
    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b1",
            "--question",
            "List known addresses",
            "--model-revision",
            REVISION,
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "blocked"


def test_predict_can_use_injected_backend_after_preflight(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "load_real_backend", lambda config: ScriptedBackend())

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b1",
            "--question",
            "List known addresses",
            "--model-revision",
            REVISION,
            "--real-inference",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ready"
    assert payload["prediction"]["sql"] == SAFE_SQL
    assert payload["prediction"]["completion"]["synthetic_backend"] is True


def test_validate_b1_catalog_does_not_load_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        workflow,
        "load_real_backend",
        lambda config: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )

    result = CliRunner().invoke(workflow.cli, ["validate", "--baseline", "b1"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ready"
    assert len(payload["catalog_sha256"]) == 64


def test_catalog_summary_fixture_remains_self_authenticating() -> None:
    text = "catalog\n"
    summary = CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )

    assert summary.text == text


def test_evaluate_rejects_output_alias_before_model_loading(tmp_path: Path, monkeypatch) -> None:
    test_set = tmp_path / "test.jsonl"
    test_set.write_text("{}\n")
    monkeypatch.setattr(
        workflow,
        "load_real_backend",
        lambda config: (_ for _ in ()).throw(AssertionError("model must stay unloaded")),
    )

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b1",
            "--test-set",
            str(test_set),
            "--predictions",
            str(test_set),
            "--model-revision",
            REVISION,
            "--run-id",
            "run-001",
            "--real-inference",
        ],
    )

    assert result.exit_code == 2
    assert "alias" in json.loads(result.output)["error"]


def test_b2_invalid_training_precedes_encoder_and_model_loading(
    tmp_path: Path, monkeypatch
) -> None:
    training = tmp_path / "invalid.jsonl"
    training.write_text("{}\n")

    def bomb(*args, **kwargs):
        raise AssertionError("must stay lazy")

    monkeypatch.setattr(workflow, "load_sentence_encoder", bomb)
    monkeypatch.setattr(workflow, "load_real_backend", bomb)

    with pytest.raises(workflow.SmallLLMError, match="split=train"):
        workflow._build_baseline(
            "b2",
            config=workflow.GenerationConfig(REVISION),
            catalog_path=CATALOG_PATH,
            training_path=training,
            cache_path=tmp_path / "cache.npz",
            encoder_id=workflow.DEFAULT_ENCODER_ID,
            encoder_revision="c" * 40,
            accepted_training_sha256=None,
        )
