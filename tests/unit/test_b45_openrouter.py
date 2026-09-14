import asyncio
import builtins
import socket
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import LargeLLMConfig, ProviderPolicy
from nl2sparql.models.b45.budget import BudgetLedger
from nl2sparql.models.b45.openrouter import (
    OpenRouterRequestError,
    OpenRouterTransport,
    RetryPolicy,
    validate_model_metadata,
)

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
PROMPT_BYTES = 11


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network forbidden in local tests")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)


async def no_wait(delay: float) -> None:
    assert 0.0 <= delay <= 30.0


def make_config(*, max_attempts: int = 3) -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        max_cost_usd=Decimal("1.00"),
        max_attempts=max_attempts,
    )


class FakeCompletions:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = iter(outcomes)
        self.requests: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class SDKError(Exception):
    def __init__(
        self,
        status_code: int,
        *,
        retry_after: str | None = None,
        detail: str = "provider request failed",
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.response = SimpleNamespace(
            headers={} if retry_after is None else {"Retry-After": retry_after}
        )


def response(
    cost: object = "0.0002",
    *,
    provider: str | None = "deepinfra",
    provider_name: str | None = None,
    openrouter_metadata: object | None = None,
    model: object = "meta-llama/llama-3.3-70b-instruct",
    choices: list[object] | None = None,
    prompt_tokens: object = 20,
    completion_tokens: object = 10,
) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": "gen-1",
        "model": model,
        "system_fingerprint": "fp-1",
        "choices": choices
        if choices is not None
        else [
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=SAFE_SQL),
            )
        ],
        "usage": SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            cost_details=SimpleNamespace(upstream_inference_cost="0.00018"),
        ),
    }
    if provider is not None:
        values["provider"] = provider
    if provider_name is not None:
        values["provider_name"] = provider_name
    if openrouter_metadata is not None:
        values["openrouter_metadata"] = openrouter_metadata
    return SimpleNamespace(**values)


def make_transport(
    outcomes: list[object],
    *,
    config: LargeLLMConfig | None = None,
    sleep=no_wait,
    jitter=lambda _attempt: 0.0,
) -> tuple[OpenRouterTransport, FakeCompletions, BudgetLedger]:
    selected_config = config or make_config()
    completions = FakeCompletions(outcomes)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    ledger = BudgetLedger(selected_config)
    transport = OpenRouterTransport(
        sdk=sdk,
        ledger=ledger,
        sleep=sleep,
        clock_ns=iter([0, 2_000_000]).__next__,
        jitter=jitter,
    )
    return transport, completions, ledger


def run_completion(
    transport: OpenRouterTransport,
    config: LargeLLMConfig,
    *,
    request_id: str = "case-1",
):
    return asyncio.run(
        transport.complete((ChatMessage("user", "List labels"),), config, request_id=request_id)
    )


