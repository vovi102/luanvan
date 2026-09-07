# T5.3 GoogleSQL Large-LLM Baselines Design

**Date:** 2026-09-07  
**Status:** approved by the user on 2026-09-07  
**Scope:** migrate B4/B5 from NL-to-SPARQL to reproducible, budget-bounded
NL-to-GoogleSQL baselines backed by OpenRouter. Local development must not send
requests or incur API cost.

## Context

Pivot #1 made read-only GoogleSQL over the managed BigQuery analytical catalog
the canonical target. The legacy T5.3 task still describes ontology prompts,
SPARQL extraction, and the retired Llama 3 70B identifier. T5.3 must instead be
comparable with the accepted B1/B2 GoogleSQL baselines: B4 is raw zero-shot and
B5 differs only by the same five-example block used by B2.

T5.3 has two completion boundaries. Local completion covers contracts, request
construction, fake-transport execution, retry policy, cost reservations,
fail-closed GoogleSQL extraction, artifact publication, CLI preflight, and tests.
Scientific acceptance requires an explicit later opt-in with an OpenRouter key,
the finalized T3.5 test set, account funds, and human approval to spend money.
No local test or default command may contact OpenRouter.

## Decision

Add a focused `nl2sparql.models.b45` module rather than adding remote-provider
concerns to `b12` or refactoring all model baselines behind a new generic
framework. B4/B5 reuse the already accepted B1/B2 catalog, prompt, retrieval,
and GoogleSQL extraction contracts. The new module owns only behavior that is
specific to remote large-model inference: OpenRouter requests, provider
provenance, retryability, cost accounting, concurrency, and run publication.

The public prediction interfaces are asynchronous because the scientific run
requires bounded concurrency without blocking worker threads:

```python
await BaselineB4.predict(question) -> str | None
await BaselineB4.predict_detailed(question) -> LargeLLMPrediction

await BaselineB5.predict(question) -> str | None
await BaselineB5.predict_detailed(question) -> LargeLLMPrediction
```

Construction accepts an injected completion transport. Production uses the
OpenRouter adapter; tests use an in-memory scripted transport through the same
interface. A fake transport is permanently marked synthetic and its artifacts
cannot satisfy scientific readiness.

## Alternatives rejected

1. **Put OpenRouter directly in `b12`:** this couples local Transformers loading
   to remote billing, retries, and provider routing and weakens the current deep
   B1/B2 interface.
2. **Refactor B1-B5 into a new universal backend framework:** this creates a
   broad migration with no acceptance benefit for T5.3 and risks changing the
   already reviewed B1/B2 evidence contracts.
3. **Copy B1/B2 prompt and retrieval code into B4/B5:** this is initially easy
   but allows baseline prompts to drift and invalidates controlled comparison.

## Module layout

`src/nl2sparql/models/b45/` owns the implementation:

- `contracts.py` defines immutable run configuration, provider policy,
  completion, prediction, retry, cost, and readiness records.
- `transport.py` defines the narrow asynchronous completion protocol used by
  both scripted and live adapters.
- `openrouter.py` lazily constructs the OpenAI-compatible SDK client from the
  environment and translates responses/errors into internal contracts.
- `budget.py` owns concurrent pre-request reservations and post-request cost
  reconciliation.
- `baseline.py` orchestrates the shared B1/B2 prompt and extraction path for B4
  and B5.
- `evaluate.py` validates a snapshot, runs bounded workers, resumes safely, and
  publishes predictions, request logs, the cost ledger, and the run report.
- `__init__.py` exports only stable public interfaces and result contracts.

Task-named modules `models/b4_zero_shot.py` and `models/b5_few_shot.py` are
compatibility imports. Numbered wrapper `scripts/18_large_llm_baselines.py`
delegates to an importable workflow module.

## Model and provider identity

The canonical model is `meta-llama/llama-3.3-70b-instruct`, replacing the
legacy Llama 3 slug while retaining the intended 70B open-weight upper bound.
The versioned run configuration pins:

- the exact model slug;
- one explicit provider slug;
- `allow_fallbacks=false` and `require_parameters=true`;
- a provider `max_price` ceiling for prompt and completion tokens;
- `temperature=0`, `seed=42`, `max_tokens=512`, and one response;
- concurrency, timeout, retry count, and the total USD budget.

