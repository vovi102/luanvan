# T5.3 GoogleSQL Large-LLM Baselines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build offline-verifiable B4/B5 GoogleSQL baselines with a lazy OpenRouter adapter, retry-safe request handling, a concurrent USD 20 cost ledger, reproducible artifacts, and explicit scientific blockers.

**Architecture:** Add a focused `nl2sparql.models.b45` deep module that reuses B1/B2 catalog prompts, five-shot retrieval, and fail-closed GoogleSQL extraction. Keep remote transport, cost accounting, baseline orchestration, evaluation, and artifact publication as separate units; the CLI validates everything locally before an explicit network opt-in can construct the OpenRouter client.

**Tech Stack:** Python 3.11, frozen dataclasses, `asyncio`, `decimal.Decimal`, OpenAI-compatible `openai` SDK, Click, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-07-t5-3-google-sql-large-llm-design.md`

## Global Constraints

- Canonical model ID is exactly `meta-llama/llama-3.3-70b-instruct`.
- B4 is zero-shot; B5 differs only by the exact five-example block produced by the accepted B2 retriever.
- Both baselines reuse `b12.prompts.build_messages` and `b12.extraction.extract_google_sql`; neither may consume T4 linker/resolver evidence.
- Generation is fixed at `temperature=0`, `seed=42`, `max_tokens=512`, and one returned choice.
- Live routing pins one provider, sets `allow_fallbacks=false`, `require_parameters=true`, `data_collection="deny"`, and explicit maximum prompt/completion prices.
- The total configured live budget must be greater than zero and at most USD 20.
- Network access requires both `--allow-network` and a non-empty `OPENROUTER_API_KEY`; help, validation, and local tests must not construct a client or open a socket.
- Synthetic transports and caller-provided readiness booleans can never create scientific evidence.
- Money uses `Decimal`, while JSON stores canonical decimal strings.
- Production code uses Loguru rather than `print`; CLI JSON is emitted through Click.
- Public functions/classes have type hints and Google-style docstrings.
- Use `uv run python -m pytest`, because this repository's direct `pytest` entry point does not collect existing `scripts.*` imports correctly.
- Every task follows red-green-refactor and ends in a Conventional Commit.

---

### Task 1: Immutable B4/B5 contracts and pinned configuration

**Files:**
- Create: `src/nl2sparql/models/b45/contracts.py`
- Create: `src/nl2sparql/models/b45/__init__.py`
- Create: `tests/unit/test_b45_contracts.py`

**Interfaces:**
- Consumes: `ChatMessage`, `CatalogSummary`, `ExtractionStatus`, `SelectedExample`, and `validate_question` from `nl2sparql.models.b12.contracts`.
- Produces: `LargeLLMError`, `ProviderPolicy`, `LargeLLMConfig`, `RemoteCompletion`, `LargeLLMPrediction`, `canonical_money(value: Decimal) -> str`, and private loader-issued live completion provenance.

- [ ] **Step 1: Write failing tests for canonical configuration and immutable accounting**

```python
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from nl2sparql.models.b45.contracts import (
    LargeLLMConfig,
    LargeLLMError,
    ProviderPolicy,
    RemoteCompletion,
)


def policy() -> ProviderPolicy:
    return ProviderPolicy(
        provider_slug="deepinfra",
        prompt_price_per_million_usd=Decimal("0.50"),
        completion_price_per_million_usd=Decimal("1.00"),
    )


def test_config_is_pinned_and_self_fingerprinting() -> None:
    config = LargeLLMConfig(provider=policy())
    assert config.model_id == "meta-llama/llama-3.3-70b-instruct"
    assert config.temperature == Decimal("0")
    assert config.seed == 42
    assert config.max_tokens == 512
    assert config.max_cost_usd == Decimal("20.00")
    assert len(config.sha256) == 64
    with pytest.raises(FrozenInstanceError):
        config.seed = 7  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_id", "openrouter/auto", "model_id"),
        ("temperature", Decimal("0.1"), "temperature"),
        ("seed", 7, "seed"),
        ("max_tokens", 513, "max_tokens"),
        ("max_cost_usd", Decimal("20.01"), "at most USD 20"),
    ],
)
def test_config_rejects_scientific_drift(field, value, message) -> None:
    with pytest.raises(LargeLLMError, match=message):
        replace(LargeLLMConfig(provider=policy()), **{field: value})


def test_completion_is_synthetic_by_default_and_cannot_be_relabelled() -> None:
    completion = RemoteCompletion.synthetic(
        raw_text="SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
        model_id="meta-llama/llama-3.3-70b-instruct",
        provider_slug="scripted",
        input_tokens=10,
        output_tokens=5,
        charged_cost_usd=Decimal("0"),
        latency_ms=1.0,
    )
    assert completion.synthetic_backend is True
    with pytest.raises(TypeError):
        RemoteCompletion(  # type: ignore[call-arg]
            raw_text="x", synthetic_backend=False
        )
```

- [ ] **Step 2: Run the contract tests and verify the missing module failure**

Run: `uv run python -m pytest tests/unit/test_b45_contracts.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'nl2sparql.models.b45'`.

- [ ] **Step 3: Implement strict frozen contracts and fingerprints**

Implement these exact public shapes in `contracts.py`:

```python
MODEL_ID = "meta-llama/llama-3.3-70b-instruct"


class LargeLLMError(ValueError):
    """Raised when B4/B5 configuration, responses, or artifacts are invalid."""


@dataclass(frozen=True)
class ProviderPolicy:
    """Pinned OpenRouter provider and maximum accepted token prices."""

    provider_slug: str
    prompt_price_per_million_usd: Decimal
    completion_price_per_million_usd: Decimal
    allow_fallbacks: bool = False
    require_parameters: bool = True
    data_collection: Literal["deny"] = "deny"


