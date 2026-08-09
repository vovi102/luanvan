# Query Template Library

This directory contains the active T3.1 GoogleSQL template library for the
synthetic dataset pipeline. The 25 stable template IDs and their approved
difficulty/category distribution are preserved from the original taxonomy, but
the executable contract now targets the managed BigQuery analytical layer.

## Template contract v2

Each object in `templates.json` contains exactly these fields:

- `id`: stable `T_...` identifier.
- `name`: short human-readable label.
- `category`: one of the ten approved analytics families.
- `difficulty`: `easy`, `medium`, or `hard`.
- `slots`: typed placeholder definitions and optional bounds.
- `sql_template`: read-only Standard SQL rendered by the typed validator.
- `nl_seed`: natural-language seed using the same placeholders.
- `expected_columns`: aliases required in the result projection.
- `schema_elements`: canonical analytical catalog relations and fields.
- `cq_ids`: supported competency questions exercised by the template.
- `example_fill`: deterministic, bounded example values.
- `validation`: execution expectations such as whether a non-empty result is
  required.

Legacy `sparql_template` and `ontology_elements` fields are rejected. Every
query references the fully qualified `nl2sparql-thesis.nl2sparql_analytics`
dataset and uses its views or table-valued functions; direct access to public
source tables is not part of this contract.

## Slot types

The renderer supports these fail-closed slot types:

- `integer`
- `date`
- `decimal_wei`
- `ethereum_address`
- `transaction_hash`
- `block_number`
- `token_symbol`
- `entity_owner`
- `entity_category`
- `concept_class`
- `duration_minutes`

Values are validated before interpolation. Strings are quoted safely, integer
and decimal bounds are enforced, and fact-query date windows cannot be reversed
or exceed 31 days.

## Validation

Offline validation checks JSON shape, stable IDs, placeholder consistency,
difficulty/category coverage, expected aliases, schema and competency-question
references, safe read-only SQL, and managed-object usage:

```bash
uv run python scripts/08_validate_sql_templates.py
```

BigQuery dry-run validation compiles all rendered templates, disables cache
assumptions, and enforces the accepted 20 GiB/template and 64 GiB/library byte
budgets without executing them:

```bash
uv run python scripts/08_validate_sql_templates.py --live
```

Execution is opt-in and still applies the configured per-template and library
budgets:

```bash
uv run python scripts/08_validate_sql_templates.py --execute
```
