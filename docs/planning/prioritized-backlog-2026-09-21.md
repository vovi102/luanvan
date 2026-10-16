# Backlog ưu tiên — small-LLM NL2SQL

> **Canonical backlog:** dùng tài liệu này để chọn công việc tiếp theo. Các ticket
> chi tiết trong `docs/tasks/` là nguồn acceptance. Ticket còn mô tả SPARQL/Fuseki
> phải được migrate sang GoogleSQL trước khi triển khai.

## Phạm vi đã chốt

Dự án nghiên cứu NL2SQL trên BigQuery với bốn cấu hình B0–B3:

| ID | Cấu hình | Vai trò |
|---|---|---|
| B0 | Rule-based | Lower-bound deterministic |
| B1 | Small LLM zero-shot | Baseline mô hình gốc |
| B2 | Small LLM five-shot | Đo tác động của retrieval/examples |
| B3 | Small LLM fine-tuned | Hệ thống đề xuất |

Không dùng mô hình qua API. Contribution thực nghiệm là so sánh zero-shot,
few-shot và fine-tuned trong cùng phạm vi small LLM, đồng thời đo đóng góp của
schema/entity/class linking.

## Snapshot

| Nhóm | Trạng thái | Hành động |
|---|---|---|
| Phase 0–2 và T2-SQL-1/2/3 | Hoàn tất; T2.5 superseded | Đóng, không đầu tư thêm Plan A |
| T3.1–T3.2 | Hoàn tất | Giữ immutable làm nguồn Stage A |
| T3.3 | Audit 31 ngày hoàn tất: ba flow intents thiếu coverage; positive native funding → token transfer có witness; Stage A v2 chưa accepted | Duyệt đề xuất thay ba intents + funding/CQ correction, rồi spec/plan và regenerate |
| T3.4 | Superseded | Không sinh noise dataset riêng |
| T3.5 | English finalized; Vietnamese draft chờ user review | Finalize paired benchmark, giữ ngoài training/tuning |
| T4.1–T4.3 | Hoàn tất development evaluation | Giữ snapshot/hash immutable; không claim independent holdout |
| T5.1/B0 | Genuine negative result hoàn tất (`0/100`) | Giữ làm lower bound, không tune trên test set |
| T5.2/B1–B2 | Implementation local hoàn tất | Chạy genuine trên Kaggle sau khi training artifact được accept |
| T5.4 | Framework hoàn tất; comparison chưa đủ input | Ingest B1–B3 genuine runs và làm failure analysis |
| T5.5 | Chưa quyết định scope fine-tuning | Quyết định full B3, scope-down B3 hoặc full-system không fine-tune từ số liệu B1/B2 |
| Phase 6–7 | Ticket cũ còn SPARQL | Redesign sang NL2SQL trước khi implement |

## Thứ tự thực hiện

### P0 — Mở gate dữ liệu

1. **Accept Stage A v2.** Duyệt
   [coverage proposal](../research/stage-a-v2-hard-intent-coverage-audit-2026-10-14.md):
   giữ positive/successful native funding → token transfer, thay ba flow intents
   bằng net native flow, native recipient concentration và token diversity theo
   treasury owner; sửa CQ mappings rõ nghĩa. Sau spec/plan, regenerate và
   diagnostic thành công mới fresh preflight và approval live; giữ gate
   1.000/1.000 records non-empty, zero cache hits.
2. **Build T3.3 canonical.** Audit 100 English + 100 Vietnamese, build/validate
   artifact 8.000 records hai lần và xác nhận byte reproducibility.
3. **Finalize Vietnamese T3.5.** User review 100 candidates; live verify và khóa
   immutable. Không dùng wording hoặc gold SQL của benchmark để tune.

### P1 — Baseline small LLM và quyết định scope

4. **B1/B2 genuine run.** Pin exact small-model và encoder revisions, chạy trên
   Kaggle T4 với cùng catalog, prompt và test snapshot; publish prediction/log/report.