OpenRouter documents that provider routing otherwise load-balances or falls
back between endpoints. Pinning one provider prevents provider changes from
being mistaken for model variance. The live preflight queries OpenRouter's model
metadata only after explicit network opt-in and rejects a model/provider that
does not support all pinned parameters. The exact accepted metadata response is
fingerprinted and stored with the run.

The response must match the requested model. Every completion records the
generation ID, returned model, provider, system fingerprint when present,
finish reason, token counts, total charged cost, and upstream inference cost.
Missing provider identity or final cost makes the request operationally usable
only for diagnosis; it cannot be published as scientific evidence.

## Prompt parity and few-shot retrieval

B4 and B5 call `b12.prompts.build_messages`, use the same compiled catalog
summary, and pass their output through `b12.extraction.extract_google_sql`.
This guarantees the same instructions and managed-relation safety boundary as
B1/B2.

B4 passes no examples. B5 accepts an already validated B2 retriever and passes
exactly five immutable selected examples. It retains the B2 safeguards:
accepted training provenance, test/train non-aliasing, normalized-question and
ID leakage exclusion, deterministic ranking, pinned encoder identity, and
selected-example fingerprints. B4/B5 differ only in baseline ID and the B5
examples block; generation settings and remote model/provider are identical.

Linker or resolver output from T4.1-T4.3 is forbidden in both prompts so these
remain raw-model controls.

## OpenRouter request and error handling

The live adapter is lazy: imports and client construction occur only after
input, output-path, budget, model-policy, and explicit-opt-in validation. It
reads `OPENROUTER_API_KEY` from the environment and never serializes, logs, or
echoes the key. Request metadata headers identify the thesis project but contain
no secrets.

Only transient failures are retried: HTTP 408, 409, 429, 500, 502, 503, 504,
connection errors, and timeouts. Authentication, payment, malformed request,
unsupported parameter, moderation, and other client errors fail immediately.
Retries use deterministic attempt limits with exponential backoff plus injected
jitter and sleep functions so local tests do not wait. `Retry-After`, when valid
and bounded, takes precedence. Each attempt is logged without request headers or
full prompt text.

A successful HTTP response is still rejected if it has no single text choice,
invalid usage, an unexpected model/provider, an unapproved finish reason, or
ambiguous charged cost. The raw model text is retained before fail-closed SQL
extraction. The workflow never searches prose for a convenient query.

## Cost cap and concurrent reservations

The USD 20 limit is a hard workflow invariant, not a report-time warning. A
single async `BudgetLedger` serializes access with a lock. Before each request,
the worker reserves a conservative maximum charge computed from:

- UTF-8 byte length as an upper bound for prompt token count;
- configured `max_tokens=512` for output;
- accepted `max_price` prompt/completion ceilings;
- any configured per-request price ceiling.

If the available amount cannot cover the whole reservation, the case is marked
`budget_blocked` before network I/O. Concurrency therefore cannot collectively
oversubscribe the budget. After a response, the reservation is reconciled
against OpenRouter's returned `usage.cost`, which its usage-accounting
documentation defines as the total amount charged. A missing/invalid cost does
not release the reservation and stops new requests pending audit. If actual
cost exceeds the reserved ceiling, the run stops, records a provider-pricing
violation, and cannot be scientifically ready.

The live command also requires `--max-cost-usd` and `--allow-network` explicitly;
there is no network-enabled default. The configured cap must be positive and at
most USD 20. Retry attempts that fail before a completion may still have
provider-side cost, so the ledger keeps their reservation until authoritative
usage is available or the run is manually reconciled. This biases toward early
stopping rather than overspending.

## Workflow, resumption, and artifacts

Commands are:

```text
validate   validate catalog, evaluation/train snapshots, model policy, budget,
           and protected output paths without imports or network
predict    run one explicitly opted-in B4 or B5 request
evaluate   execute one baseline/run over an accepted evaluation snapshot
summarize  rebuild a report from already recorded artifacts without network
```

Scientific evaluation uses three distinct run IDs for each baseline. Within a
run, the evaluator keeps at most the configured number of requests in flight
and preserves output order by evaluation case ID. It writes one durable request
record after each completed case so interruption is resumable. Resume accepts
only artifacts whose input, prompt, catalog, model/provider, price, and run
configuration fingerprints match exactly; conflicts fail closed.

Default artifacts are:

- `data/eval/predictions/b4_test.jsonl` and `b5_test.jsonl`;
- `data/eval/logs/b4_openrouter.jsonl` and `b5_openrouter.jsonl`;
- `data/eval/logs/openrouter_cost.csv`;
- `reports/b4_inference.json` and `b5_inference.json`.

