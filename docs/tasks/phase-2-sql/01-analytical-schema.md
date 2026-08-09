# T2-SQL-1 — Chốt analytical SQL schema

## Mục tiêu

Chốt một contract GoogleSQL có thể kiểm chứng bằng máy cho Plan B NL2SQL: map
các semantic concept/competency question hiện có sang BigQuery tables/columns,
định nghĩa canonical relations và join paths, đồng thời bắt buộc date/cost/role
safety trước khi tạo label-enriched routines ở T2-SQL-2.

## Bối cảnh và lý do

Pivot #1 đã dừng Plan A vì full KG query vượt latency gate. BigQuery public
Ethereum trở thành execution substrate, nhưng query trực tiếp raw schema có ba
rủi ro: model phải tự nhớ join keys, date filter dễ bị bỏ sót, và token/entity
roles dễ bị diễn giải sai. T2-SQL-1 tạo một schema contract chung cho template
generation, linker, validator, evaluation và demo.

Live audit ngày 2026-08-09 cũng xác nhận:

- bốn bảng fact/core hiện có đều ở location `US` và được partition theo thời
  gian;
- public view `amended_tokens` cung cấp token symbol/name/decimals;
- bảng `nl2sparql_kg.labeled_addresses` cũ chỉ có 4.520 address, không có label
  metadata và không phù hợp làm semantic dimension;
- dictionary mới có 5.135 entities, 8.538 aliases và strict address roles.

## Phụ thuộc

- T2.2 — entity dictionary chain-aware đã accepted.
- T2.3 — BigQuery access/extraction/cost guard đã chạy live.
- T2.6 — Pivot #1 đã chọn Plan B NL2SQL.
- Design đã được duyệt trong conversation ngày 2026-08-09: hybrid logical
  layer + parameterized table-valued functions (TVFs).

## Đầu vào

- `bigquery-public-data.crypto_ethereum.transactions`
- `bigquery-public-data.crypto_ethereum.blocks`
- `bigquery-public-data.crypto_ethereum.token_transfers`
- `bigquery-public-data.crypto_ethereum.contracts`
- `bigquery-public-data.crypto_ethereum.amended_tokens`
- `src/nl2sparql/linking/dictionary/entities.json`
- `src/nl2sparql/kg/ontology/competency-questions.md`
- `docs/research/bigquery-analytical-layer-options-2026-08-09.md`

## Đầu ra

- Machine-readable catalog tại
  `src/nl2sparql/sql/catalog/ethereum_analytics.json`.
- Catalog/date/live-schema validator tại `src/nl2sparql/sql/schema.py`.
- CLI offline/live metadata validation tại `scripts/05_validate_sql_schema.py`.
- Unit tests tại `tests/unit/test_sql_schema.py`.
- Design và implementation plan trong `docs/superpowers/`.

## Phạm vi

T2-SQL-1 định nghĩa contract và kiểm tra schema metadata. Task này không upload
dictionary, không tạo BigQuery table/view/routine, không chạy benchmark tính
phí, và không migrate Phase 3 templates. Những mutation đó thuộc T2-SQL-2; live
execution/cost/latency benchmark thuộc T2-SQL-3.

## Contract đã duyệt

### Dialect và thời gian

- Dialect là GoogleSQL (`use_legacy_sql = false`).
- Mọi fact relation nhận `start_date` và `end_date` theo half-open interval
  `[start_date, end_date)`; `start_date < end_date` và span tối đa 31 ngày.
- Evaluation slice pinned là `[2026-05-31, 2026-07-01)`, tương đương live
  extraction từ 2026-05-31 đến hết 2026-06-30.
- Partition filters so sánh trực tiếp timestamp column với typed bounds.

### Canonical relations

1. `transaction_facts(start_date, end_date)`
2. `block_facts(start_date, end_date)`
3. `token_transfer_facts(start_date, end_date)`
4. `contract_dimension(end_date)`
5. `token_dimension`
6. `entity_labels_v1`

T2-SQL-2 sẽ materialize `entity_labels_v1` và tạo parameterized TVFs cho các
fact relations. Logical views chỉ được dùng cho parameterless projections.

### Canonical joins

- Transaction → block: `block_number = number` và `block_hash = hash`, với date
  bounds trên cả hai partitioned sources.
- Transaction → contract: normalized `to_address = address`, với contract
  deployment trước `end_date`; path này chứng minh CQ18 thay vì suy từ calldata.
- Token transfer → transaction: `transaction_hash = hash` và matching block
  identity, với date bounds trên cả hai fact sources.
