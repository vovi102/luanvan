# T1.2 — Pilot: Extract 100 rows từ BigQuery

## Mục tiêu

Extract 100 transactions từ BigQuery Ethereum, save thành CSV, sanity-check dữ liệu.

## Bối cảnh & lý do

Bước pilot 2: verify pipeline BigQuery → CSV chạy được, hiểu format dữ liệu thực tế (NULL, decimals, edge cases).

## Phụ thuộc

- T0.3 — BigQuery access đã setup.

## Đầu vào

- Bảng `bigquery-public-data.crypto_ethereum.transactions`.
- Bảng phụ: `blocks`, `token_transfers`, `contracts` (lấy mẫu nhỏ).

## Đầu ra

- File `src/nl2sparql/kg/extraction/pilot_extract.sql` chứa SQL.
- File `src/nl2sparql/kg/extraction/pilot_extract.py` chứa Python script.
- 4 file CSV trong `data/raw/pilot/`:
  - `transactions_pilot.csv` (100 rows).
  - `blocks_pilot.csv` (10 rows tương ứng).
  - `token_transfers_pilot.csv` (100 rows tự chọn).
  - `contracts_pilot.csv` (50 rows).
- Notebook `notebooks/03_bq_pilot.ipynb` exploratory analysis: `df.info()`, `df.describe()`, count NULLs, distribution `value`.

## Acceptance criteria

- [x] CSV có đủ 100/10/100/50 rows.
- [x] Không lỗi parse (encoding, delimiter).
- [x] Identify ≥3 edge cases (zero-value, large integer, typed transaction).
- [x] Document trong `src/nl2sparql/kg/extraction/edge_cases.md`.

## Hướng dẫn triển khai

1. **SQL pilot — `pilot_extract.sql`:**
   ```sql
   -- transactions_pilot.csv: 100 rows từ 1 ngày
   SELECT
     hash, from_address, to_address, value, gas, gas_price,
     block_number, block_timestamp, transaction_type, receipt_status
   FROM `bigquery-public-data.crypto_ethereum.transactions`
   WHERE DATE(block_timestamp) = '2024-01-15'
   LIMIT 100;
   ```

2. **Python script `pilot_extract.py`:**
   ```python
   from google.cloud import bigquery
   import pandas as pd
   from pathlib import Path

   client = bigquery.Client()
   out_dir = Path("data/raw/pilot")
   out_dir.mkdir(parents=True, exist_ok=True)

   queries = {
       "transactions_pilot.csv": """
           SELECT hash, from_address, to_address, value, gas, gas_price,
                  block_number, block_timestamp, transaction_type, receipt_status
           FROM `bigquery-public-data.crypto_ethereum.transactions`
           WHERE DATE(block_timestamp) = '2024-01-15' LIMIT 100""",
       "blocks_pilot.csv": """
           SELECT number, hash, timestamp, miner, gas_used, gas_limit, transaction_count
           FROM `bigquery-public-data.crypto_ethereum.blocks`
           WHERE DATE(timestamp) = '2024-01-15' LIMIT 10""",
       "token_transfers_pilot.csv": """
           SELECT transaction_hash, from_address, to_address, value, token_address, block_timestamp
           FROM `bigquery-public-data.crypto_ethereum.token_transfers`
           WHERE DATE(block_timestamp) = '2024-01-15' LIMIT 100""",
       "contracts_pilot.csv": """
           SELECT address, is_erc20, is_erc721, block_timestamp
           FROM `bigquery-public-data.crypto_ethereum.contracts`
           WHERE DATE(block_timestamp) = '2024-01-15' LIMIT 50""",
   }

   for fname, q in queries.items():
       df = client.query(q).to_dataframe()
       df.to_csv(out_dir / fname, index=False)
       print(f"{fname}: {len(df)} rows, columns={list(df.columns)}")
   ```

3. **Exploratory notebook** — chạy:
   ```python
   import pandas as pd
   tx = pd.read_csv("data/raw/pilot/transactions_pilot.csv")
   tx.info()
   tx.describe()
   tx.isnull().sum()
   tx['value'].describe()
   tx[tx['to_address'].isnull()].head()  # contract creations
   ```

4. **Edge cases cần document:**
   - `to_address` NULL → contract creation.
   - `value` = 0 → contract calls without ETH transfer.
   - `value` cực lớn → big transfer (cần xử lý overflow).
   - `gas_price` = 0 → có thể gặp với MEV/private mempool.
   - `transaction_type` ≠ "0" → EIP-1559 transactions có format khác.

5. **Note vào `edge_cases.md`:** mỗi edge case 1 đoạn ngắn + cách handle dự kiến trong RML mapping.

## Rủi ro & note

- **`value` cột là `NUMERIC`** trong BigQuery → pandas convert thành `decimal.Decimal`. Khi save CSV: phải convert sang string để giữ chính xác.
- **Timestamp** là `TIMESTAMP` BigQuery → pandas thành `datetime64[ns, UTC]`. CSV save thành ISO string.
- **DON'T forget filter `DATE(block_timestamp)`** — không filter sẽ scan toàn bảng (vài trăm GB).
- **100 rows = vài KB** — chi phí không đáng kể, nhưng giúp verify pipeline trước Phase 2.

## Estimated effort

0.5 ngày.

## Trạng thái

`done — 2026-06-20`

Kết quả pilot ngày `2024-01-15`:

- Dry-run: tổng `0.50 GiB` cho 4 query.
- CSV: transactions `100`, blocks `10`, token transfers `100`, contracts `50` rows.
- Edge cases quan sát được: `80` zero-value transactions, `19` values vượt vùng số
  nguyên chính xác IEEE-754, `93` typed transactions.
- Dữ liệu pilot nằm trong `data/raw/pilot/` và được `.gitignore`; chỉ code, SQL,
  notebook và tài liệu được commit.

Verification:

```bash
uv run pytest -q
uv run ruff check src tests scripts
```
