# T5.3 — B4 + B5: GoogleSQL Large-LLM Baselines

local implementation complete
scientific acceptance pending

## Scope

T5.3 provides two raw-model NL-to-GoogleSQL controls over the managed BigQuery
analytical catalog:

- **B4 zero-shot:** the question and the compiled catalog summary only.
- **B5 few-shot:** the same prompt and generation policy, plus exactly five
  accepted examples selected by the B2 retriever.

B4 and B5 do not consume T4 schema, entity, or class-linking evidence. They
reuse the accepted B1/B2 catalog summary, `b12.prompts.build_messages`, and
`b12.extraction.extract_google_sql`. Extraction validates the whole model
output and returns only a read-only, managed GoogleSQL statement; prose,
multiple statements, invalid SQL, and unsafe SQL fail closed. B5 retains the
B2 training/cache leakage and provenance checks.

The canonical model is exactly
`meta-llama/llama-3.3-70b-instruct`. Every run fixes `temperature=0`, `seed=42`,
`max_tokens=512`, and one returned choice. The model identifier is a run
contract, not a claim that the provider will keep the model or its pricing
available forever.

## Provider and request policy

The live adapter is OpenRouter-compatible and is constructed lazily only after
all local checks and explicit network opt-in. `--provider` is required and
identifies one pinned provider. Requests set `allow_fallbacks=false`,
`require_parameters=true`, and `data_collection="deny"`; provider switching or
silent fallback is not allowed. The workflow currently constructs policy
ceilings of `0.50` USD per million prompt tokens and `1.00` USD per million
completion tokens. These are run-policy ceilings, not timeless market prices;
the accepted live model metadata and response usage remain authoritative.

Only transient transport failures are retried: HTTP 408, 409, 429, 500, 502,
503, and 504, connection failures, and timeouts. Retry attempts are bounded by
the configured maximum (default three), use exponential backoff with injected
jitter, and honor a valid bounded `Retry-After`. Authentication, payment,
malformed-request, unsupported-parameter, moderation, and other non-transient
errors stop immediately. Logs retain safe error codes and fingerprints, never
API keys or full prompts.

The hard budget is a positive `Decimal` cap no greater than USD 20. Before a
request, a lock-protected ledger reserves a conservative maximum based on the
UTF-8 prompt size, 512 output tokens, and the configured provider ceilings. A
case is `budget_blocked` before network I/O when the complete reservation does
not fit. Every network attempt has its own reservation ID. A retryable failure
holds that attempt's full ceiling as unresolved liability, so a later attempt
must reserve another ceiling and can never oversubscribe the cap. Returned
authoritative usage cost reconciles only the current attempt; earlier unknown
liabilities stay in the checkpoint. A missing/invalid charge remains unresolved,
and a charge above the reservation
or cap records a pricing violation and stops further work. Concurrent workers
cannot collectively oversubscribe the cap, and interrupted runs retain
unresolved reservations and unattributed spend in their checkpoint. Cooperative
cancellation shields the hold/reconcile and durable failure append before
propagating; an abrupt process kill can only preserve the last durable journal
checkpoint.

## Privacy and evidence boundary

Live requests require both `--allow-network` and a non-empty
`OPENROUTER_API_KEY`. Help, validation, local tests, and `summarize` do not
construct an OpenRouter client or open a socket. The key is read only at the
live boundary and is never serialized, echoed, or logged. Questions and
catalog context leave the workstation and may be processed by the pinned
provider; `data_collection="deny"` is a requested routing policy, not a
guarantee of zero retention. The accepted test snapshot must contain no
secrets or personal data. The canonical local marker `<test-set>.privacy.json`
(or `--privacy-review`) records the exact input SHA and affirmative
`reviewed`, `no_secrets`, and `no_personal_data` assertions. Live `evaluate`
refuses key/metadata/client construction until
`--accepted-privacy-review-sha256` matches the marker's exact bytes. Its
privacy fingerprint is retained in every outcome, journal header/terminal,
report, and resume identity. Offline `validate` remains networkless and
reports a missing or invalid privacy gate instead of inventing acceptance.

Injected/synthetic transports are useful for local tests but are permanently
marked synthetic and cannot make a run scientifically ready. The report keeps
separate local implementation readiness and scientific readiness; a caller
boolean cannot override either one.

## Artifacts and resumption

The default outputs are:

- `data/eval/predictions/b4_test.jsonl` or `b5_test.jsonl`;
- `data/eval/logs/b4_openrouter.jsonl` or `b5_openrouter.jsonl`;
- `data/eval/logs/openrouter_cost.csv`;
- `reports/b4_inference.json` or `b5_inference.json`.

