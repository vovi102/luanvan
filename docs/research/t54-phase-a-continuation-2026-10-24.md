# T5.4-B — tiếp tục dry-run, dừng ở compile-error đầu tiên

Checkpoint này giữ điểm dừng đợt hai. Sau phê duyệt tiếp, đã có
[kết quả đầy đủ 143 SQL và ba compile errors](t54-phase-a-final-2026-10-24.md).

Ngày 2026-10-24 (Asia/Saigon). Người dùng nói “oke” để duyệt 118 SQL còn lại,
cho ghi estimate vượt 24 GiB rồi tiếp tục khảo sát. [Decision](../evidence/t54-phase-a-continuation-2026-10-24/decision.json)
ghi nhận lúc 07:17:44 UTC, bind proposal hash, reviewer role `conversation-user`.
Không yêu cầu tên cá nhân thêm hoặc mở quyền live.

## Kết quả và điểm dừng

Kiểm tra lại 31 payload/sáu related inputs của đợt đầu, refresh billing vẫn tắt.
Chạy nối tiếp, HTTP/job/auth retries tắt; session từ chối SQL/hash/scope ngoài
118 requests đã pin và mọi request live. Source chạy lưu tại
[run.py.txt](../evidence/t54-phase-a-continuation-2026-10-24/operations/run.py.txt).

Đã gửi **74/118 requests**: 73 estimates, một HTTP 404. Dừng đúng rule
`dry_run_error` còn hiệu lực; 44 SQL chưa gửi, không retry 25 SQL cũ. Đợt mới
gồm original indices 25–98; request cuối kết thúc 07:21:05 UTC (14:21:05 giờ VN).
Không có live/result-row requests hoặc estimate vượt cap mới trong 73 SQL này.

Lỗi ở **prediction B2 EN, `t35-006`**, SHA-256
`bca620d09297f385c7b65f847e0e0d7160bf388cfa2542780575d27080d35622`.
BigQuery trả reason `notFound`, thông báo table `transaction_facts` không có ở
US. SQL tham chiếu object như bảng, không gọi function với arguments; metadata
đã pin ghi đây là `TABLE_VALUED_FUNCTION`, và các function-call dry-runs khác
đã thành công. Không suy ra routine bị xóa từ thông báo này. Giữ nguyên SQL,
error và estimate null; không đổi native extraction status hoặc sửa benchmark.

[Journal](../evidence/t54-phase-a-continuation-2026-10-24/dry-run-journal.jsonl)
có durable intents/outcomes và terminal seal. Lưu 74 raw HTTP bodies có hash,
gồm 73 estimates và 404 gốc; không log auth headers/tokens. Provider job metadata
giữ trong workspace/repository private đã duyệt, không push/public hóa.

## Hai đợt cộng lại

| Hạng mục | Số lượng |
|---|---:|
| Unique SQL đã gửi / scope | 99 / 143 |
| Có estimate | 98: 72 gold + 26 predicted |
| Compile-error, estimate null | 1 predicted |
| Chưa gửi | 44: 28 gold + 16 predicted |
| Logical uses có estimate | 942: 864 gold + 78 predicted |
| Logical uses compile-error | 3 predicted |
| Logical uses chưa khảo sát | 384: 336 gold + 48 predicted |

[Combined estimates](../evidence/t54-phase-a-continuation-2026-10-24/combined-estimates.json)
và [1.329 logical rows](../evidence/t54-phase-a-continuation-2026-10-24/logical-estimates.jsonl)
giữ run/case/role/language, SQL hash, canonical hashes cũ/mới và journal nguồn.
Tổng **thành phần estimates đã biết**, nhân theo logical uses, là
5.038.522.117.728 bytes (~4,58 TiB). Full campaign estimate vẫn null; đây không
phải observed processed/billed bytes, invoice hoặc execution accuracy.

Mỗi replicate B1 có 72/100 gold estimates; B2 EN có 72/100 gold và 18/31
prediction estimates, một compile-error, 12 prediction chưa khảo sát; B2 VI có
72/100 gold và 8/12 prediction estimates. Không pooling EN/VI hoặc ba replicates.
25 estimates đợt đầu là SDK-observed scalars, chưa lưu raw HTTP statistics;
73 estimates mới được đối chiếu với raw response statistics. Không gửi lại SQL
để bổ sung response cũ, không reuse bất kỳ live gold evidence nào.

## Verification, live blockers và bước tiếp theo

[Aggregation/verifier](../evidence/t54-phase-a-continuation-2026-10-24/aggregate.py)
kiểm tra hai hash-chains/seals, 99 identities không trùng, raw responses mới,
404 gốc và đủ 1.329 unique logical keys. [Kết quả](../evidence/t54-phase-a-continuation-2026-10-24/verification.json)
khớp số lượng trên. Ruff check/format và diff whitespace pass; không sửa
implementation nên không chạy lại full pytest. Nguồn native và canonical cũ
giữ nguyên. Scientific completion vẫn chưa đạt.

Monthly free balance còn null; daily quota limits không phải số dư miễn phí.
Chưa thể reserve/live hoặc cam kết lịch trước expiry 2026-12-09. Ngoài ra,
`execution.py` hiện bật initial `aggregate_blocked` nếu bất kỳ request vượt
per-query guard: prediction `t35-028` vượt 24 GiB đã biết sẽ chặn **toàn B2 EN
run** nếu estimates tương tự ở preflight mới. Không tự tăng cap, sửa executor,
gia hạn nguồn hoặc đổi protocol. Các blockers này không phải lý do bỏ B3 QLoRA.

[State mới](../../configs/t54/phase-a-continuation-state-2026-10-24.json) khóa
request sau điểm dừng. [Đề xuất 44 SQL cuối](../../configs/t54/phase-a-final-survey-proposal-2026-10-24.json)
chưa duyệt: giữ exact SQL và cap live; cho ghi compilation errors HTTP 400/404
với reasons `invalidQuery`/`notFound` rồi tiếp tục survey. Auth/permission/quota/
rate/network/hash/scope hoặc lỗi không phân loại vẫn dừng; không retry 99 SQL cũ.
Execution/answer metrics vẫn null, inference cost unmeasured, native blockers
giữ nguyên. Chỉ xin duyệt live riêng khi có phương án đầy đủ và reviewable.
