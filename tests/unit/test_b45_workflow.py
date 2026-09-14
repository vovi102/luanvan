"""Offline-first CLI contract tests for the B4/B5 workflow."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import scripts.large_llm_baselines_workflow as workflow
from nl2sparql.models.b12 import CatalogSummary, EvaluationCase, SelectedExample
from nl2sparql.models.b12.prompts import build_messages
from nl2sparql.models.b45 import (
    AttemptEvidencePersistenceError,
    BudgetLedger,
    LargeLLMConfig,
    PrivacyReviewEvidence,
    ProviderPolicy,
    RemoteCompletion,
    RequestJournal,
    preview_b4_prompt,
    serialize_privacy_review,
)
from nl2sparql.models.b45.openrouter import (
    ModelMetadataEvidence,
    OpenRouterRequestError,
    OpenRouterTransport,
    validate_model_metadata,
)

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
METADATA_SHA = "c" * 64
V2_JOURNAL_FIXTURE = Path("tests/fixtures/b45/request-journal-v2-in-progress.jsonl")


@pytest.fixture(autouse=True)
def _validated_local_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep workflow tests focused while the real manifest loader is tested separately."""
    monkeypatch.setattr(
        workflow,
        "load_local_verification_evidence",
        lambda: SimpleNamespace(ready=True, blockers=()),
    )


def test_task_document_matches_google_sql_acceptance_boundary() -> None:
    text = Path("docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md").read_text()
    assert "GoogleSQL" in text
    assert "meta-llama/llama-3.3-70b-instruct" in text
    assert "local implementation complete" in text
    assert "scientific acceptance pending" in text
    assert "SPARQL extraction" not in text


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
    def __init__(self, config: LargeLLMConfig, ledger: BudgetLedger | None = None) -> None:
        self._ledger = ledger if ledger is not None else BudgetLedger(config)

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


class _QueryRetriever:
    training_sha256 = "d" * 64
    encoder_id = "encoder"
    encoder_revision = "a" * 40
    training_accepted = True

    def retrieve(
        self, _question: str, *, target_id: str | None = None
    ) -> tuple[SelectedExample, ...]:
        return tuple(
            SelectedExample(
                record_id=f"train-{index}",
                question=f"Question {index}",
                sql=SAFE_SQL,
                score=0.5,
            )
            for index in range(1, 6)
        )


class _LargeQueryRetriever(_QueryRetriever):
    """Return valid examples large enough to expose fixed-size prompt guesses."""

    def retrieve(
        self, _question: str, *, target_id: str | None = None
    ) -> tuple[SelectedExample, ...]:
        return tuple(
            SelectedExample(
                record_id=f"train-{index}",
                question=f"Example {index} " + "x" * 1_900,
                sql=SAFE_SQL,
                score=0.5,
            )
            for index in range(1, 6)
        )


class _StatefulQueryRetriever(_QueryRetriever):
    """Return a larger prompt after a configured number of retrievals."""

    def __init__(self, *, stable_calls: int) -> None:
        self.calls = 0
        self.stable_calls = stable_calls

    def retrieve(
        self, question: str, *, target_id: str | None = None
    ) -> tuple[SelectedExample, ...]:
        self.calls += 1
        if self.calls <= self.stable_calls:
            return super().retrieve(question, target_id=target_id)
        return _LargeQueryRetriever().retrieve(question, target_id=target_id)


class _RecordingSyntheticTransport(_SyntheticTransport):
    def __init__(self, config: LargeLLMConfig, ledger: BudgetLedger | None = None) -> None:
        super().__init__(config, ledger)
        self.messages: list[tuple[object, ...]] = []

    async def complete(self, messages, config, *, request_id):
        self.messages.append(messages)
        return await super().complete(messages, config, request_id=request_id)


def _metadata_response(*, context_length: int) -> dict[str, object]:
    return {
        "data": {
            "id": "meta-llama/llama-3.3-70b-instruct",
            "endpoints": [
                {
                    "provider_name": "DeepInfra",
                    "context_length": context_length,
                    "supported_parameters": ["temperature", "seed", "max_tokens"],
                    "pricing": {"prompt": "0.0000004", "completion": "0.0000008"},
                }
            ],
        }
    }