Each prediction records the case/question identity, raw output, safe SQL or
extraction status, model/provider/generation identity, token counts, charged
cost, attempts, latency, and catalog, summary, prompt, configuration, and (for
B5) training/encoder/example fingerprints. Failure outcomes retain a safe
error code, prompt fingerprint, attempt count, authoritative cost when known,
and the durable budget checkpoint. Run/outcome/report identities also retain
the provider-policy and accepted privacy fingerprints.

Existing in-progress request journals may be schema **v3** when they contain
only outcome evidence and upgrade to schema **v4** before live provider-attempt
evidence is appended. Header, attempt, outcome, and terminal records are
SHA-256-chained, and the final terminal record seals outcome count, derived
metrics, budget, blockers, readiness, and the canonical attempt set. Each
attempt record contains only secret-safe
evidence: request/reservation identity, attempt number, status, prompt hash,
reserved ceiling, latest budget checkpoint, and authoritative cost when known.
Outcome and terminal rows cross-bind the attempt count and attempt-set digest,
so reordered, duplicate, tampered, or mismatched attempt evidence fails closed.
An attempt-only prefix restores the latest durable budget checkpoint without
treating the case as completed. Reports are published last and are cross-bound
to the terminal record; a sealed terminal checkpoint forbids later append.
Hashes detect corruption and bind artifacts relative to an accepted digest, but
unkeyed hashes do not authenticate a coordinated rewrite of every artifact. An
external accepted digest or signature would be required for that threat model
and is outside T5.3.

On resume, a pre-network budget block reports the cumulative durable attempt
count while attributing zero cost to the new outcome. Costs from completed
attempts whose outcomes were lost remain in budget spend as unattributed spend,
which is always a scientific blocker. A later successful attempt attributes
only its own authoritative cost; earlier orphan costs remain unattributed.

For compatibility, an authentic terminal-free schema-v2 journal may be loaded
**only for resume**, after exact identity and budget validation. Before the next
append it is atomically migrated one-way to schema v3. A valid in-progress
schema-v3 journal is upgraded atomically to schema v4 only when the first
attempt row is appended. New publication is always sealed as schema v4,
including runs with no attempt rows. Summary loading retains read-only support
for sealed v3 evidence; v2 cannot be used as a final result.

## CLI

The numbered entry point is `scripts/18_large_llm_baselines.py`. Use `--help`
for the authoritative Click rendering. All commands emit compact JSON on
non-help paths. Fatal attempt-evidence persistence failures use the stable
`attempt_evidence_persistence_failed` code and never emit traceback, prompt, or
provider details.

Offline validation never needs a key, model, encoder, or network:

```bash
uv run python scripts/generate_b45_local_verification.py
uv run python scripts/18_large_llm_baselines.py validate \
  --baseline b4 \
  --provider deepinfra \
  --max-cost-usd 20
```

The generator is the only canonical publication workflow for
`docs/evidence/t5-3-local-verification.json`. It executes the exact focused and
full pytest commands, Ruff check and format checks, CLI help, and offline
validation before atomically publishing command-output hashes, passing test
counts, and a deterministic source-set SHA-256. The source set covers the B45
module, workflow and numbered wrapper, generator, B45 tests and fixtures,
`pyproject.toml`, `uv.lock`, and `.python-version`; the manifest and
closure-only documentation are deliberately outside that digest to avoid a
self-reference cycle. A missing, malformed, tampered, or source-stale manifest
yields a local-readiness blocker. Live `evaluate` rejects that state before
snapshot, key, metadata, SDK, or transport access, while offline `validate`
reports it without opening a network connection.

`validate` accepts `--baseline {b4,b5}`, required `--provider`,
`--max-cost-usd`, `--test-set`, `--predictions`, `--request-log`, `--cost-log`,
`--report`, `--privacy-review`,
`--accepted-privacy-review-sha256`, `--catalog`, `--training`, `--cache`,
`--encoder-id`, `--encoder-revision`, and `--accepted-training-sha256`; B5
additionally requires a valid accepted training digest and pinned encoder
revision. Missing privacy evidence is reported as an offline blocker.

`predict` requires `--baseline`, `--question`, and the common options. A live
request additionally requires explicit `--max-cost-usd`, `--allow-network`,
and `--accepted-model-metadata-sha256`; B5 may use `--target-id` and requires
the same accepted training/cache options. `predict` has no artifact
publication.

`evaluate` requires `--baseline` and `--run-id`, and accepts `--test-set`,
`--privacy-review`, `--accepted-privacy-review-sha256`, `--predictions`,
`--request-log`, `--cost-log`, `--report`, `--resume`, `--allow-network`, and
`--accepted-model-metadata-sha256` in addition to the common options. Live
evaluation requires explicit `--max-cost-usd`; it computes all local identity
fingerprints, including deterministic per-case prompt hashes and a canonical
prompt-set digest, and validates resume state before API key, metadata, or client
access. For B5, local cache validation and encoder/retriever construction
precede prompt and resume validation, so changed retrieval evidence fails closed
without network access. It performs local path protection before the live loader,
keeps ordered durable outcomes, and publishes atomically.