@dataclass(frozen=True)
class LargeLLMConfig:
    """Scientific generation, retry, concurrency, and budget configuration."""

    provider: ProviderPolicy
    model_id: str = MODEL_ID
    temperature: Decimal = Decimal("0")
    seed: int = 42
    max_tokens: int = 512
    choice_count: int = 1
    max_cost_usd: Decimal = Decimal("20.00")
    concurrency: int = 5
    timeout_seconds: Decimal = Decimal("60")
    max_attempts: int = 3

    @property
    def sha256(self) -> str:
        """Return a canonical fingerprint of every run-affecting setting."""


@dataclass(frozen=True)
class RemoteCompletion:
    """One validated remote completion with provider and billing evidence."""

    raw_text: str
    generation_id: str
    model_id: str
    provider_slug: str
    input_tokens: int
    output_tokens: int
    charged_cost_usd: Decimal
    upstream_cost_usd: Decimal | None
    latency_ms: float
    attempt_count: int
    finish_reason: str
    system_fingerprint: str | None
    synthetic_backend: bool = field(init=False, default=True)

    @classmethod
    def synthetic(
        cls,
        *,
        raw_text: str,
        model_id: str,
        provider_slug: str,
        input_tokens: int,
        output_tokens: int,
        charged_cost_usd: Decimal,
        latency_ms: float,
        generation_id: str = "synthetic",
        upstream_cost_usd: Decimal | None = None,
        attempt_count: int = 1,
        finish_reason: str = "stop",
        system_fingerprint: str | None = None,
    ) -> RemoteCompletion:
        """Create an explicitly synthetic completion for local tests."""
        return cls(
            raw_text=raw_text,
            generation_id=generation_id,
            model_id=model_id,
            provider_slug=provider_slug,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            charged_cost_usd=charged_cost_usd,
            upstream_cost_usd=upstream_cost_usd,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
            finish_reason=finish_reason,
            system_fingerprint=system_fingerprint,
        )


@dataclass(frozen=True)
class LargeLLMPrediction:
    """One B4/B5 result with SQL extraction and complete remote provenance."""

    baseline: Literal["b4", "b5"]
    question: str
    raw_output: str
    sql: str | None
    extraction_status: ExtractionStatus
    completion: RemoteCompletion
    catalog_sha256: str
    summary_sha256: str
    prompt_sha256: str
    config_sha256: str
    latency_ms: float
    training_sha256: str | None = None
    encoder_id: str | None = None
    encoder_revision: str | None = None
    training_accepted: bool = False
    selected_examples: tuple[SelectedExample, ...] = ()
```

Validate all strings, finite numbers, non-negative token/cost values, fixed generation parameters, price ceilings, baseline-specific provenance, exact five-example B5 cardinality, and SHA-256 fields. Hash dataclasses through sorted compact JSON after converting each `Decimal` with `canonical_money`; never hash `float(Decimal)`.

Keep live provenance private: `RemoteCompletion.synthetic` is public, while `_openrouter_completion(response, marker)` requires a module-private identity marker and is imported only by the live adapter. There is no constructor parameter or public method that changes `synthetic_backend` to false.

Export the stable public names from `b45/__init__.py`; do not import `b45.openrouter` there.

- [ ] **Step 4: Run focused contracts and existing B1/B2 tests**

Run: `uv run python -m pytest tests/unit/test_b45_contracts.py tests/unit/test_b12_baseline.py tests/unit/test_b12_prompts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the contract layer**

```bash
git add src/nl2sparql/models/b45 tests/unit/test_b45_contracts.py
git commit -m "feat(baselines): define large-LLM contracts"
```

---

### Task 2: Concurrent hard-cap budget ledger

**Files:**
- Create: `src/nl2sparql/models/b45/budget.py`
- Create: `tests/unit/test_b45_budget.py`
- Modify: `src/nl2sparql/models/b45/__init__.py`

**Interfaces:**
- Consumes: `LargeLLMConfig`, `LargeLLMError`, `ChatMessage`.
- Produces: `BudgetLedger.reserve(request_id: str, messages: tuple[ChatMessage, ...]) -> BudgetReservation | None`, `BudgetLedger.reconcile(reservation, actual_cost_usd) -> BudgetSnapshot`, `BudgetLedger.hold(reservation, reason) -> BudgetSnapshot`, `BudgetLedger.snapshot() -> BudgetSnapshot`, and `conservative_request_cost(messages, config) -> Decimal`.

- [ ] **Step 1: Write failing tests for reservation, reconciliation, and concurrency**

```python
import asyncio
from decimal import Decimal

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import LargeLLMConfig, ProviderPolicy
from nl2sparql.models.b45.budget import BudgetLedger


def config(cap: str = "0.001") -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("1"),
            completion_price_per_million_usd=Decimal("1"),
        ),
        max_cost_usd=Decimal(cap),
    )


def test_reservation_reconciles_authoritative_cost() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.001"))
        messages = (ChatMessage("user", "x"),)
        reservation = await ledger.reserve("case-1", messages)
        assert reservation is not None
        snapshot = await ledger.reconcile(reservation, Decimal("0.0002"))
        assert snapshot.spent_usd == Decimal("0.0002")
        assert snapshot.reserved_usd == Decimal("0")

    asyncio.run(scenario())


def test_concurrent_workers_cannot_oversubscribe_cap() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.0011"))
        messages = (ChatMessage("user", "x"),)
        reservations = await asyncio.gather(
            *(ledger.reserve(f"case-{index}", messages) for index in range(3))
        )
        accepted = [item for item in reservations if item is not None]
        snapshot = await ledger.snapshot()
        assert len(accepted) == 2
        assert snapshot.spent_usd + snapshot.reserved_usd <= snapshot.cap_usd

    asyncio.run(scenario())


def test_unknown_cost_holds_reservation_and_blocks_future_spend() -> None:
    async def scenario() -> None:
        ledger = BudgetLedger(config("0.001"))
        messages = (ChatMessage("user", "x"),)
        reservation = await ledger.reserve("case-1", messages)
        assert reservation is not None
        snapshot = await ledger.hold(reservation, "missing_usage_cost")
        assert snapshot.unresolved_request_ids == ("case-1",)
        assert await ledger.reserve("case-2", messages) is None

    asyncio.run(scenario())
```