def assert_secret_absent_from_error_chain(error: BaseException, secret: str) -> None:
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert secret not in str(current)
        assert secret not in repr(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


def test_request_pins_model_provider_and_generation_parameters() -> None:
    config = make_config()
    transport, completions, ledger = make_transport([response()], config=config)

    result = run_completion(transport, config)

    request = completions.requests[0]
    assert request["model"] == config.model_id
    assert request["messages"] == [{"role": "user", "content": "List labels"}]
    assert request["temperature"] == 0.0
    assert request["seed"] == 42
    assert request["max_tokens"] == 512
    assert request["n"] == 1
    assert request["provider"] == {
        "only": ["deepinfra"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {"prompt": 0.5, "completion": 1.0},
    }
    assert request["extra_headers"] == {
        "X-OpenRouter-Metadata": "enabled",
        "HTTP-Referer": "https://github.com/vovi102/luanvan",
        "X-Title": "NL2SQL-Thesis",
    }
    assert result.synthetic_backend is False
    assert result.charged_cost_usd == Decimal("0.0002")
    assert result.upstream_cost_usd == Decimal("0.00018")
    assert result.latency_ms == 2.0
    snapshot = asyncio.run(ledger.snapshot())
    assert snapshot.spent_usd == Decimal("0.0002")
    assert snapshot.unresolved_request_ids == ()


def test_official_openrouter_metadata_supplies_provider_identity() -> None:
    config = make_config()
    raw = response(
        provider="wrong-provider",
        openrouter_metadata={"provider_name": "DeepInfra", "provider_slug": "deepinfra"},
    )
    transport, _, _ = make_transport([raw], config=config)

    result = run_completion(transport, config)

    assert result.provider_slug == "deepinfra"


@pytest.mark.parametrize("field", ["provider", "provider_name"])
def test_normalized_top_level_provider_shapes_are_accepted(field: str) -> None:
    config = make_config()
    kwargs = {"provider": None, "provider_name": None, field: "DeepInfra"}
    transport, _, _ = make_transport([response(**kwargs)], config=config)

    result = run_completion(transport, config)

    assert result.provider_slug == "deepinfra"


def test_missing_provider_evidence_fails_closed() -> None:
    config = make_config()
    transport, _, _ = make_transport([response(provider=None)], config=config)

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert captured.value.code == "invalid_response"


@pytest.mark.parametrize("status_code", [408, 409, 429, 500, 502, 503, 504])
def test_transient_http_status_is_retried(status_code: int) -> None:
    config = make_config()
    transport, completions, _ = make_transport([SDKError(status_code), response()], config=config)

    result = run_completion(transport, config)

    assert result.attempt_count == 2
    assert len(completions.requests) == 2


@pytest.mark.parametrize("error", [ConnectionError("down"), TimeoutError("slow")])
def test_transient_transport_error_is_retried(error: Exception) -> None:
    config = make_config()
    transport, completions, _ = make_transport([error, response()], config=config)

    result = run_completion(transport, config)

    assert result.attempt_count == 2
    assert len(completions.requests) == 2


@pytest.mark.parametrize("status_code", [401, 402, 403, 404, 413, 422])
def test_non_retryable_http_status_fails_after_one_attempt(status_code: int) -> None:
    config = make_config()
    transport, completions, ledger = make_transport(
        [SDKError(status_code), response()], config=config
    )

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert captured.value.code == "request_failed"
    assert captured.value.attempt_count == 1
    assert len(completions.requests) == 1
    assert asyncio.run(ledger.snapshot()).unresolved_request_ids == ("case-1:attempt-1",)


def test_bounded_retry_after_takes_precedence() -> None:
    config = make_config()
    delays: list[float] = []

    async def record_wait(delay: float) -> None:
        delays.append(delay)

    transport, _, _ = make_transport(
        [SDKError(429, retry_after="7.5"), response()],
        config=config,
        sleep=record_wait,
        jitter=lambda _attempt: 0.25,
    )

    run_completion(transport, config)

    assert delays == [7.5]


def test_retry_after_is_capped_at_thirty_seconds() -> None:
    config = make_config()
    delays: list[float] = []

    async def record_wait(delay: float) -> None:
        delays.append(delay)

    transport, _, _ = make_transport(
        [SDKError(429, retry_after="90"), response()], config=config, sleep=record_wait
    )

    run_completion(transport, config)

    assert delays == [30.0]


def test_exhausted_transient_error_has_stable_code() -> None:
    config = make_config(max_attempts=2)
    transport, completions, ledger = make_transport([SDKError(429), SDKError(429)], config=config)

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert captured.value.code == "rate_limit_exhausted"
    assert captured.value.attempt_count == 2
    assert len(completions.requests) == 2
    assert asyncio.run(ledger.snapshot()).unresolved_request_ids == (
        "case-1:attempt-1",
        "case-1:attempt-2",
    )


@pytest.mark.parametrize("cost", [None, "", "NaN", "Infinity", "-0.1", object()])
def test_malformed_authoritative_cost_holds_reservation(cost: object) -> None:
    config = make_config()
    transport, _, ledger = make_transport([response(cost)], config=config)

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert captured.value.code == "cost_unresolved"
    assert captured.value.attempt_count == 1
    snapshot = asyncio.run(ledger.snapshot())
    assert snapshot.spent_usd == Decimal("0")
    assert snapshot.unresolved_request_ids == ("case-1:attempt-1",)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            response(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop", message=SimpleNamespace(content=SAFE_SQL)
                    ),
                    SimpleNamespace(
                        finish_reason="stop", message=SimpleNamespace(content=SAFE_SQL)
                    ),
                ]
            ),
            "invalid_response",
        ),
        (
            response(
                choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=""))]
            ),
            "invalid_response",
        ),
        (
            response(
                choices=[
                    SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=" "))
                ]
            ),
            "invalid_response",
        ),
        (
            response(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop", message=SimpleNamespace(content="SELECT\x00 1")
                    )
                ]
            ),
            "invalid_response",
        ),
        (response(provider="other"), "provider_mismatch"),
        (response(model="other/model"), "model_mismatch"),
        (
            response(
                choices=[
                    SimpleNamespace(
                        finish_reason="content_filter",
                        message=SimpleNamespace(content=SAFE_SQL),
                    )
                ]
            ),
            "invalid_response",
        ),
        (response(prompt_tokens=True), "invalid_usage"),
        (response(completion_tokens=-1), "invalid_usage"),
    ],
)
def test_malformed_completion_is_rejected(raw: object, code: str) -> None:
    config = make_config()
    transport, completions, ledger = make_transport([raw, response()], config=config)

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert captured.value.code == code
    assert len(completions.requests) == 1
    assert asyncio.run(ledger.snapshot()).spent_usd == Decimal("0.0002")
    assert captured.value.authoritative_cost_usd == Decimal("0.0002")
    assert captured.value.prompt_sha256 is not None