`summarize` is offline and requires exactly three repeated `--report PATH` and
three repeated `--request-log PATH` options. It loads only sealed local runs and
reports observed pairwise normalized-SQL and raw-output agreement; it does not
invent missing predictions or claim determinism. A per-baseline three-run
summary always reports `counterpart_baseline_missing` and
`combined_budget_unverified`, keeps `scientific_ready=false`, and separately
emits derived `local_implementation_ready`.

## Bằng chứng chốt triển khai local

Manifest xác minh local chuẩn được tạo tại implementation HEAD
`84a773c7ac45d7fe8ba6ef20b06419d8d9bc5ca0` vào ngày 2026-09-14. Manifest ghi
lại lệnh chính xác, exit code, số test passed/skipped, digest của output và hash
của source set. Lần chạy xác minh chuẩn cho kết quả:

- 242 test B45 tập trung passed, 0 skipped;
- 1.189 test toàn repository passed, 0 skipped; output của lần chạy full test
  báo 342 cảnh báo dependency đã tồn tại từ trước;
- `ruff check` và `ruff format --check` passed;
- CLI help và offline B4 validation trả về thành công mà không yêu cầu
  credentials; hành vi không truy cập mạng của các đường chạy local được bao
  phủ bởi test.

SHA-256 của source set đã xác minh là
`af48ec15b0fc9273943218b44a222d075b8b635478d4ea5901cf6c6c3f6aef14`. Trường
self-hash `manifest_sha256` của nội dung manifest chuẩn là
`a852e01a197fc5671d3b920775bc2a7f2bfea7e3d66f333658ffbc6c0a66c150`, còn
SHA-256 của toàn bộ file manifest đã commit là
`4f51552d3f6a6b7f95d24a7ded0571f1f9a3424d1d68a8b6cf59def65f13fd07`. Tài
liệu closure không thuộc source set theo chủ đích.

Chuỗi review độc lập theo hai trục Spec/Standards bao phủ các thay đổi từ base
`3b34ac48c86a7b02799a953062e162502470a8d2` đến implementation HEAD
`84a773c7ac45d7fe8ba6ef20b06419d8d9bc5ca0`. Review ban đầu tìm thấy hai lỗi
Critical và sáu lỗi Important. Các vòng sửa test-first và scoped re-review sau
đó đã chốt các vấn đề về retry/cancellation accounting, privacy evidence,
resume và prompt identity, local readiness, durable attempt records, exact
prompt context preflight, explicit fresh-run behavior và exact/conservative
price parsing. Không còn finding Critical hoặc Important tại `84a773c`.

Bằng chứng này chỉ xác nhận local implementation readiness. Không có request
OpenRouter live nào được thực hiện và không có tuyên bố về live accuracy,
latency, cost, provider reproducibility hoặc so sánh khoa học B4/B5.

## Acceptance boundary

The local implementation gate covers contracts, B4/B5 prompt parity, B2
retrieval reuse, fail-closed GoogleSQL extraction, lazy provider loading,
retry/error policy, hard-cap accounting, protected atomic artifacts, sealed v4
publication terminal evidence, sealed-v3 read-only compatibility, v2 resume
migration, CLI preflight, focused tests, the full test suite, and lint/format
checks. Readiness is derived from the validated canonical manifest rather than
a caller-provided boolean. Local completion does not produce research results.

Scientific acceptance remains blocked until all of the following are supplied
and independently reviewed:

- finalized T3.5 test-set evidence with 100 trusted cases and no secrets;
- an accepted non-test B5 training snapshot, cache, and pinned encoder
  revision;
- accepted live OpenRouter model metadata for the exact model and one provider
  supporting every pinned parameter;
- explicit human permission, valid account/key, and sufficient funds for live
  requests;
- three complete genuine B4 runs and three complete genuine B5 runs;
- authoritative total cost at or below USD 20, no unresolved or unattributed
  spend, and complete provider/latency/token/reproducibility evidence.

Until those external gates pass, this task makes no claim about live accuracy,
latency, cost, or scientific comparison. Current provider prices and model
availability must be captured at live preflight rather than copied into a
timeless document.

Linked:

- Spec: `docs/superpowers/specs/2026-09-07-t5-3-google-sql-large-llm-design.md`.
- Plan: `docs/superpowers/plans/2026-09-07-t5-3-google-sql-large-llm.md`.
- Code: `src/nl2sparql/models/b45/`, `scripts/18_large_llm_baselines.py`.