def _live_evaluate_arguments(
    tmp_path: Path,
    *,
    baseline: str = "b4",
    accepted_metadata: str = METADATA_SHA,
) -> list[str]:
    arguments = [
        "evaluate",
        "--baseline",
        baseline,
        "--test-set",
        str(tmp_path / "test.jsonl"),
        "--run-id",
        "run-1",
        "--provider",
        "deepinfra",
        "--max-cost-usd",
        "20",
        "--allow-network",
        "--accepted-model-metadata-sha256",
        accepted_metadata,
        "--accepted-privacy-review-sha256",
        "d" * 64,
        "--predictions",
        str(tmp_path / "predictions.jsonl"),
        "--request-log",
        str(tmp_path / "requests.jsonl"),
        "--cost-log",
        str(tmp_path / "cost.csv"),
        "--report",
        str(tmp_path / "report.json"),
    ]
    if baseline == "b5":
        arguments.extend(
            [
                "--training",
                str(tmp_path / "train.jsonl"),
                "--cache",
                str(tmp_path / "cache.npz"),
                "--encoder-revision",
                "a" * 40,
                "--accepted-training-sha256",
                "d" * 64,
            ]
        )
    return arguments


def _live_b5_predict_arguments(
    tmp_path: Path, *, question: str, accepted_metadata: str
) -> list[str]:
    return [
        "predict",
        "--baseline",
        "b5",
        "--question",
        question,
        "--provider",
        "deepinfra",
        "--max-cost-usd",
        "20",
        "--training",
        str(tmp_path / "train.jsonl"),
        "--cache",
        str(tmp_path / "cache.npz"),
        "--encoder-revision",
        "a" * 40,
        "--accepted-training-sha256",
        "d" * 64,
        "--allow-network",
        "--accepted-model-metadata-sha256",
        accepted_metadata,
    ]


def _legacy_v2_workflow_payload() -> bytes:
    """Adapt the authentic v2 fixture only to this workflow test's identities."""
    rows = [json.loads(line) for line in V2_JOURNAL_FIXTURE.read_text().splitlines()]
    summary = _summary()
    config = LargeLLMConfig(provider=_policy())
    rows[0]["config_sha256"] = config.sha256
    rows[0]["summary_sha256"] = summary.summary_sha256
    rows[0]["model_metadata_sha256"] = METADATA_SHA
    rows[1]["config_sha256"] = config.sha256
    rows[1]["summary_sha256"] = summary.summary_sha256
    rows[1]["model_metadata_sha256"] = METADATA_SHA
    prediction = rows[1]["prediction"]
    assert isinstance(prediction, dict)
    prompt_hash = preview_b4_prompt("List addresses", summary).prompt_sha256
    rows[1]["prompt_sha256"] = prompt_hash
    prediction["prompt_sha256"] = prompt_hash
    prediction["config_sha256"] = config.sha256
    prediction["summary_sha256"] = summary.summary_sha256
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        for row in rows
    )


def _legacy_v2_case() -> EvaluationCase:
    case = EvaluationCase(
        case_id="case-1",
        question="List addresses",
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("entity_lookup",),
        input_sha256="f" * 64,
        reviewed=True,
        live_verified=True,
        synthetic=False,
    )
    object.__setattr__(case, "_trusted_source", True)
    return case


def _stub_live_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    config = LargeLLMConfig(provider=_policy())
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_legacy_v2_case(),))
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
        workflow,
        "load_openrouter_transport",
        lambda _config, ledger: _SyntheticTransport(config, ledger),
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


