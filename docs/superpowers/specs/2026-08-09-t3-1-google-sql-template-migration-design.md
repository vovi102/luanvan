# T3.1 GoogleSQL Template Migration Design

## Context

The existing 25-template library was built before Pivot #1. Its taxonomy and
difficulty distribution remain useful, but every executable field assumes RDF,
ontology IRIs and Fuseki. T3.2 also consumes those legacy field names. Phase 3
must establish a clean GoogleSQL gold-query contract before generating any new
records.

## Goals

- Preserve stable template IDs/taxonomy while replacing executable semantics.
- Cover the accepted managed analytical relations and representative CQ shapes.
- Make typed slots, date bounds, schema links and CQ links machine-validatable.
- Prove every example parses within a deliberately smaller live byte budget.
- Execute examples once to catch result-schema and non-empty-policy failures.

## Non-goals

- Generate the 1,000 Stage A records; that is T3.2.
- Close dictionary coverage gaps for mixers/NFT/MEV.
- Benchmark full-month stress latency again.
- Preserve SPARQL output compatibility after the explicit Plan B pivot.

## Selected migration

Keep all 25 IDs, categories and 8/11/6 difficulty split. Replace
`sparql_template` with `sql_template`, `ontology_elements` with
`schema_elements`, and add `cq_ids` plus validation policy. `expected_columns`
become SQL aliases. Example slots use live June 2026 values and one-day fact
windows.

The alternative of maintaining dual SPARQL/SQL targets was rejected because it
would double validation paths and let downstream records mix dialects. Creating
entirely new IDs was also rejected because category/difficulty history and T3.2
distribution logic can be migrated safely under stable semantic IDs.

## SQL and slot contract

Templates are read-only GoogleSQL beginning with `SELECT` or `WITH`. They may
reference only fully qualified objects in
`nl2sparql-thesis.nl2sparql_analytics`. Fact queries call TVFs rather than raw
public tables. Projection aliases are explicit; no `SELECT *` or DDL/DML.

All fact templates include typed `date` slots for a half-open window. Entity
addresses are lowercase Ethereum literals. Owner/category/concept/token symbol
are validated strings and SQL-escaped by the renderer. Numeric slots have
closed ranges; `n` is capped to prevent large result transfer.

Slot types are `integer`, `date`, `decimal_wei`, `ethereum_address`,
`transaction_hash`, `block_number`, `token_symbol`, `entity_owner`,
`entity_category`, `concept_class`, and `duration_minutes`. Every placeholder
must exist in both `slots` and `example_fill`; unused example-fill keys are
rejected to keep generation inputs precise.

## Semantic coverage

`schema_elements` entries resolve against the T2-SQL-1 relation and field
catalog. `cq_ids` resolve against CQ01-CQ30 and document why a template exists.
Labels are joined through the enriched TVFs or stable label view, and role
predicates remain explicit.

Templates associated with catalog coverage gaps may remain in the library to
teach the query shape, but their example validation declares
`expect_non_empty=false` and records the gap. Unsupported CQ24 is excluded
because no correct SQL target exists.

## Validation architecture

A small validator loads both catalogs and validates structure, distribution,
SQL safety, placeholders, slot types/values, date spans, schema references and
CQ references offline. Rendering uses type-aware literal rules rather than
blindly trusting arbitrary strings.

Live mode first dry-runs all 25 examples. The initial 5/30 GiB proposal failed
closed because token TVFs also scan the historical contract dimension. A full
diagnostic dry run measured 21 queries below 0.33 GiB and four token queries at
12.80–13.38 GiB, 56.53 GiB total. The accepted evidence-based gate is therefore
20 GiB per template and 64 GiB for the library, while the per-query cap remains
well below the general 50 GiB contract.
Execution is a separate explicit flag, starts only after complete preflight,
disables cache, verifies returned column names and enforces per-template
non-empty policy. It records bytes and latency but does not rerun to improve
measurements.

## Testing and completion

Tests migrate before artifacts. They require no legacy field names, exact
distribution, safe bounded SQL, correct schema/CQ references, typed rendering,
live fake-client budgets/order/result handling, README and notebook migration.
Then live dry-run/execute evidence, full pytest, Ruff, format and whitespace
checks close the task.