Publication is atomic and report-last. Output paths must not alias the catalog,
test/train inputs, model-policy file, existing B1/B2 evidence, locks, or each
other. A prediction binds case ID, baseline, run ID, question/input fingerprint,
raw output, safe SQL or failure status, prompt/config/catalog/training hashes,
selected examples, request/provider identity, token usage, charged cost,
attempts, monotonic latency, seed, and UTC timestamp.

`openrouter_cost.csv` is derived from immutable request records rather than
being an independent source of truth. It includes one row per request and total
rows per baseline/run. Reports distinguish completed, extraction-failed,
request-failed, budget-blocked, and unresolved-cost cases.

## Reproducibility and privacy

Each baseline is run three times over the same ordered test snapshot. T5.3
reports pairwise normalized-SQL agreement and raw-output agreement, but leaves
the final six-dimensional comparison to T5.4. Same seed and temperature do not
justify claiming determinism; the report records observed agreement only.

Questions and catalog context leave the device and may be processed by the
pinned provider. Live preflight requires an accepted dataset marker confirming
that the evaluation snapshot contains no secrets or personal data. Provider
routing uses `data_collection="deny"` when supported, but this is recorded as a
policy request rather than a guarantee of zero retention. Reports label B4/B5
as remote-processing baselines and retain no API credentials.

## Local and scientific readiness

The workflow emits separate readiness fields:

- `local_implementation_ready`: contracts, fake transport, validation, CLI,
  artifact checks, focused tests, full tests, and lint all pass.
- `scientific_ready`: finalized/reviewed T3.5 snapshot, accepted B5 training
  source, pinned supported model/provider metadata, three genuine complete runs,
  final cost under USD 20, no unresolved charges, and no synthetic records.

No caller-provided boolean alone can confer either status. Readiness is derived
from loader-issued provenance objects and validated artifacts. Synthetic
transport completions are marked at construction and cannot be relabeled.

## Testing

Implementation follows red-green-refactor and tests observable behavior through
the public interfaces:

- B4/B5 prompt parity and proof that B5 alone has exactly five examples;
- reuse of catalog/retrieval/extraction fingerprints and GoogleSQL safety;
- immutable config, model/provider identity, seed, price, and budget contracts;
- transient retry matrix, non-retryable failures, `Retry-After`, attempt limits,
  and secret-safe errors/logs;
- concurrent reservation safety, reconciliation, missing/over-ceiling cost,
  cancellation, and USD 20 maximum;
- response-shape, usage, finish-reason, provider, and model validation;
- latency/token/cost provenance and synthetic-evidence rejection;
- lazy imports, no-network defaults, missing key, explicit opt-in, and preflight
  ordering;
- atomic ordered publication, protected paths, interruption/resume, duplicate
  cases, stale fingerprints, and report-last failure;
- three-run reproducibility summaries without fabricated predictions;
- focused tests, `uv run python -m pytest -q`, Ruff check/format, CLI help,
  `git diff --check`, and branch review.

All local API behavior is exercised using injected SDK/transport doubles. Tests
must fail if any socket or real OpenRouter call is attempted.

## Acceptance boundary

T5.3 is locally complete when the migrated task document, `b45` module,
compatibility imports, offline-safe workflow, artifact contracts, tests,
documentation, and review pass. Local completion does not create or commit fake
research results.

Scientific acceptance remains pending until a later authorized live run has:

- a finalized independently reviewed T3.5 100-case test snapshot;
- an accepted B5 training snapshot and retrieval model;
- a verified OpenRouter account/key and explicit permission to spend;
- one pinned Llama 3.3 70B provider supporting the requested parameters;
- three complete genuine B4 and B5 runs;
- total authoritative OpenRouter cost at or below USD 20;
- complete latency, usage, cost, provider, and reproducibility evidence.

## External references checked

- [OpenRouter chat completion API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request)
  documents `seed`, response usage, metadata opt-in, and HTTP error classes.
- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
  documents response `usage.cost` as the charged total and the generation audit
  endpoint as an alternative.
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
  documents provider pinning, fallback control, parameter enforcement, data
  collection preferences, and maximum price filters.
- [Llama 3.3 70B on OpenRouter](https://openrouter.ai/meta-llama/llama-3.3-70b-instruct)
  confirms the canonical model slug. Pricing remains mutable and is therefore
  accepted at live preflight rather than hard-coded as scientific evidence.