def test_errors_never_echo_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-openrouter-secret"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    config = make_config(max_attempts=1)
    transport, _, _ = make_transport(
        [SDKError(401, detail=f"bad credential {secret}")], config=config
    )

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert_secret_absent_from_error_chain(captured.value, secret)


def test_transport_rejects_config_mismatch_before_reservation() -> None:
    ledger_config = make_config()
    request_config = LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.75"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        max_cost_usd=Decimal("1.00"),
    )
    transport, completions, ledger = make_transport([response()], config=ledger_config)

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, request_config)

    assert captured.value.code == "transport_configuration_mismatch"
    assert completions.requests == []
    assert asyncio.run(ledger.snapshot()).unresolved_request_ids == ()


def test_budget_rejection_prevents_sdk_request() -> None:
    config = LargeLLMConfig(
        provider=make_config().provider,
        max_cost_usd=Decimal("0.000001"),
    )
    transport, completions, _ = make_transport([response()], config=config)

    with pytest.raises(OpenRouterRequestError) as captured:
        run_completion(transport, config)

    assert captured.value.code == "budget_blocked"
    assert completions.requests == []


def test_from_env_rejects_missing_key_before_importing_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "openai":
            raise AssertionError("SDK construction must stay lazy")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    with pytest.raises(OpenRouterRequestError) as captured:
        OpenRouterTransport.from_env(make_config(), BudgetLedger(make_config()))

    assert captured.value.code == "missing_api_key"


def test_from_env_uses_pinned_client_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    fake_sdk = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions([])))

    def async_openai(**kwargs: object) -> object:
        calls.append(kwargs)
        return fake_sdk

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=async_openai))
    config = make_config()
    ledger = BudgetLedger(config)

    transport = OpenRouterTransport.from_env(config, ledger)

    assert isinstance(transport, OpenRouterTransport)
    assert calls == [
        {
            "api_key": "test-only-key",
            "base_url": "https://openrouter.ai/api/v1",
            "timeout": 60.0,
            "max_retries": 0,
        }
    ]


def test_from_env_redacts_sdk_construction_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-only-secret"

    def fail_construction(**_kwargs: object) -> object:
        raise RuntimeError(f"constructor exposed {secret}")

    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=fail_construction))

    with pytest.raises(OpenRouterRequestError) as captured:
        OpenRouterTransport.from_env(make_config(), BudgetLedger(make_config()))

    assert captured.value.code == "client_initialization_failed"
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert_secret_absent_from_error_chain(captured.value, secret)


def metadata_response() -> dict[str, object]:
    return {
        "data": {
            "id": "meta-llama/llama-3.3-70b-instruct",
            "endpoints": [
                {
                    "provider_name": "DeepInfra",
                    "context_length": 131_072,
                    "supported_parameters": ["temperature", "seed", "max_tokens"],
                    "pricing": {"prompt": "0.0000004", "completion": "0.0000008"},
                }
            ],
        }
    }


