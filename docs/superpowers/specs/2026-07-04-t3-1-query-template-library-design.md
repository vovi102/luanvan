# T3.1 Query Template Library Design

## Goal

Create a reproducible SPARQL query template library for Phase 3 synthetic dataset generation. The library should cover common Ethereum analytics intents, expose typed slots for T3.2 sampling, and be validated offline for structure and coverage.

## Scope

Included:

- Add `src/nl2sparql/dataset/templates/templates.json` with at least 25 templates.
- Add `src/nl2sparql/dataset/templates/README.md` documenting template schema, slot types, and validation expectations.
- Add `notebooks/07_template_validate.ipynb` as an unexecuted local validation notebook skeleton.
- Add unit tests for template schema, uniqueness, difficulty/category coverage, SPARQL placeholder consistency, and ontology element references.
- Update the T3.1 task file with scaffold evidence.

Excluded:

- Running each template against Fuseki.
- Guaranteeing non-empty result sets for every fill-in.
- Synthetic data generation, paraphrasing, or slot sampling implementation for T3.2.

## Template Contract

Each template is a JSON object with:

- `id`: stable uppercase identifier.
- `name`: short human-readable label.
- `category`: one of the T3.1 categories.
- `difficulty`: `easy`, `medium`, or `hard`.
- `slots`: mapping from slot name to slot metadata.
- `sparql_template`: canonical SPARQL with Python format placeholders.
- `nl_seed`: natural-language seed question using the same placeholders.
- `expected_columns`: result variable names, or `["ask"]` for ASK queries.
- `ontology_elements`: local ontology classes/properties used by the query.
- `example_fill`: one deterministic fill-in for offline formatting and future Fuseki validation.

Minimum distribution:

- At least 25 templates.
- Difficulty: at least 30% easy, 40% medium, 20% hard.
- Category: at least 6 categories.

## Testing

Offline tests will validate:

- `templates.json` parses as a non-empty list with unique IDs.
- Count/distribution acceptance for scaffold.
- Required fields and supported difficulty/category values.
- Every `{slot}` in `sparql_template` and `nl_seed` exists in `slots` and `example_fill`.
- Every `expected_columns` item appears in the SELECT projection unless the query is ASK.
- Every ontology element starts with `:`.
- README exists and documents slot types.
- Notebook exists, is unexecuted, and references the template file and Fuseki validation flow.

## Documentation

T3.1 task status becomes `scaffold done; Fuseki execution pending`. Acceptance for running every template on Fuseki remains unchecked until the live KG exists.
