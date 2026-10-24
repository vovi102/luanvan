# T5.4-A — NL2SQL Evaluation Framework

## Mục tiêu

T5.4-A cung cấp framework offline-first để chuẩn hóa, kiểm chứng và so sánh bằng
chứng của các baseline NL2SQL B0, B1, B2 và B3. Framework đo sáu chiều:
accuracy, latency, cost, privacy, reproducibility và failure modes. Đây là task
triển khai công cụ; việc tạo và diễn giải kết quả khoa học thật thuộc T5.4-B.

## Phạm vi và phụ thuộc

- Đầu vào gold là snapshot T3.5 đã review, chứa GoogleSQL cho BigQuery.
- Prediction và log native đến từ T5.1–T5.2 và T6.1; adapter không tin các metric tổng
  hợp sẵn trong report native.
- T5.4-A không chạy baseline inference, không tạo kết luận nghiên cứu và không
  tự động truy cập BigQuery.
- T5.4-B sở hữu genuine runs, live execution evidence, bảng kết quả và phân tích
  luận văn sau khi snapshot T3.5 được chốt.

## Artifact và module

Các artifact canonical là immutable JSON có schema version và SHA-256 tự ràng
buộc. Journal execution là canonical JSONL hash-chain, fsync sau mỗi record và
chỉ được chấp nhận khi có terminal seal.

- `CanonicalPredictionRun`: test-set identity, provenance, privacy và đủ mọi case.
- `ExecutionEvidence`: policy, executor provenance, dry-run/live outcomes và
  terminal journal hash.
- `EvaluationReport`: primary run tường minh, replicate identities, six
  dimensions, breakdowns và readiness.
- `ComparisonReport`: paired left-minus-right deltas; không có winner/ranking.
- `PrivacyReview`: sidecar review được hash-bind với baseline và test snapshot.

Mã nguồn nằm trong `src/nl2sparql/evaluation/`; entry point là
`scripts/19_nl2sql_evaluation.py`.

## Workflow an toàn

Các lệnh help và validate chỉ đọc local artifact, không khởi tạo credential,
BigQuery client hay network:

```bash
uv run python scripts/19_nl2sql_evaluation.py --help
uv run python scripts/19_nl2sql_evaluation.py validate \
  data/eval/canonical/b0-run.json
uv run python scripts/19_nl2sql_evaluation.py report --help
uv run python scripts/19_nl2sql_evaluation.py compare --help
```

Adapter nhận input native riêng cho từng baseline:

```bash
uv run python scripts/19_nl2sql_evaluation.py adapt b0 \
  --test-set data/dataset/test/test-100.jsonl \
  --predictions data/eval/b0/predictions.jsonl \
  --report data/eval/b0/report.json \
  --run-id b0-run-01 \
  --output data/eval/canonical/b0-run-01.json
```

Live execution luôn yêu cầu `--allow-bigquery` cùng project, location, timeout,
per-query/aggregate byte caps, estimated USD cap và pricing policy đã pin. Không
có giá trị mặc định ngầm cho live cost guard:

```bash
uv run python scripts/19_nl2sql_evaluation.py execute \
  --prediction-run data/eval/canonical/b0-run-01.json \
  --execution-id b0-exec-01 \
  --journal data/eval/evidence/b0-exec-01.jsonl \
  --output data/eval/evidence/b0-exec-01.json \
  --allow-bigquery \
  --executor bigquery \
  --project <gcp-project> --location <location> \
  --timeout-seconds <seconds> \
  --per-query-byte-cap <bytes> --aggregate-byte-cap <bytes> \
  --aggregate-billed-byte-cap <bytes> \
  --estimated-cost-cap <usd> \
  --pricing-id <policy-id> --price-per-tib <usd> \
  --pricing-source-sha256 <64-lowercase-hex>
```

Đây là thao tác live thủ công, có thể phát sinh chi phí. CI, test và tài liệu
không được thêm `--allow-bigquery`.

## Semantics

### Accuracy và denominator

- Exact match dùng canonical GoogleSQL; structural match bỏ khác biệt alias nhưng
  giữ literal và cấu trúc typed.