def test_validate_reports_missing_local_verification_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hard-coding local readiness to true would make this test fail."""
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "load_local_verification_evidence",
        lambda: SimpleNamespace(
            ready=False,
            blockers=("local_verification_manifest_missing",),
        ),
        raising=False,
    )

    result = CliRunner().invoke(
        workflow.cli,
        ["validate", "--baseline", "b4", "--provider", "deepinfra", "--max-cost-usd", "20"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["local_implementation_ready"] is False
    assert "local_verification_manifest_missing" in payload["blockers"]


def test_evaluate_rejects_invalid_local_verification_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reaching any live seam with stale local evidence would fail this test."""
    events: list[str] = []
    monkeypatch.setattr(
        workflow,
        "load_local_verification_evidence",
        lambda: SimpleNamespace(
            ready=False,
            blockers=("local_verification_source_stale",),
        ),
    )
    monkeypatch.setattr(
        workflow,
        "load_evaluation_cases",
        lambda _path: events.append("snapshot") or (_case(),),
    )
    monkeypatch.setattr(
        workflow,
        "load_model_metadata",
        lambda *_args, **_kwargs: events.append("metadata") or {"unexpected": True},
    )
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: events.append("transport") or None,
    )

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
            "--max-cost-usd",
            "20",
            "--allow-network",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--accepted-privacy-review-sha256",
            "d" * 64,
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == (
        "local implementation verification is blocked: local_verification_source_stale"
    )
    assert events == []


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


def test_validate_rejects_malformed_snapshot_before_live_seams(tmp_path: Path) -> None:
    snapshot = tmp_path / "test.jsonl"
    snapshot.write_text("{malformed}\n", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
        monkeypatch.setattr(
            workflow,
            "load_openrouter_transport",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("validate must stay offline")
            ),
        )
        result = CliRunner().invoke(
            workflow.cli,
            [
                "validate",
                "--baseline",
                "b4",
                "--test-set",
                str(snapshot),
                "--provider",
                "deepinfra",
                "--max-cost-usd",
                "20",
            ],
        )
    finally:
        monkeypatch.undo()
    assert result.exit_code == 2
    assert "evaluation snapshot" in json.loads(result.output)["error"]


def test_validate_rejects_publication_alias_before_live_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = tmp_path / "test.jsonl"
    snapshot.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("validate must stay offline")
        ),
    )
    result = CliRunner().invoke(
        workflow.cli,
        [
            "validate",
            "--baseline",
            "b4",
            "--test-set",
            str(snapshot),
            "--predictions",
            str(snapshot),
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
        ],
    )
    assert result.exit_code == 2
    assert "alias" in json.loads(result.output)["error"]


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
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
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
            "--allow-network",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
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
            "--max-cost-usd",
            "20",
            "--allow-network",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
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
            "--max-cost-usd",
            "20",
            "--allow-network",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
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
            "--max-cost-usd",
            "20",
            "--allow-network",
            "--accepted-model-metadata-sha256",
            "a" * 64,
        ],
    )

    assert result.exit_code == 2
    assert "metadata" in json.loads(result.output)["error"]


def test_evaluate_metadata_context_uses_largest_exact_b5_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing exact previews with a fixed prompt allowance would reach transport."""
    summary = _summary()
    config = LargeLLMConfig(provider=_policy())
    old_prompt_guess = len(summary.text.encode("utf-8")) + 2_000
    raw_metadata = _metadata_response(context_length=old_prompt_guess + config.max_tokens)
    accepted_metadata = validate_model_metadata(
        raw_metadata, config, prompt_bytes=old_prompt_guess
    ).metadata_sha256
    retriever = _LargeQueryRetriever()
    request_log = tmp_path / "requests.jsonl"
    events: list[str] = []

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: summary)
    monkeypatch.setattr(workflow, "_b5_cache_preflight", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "_b5_retriever", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "load_model_metadata", lambda _config: raw_metadata)
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
    )
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (
            events.append("transport")
            or (_ for _ in ()).throw(AssertionError("undersized context must block transport"))
        ),
    )

    result = CliRunner().invoke(
        workflow.cli,
        _live_evaluate_arguments(tmp_path, baseline="b5", accepted_metadata=accepted_metadata),
    )

    assert result.exit_code == 2
    assert "metadata" in json.loads(result.output)["error"]
    assert events == []
    assert not request_log.exists()


def test_predict_metadata_context_uses_exact_b5_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counting only summary and question bytes would omit five sent examples."""
    summary = _summary()
    question = "List labels"
    config = LargeLLMConfig(provider=_policy())
    old_prompt_guess = len(summary.text.encode("utf-8")) + len(question.encode("utf-8"))
    raw_metadata = _metadata_response(context_length=old_prompt_guess + config.max_tokens)
    accepted_metadata = validate_model_metadata(
        raw_metadata, config, prompt_bytes=old_prompt_guess
    ).metadata_sha256
    retriever = _LargeQueryRetriever()
    events: list[str] = []

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: summary)
    monkeypatch.setattr(workflow, "_b5_cache_preflight", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "_b5_retriever", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "load_model_metadata", lambda _config: raw_metadata)
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (
            events.append("transport")
            or (_ for _ in ()).throw(AssertionError("undersized context must block transport"))
        ),
    )

    result = CliRunner().invoke(
        workflow.cli,
        _live_b5_predict_arguments(
            tmp_path, question=question, accepted_metadata=accepted_metadata
        ),
    )

    assert result.exit_code == 2
    assert "metadata" in json.loads(result.output)["error"]
    assert events == []


