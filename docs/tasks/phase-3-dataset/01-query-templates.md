# T3.1 — GoogleSQL Query Template Library

## Mục tiêu

Migrate scaffold 25 SPARQL templates sang 25 canonical GoogleSQL templates phủ
các pattern Ethereum analytics chính, có typed slots/schema/CQ metadata để T3.2
sinh dữ liệu reproducible và validator có thể dry-run/execute trên analytical
layer đã accepted.

## Bối cảnh

Scaffold ngày 2026-07-04 đạt count/distribution nhưng target Fuseki đã bị
superseded bởi Pivot #1. Không được âm thầm tái sử dụng `sparql_template`,
ontology IRI slots hay window 2024. T2-SQL-1 đến T2-SQL-3 hiện cung cấp catalog,
entity labels, bounded TVFs và live correctness/cost evidence cho Plan B.

## Phụ thuộc

- T2-SQL-1 — machine-readable GoogleSQL catalog/CQ mappings.
- T2-SQL-2 — 2 views và 6 TVFs live.
- T2-SQL-3 — correctness/cost gate pass; token full-month latency limitation.
- T2.2 — 5.135 chain/role-aware entities.

## Đầu ra

- `src/nl2sparql/dataset/templates/templates.json` contract v2.
- `src/nl2sparql/dataset/templates/README.md` document format/slot/safety.
- `src/nl2sparql/dataset/templates/validate.py` offline/live validator.
- `scripts/08_validate_sql_templates.py` CLI.
- `tests/unit/test_query_templates.py` migrated tests.
- `notebooks/07_template_validate.ipynb` migrated to GoogleSQL workflow.
- Live validation report/evidence trong task này.

## Template contract v2

Mỗi template bắt buộc có:

- stable `id`, `name`, `category`, `difficulty`;
- typed `slots` và deterministic `example_fill`;
- `sql_template` GoogleSQL read-only;
- `nl_seed`, `expected_columns`;
- `schema_elements` theo `relation` hoặc `relation.field` trong catalog;
- `cq_ids` tham chiếu CQ01-CQ30;
- `validation` gồm `expect_non_empty` và scope note.

Fact templates gọi fully qualified managed TVFs với `{start_date}` và
`{end_date}`, interval half-open, tối đa 31 ngày. Example fills dùng window một
ngày trong pinned month. Parameterless label/token lookups có thể không có date
slots. Address/string slots nằm trong quoted literals; integer/decimal slots
được validator type-check trước render.

## Coverage

- Giữ 25 stable IDs, 8 easy / 11 medium / 6 hard.
- Giữ đủ 10 categories: simple filter, time range, entity lookup, aggregation,
  top-k, multi-hop, class-level, token-specific, comparison, temporal pattern.
- Cover transaction, block, contract, token transfer, token metadata và label
  relations; role-aware templates không thay treasury/token thành operational.
- CQ coverage metadata phải reference đúng catalog. Known CQ coverage gaps có
  thể execute rỗng nhưng phải ghi `expect_non_empty=false`; không claim coverage
  giả.

## Validation

- Offline: schema, ID/distribution, placeholders/slots, slot values, read-only
  SQL, fully qualified managed objects, date bounds, projections,
  schema-elements/CQ references.
- Live `--live`: dry-run cả 25 rendered examples, mỗi query ≤5 GiB và tổng ≤30
  GiB.
- Live `--execute`: chỉ sau full preflight, chạy mỗi example một lần với cache
  disabled; query phải thành công và result schema khớp. Non-empty chỉ bắt buộc
  khi `validation.expect_non_empty=true`.

## Acceptance criteria

- [ ] Design/plan migration commit trước code.
- [ ] Đúng 25 SQL templates; không còn SPARQL/Fuseki field/runtime dependency.
- [ ] Distribution giữ 8 easy / 11 medium / 6 hard và 10 categories.
- [ ] 100% schema/CQ/placeholder/date/read-only validation pass offline.
- [ ] 25/25 examples dry-run thành công, per/total cost caps pass.
- [ ] 25/25 examples execute thành công; non-empty policy pass.
- [ ] README/notebook/script đều mô tả GoogleSQL workflow.
- [ ] Focused/full pytest, Ruff, format và `git diff --check` pass.
- [ ] Task/decision evidence cập nhật, worktree clean.

## Trạng thái

`in progress — Plan B migration design approved`

## Historical scaffold

SPARQL scaffold/evidence ngày 2026-07-04 được giữ trong git history và design
files cũ, nhưng đã superseded; không còn là active acceptance contract.