- Execution comparison giữ thứ tự khi gold có `ORDER BY`; trường hợp còn lại là
  multiset, không làm mất duplicate.
- Exact, structural, execution accuracy và macro answer precision/recall/F1 dùng
  full denominator `N` của snapshot. Missing, invalid, unsafe, timeout,
  guard-blocked và execution-error đều ở lại denominator với điểm 0.
- Nếu bất kỳ gold execution nào lỗi, execution và answer numerator/value/CI là
  null cho toàn report; framework không công bố partial-success accuracy.

### Bootstrap và breakdown

Mặc định là 10,000 bootstrap samples, seed 42, percentile CI 95%. Resampling theo
case index. Difficulty groups không chồng lấp; category groups có thể chồng lấp.
Mọi ratio giữ numerator, denominator, value và interval.

### Latency và cost

Inference, predicted-query execution và gold-query execution được báo riêng với
expected/observed/missing counts cùng P50/P95/P99. Skipped query không được gán
latency 0.

Inference cost và BigQuery cost là hai nhánh riêng. Billed bytes quan sát được có
thể dùng để tạo estimated on-demand USD theo billing floor/rounding đã pin; nó
không được gọi là observed invoice charge. Submitted job chưa rõ billing giữ
`unmeasured`/`unresolved`, không được bịa thành 0. Local inference thiếu billing
evidence cũng là unmeasured, không mặc định USD 0.

### Privacy, reproducibility và failure modes

- Privacy lấy từ sidecar được hash-bind; thiếu review là scientific blocker.
- Reproducibility tính agreement trên mọi cặp run tương thích. Có thể tính từ hai
  run, nhưng scientific readiness cần ít nhất ba genuine runs.
- Failure classification là multi-label. Automated classifier chỉ dùng facts có
  bằng chứng như `wrong_relation`, `wrong_filter`, `timeout` và
  `answer_mismatch`; `semantic_drift` chỉ đến từ manual review sidecar.

## Readiness

`implementation_status=ready` nghĩa là artifact hoàn chỉnh và integrity-valid;
nó không khẳng định nghiên cứu đã hoàn tất. `scientific_status=ready` chỉ đạt khi
không còn blocker, bao gồm finalized T3.5 provenance, privacy evidence, ba genuine
compatible runs, non-fake executor, gold execution hợp lệ và resolved submitted
cost.

Synthetic fixtures và scripted executor được phép chứng minh pipeline với
`implementation_status=ready`, nhưng luôn giữ `scientific_status=blocked`.

## Acceptance criteria T5.4-A

- [x] Strict canonical codecs, immutable publication và tamper detection.
- [x] Adapter B0/B1/B2 kiểm tra cross-file identity; B3 phải dùng cùng canonical
  contract khi T6.1 được triển khai.
- [x] GoogleSQL/result semantics giữ order, type và duplicate multiplicity.
- [x] Double dry-run, fail-closed aggregate/cost guards và explicit BigQuery opt-in.
- [x] Deterministic six-dimension report, breakdown và paired comparison.
- [x] Offline CLI/help/validate không truy cập credential hoặc network.
- [x] Synthetic end-to-end pipeline có implementation ready và scientific blocked.
- [ ] Genuine baseline artifacts, live BigQuery execution và scientific tables —
  thuộc T5.4-B, không phải completion gate của T5.4-A.

## Trạng thái

Implementation T5.4-A: complete khi toàn bộ test/lint/format gates của branch pass.
Scientific completion: no; chờ T5.4-B và external evidence thật.

## B1/B2 paired Vietnamese boundary — 2026-10-16

