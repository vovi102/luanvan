# T3.2 — Witness-Grounded GoogleSQL Generation (Stage A)

## Mục tiêu

Sinh đúng 1.000 cặp `(GoogleSQL, nl_seed)` deterministic từ T3.1 contract v2,
sau đó dùng bounded BigQuery witnesses để chứng minh 100% records non-empty mà
không lặp lại cùng một scan cho mọi biến thể `LIMIT`.

## Bối cảnh

Scaffold tháng 7 dùng `sparql_template`, Fuseki, RDF IRI và window 2024 nên đã
superseded sau Pivot #1. T3.1 hiện có 25 typed GoogleSQL templates, nhưng chín
example thuộc sentinel/coverage gap có thể trả rỗng và không được đưa vào
training Stage A.

Live probe toàn tháng xác nhận chỉ hai hard templates có dữ liệu:
`T_TOKEN_AFTER_NATIVE_FUNDING` và `T_REPEATED_PAIR_FLOW`. Với cap 10% mỗi
template, hard share tối đa trung thực là 20%; target cũ khoảng 25% không thể đạt
nếu vẫn bắt buộc non-empty.

## Phụ thuộc

- T3.1 — 25 GoogleSQL templates, typed renderer và live 20/64 GiB gate.
- T2.2 — role-aware entity dictionary.
- T2-SQL-2 — managed views/TVFs trên BigQuery.
- T2-SQL-3 — bounded-window correctness/cost evidence.

## Đầu ra

- `data/dataset/raw/synthetic-stage-a.jsonl` — 1.000 verified SQL records.
- `data/dataset/raw/generation-config.json` — seed, allocations, input/artifact
  hashes và live witness metrics.
- `data/dataset/raw/stats.md` — difficulty/template/entity/proof/cost stats.
- `src/nl2sparql/dataset/generate.py` — network-free candidate generator.
- `src/nl2sparql/dataset/stage_a/verify.py` — BigQuery witness verifier.
- `scripts/09_generate_stage_a.py` — offline/live atomic artifact CLI.
- `notebooks/08_generate_synthetic.ipynb` — unexecuted workflow.

## Record contract

Mỗi record lưu stable ID, template/category/difficulty, typed slot values,
`entities_used`, canonical `sql`, `nl_seed`, schema/CQ links, template/record
SHA-256, seed, witness group và verification object. Candidate identity không
phụ thuộc live latency/timestamp.

Witness group chỉ được bỏ slot `n`. Query có `LIMIT 1` được execute exact; nếu
có row thì mọi record cùng semantics với `n >= 1` được đánh dấu
`live_limit_monotonic`. Query không có `n` là singleton `live_exact`. Không
record nào claim exact result count từ propagated proof.

## Distribution contract

- easy: 350 records trên 6 live templates;
- medium: 450 records trên 8 live templates;
- hard: 200 records trên 2 live hard templates;
- mỗi template tối đa 100 records;
- mỗi typed entity value tối đa 50 records;
- 1.000 SQL strings và record hashes phải unique bằng slot variation thật,
  không dùng comment/tautology để giả diversity.

## Validation và cost safety

- Offline: exact allocation/schema/hash/render checks, typed pool provenance,
  unique SQL/IDs, template/entity caps và seed 42.
- Live: dry-run toàn bộ witness set trước mọi execution, tối đa 20 GiB/witness
  và 96 GiB tổng.
- Mỗi witness được re-dry-run ngay trước execution; query cache disabled; result
  columns phải exact; zero row/cache hit/schema drift đều fail closed.
- `T_COUNT_TX_IN_RANGE` chỉ pass khi `transaction_count > 0`, không chỉ vì
  aggregate query trả một row.
- Final JSONL/config/stats chỉ được replace sau khi toàn bộ verification pass.

## Acceptance criteria

- [x] Plan B design/plan được duyệt và commit trước implementation.
- [x] Candidate generator dùng `sql`, không còn SPARQL/Fuseki runtime contract.
- [x] Exact 1.000 records, seed 42 byte-stable, 1.000 unique SQL/hashes.
- [x] Distribution 350/450/200; template cap 100; entity cap 50.
- [x] Fake-client tests cover witness planning, full preflight, caps, schema,
  non-empty/count/cache và proof propagation.
