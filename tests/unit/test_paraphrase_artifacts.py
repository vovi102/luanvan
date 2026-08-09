"""Tests for OpenRouter adaptation, Stage C expansion, and CLI gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from nl2sparql.dataset.paraphrase.artifacts import (
    ParaphraseArtifactError,
    build_run_manifest,
    deterministic_audit_ids,
    expand_stage_c_records,
    total_generation_cost,
    validate_stage_b_records,
    validate_stage_c_records,
    write_json_atomic,
)
from nl2sparql.dataset.paraphrase.contracts import build_preserved_facts
from nl2sparql.dataset.paraphrase.openrouter import (
    OpenRouterClient,
    OpenRouterConfigurationError,
)
from nl2sparql.dataset.paraphrase.prompts import build_stage_b_request
from nl2sparql.dataset.paraphrase.runner import CompletionResult

STAGE_A_PATH = Path("data/dataset/raw/synthetic-stage-a.jsonl")


def one_source() -> dict[str, object]:
    return json.loads(STAGE_A_PATH.read_text().splitlines()[0])


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="gen-1",
            model=kwargs["model"],
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"question":"Q?","preserved_facts":[]}')
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                model_dump=lambda: {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.0002,
                },
            ),
        )


def test_openrouter_adapter_sends_strict_schema_and_extracts_actual_cost() -> None:
    completions = FakeCompletions()
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = OpenRouterClient(sdk=sdk, clock_ns=iter([0, 2_000_000]).__next__)
    request = build_stage_b_request(one_source(), {})

    result = __import__("asyncio").run(client.complete(request))

    assert isinstance(result, CompletionResult)
    assert result.cost_usd == 0.0002
    assert result.latency_ms == 2.0
    assert completions.kwargs["response_format"]["type"] == "json_schema"
    assert completions.kwargs["response_format"]["json_schema"]["strict"] is True
    assert completions.kwargs["extra_body"]["provider"]["require_parameters"] is True
    assert completions.kwargs["messages"][0]["content"].startswith("You are a precise")


def test_openrouter_from_env_fails_without_leaking_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(OpenRouterConfigurationError, match="OPENROUTER_API_KEY") as error:
        OpenRouterClient.from_env()
    assert "sk-" not in str(error.value)


def test_stage_c_expands_three_children_and_enforces_quality() -> None:
    source = one_source()
    formal = source["nl_seed"]
    parent = {
        **source,
        "nl_formal": formal,
        "stage_b": {"preserved_facts": build_preserved_facts(source)},
        "stage_c": {
            "responses": {
                "casual": "How many transactions happened from 2026-06-01 to 2026-06-02?",
                "abbreviated": "Transaction count, 2026-06-01–2026-06-02?",
                "alternative": "Between 2026-06-01 and 2026-06-02, what was the transaction total?",
            },
            "pairwise_distances": [0.4, 0.5, 0.6],
        },
    }

    children = expand_stage_c_records([parent])

    assert len(children) == 3
    assert {child["version"] for child in children} == {
        "casual",
        "abbreviated",
        "alternative",
    }
    assert all(child["parent_id"] == source["id"] for child in children)
    assert all(child["sql"] == source["sql"] for child in children)
    assert len({child["nl_normalized"] for child in children}) == 3
    with pytest.raises(ParaphraseArtifactError, match="3000"):
        validate_stage_c_records(children)


def test_manifest_helpers_are_deterministic_and_costs_are_deduplicated(
    tmp_path: Path,
) -> None:
    records = [{"id": f"syn-{index:06d}"} for index in range(100)]
    assert deterministic_audit_ids(records, 5) == deterministic_audit_ids(records, 5)
    assert len(deterministic_audit_ids(records, 5)) == 5

    generated = [
        {
            "id": "one",
            "stage_b": {"generation_id": "gen-1", "cost_usd": 0.01},
        },
        {
            "id": "one-copy",
            "stage_b": {"generation_id": "gen-1", "cost_usd": 0.01},
        },
    ]
    assert total_generation_cost({"stage_b": generated}) == pytest.approx(0.01)

    stage_b_records = [
        {
            "id": f"syn-{index:06d}",
            "nl_formal": f"Formal question {index}?",
            "stage_b": {"generation_id": f"stage-b-{index}"},
        }
        for index in range(1000)
    ]
    stage_c_records = [
        {
            "id": f"child-{index}",
            "parent_id": f"syn-{index // 3:06d}",
            "nl_normalized": f"question {index}",
            "stage_c": {"pairwise_distances": [0.4, 0.5, 0.6]},
        }
        for index in range(3000)
    ]
    validate_stage_b_records(stage_b_records)
    validate_stage_c_records(stage_c_records)
    with pytest.raises(ParaphraseArtifactError, match="1000"):
        validate_stage_b_records(stage_b_records[:-1])

    manifest = build_run_manifest(
        source_sha256="a" * 64,
        stage_b_sha256="b" * 64,
        stage_c_sha256="c" * 64,
        stage_b_records=stage_b_records,
        stage_c_records=stage_c_records,
        actual_cost_usd=0.01,
        cost_cap_usd=30.0,
        generated_at="2026-08-09T00:00:00Z",
    )
    assert manifest["quality"]["mean_stage_c_distance"] == pytest.approx(0.5)
    assert len(manifest["audits"]["stage_b_record_ids"]) == 50
    assert len(manifest["audits"]["stage_c_parent_ids"]) == 100
    output = tmp_path / "manifest.json"
    write_json_atomic(manifest, output)
    assert json.loads(output.read_text()) == manifest


def test_atomic_json_writer_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
) -> None:
    class FailingReplacePath(type(Path())):
        def replace(self, target):
            raise OSError("simulated replace failure")

    output = FailingReplacePath(tmp_path / "manifest.json")
    output.write_text("original\n")
    with pytest.raises(OSError, match="replace failure"):
        write_json_atomic({"status": "new"}, output)
    assert output.read_text() == "original\n"
    assert not (tmp_path / ".manifest.json.tmp").exists()


def load_script():
    path = Path("scripts/10_paraphrase_stage_a.py").resolve()
    spec = importlib.util.spec_from_file_location("paraphrase_stage_a_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_validate_only_never_constructs_openrouter(monkeypatch) -> None:
    script = load_script()

    class ForbiddenClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("validate-only must not construct a client")

    monkeypatch.setattr(script, "OpenRouterClient", ForbiddenClient)
    result = CliRunner().invoke(script.main, ["--mode", "validate-only"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "validate-only"
    assert payload["stage_a_records"] == 1000
    assert payload["source_sha256"] == (
        "a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709"
    )
