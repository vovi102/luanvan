"""Offline-first CLI contract tests for the B4/B5 workflow."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.large_llm_baselines_workflow as workflow
from nl2sparql.models.b12 import CatalogSummary, EvaluationCase
from nl2sparql.models.b45 import BudgetLedger, LargeLLMConfig, ProviderPolicy, RemoteCompletion
from nl2sparql.models.b45.openrouter import ModelMetadataEvidence

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
METADATA_SHA = "c" * 64


def _policy() -> ProviderPolicy:
    return ProviderPolicy(
        provider_slug="deepinfra",
        prompt_price_per_million_usd=Decimal("0.50"),
        completion_price_per_million_usd=Decimal("1.00"),
    )


def _summary() -> CatalogSummary:
    text = "GoogleSQL catalog\n"
    return CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _case() -> EvaluationCase:
    return EvaluationCase(
        case_id="case-1",
        question="List labels",
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("lookup",),
        input_sha256="b" * 64,
        reviewed=True,
        live_verified=True,
        synthetic=False,
    )


class _SyntheticTransport:
    def __init__(self, config: LargeLLMConfig) -> None:
        self._ledger = BudgetLedger(config)

    @property
    def budget_ledger(self) -> BudgetLedger:
        return self._ledger

    async def complete(self, messages, config, *, request_id):
        return RemoteCompletion.synthetic(
            raw_text=SAFE_SQL,
            model_id=config.model_id,
            provider_slug="scripted",
            input_tokens=10,
            output_tokens=5,
            charged_cost_usd=Decimal("0"),
            latency_ms=1.0,
        )


def test_help_does_not_import_openai() -> None:
    """Removing lazy imports should make this subprocess assertion fail."""
    code = """
import sys
from click.testing import CliRunner
from scripts.large_llm_baselines_workflow import cli
result = CliRunner().invoke(cli, ["--help"])
assert result.exit_code == 0, result.output
print(int("openai" in sys.modules))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip().endswith("0")


def test_validate_uses_only_local_catalog_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loading a client from validate would make this test fail."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )

    result = CliRunner().invoke(
        workflow.cli,
        ["validate", "--baseline", "b4", "--provider", "deepinfra", "--max-cost-usd", "20"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ready"
    assert payload["baseline"] == "b4"


def test_validate_does_not_import_openai() -> None:
    """Eager SDK imports in local validation would make this subprocess fail."""
    code = """
import sys
from click.testing import CliRunner
from scripts.large_llm_baselines_workflow import cli
result = CliRunner().invoke(
    cli,
    ["validate", "--baseline", "b4", "--provider", "deepinfra", "--max-cost-usd", "20"],
)
assert result.exit_code == 0, result.output
print(int("openai" in sys.modules))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip().endswith("0")


def test_predict_requires_network_opt_in_before_key_or_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving key/client access before the opt-in gate would fail this test."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )

    result = CliRunner().invoke(
        workflow.cli,
        ["predict", "--baseline", "b4", "--question", "List labels", "--provider", "deepinfra"],
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "network access requires --allow-network"


def test_evaluate_rejects_output_alias_before_network_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allowing an output to overwrite a snapshot would fail this test."""
    test_set = tmp_path / "test.jsonl"
    test_set.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(test_set),
            "--predictions",
            str(test_set),
            "--run-id",
            "run-1",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--accepted-model-metadata-sha256",
            "a" * 64,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "alias" in json.loads(result.output)["error"]


def test_b5_training_cache_preflight_precedes_encoder_and_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loading an encoder/client before invalid B5 evidence would fail this test."""
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "load_sentence_encoder",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("encoder must stay lazy")),
    )
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("client must stay lazy")),
    )

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b5",
            "--question",
            "List labels",
            "--training",
            str(tmp_path / "missing.jsonl"),
            "--cache",
            str(tmp_path / "missing.npz"),
            "--encoder-revision",
            "c" * 40,
            "--accepted-training-sha256",
            "a" * 64,
            "--provider",
            "deepinfra",
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "training" in json.loads(result.output)["error"]


def test_missing_key_follows_local_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checking the key before catalog validation would fail this test."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b4",
            "--question",
            "List labels",
            "--catalog",
            "missing-catalog.json",
            "--provider",
            "deepinfra",
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "catalog" in json.loads(result.output)["error"]


def test_cap_above_twenty_is_rejected_before_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Weakening the USD 20 hard cap would make this test fail."""
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("client must stay lazy")),
    )
    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b4",
            "--question",
            "List labels",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20.01",
        ],
    )

    assert result.exit_code == 2
    assert "at most USD 20" in json.loads(result.output)["error"]


