"""Tests for Gemini adaptation, Stage C expansion, and CLI gates."""

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
from nl2sparql.dataset.paraphrase.contracts import (
    STAGE_B_MODEL,
    STAGE_C_MODEL,
    build_preserved_facts,
)
from nl2sparql.dataset.paraphrase.gemini import (
    GeminiClient,
    GeminiConfigurationError,
)
from nl2sparql.dataset.paraphrase.prompts import build_stage_b_request
from nl2sparql.dataset.paraphrase.runner import CompletionAPIError, CompletionResult

STAGE_A_PATH = Path("data/dataset/raw/synthetic-stage-a.jsonl")


def one_source() -> dict[str, object]:
    return json.loads(STAGE_A_PATH.read_text().splitlines()[0])


class FakeHTTP:
    def __init__(self) -> None:
        self.kwargs = None

    async def post(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "responseId": "gen-1",
                "modelVersion": "gemini-3.5-flash",
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"question":"Q?","preserved_facts":[]}'}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 15,
                },
            },
        )


def test_gemini_adapter_sends_json_schema_and_records_free_tier_cost() -> None:
    http = FakeHTTP()
    client = GeminiClient(
        api_key="test-key",
        http=http,
        clock_ns=iter([0, 2_000_000]).__next__,
    )
    request = build_stage_b_request(one_source(), {})

    result = __import__("asyncio").run(client.complete(request))

    assert isinstance(result, CompletionResult)
    assert result.cost_usd == 0.0
    assert result.latency_ms == 2.0
    assert http.url.endswith("/models/gemini-3.5-flash:generateContent")
    assert http.kwargs["headers"] == {"x-goog-api-key": "test-key"}
    payload = http.kwargs["json"]
    assert payload["contents"][0]["parts"][0]["text"] == request.user_prompt
    assert payload["systemInstruction"]["parts"][0]["text"].startswith("You are a precise")
    config = payload["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == request.response_schema
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert config["maxOutputTokens"] == 1024


def test_gemini_from_env_requires_only_gemini_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY") as error:
        GeminiClient.from_env()
    assert "must-not-be-used" not in str(error.value)


def test_gemini_from_env_requires_free_tier_attestation(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)

    with pytest.raises(GeminiConfigurationError, match="GEMINI_FREE_TIER_CONFIRMED=1"):
        GeminiClient.from_env()


def test_gemini_adapter_rejects_truncated_response() -> None:
    class TruncatedHTTP(FakeHTTP):
        async def post(self, url, **kwargs):
            response = await super().post(url, **kwargs)
            payload = response.json()
            payload["candidates"][0]["finishReason"] = "MAX_TOKENS"
            return SimpleNamespace(status_code=200, json=lambda: payload)

    client = GeminiClient(api_key="test-key", http=TruncatedHTTP())

    with pytest.raises(CompletionAPIError, match="MAX_TOKENS") as error:
        __import__("asyncio").run(client.complete(build_stage_b_request(one_source(), {})))

    assert error.value.retryable is False


@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(400, False), (429, True), (503, True)],
)
def test_gemini_adapter_classifies_http_failures_without_leaking_key(
    status_code: int, retryable: bool
) -> None:
    class FailingHTTP:
        async def post(self, url, **kwargs):
            return SimpleNamespace(status_code=status_code)

    client = GeminiClient(api_key="secret-key", http=FailingHTTP())

    with pytest.raises(CompletionAPIError, match=str(status_code)) as error:
        __import__("asyncio").run(client.complete(build_stage_b_request(one_source(), {})))

    assert error.value.retryable is retryable
    assert "secret-key" not in str(error.value)


def test_gemini_adapter_fails_fast_and_reports_safe_daily_quota_metadata() -> None:
    class DailyQuotaHTTP:
        async def post(self, url, **kwargs):
            return SimpleNamespace(
                status_code=429,
                json=lambda: {
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "sensitive provider text must not be copied",
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                "violations": [
                                    {
                                        "quotaMetric": (
                                            "generativelanguage.googleapis.com/"
                                            "generate_content_free_tier_requests"
                                        ),
                                        "quotaId": (
                                            "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
                                        ),
                                        "quotaDimensions": {"model": "gemini-3.5-flash"},
                                        "quotaValue": "20",
                                    }
                                ],
                            },
                            {
                                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                "retryDelay": "123s",
                            },
                        ],
                    }
                },
            )

    client = GeminiClient(api_key="secret-key", http=DailyQuotaHTTP())

    with pytest.raises(CompletionAPIError) as error:
        __import__("asyncio").run(client.complete(build_stage_b_request(one_source(), {})))

    text = str(error.value)
    assert error.value.retryable is False
    assert "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in text
    assert "quota_value=20" in text
    assert "retry_after=123s" in text
    assert "sensitive provider text" not in text
    assert "secret-key" not in text


