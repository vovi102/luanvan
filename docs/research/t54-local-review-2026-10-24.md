# T5.4-B — rà gói free-only và đồng bộ T5.5

Ngày 2026-10-24 (Asia/Saigon). Đọc worktree `main` trước khi sửa: gói duyệt
free-only và các cập nhật backlog/decision log/T5.4 đã có thay đổi chưa commit.
Giữ các thay đổi đó; bổ sung chỉ dẫn T5.5 theo handoff người dùng, không chạy
inference, BigQuery dry-run/live hoặc thay protocol.

## Thay đổi hiện hành

- [T5.5](../tasks/phase-5-baselines/05-pivot-decision.md) và
  [backlog](../planning/prioritized-backlog-2026-09-21.md) giữ B3 QLoRA là hướng
  chính cho RQ1. Scope-down vẫn train QLoRA, giảm sweep/phần không thiết yếu khi
  có bằng chứng thiếu tài nguyên. Bỏ B3 cần quyết định riêng của người dùng.
- Thêm entry tại [decision log](../memory/05-DECISION_LOG.md), giữ lịch sử định
  hướng cũ. Cấu hình/lịch B3 chưa được chốt và training chưa mở.
- Đánh dấu đề xuất 9 TiB/60 USD trong
  [checkpoint offline](t54-offline-2026-10-24.md) là lịch sử đã bị thay thế bởi
  gói free-only. Không sửa các frozen review inputs hoặc nguồn evidence.

## Kiểm chứng local mới

[Audit source](../evidence/t54-local-review-2026-10-24/audit.py) chỉ đọc local
artifacts và tái tạo offline trong bộ nhớ bằng `prepare()` hiện có; không gọi
executor/provider client. Chạy từ repo root:

```bash
PYTHONPATH=src .venv/bin/python docs/evidence/t54-local-review-2026-10-24/audit.py
PYTHONPATH=src .venv/bin/python scripts/19_nl2sql_evaluation.py validate docs/evidence/t54-offline-2026-10-23/canonical/*.json
git diff --check
```

[Kết quả audit](../evidence/t54-local-review-2026-10-24/verification.json) ghi
thời điểm UTC thật, SHA-256 audit source, manifest và ba inputs xin duyệt:

| Hạng mục | Kết quả |
|---|---|
| Review payload hash/size | 19/19 khớp |
| Frozen review inputs so với file hiện hành | 6/6 khớp |
| Provider source snapshots nén và nội dung giải nén | 4/4 khớp hash |
| Canonical codec và N=100/run | 12/12 hợp lệ |
| Exact SQL hash và static safety | 143/143; 100 gold + 43 predicted |
| Mapping đầy đủ, không trùng logical use | 1.200 gold + 129 predicted |
| Privacy worksheets và snapshot/policy bindings | 4/4, reviewer/time còn null |
| Approval template/ledger | Chưa ký; số dư chưa biết, không reservation |
| Tái tạo toàn gói offline | 15/15 files byte-identical trong bộ nhớ |
| Hai setup failures | Existing prepare kiểm tra 22 và 45 manifest entries |

Đây là integrity/reproducibility check local, không phải kiểm tra SQL trên
BigQuery, số dư quota mới hoặc execution evidence. Không đổi hash proposal,
policy, SQL scope hoặc 12 canonical runs. Không chạy lại full pytest vì không
thay implementation; kết quả full suite lịch sử không được gọi là test mới.

## Vướng mắc còn lại và phạm vi xin duyệt

Gói giai đoạn A đủ để người dùng review; chưa được cấp quyền chạy. Chỉ cần
quyết định thật về policy/egress/access/retention, reviewer identity và tối đa
143 exact-SQL dry-runs theo scope đã pin. Không ký thay hoặc backdate. Sau duyệt
mới tạo sidecars thật; canonical có privacy phải xuất sang thư mục mới, pin
hashes lại trước duyệt live riêng.

Số dư miễn phí và transitive dependencies phía dưới public views chưa xác minh.
Lịch live chưa khả thi để cam kết: với reservation hiện tại 768 GiB/run và
không tự release, hai reservations cần 1.536 GiB, lớn hơn mức danh nghĩa
1.024 GiB/tháng trong gói đã pin. Như vậy kế hoạch giữ nguyên reservation chỉ
đặt được tối đa một run mỗi kỳ có đủ allowance; 12 runs cần ít nhất 12 kỳ như
vậy. Đây là suy luận từ cấu hình, không phải lịch đã được duyệt hoặc xác nhận
quota/reset. Một số sources hết hạn 2026-12-09 UTC theo metadata snapshot.

Sau phase A cần rà lại estimates, quota authority, reservation và expiry/drift
để chuẩn bị phương án miễn phí cụ thể. Không tự giảm reservation, gia hạn
nguồn, reuse gold/materialize, đổi protocol hoặc chuyển sang trả phí. Nếu cần
đổi protocol phải trình đề xuất riêng. Trở ngại này không phải bằng chứng nên
bỏ B3 QLoRA.

Execution/answer metrics vẫn null, inference cost unmeasured; native latency
gate và scientific blockers giữ nguyên. Bước sau genuine execution vẫn là
sealed journals → bốn reports → comparison riêng EN/VI → failure analysis →
chốt kế hoạch B3 tại T5.5.