def test_metadata_drift_blocks_client_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructing a client before checking accepted metadata would fail this test."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow, "load_model_metadata", lambda *_args, **_kwargs: {"id": "drift"})
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("client must stay lazy")),
    )

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b4",
            "--question",
            "List labels",
            "--provider",
            "deepinfra",
            "--allow-network",
            "--accepted-model-metadata-sha256",
            "a" * 64,
        ],
    )

    assert result.exit_code == 2
    assert "metadata" in json.loads(result.output)["error"]


def test_injected_synthetic_transport_can_run_but_is_not_scientifically_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Treating injected synthetic output as scientific evidence would fail this test."""
    test_set = tmp_path / "test.jsonl"
    test_set.write_text("{}\n", encoding="utf-8")
    config = LargeLLMConfig(provider=_policy())
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow, "load_model_metadata", lambda *_args, **_kwargs: {"stub": True})
    monkeypatch.setattr(
        workflow,
        "validate_model_metadata",
        lambda *_args, **_kwargs: ModelMetadataEvidence(
            model_id=config.model_id,
            provider_slug="deepinfra",
            context_length=10_000,
            supported_parameters=("max_tokens", "seed", "temperature"),
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
            metadata_sha256=METADATA_SHA,
        ),
    )
    monkeypatch.setattr(
        workflow, "load_openrouter_transport", lambda *_args, **_kwargs: _SyntheticTransport(config)
    )

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(test_set),
            "--run-id",
            "run-1",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--allow-network",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--predictions",
            str(tmp_path / "predictions.jsonl"),
            "--request-log",
            str(tmp_path / "requests.jsonl"),
            "--cost-log",
            str(tmp_path / "cost.csv"),
            "--report",
            str(tmp_path / "report.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["scientific_ready"] is False


def test_summarize_accepts_three_local_reports_without_a_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any client construction in summarize would make this test fail."""
    reports = []
    request_logs = []
    for index in range(3):
        report = tmp_path / f"run-{index}.json"
        report.write_text(json.dumps({"run_id": f"run-{index}"}), encoding="utf-8")
        reports.append(report)
        request_log = tmp_path / f"run-{index}.jsonl"
        request_log.write_text("{}\n", encoding="utf-8")
        request_logs.append(request_log)
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay local")),
    )
    monkeypatch.setattr(
        workflow,
        "load_large_run_report",
        lambda _report, _log: type("Run", (), {"outcomes": ()})(),
    )
    monkeypatch.setattr(workflow, "summarize_large_runs", lambda runs: {"run_count": len(runs)})

    result = CliRunner().invoke(
        workflow.cli,
        [
            "summarize",
            "--report",
            str(reports[0]),
            "--report",
            str(reports[1]),
            "--report",
            str(reports[2]),
            "--request-log",
            str(request_logs[0]),
            "--request-log",
            str(request_logs[1]),
            "--request-log",
            str(request_logs[2]),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"run_count": 3, "status": "ready"}


@pytest.mark.parametrize(
    "arguments",
    [
        ["predict", "--baseline", "not-a-baseline"],
        ["validate", "--baseline", "b4"],
    ],
)
def test_click_parse_errors_are_one_compact_json_object(arguments: list[str]) -> None:
    """Restoring Click's usage output would make this JSON-only contract fail."""
    result = CliRunner().invoke(workflow.cli, arguments)

    assert result.exit_code == 2
    assert result.output.count("\n") == 0
    assert json.loads(result.output)["status"] == "failed"


def test_invalid_run_id_precedes_filesystem_key_metadata_and_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving primitive validation behind preflight dependencies would fail this test."""

    def bomb(*_args, **_kwargs):
        raise AssertionError("primitive validation must stop first")

    monkeypatch.setattr(workflow, "load_evaluation_cases", bomb)
    monkeypatch.setattr(workflow, "compile_catalog_summary", bomb)
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--run-id",
            "bad id",
            "--provider",
            "deepinfra",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "run ID" in json.loads(result.output)["error"]


def test_invalid_metadata_sha_precedes_catalog_key_and_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deferring accepted metadata SHA validation would fail this ordering check."""

    def bomb(*_args, **_kwargs):
        raise AssertionError("primitive validation must stop first")

    monkeypatch.setattr(workflow, "compile_catalog_summary", bomb)
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b4",
            "--question",
            "List labels",
            "--provider",
            "deepinfra",
            "--accepted-model-metadata-sha256",
            "invalid",
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "metadata fingerprint" in json.loads(result.output)["error"]


def test_b5_cache_hit_never_loads_encoder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Loading an encoder for a valid cache would fail this cache-hit regression."""
    cached = object()
    monkeypatch.setattr(
        workflow.FewShotRetriever,
        "from_snapshot",
        lambda *_args, **_kwargs: cached,
    )
    monkeypatch.setattr(
        workflow,
        "load_sentence_encoder",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache hit")),
    )

    preflight = workflow._b5_cache_preflight(
        tmp_path / "train.jsonl", tmp_path / "cache.npz", "encoder", "a" * 40, "b" * 64
    )
    result = workflow._b5_retriever(
        tmp_path / "train.jsonl",
        tmp_path / "cache.npz",
        "encoder",
        "a" * 40,
        "b" * 64,
        preflight,
    )

    assert result is cached


def test_b5_stale_cache_rebuilds_only_after_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Skipping the post-preflight rebuild would fail this stale-cache regression."""
    rebuilt = object()
    calls = []

    def from_snapshot(*_args, **kwargs):
        calls.append(kwargs["encoder"])
        if kwargs["encoder"] is None:
            raise workflow.SmallLLMError("few-shot cache is invalid and encoder unavailable")
        return rebuilt

    monkeypatch.setattr(workflow.FewShotRetriever, "from_snapshot", from_snapshot)
    monkeypatch.setattr(workflow, "load_sentence_encoder", lambda *_args: "encoder")

    preflight = workflow._b5_cache_preflight(
        tmp_path / "train.jsonl", tmp_path / "cache.npz", "encoder", "a" * 40, "b" * 64
    )
    result = workflow._b5_retriever(
        tmp_path / "train.jsonl",
        tmp_path / "cache.npz",
        "encoder",
        "a" * 40,
        "b" * 64,
        preflight,
    )

    assert preflight is None
    assert result is rebuilt
    assert calls == [None, "encoder"]


@pytest.mark.parametrize("sidecar", [".json", ".lock"])
def test_evaluate_protects_b5_cache_sidecars(sidecar: str, tmp_path: Path) -> None:
    """Dropping cache sidecars from protected paths would allow this alias."""
    cache = tmp_path / "b5-cache.npz"
    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--run-id",
            "run-1",
            "--provider",
            "deepinfra",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--cache",
            str(cache),
            "--predictions",
            str(cache.with_suffix(cache.suffix + sidecar)),
        ],
    )

    assert result.exit_code == 2
    assert "alias" in json.loads(result.output)["error"]


