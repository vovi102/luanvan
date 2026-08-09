# Điều chỉnh backlog sau Pivot #1 — Plan B NL2SQL

**Hiệu lực:** 2026-08-09

**Target mới:** Sinh SQL cho BigQuery Ethereum thay vì sinh SPARQL cho Fuseki.

## Giữ nguyên

- BigQuery access, extraction và cost guard từ Phase 0–2.
- Entity dictionary, aliases, concepts và quy trình manual source verification.
- Competency questions như semantic requirements; target query sẽ chuyển sang
  SQL.
- Quy trình synthetic dataset, independent three-pool test set, schema/entity
  linking, baselines, fine-tuning, evaluation và demo ở cấp kiến trúc.
- Full KG/TDB2 và benchmark T2.4 như negative-result artifact cho luận văn.

## Dừng đầu tư Plan A

- Không tiếp tục full pySHACL validation T2.5; scaffold/fixtures vẫn được giữ để
  tái lập kết quả Phase 2.
- Không tối ưu Fuseki bằng cache/pre-aggregation nhằm đảo kết quả Pivot #1.
- Không tạo thêm RML mapping hoặc ontology extension trừ khi cần mô tả phương
  pháp và limitations trong luận văn.

## Backlog Phase 2 SQL cần bổ sung

Thực hiện ba task này trước khi tiếp tục Phase 3:

1. **T2-SQL-1 — Chốt analytical SQL schema:** map các semantic concept hiện có
   sang BigQuery tables/columns, xác định query dialect và canonical joins.
2. **T2-SQL-2 — Label-enriched views:** tạo reproducible views/CTEs join entity
   dictionary với transaction/token-transfer data, có cost guard.
3. **T2-SQL-3 — Smoke và benchmark:** chạy representative SQL queries, xác nhận
   correctness, bytes processed, latency và budget.

Mỗi task phải có task spec riêng trong `docs/tasks/phase-2-sql/` trước khi code.

## Điều chỉnh các phase sau

| Phase | Giữ | Thay đổi bắt buộc |
|---|---|---|
| Phase 3 — Dataset | Template taxonomy, synthesis, paraphrase, noise, three-pool protocol | Target từ SPARQL sang Standard SQL; validator và canonicalization theo SQL/BigQuery. |
| Phase 4 — Linking | Entity aliases, fuzzy/embedding matching, class resolution concept | Schema linker rank tables/columns/join paths thay vì RDF properties/classes. |
| Phase 5 — Baselines | B0–B5, evaluation protocol, latency/cost comparison | Prompt/output parser/metrics chạy SQL; execution accuracy dùng BigQuery result semantics. |
| Phase 6 — Fine-tune | QLoRA, ablation methodology | Training target và constrained grammar là SQL. |
| Phase 7 — Demo | Recovery flow, case studies, Gradio | SQL safety checks, dry-run/cost display và BigQuery execution thay Fuseki. |

## Artifact và terminology

- Từ checkpoint này, tài liệu mới dùng `NL2SQL`, `SQL template`, `schema linker`
  cho BigQuery và `execution accuracy` trên SQL.
- Tài liệu lịch sử Phase 0–2 không bị rewrite: chúng là evidence của Plan A đã
  thử nghiệm.
- File/task cũ theo SPARQL phải được đánh dấu `superseded` hoặc được migrate rõ
  ràng trước khi implementation; không được âm thầm chạy spec cũ.

## Thứ tự tiếp theo

1. Viết và duyệt spec cho T2-SQL-1 đến T2-SQL-3.
2. Hoàn thành Phase 2 SQL và benchmark.
3. Migrate Phase 3 sang SQL rồi tiếp tục dependency order đến Phase 7.
