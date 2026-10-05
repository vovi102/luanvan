# Backlog ưu tiên sau Pivot #1 — 2026-09-21

> **Canonical backlog:** dùng tài liệu này để chọn công việc tiếp theo. Các ticket
> chi tiết trong `docs/tasks/` vẫn là nguồn acceptance, nhưng ticket còn nói về
> SPARQL/Fuseki phải được migrate sang GoogleSQL trước khi triển khai.

## Mục tiêu hiện tại

Hoàn thiện một nghiên cứu NL2SQL trên BigQuery có dataset và test set được review,
đủ baseline B0–B5, đánh giá định lượng cho linking/fine-tuning, một demo an toàn,
và luận văn có thể tái lập. Full KG/Fuseki chỉ còn là negative-result artifact của
Plan A; không nằm trên critical path.

## Snapshot

| Nhóm | Trạng thái | Hành động |
|---|---|---|
| Phase 0–2 và T2-SQL-1/2/3 | Hoàn tất; T2.5 superseded | Đóng, không đầu tư thêm Plan A |
| T3.1–T3.2 | Hoàn tất | Giữ immutable làm nguồn Stage A |
| T3.3–T3.5 | T3.5 finalized; T3.3 paused ở 26/1.000 Stage B sau lượt resume 2026-10-05 do Gemini Free Tier daily quota 20; T3.4 chưa có genuine artifact | Resume T3.3 sau quota reset, audit, rồi sinh Stage D |
| T4.1–T4.3 | Hoàn tất reviewed development evaluation ngày 2026-09-26; ba report `ready` | Đóng; giữ snapshot/hash immutable; không claim independent holdout |
| T5.1–T5.2 | T5.1 genuine B0 đã chạy nhưng không đạt (`0/100`, no output); T5.2 implementation local hoàn tất | Giữ B0 negative result; chờ Stage D rồi chạy T5.2 |
| T5.3 | Gemini primary path và final verification đã hoàn tất | Giữ artifact; không mở lại nếu không có regression |
| T5.4–T5.5 | T5.4-A complete; đã ingest T5.1 negative result; T5.4-B/T5.5 chờ B1/B2/B4/B5 genuine runs | Hoàn thiện training data rồi chạy các baseline còn lại |
| Phase 6–7 | Legacy SPARQL, chưa làm | Redesign NL2SQL; chưa implement ticket cũ |

## Thứ tự thực hiện

### P0 — Bắt đầu ngay

1. **Mở các external gate có lead time dài.** Chuẩn bị BigQuery credentials,
   Gemini API key và Kaggle T4. T3.5 do Codex soạn + user human-review; user cũng
   chấm các bộ ground truth T4 theo checklist. Việc này chạy song song với code;
   không chờ T5.3 mới bắt đầu.
2. **T5.3-G — Migrate B4/B5 sang Gemini free tier.** Implement design đã duyệt
   ngày 2026-09-21: model-inventory preflight, exact stable model pinning, free-tier
   policy, privacy disclosure, quota checkpoint/resume và artifact IDs B4/B5.
   Giữ OpenRouter Llama thành optional B4L/B5L, không để nó chặn critical path.
3. **Migrate governance/evaluation sang NL2SQL.** Viết lại spec cho T5.4 và T5.5,
   đồng thời chốt tên đề tài, RQ1/RQ2 và contribution claims sau pivot. T5.4 phải
   dùng execution semantics BigQuery; T5.5 phải ra quyết định continue/scope-down/
   drop-FT từ số liệu thật, không dùng ngưỡng SPARQL legacy.
4. **Migrate Phase 6 và Phase 7 trước khi triển khai.** Chuyển B3, constrained
   decoding, ablation, validator/recovery, case studies và demo sang GoogleSQL,
   BigQuery dry-run/cost guard và analytical catalog. Không dùng các code skeleton
   SPARQL/Fuseki hiện có làm acceptance.

