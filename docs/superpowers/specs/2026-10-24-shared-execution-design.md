# Shared exact-SQL execution và prediction failure isolation

Người dùng duyệt hai thay đổi protocol trong cuộc trò chuyện ngày 2026-10-24:
“Giữ SQL lỗi/vượt cap là failure, cho các truy vấn hợp lệ tiếp tục” và “Cho dùng
chung execution evidence của SQL giống hệt nhau giữa các runs”. Đây là duyệt
implementation/protocol, không phải final hash-bound live authorization.

## Thiết kế được triển khai

- Giữ nguyên native/canonical source artifacts, SQL, prompts/model/thresholds,
  N=100/run/language và 12 generation runs. Không tạo inference hoặc BigQuery jobs.
- Thêm shared campaign mode, artifact type riêng và sealed journal. Legacy
  execution artifact/schema vẫn đọc được; không ghi đè hoặc giả fresh jobs.
- Input campaign pin mọi canonical run hash, execution policy và source context
  SHA-256. Context là manifest được review của cùng batch nguồn/cấu hình; không
  tái sử dụng evidence xuyên campaign hoặc nhận cache/history làm input execution.
- Mỗi exact UTF-8 SQL chỉ có một physical outcome trong campaign. Nếu SQL dùng
  ở cả gold/prediction thì gold obligations ưu tiên; bất kỳ gold failure nào
  ngăn submissions tiếp theo. Logical refs vẫn giữ run/case/role riêng.
- Store ordered physical row digests để phục vụ cả ordered/unordered consumers;
  accuracy tuân theo ORDER BY của gold tại logical case, không mất duplicates.
- Initial và immediate dry-run vẫn có; không dùng survey cũ làm live preflight.
  Prediction validation errors/per-query caps giữ terminal failure và full N.
  Gold validation/guard failure, global caps, auth/quota/network errors, timeout/
  unknown cancellation hoặc unresolved submitted cost đều fail closed.
- Physical budget tính eligible unique queries; initial rejected predictions
  không làm poison aggregate reservation. Immediate rejected prediction release
  pending reservation; observed costs/bytes vẫn đối chiếu với pending estimates.
- Shared reporting nhận campaign trực tiếp, kiểm chứng exact run/SQL mapping,
  dùng results chung cho accuracy/answer metrics, nhưng không nhân physical
  latency/billing thành logical observations. Inference giữ riêng từng run.
  Comparison không xuất paired SQL-latency/cost từ observations dùng chung.
- Fake executor/fixtures luôn scientific blocked. Native scientific blockers,
  inference cost unmeasured và mọi unknown actual evidence không bị xóa.

## Phương án và giới hạn

Đã chọn explicit campaign thay vì cache trong từng run: cache sẽ dễ làm trùng
cost/latency và tạo execution artifacts trông như jobs mới. Không chỉ share gold,
không repair SQL hoặc tăng cap 24 GiB. Live runner phải yêu cầu actual disabled
billing, verified remaining free bytes/reservation và final config approval;
chưa đủ bằng chứng thì chỉ chuẩn bị config/hash và offline checks.

Workspace hiện tại có tài liệu/evidence chưa commit do công việc đã được duyệt.
Implementation làm tại đây, không chuyển/xóa/stash nguồn; chỉ sửa evaluation code,
focused tests và tài liệu liên quan. Không commit/push/public hóa trong task này.
