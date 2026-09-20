# T5.3 Gemini Free-Tier Baselines Design

**Date:** 2026-09-21  
**Status:** approved design; implementation pending  
**Scope:** make Gemini free tier the required hosted-model path for B4/B5 while
retaining Large Llama as an optional extension.

## Intent

T5.3 must provide a hosted-model comparison without making paid OpenRouter
inference or hardware capable of serving a 70B model part of the critical path.
The required experiment remains controlled at the prompting layer:

- B4 receives the question and compiled GoogleSQL catalog summary only.
- B5 uses the same model and generation policy plus exactly five accepted
  examples selected by the B2 retriever.
- Both use the existing whole-output GoogleSQL extraction and safety boundary.

Gemini free tier is the required provider path. Large Llama through OpenRouter
is retained as optional B4L/B5L evidence and does not affect T5.3 completion.

## Scientific claim

The primary comparison is between a small open-weight model executed locally
or on Kaggle and a hosted proprietary frontier model. It measures end-to-end
accuracy, latency, observed API charge, privacy policy, reproducibility and
failure modes under a shared test and prompting protocol.

The study must not attribute a difference to parameter count. Gemini and Llama
may differ in architecture, tokenizer, training corpus, alignment and serving
stack, and Gemini does not expose a parameter count suitable for a controlled
size claim. A same-family size analysis is permitted only if optional B4L/B5L
runs are later accepted.

## Baseline identities

| ID | Required model path | Prompt condition | Acceptance role |
|---|---|---|---|
| B4 | Pinned Gemini free-tier model | Zero-shot | Required |
| B5 | Same pinned Gemini model | Exactly five B2 examples | Required |
| B4L | Pinned Large Llama/OpenRouter | Zero-shot | Optional |
| B5L | Same pinned Large Llama model | Exactly five B2 examples | Optional |

Optional results must use distinct IDs and reports. They must never be merged
with Gemini runs or silently substituted for an incomplete Gemini run.

## Model pinning

The design does not guess a timeless Gemini model name. Before a scientific
run, an explicit preflight must:

1. query the account-visible model inventory without sending test questions;
2. require a stable text-generation model available on the free tier;
3. record its exact model ID, supported generation parameters and metadata;
4. require the operator to accept the metadata SHA-256; and
5. bind that ID and fingerprint into every request, checkpoint and report.

Preview aliases or an unversioned model alias cannot produce scientific-ready
evidence. If no suitable stable free-tier model exists, the run stops blocked;
it does not switch to paid tier or another model automatically.

## Architecture

The existing prompt, retrieval and SQL validation path remains provider-neutral.
A generic completion transport owns remote invocation and returns normalized
completion evidence. Two adapters may implement it:

- `GeminiCompletionTransport`, the required B4/B5 path;
- the existing OpenRouter transport, retained for optional B4L/B5L.

Provider-neutral contracts bind baseline ID, exact model ID, provider/tier,
generation settings, prompt fingerprint, token usage, latency, finish reason
and checkpoint identity. Provider-specific metadata and errors remain inside
the adapter and are normalized to stable public error codes.

## Free-tier and privacy policy

Gemini runs use an explicitly supplied `GEMINI_API_KEY` and require network
opt-in. The workflow must never enable billing, upgrade the account or fallback
to a paid endpoint. Reports record `$0 observed API charge`, not a claim that
the service has zero infrastructure cost.

The accepted test snapshot must retain the existing no-secrets and
no-personal-data review. Reports disclose that prompts leave the workstation
and that free-tier content may be used by the provider to improve products.
This policy is part of the privacy dimension and must not be presented as
equivalent to local inference or a paid no-training policy.

## Quota, retry and resumption

Only transient transport and bounded rate-limit failures may retry. Quota
exhaustion seals the latest durable checkpoint and exits with a stable blocked
status. A later invocation may resume the same run after quota renewal, but
must validate the exact model, prompt set, test snapshot and checkpoint chain
before contacting the provider.

Retries must not change model or tier. A complete scientific comparison still
requires three genuine B4 runs and three genuine B5 runs over the finalized
T3.5 test set. Runs split across quota windows must retain timestamps and model
metadata so possible service drift remains visible.

## Evidence and acceptance

Local implementation readiness requires adapter tests, no-network default
behavior, model-metadata validation, quota and resume tests, safe error mapping,
artifact integrity checks, CLI verification and the full repository quality
gates.

Scientific readiness requires:

- finalized independently reviewed T3.5 evidence;
- accepted non-test B5 training/retrieval evidence;
- one accepted stable Gemini free-tier model identity;
- complete privacy review and disclosure;
- three complete genuine runs for B4 and B5;
- complete prediction, token, latency, failure and reproducibility artifacts;
- no model/tier drift or unresolved outcomes.

Large Llama/OpenRouter evidence is explicitly absent from this required list.

## Documentation migration

Implementation must update the T5.3 task, README commands, CLI help, decision
log and evaluation terminology. Existing Llama/OpenRouter closure evidence
remains historical evidence for the optional adapter and must not be rewritten
as Gemini verification. The thesis must describe B4/B5 as hosted frontier-model
baselines unless optional B4L/B5L results are actually executed and accepted.
