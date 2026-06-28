# T2.3 — Full BigQuery Extraction (1 tháng dữ liệu)

## Mục tiêu

Extract dữ liệu Ethereum 1 tháng gần nhất từ BigQuery thành CSV files có cấu trúc, ready cho RML mapping.

## Bối cảnh & lý do

Đây là dữ liệu nền cho KG. 1 tháng = ~30-50M transactions (toàn bộ là quá nhiều cho thesis); ta sẽ filter strategic (xem chi tiết).

## Phụ thuộc

- T1.2 — pilot extract đã chạy.
- T2.2 — Entity dictionary (cần để filter "interesting" tx).

## Đầu vào

- BigQuery 4 bảng chính.
- `entities.json` từ T2.2 → list các địa chỉ "interesting".

## Đầu ra

- 4 file CSV trong `data/raw/full/`:
  - `transactions.csv` (~5-10M rows sau filter — đợi quyết định scope dưới).
  - `blocks.csv` (~200K blocks/tháng).
  - `token_transfers.csv` (~20-30M tổng, filter còn ~5M).
  - `contracts.csv` (subset cho contracts được nhắc tới).
- File `src/nl2sparql/kg/extraction/full_extract.sql` chứa SQL.
- File `src/nl2sparql/kg/extraction/full_extract.py`.
- File `data/raw/full/manifest.json` ghi metadata: ngày extract, số rows, BigQuery cost.

## Acceptance criteria

- [ ] Tổng size CSV ≤ 5GB.
- [ ] BigQuery cost dưới $5 (cảnh báo nếu vượt — re-strategize).
- [ ] Schema khớp với pilot CSV.
- [ ] Cover ≥80% các "interesting addresses" từ entity dictionary.
- [ ] Pandas đọc được không lỗi.
- [ ] Manifest ghi đầy đủ metadata.

## Local automation scaffold

- [x] `src/nl2sparql/kg/extraction/full_extract.py` có helper load dictionary address, date window, SQL builder, cost guard, manifest writer.
- [x] `src/nl2sparql/kg/extraction/full_extract.sql` ghi lại strategy query tier1/tier2.
- [x] `scripts/04_bigquery_full_extract.py` có CLI dry-run và chặn live extraction nếu chưa có `--force`.
- [x] Unit tests cover dictionary loading, date range, SQL shape, cost guard, manifest schema, CSV read validation, dry-run orchestration.
- [ ] BigQuery dry-run đã chạy với credentials thật và table `labeled_addresses` thật.
- [ ] Live extraction đã export 4 CSV thật vào `data/raw/full/`.

## Hướng dẫn triển khai

### Strategy: filter tx theo entity dictionary

1 tháng full = quá nhiều. Filter:

- **Tier 1 — All transactions involving any address trong dictionary** (~5M rows).
- **Tier 2 — Random sample 1% các tx khác** (~300K rows) để có "background traffic" cho generalization.

Lý do: KG cần đủ "interesting" tx để query meaningful, không phải toàn bộ; nhưng cần background để model không overfit chỉ vào labeled entities.

### SQL chính

```sql
-- transactions.csv
WITH labeled_addresses AS (
  SELECT address FROM UNNEST([
    '0x28C6c06298d514Db089934071355E5743bf21d60',  -- Binance Hot 14
    -- ... (load từ entities.json bằng Python build dynamically)
  ]) AS address
)
SELECT
  hash, from_address, to_address, value, gas, gas_price,
  block_number, block_timestamp, transaction_type, receipt_status,
  CASE
    WHEN from_address IN (SELECT address FROM labeled_addresses)
      OR to_address IN (SELECT address FROM labeled_addresses)
    THEN 'tier1' ELSE 'tier2'
  END AS tier
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE DATE(block_timestamp) BETWEEN @start_date AND @end_date
  AND (
    from_address IN (SELECT address FROM labeled_addresses)
    OR to_address IN (SELECT address FROM labeled_addresses)
    OR MOD(ABS(FARM_FINGERPRINT(hash)), 100) = 0  -- 1% sample
  )
```

Các bảng khác: tương tự, filter theo `transaction_hash IN (transactions ở trên)` cho `token_transfers`.

### Python script `full_extract.py`