def test_model_metadata_validates_provider_capabilities_and_is_immutable() -> None:
    evidence = validate_model_metadata(
        metadata_response(), make_config(), prompt_bytes=PROMPT_BYTES
    )

    assert evidence.model_id == "meta-llama/llama-3.3-70b-instruct"
    assert evidence.provider_slug == "deepinfra"
    assert evidence.context_length == 131_072
    assert evidence.supported_parameters == ("max_tokens", "seed", "temperature")
    assert evidence.prompt_price_per_million_usd == Decimal("0.4")
    assert evidence.completion_price_per_million_usd == Decimal("0.8")
    assert len(evidence.metadata_sha256) == 64
    assert (
        evidence.metadata_sha256
        == validate_model_metadata(
            metadata_response(), make_config(), prompt_bytes=PROMPT_BYTES
        ).metadata_sha256
    )
    with pytest.raises(FrozenInstanceError):
        evidence.context_length = 1  # type: ignore[misc]


def test_model_metadata_keeps_injected_float_adapter_compatible() -> None:
    """A conservative float adapter must remain usable without understating its value."""
    raw = metadata_response()
    raw["data"]["endpoints"][0]["pricing"] = {  # type: ignore[index]
        "prompt": 4e-7,
        "completion": 8e-7,
    }

    evidence = validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)

    assert Decimal("0") < evidence.prompt_price_per_million_usd <= Decimal("0.4")
    assert Decimal("0") < evidence.completion_price_per_million_usd <= Decimal("0.8")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["data"].update({"id": "other/model"}),
        lambda raw: raw["data"]["endpoints"][0].update({"provider_name": "Other"}),
        lambda raw: raw["data"]["endpoints"][0].update(
            {"supported_parameters": ["temperature", "max_tokens"]}
        ),
        lambda raw: raw["data"]["endpoints"][0]["pricing"].update({"prompt": "0.0000006"}),
        lambda raw: raw["data"]["endpoints"][0].update({"context_length": 511}),
    ],
)
def test_model_metadata_fails_closed_on_drift(mutate) -> None:
    raw = metadata_response()
    mutate(raw)

    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)

    assert captured.value.code == "model_metadata_invalid"


def test_model_metadata_requires_explicit_prompt_bytes() -> None:
    with pytest.raises(TypeError):
        validate_model_metadata(metadata_response(), make_config())


@pytest.mark.parametrize("prompt_bytes", [True, -1, 1.5])
def test_model_metadata_rejects_invalid_prompt_bytes(prompt_bytes: object) -> None:
    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(
            metadata_response(),
            make_config(),
            prompt_bytes=prompt_bytes,  # type: ignore[arg-type]
        )

    assert captured.value.code == "model_metadata_invalid"


def test_model_metadata_requires_endpoint_local_parameters() -> None:
    raw = metadata_response()
    raw["data"]["supported_parameters"] = [
        "temperature",
        "seed",
        "max_tokens",
    ]  # type: ignore[index]
    del raw["data"]["endpoints"][0]["supported_parameters"]  # type: ignore[index]

    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)

    assert captured.value.code == "model_metadata_invalid"


def test_model_metadata_requires_endpoint_local_context_length() -> None:
    raw = metadata_response()
    raw["data"]["context_length"] = 131_072  # type: ignore[index]
    del raw["data"]["endpoints"][0]["context_length"]  # type: ignore[index]

    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)

    assert captured.value.code == "model_metadata_invalid"


def test_model_metadata_uses_explicit_prompt_byte_count() -> None:
    raw = metadata_response()
    raw["data"]["endpoints"][0]["context_length"] = 512 + PROMPT_BYTES  # type: ignore[index]
    evidence = validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)
    assert evidence.context_length == 512 + PROMPT_BYTES

    raw = metadata_response()
    raw["data"]["endpoints"][0]["context_length"] = 512 + PROMPT_BYTES - 1  # type: ignore[index]
    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)

    assert captured.value.code == "model_metadata_invalid"


def test_model_metadata_rejects_non_finite_fingerprint_input() -> None:
    raw = metadata_response()
    raw["diagnostic"] = float("nan")

    with pytest.raises(OpenRouterRequestError) as captured:
        validate_model_metadata(raw, make_config(), prompt_bytes=PROMPT_BYTES)

    assert captured.value.code == "model_metadata_invalid"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1])
def test_retry_policy_rejects_invalid_jitter(value: float) -> None:
    policy = RetryPolicy(max_attempts=3)

    with pytest.raises(OpenRouterRequestError, match="retry delay"):
        policy.delay_seconds(SDKError(429), attempt=1, jitter=lambda _attempt: value)