- [ ] **Step 2: Run the budget tests and verify they fail**

Run: `uv run python -m pytest tests/unit/test_b45_budget.py -q`

Expected: FAIL because `nl2sparql.models.b45.budget` does not exist.

- [ ] **Step 3: Implement byte-conservative reservations under one async lock**

Use these immutable records and formulas:

```python
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class BudgetReservation:
    request_id: str
    maximum_cost_usd: Decimal


@dataclass(frozen=True)
class BudgetSnapshot:
    cap_usd: Decimal
    spent_usd: Decimal
    reserved_usd: Decimal
    remaining_usd: Decimal
    unresolved_request_ids: tuple[str, ...]


def conservative_request_cost(
    messages: tuple[ChatMessage, ...], config: LargeLLMConfig
) -> Decimal:
    prompt_bytes = sum(len(message.content.encode("utf-8")) for message in messages)
    prompt = Decimal(prompt_bytes) * config.provider.prompt_price_per_million_usd / MILLION
    output = Decimal(config.max_tokens) * config.provider.completion_price_per_million_usd / MILLION
    return prompt + output
```

`BudgetLedger` keeps reservations in a dictionary keyed by request ID and protects every read/write with one `asyncio.Lock`. Reject duplicate IDs, foreign/already-finalized reservations, negative or non-finite authoritative costs, and actual cost above the reserved ceiling. On an over-ceiling response, add the actual amount to spent, clear the reservation, set a permanent `pricing_violation` stop reason, and reject every later reservation. `hold` leaves the full amount reserved and records the reason. Every snapshot sorts unresolved IDs.

- [ ] **Step 4: Run focused tests including cancellation/duplicate edge cases**

Add tests that cancel a waiter without corrupting state, reject duplicate request IDs, reject reconciliation twice, and assert `spent + reserved <= cap` for accepted prices.

Run: `uv run python -m pytest tests/unit/test_b45_budget.py tests/unit/test_b45_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the budget ledger**

```bash
git add src/nl2sparql/models/b45/budget.py src/nl2sparql/models/b45/__init__.py tests/unit/test_b45_budget.py
git commit -m "feat(baselines): cap concurrent OpenRouter cost"
```

---

### Task 3: B4/B5 prompt orchestration over an async transport

**Files:**
- Create: `src/nl2sparql/models/b45/transport.py`
- Create: `src/nl2sparql/models/b45/baseline.py`
- Create: `src/nl2sparql/models/b4_zero_shot.py`
- Create: `src/nl2sparql/models/b5_few_shot.py`
- Create: `tests/unit/test_b45_baseline.py`
- Modify: `src/nl2sparql/models/b45/__init__.py`

**Interfaces:**
- Consumes: `build_messages`, `prompt_sha256`, `extract_google_sql`, `CatalogSummary`, `SelectedExample`, `LargeLLMConfig`, `RemoteCompletion`, and a B2-compatible retriever.
- Produces: `CompletionTransport.complete(messages, config, request_id) -> RemoteCompletion`, `BaselineB4.predict[_detailed]`, and `BaselineB5.predict[_detailed]`.

- [ ] **Step 1: Write failing public-interface tests for parity and fail-closed SQL**

```python
import asyncio
import hashlib
from decimal import Decimal

from nl2sparql.models.b12 import CatalogSummary, SelectedExample
from nl2sparql.models.b45 import BaselineB4, BaselineB5, LargeLLMConfig, ProviderPolicy
from nl2sparql.models.b45.contracts import RemoteCompletion

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


class ScriptedTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = []

    async def complete(self, messages, config, *, request_id):
        self.calls.append((messages, config, request_id))
        return RemoteCompletion.synthetic(
            raw_text=self.text,
            model_id=config.model_id,
            provider_slug="scripted",
            input_tokens=12,
            output_tokens=7,
            charged_cost_usd=Decimal("0"),
            latency_ms=2.0,
        )


def summary() -> CatalogSummary:
    text = "GoogleSQL catalog\n"
    return CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def test_b4_returns_safe_sql_and_keeps_synthetic_marker() -> None:
    async def scenario() -> None:
        backend = ScriptedTransport(SAFE_SQL)
        baseline = BaselineB4(summary(), LargeLLMConfig(provider=policy()), backend)
        prediction = await baseline.predict_detailed("List labels", request_id="case-1")
        assert prediction.sql == SAFE_SQL
        assert prediction.baseline == "b4"
        assert prediction.completion.synthetic_backend is True
        assert "Examples:" not in backend.calls[0][0][1].content

    asyncio.run(scenario())


def test_b5_is_identical_except_for_exactly_five_examples() -> None:
    async def scenario() -> None:
        retriever = ScriptedRetriever(five_examples())
        backend = ScriptedTransport("Here is SQL: " + SAFE_SQL)
        baseline = BaselineB5(
            summary(), LargeLLMConfig(provider=policy()), backend, retriever
        )
        prediction = await baseline.predict_detailed(
            "List labels", request_id="case-1", target_id="case-1"
        )
        assert prediction.sql is None
        assert prediction.extraction_status == "prose"
        assert len(prediction.selected_examples) == 5
        assert [item.record_id for item in prediction.selected_examples] == [
            "train-1", "train-2", "train-3", "train-4", "train-5"
        ]

    asyncio.run(scenario())
```

In the test file, define `policy()` exactly as Task 1, `five_examples()` as five valid `SelectedExample` records with stable IDs and scores, and `ScriptedRetriever` with `training_sha256`, `encoder_id`, `encoder_revision`, `training_accepted=True`, and `retrieve` returning those examples.

- [ ] **Step 2: Run the baseline tests and verify missing interfaces**

Run: `uv run python -m pytest tests/unit/test_b45_baseline.py -q`

Expected: FAIL importing `BaselineB4` and `BaselineB5`.

- [ ] **Step 3: Implement the transport protocol and baseline orchestration**

Define the protocol:

```python
class CompletionTransport(Protocol):
    """Complete one ordered chat prompt through a local or remote adapter."""

    async def complete(
        self,
        messages: tuple[ChatMessage, ...],
        config: LargeLLMConfig,
        *,
        request_id: str,
    ) -> RemoteCompletion:
        """Return validated response and accounting evidence."""
