# T5.3 B4/B5 remote large-LLM alternatives (2026-09-20)

## Scope and recommendation

T5.3 currently compares B4 (zero-shot) and B5 (exactly five retrieved
examples) using `meta-llama/llama-3.3-70b-instruct` through OpenRouter, with a
hard total budget of USD 20 and three genuine runs per baseline. The best
scientific choice is to retain that design and treat provider pinning as an
explicit part of the baseline identity. A provider switch should be a new
baseline/configuration, not a silent replacement: model-family, tokenizer,
sampling behavior, privacy terms, and cost accounting can all change.

OpenRouter's provider-routing documentation supports an ordered provider
allowlist, `allow_fallbacks=false`, `require_parameters=true`, data-collection
controls, and per-request `max_price`; its fallback documentation also says
that the response's `model` identifies the model ultimately used and that the
ultimate provider's price is charged. These are the controls needed by the
existing fail-closed provenance and USD 20 ledger:
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[OpenRouter model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks),
[OpenRouter guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview).

OpenRouter states that inference pricing is passed through from providers
without markup, while BYOK can add a 5% fee after a plan-dependent allowance;
this makes the already implemented usage-cost reconciliation preferable to
estimating cost from a public price page:
[OpenRouter support/billing](https://openrouter.ai/support/),
[OpenRouter BYOK](https://openrouter.ai/docs/guides/overview/auth/byok).

## Candidate comparison

| Candidate | Scientific fit to current B4/B5 | Cost/privacy/reproducibility evidence | Code/spec impact |
|---|---|---|---|
| **OpenRouter, pinned provider (recommended)** | Same requested Llama 3.3 70B model ID; preserves B4/B5 prompt and retrieval controls. Must retain exact provider, model, generation settings, and response identity in artifacts. | Provider routing can be constrained; `data_collection`/ZDR are policy controls, not proof of zero retention. Usage and final model are returned by the API. | **None** beyond current implementation. Keep explicit provider and no-fallback policy. |
| **Direct Fireworks API** | Potentially closest API alternative: Fireworks publishes a Llama 3.3 70B Instruct page, Llama license/model metadata, and a stated serverless price of $0.90/M tokens. However, the same page's specification currently says “Serverless: Not supported,” so availability must be verified in the account before use. | Direct endpoint removes OpenRouter routing ambiguity, but requires a new provider adapter and authoritative usage/cost extraction. Fireworks' page says function calling is unsupported, which is irrelevant if plain text SQL is retained. | Moderate: new adapter, auth, rate-limit/retry mapping, cost ledger semantics, and a new pinned provider identity. A direct-provider run is not interchangeable with existing runs. [Fireworks model page](https://fireworks.ai/models/fireworks/llama-v3p3-70b-instruct) |
| **Direct Groq API** | Not recommended. Groq lists `llama-3.3-70b-versatile`, but its official deprecation history says it was deprecated with shutdown on 2026-08-16 for free/developer tiers. | Current docs list price as “Contact Sales,” so the USD 20 experiment cannot be independently budgeted from public list pricing. | High risk of a failed or late migration; do not start a new scientific run on this endpoint. [Groq supported models](https://console.groq.com/docs/models), [Groq deprecations](https://console.groq.com/docs/deprecations) |
| **Gemini API (Google AI Studio)** | Gemini 2.5 Flash/Pro (or current Gemini models) are a different proprietary model family, so this is a new large-LLM comparator, not a replacement preserving the Llama control. Gemini output can include reasoning tokens; compare token usage and output policy explicitly. | Google documents free and paid tiers, current per-token prices, spend-based rate limits, and that free-tier content is used to improve products while paid-tier content is not. Paid API billing is separate from the Google Cloud Welcome credit; failed 400/500 calls are not charged. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [billing](https://ai.google.dev/gemini-api/docs/billing), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) | Moderate/high: new SDK/transport, model-policy metadata, safety/finish-reason handling, usage fields, privacy declaration, and likely a new baseline ID. Do not relabel B4/B5 as Llama results. |
| **Gemini on Vertex AI** | Same model-family caveat as Gemini API. Vertex is a Google-managed deployment and may be a useful separately named comparator when enterprise data controls are required. | Vertex publishes current Gemini 2.5 token prices and batch/flex/priority variants; batch can alter latency and pricing, so use standard synchronous calls for parity with B4/B5. Pricing is subject to region/account configuration. [Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing), [Vertex Gemini quickstart](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart) | High: GCP project/location/service-account setup, quota/billing evidence, a Vertex adapter, and explicit data-residency/privacy artifacts. Not a minimal T5.3 change. |
| **OpenAI API** | Not suitable as a drop-in replacement: OpenAI's current API exposes its own GPT model family (the official quickstart uses `gpt-5`), not Meta Llama 3.3 70B. It would answer a different scientific question. | OpenAI documents API-key billing and data controls; the Responses API has a default 30-day application-state retention period unless configured otherwise. This is not equivalent to the current OpenRouter privacy policy. [OpenAI quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request), [OpenAI data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint), [OpenAI pricing](https://openai.com/api/pricing/) | Moderate adapter work, but high spec impact because model identity and retention semantics change. Use only as a separately labeled comparator. |
| **Local/Hugging Face inference** | The strongest privacy/reproducibility option in principle: weights and inference stack can be pinned and prompts never leave the machine. The official Meta Llama 3.3 repository is gated, and Hugging Face requires account access and agreement to share username/email with the model author. | No per-token provider bill, but hardware/runtime cost must be recorded. The model repository is roughly 70B-scale and split across many multi-GB safetensor shards; memory, quantization, CUDA/runtime, and decoding implementation become experimental variables. [Meta Llama 3.3 model repository](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct), [Hugging Face gated models](https://huggingface.co/docs/hub/models-gated) | Very high for this project: new local transport, model artifact/quantization fingerprints, hardware manifest, deterministic runtime controls, and a new cost definition. Do not run on an unspecified laptop and call it equivalent. |
| **Kaggle/HF hosted notebook** | Useful for an exploratory local/open-weight proof of concept, but not a stable T5.3 scientific backend. Kaggle's official documentation describes one P100 or two T4s, 12-hour sessions, and weekly accelerator quotas; this does not establish that an unquantized 70B model fits or that capacity is repeatable. | Compute is not a per-request API bill, but quota/availability and notebook environment drift must be captured. Kaggle versions are reproducible snapshots, but hardware queues and quotas remain external conditions. [Kaggle notebooks](https://www.kaggle.com/docs/notebooks), [Kaggle GPU usage](https://www.kaggle.com/docs/efficient-gpu-usage) | Very high: package/environment lock, model download authorization, GPU/hardware manifest, quantization choice, notebook version, and artifact export. Prefer a dedicated pinned VM if this path is selected. |

## Reducing or removing B4/B5

Removing B4/B5 is scientifically defensible only if the thesis question no
longer needs a remote large-model control. The current design explicitly uses
B4/B5 to measure (a) a raw large-model zero-shot control and (b) the isolated
effect of five retrieved examples against the accepted B1/B2 setup. Deleting
them would remove that control and should be recorded as a scope change, not
as an “alternative provider.”

Lower-risk reductions are:

1. Keep B4/B5 implementation and local/offline evidence, but defer the live
   three-run execution until funding and the finalized test set are available.
   This preserves the protocol without spending the USD 20.
2. Run one explicitly labeled pilot request per baseline only to validate
   transport, model/provider metadata, and cost accounting. A pilot cannot be
   reported as the required three-run scientific result.
3. If the budget is reduced, use fewer cases or fewer runs only after changing
   the preregistered acceptance criterion; do not silently compare incomplete
   runs with B1/B2.
4. If privacy is decisive, replace remote B4/B5 with a separately named local
   open-weight comparator. Keep the model revision, quantization, hardware,
   software lock, and decoding configuration in every artifact.

## Decision

Retain OpenRouter with one explicitly pinned provider, no fallbacks, model and
provider response verification, usage-derived cost reconciliation, and the
existing USD 20 hard ledger. Fireworks is the only plausible direct-provider
fallback for the same Llama family, but its own current page has contradictory
serverless availability text and therefore needs an account-level preflight
before any design work. Do not use Groq because the official deprecation notice
has already passed; do not substitute Gemini or OpenAI under the same B4/B5
labels; and treat local/Kaggle/HF inference as a new privacy-focused baseline,
not a drop-in remote replacement.

