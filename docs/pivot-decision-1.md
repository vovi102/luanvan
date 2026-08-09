# Pivot Decision #1 — Kết thúc Phase 2

**Ngày:** 2026-08-09

**Quyết định:** Pivot sang Plan B — NL2SQL trên BigQuery Ethereum.

## GO criteria evaluation

Plan A chỉ được tiếp tục khi đủ 4/4 tiêu chí. Kết quả đo được là 2 pass, 2
fail/unproven.

| # | Criterion | Kết quả | Evidence |
|---|---|---|---|
| 1 | KG load thành công vào Fuseki | Pass | TDB2 load exit 0 với 73.907.909 triples; endpoint trả kết quả. T2.4 tổng thể vẫn fail latency. |
| 2 | Ontology cover ≥80% câu hỏi mẫu | Pass | T2.1 cover 30/30 competency questions. |
| 3 | Dictionary ≥3.000 entries và sample 50 đúng | Fail | Có 4.520 entries nhưng manual audit chỉ pass 43/50; 7 rows sai chain provenance. |
| 4 | Tự tin với stack, không stuck >1 tuần | Unproven/Fail | Stack vận hành được, nhưng không có self-assessment đã ký nhận; strict gate không coi evidence thiếu là pass. |

## NO-GO triggers

Chỉ một trigger là đủ NO-GO.

| # | Trigger | Xảy ra? | Evidence |
|---|---|---|---|
| 1 | Không setup được Fuseki sau 2 tuần | Không | Fuseki/TDB2 5.1.0 đang serve dataset persistent. |
| 2 | RML thuần tốn >2 tuần | Không quan sát thấy | Mapping hoàn tất; live run 89 chunks thành công sau khi giảm chunk 100k xuống 50k. Không có log effort chứng minh >2 tuần thuần RML. |
| 3 | Query đơn giản >5 giây | **Có** | Q1 mất 34,55 giây; Q2 mất 38,01 giây. |
| 4 | Stuck >1 tuần ở vấn đề kỹ thuật KG | Không quan sát thấy | OOM được xử lý bằng bounded chunks và resume manifest; không có blocker kỹ thuật mở kéo dài >1 tuần. |

## Performance benchmark

Các query được chạy tuần tự trên endpoint
`http://localhost:3030/eth-kg/query`, không chạy tải song song.

| Query | Thời gian | Rows | Gate | Kết quả |
|---|---:|---:|---:|---|
| Q1 — count toàn KG | 34,554 s | 1 | <2 s | Fail |
| Q2 — Transaction có value >1 ETH, không LIMIT | 38,015 s | 88.264 | <5 s | Fail |
| Q3 — Transaction join account label, LIMIT 100 | 0,028 s | 100 | <5 s | Pass |
| Q4 — aggregate top exchange, LIMIT 10 | 0,967 s | 10 | <10 s | Pass |
| Q5 — DEX → Mixer multi-hop | 0,070 s | 0 | <10 s | Pass (execution) |

Q5 không tìm thấy row trong slice dữ liệu hiện tại; phép đo chỉ chứng minh query
được parse và execute, không chứng minh coverage cho pattern này.

## Decision rationale

Plan A không đạt điều kiện bắt buộc 4/4 GO và kích hoạt NO-GO trigger #3.
Full KG vẫn là artifact nghiên cứu có giá trị: materialization và TDB2 load thành
công, còn selective query nhanh. Tuy nhiên exact full-scan/filter query mà
evaluation và analytics cần có latency 34–38 giây trên hardware mục tiêu. Việc
thêm cache hoặc pre-aggregation để giữ Plan A sẽ thay đổi workload được đo và
không xóa negative evidence của gate.

Theo rule đã chốt trước Phase 2 — bất kỳ một NO-GO trigger nào cũng phải pivot —
dự án chuyển target language sang SQL. Entity dictionary, raw extraction,
dataset methodology, test-set protocol, linker/evaluation framework và mô hình
vẫn được giữ. Chi tiết migration nằm trong `docs/plan-b-adjustments.md`.

## Rủi ro sau pivot

- BigQuery query cost phải có dry-run và maximum-bytes guard ở mọi live run.
- SQL schema/derived views cần giữ semantics của ontology để tái sử dụng entity
  linking và competency questions.
- Các task Phase 3–7 hiện viết theo SPARQL phải được cập nhật trước khi triển khai,
  tránh trộn hai target language trong dataset/evaluation.