def test_predict_sends_the_single_metadata_preflight_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retrieving again after metadata could send a larger unvalidated prompt."""
    summary = _summary()
    question = "List labels"
    config = LargeLLMConfig(provider=_policy())
    expected_messages = build_messages(
        question, summary, examples=_QueryRetriever().retrieve(question)
    )
    prompt_bytes = sum(len(message.content.encode("utf-8")) for message in expected_messages)
    raw_metadata = _metadata_response(context_length=prompt_bytes + config.max_tokens)
    accepted_metadata = validate_model_metadata(
        raw_metadata, config, prompt_bytes=prompt_bytes
    ).metadata_sha256
    retriever = _StatefulQueryRetriever(stable_calls=1)
    transport = _RecordingSyntheticTransport(config)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: summary)
    monkeypatch.setattr(workflow, "_b5_cache_preflight", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "_b5_retriever", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "load_model_metadata", lambda _config: raw_metadata)
    monkeypatch.setattr(workflow, "load_openrouter_transport", lambda *_args: transport)

    result = CliRunner().invoke(
        workflow.cli,
        _live_b5_predict_arguments(
            tmp_path, question=question, accepted_metadata=accepted_metadata
        ),
    )

    assert result.exit_code == 0, result.output
    assert retriever.calls == 1
    assert transport.messages == [expected_messages]


def test_evaluate_sends_each_preflight_preview_without_retrieval_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A third retrieval after matching resume hashes could bypass context preflight."""
    summary = _summary()
    case = _case()
    config = LargeLLMConfig(provider=_policy())
    expected_messages = build_messages(
        case.question, summary, examples=_QueryRetriever().retrieve(case.question)
    )
    prompt_bytes = sum(len(message.content.encode("utf-8")) for message in expected_messages)
    raw_metadata = _metadata_response(context_length=prompt_bytes + config.max_tokens)
    accepted_metadata = validate_model_metadata(
        raw_metadata, config, prompt_bytes=prompt_bytes
    ).metadata_sha256
    retriever = _StatefulQueryRetriever(stable_calls=2)
    transport = _RecordingSyntheticTransport(config)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (case,))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: summary)
    monkeypatch.setattr(workflow, "_b5_cache_preflight", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "_b5_retriever", lambda *_args: retriever)
    monkeypatch.setattr(workflow, "load_model_metadata", lambda _config: raw_metadata)
    monkeypatch.setattr(workflow, "load_openrouter_transport", lambda *_args, **_kwargs: transport)
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
    )

    result = CliRunner().invoke(
        workflow.cli,
        _live_evaluate_arguments(tmp_path, baseline="b5", accepted_metadata=accepted_metadata),
    )

    assert result.exit_code == 0, result.output
    assert retriever.calls == 1
    assert transport.messages == [expected_messages]


