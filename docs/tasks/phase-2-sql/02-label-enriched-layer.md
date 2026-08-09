# T2-SQL-2 — Deploy label-enriched analytical layer

## Mục tiêu

Tạo analytical layer GoogleSQL ổn định cho Plan B: upload dictionary đã accepted
thành immutable label snapshot, publish stable label view, và deploy canonical
views/TVFs để downstream NL2SQL không phải tự viết lại raw BigQuery joins, token
precision rules hay address-role semantics.

## Phụ thuộc

- T2.2 — dictionary chain-aware đã accepted với 5.135 entity.
- T2.3 — BigQuery credentials, dry-run và 50 GiB cost guard đã verified.
- T2-SQL-1 — analytical schema contract đã accepted và live-schema validated.
- Design/lifecycle được self-approved theo ủy quyền của người dùng ngày
  2026-08-09.

## Đầu vào

- `src/nl2sparql/linking/dictionary/entities.json`
- `src/nl2sparql/sql/catalog/ethereum_analytics.json`
- BigQuery public Ethereum sources trong location `US`
- Project `nl2sparql-thesis`

## Đầu ra

- Dataset bền vững `nl2sparql_analytics` tại `US`, không có default expiration.
- Immutable snapshot `entity_labels_snapshot_<sha12>`.
- Stable view `entity_labels_v1` trỏ tới snapshot đã validation.
- Core analytical objects:
  - `transaction_facts(start_date, end_date)`
  - `block_facts(start_date, end_date)`
  - `contract_dimension(end_date)`
  - `token_transfer_facts(start_date, end_date)`
  - `token_dimension`
- Label-enriched TVFs:
  - `labeled_transactions(start_date, end_date)`
  - `labeled_token_transfers(start_date, end_date)`
- Reproducible plan/apply CLI, unit tests, deployment evidence và catalog live
  state.

## Phạm vi

Task này tạo và metadata-validates analytical objects. Chỉ chạy query nhỏ trên
label snapshot và dry-run routine bodies; không execute large public-fact
benchmarks. Live result correctness, latency và bytes benchmark thuộc T2-SQL-3.
Legacy `nl2sparql_kg.labeled_addresses` được giữ nguyên.

## Contract đã duyệt

### Snapshot và stable view

- Digest là SHA-256 của raw committed `entities.json`; snapshot name dùng 12 ký
  tự đầu.
- Load dùng explicit BigQuery schema, `WRITE_EMPTY`, không autodetect và không
  expiration.
- Một address lowercase duy nhất mỗi row; aliases/provenance được giữ trong
  dimension.
- Snapshot chỉ accepted khi row count, unique address count, role counts và
  digest đều khớp local artifact.
- Redeploy cùng digest là idempotent; digest mới tạo snapshot mới.
- Không tự xóa snapshot cũ. Rollback là repoint `entity_labels_v1` về snapshot
  đã accepted trước đó.
- Stable view chỉ được create/replace sau snapshot validation.

### Analytical routines

- GoogleSQL, fully qualified objects, explicit output columns và typed params.
- Fact windows là `[start_date, end_date)`, `start_date < end_date`, tối đa 31
  ngày; partition predicates nằm trực tiếp trên mỗi fact source.
- `contract_dimension` chọn deployment mới nhất trước `end_date` cho mỗi
  normalized address.
- Token transfer giữ raw value, safe `BIGNUMERIC`, cast-valid flag, ERC flags,
  decimals và normalized fungible amount theo T2-SQL-1.
- `labeled_*` dùng `LEFT JOIN` vào unique label dimension để giữ nguyên fact
  rows và không nhân bản kết quả.
- Label fields được flatten theo prefix `from_`, `to_`, `token_`; role luôn được
  expose để downstream không đánh đồng operational, treasury và token.

### Deploy safety

- CLI mặc định plan-only; remote mutation bắt buộc `--apply`.
- Local dictionary/catalog validation và DDL preflight chạy trước mutation.
- Dataset hiện hữu phải ở `US` và không có default table/partition expiration;
  mismatch thì fail closed, không tự sửa policy bất ngờ.
- Deployment order: dataset → snapshot → snapshot validation → stable label
  view → dimensions/core TVFs → enriched TVFs → metadata/dry-run validation.
- Label view swap không bị rollback nếu routine update sau đó fail, vì schema
  stable tương thích; routine version trước vẫn usable. Snapshot cũ luôn còn để
  repoint thủ công.
- Query jobs dùng `maximum_bytes_billed`; T2-SQL-2 không chạy large fact query.

## Acceptance criteria

- [ ] Task spec, design và implementation plan được commit trước code.
- [ ] Snapshot builder deterministic và dictionary validation fail closed.
- [ ] Explicit label schema, digest naming và role/source preservation có unit
  tests.
- [ ] DDL renderer tạo đúng 2 views, 6 TVFs và date/precision/role contracts.
- [ ] Plan-only mode không tạo BigQuery object; apply là explicit.
- [ ] Idempotent same-digest deploy và incompatible dataset/table cases fail
  safely.
- [ ] Live snapshot count/uniqueness/role/digest validation pass.
- [ ] Tất cả views/TVFs tồn tại, metadata đúng và representative calls dry-run
  dưới 50 GiB.
- [ ] Catalog chuyển `entity_labels_v1` từ deferred sang live logical view chỉ
  sau successful deployment.
- [ ] Focused tests, full pytest, Ruff và `git diff --check` pass.
- [ ] Task evidence và decision log được cập nhật.

## Trạng thái

`in progress — design approved, implementation pending`

