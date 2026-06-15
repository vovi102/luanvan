# T5.5 — Pivot Point #2 (Last Resort, Mid-Month 4)

## Mục tiêu

Quyết định cuối cùng: tiếp tục Plan A (NL2SPARQL) hay pivot sang scope giảm. Đây là **last resort** — chỉ trigger khi B1 baseline quá tệ hoặc trễ tiến độ ≥3 tuần.

## Bối cảnh & lý do

Khác Pivot Point #1 (cuối tháng 2, pivot sang NL2SQL toàn phần), Pivot Point #2 đã quá muộn để đổi target language. Các option ở đây nhỏ hơn:

**Option 1:** Tiếp tục Plan A như planned.
**Option 2:** Scope down dataset (1000 → 500 cặp), giảm số baselines (6 → 4), focus quality.
**Option 3:** Drop fine-tuning (B3) hoàn toàn, focus vào contribution 1 (dataset) + contribution 2 (linking) + report B1-B5 với schema/entity linking.

## Phụ thuộc

- T5.1-5.4 — Tất cả baselines + evaluation framework đã có.
- T3 — Dataset đã hoàn tất hoặc partial.

## Đầu vào

- B1 baseline metrics.
- Schema linker improvement metric (schema-link-on vs schema-link-off).
- Calendar timeline status.

## Đầu ra

- Document `docs/pivot-decision-2.md`.
- Updated timeline cho Phase 6+7.

## Acceptance criteria

- [ ] Document có decision (continue / scope-down / drop-FT) + rationale.
- [ ] Nếu scope-down hoặc drop-FT → updated task list cho Phase 6.
- [ ] Email/note GVHD cập nhật progress.

## Hướng dẫn triển khai

### NO-GO triggers (1 trong 3 → cân nhắc serious)

1. **B1 F1 < 20% trên test set.**
   - Có nghĩa Llama 3 8B base không "hiểu" được SPARQL ngay cả với prompt + ontology.
   - Fine-tuning có thể vẫn cứu nhưng risk cao.

2. **Schema linker không cải thiện ≥5% F1.**
   - So sánh: B1 (no linker) vs B1+linker.
   - Nếu linker không giúp → đóng góp 2 (linking) yếu, RQ2 negative.
   - Vẫn có thể publish negative result, nhưng cần frame cẩn thận.

3. **Trễ ≥3 tuần.**
   - Có nghĩa khoảng 4 tuần còn lại cho fine-tuning + ablation + thesis writing.
   - Quá ít để làm full Phase 6.

### Decision matrix

| B1 F1 | Linker improve | Trễ | → Decision |
|---|---|---|---|
| ≥40% | ≥10% | <2 weeks | **Continue Plan A** |
| ≥30% | ≥5% | <3 weeks | **Continue Plan A**, monitor |
| 20-30% | ≥5% | 2-3 weeks | **Scope-down** (Option 2) |
| <20% | <5% | ≥3 weeks | **Drop FT** (Option 3), focus contributions 1+2 |
| <20% | n/a | ≥4 weeks | **Emergency** — meet GVHD ngay |

### Option 2: Scope-down (chi tiết)

- Dataset: giữ 500 cặp tốt nhất (filter chất lượng cao).
- Baselines: skip B0 hoặc B5 (giữ B1, B2, B3, B4).
- Ablation: 2-3 configs thay 4-5.
- Test set: vẫn 100 (không touch).
- Timeline: rút gọn Phase 6 từ 4 tuần xuống 2.5 tuần.

### Option 3: Drop FT (chi tiết)

- Skip toàn bộ T6.1 (B3 QLoRA).
- Phase 6 tập trung vào:
  - T6.2 — Constrained decoding với B1/B2.
  - Build "Full system without FT" = B2 + schema linker + entity linker + class resolver + constrained decoding.
- Compare: B1 (raw) vs Full-no-FT vs B4/B5 (API).
- RQ1 reframe: "Có thể đạt usable accuracy without fine-tuning, with linking + constrained decoding?"
- Vẫn có 3 contributions (chỉ contribution 3 là "small vs large WITHOUT FT").

### Document template

```markdown
# Pivot Decision #2 — <date>

## Status snapshot

- Calendar: [on track / X weeks behind].
- B1 F1: <%>
- B2 F1: <%>
- Schema linker delta: <%>
- Entity linker delta: <%>
- Test set: <% complete>

## Decision

[Continue / Scope-down / Drop-FT]

## Rationale

<2-3 paragraphs>

## Adjusted plan

<table or list of modified tasks>

## GVHD notification

<email draft>
```

### GVHD communication

Nếu pivot, GỬI EMAIL GVHD ngay:
- Status snapshot ngắn.
- Rationale.
- Updated plan.
- Hỏi: confirm OK không?

Đừng đợi đến defense mới reveal pivot.

## Rủi ro & note

- **Self-deception bias:** dễ argue "thêm 1 tuần nữa sẽ ổn". Quy tắc 5 từ kế hoạch: "Nếu argue với chính mình về pivot — câu trả lời là pivot."
- **GVHD pushback:** thầy có thể muốn giữ Plan A. Lúc này lý do phải dữ liệu (numbers), không cảm tính.
- **Demo deadline:** dù pivot gì, demo (T7.3) vẫn cần — đảm bảo demo path không break.

## Estimated effort

1 ngày.

## Trạng thái

todo