def test_metadata_loader_rejects_json_price_above_decimal_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parsing provider JSON prices through binary float would round this down."""
    payload = b"""{
        "data": {
            "id": "meta-llama/llama-3.3-70b-instruct",
            "endpoints": [{
                "provider_name": "DeepInfra",
                "context_length": 131072,
                "supported_parameters": ["temperature", "seed", "max_tokens"],
                "pricing": {
                    "prompt": 0.0000005000000000000000000000000000000000000000000000000001,
                    "completion": 0.000001
                }
            }]
        }
    }"""

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return payload

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    config = LargeLLMConfig(provider=_policy())
    raw = workflow.load_model_metadata(config)
    prompt_price = raw["data"]["endpoints"][0]["pricing"]["prompt"]  # type: ignore[index]
    assert isinstance(prompt_price, Decimal)
    assert prompt_price > Decimal("0.0000005")

    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(raw, config, prompt_bytes=1)

    assert captured.value.code == "model_metadata_invalid"


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
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
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


def test_evaluate_resume_authorizes_v2_migration_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting explicit resume authority would strand a validated v2 journal."""
    _stub_live_evaluation(monkeypatch)
    request_log = tmp_path / "requests.jsonl"
    request_log.write_bytes(_legacy_v2_workflow_payload())

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(tmp_path / "test.jsonl"),
            "--run-id",
            "run-v2",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--allow-network",
            "--resume",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--predictions",
            str(tmp_path / "predictions.jsonl"),
            "--request-log",
            str(request_log),
            "--cost-log",
            str(tmp_path / "cost.csv"),
            "--report",
            str(tmp_path / "report.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in request_log.read_text().splitlines()]
    assert rows[0]["schema_version"] == 4
    assert rows[-1]["attempt_set_count"] == 0
    assert [row["record_type"] for row in rows] == ["header", "outcome", "terminal"]
    assert rows[-1]["budget_checkpoint"]["cap_usd"] == "20"
    assert rows[-1]["budget_checkpoint"]["spent_usd"] == "0.02"
    assert rows[-1]["metrics"]["unattributed_spend_usd"] == "0.01"


def test_evaluate_without_resume_rejects_v2_and_preserves_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-resume run must reject legacy evidence without parsing or rewriting it."""
    _stub_live_evaluation(monkeypatch)
    request_log = tmp_path / "requests.jsonl"
    original = _legacy_v2_workflow_payload()
    request_log.write_bytes(original)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(tmp_path / "test.jsonl"),
            "--run-id",
            "run-v2",
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
            str(request_log),
            "--cost-log",
            str(tmp_path / "cost.csv"),
            "--report",
            str(tmp_path / "report.json"),
        ],
    )

    assert result.exit_code == 2
    assert "already exists" in json.loads(result.output)["error"]
    assert request_log.read_bytes() == original


def test_evaluate_without_resume_rejects_existing_v3_before_live_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Treating an existing current journal as a new run would permit remote work."""
    config = LargeLLMConfig(provider=_policy())
    summary = _summary()
    case = _case()
    preview = preview_b4_prompt(case.question, summary)
    prompt_set = workflow.prompt_set_sha256(
        ((case.case_id, (preview.prompt_sha256, preview.retrieval_sha256)),)
    )
    request_log = tmp_path / "requests.jsonl"
    RequestJournal(
        request_log,
        run_id="run-1",
        baseline="b4",
        input_sha256=case.input_sha256,
        config_sha256=config.sha256,
        catalog_sha256=summary.catalog_sha256,
        summary_sha256=summary.summary_sha256,
        training_sha256=None,
        model_id=config.model_id,
        provider_slug=config.provider.provider_slug,
        model_metadata_sha256=METADATA_SHA,
        provider_policy_sha256=config.provider.sha256,
        privacy_sha256="d" * 64,
        prompt_set_sha256=prompt_set,
    )
    original = request_log.read_bytes()
    assert json.loads(original.splitlines()[0])["schema_version"] == 3
    events: list[str] = []

    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (case,))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: summary)
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
    )
    monkeypatch.setattr(
        workflow,
        "_require_api_key",
        lambda: (
            events.append("key")
            or (_ for _ in ()).throw(AssertionError("existing output must precede key access"))
        ),
    )
    monkeypatch.setattr(
        workflow,
        "load_model_metadata",
        lambda *_args: (
            events.append("metadata")
            or (_ for _ in ()).throw(AssertionError("existing output must precede metadata"))
        ),
    )
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *_args, **_kwargs: (
            events.append("transport")
            or (_ for _ in ()).throw(AssertionError("existing output must precede transport"))
        ),
    )

    result = CliRunner().invoke(workflow.cli, _live_evaluate_arguments(tmp_path))

    assert result.exit_code == 2
    assert "already exists" in json.loads(result.output)["error"]
    assert events == []
    assert request_log.read_bytes() == original


