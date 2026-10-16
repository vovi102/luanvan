# Review benchmark Vietnamese — 10 batch × 10 câu

Trạng thái: **chờ human review**, 100 candidates, **0 human events** tại lúc tạo
pack. Pack là bản trình bày phục vụ review; không phải benchmark finalized.

1. Mở [batch-01.md](batch-01.md), đọc từng câu Vietnamese cùng SQL và metadata.
2. Với từng `pair_id`, ghi decision, bốn điểm và ghi chú trong
   [batch-01.csv](batch-01.csv), hoặc gửi kết quả trực tiếp trong chat. Ví dụ
   định dạng trả lời (mọi chỗ trống do bạn tự điền):
   `pair-t35-001 | decision=… | naturalness=… | sql_faithfulness=… | terminology=… | ambiguity=… | revised_question=… | notes=…`.
3. Tiếp tục các batch dưới đây. Không cần review lại 120 English candidates:
   English benchmark đã finalized, có human review và live evidence.
4. Sau mỗi batch, gửi phiếu hoặc các quyết định cụ thể để Codex đối chiếu hash,
   kiểm tra điểm/ID rồi append **đúng quyết định bạn cung cấp** vào log gốc.
   Phiếu CSV không phải event log và không được import ngầm. Không điền điểm,
   decision hoặc reviewer thay cho bạn; chỗ bỏ trống vẫn pending.

| Batch | Câu theo thứ tự snapshot | Phiếu |
| --- | --- | --- |
| [01](batch-01.md) | 1–10 | [CSV](batch-01.csv) |
| [02](batch-02.md) | 11–20 | [CSV](batch-02.csv) |
| [03](batch-03.md) | 21–30 | [CSV](batch-03.csv) |
| [04](batch-04.md) | 31–40 | [CSV](batch-04.csv) |
| [05](batch-05.md) | 41–50 | [CSV](batch-05.csv) |
| [06](batch-06.md) | 51–60 | [CSV](batch-06.csv) |
| [07](batch-07.md) | 61–70 | [CSV](batch-07.csv) |
| [08](batch-08.md) | 71–80 | [CSV](batch-08.csv) |
| [09](batch-09.md) | 81–90 | [CSV](batch-09.csv) |
| [10](batch-10.md) | 91–100 | [CSV](batch-10.csv) |

Decision: `ACCEPT`, `REVISE` hoặc `REJECT`. Điểm đều là số nguyên 1–5:
naturalness, SQL faithfulness và terminology càng cao càng tốt; ambiguity càng
thấp càng tốt. `ACCEPT` cần ba điểm đầu ≥4 và ambiguity ≤2. `REVISE` cần câu
sửa không rỗng, rồi một vòng review tiếp theo; quyết định cuối phải là ACCEPT.
`REJECT` giữ benchmark pending và cần xử lý rõ với bạn, không âm thầm thay câu
hoặc hạ threshold. Không thêm event sau ACCEPT. Mỗi pair bắt đầu round 1, các
round phải liên tiếp. Event log chỉ ghi `reviewer_role=user` khi chính bạn đã
cung cấp quyết định; không tạo tên hay danh tính reviewer giả.

Nguồn bất biến:
`data/review_drafts/t3_5_vi_candidate_set_2026-10-07/`.
[Manifest](manifest.json) bind cả candidate file SHA-256
`ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`,
semantic digest, hash từng file nguồn và từng file batch. Mỗi hàng CSV có ID và
hash dòng candidate gốc (gồm newline). Giữ hai cột này khi gửi phiếu; không sửa
candidate source hoặc SQL. REVISE được ghi qua event, giữ candidate gốc làm audit.

Training adapter/tests/export đã khóa tại `9adf02c` **trước khi mở nội dung
benchmark để soạn pack**. Benchmark wording/gold SQL không được dùng để sửa
training, prompt, retrieval, linker hay test nhằm nâng accuracy.

Lệnh offline kiểm tra draft hiện có (không kiểm tra hay tạo human decisions):

```bash
PYTHONPATH=src python scripts/22_vietnamese_testset_workflow.py validate-draft \
  --candidates data/review_drafts/t3_5_vi_candidate_set_2026-10-07/candidates.jsonl
```

`REVIEW_GUIDE.md` gốc mô tả đúng schema/điểm, nhưng tên lệnh `finalize` đã cũ.
CLI hiện dùng **`apply-review`** với explicit `--candidates` và `--review-events`
trỏ tới draft ngày 2026-10-07 (default CLI vẫn trỏ ngày 2026-10-04). Chỉ dùng
sau khi đủ 100 final ACCEPT. Trong lượt chuẩn bị pack này không chạy lệnh đó.
Sau review cần kiểm tra binding và live-evidence policy: tooling có thể tái sử
dụng English evidence khi SQL/metadata khớp hoàn toàn; nếu không, genuine live
verification cần một lượt được cho phép riêng. Không gọi live chỉ để soạn pack.

Nguồn `PREFLIGHT.md` ngày 2026-10-07 là lịch sử trước publication deterministic;
nhắc Gemini ở đó không mở lại hosted baselines hoặc external paraphrasing.

Builder lưu tại `docs/evidence/vietnamese-review-pack-builder-2026-10-16.txt`;
chạy từ repo root với Python để tái lập 20 file batch và manifest. Builder từ
chối overwrite phiếu đã sửa hoặc tạo lại sau khi log gốc có review events.
README này là hướng dẫn thủ công, không phải input acceptance.
