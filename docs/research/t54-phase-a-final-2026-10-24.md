# T5.4-B — đủ 143 dry-runs và chẩn đoán lỗi

Ngày 2026-10-24 (Asia/Saigon). Người dùng nói “oke kiểm tra lỗi đii” để duyệt
44 SQL cuối và cho ghi lỗi compile rồi tiếp tục khảo sát. [Decision](../evidence/t54-phase-a-final-2026-10-24/decision.json)
ghi nhận lúc 07:32:52 UTC, bind proposal hash, reviewer role `conversation-user`.
Không hỏi lại tên cá nhân hoặc cấp quyền live.

## Kết quả khảo sát đầy đủ

Kiểm tra lại 85 payload/scope inputs của đợt trước; billing refresh vẫn tắt.
Gửi đúng 44 requests mới, không retry 99 SQL cũ: 42 estimates, hai lỗi compile
HTTP 404 được giữ nguyên và tiếp tục đúng policy đã duyệt. Endpoint/project/US,
exact SQL hashes, dry-run/cache/cap flags được chặn trước HTTP request; retries
tắt. Lưu 44 raw HTTP bodies và sealed hash-chain journal, không tải result rows.

| Toàn bộ ba đợt | Kết quả |
|---|---:|
| Unique SQL đã khảo sát | 143/143 |
| Gold có estimate / gold scope | 100/100 |
| Predicted có estimate / predicted scope | 40/43 |
| Predicted compile-error, estimate null | 3 |
| SQL chưa gửi | 0 |
| Unique SQL có estimate vượt 24 GiB | 1 predicted |
| Logical uses có estimate | 1.320: 1.200 gold + 120 predicted |
| Logical uses compile-error | 9 predicted |
| Logical uses chưa khảo sát | 0 |

[Combined estimates](../evidence/t54-phase-a-final-2026-10-24/combined-estimates.json)
và [1.329 logical rows](../evidence/t54-phase-a-final-2026-10-24/logical-estimates.jsonl)
giữ source hashes, language/run/case/role, canonical hashes cũ/mới và journal
nguồn. Dedup chỉ áp dụng preparatory estimates, không reuse live gold evidence.
100 câu/run/language, 12 runs và 14 attempted generation IDs không thay đổi.

## Lỗi và nguyên nhân

| Case B2 EN | Provider error | Đối chiếu SQL/metadata |
|---|---|---|
| `t35-006` | HTTP 404, `notFound` | Dùng `transaction_facts` như bảng, không có function arguments |
| `t35-015` | HTTP 404, `notFound` | Cùng lỗi relation kind |
| `t35-110` | HTTP 404, `notFound` | Cùng lỗi relation kind |

Metadata đã pin ghi `transaction_facts` là `TABLE_VALUED_FUNCTION`; AST của cả
ba SQL là plain table identifier, trong khi các function-call dry-runs khác
thành công. Thông báo provider “Table … was not found” không chứng minh routine
bị xóa. Giữ nguyên SQL/error và estimate null, không sửa benchmark, native
extraction status, prompt/model/threshold hoặc gọi những lỗi này là live failures.
Mỗi exact SQL có ba logical uses ở ba replicates, không phải ba requests mới.

Một finding khác ở **`t35-028` B2 EN**: estimate 30.470.124.008 bytes vượt
25.769.803.776 bytes (24 GiB). SQL dùng date window 2022-06-22 đến 2026-07-01,
vượt điều kiện <=31 ngày trong TVF definition đã pin; compile thành công không
chứng minh runtime thành công. Không gửi live để kiểm tra hoặc sửa date literals.

[Preparatory findings](../evidence/t54-phase-a-final-2026-10-24/preparatory-findings.json)
bind SQL/provider errors/AST observations/metadata và logical refs. Đây là chẩn
đoán của agent từ evidence, không phải human semantic-review sidecar hay sửa
failure taxonomy canonical.

## Estimates và giới hạn kế hoạch live

Các số dưới áp dụng **riêng mỗi replicate**, EN/VI không pooling:

| Nhóm | Gold estimates | Predicted estimates | Known component bytes/run |
|---|---:|---:|---:|
| B1 EN hoặc VI | 100/100 | 0 expected | 571.956.810.459 |
| B2 EN | 100/100 | 28/31; ba compile errors | 746.228.830.210 |
| B2 VI | 100/100 | 12/12 | 663.758.800.324 |

Tổng phần có estimate theo đủ logical uses là **7.661.703.754.356 bytes
(~6,968 TiB)**, gồm cả prediction vượt cap. Riêng gold 12 runs là
6.863.481.725.508 bytes (~6,242 TiB). Full raw campaign estimate vẫn null vì
chín logical uses compile-error không có estimate; không gán chúng scan/cost 0.
Đây không phải processed/billed bytes đã tiêu thụ hoặc invoice.

Một gold run có estimate 532,676 GiB; hai gold runs theo estimates này đã vượt
mức danh nghĩa 1.024 GiB/tháng. Reservation hiện tại 768 GiB/run cũng chỉ đặt
được tối đa một run trong một kỳ có đủ allowance nếu không release. Không
cam kết lịch đủ 12 runs trước expiry 2026-12-09; không tự gia hạn nguồn.

Monthly free balance vẫn chưa xác minh; daily quota limits không phải số dư
miễn phí. CLI19 initial aggregate guard còn chặn **toàn B2 EN run** nếu bất kỳ
request vượt per-query cap. Survey này không thay cap, guard hoặc protocol.
Do đó chưa có config live khả thi để xin duyệt; bước tiếp theo là chốt quota,
calendar và xử lý guard/protocol bằng quyết định riêng, giữ B3 QLoRA làm hướng
chính. Không tự bỏ fine-tuning vì các trở ngại BigQuery này.

## Kiểm chứng và trạng thái

[Aggregation/verifier](../evidence/t54-phase-a-final-2026-10-24/aggregate.py)
kiểm tra ba journals/seals, 143 scope indices không trùng, 118 raw responses
đợt sau, provider errors và đủ 1.329 logical keys. 25 estimates đầu là SDK
scalars, chưa lưu raw statistics; 115 estimates sau được đối chiếu raw bodies.
Ruff/format, local links, hashes và diff whitespace được kiểm tra; không sửa
implementation nên không chạy full pytest. Nguồn native, canonical cũ và bốn
privacy sidecars giữ nguyên.

[State](../../configs/t54/phase-a-final-state-2026-10-24.json) ghi survey đã hết
scope, không có request mới/live được cho phép. Khảo sát 143 SQL hoàn tất;
quota/live execution/reports/comparison và scientific acceptance chưa hoàn tất.
Execution/answer metrics vẫn null, inference cost unmeasured; mọi native
latency/scientific blockers được giữ nguyên.