def test_evaluate_without_resume_rejects_existing_publication_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silently replacing any prior publication artifact would erase evidence."""
    existing = tmp_path / "predictions.jsonl"
    existing.write_bytes(b"prior evidence\n")
    original = existing.read_bytes()
    events: list[str] = []
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
    )
    monkeypatch.setattr(
        workflow,
        "_require_api_key",
        lambda: (
            events.append("key")
            or (_ for _ in ()).throw(AssertionError("existing output must precede key access"))
        ),
    )

    result = CliRunner().invoke(workflow.cli, _live_evaluate_arguments(tmp_path))

    assert result.exit_code == 2
    assert "already exists" in json.loads(result.output)["error"]
    assert events == []
    assert existing.read_bytes() == original
    assert not (tmp_path / "requests.jsonl").exists()


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


def test_attempt_sink_failure_is_one_secret_safe_cli_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fatal attempt-journal failure must not leak through Click or become an outcome."""
    _stub_live_evaluation(monkeypatch)

    async def fail_attempt(_journal, _evidence) -> None:
        raise workflow.LargeLLMError("raw secret prompt and provider detail")

    class Completions:
        calls = 0

        async def create(self, **_kwargs: object) -> object:
            type(self).calls += 1
            raise AssertionError("SDK must not run after attempt sink failure")

    def failing_transport(config, ledger, *, attempt_sink):
        return OpenRouterTransport(
            sdk=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
            ledger=ledger,
            attempt_sink=attempt_sink,
        )

    monkeypatch.setattr(workflow.RequestJournal, "append_attempt", fail_attempt)
    monkeypatch.setattr(workflow, "load_openrouter_transport", failing_transport)
    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(tmp_path / "test.jsonl"),
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

    assert result.exit_code == 2
    assert result.output.count("\n") == 0
    assert json.loads(result.output) == {
        "error": str(AttemptEvidencePersistenceError()),
        "error_code": "attempt_evidence_persistence_failed",
        "status": "failed",
    }
    assert Completions.calls == 0
    assert not any(
        value in result.output.lower()
        for value in ("traceback", "usage:", "prompt", "secret", "provider detail")
    )


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


