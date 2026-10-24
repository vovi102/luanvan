# T5.5 — Chốt cấu hình và kế hoạch B3 QLoRA khả thi

## Mục tiêu

Dùng genuine B1/B2 metrics, linker deltas và bằng chứng tài nguyên để chốt cấu
hình/kế hoạch B3 QLoRA khả thi cho RQ1. B3 fine-tuning là hướng chính đã được
người dùng xác nhận; T5.5 chọn mức thực nghiệm và lịch triển khai. Target vẫn
là NL2SQL; quyết định này không mở lại Plan A.

## Phụ thuộc

- Stage A v2 accepted và T3.3 canonical published `2b652a3` (hoàn tất).
- T3.3 → B2 train-only integration `9adf02c` (hoàn tất offline): exact accepted
  fingerprint bind 7.208 consumed train records, không 792 development records.
- English và Vietnamese T3.5 finalized (hoàn tất); VI có 100 user ACCEPT events
  điểm 5/5/5/1 và exact reused English live evidence, zero new BigQuery jobs.
- B1/B2 chạy genuine với model/encoder revision đã pin.
- T5.4 tạo report canonical trên cùng test snapshot.
- Linker evaluation và calendar snapshot có bằng chứng.

## Đầu vào bắt buộc

- Execution/exact/structural accuracy và answer metrics của B1/B2.
- Latency, memory/OOM evidence và reproducibility của ít nhất ba compatible runs.
- Schema/entity/class-linker deltas trên evaluation protocol đã chốt.
- Thời gian và GPU budget còn lại, kèm thời điểm quan sát; không dùng quota cũ
  như số dư hiện tại. Ghi model/runtime, memory/OOM và dự kiến thời gian train
  từ bằng chứng phù hợp; phần chưa đo phải ghi rõ chưa xác minh.

## Phương án trong phạm vi đã chốt

1. **Full B3:** QLoRA, constrained generation và ablation đầy đủ.
2. **Scope-down B3:** khi có bằng chứng thiếu tài nguyên, train một cấu hình
   QLoRA, giữ component ablation quan trọng, giảm hyperparameter sweep hoặc phần
   thực nghiệm không thiết yếu. Vẫn phải có genuine fine-tuning và đánh giá B3
   có thể tái lập để trả lời RQ1.

Bỏ B3 là thay đổi phạm vi nghiên cứu, chỉ được xem xét khi người dùng quyết định
riêng; không phải lựa chọn mặc định của T5.5 và không được tự thay B3 bằng B2.

## Nguyên tắc quyết định

- Không tune threshold, prompt hoặc hyperparameter trên T3.5.
- Không dùng synthetic/fixture metrics làm scientific input.
- Negative result của B1/B2 là dữ liệu hợp lệ, không phải lý do sửa benchmark.
- Kết quả B1/B2 yếu và quota BigQuery không tự chứng minh nên bỏ fine-tuning.
- Nếu compute/timeline không đủ, ghi bằng chứng và ưu tiên scope-down vẫn giữ
  QLoRA. Nếu chưa tìm được cấu hình khả thi, báo phần còn thiếu và xin quyết
  định riêng về scope; không tự bỏ B3 hoặc reframe RQ1.
- Có thể rà tài nguyên và chuẩn bị kế hoạch offline trong lúc chờ T5.4-B;
  execution/answer metrics còn thiếu không được điền bằng kết quả static.
- Không tự mở inference/training hoặc gửi BigQuery jobs ngoài scope được duyệt.

## Đầu ra và acceptance

- [ ] `docs/pivot-decision-2.md` ghi snapshot, cấu hình QLoRA/kế hoạch B3, rationale,
  bằng chứng GPU/memory/timeline, phần chưa xác minh và scope-down nếu cần.
- [ ] Backlog Phase 6–7 được cập nhật theo lựa chọn.
- [ ] RQ1/contribution claims nhất quán với B0–B3 thực sự đã chạy.
- [ ] Có bản nháp note cập nhật GVHD; chỉ gửi khi người dùng yêu cầu riêng.

## Trạng thái

Todo; B3 QLoRA là hướng chính, chưa chốt cấu hình/lịch thực nghiệm. Data
integration và Vietnamese human review/finalization đã xong. Generation B1/B2
đủ 12/12 genuine runs và T5.4 offline hoàn tất. Privacy/giai đoạn A đã duyệt;
Đã khảo sát đủ 143 SQL (140 estimates, ba compile errors), giữ nguyên lỗi
và SQL. Còn verified free allowance, live cap/calendar/protocol feasibility,
duyệt live riêng, execution miễn phí và
reports/comparison T5.4-B trước khi chốt kế hoạch T5.5. Xem
[checkpoint giai đoạn A đầy đủ](../../research/t54-phase-a-final-2026-10-24.md).
B0 genuine 0/100 đã hoàn tất; B1/B2 local implementation không thay genuine
Kaggle evidence. Review pack hoặc offline tests không đóng scientific gate.
Không mở lại Stage D noise hoặc hosted LLM baselines.

Typed EN/VI consumer và runner đã implemented offline tại
[handoff 2026-10-16](../../research/b12-bilingual-consumer-2026-10-16.md).
Bằng chứng genuine phải giữ riêng language/snapshot và ba process replicates
mỗi (baseline, language). Fixture plumbing không phải đầu vào quyết định B3.
Thứ tự còn lại: T5.4-B execution/reports/comparison → chốt cấu hình/kế hoạch
B3 tại T5.5 → triển khai B3 và ablation trong scope được duyệt.

## Lịch sử định hướng — 2026-10-24

Ticket trước đây liệt kê full B3, scope-down B3 và bỏ fine-tuning ngang hàng.
Theo chỉ dẫn mới của người dùng, phần hiện hành giữ B3 QLoRA làm mục tiêu chính;
scope-down chỉ giảm sweep/phần không thiết yếu. Chưa có quyết định bỏ B3.
Xem [decision log](../../memory/05-DECISION_LOG.md) và
[backlog](../../planning/prioritized-backlog-2026-09-21.md).

## T5.4 shared protocol — cập nhật 2026-10-24

Đã duyệt hai thay đổi: cô lập prediction SQL lỗi/vượt 24 GiB thành failure và dùng
chung execution evidence cho exact SQL trong một campaign. Giữ N=100, EN/VI riêng,
12 generation runs và B3 QLoRA. Implementation/offline scope xem
[checkpoint shared protocol](../../research/t54-shared-protocol-2026-10-24.md).
Live vẫn chờ verified free allowance/reservation và final config/hash approval;
không dùng forecast ~752,10 GiB làm quota balance hoặc claim scientific complete.
