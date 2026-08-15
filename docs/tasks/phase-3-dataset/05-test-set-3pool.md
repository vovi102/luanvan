# T3.5 — Test set 100 cặp (3-pool cross-validation, GoogleSQL)

## Mục tiêu

Xây dựng benchmark độc lập khoảng 100 cặp NL–GoogleSQL chất lượng cao, viết và
review bởi nhiều người theo quy trình 3-pool. Benchmark này đo generalization,
không chỉ mức độ ghi nhớ các template synthetic của T3.2–T3.4.

## Quyết định kiến trúc

Sau Pivot #1, target của task là read-only GoogleSQL trên BigQuery analytical
catalog; SPARQL/Fuseki trong bản task cũ là lịch sử Plan A và không còn là
acceptance runtime. Pool A vẫn viết câu hỏi tự nhiên không xem schema, Pool B
viết SQL gold, và Pool C review độc lập. Kappa cần hai reviewer trên subset 30,
nên `review_pool_c.csv` lưu `reviewer_id` thay vì giả định chỉ một reviewer.

## Phụ thuộc và blocker

- T2-SQL-1/2/3, entity dictionary và SQL catalog đã có local evidence.
- Final acceptance cần ≥3 cộng tác viên Pool A, Pool B/C độc lập, consent, và
  BigQuery credentials. Agent không tự tạo dữ liệu người thật hoặc claim live
  execution khi thiếu các đầu vào này.
- T3.3 live paraphrasing và T3.4 final Stage D cũng còn credential-gated; các
  blocker này không được lẫn vào benchmark độc lập.

## Đầu ra và contract

Tooling nằm ở `src/nl2sparql/dataset/testset/` và CLI
`scripts/12_test_set_workflow.py`:

- `raw_pool_a.csv`: `question_id,author_id,nl,persona,source_batch`.
- `sql_pool_b.csv`: `question_id,writer_id,sql,expected_empty,ambiguity_flag,notes`.
- `review_pool_c.csv`: `question_id,reviewer_id,nl_quality,faithfulness,difficulty,decision,notes`.
- `final_selection.csv`: `question_id,final_difficulty,categories,entity_kinds,selection_note`.
- `test-100.jsonl`: SQL-native final records with NL, SQL, difficulty, categories,
  schema/CQ provenance, reviewer IDs, result size, SQL evidence hash and UTC
  verification time. Không có field SPARQL/Fuseki.
- `PROCESS.md` và `CONSENT.md`: brief, pseudonym/consent/privacy handoff; không
  chứa email hoặc dữ liệu định danh công khai.

Các mode CLI:

```text
scaffold      tạo header và tài liệu handoff, không overwrite file có dữ liệu
validate      chạy toàn bộ validation offline, không cần credentials
verify-live   dry-run toàn bộ rồi execute SQL bounded với BigQuery
finalize      chỉ publish test-100 khi bundle + live evidence + selection pass
```

## Acceptance criteria

### Đã hoàn thành offline

- [x] Design/plan T3.5 GoogleSQL được ghi tại spec/plan ngày 2026-08-15.
- [x] Typed CSV contracts fail closed với header, ID, text/control-character,
  pseudonym và boolean lỗi.
- [x] Bundle validator kiểm tra NL dedup, Pool A/B join, ≥3 author và ≥20 câu/
  author, review ownership, reject rate, deterministic double-review subset và
  Cohen's kappa.
- [x] Selection validator yêu cầu đúng 100 dòng, quota `easy=30, medium=50,
  hard=20`, ≥6 category và ≥3 entity kinds.
- [x] SQL adapter enforce read-only/managed-object policy, 20 GiB/query, 64 GiB
  aggregate, cache-off, complete dry-run preflight, batch-wide re-preflight và
  bounded result preview.
- [x] Scaffold/report/finalizer/CLI có atomic publication, hash evidence và
  metadata provenance, structured blocked behavior và fail-closed evidence
  validation; offline mode không khởi tạo BigQuery client.
- [x] Focused verification: 30 tests pass; full repository: 423 tests pass;
  Ruff và format pass; scaffold/CLI help chạy không cần credentials; empty
  scaffold validate fail closed.

### Còn pending — external acceptance

- [ ] ≥100 final pairs pass review; target raw 110–120 rồi filter còn 100.
- [ ] Difficulty final đúng 30 Easy / 50 Medium / 20 Hard từ lead selection.
- [ ] 100% SQL execute trên BigQuery, non-empty hoặc `expected_empty=true` rõ ràng.
- [ ] Pool A có ≥3 author, mỗi author ≥20 câu, và consent tương ứng.
- [ ] Pool C reject rate <30%.
- [ ] Kappa ≥0.7 trên subset 30 được hai reviewer độc lập chấm.

## Brief cộng tác viên

### Pool A

Viết 30–40 câu hỏi tiếng Anh tự nhiên về Ethereum cho persona journalist,
compliance officer hoặc researcher; không xem schema/catalog; dùng tên entity
được cung cấp và đa dạng filter, aggregation, top-k, time range, multi-hop.

### Pool B

Với mỗi câu Pool A, viết một GoogleSQL read-only đúng nhất trên catalog kèm theo;
ghi `expected_empty`, `ambiguity_flag`, notes và chạy thử khi credentials sẵn.
Nếu intent mơ hồ, flag để Pool C quyết định; không âm thầm chọn một diễn giải.

### Pool C

Mỗi reviewer chấm NL quality, faithfulness (1–5), difficulty và
`ACCEPT/REVISE/REJECT`. Hai reviewer độc lập cùng chấm subset 30 để tính kappa;
reviewer không tham gia viết cặp tương ứng.

## Handoff và kiểm chứng

Chạy offline:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/12_test_set_workflow.py scaffold
UV_CACHE_DIR=.uv-cache uv run python scripts/12_test_set_workflow.py validate
```

`validate` phải fail với status/error rõ ràng khi scaffold còn trống. Khi đủ
bundle và credentials, chạy `verify-live`, sau đó `finalize`; không sửa tay
`test-100.jsonl` sau khi hash evidence được tạo.

## Trạng thái

`implementation complete — external collaborator/credential gates pending`

Linked:

- Spec: `docs/superpowers/specs/2026-08-15-t3-5-google-sql-test-set-design.md`
- Plan: `docs/superpowers/plans/2026-08-15-t3-5-google-sql-test-set.md`
- Code: `src/nl2sparql/dataset/testset/`, `scripts/12_test_set_workflow.py`