@pytest.mark.parametrize("target_id", ["", "bad id"])
def test_b5_predict_rejects_invalid_target_id_before_every_dependency(
    target_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing target-ID primitive validation would reach a dependency seam."""

    def bomb(*_args, **_kwargs):
        raise AssertionError("target ID must stop before dependency construction")

    monkeypatch.setattr(workflow, "compile_catalog_summary", bomb)
    monkeypatch.setattr(workflow, "_b5_cache_preflight", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_sentence_encoder", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b5",
            "--question",
            "List labels",
            "--target-id",
            target_id,
            "--provider",
            "deepinfra",
            "--encoder-revision",
            "a" * 40,
            "--accepted-training-sha256",
            "d" * 64,
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "target ID" in json.loads(result.output)["error"]


def test_b5_predict_rejects_invalid_encoder_id_before_every_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leaving an analogous B5 primitive to filesystem preflight would fail this test."""

    def bomb(*_args, **_kwargs):
        raise AssertionError("encoder ID must stop before dependency construction")

    monkeypatch.setattr(workflow, "compile_catalog_summary", bomb)
    monkeypatch.setattr(workflow, "_b5_cache_preflight", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b5",
            "--question",
            "List labels",
            "--target-id",
            "case-1",
            "--provider",
            "deepinfra",
            "--encoder-id",
            " ",
            "--encoder-revision",
            "a" * 40,
            "--accepted-training-sha256",
            "d" * 64,
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "encoder ID" in json.loads(result.output)["error"]


def test_live_predict_requires_metadata_sha_before_key_or_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allowing a live prediction without accepted metadata would bypass evidence binding."""

    def bomb(*_args, **_kwargs):
        raise AssertionError("required primitive must stop first")

    monkeypatch.setattr(workflow, "compile_catalog_summary", bomb)
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
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "accepted-model-metadata" in json.loads(result.output)["error"]


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("predict", ["--question", "List labels"]),
        ("evaluate", ["--run-id", "run-1"]),
    ],
)
def test_live_commands_require_explicit_cost_cap_before_dependencies(
    command: str, arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defaulting a live cap would permit spending without an explicit operator choice."""

    def bomb(*_args, **_kwargs):
        raise AssertionError("live cap must stop before dependencies")

    monkeypatch.setattr(workflow, "load_evaluation_cases", bomb)
    monkeypatch.setattr(workflow, "compile_catalog_summary", bomb)
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            command,
            "--baseline",
            "b4",
            *arguments,
            "--provider",
            "deepinfra",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "--max-cost-usd" in json.loads(result.output)["error"]


@pytest.mark.parametrize(
    ("marker_input_sha", "accepted_sha", "expected_error"),
    [
        ("f" * 64, "e" * 64, "accepted evidence"),
        ("f" * 64, None, "evaluation snapshot"),
    ],
)
def test_live_evaluate_privacy_marker_blocks_metadata_and_client(
    marker_input_sha: str,
    accepted_sha: str | None,
    expected_error: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Privacy acceptance must bind the exact test bytes before a live dependency."""
    test_set = tmp_path / "test.jsonl"
    snapshot = b'{"id":"case-1"}\n'
    test_set.write_bytes(snapshot)
    privacy_path = tmp_path / "test.jsonl.privacy.json"
    marker = PrivacyReviewEvidence(
        input_sha256=marker_input_sha,
        reviewed=True,
        no_secrets=True,
        no_personal_data=True,
    )
    privacy_path.write_bytes(serialize_privacy_review(marker))
    accepted = accepted_sha or hashlib.sha256(privacy_path.read_bytes()).hexdigest()

    def bomb(*_args, **_kwargs):
        raise AssertionError("privacy acceptance must stop before live dependencies")

    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(test_set),
            "--privacy-review",
            str(privacy_path),
            "--accepted-privacy-review-sha256",
            accepted,
            "--run-id",
            "run-1",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert expected_error in json.loads(result.output)["error"]


def test_live_evaluate_privacy_binds_the_loaded_snapshot_before_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-reading a changed path cannot authorize previously loaded test cases."""
    test_set = tmp_path / "test.jsonl"
    test_set.write_bytes(b'{"id":"replacement"}\n')
    privacy_path = tmp_path / "test.jsonl.privacy.json"
    marker = PrivacyReviewEvidence(
        input_sha256=hashlib.sha256(test_set.read_bytes()).hexdigest(),
        reviewed=True,
        no_secrets=True,
        no_personal_data=True,
    )
    privacy_path.write_bytes(serialize_privacy_review(marker))
    accepted = hashlib.sha256(privacy_path.read_bytes()).hexdigest()

    def bomb(*_args, **_kwargs):
        raise AssertionError("snapshot/privacy drift must stop before live dependencies")

    # The loader has already captured these cases from an earlier snapshot.
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(test_set),
            "--privacy-review",
            str(privacy_path),
            "--accepted-privacy-review-sha256",
            accepted,
            "--run-id",
            "run-1",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "evaluation snapshot" in json.loads(result.output)["error"]


def test_live_evaluate_requires_loaded_snapshot_identity_before_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live evaluation cannot fall back to a later filesystem fingerprint."""
    test_set = tmp_path / "test.jsonl"
    test_set.write_bytes(b'{"id":"case-1"}\n')
    privacy_path = tmp_path / "test.jsonl.privacy.json"
    marker = PrivacyReviewEvidence(
        input_sha256=hashlib.sha256(test_set.read_bytes()).hexdigest(),
        reviewed=True,
        no_secrets=True,
        no_personal_data=True,
    )
    privacy_path.write_bytes(serialize_privacy_review(marker))
    accepted = hashlib.sha256(privacy_path.read_bytes()).hexdigest()
    unidentified_case = EvaluationCase(
        case_id="case-1",
        question="List labels",
        gold_sql=SAFE_SQL,
        difficulty="easy",
        categories=("lookup",),
    )

    def bomb(*_args, **_kwargs):
        raise AssertionError("missing snapshot identity must stop before live dependencies")

    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (unidentified_case,))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow, "load_model_metadata", bomb)
    monkeypatch.setattr(workflow, "load_openrouter_transport", bomb)
    monkeypatch.setattr(workflow, "_require_api_key", bomb)

    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b4",
            "--test-set",
            str(test_set),
            "--privacy-review",
            str(privacy_path),
            "--accepted-privacy-review-sha256",
            accepted,
            "--run-id",
            "run-1",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 2
    assert "snapshot fingerprint is missing" in json.loads(result.output)["error"]


def test_evaluate_snapshot_precedes_output_path_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validating outputs before the snapshot would violate the phase contract."""

    def invalid_snapshot(_path: Path):
        raise workflow.SmallLLMError("snapshot is invalid")

    monkeypatch.setattr(workflow, "load_evaluation_cases", invalid_snapshot)
    monkeypatch.setattr(
        workflow,
        "validate_artifact_paths",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("output too early")),
    )

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
        ],
    )

    assert result.exit_code == 2
    assert "snapshot" in json.loads(result.output)["error"]


