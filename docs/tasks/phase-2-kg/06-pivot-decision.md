# T2.6 — Pivot Point #1: Plan A (NL2SPARQL) hay Plan B (NL2SQL)?

## Mục tiêu

Đánh giá khách quan kết quả Phase 1+2; ra quyết định **Plan A tiếp tục** hay **pivot Plan B**; document trong `05-DECISION_LOG.md`.

## Bối cảnh & lý do

Đây là **gate critical**. Cuối tháng 2. Nếu KG không khả thi (RML chậm, query lag, thiếu data), tiếp tục Plan A là sai lầm chiến lược.

Quy tắc: "Cuối tháng 2 nếu còn argue về pivot — câu trả lời là pivot." (`docs/memory/00-PROJECT_OVERVIEW.md`)

## Phụ thuộc

- T2.1 → T2.5 đã hoàn thành (hoặc đã thử và thất bại).

## Đầu vào

- Kết quả thực tế từ Phase 1+2.
- File `docs/memory/00-PROJECT_OVERVIEW.md` mục "Plan A vs Plan B".

## Đầu ra

- File `docs/pivot-decision-1.md` chứa đánh giá đầy đủ + quyết định.
- Entry trong `05-DECISION_LOG.md`.
- Nếu pivot → tạo file `docs/plan-b-adjustments.md` chứa thay đổi cần làm.

## Acceptance criteria

- [ ] Mọi GO criteria đã được đánh giá khách quan (đo, không cảm tính).
- [ ] Mọi NO-GO trigger đã được kiểm tra.
- [ ] Quyết định cuối được ghi rõ với rationale.

## Hướng dẫn triển khai

### Bước 1 — Chấm điểm GO criteria

Cần đủ **4/4** để GO:

| # | Criterion | Cách đo | Kết quả |
|---|---|---|---|
| 1 | KG load thành công vào Fuseki | T2.4 acceptance pass | ☐ Pass / ☐ Fail |
| 2 | Ontology cover ≥80% câu hỏi mẫu | T2.1: viết SPARQL được cho ≥24/30 competency questions | ☐ Pass / ☐ Fail |
| 3 | Entity dictionary ≥3000 entries + sample 50 OK | T2.2 acceptance pass | ☐ Pass / ☐ Fail |
| 4 | Tự tin với stack, không stuck >1 tuần | Tự đánh giá; nếu phải rework >1 lần → fail | ☐ Pass / ☐ Fail |

### Bước 2 — Kiểm tra NO-GO triggers

Bất kỳ **1/4** trigger → NO-GO:

| # | Trigger | Đã xảy ra? |
|---|---|---|
| 1 | Không setup được Fuseki/triple store sau 2 tuần thử | ☐ Yes / ☐ No |
| 2 | RML mapping phức tạp tốn quá nhiều thời gian (>2 tuần thuần RML) | ☐ Yes / ☐ No |
| 3 | KG loaded nhưng query đơn giản chạy >5s/query | ☐ Yes / ☐ No |
| 4 | Stuck >1 tuần ở vấn đề kỹ thuật KG | ☐ Yes / ☐ No |

### Bước 3 — Performance benchmark

Chạy 5 query đại diện đo response time. Lưu vào `docs/kg-benchmark.md`:

```sparql
# Q1: simple count
SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }
# Expected: <2s

# Q2: filter by class + value
SELECT ?tx WHERE { ?tx a :Transaction ; :hasValue ?v . FILTER(?v > 1000000000000000000) }
# Expected: <5s

# Q3: join (transaction + account label)
SELECT ?tx ?fromLabel WHERE {
  ?tx a :Transaction ; :hasFrom ?from .
  ?from :hasLabel ?fromLabel .
} LIMIT 100
# Expected: <5s

# Q4: aggregation (top exchanges)
SELECT ?owner (COUNT(*) AS ?n) WHERE {
  ?tx :hasTo ?to . ?to a :ExchangeAccount ; :hasOwner ?owner .
} GROUP BY ?owner ORDER BY DESC(?n) LIMIT 10
# Expected: <10s

# Q5: multi-hop (DEX → Mixer)
SELECT ?tx WHERE {
  ?tx :hasFrom ?dex ; :hasTo ?mixer .
  ?dex a :DEXProtocol . ?mixer a :MixerAccount .
}
# Expected: <10s
```

Nếu Q1-Q3 vượt 5s → NO-GO trigger #3.

### Bước 4 — Form quyết định

Template trong `docs/pivot-decision-1.md`:

```markdown
# Pivot Decision #1 — End of Month 2

**Date:** YYYY-MM-DD
**Decision:** Continue Plan A | Pivot to Plan B

## GO criteria evaluation

| # | Criterion | Result | Notes |
|---|---|---|---|
| 1 | ... | Pass/Fail | ... |
...

## NO-GO triggers

(none / list which triggered)

## Performance benchmark

| Query | Time | Pass (<5s) |
|---|---|---|
| Q1 | 0.3s | ✅ |
...

## Decision rationale

(2-3 paragraphs)

## If continuing Plan A: Risks remaining

- ...

## If pivoting Plan B: What changes

(see plan-b-adjustments.md)
```

### Bước 5 — Nếu pivot Plan B

Tạo `docs/plan-b-adjustments.md`:

**Cái GIỮ NGUYÊN (~70% công sức Phase 1+2 không phí):**
- T0.1, T0.3, T0.4 (setup, BigQuery, lit review).
- T2.2 entity dictionary (vẫn dùng cho NL2SQL entity linking).
- T2.3 BigQuery extraction (CSV vẫn cần để build derived tables nếu muốn).

**Cái THAY:**
- Bỏ T1.1, T1.3, T2.1, T2.4, T2.5 (Fuseki/RML/SHACL).
- Thay bằng task mới `phase-2-sql/`:
  - **T2-SQL-1:** Thiết kế schema SQL (có thể dùng trực tiếp BigQuery schema, hoặc denormalize để giảm complexity).
  - **T2-SQL-2:** Tạo derived tables/views với labels (JOIN entity dictionary).
  - **T2-SQL-3:** Verify smoke queries.

**Phase 3 đổi:**
- Templates → SQL templates (dễ hơn SPARQL về syntax).
- Synthetic generation: SQL → NL question (dễ hơn vì spider-style đã có nhiều benchmark).
- Test set 3-pool vẫn dùng được, chỉ thay target.

**Phase 4 đổi nhẹ:**
- Schema linker target SQL columns thay properties.
- Entity linker giữ nguyên.

**Phase 5 đổi nhẹ:**
- Baselines tương tự, thay SPARQL → SQL.
- Spider/BIRD benchmark có thể tham khảo prompt format.

**Phase 6 giữ nguyên** (QLoRA fine-tune).

**Phase 7 đổi:**
- Validator: SQL syntax (sqlparse) thay rdflib parse.
- Demo: tương tự.

### Bước 6 — Update memory

- Mở `05-DECISION_LOG.md`, thêm entry với rationale chi tiết.
- Mở `00-PROJECT_OVERVIEW.md`, update Plan A/B status.
- Cập nhật README index task.

## Estimated effort

1-2 ngày (đa phần là viết, thinking).

## Trạng thái

`todo`