```

Implement a private `_predict` that validates question/request ID, calls
`build_messages(question, summary, examples=examples)`, measures end-to-end
monotonic latency, awaits the transport, validates returned model identity,
calls `extract_google_sql`, and builds `LargeLLMPrediction`. Convert unexpected
adapter exceptions to `LargeLLMError` without including secrets or full prompts.

Public signatures are `BaselineB4.predict(question: str, *, request_id: str) ->
str | None`, `BaselineB4.predict_detailed(question: str, *, request_id: str) ->
LargeLLMPrediction`, `BaselineB5.predict(question: str, *, request_id: str,
target_id: str | None = None) -> str | None`, and
`BaselineB5.predict_detailed(question: str, *, request_id: str, target_id: str |
None = None) -> LargeLLMPrediction`. Each method is asynchronous and `predict`
returns the `.sql` value from `predict_detailed`.

Compatibility files only import and export the corresponding class. Add an
AST/import-guard test that `b45` does not import `nl2sparql.linking` and that
`b4_zero_shot.py`/`b5_few_shot.py` contain no parallel implementation.

- [ ] **Step 4: Run B4/B5 and reused prompt/extraction tests**

Run: `uv run python -m pytest tests/unit/test_b45_baseline.py tests/unit/test_b12_prompts.py tests/unit/test_b12_baseline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit baseline behavior**

```bash
git add src/nl2sparql/models/b45 src/nl2sparql/models/b4_zero_shot.py src/nl2sparql/models/b5_few_shot.py tests/unit/test_b45_baseline.py
git commit -m "feat(baselines): predict GoogleSQL with B4 and B5"
```

---

### Task 4: Lazy OpenRouter adapter with typed retries and usage validation

**Files:**
- Create: `src/nl2sparql/models/b45/openrouter.py`
- Create: `tests/unit/test_b45_openrouter.py`

**Interfaces:**
- Consumes: `BudgetLedger`, `LargeLLMConfig`, `ChatMessage`, and private live completion factory.
- Produces: `OpenRouterTransport.from_env(config: LargeLLMConfig, ledger: BudgetLedger) -> OpenRouterTransport`, `OpenRouterTransport.complete(messages: tuple[ChatMessage, ...], config: LargeLLMConfig, *, request_id: str) -> RemoteCompletion`, `OpenRouterRequestError`, `RetryPolicy`, and `validate_model_metadata(raw: object, config: LargeLLMConfig) -> ModelMetadataEvidence`.

- [ ] **Step 1: Write failing tests for payload, retry matrix, and live evidence**

```python
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45 import LargeLLMConfig, ProviderPolicy
from nl2sparql.models.b45.budget import BudgetLedger
from nl2sparql.models.b45.openrouter import OpenRouterTransport

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


async def no_wait(delay: float) -> None:
    assert 0.0 <= delay <= 30.0


def make_config() -> LargeLLMConfig:
    return LargeLLMConfig(
        provider=ProviderPolicy(
            provider_slug="deepinfra",
            prompt_price_per_million_usd=Decimal("0.50"),
            completion_price_per_million_usd=Decimal("1.00"),
        ),
        max_cost_usd=Decimal("1.00"),
    )


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(cost="0.0002"):
    return SimpleNamespace(
        id="gen-1",
        model="meta-llama/llama-3.3-70b-instruct",
        provider="deepinfra",
        system_fingerprint="fp-1",
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=SAFE_SQL),
        )],
        usage=SimpleNamespace(
            prompt_tokens=20,
            completion_tokens=10,
            cost=cost,
            cost_details=SimpleNamespace(upstream_inference_cost="0.00018"),
        ),
    )


def test_request_pins_model_provider_and_generation_parameters() -> None:
    async def scenario() -> None:
        config = make_config()
        completions = FakeCompletions([response()])
        sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        transport = OpenRouterTransport(
            sdk=sdk,
            ledger=BudgetLedger(config),
            sleep=lambda delay: no_wait(delay),
            clock_ns=iter([0, 2_000_000]).__next__,
        )
        result = await transport.complete(
            (ChatMessage("user", "List labels"),), config, request_id="case-1"
        )
        request = completions.requests[0]
        assert request["model"] == config.model_id
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
        assert result.synthetic_backend is False
        assert result.charged_cost_usd == Decimal("0.0002")

    asyncio.run(scenario())
```

Add parameterized cases using SDK exception doubles with `status_code` for 408,
409, 429, 500, 502, 503, and 504; assert a later success uses two attempts. Add
401, 402, 403, 404, 413, and 422 cases that assert one attempt. Add tests for a
bounded `Retry-After`, malformed usage cost, two choices, empty content,
unexpected provider/model, non-`stop`/`length` finish reasons, held reservation
after ambiguous cost, and errors that never contain `OPENROUTER_API_KEY`.

- [ ] **Step 2: Run adapter tests and verify the missing adapter failure**

Run: `uv run python -m pytest tests/unit/test_b45_openrouter.py -q`

Expected: FAIL because `b45.openrouter` does not exist.

- [ ] **Step 3: Implement a lazy injected SDK adapter**

The constructor takes an SDK-like object, ledger, injected async sleep, clock,
and deterministic jitter function. `from_env` imports `AsyncOpenAI` inside the
method, reads the key once, and constructs the client with
`base_url="https://openrouter.ai/api/v1"`, `timeout=float(config.timeout_seconds)`,
and SDK retries disabled.

Build the request exactly as asserted above plus
`extra_headers={"X-OpenRouter-Metadata": "enabled", "HTTP-Referer":
"https://github.com/vovi102/luanvan", "X-Title": "NL2SQL-Thesis"}`. Convert
ordered `ChatMessage` objects to dictionaries without logging their content.

