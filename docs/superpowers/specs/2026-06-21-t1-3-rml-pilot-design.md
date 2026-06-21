# T1.3 RML Pilot Design

## Goal

Prove that Morph-KGC can transform the existing BigQuery pilot CSV data into a
queryable RDF graph. The pilot must materialize at least 500 triples, load them
into the Fuseki `pilot-kg` dataset, and pass the three SPARQL checks defined by
T1.3.

## Scope

The pilot maps `transactions_pilot.csv` and `blocks_pilot.csv`. The extracted
`token_transfers_pilot.csv` and `contracts_pilot.csv` files remain inputs for
later Phase 2 work and are not mapped in T1.3.

Generated CSV and RDF files remain ignored by Git. The repository stores only
the mapping, runner, notebook, tests, and reproducible result documentation.

## Architecture

`pilot_mapping.ttl` is the authoritative RML definition. It contains one
triples map for transactions and one for blocks, using paths relative to the
repository root. Morph-KGC reads that mapping and returns an `rdflib.Graph`.

`run_morph_pilot.py` provides small, testable functions to:

1. resolve and validate the mapping and required CSV paths;
2. build the Morph-KGC configuration;
3. materialize the graph;
4. serialize Turtle output;
5. parse the serialized file again and enforce the 500-triple minimum.

`notebooks/04_rml_pilot.ipynb` uses the existing Fuseki pilot client pattern to
create or replace `pilot-kg`, upload the generated Turtle file, and execute the
three acceptance queries.

## RDF Model

All generated resources use `https://thesis.example.org/eth-kg/`.

- A transaction is `tx/{hash}`, typed as `:Transaction`.
- A block is `block/{number}`, typed as `:Block`.
- Sender and recipient addresses are `addr/{address}` IRIs.
- Transaction predicates cover sender, optional recipient, value, gas,
  timestamp, and block number.
- Block predicates cover block number, timestamp, miner, gas used, gas limit,
  and transaction count.
- Wei values use `xsd:decimal`, integer measurements use `xsd:integer`, and
  timestamps use `xsd:dateTime`.

Morph-KGC must omit the recipient triple when `to_address` is empty. It must
never generate an `addr/None`, `addr/nan`, or empty-address resource.

## Data Flow

The ignored pilot CSV files are copied from the completed T1.2 workspace into
the T1.3 worktree before local verification. The runner reads them in place,
materializes the graph, and writes `data/processed/pilot/output.ttl`.

The notebook then uploads that file into a replaceable local Fuseki dataset.
It compares SPARQL results against values calculated from the CSV sources:

1. transaction count is exactly 100;
2. transactions above one ETH match the CSV-derived count;
3. the grouped sender results match the CSV-derived top senders.

## Error Handling

The runner fails with a clear path-specific error when the mapping or a required
CSV file is missing. It propagates Morph-KGC mapping/materialization failures,
rejects RDF that cannot be parsed after serialization, and rejects a graph with
fewer than 500 triples.

Fuseki operations fail on non-success HTTP responses. Notebook assertions make
query mismatches visible instead of recording a successful-looking run with
incorrect data.

## Testing and Verification

Development follows test-driven development.

- Unit tests verify required-file validation, Morph-KGC configuration, output
  serialization, minimum triple enforcement, and required mapping semantics.
- A small fixture-based integration test invokes Morph-KGC itself and verifies
  parseable RDF, datatype preservation, and omission of missing recipients.
- The real pilot run verifies the ignored 100-row and 10-row CSV inputs and a
  graph of at least 500 triples.
- The notebook is executed non-interactively against local Fuseki and must pass
  all three SPARQL assertions.
- The full unit test suite and Ruff must pass before completion.

## Deliverables

- `src/nl2sparql/kg/rml/pilot_mapping.ttl`
- `src/nl2sparql/kg/rml/run_morph_pilot.py`
- `data/processed/pilot/output.ttl` as an ignored generated artifact
- `notebooks/04_rml_pilot.ipynb`
- automated tests for the mapping and runner
- updated T1.3 task status, acceptance checkboxes, verification evidence, and
  Morph-KGC decision record