def test_b5_cache_hit_attaches_query_encoder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Returning an encoder-less cached retriever would break B5 prediction."""
    cached = object()
    calls = []

    def from_snapshot(*_args, **kwargs):
        calls.append(kwargs["encoder"])
        return cached

    monkeypatch.setattr(
        workflow.FewShotRetriever,
        "from_snapshot",
        from_snapshot,
    )
    monkeypatch.setattr(
        workflow,
        "load_sentence_encoder",
        lambda *_args, **_kwargs: "encoder",
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
    assert calls == [None, "encoder"]


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


@pytest.mark.parametrize("stale", [False, True])
def test_b5_prediction_prepares_query_encoder_before_transport(
    stale: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Creating transport before B5 query retrieval is ready would fail this test."""
    events: list[str] = []
    config = LargeLLMConfig(provider=_policy())
    retriever = _QueryRetriever()

    def from_snapshot(*_args, **kwargs):
        events.append("cache" if kwargs["encoder"] is None else "retriever")
        if stale and kwargs["encoder"] is None:
            raise workflow.SmallLLMError("few-shot cache is invalid and encoder unavailable")
        return retriever

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
    monkeypatch.setattr(workflow.FewShotRetriever, "from_snapshot", from_snapshot)
    monkeypatch.setattr(
        workflow, "load_sentence_encoder", lambda *_args: events.append("encoder") or "encoder"
    )
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
        lambda *_args: events.append("transport") or _SyntheticTransport(config),
    )

    result = CliRunner().invoke(
        workflow.cli,
        [
            "predict",
            "--baseline",
            "b5",
            "--question",
            "List labels",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
            "--training",
            str(tmp_path / "train.jsonl"),
            "--cache",
            str(tmp_path / "cache.npz"),
            "--encoder-revision",
            "a" * 40,
            "--accepted-training-sha256",
            "d" * 64,
            "--accepted-model-metadata-sha256",
            METADATA_SHA,
            "--allow-network",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["prediction"]["sql"] == SAFE_SQL
    assert events.index("encoder") < events.index("transport")
    assert events == (
        ["cache", "encoder", "retriever", "transport"]
        if stale
        else ["cache", "encoder", "retriever", "transport"]
    )


@pytest.mark.parametrize("sidecar", [".json", ".lock"])
def test_evaluate_protects_b5_cache_sidecars(
    sidecar: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping cache sidecars from protected paths would allow this alias."""
    cache = tmp_path / "b5-cache.npz"
    monkeypatch.setattr(workflow, "load_evaluation_cases", lambda _path: (_case(),))
    monkeypatch.setattr(workflow, "compile_catalog_summary", lambda _path: _summary())
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
    monkeypatch.setattr(
        workflow,
        "_privacy_preflight",
        lambda *_args, **_kwargs: (
            SimpleNamespace(privacy_sha256="d" * 64),
            None,
            Path("stub.privacy.json"),
        ),
    )
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
                "--max-cost-usd",
                "20",
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
