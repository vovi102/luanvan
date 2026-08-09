# BigQuery analytical-layer options

Researched 2026-08-09 against Google Cloud's official BigQuery documentation only.

## Research conclusion

Use a **table function (TVF)** for a reusable analytical endpoint that needs
caller-supplied date bounds. Use a logical view only for a fixed, parameterless
base projection. A logical view **cannot reference query parameters**; a TVF is
specifically the view-like BigQuery object that can accept parameters.

```sql
CREATE OR REPLACE TABLE FUNCTION `project.dataset.transfers_between`(
  start_date DATE,
  end_date DATE
) AS (
  SELECT
    block_timestamp,
    SAFE_CAST(value AS BIGNUMERIC) AS value_bignumeric,
    from_address,
    to_address
  FROM `project.dataset.token_transfers`
  WHERE DATE(block_timestamp) >= start_date
    AND DATE(block_timestamp) < end_date
);
```

If the base table is partitioned by a `DATE` column, prefer filtering that
column directly (for example, `block_date >= start_date AND block_date <
end_date`) instead of wrapping a `TIMESTAMP` at query time.

## Findings

1. **Logical views are not parameterized.** Google explicitly lists “You cannot
   reference query parameters in views” among view limitations. Querying a
   logical view expands and re-executes its underlying SQL, so it remains useful
   as a stable, parameterless semantic layer, not as the date-range API.
   [Create logical views](https://cloud.google.com/bigquery/docs/views) and
   [logical-view overview](https://cloud.google.com/bigquery/docs/logical-materialized-view-overview).

2. **TVFs accept typed scalar parameters, including `DATE`.** A TVF returns the
   result of a `SELECT` and can be used anywhere a table is valid. The official
   examples pass scalar arguments into `WHERE`; therefore `start_date DATE,
   end_date DATE` is the appropriate interface. Parameters must be named
   differently from referenced columns to avoid ambiguity. TVFs cannot run DDL
   or DML (the body must be `SELECT`) and must be in the same location as their
   referenced tables. [Table functions](https://cloud.google.com/bigquery/docs/table-functions).

3. **Partition pruning must be designed into the TVF/view body.** BigQuery
   prunes only when it can determine partitions from a qualifying filter.
   Keep the partition column on one side of a comparison and use a constant or
   supplied scalar bound; avoid arithmetic/unsupported functions over the
   partition column. `require_partition_filter` applies to queries through
   views and materialized views too, so a view cannot bypass it. Validate the
   actual scan with a dry run. [Query partitioned tables](https://cloud.google.com/bigquery/docs/querying-partitioned-tables).

4. **Cost guardrails belong to the invoking query job.** Set
   `maximum_bytes_billed` / `maximumBytesBilled`; BigQuery estimates bytes
   before execution and fails without charge when the estimate exceeds the
   limit. For clustered tables that estimate is an upper bound, so a query can
   be rejected even if its eventual actual bytes would have been lower. A dry
   run validates the query and returns an estimate, uses no slots, and is free;
   an external/federated source can report a zero lower bound, so do not treat
   it as a guarantee. [Estimate and control costs](https://cloud.google.com/bigquery/docs/best-practices-costs) and
   [Run a query / dry run](https://cloud.google.com/bigquery/docs/running-queries).

5. **`token_transfers.value` as `STRING`: use `SAFE_CAST(... AS BIGNUMERIC)`
   when bad or out-of-range values must not abort the analytical query.**
   `SAFE_CAST` turns runtime conversion errors into `NULL` (invalid casts that
   fail static analysis still fail). `BIGNUMERIC` avoids the much smaller
   `NUMERIC` range, but it is still finite; expose/monitor `value IS NOT NULL
   AND value_bignumeric IS NULL` if malformed values need data-quality
   accounting. Do not cast to `FLOAT64` for token quantities because the
   official conversion rules warn it can lose precision. [Conversion functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/conversion_functions).

## Practical shape

- Keep a logical view for normalized columns, including the `SAFE_CAST` result
  and an `is_valid_value` flag if it is broadly useful.
- Put date arguments and the partition predicate in a TVF over that layer (or
  directly over the base table when that gives the clearest pruning plan).
- Every client call should use query parameters for the *TVF invocation* and
  set a per-job `maximum_bytes_billed`; run dry-run checks for representative
  date spans before setting the production cap.

The documentation establishes the object semantics and cost/pruning rules; the
actual number of bytes scanned must still be measured against the project's
specific table partitioning, clustering, and TVF SQL.

## Project-specific live observations

The following read-only checks used `bq show`, `bq ls`, and `bq query
--dry_run` against project `nl2sparql-thesis` on 2026-08-09:

- `transactions`, `blocks`, `token_transfers`, and `contracts` are native
  `DAY`-partitioned tables in the `US` location. Their partition columns are
  `block_timestamp`, `timestamp`, `block_timestamp`, and `block_timestamp`,
  respectively.
- The public dataset also exposes `amended_tokens`, a maintained logical view
  that deduplicates `tokens` by address and overlays first-party amendment
  data. It supplies `address`, `symbol`, `name`, and `decimals`, covering the
  token metadata required by competency questions CQ08, CQ15, and CQ25.
- `token_transfers.value` and token `decimals` are strings. The analytical
  contract must preserve the raw value, expose a safe numeric projection, and
  make cast failures observable rather than silently treating them as zero.
- The existing project table
  `nl2sparql-thesis.nl2sparql_kg.labeled_addresses` has only one nullable
  `address` column, 4,520 rows, and an expiration time of 2026-08-31. It is an
  extraction filter from the pre-remediation snapshot, not a reusable label
  dimension.
- The accepted local dictionary now contains 5,135 entities and 8,538 aliases.
  Its entity artifact SHA-256 is
  `190f73a91b7affa8b8396cc189e4a6b332dc6f7f0109037a0d44edb14531c536`.

Representative dry runs over the pinned evaluation slice produced these
estimates without executing billable queries:

| Query shape | Estimated bytes |
|---|---:|
| Transactions joined to blocks | 17,351,046,284 |
| Transactions joined to the legacy address filter | 10,758,865,404 |
| Token transfers joined to contracts | 23,126,681,624 |
| Token transfers joined to `amended_tokens` | 17,655,509,985 |

These observations rule out treating the legacy address-only table as the
semantic dimension. A new versioned label dimension is required before
label-enriched analytical routines can meet the current dictionary contract.
