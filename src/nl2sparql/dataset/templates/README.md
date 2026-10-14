# Query Template Library

This directory contains the active T3.1 GoogleSQL template library for the
synthetic dataset pipeline. It contains 25 intents targeting the managed
BigQuery analytical layer. The approved 2026-10-14 coverage revision replaces
three unsupported-by-data flow intents with owner net native flow, native
recipient concentration and token counterparty diversity; it also tightens
native funding to successful positive-value transactions.

Template validation explicitly uses `ethereum_analytics_stage_a_v2.json`
(catalogue 1.1.0, CQ01–CQ34). The default `ethereum_analytics.json` remains
the byte-identical historical 1.0.0 catalogue for benchmark/model consumers.
CQ01–CQ30 keep their meanings; CQ31–CQ34 are GoogleSQL training extensions,
not retroactive changes to the ontology SPARQL questions. Catalogue support
does not establish non-empty data coverage.

Funding maps to CQ31, not the opposite-direction historical CQ29. Its token
timestamp can equal the funding timestamp and must be strictly before the
duration boundary; no causation, account ownership or within-block order is
claimed. New replacements map only to CQ32/CQ33/CQ34, not retired CQ13/CQ22/CQ26.

Historical v1 rows must be paired with their historical template snapshot;
the current bilingual renderer deliberately rejects v1 funding SQL drift.
Do not rewrite historical rows or loosen that guard to reuse the new patterns.

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
