# Query Template Library

This directory contains the T3.1 SPARQL template library used by the synthetic
dataset pipeline. Templates are stored in `templates.json` so later stages can
sample slot values, render SPARQL, and generate natural-language questions.

## Template schema

Each template object has these fields:

- `id`: stable `T_...` identifier.
- `name`: short human-readable label.
- `category`: analytics family such as `entity_lookup`, `top_k`, or `multi_hop`.
- `difficulty`: one of `easy`, `medium`, or `hard`.
- `slots`: mapping from placeholder name to slot metadata.
- `sparql_template`: canonical SPARQL string rendered with Python `str.format`.
- `nl_seed`: natural-language seed using the same placeholders.
- `expected_columns`: result variables expected from the SELECT projection.
- `ontology_elements`: local ontology classes/properties referenced by the query.
- `example_fill`: deterministic fill-in used for offline formatting and future Fuseki checks.

## Slot types

Supported slot types for T3.1 are:

- `integer`
- `date`
- `decimal_wei`
- `ethereum_iri`
- `transaction_iri`
- `token_symbol`
- `entity_owner`
- `entity_category`
- `concept_class`

T3.2 may extend the slot sampler, but new slot types should be documented here
and covered by tests before use.

## Validation

Offline validation checks JSON shape, placeholder consistency, difficulty and
category coverage, expected SELECT columns, ontology element notation, and the
unexecuted notebook contract.

Live validation requires Fuseki and a loaded KG:

1. Load `templates.json`.
2. Render each `sparql_template` with `example_fill`.
3. Submit the rendered query to the Fuseki `/eth-kg/sparql` endpoint.
4. Record whether the query executes and whether it returns plausible rows.

Live Fuseki execution is pending until the full T2.4 KG materialization and load
are complete.
