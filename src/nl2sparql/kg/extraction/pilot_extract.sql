-- Pilot BigQuery extraction for T1.2.
-- Date slice: 2024-01-15.

-- transactions_pilot.csv
SELECT
  `hash`, from_address, to_address, value, gas, gas_price,
  block_number, block_timestamp, transaction_type, receipt_status
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE DATE(block_timestamp) = '2024-01-15'
LIMIT 100;

-- blocks_pilot.csv
SELECT number, `hash`, timestamp, miner, gas_used, gas_limit, transaction_count
FROM `bigquery-public-data.crypto_ethereum.blocks`
WHERE DATE(timestamp) = '2024-01-15'
LIMIT 10;

-- token_transfers_pilot.csv
SELECT transaction_hash, from_address, to_address, value, token_address, block_timestamp
FROM `bigquery-public-data.crypto_ethereum.token_transfers`
WHERE DATE(block_timestamp) = '2024-01-15'
LIMIT 100;

-- contracts_pilot.csv
SELECT address, is_erc20, is_erc721, block_timestamp
FROM `bigquery-public-data.crypto_ethereum.contracts`
WHERE DATE(block_timestamp) = '2024-01-15'
LIMIT 50;
