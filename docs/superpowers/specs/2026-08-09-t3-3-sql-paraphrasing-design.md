# T3.3 Two-Model GoogleSQL Paraphrasing Design

## Context

The active Stage A artifact contains 1,000 live-witnessed GoogleSQL records.
The existing T3.3 task still prompts a SPARQL-to-English translator, writes
`sparql` fields, assumes 2024 examples, and names models that are no longer a
pinned executable contract. No OpenRouter, OpenAI, Anthropic, or local Ollama
credential/runtime is currently available, so implementation and offline
verification can proceed but the 2,000-call live run must remain fail-closed
until `OPENROUTER_API_KEY` is configured.

## Goals and non-goals

Stage B produces one faithful formal English question for every Stage A SQL
record. Stage C produces three meaning-preserving styles—casual, abbreviated,
and alternative—for every formal question. The pipeline must be resumable,
cost-auditable, strict-schema, and incapable of publishing partial final files.

This task does not perform noise injection, split train/test pools, or use the
LLM to alter SQL. It does not promise byte-reproducible model text; instead it
pins model IDs, prompts, source hashes, response IDs, usage, actual cost, and
output hashes so the run is reproducible and auditable.

## Considered approaches

1. One model and free-form text for both stages. It is simple but preserves the
   original single-model bias and makes parsing/recovery fragile.
2. Local deterministic rewrite rules. They are credential-free but cannot
   provide the linguistic diversity required by Stage C.
3. Two pinned models behind one OpenRouter-compatible client with strict JSON
   schemas, checkpoints, and deterministic validators. This is selected.

## Models and API contract

Stage B uses `openai/gpt-4.1-mini` at temperature 0. Stage C uses
`google/gemini-2.5-flash` at temperature 0.7. Both support structured outputs
on OpenRouter, and provider routing must set `require_parameters=true` so a
fallback cannot silently discard `response_format`. Model IDs remain CLI
options but the run manifest records the exact values.

OpenRouter's official structured-output contract uses
`response_format.type=json_schema` with strict JSON Schema, and its usage
accounting returns token counts plus actual `usage.cost` on non-streaming
responses. The implementation relies on those response fields rather than a
hard-coded price table:

- <https://openrouter.ai/docs/guides/features/structured-outputs>
- <https://openrouter.ai/docs/cookbook/administration/usage-accounting>
- <https://openrouter.ai/docs/quickstart>

The project already pins `openai>=1.30,<2`; `AsyncOpenAI` uses
`https://openrouter.ai/api/v1`. The API key is read only from
`OPENROUTER_API_KEY` and is never written to logs, checkpoints, or manifests.

## Prompt and response contracts

Stage B receives SQL, `nl_seed`, typed slot values, entity context, and CQ/schema
metadata. It returns exactly:

```json
{"question": "...", "preserved_facts": ["start_date=...", "n=..."]}
```

Stage C receives only the accepted formal question plus the same immutable fact
list and returns exactly:

```json
{
  "casual": "...",
  "abbreviated": "...",
  "alternative": "...",
  "preserved_facts": ["start_date=...", "n=..."]
}
```

Every required slot appears once as a canonical `name=value` fact. The model is
instructed to preserve limits, thresholds, dates, durations, token symbols, and
entity identity. SQL is reference context, never an output field the model may
edit.

## Deterministic validation

Responses are rejected on unknown/missing fields, empty or multi-sentence formal
questions, control characters, duplicate Stage C variants, missing/changed
preserved facts, numeric/date/token anchor loss, or forbidden SQL/code-fence
output. Address entities may appear as the exact address or a pinned dictionary
owner/primary label; the accepted alias is recorded in prompt context.

Normalized Levenshtein distance is calculated for all three Stage C pairs. The
per-parent three-way average and the dataset-wide mean are recorded. Final Stage
C acceptance requires 3,000 unique normalized questions and a mean pairwise
distance above 0.30. Automated checks supplement, but do not replace, the
seed-42 manual audits of 50 Stage B and 100 Stage C parents.

## Runner, checkpoints, and cost

The asynchronous runner has configurable concurrency (default 10), maximum
three attempts for retryable 429/5xx/timeouts, exponential backoff, and no retry
for schema/faithfulness failures. Each successful response appends a canonical
checkpoint row keyed by source record hash, prompt hash, stage, and model.
Resume rejects duplicate/conflicting keys and never calls already accepted rows.

Each response records generation ID, model, prompt/completion/total tokens,
actual USD cost, attempt count, and latency. The hard total cap is $30. Before a
batch is scheduled the runner reserves a conservative $0.02 per outstanding
request; it stops before the reservation could cross the cap. Missing cost data
is an error, not zero cost.

## Artifacts

- `synthetic-stage-b.jsonl`: 1,000 Stage A records plus `nl_formal` and Stage B
  response metadata.
- `synthetic-stage-c.jsonl`: 3,000 child records with `parent_id`, `version`,
  `nl`, `nl_formal`, unchanged `sql`/provenance, and Stage C metadata.
- `cost_log.csv`: one row per paid API response with no secrets or prompt text.
- `paraphrase-config.json`: source/prompt/output hashes, models, counts, quality,
  actual cost, and run timestamp.
- stage-specific checkpoint JSONL files used only for safe resume.

Final artifacts are written to sibling temporary files and replaced only when
the whole stage validates. A stopped or failed run retains checkpoints and cost
logs but cannot overwrite a previously accepted final artifact.

## Testing and completion

Unit tests use injected fake clients and clocks. They cover prompt hashes,
strict parsing, anchor/alias faithfulness, edit distance, retry classification,
resume/conflict behavior, concurrency-independent ordering, actual-cost gates,
output expansion, atomic writes, and no-client offline validation. Live closure
requires 1,000/3,000 final counts, cost at most $30, automated quality gates,
and documented manual sample results.