Before attempt one, reserve through the ledger. Retry only transient exceptions.
Delay is `min(30.0, retry_after or 2 ** (attempt - 1) + jitter(attempt))` and all
injected values must be finite/non-negative. On success, validate exactly one
choice, text content, accepted finish reason (`stop` or `length`), token counts,
model/provider identity, and authoritative decimal cost; then reconcile the
ledger and issue a private live completion. On an exhausted or non-retryable
error with no authoritative generation cost, hold the reservation.

Implement `validate_model_metadata` to require the configured model ID, provider
endpoint, `seed`, `temperature`, and `max_tokens` support, prices at or below the
policy ceilings, and a context window large enough for prompt bytes plus 512.
Return an immutable `ModelMetadataEvidence` carrying a canonical metadata SHA.

- [ ] **Step 4: Prove no live network is reachable from local test paths**

Add an autouse test fixture that monkeypatches `socket.socket.connect` to raise
`AssertionError("network forbidden in local tests")`. Test `from_env` with a
missing key before allowing any SDK construction, then run:

Run: `uv run python -m pytest tests/unit/test_b45_openrouter.py tests/unit/test_b45_budget.py -q`

Expected: PASS with no real sleeps or sockets.

- [ ] **Step 5: Commit the production adapter**

```bash
git add src/nl2sparql/models/b45/openrouter.py tests/unit/test_b45_openrouter.py
git commit -m "feat(baselines): add budgeted OpenRouter transport"
```

---

### Task 5: Ordered async evaluation, blockers, and reproducibility

**Files:**
- Create: `src/nl2sparql/models/b45/evaluate.py`
- Create: `tests/unit/test_b45_evaluate.py`
- Modify: `src/nl2sparql/models/b45/__init__.py`

**Interfaces:**
- Consumes: B1/B2 `EvaluationCase` and `load_evaluation_cases`, B4/B5 public interfaces, `BudgetLedger.snapshot`, and remote prediction contracts.
- Produces: `OutcomeJournal`, `EvaluationOutcome`, `LargeEvaluationMetrics`, `LargeEvaluationRun`, `evaluate_large_baseline(cases, baseline, *, run_id, concurrency, model_metadata, journal=None, completed_outcomes=()) -> LargeEvaluationRun`, and `compare_large_reproducibility(runs) -> ReproducibilityReport`.

- [ ] **Step 1: Write failing tests for bounded concurrency and ordered outcomes**

```python
import asyncio

from nl2sparql.models.b45.evaluate import (
    compare_large_reproducibility,
    evaluate_large_baseline,
)


def test_evaluation_preserves_case_order_under_concurrency() -> None:
    async def scenario() -> None:
        baseline = DelayedBaseline(delays={"case-1": 0.02, "case-2": 0.0})
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            baseline,
            run_id="run-1",
            concurrency=2,
            model_metadata=None,
        )
        assert [item.case_id for item in run.outcomes] == ["case-1", "case-2"]
        assert baseline.max_in_flight == 2
        assert run.scientific_ready is False
        assert "synthetic_backend" in run.blockers
        assert "synthetic_test_set" in run.blockers

    asyncio.run(scenario())


def test_request_failure_is_an_outcome_not_a_lost_case() -> None:
    async def scenario() -> None:
        run = await evaluate_large_baseline(
            two_synthetic_cases(),
            FailingSecondBaseline(),
            run_id="run-1",
            concurrency=2,
            model_metadata=None,
        )
        assert len(run.outcomes) == 2
        assert run.outcomes[1].status == "request_failed"
        assert run.metrics.request_failed == 1
        assert "incomplete_generation" in run.blockers

    asyncio.run(scenario())


def test_three_run_report_measures_raw_and_normalized_sql_agreement() -> None:
    report = compare_large_reproducibility(
        (run_with_sql("run-1", "SELECT  address FROM `p.d.t`"),
         run_with_sql("run-2", "select address from `p.d.t`"),
         run_with_sql("run-3", "SELECT address FROM `p.d.t`"))
    )
    assert report.run_count == 3
    assert report.normalized_sql_agreement == 1.0
    assert report.raw_output_agreement < 1.0
```

- [ ] **Step 2: Run evaluation tests and verify they fail**

Run: `uv run python -m pytest tests/unit/test_b45_evaluate.py -q`

Expected: FAIL because `b45.evaluate` does not exist.

- [ ] **Step 3: Implement evaluator records and worker orchestration**

Use these public records:

```python
OutcomeStatus = Literal[
    "completed", "extraction_failed", "request_failed", "budget_blocked", "cost_unresolved"
]


@dataclass(frozen=True)
class EvaluationOutcome:
    case_id: str
    gold_sql: str
    difficulty: Literal["easy", "medium", "hard"]
    categories: tuple[str, ...]
    status: OutcomeStatus
    prediction: LargeLLMPrediction | None
    safe_error_code: str | None


@dataclass(frozen=True)
class LargeEvaluationRun:
    run_id: str
    baseline: Literal["b4", "b5"]
    outcomes: tuple[EvaluationOutcome, ...]
    metrics: LargeEvaluationMetrics
    scientific_ready: bool
    blockers: tuple[str, ...]
    seed: int
    generated_at_utc: str
    input_sha256: str | None
    config_sha256: str
    budget: BudgetSnapshot
```

In the test file, define `two_synthetic_cases()` by constructing two B1/B2
`EvaluationCase` objects whose IDs are `case-1` and `case-2`; define
`DelayedBaseline.predict_detailed` to track in-flight calls, await the configured
delay, and return a Task 1 synthetic `LargeLLMPrediction`; define
`FailingSecondBaseline` to return that prediction for `case-1` and raise a typed
`OpenRouterRequestError(code="rate_limit_exhausted")` for `case-2`; and define
`run_with_sql` by constructing a one-outcome `LargeEvaluationRun` with the same
input/config/model/provider fingerprints for all three calls. These factories
must use real Task 1 and Task 5 records, not dictionaries or mocks that bypass
contract validation.

