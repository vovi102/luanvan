# BigQuery Ethereum Pilot Edge Cases

This note records edge cases the T1.2 pilot extractor is expected to surface and
preserve for later RML mapping decisions.

## Contract Creation

Rows with `to_address` set to null represent contract creation transactions.
RML mapping should not force these rows into a normal sender-to-recipient edge;
instead they need either a created-contract relation or a nullable recipient.

## Zero-Value Calls

Transactions with `value = 0` are common contract calls without native ETH
transfer. They are still semantically important because token transfers, swaps,
or contract interactions can be represented through logs and related tables.

## Large Integer Values

Ethereum values and token amounts can exceed ordinary floating-point precision.
The pilot extractor writes Decimal values as strings so CSV round-trips do not
lose wei-level precision before RDF literal conversion.

## Zero Gas Price

Rows with `gas_price = 0` can appear in special execution contexts or after
schema changes. They should remain valid numeric literals instead of being
treated as missing values.

## Typed Transactions

`transaction_type` values other than `0` represent typed transactions such as
EIP-1559. Mapping and query templates should keep the type field available so
questions can distinguish legacy and typed transactions later.
