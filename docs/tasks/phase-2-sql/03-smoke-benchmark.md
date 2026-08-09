# T2-SQL-3 — Live correctness, cost và latency benchmark

## Mục tiêu

Chứng minh analytical layer T2-SQL-2 không chỉ deploy/parse được mà trả kết quả
đúng trên pinned evaluation slice, giữ row cardinality/precision invariants,
nằm trong byte budget và có latency được đo bằng live BigQuery jobs.

## Phụ thuộc

- T2-SQL-1 — schema/date/cost contract đã accepted.
- T2-SQL-2 — label snapshot, 2 views và 6 TVFs đang live.
- Full extraction evidence đã pin counts tháng: 4.431.329 transactions,
  221.548 blocks và 4.001.230 token transfers.
- Benchmark design self-approved ngày 2026-08-09 theo ủy quyền người dùng.

## Đầu ra

- Benchmark cases/harness tại `src/nl2sparql/sql/benchmark.py`.
- Plan/execute CLI tại `scripts/07_benchmark_sql_layer.py`.
- Offline unit tests tại `tests/unit/test_sql_benchmark.py`.
- Live report tại `docs/sql-benchmark.md`.

## Workload contract

Tất cả fact cases dùng `[2026-05-31, 2026-07-01)`:

1. Stable label count/role/digest contract.
2. Canonical transaction count = 4.431.329.
3. Canonical block count = 221.548.
4. Contract dimension address uniqueness và deployment trước end bound.
5. Labeled transaction count/distinct hash vẫn = 4.431.329.
6. Labeled token-transfer count/distinct event key vẫn = 4.001.230 và không có
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

- [ ] Task spec/design/plan commit trước code.
- [ ] Case catalog encode đúng 6 bounded machine assertions.
- [ ] Harness bắt buộc dry-run, per-case cap, total cap và cache disabled.
- [ ] Dry-run-only CLI không execute query result.
- [ ] Fake-client tests cover pass, false assertion, bytes overflow và job
  metadata.
- [ ] Live 6/6 correctness assertions pass.
- [ ] Mọi case dưới 50 GiB, tổng dưới 100 GiB.
- [ ] Latency/bytes/slot/cache metrics được commit trong report.
- [ ] Full pytest, Ruff, format và `git diff --check` pass.
- [ ] Task/decision evidence cập nhật, Phase 2 SQL được checkpoint.

## Trạng thái

`in progress — benchmark design approved`

