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

- Dataset riêng `nl2sparql_analytics` tại `US`. Contract mặc định yêu cầu không
  expiration; deployment hiện tại dùng explicit Sandbox exception 60 ngày vì
  project chưa bật billing.
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
- Load dùng explicit BigQuery schema, `WRITE_EMPTY`, không autodetect. Durable
  mode yêu cầu không expiration; Sandbox mode phải expose đúng TTL 60 ngày.
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
- Dataset hiện hữu phải ở `US`. Mặc định, mọi default expiration đều fail
  closed. Flag explicit `--allow-sandbox-expiration` chỉ chấp nhận đúng default
  `5.184.000.000 ms`; policy khác vẫn fail.
- Deployer read-back dataset sau create và snapshot sau load; request-side
  `None` không được coi là bằng chứng server đã bỏ TTL.
- Deployment order: dataset → snapshot → snapshot validation → stable label
  view → dimensions/core TVFs → enriched TVFs → metadata/dry-run validation.
- Label view swap không bị rollback nếu routine update sau đó fail, vì schema
  stable tương thích; routine version trước vẫn usable. Snapshot cũ luôn còn để
  repoint thủ công.
- Query jobs dùng `maximum_bytes_billed`; T2-SQL-2 không chạy large fact query.

## Acceptance criteria

- [x] Task spec, design và implementation plan được commit trước code.
- [x] Snapshot builder deterministic và dictionary validation fail closed.
- [x] Explicit label schema, digest naming và role/source preservation có unit
  tests.
- [x] DDL renderer tạo đúng 2 views, 6 TVFs và date/precision/role contracts.
- [x] Plan-only mode không tạo BigQuery object; apply là explicit.
- [x] Idempotent same-digest deploy và incompatible dataset/table cases fail
  safely.
- [x] Live snapshot count/uniqueness/role/digest validation pass.
- [x] Tất cả views/TVFs tồn tại, metadata đúng và representative calls dry-run
  dưới 50 GiB.
- [x] Catalog chuyển `entity_labels_v1` từ deferred sang live logical view chỉ
  sau successful deployment.
- [x] Focused tests, full pytest, Ruff và `git diff --check` pass.
- [x] Task evidence và decision log được cập nhật.

## Trạng thái

`done — live layer validated with documented Sandbox TTL`

## Evidence — 2026-08-09

- Design/plan checkpoint: `13df466`.
- Implementation checkpoints:
  - `a247f6f` — deterministic immutable label snapshot builder.
  - `820c60c` — 2 views và 6 canonical/enriched TVF renderers.
  - `e09ad68` — plan-first BigQuery deployer và rollback boundary.
  - `d1aa4dd` — server-policy readback và explicit Sandbox expiry guard.
- Live dataset: `nl2sparql-thesis.nl2sparql_analytics`, location `US`.
- Accepted snapshot: `entity_labels_snapshot_190f73a91b7a`, 5.135 unique
  addresses, roles `operational=14`, `token=5.091`, `treasury=30`, một digest
  `190f73a91b7affa8b8396cc189e4a6b332dc6f7f0109037a0d44edb14531c536`.
- Metadata: 2 views (`entity_labels_v1`, `token_dimension`) và 6
  `TABLE_VALUED_FUNCTION` routines tồn tại; catalog live validation pass 6/6
  sources, 59 fields, 0 deferred.
- Pinned-window dry-run bytes:
  - `transaction_facts`: `524.971.648`.
  - `block_facts`: `1.778.480`.
  - `contract_dimension`: `12.996.876.032`.
  - `token_transfer_facts`: `19.523.422.196`.
  - `labeled_transactions`: `6.296.633.456`.
  - `labeled_token_transfers`: `30.551.889.008`.
- Tất cả dry-runs dưới cap `53.687.091.200` bytes; không execute public-fact
  result query trong T2-SQL-2.
- Focused SQL verification: `102 passed`.
- Full verification: `284 passed`, 342 upstream deprecation/user warnings;
  `ruff check .`, `ruff format --check .` (61 files) và `git diff --check` pass.
- Billing check: `billingEnabled=false`. BigQuery Sandbox ép dataset/table/view
  TTL 60 ngày; snapshot hiện expire `2026-10-08`. Deployer mặc định từ chối
  policy này và chỉ accept khi operator truyền `--allow-sandbox-expiration`.
  Cần bật billing hoặc redeploy trước expiry; đây là infrastructure constraint,
  không được mô tả sai thành durable state.
- Legacy `nl2sparql_kg.labeled_addresses` không bị sửa hoặc xóa.
