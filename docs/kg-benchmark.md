# T2.4 — Benchmark live cho full KG

Date: 2026-08-09

Host: AMD Ryzen 7 4800H, 16 logical CPUs, 7.4 GiB RAM, SSD

Software: Morph-KGC 2.8.1, Apache Jena Fuseki/TDB2 5.1.0

## Dataset

- Period: 2026-05-31 through 2026-06-30.
- Transactions: 4,431,329 rows.
- Token transfers: 4,001,230 rows.
- Blocks: 221,548 rows.
- Contracts: 3,513 rows.
- Entity labels: 4,520 rows.

## Materialization

Lần chạy live đầu tiên dùng 100.000 source rows mỗi chunk. Morph-KGC tạo
2.434.120 triples cho chunk đầu nhưng process bị kill với exit 137 khi RDFLib
serialize graph. Khi đó máy đã dùng hết 7,4 GiB RAM và gần hết 2 GiB swap.

Lần chạy thành công dùng 50.000 rows mỗi chunk, một Morph-KGC process và 89
chunks:

```text
Chunk 89/89: 313288 triples; total=73906181
Morph-KGC full triples: 73906181
Output: data/processed/full/output.nt
```

Đối chiếu độc lập trực tiếp trên file:

```text
73906181 data/processed/full/output.nt
16811090019 bytes data/processed/full/output.nt
```

Runner hiện mặc định 50.000 rows mỗi chunk. Mỗi chunk hoàn tất có completion
marker; `--resume` kiểm tra run manifest SHA-256 trước khi reuse. Cơ chế này
ngăn resume với input/cấu hình không tương thích và không reuse partial file
sau crash.

## TDB2 load

Jena 5.1.0 phased loader đọc N-Triples đã materialize, EthOn và ontology
extension cục bộ mà không có parse error:

```text
Finished: 3 files: 73,907,909 tuples in 646.67s (Avg: 114,290/s)
Index set: SPO => SPO->POS, SPO->OSP [73,907,909 items, 498.5 seconds]
Time = 1,154.310 seconds : Triples = 73,907,909 : Rate = 64,028/s
```

Footprint cuối của `data/kg/tdb2` là 10.883.888.734 bytes (khoảng 10 GiB), thấp
hơn acceptance limit 30 GB.

## Fuseki query benchmark

Fuseki serve persistent dataset ở chế độ read-only tại
`http://localhost:3030/eth-kg/query`. Cả mười competency queries đại diện đều
parse, execute và trả về kết quả.

| Query | Thời gian (ms) | Rows | Kết quả |
|---|---:|---:|---|
| CQ01 count all transactions | 69,678.79 | 1 | Pass, latency fail |
| CQ02 transactions above 1 ETH | 192.92 | 10 | Pass |
| CQ03 failed transactions | 29.76 | 10 | Pass |
| CQ04 transactions by account | 38.86 | 10 | Pass |
| CQ07 exchange accounts | 37.70 | 10 | Pass |
| CQ09 blocks with transaction counts | 70.54 | 10 | Pass |
| CQ13 exchange-to-DEX transactions | 344.05 | 10 | Pass |
| CQ14 token transfers involving exchanges | 59.01 | 10 | Pass |
| CQ19 transfers emitted by high-value transactions | 305.30 | 10 | Pass |
| CQ20 accounts grouped by owner/category | 1,077.50 | 10 | Pass |

Hai phép đo aggregate bổ sung xác nhận đây là vấn đề full-scan latency, không
phải thời gian khởi động endpoint:

- Count all triples, warm: 15,122.38 ms, result 73,907,909.
- Count all transactions, repeated warm run: 44,946.23 ms, result 4,431,329.

Các query lookup, filter và bounded join đạt mục tiêu hai giây. Full aggregate
count không đạt mục tiêu và vượt ngưỡng NO-GO năm giây của T2.6. Vì vậy T2.4 đã
được đánh giá live nhưng không pass toàn bộ acceptance criteria; Pivot Point #1
phải ghi nhận aggregate latency là negative evidence đã đo được.

## Benchmark chính thức cho Pivot #1

Năm query trong T2.6 được chạy tuần tự, không có tải song song:

| Query | Thời gian (ms) | Rows | Gate | Kết quả |
|---|---:|---:|---:|---|
| Q1 count toàn KG | 34.554,46 | 1 | <2.000 | Fail |
| Q2 Transaction value >1 ETH, không LIMIT | 38.014,55 | 88.264 | <5.000 | Fail |
| Q3 Transaction join label, LIMIT 100 | 27,56 | 100 | <5.000 | Pass |
| Q4 top exchange aggregation, LIMIT 10 | 967,20 | 10 | <10.000 | Pass |
| Q5 DEX → Mixer multi-hop | 70,33 | 0 | <10.000 | Pass (execution) |

Q1 và Q2 kích hoạt NO-GO trigger #3. Q5 trả 0 rows trong slice hiện tại nên chỉ
chứng minh query parse/execute thành công, không chứng minh data coverage.
