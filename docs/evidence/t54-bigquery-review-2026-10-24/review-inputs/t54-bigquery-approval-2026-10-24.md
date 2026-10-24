# T5.4-B — gói duyệt BigQuery chỉ dùng miễn phí

Chuẩn bị ngày 2026-10-24 (Asia/Saigon), theo yêu cầu hoàn thiện gói duyệt và tận
dụng BigQuery miễn phí. Phạm vi task là chuẩn bị/review; chưa chạy dry-run hoặc
live query, không đổi billing/IAM/quota hay protocol evaluation.

## Quyết định và bằng chứng

Không cần duyệt khoản chi 60 USD để dùng sandbox. Cấu hình mới đặt
`paid_spend_authorized_usd=0.00`, giữ billing tắt. Đề xuất 9 TiB/60 USD cũ chỉ
được giữ trong [historical-paid-proposal.json](../evidence/t54-bigquery-review-2026-10-24/historical-paid-proposal.json),
không còn là phương án thực thi active.

- `gcloud billing projects describe`: project `nl2sparql-thesis`,
  `billingEnabled=false`; [billing evidence](../evidence/t54-bigquery-review-2026-10-24/billing.json).
- GET dataset: location `US`, default expiry 60 ngày. Sáu direct SQL objects
  tồn tại; metadata inventory mở rộng ra 13 objects. Public views không trả
  definition, nên transitive dependencies phía dưới các views đó chưa xác minh.
  Label snapshot/view và token dimension hiện hết hạn ngày 2026-12-09 UTC;
  không tự gia hạn. [Metadata](../evidence/t54-bigquery-review-2026-10-24/metadata.json).
- GET `jobs.list`, all-users/full projection và hết pagination: 675 jobs,
  không thấy job chưa terminal, không thiếu billed count cho query jobs.
  Cửa sổ từ 2026-09-30 UTC đến lúc quan sát; mọi job trả về đều thuộc tháng 10.
  Tổng processed 1.457.494.173.013 bytes, billed 1.459.720.552.448 bytes.
  Đây là gross historical bytes, **không phải số dư miễn phí hoặc hóa đơn**;
  không biết billing ở thời điểm từng job. Không suy ra còn quota hoặc đã bị
  tính phí từ các con số này. [Usage summary](../evidence/t54-bigquery-review-2026-10-24/usage-summary.json).
- `projects.testIamPermissions` trả 403; chưa chứng minh thiếu quyền
  `bigquery.jobs.create`. Metadata read thành công không chứng minh SQL sẽ chạy;
  dry-run sẽ kiểm tra quyền/compile theo từng query.
  [Permission probe](../evidence/t54-bigquery-review-2026-10-24/permissions.json).

Các nguồn web chính thức được tải và hash-pin trong
[source manifest](../evidence/t54-bigquery-review-2026-10-24/sources/manifest.json).
Snapshot time lưu UTC; ngày tài liệu dùng Asia/Saigon.

## Miễn phí và giới hạn bytes

Sandbox không yêu cầu billing account/thẻ và có 1 TiB query processing mỗi
tháng. Giới hạn này không phải miễn phí không giới hạn. Sandbox còn giới hạn
storage và tự hết hạn tables/views/partitions sau 60 ngày.
[Google sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox).

