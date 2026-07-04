# T2.5 SHACL Validation Scaffold Design

## Goal

Build a reproducible SHACL validation scaffold for the Ethereum KG without requiring the full Fuseki/TDB2 dataset. The scaffold validates small RDF fixture graphs locally, writes SHACL reports, summarizes violations, and leaves full KG validation as a later evidence step after T2.4 live materialization.

## Scope

Included:

- Create `src/nl2sparql/kg/validation/shapes.ttl` with SHACL Core shapes aligned to ontology v0.1.0.
- Create `src/nl2sparql/kg/validation/run_shacl.py` for local RDF validation, report writing, and violation summary generation.
- Add tests using small RDF fixtures. One fixture conforms; one fixture intentionally violates critical transaction constraints.
- Update `docs/tasks/phase-2-kg/05-shacl-validation.md` with scaffold evidence and pending live acceptance.

Excluded:

- Validating `data/processed/full/output.nt`.
- Querying Fuseki for live KG validation.
- Claiming violation percentages for the full KG.
- Running the T2.4 full materialization or TDB2 load.

## Shapes Contract

Shapes use namespace `https://thesis.example.org/eth-kg/` and property names from `docs/memory/03-ONTOLOGY_REFERENCE.md`.

Core shapes:

- `:TransactionShape`: targets `:Transaction`; requires one `:hasFrom`, one non-negative decimal `:hasValue`, one `xsd:dateTime :hasTimestamp`, one integer `:hasBlockNumber`, and at most one `:hasTo`. `:hasTo` remains optional for contract creation.
- `:BlockShape`: targets `:Block`; requires integer `:hasBlockNumber`, dateTime `:hasTimestamp`, optional `:hasMiner`, and integer `:hasTxCount` when present.
- `:AccountShape`: targets `:Account`; constrains labels, aliases, owner, and category to strings when present.
- `:ExchangeAccountShape`: targets `:ExchangeAccount`; requires `:hasLabel` and `:hasOwner`.
- `:TokenTransferShape`: targets `:TokenTransfer`; requires `:emittedInTransaction`, `:tokenTransferFrom`, `:tokenTransferTo`, `:transferredToken`, and decimal `:transferredAmount`.
- `:TokenContractShape`: targets `:TokenContract`; constrains token metadata strings/integers when present.

The scaffold does not require `sh:class :Account` for every account link because local fixture graphs may not include full RDFS inference for every address node. Range/class checks can be tightened after live KG validation if they do not create noisy false positives.

## Runner Design

`run_shacl.py` provides testable local functions:

- `parse_rdf_graph(path: Path, rdf_format: str | None = None) -> Graph`
- `run_shacl_validation(data_path, shapes_path, report_path, data_format=None, inference="rdfs") -> ShaclValidationResult`
- `summarize_validation_report(report_graph: Graph) -> list[ViolationSummary]`
- `write_violations_summary(summary_path, result, source_data_path, shapes_path) -> Path`

The CLI accepts:

- `--data`: local RDF file, default `data/processed/full/output.nt`
- `--shapes`: default `src/nl2sparql/kg/validation/shapes.ttl`
- `--report`: default `data/processed/full/shacl_report.ttl`
- `--summary`: default `src/nl2sparql/kg/validation/violations_summary.md`
- `--data-format`: optional override; defaults from file suffix
- `--allow-nonconform`: return exit 0 even when violations exist, useful for exploratory live validation

Default CLI behavior returns exit 1 on non-conformance, exit 0 on conformance, and writes both report and markdown summary.

## Testing

Tests cover:

- `shapes.ttl` parses and contains expected NodeShapes and ontology predicates.
- A conforming fixture graph validates cleanly and writes a report.
- A violating fixture graph fails validation and summary groups violations by path/message.
- CLI help exits cleanly.
- CLI returns 1 for non-conforming data unless `--allow-nonconform` is set.

Fixtures are small Turtle files under `tests/fixtures/shacl/`, independent from BigQuery, Fuseki, Docker, and full T2.4 artifacts.

## Documentation

The T2.5 task file will add a local scaffold section and evidence commands. Acceptance criteria for full KG validation remain unchecked until the live KG exists and validation is run against it.

## Risks

Full SHACL validation over 50M+ triples may be slow or memory-heavy. The scaffold therefore validates local files first, writes reusable reports, and keeps full validation as an explicit command rather than a test-suite action.