- [x] CLI offline không tạo BigQuery client; live outputs chỉ ghi sau success.
- [x] Live preflight pass trong 20/96 GiB gates.
- [x] 100% final records có non-empty witness; zero cache hits.
- [x] Final artifacts/stats/config được tạo và hash-verified.
- [x] Full pytest, Ruff, format, `git diff --check` pass; worktree clean.

## Trạng thái

`done — 2026-08-09; 1.000 GoogleSQL records live-witness verified`

### Stage A v2 — candidate 25 intent (2026-10-10)

Stage A v1 ở trên vẫn là historical accepted artifact và không bị sửa. Một v2
candidate riêng đã được tạo để giải quyết coverage 16/25 intent:

- `synthetic-stage-a-v2-candidate.jsonl`: 1.000 records, đủ 25 intent,
  difficulty 350/450/200, seed 42; SHA-256
  `b3c1052f9d19cc47be1d39c91c7898618af8990fbfc77943c1b5751aa26f2d94`.
- `generation-config-v2-candidate.json`: lifecycle `candidate`,
  `acceptance_eligible=false`, verification `offline_candidates`; SHA-256
  `8162368ccf3255699b285e87c850f00cb9be67aeeb10afa3de9fab85a1011d5b`.
- `stats-v2-candidate.md`: SHA-256
  `5f94062d64d09bc6ee39d3c9e54e2f6c3285aec22ca3cf67d261a23e8e3172e7`.

Các giá trị `block_number` và `transaction_hash` trong candidate vẫn chỉ là giá
trị deterministic/syntax-only; candidate không supersede acceptance của v1 và
không được dùng để publish/audit corpus canonical. Pool promotion riêng hiện có
45 block numbers và 45 transaction hashes unique với BigQuery provenance,
SHA-256 `1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8`.
Live promotion vẫn phải chạy toàn bộ witness gate rồi mới được ghi ba artifact
accepted riêng (`synthetic-stage-a-v2.jsonl`, `generation-config-v2.json`,
`stats-v2.md`).

Candidate identity canonicalize thứ tự template, slot và value-pool entry. Vì
vậy đảo thứ tự input không đổi bytes; hash ở trên thay thế hash candidate ban đầu
sau whole-branch review. Acceptance gate còn kiểm tra evidence trên từng record
và quan hệ đầy đủ giữa record, witness group, preflight và execution; chỉ sửa
metadata manifest không thể mở audit/build gate.

## Chạy lại

Offline deterministic candidates:

```bash
uv run python scripts/09_generate_stage_a.py
```

Stage A v2 offline candidate:

```bash
uv run python scripts/09_generate_stage_a_v2.py
```

Stage A v2 live promotion (chỉ sau khi các evidence pool và quyền chạy đã sẵn
sàng):

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --live \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Stage A v2 dry-run-only approval boundary:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --preflight \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

## Stage A v2 batched preflight — 2026-10-10

- Giữ nguyên 170 logical witnesses nhưng gom 45 `T_TX_BY_HASH` lookups vào một
  physical query; measured plan có 126 physical queries.
- Exact BigQuery dry-run estimate: `101.534.116.450` bytes (`94,561015 GiB`),
  thấp hơn aggregate cap 96 GiB `1.545.098.654` bytes (`1,438985 GiB`).
- Query lớn nhất là `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE`, `15.851.661.328` bytes
  (`14,763010 GiB`), thấp hơn per-query cap 20 GiB.
- Gross on-demand estimate là khoảng `$0.577155` theo mức `$6.25/TiB`; chi phí
  thực tế còn phụ thuộc monthly free tier và billed bytes. Dry-run không execute
  query và không tạo accepted output.
- Local verification: `1.639 passed`, Ruff format/check và `git diff --check`
  pass; v1 và v2 candidate hashes giữ nguyên; cả ba accepted v2 output vẫn absent.
- Live execution và accepted artifacts vẫn pending explicit approval. Không bắt
  đầu bilingual audit, canonical build hoặc B1/B2 training ở trạng thái này.

## Stage A v2 live attempt — 2026-10-11

- User đã duyệt measured live run. Repeated preflight pass, nhưng execution dừng
  fail-closed tại witness `syn-v2-000834` của
  `T_MIXER_TO_DEX_LARGE_FLOW`: kết quả rỗng.
