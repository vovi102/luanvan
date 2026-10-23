# T5.4 offline adaptation — kế hoạch và quyết định

**Spec:** yêu cầu tiếp tục của người dùng; `docs/tasks/phase-5-baselines/04-evaluation-framework.md`
và `docs/planning/kaggle-b12-benchmark-campaign-2026-10-18.md`.

**Mục tiêu:** xuất 12 CanonicalPredictionRun bằng adapter đã có, kiểm chứng
traceability và chuẩn bị gói duyệt BigQuery, hoàn toàn offline.

**Thiết kế:** giữ nguyên `b12-native-v1`/schema 1 và toàn bộ nguồn native.
Script `scripts/28_prepare_t54_offline.py` chỉ điều phối adapter, codec,
static SQL checks và immutable publication. Evidence mới nằm riêng tại
`docs/evidence/t54-offline-2026-10-23/`; báo cáo diễn giải nằm trong
`docs/research/t54-offline-2026-10-24.md`. Không tạo ExecutionEvidence giả.
So với sửa adapter/schema hoặc viết lại converter, tái sử dụng adapter hiện có
ít thay đổi và giữ nguyên semantics. Đây là lựa chọn triển khai của agent.

## Ràng buộc

- Chỉ worktree `feat/b12-benchmark-preparation`, base `583144e`; không sub-agent,
  commit/push/merge/PR, inference, model download hoặc job BigQuery (kể cả dry-run).
- 12 successes × 100 rows chỉ là inventory 1.200 predictions, không phải N=1.200
  cho thống kê; N=100/run/language. Hai setup failures không có accuracy denominator.
- Giữ raw output tại nguồn và hash từng case; không sửa SQL/prompt/model/retrieval,
  không sửa native blockers/readiness; không tune trên benchmark.
- Không tự ký privacy review hoặc điền pricing/project/location như đã được duyệt.

## Checklist thực hiện trực tiếp

- [x] Đọc nguồn và canonical contract; probe read-only adapter trên đủ 12 runs.
- [x] Test trước: xuất đủ 12/1.200 rows; raw/error/lineage và hai failures còn nguyên;
  reject source-hash mismatch, missing/duplicate run, changed ledger; immutable output.
- [x] Thêm script offline, chạy test red → green; không đổi core evaluation.
- [x] Xuất canonical + traceability + đối chiếu static/exact/structural, agreement
  từng nhóm; validate lại bằng CLI19 và kiểm tra reproducible bytes.
- [x] Chuẩn bị cấu hình BigQuery vô hiệu hóa mặc định, ngân sách đề xuất và
  privacy checklist cụ thể; phân biệt guard theo run và budget toàn chiến dịch.
- [x] Chạy kiểm thử liên quan/lint, rà diff và ghi kết quả mới vào báo cáo.

## Review focus

Source hash sai phải fail trước khi publish; replacement02 giữ nguyên identity;
VI source lineage không chuyển thành evidence BigQuery mới; prose/unsafe/invalid
giữ full denominator; output có sẵn không bị ghi đè. Test dùng artifact thật
trên đĩa, không gọi model/executor. Không chạy full suite chỉ để đọc tài liệu;
phạm vi kiểm thử cho script mới là các adapter, codec, SQL semantics, metrics và CLI.

## Ledger

Ruling: người dùng đã yêu cầu làm hết phần offline trước khi hỏi, nên thực hiện
trực tiếp kế hoạch này; không thêm vòng duyệt thiết kế/plan cho công việc đã ủy quyền.
Không dùng reviewer sub-agent theo yêu cầu rõ ràng; tự rà diff và evidence.

Hoàn tất kiểm chứng 2026-10-24 Asia/Saigon: 79 focused tests pass/35,14s,
Ruff pass, CLI validate 12 artifacts. Không đổi tracked source có sẵn.
Ruling: dùng all-three agreement trên 100 case; không dùng bootstrap của 300
pair-observations trong offline audit. Không sửa framework reporting/threshold.
Gói BigQuery giữ disabled; cap là đề xuất, không phải quyền chạy hoặc cost estimate mới.

Yêu cầu tích hợp ngày 2026-10-24: người dùng đã yêu cầu commit kết quả hiện có
và merge vào `main`. Yêu cầu này thay thế giới hạn không commit/merge của bước
chuẩn bị ban đầu, chỉ cho việc tích hợp local. Giữ branch và worktree, không push,
không bật BigQuery hoặc thay đổi native evidence/readiness.

Kiểm chứng trước tích hợp: full suite mới 1.617 passed/343 warnings trong
805,99s; log tại `docs/evidence/t54-merge-verification-2026-10-24/full-suite.log`.
Ruff check/format và CLI19 validate 12 canonical runs pass. Đích `main` tại
`ef3b66d` là tổ tiên của branch, nên tích hợp bằng fast-forward local.