### P1 — Hoàn thiện dữ liệu và evidence đầu vào

5. **T3.3 — Chạy live paraphrasing và audit.** Tạo Stage B 1.000 records, Stage C
   3.000 records; hoàn tất agent-reviewed audit faithfulness/naturalness và cost
   evidence. Hai lượt 2026-10-04 và 2026-10-05 đã checkpoint tổng cộng 26 Stage B
   records, recorded cost `$0.00`, rồi dừng tại daily quota 20; resume sau
   provider reset, không publish partial artifact.
6. **T3.4 — Sinh Stage D.** Chạy deterministic noise injection từ Stage C đã
   accept, validate 3.150 records và manual review 30 mẫu.
7. **T3.5 — DONE 2026-10-02.** Benchmark agent-authored, single-human-reviewed
   đã chọn đúng 100 câu (30/50/20), live-verify `100/100` và finalize immutable.
   Đây là gate chung cho mọi claim accuracy; không thay bằng fixture và không
   claim 3-pool, independent authorship/review hoặc kappa.
8. **T4-EVAL — DONE 2026-09-26 (development acceptance).** User review/gán nhãn 50
   câu schema-link, 100 câu entity-link và 50 câu class-resolver; Codex validate,
   chạy evaluator và publish report hash-bound với accuracy, Recall@K và warm
   latency. Kết quả: Schema Field Recall@10 `0.808`; Entity Top-1/F1 `1.0/1.0`;
   Resolver plan/direction/kind accuracy `1.0/1.0/1.0`. Do linker đã được cải
   thiện sau khi xem T4, đây là post-tuning development evidence, không phải
   independent holdout. Các tập không được dùng để tune trên T3.5 test set.

T3.3→T3.4 là chuỗi bắt buộc còn mở. T3.5 và T4-EVAL đã khóa immutable; giữ chúng
ngoài training/tuning và tiếp tục enforce chống test leakage.

### P2 — Chạy baseline và quyết định scope

9. **T5.4-A — DONE (implementation) — Evaluation framework NL2SQL.** Đã chuẩn hóa schema report
   dùng chung cho execution accuracy, exact/structural match, answer metrics,
   latency, observed cost, privacy, reproducibility và failure modes. Thêm paired
   bootstrap/CI trước khi chạy toàn bộ baseline.
10. **T5.1 — DONE (genuine negative result, 2026-10-03).** B0 abstain `100/100`:
    coverage/exact/structural/execution đều `0.0`, inference p95 `259.65 ms`;
    100 gold executions `ok`, estimated BigQuery cost `$3.180927`. Không tune B0
    sau khi xem T3.5. Acceptance thresholds không đạt và được giữ làm lower-bound.
11. **T5.2 — Chạy B1/B2 trên Kaggle T4** với pinned Llama/MiniLM snapshots và
    accepted Stage D training snapshot; publish prediction/log/report artifacts.
12. **T5.3 — Chạy B4/B5 Gemini** ba run genuine cho mỗi baseline trên cùng test
    snapshot. B4L/B5L chỉ chạy sau khi hệ thống chính hoàn tất và GVHD yêu cầu.
13. **T5.4-B — Tổng hợp so sánh baseline** và failure analysis bằng framework ở
    bước 9. Không công bố scientific readiness khi còn unresolved outcomes.
14. **T5.5 — Pivot Point #2.** Dùng metrics B1/B2/B4/B5 và linker deltas để chốt
    một trong ba hướng: full B3, B3 scope-down, hoặc full-system không fine-tune.
    Cập nhật backlog và trao đổi GVHD ngay sau quyết định.

### P3 — Hệ thống đề xuất và bằng chứng RQ

15. **T6.1-SQL — B3 QLoRA** chỉ khi T5.5 chọn continue/scope-down; train target
    GoogleSQL từ Stage D, giữ T3.5 hoàn toàn ngoài training/tuning.