- Root cause là coverage contract đã biết, không phải transient provider error:
  template ghi `expect_non_empty=false` với scope note “no accepted operational
  mixer endpoint”, và analytical catalog đánh dấu `CQ21` là `coverage_gap` vì
  dictionary chưa có verified operational mixer endpoint. Điều này mâu thuẫn với
  Stage A v2 acceptance gate yêu cầu 100% records `non_empty=true`.
- Hai physical executions đã hoàn tất trước khi dừng: processed `779.483.182`
  bytes, billed `780.140.544` bytes, cache hits `0`; gross on-demand equivalent
  khoảng `$0.004435` ở `$6.25/TiB`, trước monthly free tier.
- Publication boundary hoạt động đúng: `synthetic-stage-a-v2.jsonl`,
  `generation-config-v2.json` và `stats-v2.md` đều không được tạo. Không retry,
  không sửa metadata, không hạ threshold và không bắt đầu audit/build/training.
- Promotion hiện cần một quyết định redesign: bổ sung genuine verified mixer
  coverage và chứng minh bounded flow thật, hoặc thay intent coverage-gap bằng
  một intent được support rồi tạo/hash/audit lại candidate. Cho phép empty proof
  không đáp ứng acceptance contract hiện hành.

## Stage A v2 supported-intent revision preflight — 2026-10-11

- `T_MIXER_TO_DEX_LARGE_FLOW` đã được loại và thay bằng
  `T_CATEGORY_OWNER_DISTRIBUTION`, chỉ liên kết `CQ20`, có đúng 34 records với
  `n=1..34`. Candidate mới vẫn có 1.000 records, 25 intents, difficulty
  350/450/200, 170 logical witness groups và lifecycle `candidate`.
- Hai offline builds độc lập giống byte ở cả data/config/stats. Local gate pass
  `1.646` tests; Ruff format/check và `git diff --check` pass. Stage A v1 và
  evidence pool giữ nguyên hashes; ba accepted-v2 paths vẫn absent.
- Genuine BigQuery dry-run-only preflight đo `96.112.944.434` bytes
  (`89,512154864 GiB`) trên 126 physical queries cho 170 logical witnesses,
  thấp hơn aggregate cap 96 GiB (`103.079.215.104` bytes) đúng
  `6.966.270.670` bytes (`6,487845136 GiB`).
- Query lớn nhất là
  `3a4fe25837612c22c8c3d750331fe6f77f8eacf06f08493e6b15706590d833ce`
  của `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE`, `14.829.419.966` bytes
  (`13,810973583 GiB`), dưới cap 20 GiB (`21.474.836.480` bytes).
