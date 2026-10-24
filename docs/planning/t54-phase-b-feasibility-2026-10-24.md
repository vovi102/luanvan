# T5.4-B — tính khả thi free-only sau khảo sát đầy đủ

Nguồn: [143-SQL survey và error diagnosis](../research/t54-phase-a-final-2026-10-24.md).
Đây là feasibility note, chưa phải live authorization, protocol mới hoặc config
executor. Không gửi query/live/DDL, materialize hay reuse evidence trong bước này.

## Bằng chứng và các blockers

- Privacy đã được người dùng duyệt; bốn sidecars và 12 canonical hashes mới có
  tại [mapping](../evidence/t54-phase-a-2026-10-24/privacy-bound-runs.json).
- Billing refresh vẫn disabled; paid spend authorized 0 USD. Monthly allowance
  còn lại chưa có bằng chứng authoritative; không reserve từ nominal 1 TiB.
- 143 SQL đã được dry-run một lần: 140 estimates và ba compile errors B2 EN.
  Giữ lỗi trong denominator, không repair SQL hoặc dùng estimated compile pass
  làm execution accuracy.
- Known scan components của protocol hiện tại khoảng 6,968 TiB, riêng gold
  khoảng 6,242 TiB. Một gold run khoảng 532,676 GiB, lớn hơn nửa nominal monthly
  allowance. Giữ nguyên estimates/data/protocol không cho phép hai complete
  runs trong một kỳ 1 TiB; reservation 768 GiB/run cũng chặn tương tự.
- Cap 24 GiB đang chặn toàn B2 EN run qua initial aggregate guard của CLI19.
  Không tự tăng cap hoặc sửa evaluator để làm kết quả đẹp hơn.
- Một số managed sources hết hạn 2026-12-09 UTC. Multi-period execution chưa
  có calendar khả thi; cần review expiry/data drift, không tự renew/recreate.

## So sánh số học để chuẩn bị quyết định riêng

Các biến thể dưới **chưa được thiết kế/duyệt**. Chỉ so known estimates của SQL
đã compile được; ba SQL lỗi vẫn null, không có live evidence được tạo/reuse.

| Biến thể | Known estimate components | Ý nghĩa |
|---|---:|---|
| Protocol hiện tại, gold riêng mỗi run | ~6,968 TiB | Không vừa một tháng nominal free allowance |
| Gold một lượt, predicted vẫn riêng từng run | ~1,246 TiB | Chỉ reuse gold vẫn chưa đủ để hứa một tháng miễn phí |
| Dedup cả gold và predicted exact SQL | ~0,762 TiB | Chỉ dưới nominal limit; đổi execution replicate semantics/journals/reports, không tự áp dụng |
| Materialization analytical slice | Chưa đo | Cần thiết kế, nguồn bất biến, storage/scan/egress và protocol approval riêng |

Các số giả định reuse/dedup không phải đề xuất đã chọn, không dùng làm campaign
budget/reservation và không biến evidence cũ thành execution evidence mới.
Vẫn cần current quota authority, headroom, estimates mới trước live, error/cap
handling được duyệt và giữ N=100/run/language.

## Phần tiếp theo có thể duyệt

Chưa yêu cầu bật live khi quota/cap/calendar còn chưa giải quyết. Trước live
phải chọn cách giữ hoặc thay protocol, có phương án expiry/drift và policy/config
hash mới, reservation + stop conditions theo free allowance đã xác minh. Mọi
thay đổi protocol cần tài liệu/đánh giá phương pháp riêng trước triển khai.
Giữ billing tắt, không đổi IAM/quota, tạo project né quota hoặc trả phí.

B3 QLoRA vẫn là mục tiêu chính của RQ1. Có thể chuẩn bị kế hoạch tài nguyên B3
offline trong lúc giải quyết execution; không lấy khó khăn quota làm lý do bỏ
fine-tuning hoặc tự mở thêm inference/training.