Define `OutcomeJournal` as a protocol with
`append(outcome: EvaluationOutcome) -> None`. Validate unique ordered cases,
validate that every supplied completed outcome matches one source case exactly,
and require `concurrency == config.concurrency`. Spawn one
task per case behind `asyncio.Semaphore(concurrency)`, collect `(source_index,
outcome)`, sort by source index, and never expose exception text in artifacts;
map typed exceptions to stable safe error codes. Propagate cancellation after
cancelling/gathering outstanding tasks. Do not schedule case IDs already present
in `completed_outcomes`. Call `journal.append(outcome)` immediately after each
new outcome is validated; a journal failure cancels outstanding work and fails
the run rather than continuing without durable evidence.

Metrics include total/completed/extraction-failed/request-failed/budget-blocked/
cost-unresolved counts, p50/p95 latency, input/output tokens, charged cost,
cost-per-1k, and sorted counts by extraction status, difficulty, and category.
Accept `model_metadata: ModelMetadataEvidence | None` and derive blockers from
evidence, including synthetic backend/test/training,
untrusted test/training source, expected 100 cases, incomplete generation,
unresolved cost, pricing violation, cost over cap, missing model metadata,
non-three-run evidence, and provider/model drift. No caller boolean can remove a
blocker.

`compare_large_reproducibility` requires exactly three distinct run IDs with
identical baseline, ordered case IDs, input/config/catalog/training fingerprints,
model, and provider. Compute all three pairwise per-case agreements for raw text
and normalized safe SQL; a missing/failed prediction counts as disagreement
unless both runs have the same failure status.

- [ ] **Step 4: Run evaluator and B4/B5 tests**

Run: `uv run python -m pytest tests/unit/test_b45_evaluate.py tests/unit/test_b45_baseline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit evaluation behavior**

```bash
git add src/nl2sparql/models/b45/evaluate.py src/nl2sparql/models/b45/__init__.py tests/unit/test_b45_evaluate.py
git commit -m "feat(baselines): evaluate B4 B5 runs offline"
```

---

### Task 6: Atomic artifacts and resumable publication

**Files:**
- Create: `src/nl2sparql/models/b45/artifacts.py`
- Create: `tests/unit/test_b45_artifacts.py`
- Modify: `src/nl2sparql/models/b45/__init__.py`

**Interfaces:**
- Consumes: `LargeEvaluationRun`, `ReproducibilityReport`, exact input/config fingerprints.
- Produces: `RequestJournal.append(outcome) -> None`, `load_resume_state(request_log, *, expected_input_sha256, expected_config_sha256, expected_run_id) -> ResumeState`, `publish_large_run(run, *, paths, protected_paths=()) -> None`, `summarize_large_runs(runs) -> dict[str, object]`, and deterministic JSONL/CSV serializers.

- [ ] **Step 1: Write failing tests for report-last rollback and stale resume rejection**

```python
from pathlib import Path

import pytest

import nl2sparql.models.b45.artifacts as artifacts
from nl2sparql.models.b45 import LargeLLMError


def test_publication_writes_report_last_and_rolls_back_every_output(
    tmp_path: Path, monkeypatch
) -> None:
    paths = artifact_paths(tmp_path)
    for path in paths.all_outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old\n")
    original = artifacts._atomic_write

    def fail_report(path, payload):
        if path == paths.report:
            raise OSError("disk full")
        return original(path, payload)

    monkeypatch.setattr(artifacts, "_atomic_write", fail_report)
    with pytest.raises(LargeLLMError, match="unable to publish"):
        artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    assert all(path.read_bytes() == b"old\n" for path in paths.all_outputs)


def test_resume_rejects_changed_configuration(tmp_path: Path) -> None:
    paths = artifact_paths(tmp_path)
    artifacts.publish_large_run(complete_synthetic_run(), paths=paths)
    with pytest.raises(LargeLLMError, match="config fingerprint"):
        artifacts.load_resume_state(
            paths.request_log,
            expected_input_sha256="a" * 64,
            expected_config_sha256="b" * 64,
            expected_run_id="run-1",
        )


def test_outputs_cannot_alias_inputs_or_each_other(tmp_path: Path) -> None:
    source = tmp_path / "test.jsonl"
    source.write_text("{}\n")
    paths = artifact_paths(tmp_path, predictions=source)
    with pytest.raises(LargeLLMError, match="alias"):
        artifacts.publish_large_run(
            complete_synthetic_run(), paths=paths, protected_paths=(source,)
        )
```

- [ ] **Step 2: Run artifact tests and verify they fail**

Run: `uv run python -m pytest tests/unit/test_b45_artifacts.py -q`

Expected: FAIL because `b45.artifacts` does not exist.

- [ ] **Step 3: Implement deterministic serializers and safe publication**

Define:

```python
@dataclass(frozen=True)
class ArtifactPaths:
    predictions: Path
    request_log: Path
    cost_csv: Path
    report: Path

    @property
    def all_outputs(self) -> tuple[Path, Path, Path, Path]:
        """Return outputs in publication order, with the report last."""
        return (self.predictions, self.request_log, self.cost_csv, self.report)


@dataclass(frozen=True)
class ResumeState:
    completed_case_ids: tuple[str, ...]
    prior_cost_usd: Decimal
    prior_records: tuple[dict[str, object], ...]
