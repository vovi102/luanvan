# T5.4 — shared exact-SQL execution được duyệt

Người dùng duyệt trong cuộc trò chuyện ngày 2026-10-24: “Giữ SQL lỗi/vượt cap là
failure, cho các truy vấn hợp lệ tiếp tục” và “Cho dùng chung execution evidence
của SQL giống hệt nhau giữa các runs”. Reviewer dùng pseudonym `conversation-user`
như quyết định privacy trước đó; không ghi tên cá nhân hoặc suy đoán giờ gửi duyệt.
Đây là duyệt hai thay đổi protocol/implementation. Live BigQuery cần số dư miễn phí,
reservation và duyệt cấu hình/hash cuối cùng theo handoff ban đầu.

## Kết quả chuẩn bị offline

- 12 canonical runs có privacy, 1.200 cases; N=100/run/language giữ nguyên.
- 1.329 logical query uses ánh xạ vào 143 exact UTF-8 SQL: 100 gold và 43 prediction.
- Theo survey đã sealed: 139 SQL có estimate trong cap; 3 prediction compile errors,
  1 prediction vượt cap 24 GiB. Giữ đủ 12 logical failures tương ứng qua ba EN runs.
- Estimate cho 139 SQL: 807.560.696.067 bytes (~752,10 GiB). Sau conservative billing
  rounding hiện có: 807.635.255.296 bytes. Đây là forecast, không phải balance/invoice.
- Không gửi live queries hoặc chạy thêm inference trong bước triển khai này.

Config mới: [shared-campaign-2026-10-24.json](../../configs/t54/shared-campaign-2026-10-24.json).
Plan: [campaign-plan.json](../evidence/t54-shared-protocol-2026-10-24/campaign-plan.json).
Summary: [offline-preparation.json](../evidence/t54-shared-protocol-2026-10-24/offline-preparation.json).
Scope SHA-256: `590fdebee1a2143ca2de4e0e28806316b525730baf0cdbde467773cd5d3776e1`.

Đề xuất campaign cap mới 775 GiB processed/billed, gross-price-equivalent guard
4,75 USD, reservation 800 GiB gồm reserve 25 GiB. Giữ per-query 24 GiB, cache off,
sequential jobs. Những giới hạn campaign này chưa phải final live authorization;
không nâng paid spend khỏi 0 USD. Config để `allow_bigquery=false`, `live_approval=null`
và verified remaining allowance null. Mọi thay đổi quota snapshot/config tạo scope hash
mới và cần duyệt hash đó trước live; không sửa config cũ đã được manifest pin.

## Hành vi triển khai

`exact-sql-shared-v1` tạo một campaign artifact riêng: physical query outcomes và
logical run/case references. Cùng SQL dùng ở gold/prediction chỉ có một job; gold
obligation ưu tiên. Không nhập cache hoặc execution evidence từ campaign/history khác.

Runner thực hiện initial dry-run cho mọi unique SQL trước live và immediate dry-run
trước từng submission. Prediction static/known compilation failure hoặc per-query cap
failure là terminal failure, được loại khỏi pending reservation, các SQL hợp lệ tiếp tục.
Gold failure, global budget, auth/quota/network, timeout/unknown cancellation hoặc unknown
submitted billing đều dừng. Journal phải ghi bền trước submission; lỗi journal không được
chuyển thành prediction failure rồi tiếp tục. Job IDs gắn campaign và exact request.

Reporting chấm accuracy/answer metrics đủ N theo từng language/run, dùng ORDER BY của
logical gold và giữ duplicate rows. Cost/latency của SQL chỉ được tổng hợp ở physical
campaign scope, không nhân thành ba quan sát độc lập. Inference vẫn riêng từng generation
run. Các comparison shared không xuất paired SQL latency/cost. Legacy artifact/runner
được giữ cho protocol cũ; campaign mới phải dùng `execute-shared`.

## Lệnh kiểm tra và vận hành

Từ repo root, không cần credentials/network:

```bash
.venv/bin/python scripts/29_prepare_t54_shared.py
.venv/bin/python -m nl2sparql.evaluation.cli plan-shared \
  --config configs/t54/shared-campaign-2026-10-24.json \
  --output /tmp/t54-shared-plan-review.json
```

CLI `validate --journal` và `report --primary-evidence` nhận shared artifact thật;
replicate inputs có thể trỏ cùng campaign/journal, giữ canonical generation run riêng.
Không dùng plan/survey thay execution evidence.

Sau khi có actual verified allowance/billing/source snapshot mới, cần tạo config mới,
reserve đủ bytes, đặt validity window và final approval đúng scope. Live command là
`execute-shared --config ... --allow-bigquery --output ... --journal ...`; hiện config
chặn lệnh trước khi tạo credentials. Không bật billing hoặc thay IAM/quota để vượt gate.
Các managed source có expiry 2026-12-09; cần kiểm tra drift/expiry và dependencies trước live.
B3 QLoRA vẫn là hướng chính của RQ1; thay đổi execution không thay phạm vi fine-tuning.

## Kiểm tra hoàn tất

- Focused evaluation suite: 84 passed; toàn repo: 1.655 passed, 343 warnings, 808,93 giây.
- Ruff và `git diff --check`: pass. Fresh review phát hiện ba Important issues;
  cả ba đã tái hiện RED và sửa GREEN: global unknown billing readiness, runtime
  SQL reason classification và sequential journal verification. Không còn finding
  chưa xử lý trong review này.
- Offline fake rehearsal dùng đúng 143 SQL đã pin: 139 fake submissions, 3 compile
  failures, 1 guard failure; đủ 1.200 cases. Journal/CLI reports verify; cả bốn
  reports vẫn scientific blocked. Không coi fake results là metric nghiên cứu.
- Kiểm tra lại 191 historical payloads, 6 frozen snapshots và 16 related inputs:
  hashes/sizes đúng. Không viết lại evidence cũ.
- [Bằng chứng verification](../evidence/t54-shared-protocol-2026-10-24/verification.json)
  và [review/fixes](../evidence/t54-shared-protocol-2026-10-24/review-and-fixes.json).

Giữ workspace hiện tại để bảo toàn nguồn chưa commit; không commit/push. Duyệt
conversation đã đủ để triển khai hai thay đổi, nên không hỏi lại duyệt plan.
Việc chạy live vẫn chờ actual monthly allowance/reservation và final scope/hash;
không suy diễn duyệt protocol thành duyệt live. Giá trị 775/800 GiB còn là đề xuất.