def test_gemini_adapter_rejects_malformed_success_response() -> None:
    class MalformedHTTP:
        async def post(self, url, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: {"candidates": []})

    client = GeminiClient(api_key="test-key", http=MalformedHTTP())

    with pytest.raises(CompletionAPIError, match="invalid response") as error:
        __import__("asyncio").run(client.complete(build_stage_b_request(one_source(), {})))

    assert error.value.retryable is False


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
            "stage_b": {
                "generation_id": f"stage-b-{index}",
                "requested_model": STAGE_B_MODEL,
                "cost_usd": 0.0,
            },
        }
        for index in range(1000)
    ]
    stage_c_records = [
        {
            "id": f"child-{index}",
            "parent_id": f"syn-{index // 3:06d}",
            "nl_normalized": f"question {index}",
            "stage_c": {
                "pairwise_distances": [0.4, 0.5, 0.6],
                "requested_model": STAGE_C_MODEL,
                "cost_usd": 0.0,
            },
        }
        for index in range(3000)
    ]
    validate_stage_b_records(stage_b_records)
    validate_stage_c_records(stage_c_records)
    with pytest.raises(ParaphraseArtifactError, match="1000"):
        validate_stage_b_records(stage_b_records[:-1])
    stale_stage_b = [*stage_b_records]
    stale_stage_b[0] = {
        **stale_stage_b[0],
        "stage_b": {**stale_stage_b[0]["stage_b"], "requested_model": "old-model"},
    }
    with pytest.raises(ParaphraseArtifactError, match="Gemini model"):
        validate_stage_b_records(stale_stage_b)
    stale_stage_c = [*stage_c_records]
    stale_stage_c[0] = {
        **stale_stage_c[0],
        "stage_c": {**stale_stage_c[0]["stage_c"], "cost_usd": 0.01},
    }
    with pytest.raises(ParaphraseArtifactError, match="zero-cost"):
        validate_stage_c_records(stale_stage_c)

    manifest = build_run_manifest(
        source_sha256="a" * 64,
        stage_b_sha256="b" * 64,
        stage_c_sha256="c" * 64,
        stage_b_records=stage_b_records,
        stage_c_records=stage_c_records,
        recorded_cost_usd=0.0,
        cost_cap_usd=0.0,
        generated_at="2026-08-09T00:00:00Z",
    )
    assert manifest["provider"] == {
        "id": "gemini-developer-api",
        "billing_tier": "free",
        "fallback_allowed": False,
        "operator_attestation": "GEMINI_FREE_TIER_CONFIRMED=1",
    }
    assert manifest["models"]["stage_b"]["thinking_level"] == "minimal"
    assert manifest["models"]["stage_b"]["max_output_tokens"] == 1024
    assert manifest["cost"] == {
        "recorded_usd": 0.0,
        "cap_usd": 0.0,
        "source": "operator_attested_free_tier_contract",
        "authoritative_billing_evidence": False,
    }
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


def test_cli_validate_only_never_constructs_gemini(monkeypatch) -> None:
    script = load_script()

    class ForbiddenClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("validate-only must not construct a client")

    monkeypatch.setattr(script, "GeminiClient", ForbiddenClient)
    result = CliRunner().invoke(script.main, ["--mode", "validate-only"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "validate-only"
    assert payload["provider"] == "gemini-developer-api"
    assert payload["cost_cap_usd"] == 0.0
    assert payload["stage_a_records"] == 1000
    assert payload["source_sha256"] == (
        "a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709"
    )


def test_all_mode_runs_both_stages_and_closes_client_on_one_event_loop(
    monkeypatch, tmp_path: Path
) -> None:
    script = load_script()
    loop_ids: list[int] = []
    requested_rates: list[int] = []

    class FakeClient:
        @classmethod
        def from_env(cls):
            return cls()

        async def aclose(self):
            loop_ids.append(id(__import__("asyncio").get_running_loop()))

    async def fake_stage_b(*args, **kwargs):
        loop_ids.append(id(__import__("asyncio").get_running_loop()))
        requested_rates.append(kwargs["requests_per_minute"])
        return SimpleNamespace(records=({"id": "one"},), total_cost_usd=0.0)

    async def fake_stage_c(*args, **kwargs):
        loop_ids.append(id(__import__("asyncio").get_running_loop()))
        requested_rates.append(kwargs["requests_per_minute"])
        return SimpleNamespace(records=({"id": "one"},), total_cost_usd=0.0)

    monkeypatch.setattr(script, "GeminiClient", FakeClient)
    monkeypatch.setattr(script, "load_entity_index", lambda: {})
    monkeypatch.setattr(script, "run_stage_b", fake_stage_b)
    monkeypatch.setattr(script, "run_stage_c", fake_stage_c)
    monkeypatch.setattr(script, "validate_stage_b_records", lambda records: None)
    monkeypatch.setattr(script, "validate_stage_c_records", lambda records: None)
    monkeypatch.setattr(script, "expand_stage_c_records", lambda parents: [{"id": "child"}])
    monkeypatch.setattr(script, "write_cost_log", lambda records, path: None)
    monkeypatch.setattr(script, "build_run_manifest", lambda **kwargs: {})
    monkeypatch.setattr(script, "STAGE_B_PATH", tmp_path / "stage-b.jsonl")
    monkeypatch.setattr(script, "STAGE_C_PATH", tmp_path / "stage-c.jsonl")
    monkeypatch.setattr(script, "CONFIG_PATH", tmp_path / "manifest.json")

    payload = __import__("asyncio").run(
        script._run_live(
            mode="all",
            stage_a=[{"id": "source"}],
            source_sha256="a" * 64,
            concurrency=1,
        )
    )

    assert payload["recorded_cost_usd"] == 0.0
    assert len(set(loop_ids)) == 1
    assert len(loop_ids) == 3
    assert requested_rates == [4, 4]