```

Follow the existing T5.2 hardened path checks: compare resolved paths and
`os.path.samefile`, reject symlinks/non-regular files/multiple hard links, write
with `mkstemp` in the destination directory, `fsync`, `os.replace`, and directory
`fsync`. Capture prior bytes for all four outputs and restore all of them if any
write fails. Write predictions first, request log second, derived cost CSV
third, and report last.

JSON uses sorted compact keys plus a trailing newline. Decimal costs remain
strings. Request logs contain no API key, authorization header, or full prompt;
they include prompt SHA instead. The report includes a SHA over its body,
readiness/blockers, outcome counts, authoritative total cost, provider/model
identity, and input/config fingerprints.

Resume parsing validates every line before returning anything, rejects duplicate
case IDs, requires exact run/input/config/catalog/training/model/provider
identity, and reconstructs spent/unresolved budget from authoritative records.
Never append to a mismatched file.

Add `RequestJournal` with a validated fixed header carrying run/input/config/
catalog/training/model/provider fingerprints. `append` serializes one completed
outcome to a temporary replacement containing the prior accepted bytes plus the
new row, then flushes, fsyncs, atomically replaces, and fsyncs the directory.
The evaluator calls this injected append seam immediately after each case
finishes; local unit tests may use an in-memory journal. A crash can therefore
lose an in-flight request but cannot corrupt or silently duplicate an accepted
record. Add a test that interrupts after case one, reloads `ResumeState`, and
proves the resumed evaluator schedules only case two.

- [ ] **Step 4: Run artifact and existing T5.2 rollback tests**

Run: `uv run python -m pytest tests/unit/test_b45_artifacts.py tests/unit/test_b12_artifacts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit artifact publication**

```bash
git add src/nl2sparql/models/b45/artifacts.py src/nl2sparql/models/b45/__init__.py tests/unit/test_b45_artifacts.py
git commit -m "feat(baselines): publish resumable B4 B5 evidence"
```

---

### Task 7: Offline-first CLI and live preflight ordering

**Files:**
- Create: `scripts/large_llm_baselines_workflow.py`
- Create: `scripts/18_large_llm_baselines.py`
- Create: `tests/unit/test_b45_workflow.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: all public B4/B5 contracts, evaluator, artifact publisher, B1/B2 catalog/retriever/evaluation loaders, and a lazily imported OpenRouter transport.
- Produces: Click commands `validate`, `predict`, `evaluate`, and `summarize`; `load_openrouter_transport`, `load_model_metadata`, and `build_large_baseline` seams for local tests.

- [ ] **Step 1: Write failing tests for help, opt-in, key, and path preflight**

```python
import json
import subprocess
import sys

from click.testing import CliRunner

import scripts.large_llm_baselines_workflow as workflow


def test_help_does_not_import_openai_or_open_a_socket() -> None:
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


def test_predict_requires_network_opt_in_before_key_or_client(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )
    result = CliRunner().invoke(
        workflow.cli,
        ["predict", "--baseline", "b4", "--question", "List labels"],
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "network access requires --allow-network"


def test_output_alias_is_rejected_before_network_loader(tmp_path, monkeypatch) -> None:
    test_set = tmp_path / "test.jsonl"
    test_set.write_text("{}\n")
    monkeypatch.setattr(
        workflow,
        "load_openrouter_transport",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )
    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate", "--baseline", "b4", "--test-set", str(test_set),
            "--predictions", str(test_set), "--run-id", "run-1",
            "--provider", "deepinfra", "--max-cost-usd", "20",
            "--allow-network",
        ],
    )
    assert result.exit_code == 2
    assert "alias" in json.loads(result.output)["error"]
```

Add tests proving `validate` works without key/OpenAI imports, B5 validates
training/cache before loading the sentence encoder or OpenRouter, missing key is
reported only after local inputs pass, config above USD 20 fails, metadata drift
blocks client construction, an injected synthetic transport can exercise the
workflow but yields `scientific_ready=false`, and `summarize` never loads a
client.

- [ ] **Step 2: Run CLI tests and verify the missing workflow failure**

Run: `uv run python -m pytest tests/unit/test_b45_workflow.py -q`

Expected: FAIL importing `scripts.large_llm_baselines_workflow`.

- [ ] **Step 3: Implement commands and strict preflight sequence**

Use defaults:

```python
DEFAULT_TEST_SET = Path("data/eval/test-100.jsonl")
DEFAULT_TRAINING_SET = Path("data/dataset/final/train.jsonl")
DEFAULT_CACHE = Path("data/eval/cache/b5-few-shot.npz")
DEFAULT_B4_PREDICTIONS = Path("data/eval/predictions/b4_test.jsonl")
DEFAULT_B5_PREDICTIONS = Path("data/eval/predictions/b5_test.jsonl")
DEFAULT_B4_LOG = Path("data/eval/logs/b4_openrouter.jsonl")
DEFAULT_B5_LOG = Path("data/eval/logs/b5_openrouter.jsonl")
DEFAULT_COST_LOG = Path("data/eval/logs/openrouter_cost.csv")
DEFAULT_B4_REPORT = Path("reports/b4_inference.json")
DEFAULT_B5_REPORT = Path("reports/b5_inference.json")
```

Every command emits one compact JSON object. Validation order for `predict` and
`evaluate` is: primitive CLI values; question or test snapshot; catalog; B5
training/cache and accepted fingerprint; config/budget; output/protected paths;
`--allow-network`; API key presence; live model metadata and its accepted SHA;
sentence encoder if B5 needs cache rebuild; OpenRouter transport; execution.

`evaluate` requires `--run-id`, `--provider`, `--max-cost-usd`,
`--accepted-model-metadata-sha256`, and `--allow-network`. Resume is opt-in with
`--resume` and must load matching request evidence before any new request.
`predict` never writes scientific artifacts. `summarize` accepts exactly three
report/run sets and uses only local files.

The numbered wrapper contains only:

```python
#!/usr/bin/env python
"""Numbered entry point for T5.3 B4/B5 GoogleSQL workflows."""

from large_llm_baselines_workflow import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Ensure `.env.example` contains `OPENROUTER_API_KEY=` with no sample secret.

- [ ] **Step 4: Run CLI subprocess and complete focused suite**

Run: `uv run python scripts/18_large_llm_baselines.py --help`

Expected: lists `validate`, `predict`, `evaluate`, and `summarize` without
requiring a key.

