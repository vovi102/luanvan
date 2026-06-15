# T0.3 — BigQuery Ethereum Public Dataset Access

## Mục tiêu

Có Google Cloud account, kích hoạt BigQuery, query thử trên `bigquery-public-data.crypto_ethereum.transactions` thành công, hiểu cấu trúc bảng.

## Bối cảnh & lý do

BigQuery Ethereum là nguồn dữ liệu duy nhất cho cả Plan A (extract → KG) và Plan B (NL2SQL trực tiếp). Cần verify access + hiểu schema sớm.

## Phụ thuộc

- (không có)

## Đầu vào

- Google account.
- Tham khảo schema: https://console.cloud.google.com/bigquery?project=bigquery-public-data&p=bigquery-public-data&d=crypto_ethereum

## Đầu ra

- Google Cloud project tạo xong, BigQuery enabled.
- File `src/nl2sparql/kg/extraction/bq_schema.md` ghi tóm tắt schema 4 bảng chính: `transactions`, `blocks`, `token_transfers`, `contracts`.
- Notebook `notebooks/01_bigquery_smoke.ipynb` chạy 3 query test, in DataFrame.
- Service account JSON key được lưu local (path ghi vào `.env`, KHÔNG commit).

## Acceptance criteria

- [x] Authenticate được vào BigQuery từ Python (`google-cloud-bigquery`).
- [x] Query `SELECT COUNT(*) FROM bigquery-public-data.crypto_ethereum.transactions WHERE DATE(block_timestamp) = '2024-01-01'` trả về số.
- [x] Bảng schema 4 bảng đã được ghi vào `bq_schema.md`.
- [x] Estimate chi phí cho extraction 1 tháng dữ liệu (xem hướng dẫn dưới).

## Hướng dẫn triển khai

1. **Tạo Google Cloud project:**
   - Vào https://console.cloud.google.com/.
   - Project name: `nl2sparql-thesis` (hoặc tên user prefer).
   - Bật BigQuery API.

2. **Service account:**
   - IAM & Admin → Service Accounts → Create.
   - Role: BigQuery User (đủ cho query public dataset).
   - Tạo key JSON, download.
   - Lưu vào `~/.gcp/nl2sparql-key.json` (KHÔNG commit).
   - Set env var: `export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/nl2sparql-key.json`.

3. **Cài client:**
   ```bash
   pip install google-cloud-bigquery pandas-gbq
   ```

4. **Smoke notebook `notebooks/01_bigquery_smoke.ipynb`:**
   ```python
   from google.cloud import bigquery
   client = bigquery.Client()

   query = """
   SELECT COUNT(*) AS n
   FROM `bigquery-public-data.crypto_ethereum.transactions`
   WHERE DATE(block_timestamp) = '2024-01-01'
   """
   print(client.query(query).to_dataframe())
   ```

5. **Đọc schema 4 bảng và ghi `src/nl2sparql/kg/extraction/bq_schema.md`:**
   - `transactions` — các cột chính: `hash`, `from_address`, `to_address`, `value`, `gas`, `block_number`, `block_timestamp`, `input`, `transaction_type`.
   - `blocks` — `number`, `hash`, `timestamp`, `miner`, `gas_used`.
   - `token_transfers` — `transaction_hash`, `from_address`, `to_address`, `value`, `token_address`, `block_timestamp`.
   - `contracts` — `address`, `is_erc20`, `is_erc721`, `bytecode`.

6. **Estimate cost cho 1 tháng:**
   ```sql
   -- Dry-run để estimate bytes
   SELECT *
   FROM `bigquery-public-data.crypto_ethereum.transactions`
   WHERE DATE(block_timestamp) BETWEEN '2024-01-01' AND '2024-01-31'
   ```
   Trong BigQuery UI có "This query will process X GB". 1 tháng tx ≈ 30-50 GB.
   Free tier: 1 TB/tháng. → đủ.

   **Quan trọng:** chỉ select các cột cần (giảm cost). Ví dụ:
   ```sql
   SELECT `hash`, from_address, to_address, value, block_timestamp
   FROM ...
   ```

7. **Document chi phí estimate vào `05-DECISION_LOG.md`.**

## Rủi ro & note

- **Free tier reset hàng tháng** — không cần lo cho 1 lần extract.
- **Billing alert:** set ngưỡng $10 để chắc chắn không vượt free tier do nhầm.
- **Query mà không filter `block_timestamp`** → quét toàn bảng, có thể hết quota. **LUÔN filter timestamp.**
- **NULL `to_address`:** xảy ra với contract creation tx. Phải handle khi extract.
- **`value` cột là `NUMERIC`:** chính xác, nhưng pandas có thể convert thành object string. Cần `pd.to_numeric` hoặc giữ string đến RML.

## Estimated effort

0.5-1 ngày (phần lớn là setup billing/IAM).

## Trạng thái

`completed — BigQuery credentials verified and smoke test passed as of 2026-06-14`

Đã hoàn thành:

- `src/nl2sparql/kg/extraction/bigquery_smoke.py`
- `scripts/01_bigquery_smoke.py`
- `src/nl2sparql/kg/extraction/bq_schema.md`
- `notebooks/01_bigquery_smoke.ipynb`
- Unit tests cho table constants, query date filter, dry-run query và `QueryJobConfig`.

Verification đã pass:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_bigquery_smoke.py -q
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src tests scripts
set -a; source .env; set +a; UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run python scripts/01_bigquery_smoke.py
```

Kết quả BigQuery smoke thật:

```text
transactions_2024_01_01=1101465
dry_run_bytes=6481683600
dry_run_gib=6.04
```

Credentials local đang được cấu hình qua `.env` với key nằm trong `.local/gcp/`, thư mục này được ignore và không commit.