- Token transfer → contract/token metadata: normalized token address.
- Fact address → entity label: lowercase Ethereum address.

### Precision và role semantics

- Native transaction value giữ `NUMERIC` wei.
- Token transfer giữ `value_raw STRING`, `value_bignumeric`, cast-valid flag,
  decimals và normalized amount khi phép scale hợp lệ.
- ERC-721 token ID không được cộng như fungible volume.
- `operational` dùng cho protocol execution/flow endpoints; `treasury` dùng cho
  attributed exchange accounts; `token` dùng cho token metadata. Role không
  được thay thế lẫn nhau.
- Confidence giữ vocabulary categorical, không tự suy diễn numeric score.

## Competency coverage policy

Catalog phải có đúng CQ01-CQ30. Mỗi CQ được đánh dấu một trong:

- `supported`: schema và current data đủ cho semantics đã mô tả;
- `coverage_gap`: schema hỗ trợ nhưng current entity-role coverage chưa đủ;
- `unsupported`: public substrate không chứng minh được semantics.

CQ24 (meta-transaction initiator khác executor) là `unsupported`; không được
đồng nhất với transaction sender. CQ17 dùng thuật ngữ block
beneficiary/fee-recipient thay vì khẳng định validator identity. Mixer, NFT
marketplace và MEV questions phải khai báo coverage gap khi operational labels
không đủ.

## Safety và failure behavior

- Fail closed nếu catalog reference relation/field/join/role/type không tồn tại.
- Fail nếu CQ01-CQ30 thiếu, trùng hoặc dùng status ngoài vocabulary.
- Fail nếu fact relation thiếu partition/date contract.
- Fail nếu live upstream thiếu required column hoặc đổi type; extra columns
  được phép.
- Generated analytical paths chỉ cho phép `SELECT`/`WITH`; DDL/DML không thuộc
  model output.
- Execution clients phải dry-run trước và dùng default
  `maximum_bytes_billed = 53,687,091,200` (50 GiB/query).

## Acceptance criteria

- [x] Task spec, approved design và implementation plan được commit trước code.
- [x] Catalog map đầy đủ physical sources, canonical relations, fields, joins,
  roles, safety policy và CQ01-CQ30.
- [x] Structural validator fail closed cho invalid references và unsafe date
  contracts.
- [x] Date-window validator enforce half-open interval và tối đa 31 ngày.
- [x] Live-schema validator phát hiện missing/type-changed required columns và
  bỏ qua harmless extra columns.
- [x] Offline CLI chạy không cần credentials; live mode chỉ đọc metadata.
- [x] BigQuery metadata validation pass cho năm public sources hiện có.
- [x] Representative SQL dry-runs pass và mỗi query dưới 50 GiB.
- [x] Focused tests, full pytest, Ruff và `git diff --check` pass.
- [x] Task status/evidence và decision log được cập nhật, không claim coverage
  vượt quá dữ liệu.

## Trạng thái

`done — analytical schema contract validated`

## Evidence — 2026-08-09

- Task spec/design/plan checkpoint: `431bb9b`.
- Implementation checkpoints:
  - `68bf460` — catalog loader và fail-closed structural boundary.
  - `d59391d` — live sources, analytical relations, joins và semantic mappings.
  - `0374e9d` — CQ coverage và live schema-drift validation.
- Catalog summary: 6 physical sources, 6 analytical relations, 6 canonical
  joins, 41 semantic mappings và đủ CQ01-CQ30.
- Competency status: 25 `supported`, 4 `coverage_gap` (CQ21, CQ23, CQ27,
  CQ28), 1 `unsupported` (CQ24).
- Focused verification: `70 passed`.
- Offline CLI output: 6 sources, 6 relations, 6 joins, 41 mappings, 30 CQs.
- Live metadata-only validation: 5 public sources và 41 required fields pass;
  `entity_labels_v1` được báo đúng là 1 deferred source.
- Pinned-window dry-runs `[2026-05-31, 2026-07-01)`:
  - transaction → block: `16,824,296,156` bytes.
  - transfer → deduplicated contract + amended token:
    `30,855,462,205` bytes.
  - Cả hai dưới cap `53,687,091,200` bytes và không execute query tính phí.
- Full verification: `252 passed`, 342 upstream deprecation/user warnings.
- `ruff check .`, `ruff format --check .` (58 files) và `git diff --check`
  đều pass.
- T2-SQL-1 không tạo/sửa remote BigQuery object. Upload label dimension và
  routine DDL được giữ đúng scope cho T2-SQL-2.