5. **T5.4 comparison vòng 1.** So sánh B0/B1/B2, báo execution accuracy,
   exact/structural match, answer metrics, latency, cost, reproducibility và
   failure modes với CI/bootstrap đã chốt.
6. **T5.5 decision.** Chọn full B3, scope-down B3 hoặc bỏ fine-tuning. Quyết định
   dựa trên B1/B2 genuine metrics và linker deltas, không dựa trên fixture.

### P2 — Hệ thống đề xuất

7. **T6.1-SQL — B3 QLoRA** nếu T5.5 chọn fine-tuning; target là GoogleSQL từ
   accepted deterministic bilingual artifact.
8. **T6.2-SQL — Constrained generation.** Grammar/safety target GoogleSQL; đo
   syntax/safety rate, execution accuracy và latency overhead.
9. **T6.3-SQL — Ablation.** Ưu tiên `no_schema`, `no_entity`, `no_class` và
   `no_constraint`; báo CI 95% và paired significance trên cùng test snapshot.
10. **T5.4 comparison cuối.** Tổng hợp B0–B3 và failure analysis; nếu bỏ
    fine-tuning thì thay B3 bằng full-system B2 + linkers + validator và ghi rõ
    B3 không được thực hiện.

### P3 — Demo và luận văn

11. **T7.1-SQL — Validator/recovery.** SQLGlot, managed-relation allowlist,
    BigQuery dry-run, byte cap, tối đa một retry và đầy đủ provenance.
12. **T7.3-SQL — Local Gradio demo.** Chạy small model; hiển thị linking trace,
    GoogleSQL, dry-run estimate, result, latency và failure trace.
13. **T7.2-SQL — Case studies.** Chạy trên analytical layer và ghi rõ giới hạn
    label coverage, không suy diễn AML attribution vượt evidence.
14. **T7.4-SQL — HF Spaces optional.** Chỉ deploy nếu small model chạy được trong
    resource budget hoặc có demo tĩnh trung thực; không thay model bằng API.
15. **T7.5 — Thesis/slides/rehearsal.** Khóa figures sau ablation và case studies.

## Luồng song song

- **Lane A — Evidence:** accept Stage A v2, audit/build T3.3, finalize Vietnamese T3.5.
- **Lane B — Model:** chuẩn bị Kaggle B1/B2 và pin model/encoder; chỉ chạy genuine
  khi artifact đầu vào hợp lệ.
- **Lane C — Writing:** cập nhật RQ/contributions sang small-LLM-only, viết Plan A
  negative finding và methodology; không điền metrics chưa chạy.

WIP limit: một task implementation lớn và một external-evidence task đang active.

## Loại khỏi scope

- Mọi hosted/remote LLM baseline và dependency provider.
- Full T2.5 pySHACL, tối ưu Fuseki/KG, RML/ontology extension không phục vụ luận văn.
- Stage D noise injection riêng; deterministic bilingual styles là nguồn training.
- Deploy thay model nghiên cứu bằng một model ngoài phạm vi.
- Fixture/synthetic backend dùng để tick scientific acceptance.

## Definition of done

- **Implementation complete:** test, lint, CLI/help và artifact integrity pass.
- **Scientific complete:** input độc lập được review, genuine run hoàn tất, report
  hash-bound có metrics/latency/cost/privacy/reproducibility và không còn blocker.
- **Superseded/out of scope:** không xuất hiện trong active backlog hoặc acceptance;
  lịch sử thay đổi được truy xuất qua Git.

## Công việc kế tiếp

Duyệt coverage proposal đã có bounded probe evidence, rồi chốt spec/plan cho
ba replacements và funding/CQ correction. Sau regenerate, diagnostic và fresh
preflight được duyệt mới promote Stage A v2 và audit/build T3.3 deterministic.
Tiếp đó chạy B1/B2 trên Kaggle và dùng kết quả để quyết định scope B3.
