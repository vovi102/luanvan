# T1.1 EthOn Pilot Design

## Goal

Load the official EthOn ontology into a local Fuseki dataset and prove that the
ontology can support the class, property, and subclass queries required by later
knowledge-graph tasks.

## Scope

T1.1 will commit the complete upstream `EthOn.ttl` file to the repository. The
pilot will parse it locally, derive human-readable class and property inventories,
upload it to a Fuseki dataset named `ethon-pilot`, and execute three smoke queries.

The task does not extend EthOn, enable inference, or add blockchain instance data.
Those concerns belong to later ontology and RML tasks.

## Source and Reproducibility

- Source: `https://raw.githubusercontent.com/ConsenSys/EthOn/master/EthOn.ttl`
- Repository path: `data/ontologies/EthOn.ttl`
- The complete upstream file is committed because it is only about 86.7 KB and
  removes a network dependency from tests and notebooks.
- The implementation records the upstream URL and a SHA-256 checksum so future
  updates are explicit and reviewable.
- The original namespace `http://ethon.consensys.net/` remains unchanged.

## Components

### Ontology helper module

`src/nl2sparql/kg/ontology/ethon_pilot.py` will provide focused functions to:

- parse a local EthOn Turtle file with `rdflib`;
- query ontology classes, object properties, datatype properties, and subclass
  relationships;
- render deterministic Markdown inventories for classes and properties;
- reject a missing, empty, or unparsable ontology with a descriptive exception.

The helper module owns reusable ontology logic. The notebook will call these
functions instead of duplicating SPARQL or Markdown generation code.

### Static query artifacts

`src/nl2sparql/kg/validation/ethon_smoke.sparql` will contain three independently
labelled queries:

1. OWL classes with optional labels.
2. OWL object properties with optional domains and ranges.
3. Explicit subclass relationships between OWL classes.

All three queries operate without an inference engine.

### Generated inventories

The committed files `ethon-classes.md` and `ethon-properties.md` will be generated
from the committed ontology and sorted by IRI for deterministic diffs. Each file
will include the source checksum and total item count.

### Fuseki notebook

`notebooks/02_ethon_pilot.ipynb` will:

1. Parse the committed ontology locally and display its triple count.
2. Generate and display the class/property inventories.
3. Create or replace the in-memory Fuseki dataset `ethon-pilot` through the
   administration endpoint.
4. Upload `EthOn.ttl` as Turtle.
5. execute the three smoke queries and assert that each result set is non-empty.

The base URL, admin user, and password will be configurable through environment
variables, with local-development defaults matching the existing Docker Compose
setup. Secrets will not be written to notebook output.

## Data Flow

The committed Turtle file is the single source of truth. Unit tests and the
notebook parse that same file. Inventory functions transform the RDF graph into
sorted Markdown, while the integration path uploads the unchanged Turtle bytes to
Fuseki and executes the same query text stored in the validation artifact.

## Error Handling

- Local parsing fails immediately for a missing, empty, or invalid Turtle file.
- Inventory generation fails if EthOn contains no OWL classes or no RDF
  properties, because an empty inventory would invalidate the pilot.
- Fuseki HTTP failures report the endpoint, status code, and response body without
  exposing credentials.
- Dataset creation is idempotent: an existing `ethon-pilot` dataset is cleared or
  recreated before upload so repeated notebook runs produce the same counts.
- Query verification fails when any of the three result sets is empty.

## Testing and Verification

Unit tests will verify:

- `EthOn.ttl` parses with `rdflib` and contains at least several hundred triples;
- the ontology exposes non-empty classes, object properties, datatype properties,
  and subclass relationships;
- Markdown inventories are deterministic and match the committed artifacts;
- the validation file contains exactly three parseable SPARQL queries;
- invalid ontology input produces a descriptive failure.

Integration verification will start the existing Fuseki Docker service, create
`ethon-pilot`, upload the committed ontology, run all three queries, and confirm
non-empty results. The full repository test suite and Ruff checks must pass before
T1.1 is marked done.

## Documentation and Completion

After verification, the implementation will update:

- `docs/tasks/phase-1-pilot/01-load-ethon.md` with the completion date and measured
  triple/class/property counts;
- `docs/memory/05-DECISION_LOG.md` with EthOn coverage, identified gaps, the source
  checksum, and the decision to retain EthOn for T1.3.

T1.1 is complete only when all ticket acceptance criteria are backed by fresh
local and Fuseki verification output.