Dry-run không bị tính phí và không dùng query slots. Vì vậy bước duyệt tiếp
theo có thể chỉ là dry-run để lấy scan estimates; không cần chấp nhận khoản
chi trả phí. [Google dry-run](https://docs.cloud.google.com/bigquery/docs/running-queries).

Giá on-demand USD niêm yết được pin là 6,25 USD/TiB ở phần vượt free allowance.
Giữ giá dương làm **gross list-price equivalent** cho guard/so sánh; không đặt
giá/TiB bằng 0 để giả lập miễn phí. CLI19 hiện yêu cầu price/cost cap dương và
không theo dõi free allowance. Giá quy đổi không phải invoice charge.
Billing floor theo bảng/query và rounding phải được cân nhắc; estimator hiện
chỉ có floor/query nên không chứng minh đủ mọi trường hợp multi-table.
[Google pricing](https://cloud.google.com/bigquery/pricing).

Full protocol chưa đổi: tối đa 1.200 gold + 129 predicted = 1.329 live queries,
hai dry-runs mỗi logical query trong CLI19, không reuse live gold cross-run.
Lấy 559.594.602.496 billed bytes của B0 gold lịch sử nhân 12 cho khoảng
6,107 TiB **chỉ phần gold**; đây là ngoại suy, chưa phải current estimate.
Không thể hứa full campaign nằm trong một tháng miễn phí.

Phương án giữ protocol là chia các complete runs theo quota thực tế, có thể qua
nhiều tháng. Chưa lịch hóa vì source expiry, dữ liệu public thay đổi và quota
chưa xác minh; không ghép partial runs hoặc thay live gold bằng evidence cũ.
Phương án giảm scan qua gold reuse/materialization cần thiết kế và duyệt protocol
riêng; chưa triển khai. Không tạo billing project mới để né quota.

## Nội dung duyệt giai đoạn A — dry-run miễn phí

[Proposal](../../configs/t54/b12-bigquery-review-proposal.json) còn
`allow_dry_run=false`, `allow_bigquery=false`. Scope exact SQL được pin tại
[dry-run-scope.json](../evidence/t54-bigquery-review-2026-10-24/dry-run-scope.json):

- Project `nl2sparql-thesis`, location `US`, GoogleSQL, query cache off.
- Tối đa **143 dry-run requests**, không retry tự động: 100 unique gold SQL và
  43 unique predicted SQL, bind exact SQL SHA và mọi run/case reference trong
  12 canonical runs. Chỉ deduplicate estimate theo exact SQL bytes.
- Không có live query, result-row download, inference, DDL/DML, thay đổi
  billing/quota/IAM hoặc gia hạn table. Mọi request bắt buộc `dry_run=true`.
- `maximum_bytes_billed=24 GiB` được ghi tường minh; dry-run report chỉ là estimate,
  chưa phải quyền gửi live query. Nếu estimate lớn hơn cap hoặc có lỗi, ghi lại
  và dừng; không tăng cap, sửa SQL hoặc gửi query để kiểm tra.
- Kết quả cần ghi cho từng SQL: source hash, UTC, project/location, compile/error,
  estimate, version client; nhân estimate lại đúng 1.329 logical uses cho plan
  toàn campaign. Không lấy tổng 143 estimates làm scan của cả 12 runs.
- Unknown/zero estimates, đặc biệt row-level security hoặc opaque dependency,
  không được coi mặc định là query miễn phí; cần review trước live.

## Privacy đã chuẩn bị để ký

[Policy](t54-bigquery-privacy-policy-2026-10-24.md) nêu egress lịch sử tới Kaggle,
SQL/literals tới BigQuery, quyền đọc và lưu giữ journals/results. Bốn
[worksheets](../../configs/t54/privacy-review-drafts.json) điền sẵn
`data_egress=provider`, provider scope và policy hash, giữ baseline/snapshot hashes.
`reviewer_id` và `reviewed_at` để null cho quyết định thật của reviewer;
không giả lập review đã ký. Sau duyệt, publish sidecars thật và re-adapt vào
thư mục mới, pin hashes mới trước live execution.

## Điều kiện giai đoạn B — live execution, chưa duyệt

1. Hoàn tất privacy review, canonical sidecars và hashes mới. Refresh billing
   metadata ngay trước chạy; nếu billing bật thì dừng, không tự unlink/bật/tắt.
2. Có dry-run estimates và kiểm tra quota hiện tại; số dư free tier chưa biết
   thì không tự điền 1 TiB. Refresh GET jobs metadata và đối chiếu quota platform;
   historical job totals chỉ là kiểm tra chéo, không phải quota authority.
3. Chọn complete run tiếp theo theo thứ tự đã pin và reserve 768 GiB processed
   và billed từ allowance đã xác minh. CLI guard tối đa 744 GiB/run và
   24 GiB/query để giữ headroom cho job cuối. Chạy một run mỗi lần, không tự
   release reservation/retry; nếu số dư không đủ thì chờ, không nâng cấp billing.
   Reservation ledger chưa có balance/event thực vì chưa live.
4. USD guard 4,75/run chỉ là gross list-price equivalent, không phải quyền chi.
   Duyệt live riêng theo final config hash; chuẩn bị execution ID/journal mới,
   chạy CLI19 nguyên contract. Không dùng gói duyệt này như CLI executor config.
5. Khi gold lỗi, quota/cap/policy chặn, timeout/cancel không rõ, billing chưa
   resolved, thiếu terminal seal hoặc người dùng dừng: ngừng submit; giữ job IDs,
   đối chiếu terminal metadata, không chạy tiếp để lấy kết quả khác. Query lỗi
   predicted giữ nguyên denominator. Hết quota không chuyển sang trả phí.
6. Sau mỗi complete run, validate sealed journal/evidence. Reports giữ primary
   r01, replicates r02/r03, B2 EN r03 replacement02, N=100; EN/VI riêng biệt.
   Nếu chạy qua nhiều tháng, báo thời gian/data drift; không claim cùng data
   snapshot chỉ vì SQL hash trùng nhau. Giữ mọi native latency/scientific blockers.

## Nội dung quyết định còn lại

Người dùng có thể duyệt **policy privacy và 143 dry-runs trong giai đoạn A**,
cung cấp reviewer identity và đồng ý retention/access scope đã viết. Agent ghi
thời gian UTC đúng lúc nhận quyết định, không backdate. Quyết định này không
cho phép live query. Giai đoạn B sẽ được chốt sau khi có estimate/quota, không
yêu cầu chấp nhận khoản chi 60 USD.

[Mẫu quyết định chưa ký](../../configs/t54/phase-a-approval.template.json) pin
SHA-256 proposal, policy và SQL scope; không phải authorization đã ghi nhận.
[Manifest gói review](../evidence/t54-bigquery-review-2026-10-24/manifest.json)
giữ hashes của evidence và các bản sao cấu hình/tài liệu tại lúc chuẩn bị.