16. **T6.2-SQL — Constrained decoding/structured generation.** Grammar và safety
    target GoogleSQL; đo syntax/safety rate, execution accuracy và latency overhead.
17. **T6.3-SQL — Ablation.** Ưu tiên `no_schema`, `no_entity`, `no_class` và
    `no_constraint`; chỉ làm LoRA-r ablation khi compute/timeline còn đủ. Báo CI
    95% và paired significance trên exact cùng test snapshot.

Nếu T5.5 chọn drop-FT, bỏ bước 15 và thay bước 16–17 bằng full-system B2 + T4
linkers + SQL validator, vẫn giữ ablation component để trả lời RQ2.

### P4 — Demo, case studies và luận văn

18. **T7.1-SQL — Validator/recovery.** SQLGlot + managed-relation allowlist +
    BigQuery dry-run + byte cap; retry tối đa một lần và giữ lỗi/cost provenance.
19. **T7.3-SQL — Local Gradio demo.** Ưu tiên demo defense trước case study và
    deploy: NL question, linking trace, GoogleSQL, dry-run estimate, result và
    latency/failure trace.
20. **T7.2-SQL — Ba case studies** chạy trên analytical layer và ghi rõ giới hạn
    label coverage; không suy diễn AML attribution vượt evidence.
21. **T7.4-SQL — HF Spaces showcase (optional).** Chỉ làm sau local demo ổn định;
    không đặt API key trả phí hay BigQuery write access vào public Space.
22. **T7.5 — Chốt thesis, slides và rehearsal.** Results/figures cuối chỉ khóa sau
    T6.3 và case studies, nhưng phần nền tảng có thể viết song song từ bây giờ.

## Luồng song song được phép

- **Lane A — Code:** T5.3 Gemini → T5.4 framework → Phase 6/7 SQL specs.
- **Lane B — Data/evidence:** T3.3 → T3.4; đồng thời T3.5 và T4 ground truth.
- **Lane C — Writing:** cập nhật project overview/architecture/RQ theo NL2SQL,
  viết Introduction, Background, Related Work, Plan A negative finding và
  Methodology từ decision log. Chưa điền số liệu kết quả chưa chạy.

Giới hạn WIP đề xuất: một task implementation lớn và một external-evidence task
đang active; tránh mở đồng thời T6/T7 khi T3.5 chưa finalized.

## Công việc loại khỏi critical path

- Không hoàn thiện full T2.5 pySHACL hoặc tối ưu Fuseki/KG.
- Không mở rộng ontology/RML nếu không phục vụ mô tả luận văn.
- Không chạy paid OpenRouter B4L/B5L trước khi B0–B5 chính và T5.5 hoàn tất.
- Không deploy HF Spaces trước khi local demo và security/privacy boundary pass.
- Không dùng fixture/synthetic backend để tick scientific acceptance.

## Definition of done cho mỗi nhóm

- **Implementation complete:** test, lint, CLI/help và artifact integrity pass;
  chưa được gọi là kết quả khoa học.
- **Scientific complete:** input độc lập được review, genuine run hoàn tất, report
  hash-bound có metrics/latency/cost/privacy/reproducibility và không còn blocker.
- **Superseded:** giữ artifact để tái lập lịch sử, không tiếp tục đầu tư và không
  tính checkbox còn mở vào backlog active.

## Công việc kế tiếp cụ thể

Việc kế tiếp trên critical path là **resume T3.3 live paraphrasing sau Free Tier
quota reset và hoàn tất agent-reviewed audit**, sau đó
sinh/accept Stage D ở **T3.4** để mở T5.2 và eventual fine-tuning. T5.3 Gemini
genuine runs có thể chạy song song nếu quota/credential sẵn sàng. T3.5 đã khóa;
không dùng câu hỏi, gold SQL hoặc kết quả B0 để tune bất kỳ baseline nào.