```python
from google.cloud import bigquery
from pathlib import Path
import json
import pandas as pd
from datetime import date, timedelta

client = bigquery.Client()
out_dir = Path("data/raw/full")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. Load addresses từ dictionary
with open("src/nl2sparql/linking/dictionary/entities.json") as f:
    entities = json.load(f)
addresses = list({e["address"].lower() for e in entities})
print(f"Loaded {len(addresses)} labeled addresses")

# 2. Compute date range
end_date = date.today() - timedelta(days=2)  # tránh chain lag
start_date = end_date - timedelta(days=30)

# 3. Run extraction (xem SQL ở trên, parametrized)
config = bigquery.QueryJobConfig(
    query_parameters=[
        bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
        bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        bigquery.ArrayQueryParameter("addresses", "STRING", addresses),
    ]
)

# 4. Use pandas-gbq for streaming download (large)
sql_transactions = """..."""  # xem trên
job = client.query(sql_transactions, job_config=config)
df = job.result().to_dataframe(create_bqstorage_client=True)
df.to_csv(out_dir / "transactions.csv", index=False)
print(f"transactions: {len(df)} rows, ${job.total_bytes_billed / 1e12 * 5:.2f}")

# Tương tự cho blocks, token_transfers, contracts...

# 5. Manifest
manifest = {
    "extraction_date": str(date.today()),
    "data_period": {"start": str(start_date), "end": str(end_date)},
    "rows": {"transactions": len(df), ...},
    "bytes_billed": job.total_bytes_billed,
    "bigquery_cost_usd": job.total_bytes_billed / 1e12 * 5,
}
with open(out_dir / "manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)
```

### Cẩn thận ARRAY parameter limit

BigQuery có limit số phần tử trong `ARRAY` parameter (~10000). Nếu `addresses` >10000:

- **Cách 1 (đề xuất):** load addresses vào temp table:
  ```python
  client.load_table_from_dataframe(
      pd.DataFrame({"address": addresses}),
      "myproject.mydataset.labeled_addresses",
  )
  # Rồi JOIN trong SQL
  ```

- **Cách 2:** chia nhỏ addresses thành batches, query nhiều lần, concat kết quả.

### Save format

- CSV với header.
- `value` là `NUMERIC` → save dưới dạng string để giữ chính xác.
- Timestamp ISO format UTC.
- Encoding UTF-8.

## Rủi ro & note

- **Cost spike:** nếu sai filter → quét full table → vài trăm GB. Kiểm tra "Bytes processed" trong dry-run trước khi run thật.
  - Set `bigquery.QueryJobConfig(maximum_bytes_billed=100 * 10**9)` để abort nếu >100GB.
- **Memory:** to_dataframe() với 5M rows tốn vài GB RAM. Dùng `create_bqstorage_client=True` cho streaming, hoặc export trực tiếp qua GCS:
  ```python
  job = client.extract_table(
      table_ref, "gs://bucket/transactions-*.csv",
      job_config=bigquery.ExtractJobConfig(destination_format="CSV"),
  )
  ```
  Sau đó download GCS bằng `gsutil cp gs://bucket/transactions-*.csv ./`.

- **`value` overflow:** > `int64 max`. Lưu string, convert decimal trong RML.
- **Chain lag:** block mới nhất có thể chưa được sync trong public dataset (~ vài giờ chậm). Filter `end_date - 2` an toàn.

## Estimated effort

1-2 ngày.

## Trạng thái

`in-progress-local-scaffold`

Local scaffold đã sẵn sàng để chạy dry-run thật. Chưa mark done vì acceptance criteria chính cần BigQuery dry-run/live extraction và kiểm tra CSV thực tế.

## Evidence — 2026-06-28

- Branch: `feat/t2-3-bigquery-extraction`.
- Implemented files:
  - `src/nl2sparql/kg/extraction/full_extract.py`
  - `src/nl2sparql/kg/extraction/full_extract.sql`
  - `scripts/04_bigquery_full_extract.py`
  - `tests/unit/test_full_extract.py`
- Focused local verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_full_extract.py -q
  ```
  Result: `7 passed`.
- CLI help smoke:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run python scripts/04_bigquery_full_extract.py --help
  ```
  Result: exit `0`.
- Full local verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest -q
  ```
  Result: `117 passed, 45 warnings`.
- Whitespace verification:
  ```bash
  git diff --check
  ```
  Result: exit `0`.