Run: `uv run python -m pytest tests/unit/test_b45_contracts.py tests/unit/test_b45_budget.py tests/unit/test_b45_baseline.py tests/unit/test_b45_openrouter.py tests/unit/test_b45_evaluate.py tests/unit/test_b45_artifacts.py tests/unit/test_b45_workflow.py -q`

Expected: PASS and no network attempt.

- [ ] **Step 5: Commit the offline workflow**

```bash
git add scripts/large_llm_baselines_workflow.py scripts/18_large_llm_baselines.py tests/unit/test_b45_workflow.py .env.example
git commit -m "feat(baselines): add B4 B5 offline workflow"
```

---

### Task 8: Migrate task documentation and record the local acceptance boundary

**Files:**
- Modify: `docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: final implemented CLI names, artifact schemas, blockers, and verification evidence.
- Produces: an accurate GoogleSQL T5.3 task, reproducible operator commands, and a dated architectural decision.

- [ ] **Step 1: Write a documentation assertion test before changing docs**

Add to `tests/unit/test_b45_workflow.py`:

```python
def test_task_document_matches_google_sql_acceptance_boundary() -> None:
    text = Path("docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md").read_text()
    assert "GoogleSQL" in text
    assert "meta-llama/llama-3.3-70b-instruct" in text
    assert "local implementation complete" in text
    assert "scientific acceptance pending" in text
    assert "SPARQL extraction" not in text
```

- [ ] **Step 2: Run the documentation test and verify legacy wording fails**

Run: `uv run python -m pytest tests/unit/test_b45_workflow.py::test_task_document_matches_google_sql_acceptance_boundary -q`

Expected: FAIL because the current task still describes SPARQL and has status `todo`.

- [ ] **Step 3: Rewrite T5.3 around the implemented GoogleSQL workflow**

Document B4/B5 definitions, exact model slug, B1/B2 prompt/retrieval reuse,
OpenRouter request policy, retryable statuses, USD 20 reservation behavior,
privacy boundary, artifact fields, commands, local verification, and external
scientific gates. Mark the status with these exact lines:

```text
local implementation complete
scientific acceptance pending
```

Do not include prices as timeless facts; identify values as run-policy ceilings
and require live metadata evidence. Add a README command showing local
`validate` and a clearly labeled live command that is never run automatically.

Append a 2026-09-07 decision-log entry: T5.3 uses a separate B4/B5 remote module,
Llama 3.3 70B, one pinned provider without fallback, shared B1/B2 GoogleSQL
prompt/extraction, conservative budget reservations, and separate local versus
scientific readiness.

- [ ] **Step 4: Run docs assertion and inspect all changed Markdown**

Run: `uv run python -m pytest tests/unit/test_b45_workflow.py::test_task_document_matches_google_sql_acceptance_boundary -q`

Expected: PASS.

Run: `rg -n "SPARQL|todo|OPENROUTER_API_KEY=.+" docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md README.md .env.example`

Expected: no legacy SPARQL target, stale `todo` status, or committed secret.

- [ ] **Step 5: Commit the migration and decision record**

```bash
git add docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md docs/memory/05-DECISION_LOG.md README.md tests/unit/test_b45_workflow.py
git commit -m "docs(baselines): migrate T5.3 to GoogleSQL"
```

---

### Task 9: Full verification, two-axis review, and closure evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-09-07-t5-3-google-sql-large-llm.md`
- Modify: `docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md` only if review finds a documentation gap
- Modify: implementation/tests only for concrete review findings

**Interfaces:**
- Consumes: the complete T5.3 branch and its approved design.
- Produces: passing repository evidence, resolved Spec/Standards review findings, and checked plan boxes.

- [ ] **Step 1: Run the complete focused suite from a fresh process**

Run:

```bash
uv run python -m pytest \
  tests/unit/test_b45_contracts.py \
  tests/unit/test_b45_budget.py \
  tests/unit/test_b45_baseline.py \
  tests/unit/test_b45_openrouter.py \
  tests/unit/test_b45_evaluate.py \
  tests/unit/test_b45_artifacts.py \
  tests/unit/test_b45_workflow.py -q
```

Expected: PASS with no skipped tests and no network traffic.

- [ ] **Step 2: Run full repository verification**

Run:

```bash
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/18_large_llm_baselines.py --help
uv run python scripts/18_large_llm_baselines.py validate --baseline b4 --provider deepinfra --max-cost-usd 20
git diff --check
git status --short
```

Expected: all tests pass; Ruff reports no issues or formatting changes; CLI help
and offline validation succeed without a key; diff check is empty; only intended
tracked changes remain.

- [ ] **Step 3: Request independent Spec and Standards review**

Use the `superpowers:requesting-code-review` skill followed by the repository
`code-review` skill against base commit `3b34ac48c86a7b02799a953062e162502470a8d2`.
The Spec review checks the approved design and T5.3 task; the Standards review
checks `docs/memory/04-CONVENTIONS.md`, safety, secrets, async cancellation,
money precision, and local no-network behavior.

Expected: both reviewers return no Critical or Important findings. If they do,
use `superpowers:receiving-code-review`, reproduce each finding, fix it with a
failing regression test, rerun focused/full verification, and request a recheck.

- [ ] **Step 4: Record exact verification and review evidence**

Update the task document with the final test count, Ruff results, CLI checks,
review commit SHA, and remaining scientific blockers. Check every completed box
in this plan. Do not mark live runs, cost, latency, or reproducibility complete
unless genuine OpenRouter artifacts exist.

- [ ] **Step 5: Commit closure documentation**

```bash
git add docs/superpowers/plans/2026-09-07-t5-3-google-sql-large-llm.md docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md
git commit -m "docs(baselines): close T5.3 local implementation"
```

- [ ] **Step 6: Re-run completion verification at final HEAD**

Run:

```bash
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
git diff --check
git status --short --branch
git log --oneline --decorate -12
```

Expected: full suite and lint/format pass at the exact final commit; worktree is
clean on `feat/t5-3-google-sql-large-llm`; no scientific result is claimed.
