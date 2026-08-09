# T2-SQL-3 — Live correctness, cost và latency benchmark

## Mục tiêu

Chứng minh analytical layer T2-SQL-2 không chỉ deploy/parse được mà trả kết quả
đúng trên pinned evaluation slice, giữ row cardinality/precision invariants,
nằm trong byte budget và có latency được đo bằng live BigQuery jobs.

## Phụ thuộc

- T2-SQL-1 — schema/date/cost contract đã accepted.
- T2-SQL-2 — label snapshot, 2 views và 6 TVFs đang live.
- Independent bounded raw-source query đã pin full-window counts: 65.621.456
  transactions, 222.310 blocks và 125.320.919 token transfers. Các counts
  4.431.329/221.548/4.001.230 cũ chỉ là filtered KG extraction subset.
- Benchmark design self-approved ngày 2026-08-09 theo ủy quyền người dùng.

## Đầu ra

- Benchmark cases/harness tại `src/nl2sparql/sql/benchmark.py`.
- Plan/execute CLI tại `scripts/07_benchmark_sql_layer.py`.
- Offline unit tests tại `tests/unit/test_sql_benchmark.py`.
- Live report tại `docs/sql-benchmark.md`.

## Workload contract

Tất cả fact cases dùng `[2026-05-31, 2026-07-01)`:

1. Stable label count/role/digest contract.
2. Canonical transaction count = 65.621.456.
3. Canonical block count = 222.310.
4. Contract dimension address uniqueness và deployment trước end bound.
5. Labeled transaction count/distinct hash vẫn = 65.621.456.
6. Labeled token-transfer count/distinct event key vẫn = 125.320.919 và không có
   normalized amount vi phạm ERC/cast/decimals precision rules.

Mỗi SQL trả đúng một row với `passed BOOL`; harness fail closed nếu missing row,
false/null assertion, dry-run vượt cap hoặc live job metadata không hợp lệ.

## Safety và metrics

- CLI mặc định dry-run-only; `--execute` mới chạy query thật.
- Mỗi case dry-run ngay trước execution, `use_query_cache=false` và
  `maximum_bytes_billed=53.687.091.200`.
- Tổng estimated workload không được vượt 107.374.182.400 bytes (100 GiB).
- Record dry-run bytes, processed/billed bytes, wall latency, BigQuery elapsed
  time, slot milliseconds và cache-hit.
- Operational latency target là ≤30 giây/case. Một run chỉ là evidence mô tả,
  không được dùng để claim phân phối hoặc statistical significance.
- Benchmark không mutate BigQuery objects.

## Acceptance criteria

- [x] Task spec/design/plan commit trước code.
- [x] Case catalog encode đúng 6 bounded machine assertions.
- [x] Harness bắt buộc dry-run, per-case cap, total cap và cache disabled.
- [x] Dry-run-only CLI không execute query result.
- [x] Fake-client tests cover pass, false assertion, bytes overflow và job
  metadata.
- [x] Live 6/6 correctness assertions pass.
- [x] Mọi case dưới 50 GiB, tổng dưới 100 GiB.
- [x] Latency/bytes/slot/cache metrics được commit trong report.
- [x] Full pytest, Ruff, format và `git diff --check` pass.
- [x] Task/decision evidence cập nhật, Phase 2 SQL được checkpoint.

## Trạng thái

`done — live correctness/cost gates passed; one documented latency target miss`

## Evidence — 2026-08-09

- Design checkpoint: `9985faa`.
- Implementation checkpoints:
  - `0d89b19` — six bounded benchmark assertions.
  - `226af65` — dry-run budgets, result validation và metrics harness.
  - `3c470de` — dry-run/execute JSON CLI.
  - `c733747` — correct full-public-population oracles after root-cause audit.
- Accepted report: `docs/sql-benchmark.md`.
- Live result: 6/6 assertions pass; 66.165.774.358 processed bytes and
  66.186.117.120 billed bytes; all cache hits false.
- Correctness: label roles/digest pass, full counts match independent raw
  source, contract dimension unique/end-bounded, both label joins preserve fact
  identity, token precision violations = 0.
- Latency: 5/6 cases ≤30s; full-month labeled token-transfer stress case
  45.793,73 ms wall / 41.155 ms server. Đây là recorded target miss, không bị
  retry/cache che giấu; Phase 3 phải dùng window hẹp nhất hợp lý.
- Focused SQL verification: `122 passed`.
- Full verification: `304 passed`, 342 upstream deprecation/user warnings;
  `ruff check .`, `ruff format --check .` (64 files), `git diff --check` và
  fresh live dry-run (66.165.774.358 bytes) đều pass.
