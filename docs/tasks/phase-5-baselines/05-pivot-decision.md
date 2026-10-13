# T5.5 — Quyết định phạm vi fine-tuning

## Mục tiêu

Dùng genuine B1/B2 metrics, linker deltas và tiến độ thực tế để chọn một trong
ba hướng: full B3, B3 scope-down, hoặc full-system không fine-tune. Target vẫn
là NL2SQL; quyết định này không mở lại Plan A.

## Phụ thuộc

- T3.3 training artifact accepted và T3.5 benchmark finalized.
- B1/B2 chạy genuine với model/encoder revision đã pin.
- T5.4 tạo report canonical trên cùng test snapshot.
- Linker evaluation và calendar snapshot có bằng chứng.

## Đầu vào bắt buộc

- Execution/exact/structural accuracy và answer metrics của B1/B2.
- Latency, memory/OOM evidence và reproducibility của ít nhất ba compatible runs.
- Schema/entity/class-linker deltas trên evaluation protocol đã chốt.
- Thời gian và GPU budget còn lại.

## Phương án

1. **Full B3:** QLoRA, constrained generation và ablation đầy đủ.
2. **Scope-down B3:** train một cấu hình QLoRA, giữ component ablation quan trọng,
   bỏ hyperparameter sweep không thiết yếu.
3. **Drop fine-tuning:** dùng B2 + linkers + SQL validator/constrained generation
   làm full system; báo B3 là out of scope và reframe RQ1 tương ứng.

## Nguyên tắc quyết định

- Không tune threshold, prompt hoặc hyperparameter trên T3.5.
- Không dùng synthetic/fixture metrics làm scientific input.
- Negative result của B1/B2 là dữ liệu hợp lệ, không phải lý do sửa benchmark.
- Nếu compute/timeline không đủ tạo genuine B3 và ablation có thể tái lập, chọn
  scope-down hoặc drop fine-tuning sớm.

## Đầu ra và acceptance

- [ ] `docs/pivot-decision-2.md` ghi snapshot, lựa chọn và rationale.
- [ ] Backlog Phase 6–7 được cập nhật theo lựa chọn.
- [ ] RQ1/contribution claims nhất quán với B0–B3 thực sự đã chạy.
- [ ] Có note/email cập nhật GVHD.

## Trạng thái

Todo; chờ genuine B1/B2 evidence.
