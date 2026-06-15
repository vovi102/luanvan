# BigQuery Ethereum Public Dataset Schema Summary

Dataset: `bigquery-public-data.crypto_ethereum`

This summary records the Phase 0 working schema for the four tables used by the
KG construction pipeline. Validate the live schema again before full extraction.

## `transactions`

Purpose: Ethereum transaction-level records.

Core columns for Phase 1/2:

- `hash`: transaction hash.
- `from_address`: sender address.
- `to_address`: receiver address; can be `NULL` for contract creation.
- `value`: transaction value as BigQuery `NUMERIC`.
- `gas`: gas limit.
- `gas_price`: gas price.
- `receipt_gas_used`: gas used after execution.
- `block_number`: containing block number.
- `block_timestamp`: transaction timestamp; always filter this column for cost control.
- `input`: calldata.
- `transaction_type`: transaction type when available.

## `blocks`

Purpose: block metadata for transaction grouping and time validation.

Core columns:

- `number`: block number.
- `hash`: block hash.
- `timestamp`: block timestamp.
- `miner`: miner / validator beneficiary address.
- `gas_used`: total gas used in block.

## `token_transfers`

Purpose: ERC token transfer events derived from logs.

Core columns:

- `transaction_hash`: parent transaction hash.
- `from_address`: sender address.
- `to_address`: receiver address.
- `value`: transferred token amount.
- `token_address`: token contract address.
- `block_timestamp`: event timestamp; filter this column for cost control.

## `contracts`

Purpose: contract metadata for address classification.

Core columns:

- `address`: contract address.
- `is_erc20`: whether the contract matches ERC-20 heuristics.
- `is_erc721`: whether the contract matches ERC-721 heuristics.
- `bytecode`: deployed bytecode.

## Cost-Control Query

Use dry-runs before extraction:

```sql
SELECT hash, from_address, to_address, value, block_timestamp
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE DATE(block_timestamp) BETWEEN '2024-01-01' AND '2024-01-31'
```

Never run exploratory queries on the public tables without a `block_timestamp`
filter.