- Gross on-demand equivalent là `$0.546339` theo mức tham chiếu
  [`$6.25/TiB`](https://cloud.google.com/bigquery/pricing). Đây không phải charge
  dự báo cuối: first 1 TiB/month free, rounding và billed bytes có thể thay đổi
  actual charge.
- Preflight không execute query và không ghi artifact. Snapshot hash/existence
  trước/sau giống hệt nhau; failed live run cũ chỉ là operational evidence,
  không phải acceptance evidence. Revised live execution chờ user duyệt riêng
  exact measured estimate này.

| Template | Physical queries | Estimated bytes |
|---|---:|---:|
| `T_ACCOUNTS_BY_CATEGORY` | 1 | 117.879 |
| `T_BLOCKS_BY_VALIDATOR` | 4 | 14.234.859.968 |
| `T_BLOCK_BY_NUMBER` | 45 | 66.731.040 |
| `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE` | 1 | 14.829.419.966 |
| `T_CATEGORY_OWNER_DISTRIBUTION` | 1 | 394.972 |
| `T_COUNT_TX_IN_RANGE` | 45 | 1.097.467.136 |
| `T_CROSS_EXCHANGE_FLOW` | 1 | 389.764.739 |
| `T_EXCHANGE_TO_DEX_FLOW` | 1 | 389.923.594 |
| `T_FAILED_HIGH_GAS_TX` | 1 | 198.739.900 |
| `T_FILTER_TX_BY_VALUE` | 1 | 389.415.408 |
| `T_LARGE_TX_TO_CLASS` | 1 | 389.805.715 |
| `T_LIST_FAILED_TX` | 1 | 357.617.024 |
| `T_LIST_KNOWN_EXCHANGES` | 1 | 674.882 |
| `T_LIST_TX_FROM_ACCOUNT` | 4 | 1.558.565.392 |
| `T_LIST_TX_TO_ACCOUNT` | 4 | 1.558.565.392 |
| `T_REPEATED_PAIR_FLOW` | 1 | 254.272.276 |
| `T_TOKEN_AFTER_NATIVE_FUNDING` | 1 | 14.829.255.599 |
| `T_TOKEN_TRANSFERS_OF_TOKEN` | 2 | 29.006.801.680 |
| `T_TOKEN_VOLUME_BY_SYMBOL` | 1 | 14.120.516.260 |
| `T_TOP_RECIPIENTS_BY_COUNT` | 1 | 103.229.952 |
| `T_TOP_SENDERS_BY_VALUE` | 1 | 166.941.516 |
| `T_TX_BETWEEN_ACCOUNTS` | 4 | 1.557.661.632 |
| `T_TX_BY_HASH` | 1 | 405.314.600 |
| `T_TX_BY_HOUR` | 1 | 15.899.192 |
| `T_TX_GROUPED_BY_OWNER` | 1 | 190.988.720 |

## Stage A v2 revised live attempt — 2026-10-11

- User duyệt chạy trong free quota. Trước run đã xác minh project
  `nl2sparql-thesis` có `billing_enabled=false` và không liên kết billing
  account; BigQuery Sandbox sẽ fail quota thay vì phát sinh paid usage.
- Live verifier lặp full preflight rồi dừng fail-closed tại
  `syn-v2-000436` / `T_TX_BETWEEN_ACCOUNTS`: query cho cặp
  `0x8fca4ade3a517133ff23ca55cdaea29c78c990b8` và
  `0x77021d475e36b3ab1921a0e3a8380f069d3263de` trong window
  `2026-06-15`–`2026-06-16` trả rỗng.
- 13 physical execution jobs đã hoàn tất trước khi dừng: processed
  `1.708.003.160` bytes (`1,590701900 GiB`), billed `1.749.024.768` bytes
  (`1,628906250 GiB`), cache hits `0`. Gross on-demand equivalent là
  `$0.009942` ở `$6.25/TiB`, nhưng actual charge là `$0` vì project không có
  billing account và run dùng sandbox free quota.
- Publication boundary hoạt động đúng: cả ba accepted-v2 outputs vẫn absent;
  candidate, Stage A v1 và evidence-pool hashes không đổi. Đây là failed
  operational evidence, không phải acceptance evidence. Không retry, không đổi
  pool/metadata và không hạ non-empty gate trong attempt này.

## Stage A v2 pair-backed diagnostic attempt — 2026-10-14

- Candidate được regenerate từ pool có 40 quan hệ account-pair đã chứng minh,
  giữ 1.000 records, 25 intents, difficulty 350/450/200 và seed 42. SHA-256
  hiện hành: data
  `bc82ef19884081f7017f138e6bfb6cf88851dcc4b209c990694828526edb5b7f`,
  config `ae5e0951641dd364c3c812aab5bbf17a5147af189aeff7cea0540c77483a4a88`,
  stats `c5fd8e35dca3ecff90e4cf032da19dc6016b28208f4527928ed5d95919beb13c`.
  Plan có 206 logical witnesses và 126 physical queries; 40 pair witnesses được
  gom thành bốn batch 10-pair.
- Pre-provider gate pass `1.424` tests, Ruff format/check và
  `git diff --check`. Stage A v1 hashes vẫn là
  `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`,
  `781495b7a70614bd6b87861781a816946f2443ac1c66cab2bba16df58afbe713`,
  `bc93c7a9355a34e531b275181646db269968040d2484e8a2876a8329db8579db`;
  evidence-pool hash vẫn là
  `cc596000e1c09f6ebcb46eb6ef3d48dbdd4953f66bb238ffb24901be4b7705e6`.
- Diagnostic CLI xác nhận project `nl2sparql-thesis` có
  `billing_enabled=false` và billing account rỗng trước khi tạo BigQuery
  client. Initial dry-run phủ đủ 126 physical queries / 206 logical witnesses,
  tổng estimate `99.050.610.963` bytes (`92,248070019 GiB`), thấp hơn cap 96
  GiB `4.028.604.141` bytes. Query lớn nhất là
  `3a4fe25837612c22c8c3d750331fe6f77f8eacf06f08493e6b15706590d833ce`
  / `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE`, `15.250.087.887` bytes, dưới cap 20
  GiB.
- Lượt diagnostic duy nhất dừng fail-closed ở physical execution thứ 14:
  witness `syn-v2-000637` / `T_BLOCKS_BY_VALIDATOR` cho beneficiary
  `0x77021d475e36b3ab1921a0e3a8380f069d3263de` trong window
  `2026-06-15`–`2026-06-16` trả rỗng, dù immediate dry-run estimate
  `3.561.169.792` bytes. Trước điểm dừng có 13 execution jobs và 66 logical
  outcomes thành công; processed `1.708.003.160` bytes (`1,590701900 GiB`),
  billed `1.749.024.768` bytes (`1,628906250 GiB`), cache hits `0`. Report lưu
  từng query digest, membership, execution job ID và logical outcome đã quan
  sát.
- Diagnostic report
  `docs/evidence/stage-a-v2-account-pair-diagnostic.json` có SHA-256
  `04c09aff49422274b1ad1b3a577f98a0c20e250d439a4675e8b684c57e30fb87`,
  status `failed`, mode `diagnostic` và `acceptance_authorized=false`. Đây là
  operational evidence, không phải acceptance evidence. Không retry; cả ba
  accepted-v2 outputs vẫn absent và mọi candidate/v1/evidence hash không đổi.
- Pair-level provenance đã sửa lỗi ghép hai endpoint độc lập, nhưng không chứng
  minh cùng address có vai trò block beneficiary. Bước kế tiếp là bổ sung
  relationship-specific evidence cho `T_BLOCKS_BY_VALIDATOR` (và audit các
  intent account-bound còn lại), regenerate candidate, rồi chạy fresh preflight;
  không chạy `--live` hoặc publish acceptance nếu chưa có user approval mới.

## Beneficiary correction and coverage diagnostic — 2026-10-14

- `T_BLOCKS_BY_VALIDATOR` now uses its own four-entry `block_beneficiary`
  pool; the generic transaction-address pool remains scoped to from/to intents.
  The four beneficiaries have 3,353 / 1,267 / 861 / 572 blocks in the exact
  half-open window `[2026-06-15, 2026-06-16)`. Forty generated records use
  these beneficiaries with limits 1–10, retaining 206 logical witnesses and
  126 physical queries.
- The bounded collection job `73314dc2-669a-4a66-9452-bedfb34ed714` ran in
  `nl2sparql-thesis` / `US` after checking disabled, unlinked billing.
  Estimate: 1,123,720 bytes; processed: 1,040,000; billed: 10,485,760;
  maximum bytes billed: 1,073,741,824; cache hit: false. Query SHA-256:
  `6c4eb7681270251bf846b13b54f56208b43e1a17d11ed0d8c5695f50c23a1d2a`.
  Pool entries retain each positive block count and first/last UTC timestamps.
  Collection selected the top four beneficiaries by block count, with address
  as the deterministic tie-breaker:

  ```sql
  SELECT beneficiary_address AS account, COUNT(*) AS block_count,
  MIN(block_timestamp) AS first_seen_at, MAX(block_timestamp) AS last_seen_at
  FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-15', DATE '2026-06-16')
  WHERE REGEXP_CONTAINS(beneficiary_address, r'^0x[0-9a-f]{40}$')
  GROUP BY account
  ORDER BY block_count DESC, account
  LIMIT 4
  ```

- Candidate builds are byte-identical; full local verification passed
  1,438 tests, Ruff format/check and whitespace checks. Current SHA-256:
  data `563025953b52b9465dc8fe2d879cebffa8a9e1ba86ea138b2de686f01c5235ee`,
  config `06d34f8f3ef6daf095ad96d80fab98b7ac69a644555444b91830a93416281476`,
  stats `c5fd8e35dca3ecff90e4cf032da19dc6016b28208f4527928ed5d95919beb13c`,
  pool `a6b827732320c18a274323fe4f5a5d60ea07d380065c6c1c4707b905a081fbca`.
  Existing pool entries and immutable v1 hashes remain intact. Diagnostic
  validation now permits the empty job IDs actually observed for dry runs,
  while execution evidence still requires a job ID.
- One new diagnostic used the existing workflow with an injected client that
  explicitly disabled SDK request/job/result retries. Its initial 126-query
  preflight estimated 82,577,568,447 bytes (76.906353652 GiB), within the
  96 GiB aggregate and 20 GiB individual caps. It passed the old beneficiary
  failure point and completed 74 validated executions / 145 logical outcomes,
  then stopped on zero rows at `syn-v2-000800` /
  `T_EXCHANGE_TO_DEX_FLOW`. No retry or subsequent provider query was run.
- The diagnostic report is
  `docs/evidence/stage-a-v2-beneficiary-diagnostic.json`, SHA-256
  `d020fb3369f4fc3ccea9b0de31b701875c3287d6e856fd184978a66911fb2842`.
  Its successful-execution totals are processed 47,772,996,812 bytes, billed
  48,101,326,848 bytes, cache hits zero. The failed non-empty gate still
  corresponds to a completed provider job:
  `b6137fe5-0794-4bcf-9c2b-20938448f73b`, processed 389,923,594 bytes,
  billed 390,070,272 bytes, zero rows and no cache hit. Read-only job metadata
  is preserved in `docs/evidence/stage-a-v2-beneficiary-failed-job.json`.
  Counting that job once gives 75 physical executions, total processed
  48,162,920,406 bytes and billed 48,491,397,120 bytes.
- The new failure is a coverage decision, not an account-slot repair:
  `T_EXCHANGE_TO_DEX_FLOW` already has `expect_non_empty=false`.
  `T_TOKEN_AFTER_NATIVE_FUNDING`, `T_CROSS_EXCHANGE_FLOW` and
  `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE` also carry that flag; their outcomes
  cannot be inferred from this incomplete diagnostic. Before another full run,
  resolve the conflict between these coverage contracts and the v2 requirement
  for all 25 intents to be non-empty. Changing intent semantics, labels or
  acceptance criteria requires a new coverage decision.
- Both historical failure reports remain unchanged, billing remained
  disabled/unlinked, and all three accepted paths are absent. Diagnostic
  evidence does not authorize acceptance; final approval preflight remains
  pending a successful diagnostic on a newly approved coverage contract.

## Hard-intent coverage audit — 2026-10-14

- Audit đã kiểm tra cả `[2026-05-31, 2026-07-01)` với accepted labels live
  khớp dictionary local. Count exchange→DEX, cross-exchange và bridge deposit
  đều bằng 0 trên mọi ngày. Đổi subwindow trong phạm vi này không cứu được ba
  flow intents; bridge temporal join cũng rỗng vì deposits CTE rỗng.
- `T_TOKEN_AFTER_NATIVE_FUNDING` có historical V1 witness và positive-funding
  witness mới. Receipt lookup xác nhận funding thực sự thành công. Vì vậy
  không dùng `expect_non_empty=false` làm lý do thay cả bốn hard intents.
- Ba replacement prototypes có probe non-empty: net native flow theo owner,
  native recipient concentration và treasury token diversity. Phương án giữ
  25 intents / 1.000 records / 350–450–200 nhưng đổi ba training questions,
  làm chặt funding semantics và sửa CQ annotations; **chưa được duyệt hoặc
  implement**.
- Exact SQL/jobs/rows/caps nằm trong
  `docs/evidence/stage-a-v2-hard-intent-coverage-audit.json`; label snapshot
  readback nằm trong `docs/evidence/stage-a-v2-hard-intent-label-audit.json`.
  Bảy coverage/prototype executions processed 37.670.503.883 và billed
  37.672.189.952 bytes, cache hits 0; billing disabled/unlinked. Kết quả audit
  không authorize accepted publication.
- Báo cáo và migration/CQ proposal:
  `docs/research/stage-a-v2-hard-intent-coverage-audit-2026-10-14.md`.
  Current template/catalogue/candidate, historical V1, benchmark và accepted
  paths không thay đổi. Bước kế tiếp là user duyệt coverage proposal rồi chốt
  spec/plan trước implementation.

## Stage A v2 approved coverage implementation — 2026-10-14

- User đã duyệt keep-one/replace-three proposal; implementation và provenance:
  `docs/research/stage-a-v2-supported-intents-implementation-2026-10-14.md`.
- Catalogue training 1.1.0 thêm CQ31–CQ34; catalogue mặc định/historical 1.0.0
  và benchmark/model hashes giữ nguyên. CQ01–CQ30 không đổi nghĩa.
- Ba replacements và funding correction thay đúng 133 records. Candidate vẫn
  1.000 records, 25 intents, seed 42, difficulty 350/450/200; derive đúng
  206 logical groups / 126 physical queries. 200 bilingual patterns đã migrate;
  không publish canonical 8.000 records.
- Hai regeneration có bytes giống nhau. 1.442 tests pass; V1 và evidence pools
  giữ nguyên. Initial bounded preflight: 81.554.265.475 bytes, dưới cap 96 GiB;
  query lớn nhất 15.091.902.950 bytes, dưới cap 20 GiB.
- Diagnostic xác nhận non-empty cho cả bốn revised intents, nhưng dừng ở
  `T_LARGE_TX_TO_CLASS`, witness `syn-v2-000759`: native tới DEXProtocol >=1 ETH
  trong ngày 15/6 trả zero rows. 93 successful physical / 164 logical results;
  failed empty job thứ 94 được lưu metadata riêng, không retry.
- Report failed đã validate offline. Không chạy provider tiếp, không chạy final
  preflight và không tạo accepted artifacts. Bước kế tiếp đề xuất audit coverage
  và CQ mapping của intent medium này; final `--live` chưa sẵn sàng.
- Fresh review phát hiện hai guard defects: failed-report bỏ qua provenance và
  accepted manifest không chấp nhận dry-run ID rỗng của provider. Đã sửa bằng
  TDD, giữ execution IDs/non-empty gate nghiêm ngặt; final suite 1.462 tests pass.

## Stage A v2 large-class coverage/CQ audit — 2026-10-14

- User đã duyệt audit blocker `T_LARGE_TX_TO_CLASS`; báo cáo:
  `docs/research/stage-a-v2-large-class-coverage-audit-2026-10-14.md`, kèm
  CQ source audit riêng và machine-readable evidence.
- Trong 31 ngày catalogue, DEXProtocol không có native row >=0,01 ETH, nên
  không có window cứu được ngưỡng 1 ETH. Ngày 15/6, BridgeProtocol có 9 rows
  >=1 ETH, ExchangeAccount có 160; exact production SQL của cả hai đã có
  witness non-empty. Không rerun SQL thất bại.
- Đề xuất giữ SQL/1 ETH/window cũ, đổi class fill sang BridgeProtocol cho
  41 records, bỏ CQ21/CQ25 sai nghĩa và thêm CQ35 explicit qua revision 1.2.0;
  bảo toàn snapshots 1.0.0/1.1.0 và không claim lại bridge-flow CQ26.
- In-memory parameter-only counterfactual giữ 1.000 records, 25 intents,
  350/450/200 và 206 logical / 126 physical; không ghi candidate. Rà wording
  bilingual để không claim successful funds moved khi SQL chỉ lọc tx value.
- Bốn bounded audit executions, billing disabled/unlinked, cache/retries tắt:
  estimate 9.783.123.650 / cap 24 GiB; processed 9.742.808.678,
  billed 9.753.853.952, cache 0. Source inputs và prior evidence không đổi.
- Correction trên chờ approval riêng; audit không authorize implementation,
  full diagnostic, accepted publication, merge hoặc push.

Live witness verification:

```bash
uv run python scripts/09_generate_stage_a.py --live
```

## Live evidence — 2026-08-09

- Full preflight: 81 witness groups, estimate 61.855.311.688 bytes (57,61
  GiB), dưới total cap 96 GiB; max individual 14.368.179.853 bytes, dưới cap 20
  GiB.
- Execution: 81/81 witnesses pass, cache hit 0; processed 61.855.311.688 bytes,
  billed 61.918.412.800 bytes, total wall 196.993,36 ms. Max wall 20.107,53 ms
  tại witness `syn-000800` của `T_TOKEN_AFTER_NATIVE_FUNDING`.
- Proof propagation: 81 `live_exact` + 919 `live_limit_monotonic` = 1.000
  records có `non_empty=true`.
- Artifact audit: 1.000 unique IDs/SQL/record hashes; difficulty 350/450/200;
  max template 100; max entity 30; 16 included và 9 excluded templates.
- Final JSONL size 1.559.692 bytes; SHA-256
  `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`,
  khớp `generation-config.json`.
- Repository verification sau migration: 336 passed, 342 upstream warnings;
  Ruff check/format và `git diff --check` pass.

## Historical scaffold

Scaffold SPARQL ngày 2026-07-04 được giữ trong git history và hai design/plan
files có nhãn superseded. Evidence `3 passed` khi đó chỉ chứng minh offline
rendering, không còn là acceptance contract hiện hành.