Native B12 adaptation accepts explicit `--language en|vi`; VI reuses the strict
typed finalized snapshot authority, not the English `nl` schema. It checks native
language, original case/pair/source identities, exact reused gold evidence and
cross-file paired lineage. Source refs and fingerprints retain the paired-source
binding and language; test snapshot hashes remain distinct. Prompt fingerprints
are bound as an ordered list because each complete prompt contains a different
question. EN's legacy native artifacts remain readable; current artifacts carry
per-case log and report prompt bindings. No metrics/threshold or prompt changes.
Three compatible genuine runs are required for each baseline **within each
language**; EN and VI never share the same denominator. This offline plumbing
change does not provide genuine inference, predicted-query execution, privacy,
cost or comparison evidence. See [handoff](../../research/b12-bilingual-consumer-2026-10-16.md).

## T5.4-B checkpoint — 2026-10-24

Đủ 12 genuine generation runs và 12 canonical offline artifacts; execution và
comparison chưa hoàn tất. [Gói duyệt BigQuery free-only](../../planning/t54-bigquery-approval-2026-10-24.md)
đã chuẩn bị theo yêu cầu người dùng: project `nl2sparql-thesis`, dataset US,
billing tắt, paid spend 0 USD. Giai đoạn A đề xuất 143 unique-SQL dry-runs miễn
phí, chưa được duyệt; bốn privacy worksheets đã điền scope/policy hash nhưng
chưa ký. Không có live/dry-run job mới trong bước chuẩn bị này.

Giữ positive list-price policy/cost guards của CLI19 với semantics gross
equivalent, không giả lập giá 0 hoặc invoice cost. Quota sandbox còn lại chưa
biết; dry-run estimates và verified free allowance cần có trước duyệt live
riêng. Không reuse gold evidence, sửa SQL/denominator, claim scientific ready
hoặc tự nâng cấp billing để hoàn tất campaign.

## Giai đoạn A sau phê duyệt — 2026-10-24

Người dùng đã duyệt privacy/dry-run, không yêu cầu tên reviewer; ghi vai trò
`conversation-user` và nguồn quyết định thật. Bốn privacy sidecars và 12
privacy-bound runs mới validate hợp lệ, giữ bản offline cũ. Dry-run dừng đúng
policy ở request 25 vì estimate 30.470.124.008 bytes vượt cap 24 GiB; 118 SQL
chưa gửi, không retry/live. Quota API đọc được daily limits, monthly free
balance vẫn null. [Evidence và đề xuất tiếp tục](../../research/t54-phase-a-2026-10-24.md)
chưa cho phép thêm requests hoặc thay cap/protocol live.

Sau phê duyệt tiếp, tổng 99 SQL đã khảo sát (98 estimates, một compile-error);
44 SQL chưa gửi do đợt mới dừng đúng rule `dry_run_error`. Có 74 raw HTTP
responses và đủ mapping 1.329 logical uses; full estimate/monthly allowance
còn null. [Checkpoint mới](../../research/t54-phase-a-continuation-2026-10-24.md)
giữ lỗi/SQL nguyên trạng, chưa duyệt survey cuối hoặc live.

Sau duyệt survey cuối: đủ 143 unique SQL đã khảo sát, 140 estimates và ba
compile errors B2 EN (TVF được dùng như bảng), không còn SQL chưa gửi. Có đủ
1.329 logical refs: 1.320 có estimate, chín compile-error refs giữ null. Một
prediction vượt 24 GiB; CLI19 initial guard hiện chặn toàn run tương ứng nếu
preflight mới tương tự. [Kết quả cuối giai đoạn A](../../research/t54-phase-a-final-2026-10-24.md)
và [live feasibility](../../planning/t54-phase-b-feasibility-2026-10-24.md)
không cấp quyền live hoặc thay protocol; quota tháng và scientific gates còn mở.

## T5.4 shared protocol — cập nhật 2026-10-24

Đã duyệt hai thay đổi: cô lập prediction SQL lỗi/vượt 24 GiB thành failure và dùng
chung execution evidence cho exact SQL trong một campaign. Giữ N=100, EN/VI riêng,
12 generation runs và B3 QLoRA. Implementation/offline scope xem
[checkpoint shared protocol](../../research/t54-shared-protocol-2026-10-24.md).
Live vẫn chờ verified free allowance/reservation và final config/hash approval;
không dùng forecast ~752,10 GiB làm quota balance hoặc claim scientific complete.