def test_summarize_round_trips_three_typed_local_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing typed artifact loading with report dictionaries would fail this test."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow, "load_model_metadata", lambda *_args: {"stub": True})
    monkeypatch.setattr(
        workflow,
        "validate_model_metadata",
        lambda _raw, config, **_kwargs: ModelMetadataEvidence(
            model_id=config.model_id,
            provider_slug="deepinfra",
            context_length=10_000,
            supported_parameters=("max_tokens", "seed", "temperature"),
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
            metadata_sha256=METADATA_SHA,
        ),
    )
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda config, _ledger: _SyntheticTransport(config),
    )
    reports: list[Path] = []
    request_logs: list[Path] = []
    for index in range(3):
        report = tmp_path / f"report-{index}.json"
        request_log = tmp_path / f"request-{index}.jsonl"
        result = CliRunner().invoke(
            workflow.cli,
            [
                "evaluate",
                "--baseline",
                "b4",
                "--test-set",
                str(tmp_path / "test.jsonl"),
                "--run-id",
                f"run-{index}",
                "--provider",
                "deepinfra",
                "--allow-network",
                "--accepted-model-metadata-sha256",
                METADATA_SHA,
                "--predictions",
                str(tmp_path / f"prediction-{index}.jsonl"),
                "--request-log",
                str(request_log),
                "--cost-log",
                str(tmp_path / f"cost-{index}.csv"),
                "--report",
                str(report),
            ],
        )
        assert result.exit_code == 0, result.output
        reports.append(report)
        request_logs.append(request_log)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "summarize",
            *(item for report in reports for item in ("--report", str(report))),
            *(item for request_log in request_logs for item in ("--request-log", str(request_log))),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["run_ids"] == ["run-0", "run-1", "run-2"]
